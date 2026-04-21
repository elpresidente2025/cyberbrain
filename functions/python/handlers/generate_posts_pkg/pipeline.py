"""
generatePosts Python onCall handler.

Node `handlers/posts.js`의 generatePosts 엔트리 역할을 Python으로 이관한다.
핵심 생성 로직은 기존 Step Functions 파이프라인(`pipeline_start` + Cloud Tasks)을 재사용한다.
"""

from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
import html
import json
import logging
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, Optional

from firebase_admin import firestore
from firebase_functions import https_fn

from agents.common.election_rules import check_election_eligibility
from agents.common.aeo_config import get_conclusion_archetype
from agents.common.editorial import KEYWORD_SPEC, QUALITY_SPEC, STRUCTURE_SPEC
from agents.common.h2_repair import (
    build_subheading_role_surface as _h2_repair_build_subheading_role_surface,
)
from agents.common.person_naming import (
    ROLE_TOKEN_PRIORITY,
    canonical_role_label,
    clean_full_name_candidate,
    extract_keyword_person_role,
    is_same_speaker_name,
    normalize_person_name,
)
from agents.common.poll_citation import build_poll_citation_text
from agents.common.role_keyword_policy import (
    ROLE_KEYWORD_PATTERN as COMMON_ROLE_KEYWORD_PATTERN,
    ROLE_SURFACE_PATTERN as COMMON_ROLE_SURFACE_PATTERN,
    build_role_keyword_intent_anchor_text,
    build_role_keyword_intent_text,
    build_role_keyword_policy,
    extract_person_role_facts_from_text as extract_person_role_facts_from_text_common,
    extract_role_keyword_parts,
    is_role_keyword_intent_surface,
    order_role_keyword_intent_anchor_candidates,
    normalize_role_label as normalize_role_label_common,
    roles_equivalent as roles_equivalent_common,
)
from agents.common.section_contract import (
    extract_career_fact_signature as extract_career_fact_signature_common,
    find_section_semantic_mismatch,
    extract_policy_evidence_signature as extract_policy_evidence_signature_common,
    should_apply_section_lane_contracts,
    should_apply_cross_section_contracts,
    split_sentences as split_section_contract_sentences,
    validate_cross_section_contracts,
)
from agents.common.stance_filters import looks_like_hashtag_bullet_line
from agents.core.structure_normalizer import (
    _join_sections,
    _pad_short_section,
    _plain_len,
    _split_into_sections,
    normalize_section_p_count,
)
from agents.core.subheading_agent import SubheadingAgent
from services.authz import is_admin_user, is_tester_user
from services.memory import get_recent_selected_titles
from services.posts.content_processor import (
    cleanup_post_content,
    remove_grammatical_errors,
    repair_duplicate_particles_and_tokens,
)
from services.posts.profile_loader import (
    get_or_create_session,
    increment_session_attempts,
    load_user_profile,
    peek_active_generation_session,
    remember_session_generated_title,
)
from services.posts.output_formatter import (
    build_keyword_validation,
    count_without_space,
    finalize_output,
    insert_donation_info,
    insert_poll_citation,
    insert_slogan,
    normalize_ascii_double_quotes,
    normalize_book_title_notation,
    strip_generated_addons,
    strip_generated_poll_citation,
)
from services.posts.poll_fact_guard import (
    build_poll_matchup_fact_table,
    enforce_poll_fact_consistency,
)
from services.posts.poll_focus_bundle import build_poll_focus_bundle
from services.system_config import get_test_mode_config
from services.posts.validation import (
    enforce_repetition_requirements,
    enforce_keyword_requirements,
    find_shadowed_user_keywords,
    force_insert_preferred_exact_keywords,
    force_insert_insufficient_keywords,
    repair_date_weekday_pairs,
    run_heuristic_validation_sync,
    validate_keyword_insertion,
)

logger = logging.getLogger(__name__)

DEFAULT_TARGET_WORD_COUNT = 2000
# onCall timeout(1200s) 대비 후처리 여유를 남기기 위해 파이프라인 폴링 상한을 17분으로 확장.
MAX_POLL_TIME_SECONDS = 17 * 60
POLL_INTERVAL_SECONDS = 0.8
KST = ZoneInfo("Asia/Seoul")

CATEGORY_MIN_WORD_COUNT = {
    "local-issues": 2000,
    "policy-proposal": 2000,
    "activity-report": 2000,
    "current-affairs": 2000,
    "daily-communication": 2000,
}
ROLE_MENTION_PATTERN = re.compile(
    rf"([가-힣]{{2,8}})\s*(현\s*)?({COMMON_ROLE_SURFACE_PATTERN})",
    re.IGNORECASE,
)
ROLE_KEYWORD_PATTERN = COMMON_ROLE_KEYWORD_PATTERN
SEARCH_KEYWORD_CONTEXT_PATTERN = re.compile(r"^(?:검색어|키워드|표현|문구)")
QUOTE_CHAR_PATTERN = re.compile(r"[\"'“”‘’]")
H2_TAG_PATTERN = re.compile(r"<h2\b[^>]*>([\s\S]*?)</h2\s*>", re.IGNORECASE)
PARAGRAPH_TAG_PATTERN = re.compile(r"<p\b[^>]*>([\s\S]*?)</p\s*>", re.IGNORECASE)
CONTENT_BLOCK_TAG_PATTERN = re.compile(r"<(?:h2|p)\b[^>]*>([\s\S]*?)</(?:h2|p)\s*>", re.IGNORECASE)
CONTENT_BLOCK_WITH_TAG_PATTERN = re.compile(
    r"<(?P<tag>h2|p)\b[^>]*>(?P<inner>[\s\S]*?)</(?P=tag)\s*>",
    re.IGNORECASE,
)
PERSON_ROLE_CHAIN_CANDIDATE_PATTERN = re.compile(
    r"(?:[가-힣]{2,8}\s*(?:국회의원|의원|위원장|장관|후보|시장)\s*){3,}",
    re.IGNORECASE,
)
PERSON_ROLE_PAIR_PATTERN = re.compile(
    r"([가-힣]{2,8})\s*(국회의원|의원|위원장|장관|후보|시장)",
    re.IGNORECASE,
)
NUMERIC_PERSON_CHAIN_CANDIDATE_PATTERN = re.compile(
    r"(?:\d{1,4}(?:\.\d+)?(?:%|명|일|월|년|회|건|개|시|분|p)?\s*){2,}(?:[가-힣]{2,8}\s*(?:국회의원|의원|위원장|장관|후보|시장)\s*){2,}",
    re.IGNORECASE,
)
_NUMERIC_UNIT_TOKEN_FRAGMENT = r"\d{1,4}(?:\.\d+)?(?:%|명|일|월|년|회|건|개|시|분|p)?"
_HTML_INLINE_GAP_FRAGMENT = r"(?:\s|&nbsp;|<[^>]+>)*"
_HTML_INLINE_SEPARATOR_FRAGMENT = r"(?:\s|&nbsp;|<[^>]+>)+"
INLINE_DECORATION_TAG_PATTERN = re.compile(r"</?(?:strong|em|span)\b[^>]*>", re.IGNORECASE)
NUMERIC_UNIT_RUN_PATTERN = re.compile(
    rf"(?<!\S){_NUMERIC_UNIT_TOKEN_FRAGMENT}(?:\s+{_NUMERIC_UNIT_TOKEN_FRAGMENT}){{4,}}(?!\S)",
    re.IGNORECASE,
)
DATETIME_ONLY_NUMERIC_RUN_PATTERN = re.compile(
    r"^(?:(?:\d{4}년)\s+)?\d{1,2}월\s+\d{1,2}일(?:\s+\d{1,2}시(?:\s+\d{1,2}분)?)?$"
)
LEADING_DATETIME_PREFIX_PATTERN = re.compile(
    r"^(?:(?:\d{4}년)\s+)?\d{1,2}월\s+\d{1,2}일(?:\s+\d{1,2}시(?:\s+\d{1,2}분)?)?"
)
INTEGRITY_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?。])\s+|\n+")
SUSPICIOUS_POLL_RESIDUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:(?:지난|최근)\s*)?(?:\d{1,2}일\s+){1,2}0\d{2,3}명"
        r"(?:\s+(?!(?:비전|정책|청사진|공약|리더십|메시지|방향))[가-힣]{2,8}"
        r"(?:\s*(?:의원|후보|시장|위원장|국회의원))?){0,2}",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:(?:지난|최근)\s*)?(?:\d{1,2}일\s+){1,2}\d{3,4}명"
        r"(?:\s+(?!(?:비전|정책|청사진|공약|리더십|메시지|방향))[가-힣]{2,8}"
        r"(?:\s*(?:의원|후보|시장|위원장|국회의원))?){2,}",
        re.IGNORECASE,
    ),
)
ABSTRACT_POLICY_NOUNS: tuple[str, ...] = (
    "비전",
    "정책",
    "청사진",
    "공약",
    "리더십",
    "메시지",
    "방향",
)
LOW_SIGNAL_RESIDUE_NOUNS: tuple[str, ...] = (
    *ABSTRACT_POLICY_NOUNS,
    "전략",
    "소통",
    "후보군",
    "구도",
    "쟁점",
)
STRUCTURAL_MATCHUP_RESIDUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:[가-힣]{1,8}도\s*)?후보군\s*(?=(?:[가-힣]{2,8}\s*(?:의원|후보|시장|위원장|국회의원)\s*){1,}"
        r"(?:비전|정책|청사진|공약|리더십|메시지|방향))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:[가-힣]{2,8}\s*(?:의원|후보|시장|위원장|국회의원)\s*){2,}"
        r"(?=(?:비전|정책|청사진|공약|리더십|메시지|방향))",
        re.IGNORECASE,
    ),
)
TARGETED_POLISH_HEADING_PATTERN = re.compile(
    r"(?:^|[,:\-]\s*|\s)(?:제가|저는)\s+(?:제시할\s+)?(?:비전|해법|대안|경쟁력|가능성|약속|역할|메시지|방향|해결책)은\?$",
    re.IGNORECASE,
)
TARGETED_POLISH_SENTENCE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?:상대 후보와의\s+)?(?:가상대결|양자대결|대결)에서\s+결과(?:는|가)\s+",
            re.IGNORECASE,
        ),
        "matchup_result_clause",
    ),
    (
        re.compile(
            r"(?:상대 후보와의\s+)?(?:가상 대결|양자 대결)에서\s+결과(?:는|가)\s+",
            re.IGNORECASE,
        ),
        "matchup_result_clause_spaced",
    ),
)
TARGETED_POLISH_NUMERIC_TOKEN_PATTERN = re.compile(
    r"[±]?\d{1,4}(?:,\d{3})*(?:\.\d+)?(?:%p|%|p|명)?",
    re.IGNORECASE,
)
SENTENCE_LIKE_UNIT_PATTERN = re.compile(r"(?:\d+\.\d+|[^.!?。])+(?:[.!?。](?!\d)|$)")
TARGETED_POLISH_MAX_CANDIDATES = 10
TARGETED_POLISH_MAX_TEXT_LENGTH = 180
TARGETED_POLISH_STYLE_FINGERPRINT_MIN_CONFIDENCE = 0.55
TARGETED_POLISH_STYLE_GUIDE_MAX_CHARS = 500
TARGETED_POLISH_STYLE_LIMITS: dict[str, dict[str, Any]] = {
    "light": {"max_sentences": 3, "max_ratio": "20%"},
    "medium": {"max_sentences": 6, "max_ratio": "30%"},
}
TARGETED_POLISH_JEONIM_RESERVED_SLOTS: dict[str, int] = {
    "light": 1,
    "medium": 2,
}
TARGETED_POLISH_EXCLUDED_MARKERS: tuple[str, ...] = (
    "후원계좌",
    "예금주",
    "영수증",
    "입금 후",
    "조사개요",
    "응답률",
    "신뢰수준",
    "중앙선거여론조사심의위원회",
    "전화면접",
    "ARS",
)
TARGETED_POLISH_INTRO_MARKERS: tuple[str, ...] = (
    "오늘 저는",
    "이 자리에 섰습니다",
    "여러분과 함께 나누겠습니다",
    "이번 결과를 겸허히",
    "이 자리를 빌려",
    "먼저 감사",
    "여러분께 말씀드리고자",
    "이번 선거를 통해",
)
TARGETED_POLISH_TRANSITION_MARKERS: tuple[str, ...] = (
    "하지만 저는",
    "무엇보다",
    "아울러",
    "나아가",
    "앞으로도",
    "이번 여론조사 결과는",
    "이를 위해 저는",
    "저는 앞으로",
    "저는 이미",
    "더불어",
    "또한 저는",
    "특히 저는",
    "이에 저는",
    "그래서 저는",
)
TARGETED_POLISH_CONCLUSION_MARKERS: tuple[str, ...] = (
    "감사합니다",
    "힘을 모아주십시오",
    "지지를 부탁드립니다",
    "기대해 주십시오",
    "함께라면 우리는",
    "약속드립니다",
    "여러분께 약속드립니다",
    "반드시 보답하겠습니다",
    "끝까지 함께하겠습니다",
)
TARGETED_POLISH_BOILERPLATE_MARKERS: tuple[str, ...] = (
    "가능성을 보여줍니다",
    "겸허히 받아들이고",
    "겸허히 받아들이며",
    "기대를 뛰어넘는",
    "더 나은 내일",
    "더 나은 미래",
    "더 나은 방향",
    "진정성",
    "낮은 자세로",
    "목소리에 귀 기울이고",
    "많은 관심과 지지",
    "열망을 현실로",
    "풍요로운 삶",
    "실질적인 변화를",
    "고무적인 일",
    "최선을 다하겠습니다",
    "반드시 실현하겠습니다",
    "함께 만들어 가겠습니다",
    "보다 나은 미래",
    "여러분의 목소리",
    "도전과 변화",
    "새로운 도약",
    "지역 발전을 위해",
    "미래를 열어가겠습니다",
    "책임지는 정치",
    "현장의 목소리",
    "기대에 부응",
    "소통하고 협력",
    "적극적으로 추진",
    "신뢰받는 정치인",
)
# 저는/제가 시작 반복 감지 (중간 본문 대상)
TARGETED_POLISH_JEONIM_START_RE = re.compile(r"^(?:저는|제가|저의)\s")
TARGETED_POLISH_BOILERPLATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"귀\s*기울이(?:는|고|며|어|여|았|었|왔|겠습니다|도록|려)", re.IGNORECASE),
    re.compile(r"겸허히\s+받아들이(?:며|고|겠)", re.IGNORECASE),
    re.compile(r"(?:더욱\s+)?낮은\s+자세로", re.IGNORECASE),
    re.compile(r"이러한\s+[^.!?]{0,36}(?:전달되|이어지|움직이)[^.!?]{0,16}", re.IGNORECASE),
    re.compile(r"이는\s+[^.!?]{2,40}(?:이어집니다|됩니다|요인입니다)", re.IGNORECASE),
    re.compile(
        r"(?:이러한|저의)\s+[^.!?]{0,32}(?:접근|배경|진심|전문성|실력|행보|노력)[^.!?]{0,24}마음을\s+움직이",
        re.IGNORECASE,
    ),
    re.compile(
        r"단순(?:히|한)\s+[^.!?]{0,48}"
        r"(?:(?:가|이|은|는)\s+(?:아니라|아닌)|"
        r"[을를]\s+넘어(?:서|섭니다|서며|섰|선)?|"
        r"에\s+그치지\s+않(?:고|습니다)|"
        r"머무르지\s+않(?:고|습니다)|"
        r"만이\s+아니라|"
        r"이론(?:적(?:인)?)?|"
        r"볼\s+수\s+없(?:습니다|다))",
        re.IGNORECASE,
    ),
    re.compile(
        r"단순(?:히|한)\s+[^.!?]{0,40}"
        r"(?:고향|약속|기업\s*경영|경제\s*지표|행정|구호|이론)"
        r"[^.!?]{0,24}(?:에만|로만|만으로|뿐|(?:가|이|은|는)\s+(?:아니라|아닌)|"
        r"[을를]\s+넘어(?:서|섭니다|서며|섰|선)?|에\s+그치지\s+않(?:고|습니다)|"
        r"머무르지\s+않(?:고|습니다))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:저의\s+)?이러한\s+[^.!?]{0,36}(?:진정성|접근|비전|실천\s*의지|전문성|실력|행보|노력)[^.!?]{0,24}전달되",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:단계별로\s+정리|(?:명확한\s+)?우선순위를\s+(?:명확히|설정)|"
        r"(?:필요한\s+)?자원(?:과)?\s+일정을?\s+현실적(?:으로)?\s+맞추|"
        r"즉시\s+보완|완성도를\s+높이)",
        re.IGNORECASE,
    ),
)
TARGETED_POLISH_POLICY_ACTION_RE = re.compile(
    r"(?:추진|확대|유치|창출|개선|지원|해결|약속|실현|모색|집중|강화|정비|점검|보완|제시|준비|만들겠|하겠|하겠습니다)",
    re.IGNORECASE,
)
TARGETED_POLISH_REASON_HINTS: dict[str, str] = {
    "heading_first_person_topic": "1인칭이 섞인 소제목을 더 기사형으로 정리",
    "matchup_result_clause": "깨진 가상대결 결과 문장을 자연스럽게 복원",
    "matchup_result_clause_spaced": "띄어쓰기와 조사 때문에 깨진 결과 문장을 복원",
    "ai_alternative_voice_overlay": "등록된 사용자 대체 표현을 우선 적용",
    "intro_voice_overlay": "도입부 1~2문장에 사용자 말맛을 일부 반영",
    "transition_voice_overlay": "문단 연결문을 덜 상투적으로 정리",
    "closing_voice_overlay": "마무리 문장을 사용자답게 다듬기",
    "boilerplate_voice_overlay": "AI스러운 상투 표현을 완화",
    "jeonim_voice_overlay": "본문 중간 '저는/제가' 반복 시작 패턴을 다양화",
}
_UNSUPPORTED_COMPARISON_FIRST_PERSON_RE = re.compile(
    r"(?:저는|제가|저의)(?:[^%。.!?\d]{2,60})(?:보다|에 비해|보다 더|더 나은|더 구체적|더 실질적|더 현실적)",
)
_UNSUPPORTED_COMPARISON_OPPONENT_CLAUSE_RE = re.compile(
    r"(?:와는|과는)\s*(?:달리|다르게|비해|차별화된)|"
    r"(?:와|과)\s*비교(?:했(?:을\s*때|을때|을\s*땐|을땐|을\s*경우|을경우)?|하면|해보면)",
)
_ORPHAN_BOILERPLATE_RE_LIST: tuple[re.Pattern, ...] = (
    re.compile(r"저에게\s+큰\s+기회가\s+될\s+수\s+있습니다"),
    re.compile(r"저에게\s+큰\s+힘이\s+됩니다"),
    re.compile(r"이는.{2,60}저에게.{2,40}됩니다"),
    re.compile(r"이것은.{2,60}저에게.{2,40}됩니다"),
    re.compile(r"이\s+흐름은\s+[^.!?]{0,96}(?:이름|이름과\s+메시지)[^.!?]{0,48}(?:더\s+)?알려지고\s+있음을\s+보여줍니다"),
    re.compile(
        r"(?:이는|이\s+수치는|이\s+숫자는|이\s+결과는)[^.!?]{0,72}"
        r"시민(?:들)?(?:\s+여러분)?(?:께서|의)?[^.!?]{0,48}"
        r"(?:주목|기대|지지|열망|갈망|변화\s+요구)[^.!?]{0,32}(?:신호|뜻|의미|증거|보여줍니다)"
    ),
)
SUBHEADING_SUBJECT_NOISE_MARKERS: tuple[str, ...] = (
    "조사개요",
    "조사기관",
    "조사기간",
    "조사대상",
    "표본수",
    "표본오차",
    "응답률",
    "중앙선거여론조사심의위원회",
)
SUBHEADING_LOW_SIGNAL_MARKERS: tuple[str, ...] = (
    "검색어",
    "키워드",
    "표현",
    "문구",
    "가상대결",
    "양자대결",
    "대결",
    "경쟁",
    "비교",
    "행보",
    "거론",
    "언급",
    "주목",
    "후보군",
    "지지율",
)
SUBHEADING_FIRST_PERSON_SIGNAL_PATTERN = re.compile(
    r"(저는|제가|저의|저만의|제\s*(?:비전|해법|대안|정책|생각|진심|메시지)|말씀드리|설명드리|준비했습니다|제시하겠습니다)",
    re.IGNORECASE,
)
SUBHEADING_FIRST_PERSON_TOPIC_NOUNS: tuple[str, ...] = (
    "비전",
    "해법",
    "대안",
    "정책",
    "생각",
    "진심",
    "메시지",
    "방향",
    "약속",
    "역할",
    "경쟁력",
    "가능성",
    "해결책",
    "행보",
    "구상",
    "계획",
    "승부수",
    "도전",
    "실천",
    "미래",
    "꿈",
    "과제",
    "원칙",
    "제안",
    "목표",
    "다짐",
    "소신",
    "철학",
    "이유",
    "해답",
    "로드맵",
    "리더십",
    "변화",
    "선택",
    "전략",
    "강점",
    "질문",
    "답",
    "설명",
    "주장",
    "진단",
    "기회",
)
_SUBHEADING_FIRST_PERSON_TOPIC_NOUN_FRAGMENT = "|".join(
    re.escape(item) for item in SUBHEADING_FIRST_PERSON_TOPIC_NOUNS
)
SUBHEADING_FIRST_PERSON_POSSESSIVE_PATTERN = re.compile(
    rf"(?:(?<=^)|(?<=[\s\(\[\{{\"'“”‘’,:/\-]))(?:제|내)"
    rf"(?=\s*(?:{_SUBHEADING_FIRST_PERSON_TOPIC_NOUN_FRAGMENT})"
    rf"(?:은|는|이|가|을|를|의|과|와|도)?(?:$|[\s?!.,]))",
    re.IGNORECASE,
)
SUBHEADING_NUMERIC_TOKEN_PATTERN = re.compile(
    r"\d{1,4}(?:[.,]\d+)?(?:%p|%|명|일|월|년|회|건|개)?",
    re.IGNORECASE,
)
SUBHEADING_SIGNAL_SENTENCE_LIMIT = 6
SUBHEADING_SIGNAL_PARAGRAPH_LIMIT = 3

# 프론트 로딩 오버레이가 순환 메시지를 출력하는 기준 키.
LOADING_STAGE_STRUCTURE = "구조 설계 및 초안 작성 중"
LOADING_STAGE_BODY = "본문 작성 중"
LOADING_STAGE_SEO = "검색 노출 최적화(SEO) 중"

_STEP_NAME_TO_LOADING_STAGE = {
    "structureagent": LOADING_STAGE_STRUCTURE,
    "writeragent": LOADING_STAGE_STRUCTURE,
    "keywordinjectoragent": LOADING_STAGE_BODY,
    "styleagent": LOADING_STAGE_BODY,
    "complianceagent": LOADING_STAGE_BODY,
    "seoagent": LOADING_STAGE_SEO,
    "titleagent": LOADING_STAGE_SEO,
}


@dataclass
class ApiError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


class ProgressTracker:
    """Firestore generation_progress 동기 업데이트."""

    def __init__(self, session_id: str):
        self.session_id = str(session_id or "").strip()
        self.ref = firestore.client().collection("generation_progress").document(self.session_id)

    def update(self, step: int, progress: int, message: str, error: bool = False) -> None:
        payload = {
            "step": int(step),
            "progress": int(progress),
            "message": str(message or ""),
            "timestamp": datetime.now(KST).isoformat(timespec="milliseconds"),
            "updatedAt": int(time.time() * 1000),
        }
        if error:
            payload["error"] = True
        try:
            self.ref.set(payload, merge=True)
        except Exception as exc:
            logger.warning("진행 상황 업데이트 실패: %s", exc)

    def step_preparing(self) -> None:
        self.update(1, 10, "준비 중...")

    def step_collecting(self) -> None:
        self.update(2, 25, "자료 수집 중...")

    def step_generating(self) -> None:
        # 프론트 STEP_MESSAGES 키와 동일한 값으로 고정해 랜덤 순환을 활성화한다.
        self.update(3, 50, LOADING_STAGE_STRUCTURE)

    def step_validating(self) -> None:
        self.update(4, 80, "품질 검증 중...")

    def step_finalizing(self) -> None:
        self.update(5, 95, "마무리 중...")

    def complete(self) -> None:
        self.update(5, 100, "완료")

    def error(self, error_message: str) -> None:
        self.update(-1, 0, f"오류: {error_message}", error=True)


class _InternalRequest:
    """
    pipeline_start.handle_start 재사용을 위한 최소 Request 어댑터.
    """

    def __init__(self, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None):
        self._payload = payload
        self.headers = headers or {}

    def get_json(self, silent: bool = True) -> Dict[str, Any]:
        _ = silent
        return self._payload


def _safe_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _normalize_step_name(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return " ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _to_loading_stage_message(raw_step_name: Any) -> str:
    step_name = _normalize_step_name(raw_step_name)
    normalized = re.sub(r"\s+", "", step_name).lower()
    if not normalized:
        return LOADING_STAGE_BODY

    stage_message = _STEP_NAME_TO_LOADING_STAGE.get(normalized)
    if stage_message:
        return stage_message

    # step 명칭이 일부 변경되어도 키워드 기반으로 프론트 단계와 동기화한다.
    if "seo" in normalized or "title" in normalized:
        return LOADING_STAGE_SEO
    if "structure" in normalized or "writer" in normalized:
        return LOADING_STAGE_STRUCTURE
    if "keyword" in normalized or "style" in normalized or "compliance" in normalized:
        return LOADING_STAGE_BODY
    return LOADING_STAGE_BODY


def _to_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return int(value)
        text = str(value).strip()
        if not text:
            return default
        return int(float(text))
    except Exception:
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _count_chars_no_space(text: str) -> int:
    return int(count_without_space(str(text or "")))


def _normalize_title_surface_local(title: str) -> str:
    candidate = re.sub(r"\s+", " ", str(title or "")).strip().strip('"\'')
    if not candidate:
        return ""
    try:
        from agents.common.title_generation import normalize_title_surface

        normalized = normalize_title_surface(candidate)
        return str(normalized or "").strip() or candidate
    except Exception:
        candidate = re.sub(r"\s+([,.:;!?])", r"\1", candidate)
        candidate = re.sub(r"\(\s+", "(", candidate)
        candidate = re.sub(r"\s+\)", ")", candidate)
        candidate = re.sub(r"\s{2,}", " ", candidate)
        return candidate.strip(" ,")


def _normalize_keywords(raw_keywords: Any) -> list[str]:
    if isinstance(raw_keywords, list):
        return [str(item).strip() for item in raw_keywords if str(item).strip()]
    if isinstance(raw_keywords, str):
        return [part.strip() for part in raw_keywords.split(",") if part.strip()]
    return []


AUTO_KEYWORD_NUMERIC_FRAGMENT_PATTERN = re.compile(
    r"^(?:\d{1,4}(?:\.\d+)?(?:%|%p|명|일|월|년|회|건|개|시|분|p|포인트)?|\d{4}[./-]\d{1,2}(?:[./-]\d{1,2})?)$",
    re.IGNORECASE,
)
AUTO_KEYWORD_TRAILING_PARTICLE_PATTERN = re.compile(
    r"^(?P<stem>[가-힣A-Za-z]{2,8})(?:은|는|이|가|도|를|을|의|와|과|로|에서|에게|께서)$"
)
AUTO_KEYWORD_LOW_SIGNAL_TOKENS: set[str] = {
    "후보군",
    "대결에서도",
    "이틀동",
}


def _normalize_auto_keyword_candidate(raw_keyword: Any) -> str:
    normalized = re.sub(r"\s+", " ", str(raw_keyword or "")).strip().strip("\"'")
    if not normalized:
        return ""

    compact = re.sub(r"\s+", "", normalized)
    if AUTO_KEYWORD_NUMERIC_FRAGMENT_PATTERN.fullmatch(compact):
        return ""
    if compact in AUTO_KEYWORD_LOW_SIGNAL_TOKENS:
        return ""

    particle_match = AUTO_KEYWORD_TRAILING_PARTICLE_PATTERN.fullmatch(compact)
    if particle_match:
        stem = str(particle_match.group("stem") or "").strip()
        if len(stem) >= 3 and _looks_like_person_name_token(stem):
            normalized = stem
            compact = stem

    if compact in AUTO_KEYWORD_LOW_SIGNAL_TOKENS:
        return ""
    return normalized


def _sanitize_auto_keywords(
    raw_keywords: Any,
    *,
    user_keywords: Optional[Iterable[str]] = None,
) -> list[str]:
    user_keyword_set = {
        str(item).strip()
        for item in (user_keywords or [])
        if str(item).strip()
    }
    sanitized: list[str] = []
    seen: set[str] = set()
    for item in _normalize_keywords(raw_keywords):
        normalized = _normalize_auto_keyword_candidate(item)
        if not normalized or normalized in user_keyword_set or normalized in seen:
            continue
        seen.add(normalized)
        sanitized.append(normalized)
    return sanitized


def _resolve_keyword_gate_policy(
    user_keywords: list[str],
    *,
    conflicting_role_keyword: str = "",
    role_keyword_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_user_keywords = [str(item).strip() for item in (user_keywords or []) if str(item).strip()]
    shadowed_map = find_shadowed_user_keywords(normalized_user_keywords)
    soft_keywords: set[str] = set(shadowed_map.keys())
    if isinstance(role_keyword_policy, dict):
        blocked_keywords = role_keyword_policy.get("blockedKeywords")
        if isinstance(blocked_keywords, list):
            soft_keywords.update(str(item).strip() for item in blocked_keywords if str(item).strip())

    conflicting = str(conflicting_role_keyword or "").strip()
    hard_keywords = [keyword for keyword in normalized_user_keywords if keyword not in soft_keywords]
    return {
        "allKeywords": normalized_user_keywords,
        "hardKeywords": hard_keywords,
        "softKeywords": sorted(soft_keywords),
        "shadowedMap": shadowed_map,
        "conflictingRoleKeyword": conflicting,
        "roleKeywordPolicy": role_keyword_policy if isinstance(role_keyword_policy, dict) else {},
    }


def _map_api_error(code: str, message: str) -> ApiError:
    normalized = str(code or "").strip().upper()
    mapping = {
        "INVALID_INPUT": "invalid-argument",
        "INVALID_ARGUMENT": "invalid-argument",
        "UNAUTHENTICATED": "unauthenticated",
        "PERMISSION_DENIED": "permission-denied",
        "FAILED_PRECONDITION": "failed-precondition",
        "RESOURCE_EXHAUSTED": "resource-exhausted",
        "NOT_FOUND": "not-found",
        "INTERNAL_ERROR": "internal",
        "EXECUTION_ERROR": "internal",
    }
    return ApiError(mapping.get(normalized, "internal"), message or "요청 처리에 실패했습니다.")


def _today_key() -> str:
    now = datetime.now()
    return f"{now.year:04d}-{now.month:02d}-{now.day:02d}"


def _month_key() -> str:
    now = datetime.now()
    return f"{now.year:04d}-{now.month:02d}"


def _clear_active_session(uid: str) -> None:
    try:
        firestore.client().collection("users").document(uid).update(
            {"activeGenerationSession": firestore.DELETE_FIELD}
        )
    except Exception as exc:
        logger.warning("기존 세션 삭제 실패(무시): %s", exc)


def _calc_daily_limit_warning(user_profile: Dict[str, Any]) -> bool:
    daily_usage = _safe_dict(user_profile.get("dailyUsage"))
    today = _today_key()
    return _to_int(daily_usage.get(today), 0) >= 3


def _apply_usage_updates_after_success(
    uid: str,
    *,
    is_admin: bool,
    is_tester: bool,
    session: Dict[str, Any],
) -> None:
    if is_admin:
        return
    if not bool(session.get("isNewSession")):
        return

    db = firestore.client()
    user_ref = db.collection("users").document(uid)
    user_doc = user_ref.get()
    user_data = user_doc.to_dict() if user_doc.exists else {}
    user_data = _safe_dict(user_data)

    subscription_status = str(user_data.get("subscriptionStatus") or "trial").strip().lower()
    current_month_key = _month_key()
    update_data: Dict[str, Any] = {}

    test_mode = bool(get_test_mode_config(db).get("enabled") is True)

    if is_tester or subscription_status == "active":
        update_data[f"monthlyUsage.{current_month_key}.generations"] = firestore.Increment(1)
    elif test_mode:
        update_data[f"monthlyUsage.{current_month_key}.generations"] = firestore.Increment(1)
    elif subscription_status == "trial":
        current_remaining = _to_int(
            user_data.get("generationsRemaining", user_data.get("trialPostsRemaining", 0)),
            0,
        )
        if current_remaining > 0:
            update_data["generationsRemaining"] = firestore.Increment(-1)

    if update_data:
        user_ref.update(update_data)


def _extract_start_payload(
    uid: str,
    data: Dict[str, Any],
    *,
    topic: str,
    category: str,
    sub_category: str,
    classification_meta: Optional[Dict[str, Any]] = None,
    target_word_count: int,
    user_keywords: list[str],
    pipeline_route: str,
    recent_titles: Optional[list[str]] = None,
) -> Dict[str, Any]:
    payload = dict(data)
    payload["topic"] = topic
    payload["category"] = category
    payload["subCategory"] = str(sub_category or "")
    if isinstance(classification_meta, dict) and classification_meta:
        payload["classificationMeta"] = dict(classification_meta)
    payload["targetWordCount"] = int(target_word_count)
    payload["uid"] = uid
    payload["userId"] = uid
    payload["pipeline"] = pipeline_route
    payload["keywords"] = user_keywords
    payload["userKeywords"] = user_keywords
    normalized_recent_titles = _normalize_recent_title_memory_values(list(recent_titles or []))
    if normalized_recent_titles:
        payload["recentTitles"] = normalized_recent_titles[:8]
        payload["previousTitles"] = normalized_recent_titles[:8]
    return payload


def _call_pipeline_start(start_payload: Dict[str, Any]) -> str:
    from handlers.pipeline_start import handle_start

    internal_req = _InternalRequest(payload={"data": start_payload}, headers={"X-User-Id": str(start_payload.get("uid") or "")})
    response = handle_start(internal_req)
    status_code = int(getattr(response, "status_code", 500))
    body_text = ""
    try:
        body_text = response.get_data(as_text=True)
    except Exception:
        body_text = ""

    payload = {}
    if body_text:
        try:
            payload = json.loads(body_text)
        except Exception:
            payload = {}

    if status_code >= 400:
        message = str(payload.get("error") or "파이프라인 시작에 실패했습니다.")
        raise _map_api_error(str(payload.get("code") or "INTERNAL_ERROR"), message)

    job_id = str(payload.get("jobId") or "").strip()
    if not job_id:
        raise ApiError("internal", "파이프라인 Job ID를 받지 못했습니다.")

    return job_id


def _poll_pipeline(job_id: str, progress: ProgressTracker) -> Dict[str, Any]:
    from services.job_manager import JobManager

    job_manager = JobManager()
    started_at = time.time()
    # step_generating()에서 이미 50%가 기록되므로 폴링 중 진행률이 역행하지 않게 고정한다.
    last_message = LOADING_STAGE_STRUCTURE
    last_progress = 50

    while time.time() - started_at < MAX_POLL_TIME_SECONDS:
        time.sleep(POLL_INTERVAL_SECONDS)
        job_data = job_manager.get_job(job_id)
        if not job_data:
            continue

        status = str(job_data.get("status") or "running")
        total_steps = _to_int(job_data.get("totalSteps"), 1)
        steps = _safe_dict(job_data.get("steps"))
        completed_steps = 0
        for step_val in steps.values():
            step_obj = _safe_dict(step_val)
            if step_obj.get("status") == "completed":
                completed_steps += 1

        percentage = round((completed_steps / max(total_steps, 1)) * 100, 1)
        current_step_index = str(job_data.get("currentStep", 0))
        current_step_obj = _safe_dict(steps.get(current_step_index))
        current_step_name = _normalize_step_name(current_step_obj.get("name") or "파이프라인")

        if status == "running":
            current_percentage = int(round(30 + percentage * 0.5))
            current_percentage = max(last_progress, current_percentage)
            message = _to_loading_stage_message(current_step_name)
            if message != last_message or current_percentage > last_progress:
                progress.update(3, current_percentage, message)
                last_message = message
                last_progress = current_percentage
            continue

        if status == "completed":
            result = _safe_dict(job_data.get("result"))
            if not result:
                raise ApiError("internal", "파이프라인 결과가 비어 있습니다.")
            return result

        if status == "failed":
            error_obj = _safe_dict(job_data.get("error"))
            step = str(error_obj.get("step") or current_step_name or "unknown")
            message = str(error_obj.get("message") or "파이프라인 실행 실패")
            raise ApiError("internal", f"Pipeline failed at step {step}: {message}")

    timeout_min = round(MAX_POLL_TIME_SECONDS / 60, 1)
    raise ApiError("deadline-exceeded", f"Pipeline timeout: {timeout_min}분 내에 완료되지 않았습니다.")


def _ensure_user(uid: str) -> None:
    if not uid:
        raise ApiError("unauthenticated", "로그인이 필요합니다.")


def _resolve_request_intent_with_meta(data: Dict[str, Any]) -> tuple[str, str, str, Dict[str, Any]]:
    topic = str(data.get("prompt") or data.get("topic") or "").strip()
    if not topic:
        # topic이 비어있으면 stance/news에서 추론 시도
        stance_text = str(data.get("stanceText") or "").strip()
        news_text = str(data.get("newsDataText") or "").strip()
        source_text = news_text or stance_text
        if not source_text:
            raise ApiError("invalid-argument", "주제, 입장문, 뉴스 중 하나는 입력해야 합니다.")
        try:
            from services.stance_inferrer import infer_stance_from_news
            inferred = _run_async_sync(infer_stance_from_news(news_text=source_text))
            topic = (inferred or {}).get("topic") or source_text[:50]
        except Exception as exc:
            logger.warning("[_resolve_request_intent_with_meta] stance inference failed: %s", exc)
            topic = source_text[:50]

    requested_category = str(data.get("category") or "").strip()
    requested_sub_category = str(data.get("subCategory") or "").strip()
    instructions = data.get("instructions")
    first_instruction = ""
    if isinstance(instructions, list) and instructions:
        first_instruction = str(instructions[0] or "").strip()
    elif isinstance(instructions, str):
        first_instruction = str(instructions).strip()

    classifier_payload = {
        "category": requested_category,
        "subCategory": requested_sub_category,
        "stanceText": str(data.get("stanceText") or first_instruction or "").strip(),
    }

    try:
        from services.topic_classifier import resolve_request_intent

        resolved = _run_async_sync(resolve_request_intent(topic, classifier_payload))
    except Exception as exc:
        logger.warning("Top-level request classification failed; using fallback: %s", exc)
        resolved = {}

    category = str(
        resolved.get("category")
        or classifier_payload.get("category")
        or "daily-communication"
    ).strip() or "daily-communication"
    sub_category = str(
        resolved.get("subCategory")
        or classifier_payload.get("subCategory")
        or ""
    ).strip()
    classification_meta = {
        "requestedCategory": requested_category or "auto",
        "requestedSubCategory": requested_sub_category,
        "resolvedCategory": category,
        "resolvedSubCategory": sub_category,
        "writingMethod": str(resolved.get("writingMethod") or ""),
        "source": str(resolved.get("source") or ""),
        "confidence": round(float(resolved.get("confidence") or 0.0), 3),
        "hasStanceSignal": bool(classifier_payload["stanceText"]),
        "stanceLength": len(str(classifier_payload["stanceText"] or "")),
    }
    return topic, category, sub_category, classification_meta


def _resolve_request_category(data: Dict[str, Any]) -> tuple[str, str, str]:
    topic, category, sub_category, _classification_meta = _resolve_request_intent_with_meta(data)
    return topic, category, sub_category

def _topic_and_category(data: Dict[str, Any]) -> tuple[str, str]:
    topic = str(data.get("prompt") or data.get("topic") or "").strip()
    if not topic:
        stance_text = str(data.get("stanceText") or "").strip()
        news_text = str(data.get("newsDataText") or "").strip()
        source_text = news_text or stance_text
        if not source_text:
            raise ApiError("invalid-argument", "주제, 입장문, 뉴스 중 하나는 입력해야 합니다.")
        topic = source_text[:50]
    category = str(data.get("category") or "daily-communication").strip() or "daily-communication"
    return topic, category


def _target_word_count(data: Dict[str, Any], category: str) -> int:
    requested = _to_int(data.get("wordCount"), DEFAULT_TARGET_WORD_COUNT)
    minimum = _to_int(CATEGORY_MIN_WORD_COUNT.get(category), DEFAULT_TARGET_WORD_COUNT)
    return max(requested, minimum)


def _calc_min_required_chars(target_word_count: int, stance_count: int = 0) -> int:
    # StructureAgent._build_length_spec와 동일 기준(완화 아님)
    target_chars = max(1600, min(int(target_word_count), 3200))
    total_sections = round(target_chars / 400)
    total_sections = max(5, min(7, total_sections))
    if stance_count > 0:
        total_sections = max(total_sections, min(7, stance_count + 2))

    per_section_recommended = max(360, min(420, round(target_chars / total_sections)))
    per_section_min = max(320, per_section_recommended - 50)
    return max(int(target_chars * 0.88), total_sections * per_section_min)


def _build_terminal_section_length_spec(target_word_count: int, stance_count: int = 0) -> Dict[str, int]:
    target_chars = max(1600, min(int(target_word_count or DEFAULT_TARGET_WORD_COUNT), 3200))
    section_char_target = int(STRUCTURE_SPEC["sectionCharTarget"])
    section_char_min = int(STRUCTURE_SPEC["sectionCharMin"])
    section_char_max = int(STRUCTURE_SPEC["sectionCharMax"])
    min_sections = int(STRUCTURE_SPEC["minSections"])
    max_sections = int(STRUCTURE_SPEC["maxSections"])

    total_sections = round(target_chars / section_char_target)
    total_sections = max(min_sections, min(max_sections, total_sections))
    if stance_count > 0:
        total_sections = max(total_sections, min(max_sections, stance_count + 2))

    per_section_recommended = max(
        section_char_min,
        min(section_char_max, round(target_chars / total_sections)),
    )
    per_section_min = max(section_char_min - 50, per_section_recommended - 50)
    per_section_max = min(section_char_max + 50, per_section_recommended + 50)
    return {
        "total_sections": total_sections,
        "expected_h2": max(1, total_sections - 1),
        "per_section_min": per_section_min,
        "per_section_max": per_section_max,
    }


def _apply_terminal_section_length_backstop_once(
    content: str,
    *,
    length_spec: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    spec = length_spec if isinstance(length_spec, dict) else {}
    section_min = int(spec.get("per_section_min") or max(320, int(STRUCTURE_SPEC["sectionCharMin"]) - 50))
    sections = _split_into_sections(base)
    if len(sections) < 2:
        return {"content": base, "edited": False, "actions": []}

    actions: list[str] = []
    before_lengths = [_plain_len(section.get("html", "")) for section in sections]

    for index, section in enumerate(sections):
        if not section.get("has_h2"):
            continue
        effective_min = min(section_min, 130) if index == len(sections) - 1 else section_min
        section_html = str(section.get("html") or "")
        before_len = _plain_len(section_html)
        if before_len >= effective_min:
            continue

        updated_html = section_html
        for _ in range(6):
            current_len = _plain_len(updated_html)
            if current_len >= effective_min:
                break
            updated_html = _pad_short_section(updated_html, index + 1, effective_min - current_len)

        after_len = _plain_len(updated_html)
        if updated_html != section_html:
            section["html"] = updated_html
            actions.append(f"section_length_backstop:{index + 1}:{before_len}->{after_len}")
            logger.warning(
                "Final section length backstop applied: section=%s before=%s after=%s min=%s",
                index + 1,
                before_len,
                after_len,
                effective_min,
            )

    if not actions:
        return {"content": base, "edited": False, "actions": []}

    repaired = _join_sections(sections)
    if repaired == base:
        return {"content": base, "edited": False, "actions": []}

    after_lengths = [_plain_len(section.get("html", "")) for section in sections]
    logger.info(
        "Final section length backstop summary: before=%s after=%s",
        before_lengths,
        after_lengths,
    )
    return {
        "content": repaired,
        "edited": True,
        "actions": actions,
        "beforeLengths": before_lengths,
        "afterLengths": after_lengths,
    }


def _restore_terminal_output_addons_once(
    content: str,
    *,
    output_options: Optional[Dict[str, Any]] = None,
    content_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = normalize_ascii_double_quotes(str(content or "").strip())
    if not base:
        return {"content": base, "edited": False, "actions": []}

    options = output_options if isinstance(output_options, dict) else {}
    meta = content_meta if isinstance(content_meta, dict) else {}

    slogan = str(options.get("slogan") or "").strip()
    slogan_enabled = bool(options.get("sloganEnabled") is True and slogan)
    donation_info = str(options.get("donationInfo") or "").strip()
    donation_enabled = bool(options.get("donationEnabled") is True and donation_info)
    poll_citation = str(meta.get("pollCitation") or options.get("pollCitation") or "").strip()
    poll_enabled = bool(
        poll_citation
        and (
            options.get("embedPollCitation") is True
            or meta.get("pollCitationForced") is True
        )
    )

    updated = strip_generated_addons(
        base,
        slogan=slogan,
        donation_info=donation_info,
    )
    updated = strip_generated_poll_citation(updated)

    actions: list[str] = []
    if donation_enabled:
        updated = insert_donation_info(updated, normalize_ascii_double_quotes(donation_info))
        actions.append("terminal_donation_info")
    if slogan_enabled:
        updated = insert_slogan(updated, normalize_ascii_double_quotes(slogan))
        actions.append("terminal_slogan")
    if poll_enabled:
        updated = insert_poll_citation(updated, normalize_ascii_double_quotes(poll_citation))
        actions.append("terminal_poll_citation")

    updated = normalize_ascii_double_quotes(updated)
    return {
        "content": updated,
        "edited": updated != base,
        "actions": actions,
    }


def _collect_section_paragraph_issues(content: str, *, min_p: int = 3) -> list[str]:
    issues: list[str] = []
    sections = _split_into_sections(str(content or ""))
    for index, section in enumerate(sections, start=1):
        section_html = str(section.get("html") or "")
        p_count = len(re.findall(r"<p\b[^>]*>[\s\S]*?</p\s*>", section_html, re.IGNORECASE))
        if p_count == 0:
            continue
        if p_count < min_p:
            heading = str(section.get("h2_text") or "").strip()
            label = f"{index}번 섹션"
            if heading:
                label += f"({heading})"
            issues.append(f"{label} 문단 수 {p_count}개 < {min_p}개")
    return issues


def _extract_stance_count(pipeline_result: Dict[str, Any]) -> int:
    context_analysis = pipeline_result.get("contextAnalysis")
    if not isinstance(context_analysis, dict):
        return 0
    must_include = context_analysis.get("mustIncludeFromStance")
    if not isinstance(must_include, list):
        return 0
    return len([item for item in must_include if item])


def _validate_keyword_gate(keyword_validation: Dict[str, Any], user_keywords: list[str]) -> tuple[bool, str]:
    normalized_user_keywords = [str(item).strip() for item in (user_keywords or []) if str(item).strip()]
    if not normalized_user_keywords:
        return True, ""

    if not isinstance(keyword_validation, dict) or not keyword_validation:
        return False, "키워드 검증 결과가 없습니다."

    for keyword in normalized_user_keywords:
        info = keyword_validation.get(keyword)
        if not isinstance(info, dict):
            return False, f"\"{keyword}\" 검증 정보 없음"
        status = str(info.get("status") or "").strip().lower()
        count = _to_int(info.get("gateCount"), _to_int(info.get("count"), 0))
        expected = _to_int(info.get("expected"), 0)
        max_count = _to_int(info.get("max"), 0)
        exact_count = _to_int(info.get("exclusiveCount"), count)
        if status == "insufficient":
            return False, f"\"{keyword}\" 부족 ({count}/{expected})"
        if status == "spam_risk":
            return False, f"\"{keyword}\" 과다 ({exact_count}/{max_count})"
    return True, ""


def _collect_secondary_keyword_soft_issues(
    keyword_validation: Dict[str, Any],
    user_keywords: list[str],
) -> list[str]:
    normalized_user_keywords = [str(item).strip() for item in (user_keywords or []) if str(item).strip()]
    if len(normalized_user_keywords) <= 1:
        return []
    if not isinstance(keyword_validation, dict) or not keyword_validation:
        return []

    issues: list[str] = []
    for keyword in normalized_user_keywords[1:]:
        info = keyword_validation.get(keyword)
        if not isinstance(info, dict):
            issues.append(f"\"{keyword}\" 검증 정보 없음")
            continue
        status = str(info.get("status") or "").strip().lower()
        count = _to_int(info.get("gateCount"), _to_int(info.get("count"), 0))
        expected = _to_int(info.get("expected"), 0)
        max_count = _to_int(info.get("max"), 0)
        exact_count = _to_int(info.get("exclusiveCount"), count)
        if status == "insufficient":
            issues.append(f"\"{keyword}\" 부족 ({count}/{expected})")
        elif status == "spam_risk":
            issues.append(f"\"{keyword}\" 과다 ({exact_count}/{max_count})")
    return issues


def _collect_exact_preference_keywords(
    keyword_validation: Dict[str, Any],
    user_keywords: list[str],
) -> list[str]:
    normalized_user_keywords = [str(item).strip() for item in (user_keywords or []) if str(item).strip()]
    if not normalized_user_keywords or not isinstance(keyword_validation, dict) or not keyword_validation:
        return []

    unmet: list[str] = []
    for keyword in normalized_user_keywords:
        info = keyword_validation.get(keyword)
        if not isinstance(info, dict):
            continue
        if _to_int(info.get("exactPreferredMin"), 0) <= 0:
            continue
        if _to_int(info.get("exactShortfall"), 0) > 0:
            unmet.append(keyword)
    return unmet


def _collect_over_max_keywords(
    keyword_validation: Dict[str, Any],
    user_keywords: list[str],
) -> list[str]:
    normalized_user_keywords = [str(item).strip() for item in (user_keywords or []) if str(item).strip()]
    if not normalized_user_keywords or not isinstance(keyword_validation, dict) or not keyword_validation:
        return []

    over_max_keywords: list[str] = []
    for keyword in normalized_user_keywords:
        info = keyword_validation.get(keyword)
        if not isinstance(info, dict):
            continue
        exact_count = _to_int(info.get("exclusiveCount"), _to_int(info.get("count"), 0))
        max_count = _to_int(info.get("max"), 0)
        if max_count > 0 and exact_count > max_count:
            over_max_keywords.append(keyword)
    return over_max_keywords


def _build_display_keyword_validation(
    keyword_validation: Dict[str, Any],
    *,
    soft_keywords: Optional[Sequence[str]] = None,
    shadowed_map: Optional[Mapping[str, Sequence[str]]] = None,
) -> Dict[str, Any]:
    base_validation = {
        str(keyword).strip(): dict(info)
        for keyword, info in (keyword_validation or {}).items()
        if str(keyword).strip() and isinstance(info, dict)
    }
    if not base_validation:
        return {}

    normalized_soft_keywords = {
        str(keyword).strip()
        for keyword in (soft_keywords or [])
        if str(keyword).strip()
    }
    if not normalized_soft_keywords:
        return base_validation

    normalized_shadowed_map = {
        str(keyword).strip(): [
            str(item).strip() for item in (items or []) if str(item).strip()
        ]
        for keyword, items in (shadowed_map or {}).items()
        if str(keyword).strip()
    }

    adjusted: Dict[str, Any] = {}
    for keyword, info in base_validation.items():
        updated = dict(info)
        if keyword in normalized_soft_keywords:
            count = _to_int(updated.get("count"), 0)
            updated["soft"] = True
            updated["policy"] = "soft-shadowed"
            updated["shadowedBy"] = list(normalized_shadowed_map.get(keyword) or [])
            if str(updated.get("status") or "").strip().lower() != "spam_risk":
                updated["status"] = "valid"
                updated["expected"] = 0
                updated["bodyExpected"] = 0
                updated["max"] = max(_to_int(updated.get("max"), 0), count)
                updated["exactPreferredMin"] = 0
                updated["exactShortfall"] = 0
                updated["exactPreferredMet"] = True
        adjusted[keyword] = updated
    return adjusted


def _normalize_person_name(text: str) -> str:
    return normalize_person_name(text)


def _clean_full_name_candidate(raw_name: Any) -> str:
    return clean_full_name_candidate(raw_name)


def _extract_name_from_signature_text(raw_text: Any) -> str:
    text = str(raw_text or "").strip()
    if not text:
        return ""
    normalized = re.sub(r"<[^>]*>", " ", text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return ""

    patterns = [
        re.compile(r"(?:^|[\s\-—])([가-힣]{2,8})\s*드림(?:$|[\s.,])"),
        re.compile(r"(?:^|[\s\-—])([가-힣]{2,8})\s*올림(?:$|[\s.,])"),
    ]
    for pattern in patterns:
        match = pattern.search(normalized)
        if match:
            candidate = _clean_full_name_candidate(match.group(1))
            if candidate:
                return candidate
    return ""


def _is_identity_signature_text(raw_text: Any) -> bool:
    text = str(raw_text or "").strip()
    if not text:
        return False

    plain = re.sub(r"<[^>]*>", " ", text)
    plain = re.sub(r"\s+", " ", plain).strip()
    if not plain:
        return False

    if _extract_name_from_signature_text(plain):
        return True

    return any(
        token in plain
        for token in (
            "뼛속까지",
            "이재성입니다",
            "이재성!",
            "저 이재성",
            "저는",
            "저 ",
        )
    )


def _collect_style_phrase_examples(
    phrases: Dict[str, Any],
) -> tuple[list[str], list[str]]:
    generic_phrases: list[str] = []
    identity_signatures: list[str] = []

    raw_signatures = phrases.get("signatures") or []
    if isinstance(raw_signatures, list):
        for raw_value in raw_signatures:
            value = str(raw_value or "").strip()
            if not value:
                continue
            if _is_identity_signature_text(value):
                if value not in identity_signatures:
                    identity_signatures.append(value)
                continue
            if value not in generic_phrases:
                generic_phrases.append(value)
            if len(generic_phrases) >= 5:
                break

    for key in ("emphatics", "conclusions"):
        raw_values = phrases.get(key) or []
        if not isinstance(raw_values, list):
            continue
        for raw_value in raw_values:
            value = str(raw_value or "").strip()
            if value and value not in generic_phrases:
                generic_phrases.append(value)
            if len(generic_phrases) >= 5:
                break
        if len(generic_phrases) >= 5:
            break

    return generic_phrases, identity_signatures


_SELF_ANALYTICAL_STORY_TAIL_PATTERN = re.compile(
    r"(?P<prefix>[^.!?]{0,160}?)\s*"
    r"(?P<label>(?:저의|나의|이러한\s+저의)\s+(?:이야기|서사|배경|경험|행보|삶))"
    r"(?:는|은)\s+"
    r"(?:시민들[^.!?]{0,40})?"
    r"(?:마음을\s+움직이는\s+강력한\s+힘이\s+됩니다|"
    r"마음을\s+움직이는\s+힘이\s+됩니다|"
    r"마음을\s+움직입니다|"
    r"공감과\s+희망을\s+줍니다|"
    r"공감과\s+희망을\s+주는\s+힘이\s+됩니다|"
    r"기대감을\s+키웁니다|"
    r"기대감을\s+높입니다)"
    r"\.?",
    re.IGNORECASE,
)

_SELF_ANALYTICAL_RESULT_TRIM_PATTERN = re.compile(
    r"^(?:저의|이러한\s+저의|저의\s+이러한)\s+"
    r"[^.!?]{0,84}(?:비전|실천\s*의지|접근|역량|진정성|전문성|실력|행보|노력|해결책\s+제시)"
    r"[^.!?]{0,60}(?:닿아|이어져|이어지며|반영돼|반영되어)\s*,\s*"
    r"(?P<result>[^.!?]{1,48}결과(?:로)?\s+나타났습니다)\.?\s*$",
    re.IGNORECASE,
)

_SIMPLE_NEGATION_FRAME_RE_LIST: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"단순(?:한|히)\s+[^.!?]{0,48}"
        r"(?:"
        r"(?:가|이|은|는)\s+(?:아니라|아닌)|"
        r"[을를]\s+넘어(?:서|선|섭니다|서며|섰|선)?|"
        r"에\s+그치지\s+않(?:고|습니다)|"
        r"고향|"
        r"이론(?:적(?:인)?)?(?:\s+지식)?|"
        r"지식|"
        r"약속|"
        r"수치(?:상의)?(?:\s+우위)?|"
        r"우위|"
        r"부양책"
        r")",
        re.IGNORECASE,
    ),
    re.compile(r"단순히.{1,40}에\s*그치지\s*않고", re.IGNORECASE),
    re.compile(r"에만?\s*머무르지\s*않고", re.IGNORECASE),
)

_HOEKIJEOK_RE = re.compile(r"획기적으로\s*", re.IGNORECASE)
_JEOKGEUKJEOK_RE = re.compile(r"적극적으로\s*", re.IGNORECASE)
_GYEOMHEO_CLAUSE_RE = re.compile(r"(?:이\s+결과를\s+)?겸허히\s+받아들이(?:며|고|겠(?:습니다)?)\s*,?\s*", re.IGNORECASE)
_LOW_POSTURE_CLAUSE_RE = re.compile(r"(?:더욱\s+)?낮은\s+자세로\s*", re.IGNORECASE)
_CONFIRMATION_PHRASE_RE = re.compile(r"것(?:이라|이라고)\s+확신합니다", re.IGNORECASE)
_NEGATION_FRAME_EXT_RE_LIST: tuple[re.Pattern[str], ...] = (
    re.compile(r"에\s*그치지\s*않고", re.IGNORECASE),
    re.compile(r"^\s*뿐만\s*아니라", re.IGNORECASE),
)
_VERBOSE_POSTPOS_RE_LIST: tuple[re.Pattern[str], ...] = (
    re.compile(r"에\s*있어서", re.IGNORECASE),
    re.compile(r"함에\s*있어", re.IGNORECASE),
)
_LINK_EXPR_RE_LIST: tuple[re.Pattern[str], ...] = (
    re.compile(r"^이를\s*통해,?\s*", re.IGNORECASE),
    re.compile(r"^이러한\s*점에서,?\s*", re.IGNORECASE),
)
_TRANSLATION_RE_LIST: tuple[re.Pattern[str], ...] = (
    re.compile(r"것은\s*사실(?:이다|입니다)", re.IGNORECASE),
    re.compile(r"라고\s*할\s*수\s*있다", re.IGNORECASE),
    re.compile(r"라고\s*할\s*수\s*있습니다", re.IGNORECASE),
)
_DOUBLE_PASSIVE_RE = re.compile(r"되어지([다며])", re.IGNORECASE)

_SELF_ANALYTICAL_LOW_SIGNAL_RE_LIST: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:저의|이러한\s+저의|저의\s+이러한)\s+"
        r"[^.!?]{0,84}(?:진정성|접근|비전|실천\s*의지|전문성|실력|행보|노력|해결책\s+제시|역량)"
        r"[^.!?]{0,72}(?:핵심\s+요인(?:이라고\s+확신합니다|입니다)|"
        r"중요한\s+요인(?:이\s+됩니다|입니다)|"
        r"원동력(?:입니다|이었습니다)|"
        r"방증입니다|증거입니다|"
        r"기대(?:를)?\s+모으고\s+있습니다|"
        r"높이\s+평가하고\s+적극적으로\s+인정해주신\s+것입니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:이러한\s+)?(?:저의\s+)?"
        r"[^.!?]{0,84}(?:배경|경험|행보|서사|삶의\s+궤적|개인적인\s+서사|직접적인\s+행보)"
        r"[^.!?]{0,72}(?:바탕이\s+됩니다|요인이\s+됩니다|"
        r"전달되(?:며|고)[^.!?]{0,32}(?:요인이\s+됩니다|확산되고\s+있습니다|알려지고\s+있습니다)|"
        r"기대(?:를)?\s+모으고\s+있습니다|"
        r"공감(?:과\s+희망)?을\s+줍니다|"
        r"진솔하게\s+다가가고\s+있다고\s+확신합니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:(?:많은|부산)\s+시민(?:들)?은|시민(?:들)?은)\s+"
        r"(?:저의\s+)?(?:진정성|역량|전문성|실력)"
        r"[^.!?]{0,40}(?:알아봐\s+주고\s+계십니다|높이\s+평가하고\s+있습니다|인정하고\s+있습니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"이\s+흐름은\s+[^.!?]{0,96}(?:이름|이름과\s+메시지)[^.!?]{0,48}"
        r"(?:더\s+)?알려지고\s+있음을\s+보여줍니다",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:(?:부산\s+)?시민(?:들)?(?:\s+여러분)?)께서는?\s+"
        r"[^.!?]{0,84}(?:역량|진정성|전문성|실력|진심|경험|비전|행보|문제\s*해결\s*능력)"
        r"[^.!?]{0,40}(?:알아봐\s+주셨습니다|높이\s+평가해\s+주셨습니다|믿어\s*주셨습니다|인정해\s+주셨습니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:저는|제가)\s+[^.!?]{0,48}(?:유일한\s+후보|최고(?:의)?\s+후보)"
        r"(?:라고\s+자부합니다|입니다|라고\s+생각합니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:저는|제가|[가-힣]{2,8}(?:은|는|이|가)?|시민(?:들)?에게|주민(?:들)?에게)?"
        r"[^.!?]{0,36}(?:가장\s+)?충직한\s+"
        r"(?:(?:[가-힣]{0,12})?(?:민주당원|당원|일꾼|국회의원|시의원|도의원|광역의원|기초의원|의원|정치인))"
        r"[^.!?]{0,40}(?:입니다|이라고\s+자부합니다|으로서|로서|이겠습니다|이\s+되겠습니다|으로\s+남겠습니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:이는|이러한\s+결과(?:는)?)\s+[^.!?]{0,72}"
        r"(?:인정한\s+결과(?:라고\s+생각합니다|입니다)|비전과\s+[^.!?]{0,24}전문성을\s+인정한\s+결과)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:이는|이러한\s+결과(?:는)?)\s+[^.!?]{0,72}"
        r"(?:인정받은\s+결과(?:라고\s+생각합니다|입니다)|평가받은\s+결과(?:라고\s+생각합니다|입니다))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:저는|제가)\s+[^.!?]{0,72}"
        r"(?:준비가\s+완벽(?:하게|히)\s+되어\s+있(?:습니다|다고\s+생각합니다)"
        r"|완벽(?:하게|히)\s+준비되어\s+있(?:습니다|다고\s+생각합니다))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:[^.!?]{0,48})?"
        r"(?:준비가\s+완벽(?:하게|히)\s+되어\s+있(?:습니다|다고\s+생각합니다)"
        r"|완벽(?:하게|히)\s+준비되어\s+있(?:습니다|다고\s+생각합니다))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:이러한\s+)?(?:저의\s+)?(?:경험|이력|행보|삶의\s+궤적|경영\s+경험)(?:은|이)\s+"
        r"[^.!?]{0,72}(?:역량|전문성|능력)[^.!?]{0,24}(?:저에게\s+)?(?:부여했습니다|주었습니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:이러한\s+)?(?:저의\s+)?(?:경험|이력|행보|노력)(?:은|이|들이)\s+"
        r"[^.!?]{0,72}(?:리더십|역량|전문성|능력)[^.!?]{0,24}길러주었습니다",
        re.IGNORECASE,
    ),
    re.compile(r"통찰력(?:을)?(?:\s+저에게)?\s+길러주었", re.IGNORECASE),
    re.compile(r"통찰력과\s*문제\s*해결\s*능력을\s*길러주었", re.IGNORECASE),
    re.compile(r"능력을\s*길러주었", re.IGNORECASE),
    re.compile(r"미래를\s*예측하고\s*선제적으로\s*대응하는", re.IGNORECASE),
    re.compile(
        r"(?:이러한\s+)?(?:실질적인\s+)?경험(?:은|이)\s+"
        r"[^.!?]{0,60}(?:자산|통찰력|실행력|역량|리더십|전문성)"
        r"[^.!?]{0,30}(?:됩니다|될\s+것(?:입니다)?|갖추게\s+했(?:습니다)?|제공했(?:습니다)?|부여했(?:습니다)?|주었(?:습니다)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:이러한\s+)?(?:저의\s+)?(?:경험|이력|행보|경영\s+경험)(?:은|이)\s+저에게\s+"
        r"[^.!?]{0,56}(?:통찰력|전문성|실행력|리더십|자산)[^.!?]{0,24}(?:제공했습니다|부여했습니다|주었습니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:\b\d{1,2}세(?:라는\s+젊은\s+나이)?|CJ인터넷|엔씨소프트|자율주행\s+스타트업|CEO|이사|전무|경영\s+일선)"
        r"[^.!?]{0,96}(?:자산|동력|기반|통찰력|전문성|실행력|역량|리더십)"
        r"[^.!?]{0,24}(?:입니다|됩니다|될\s+것(?:입니다)?|갖추게\s+했(?:습니다)?|제공했(?:습니다)?|부여했(?:습니다)?|주었(?:습니다)?|길러주었(?:습니다)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"혁신적인\s+사고방식과\s+과감한\s+실행력은[^.!?]{0,80}"
        r"(?:자산|동력|기반)이\s+(?:될(?:\s+것(?:입니다)?)?|됩니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"[^.!?]{0,72}(?:사고방식|실행력|통찰력)[^.!?]{0,48}필수적인\s+자산이\s+될\s+것입니다",
        re.IGNORECASE,
    ),
    re.compile(
        r"저의\s+비전이\s+[^.!?]{0,56}(?:도약|변화|미래|부산)[^.!?]{0,32}(?:이끌|만들|바꿀)\s+것이라고\s+확신합니다",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:저의\s+)?경험(?:은|이)\s+[^.!?]{0,56}(?:성과로\s+)?증명된\s+것입니다",
        re.IGNORECASE,
    ),
    re.compile(r"열망을\s+보여주는\s+것(?:입니다|이었습니다)", re.IGNORECASE),
    re.compile(
        r"(?:저의\s+)?(?:리더십|실질적인\s+경험|경험과\s+리더십)[^.!?]{0,56}(?:이끌어낼|만들어낼|바꿔낼)\s+것(?:이라|이라고)\s+확신합니다",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:이는|이것은)\s+제가\s+[^.!?]{0,96}(?:실현해\s+온|해온|쌓아온)[^.!?]{0,32}(?:증거입니다|방증입니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"최근\s+여론조사\s+결과는\s+(?:저\s+)?이재성(?:의)?\s+가능성을\s+분명히\s+보여주고\s+있습니다",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:저는|이재성은|이재성이)\s+(?:(?:조금씩|확실히|점점)\s+){1,2}알려지고\s+있",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:겸허히\s+받아들이(?:며|고|겠)|(?:더욱\s+)?낮은\s+자세로)[^.!?]{0,96}",
        re.IGNORECASE,
    ),
    re.compile(
        r"단순(?:한|히)\s+[^.!?]{0,64}"
        r"(?:(?:가|이|은|는)\s+(?:아니라|아닌)|"
        r"[을를]\s+넘어(?:서|섭니다|서며|섰|선)?|"
        r"에\s+그치지\s+않(?:고|습니다)|"
        r"머무르지\s+않(?:고|습니다)|"
        r"만이\s+아니라|"
        r"이론(?:적(?:인)?)?|"
        r"볼\s+수\s+없(?:습니다|다))",
        re.IGNORECASE,
    ),
    re.compile(
        r"단순(?:히|한)\s+[^.!?]{0,40}"
        r"(?:고향|약속|기업\s*경영|경제\s*지표|행정|구호|이론)"
        r"[^.!?]{0,24}(?:에만|로만|만으로|뿐|(?:가|이|은|는)\s+(?:아니라|아닌)|"
        r"[을를]\s+넘어(?:서|섭니다|서며|섰|선)?|에\s+그치지\s+않(?:고|습니다)|"
        r"머무르지\s+않(?:고|습니다))",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:이러한|이런|저의)?\s*(?:혁신적인\s+)?(?:경영\s+)?경험(?:은|이|을)\s+[^.!?]{0,60}"
        r"(?:통찰력|전문성|역량|자산|능력|리더십)"
        r"[^.!?]{0,30}(?:길러주었|제공했|증명(?:된|합니|입니)|부여했|갖추게\s+했|주었)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:실제\s+성과(?:로)?\s+(?:이미\s+)?)증명된\s+(?:저의\s+)?(?:역량|전문성|능력|리더십)(?:입니다|이라고\s+할\s+수\s+있습니다)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:온라인에서는|정가에서는|이\s+흐름\s+속에서는?|마지막까지|끝까지)\s+"
        r"[가-힣]{2,8}\s*(?:현\s*|전\s*)?(?:국회의원|의원|도지사|지사|시장|위원장|대표|장관|예비후보|후보)?\s+"
        r"(?:출마\s+가능성도\s+함께\s+언급됩니다|후보론도\s+함께\s+거론됩니다|출마론도\s+이어집니다)",
        re.IGNORECASE,
    ),
)

_PROJECT_MANAGEMENT_SENTENCE_RE_LIST: tuple[re.Pattern[str], ...] = (
    re.compile(r"핵심\s+과제를\s+단계별로\s+정리하고\s+성과가\s+보이도록\s+꾸준히\s+점검하겠습니다", re.IGNORECASE),
    re.compile(r"우선순위를\s+명확히\s+하고\s+필요한\s+자원과\s+일정을\s+현실적으로\s+맞추겠습니다", re.IGNORECASE),
    re.compile(
        r"(?:명확한\s+)?우선순위를\s+설정(?:하고|해)\s*,?\s*(?:필요한\s+)?자원(?:과)?\s+일정을?\s+현실적(?:으로)?\s+맞추",
        re.IGNORECASE,
    ),
    re.compile(r"실행\s+과정에서\s+드러나는\s+한계(?:는|를)?\s+즉시\s+보완해\s+완성도를\s+높이겠습니다", re.IGNORECASE),
    re.compile(r"주민\s+의견을\s+수렴해\s+정책\s+방향을\s+구체화하고\s+실천\s+계획을\s+마련하겠습니다", re.IGNORECASE),
    re.compile(r"행정\s+절차와\s+예산\s+흐름까지\s+살펴\s+실현\s+가능한\s+해법으로\s+다듬겠습니다", re.IGNORECASE),
    re.compile(r"현장\s+목소리를\s+꾸준히\s+듣고\s+미흡한\s+지점은\s+빠르게\s+손보겠습니다", re.IGNORECASE),
    re.compile(r"부산의\s+산업과\s+생활\s+문제를\s+함께\s+보며\s+해법을\s+더\s+구체화하겠습니다", re.IGNORECASE),
    re.compile(r"사업\s+추진\s+현황을\s+투명하게\s+공개하고\s+결과로\s+증명하겠습니다", re.IGNORECASE),
    re.compile(r"지역\s+현안에\s+대한\s+전문가\s+자문과\s+주민\s+토론을\s+병행하겠습니다", re.IGNORECASE),
)

_SELF_ANALYTICAL_CAUSE_TOKENS: tuple[str, ...] = (
    "비전",
    "실천 의지",
    "접근",
    "진심",
    "소통",
    "역량",
    "진정성",
    "전문성",
    "실력",
    "행보",
    "노력",
    "배경",
    "경험",
    "봉사 정신",
    "삶의 궤적",
    "개인적인 서사",
    "직접적인 행보",
    "해결책 제시",
)

_SELF_ANALYTICAL_EFFECT_TOKENS: tuple[str, ...] = (
    "핵심 요인",
    "핵심 동력",
    "중요한 요인",
    "원동력",
    "방증",
    "증거",
    "증명합니다",
    "보여줍니다",
    "공감을 얻",
    "공감하기 시작",
    "기대를 모으고",
    "알아보고",
    "알아봐 주셨",
    "높이 평가해 주셨",
    "믿어주셨",
    "인정해 주셨",
    "길러주었습니다",
    "마음을 움직이고",
    "높이 평가하고",
    "적극적으로 인정해주신",
    "인지도가 확장",
    "인지도를 확장",
    "중요한 요소",
    "부여했습니다",
    "전달되며",
    "전달되고",
    "바탕이 됩니다",
    "요인이 됩니다",
    "진솔하게 다가가고 있다고 확신합니다",
    "인지도를 높이는 중요한 요인",
    "긍정적인 변화를 만들어내고 있다고 확신합니다",
)

_PROJECT_MANAGEMENT_SENTENCE_PHRASES: tuple[str, ...] = (
    "핵심 과제를 단계별로 정리하고 성과가 보이도록 꾸준히 점검하겠습니다",
    "우선순위를 명확히 하고 필요한 자원과 일정을 현실적으로 맞추겠습니다",
    "실행 과정에서 드러나는 한계는 즉시 보완해 완성도를 높이겠습니다",
    "주민 의견을 수렴해 정책 방향을 구체화하고 실천 계획을 마련하겠습니다",
    "행정 절차와 예산 흐름까지 살펴 실현 가능한 해법으로 다듬겠습니다",
    "현장 목소리를 꾸준히 듣고 미흡한 지점은 빠르게 손보겠습니다",
    "부산의 산업과 생활 문제를 함께 보며 해법을 더 구체화하겠습니다",
    "사업 추진 현황을 투명하게 공개하고 결과로 증명하겠습니다",
    "지역 현안에 대한 전문가 자문과 주민 토론을 병행하겠습니다",
)

_OBSERVER_FRAME_SENTENCE_RE_LIST: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:이미지(?:를)?\s+(?:(?:더\s+)?(?:확고히|분명히|새롭게)\s+)?(?:구축|강화|부각|굳히)|포지셔닝|브랜딩)"
        r"[^.!?]{0,56}(?:나서고\s+있|나섰|하고\s+있|전개하고\s+있|사로잡기\s+위해\s+나섰|사로잡고\s+있)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:당심|표심)\s+잡기(?:에)?\s+(?:나서고\s+있|나섰|돌입|주력)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:당심|민심|표심)(?:과\s*(?:당심|민심|표심))?"
        r"[^.!?]{0,24}(?:동시에\s+)?사로잡(?:기\s+위해\s+나섰|고\s+있)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:정치적\s+무게감|중량감|혁신성)"
        r"[^.!?]{0,56}(?:맞붙|맞부딪|대결\s+구도|구도가\s+형성)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:대결\s+구도|양자\s+대결\s+구도|삼자\s+대결\s+구도)"
        r"[^.!?]{0,20}(?:형성되|만들어졌)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:공관위|후보\s+공모)"
        r"[^.!?]{0,88}(?:경선\s+후보|후보)로\s+(?:선정|확정)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:민주당\s+)?공관위"
        r"[^.!?]{0,120}(?:컨벤션\s+효과|선거\s+분위기)"
        r"[^.!?]{0,72}(?:경선\s+실시를\s+결정|실시를\s+최종적으로\s+결정|최종적으로\s+경선\s+실시를\s+결정|결정했습니다)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:현역\s+의원의\s+['\"]?정치적\s+무게감['\"]?"
        r"|영입\s+인재\s+출신\s+기업인의\s+['\"]?혁신성['\"]?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:[가-힣]{2,4}\s+(?:전\s*)?(?:국회의원|의원|예비후보|후보|위원장|대표))"
        r"[^.!?]{0,80}(?:강조합니다|내세웁니다|말합니다|설명합니다)",
        re.IGNORECASE,
    ),
)

_INCOMPLETE_SENTENCE_ENDINGS: tuple[str, ...] = (
    "깊이",
    "향해",
    "통해",
    "위해",
    "바탕으로",
    "의미를",
    "가능성을",
    "기대를",
    "비전을",
    "책임감을",
    "의지를",
    "확신을",
)

_COMPLETE_SENTENCE_ENDINGS: tuple[str, ...] = (
    "다",
    "니다",
    "습니다",
    "입니다",
    "합니다",
    "됩니다",
    "있습니다",
    "바랍니다",
    "약속드립니다",
)

_PREDICATELESS_FRAGMENT_ENDING_RE = re.compile(
    r"(?:[가-힣]+(?:에|에서|으로|로|와|과|이|가|을|를|의|도)|진심으로|특히|또한|그리고|먼저|다시|함께)\s*$"
)
_PREDICATE_SURFACE_RE = re.compile(
    r"(?:"
    r"하겠(?:습니다)?|되겠(?:습니다)?|이겠(?:습니다)?|"
    r"합니다|했습니다|하였습니다|됩니다|됐습니다|되었습니다|"
    r"있습니다|없습니다|입니다|였습니다|이었다|였다|이다|"
    r"한다|했다|하는|하며|하고|됐다|된다|된다면|보입니다|드립니다|받습니다|남깁니다"
    r")$"
)


def _normalize_story_effect_prefix(prefix: str, label: str) -> str:
    text = re.sub(r"\s+", " ", str(prefix or "")).strip(" ,")
    if not text:
        return ""

    replacements = (
        ("함께 해온", "함께 해왔습니다"),
        ("함께해온", "함께해왔습니다"),
        ("해온", "해왔습니다"),
        ("살아온", "살아왔습니다"),
        ("걸어온", "걸어왔습니다"),
        ("지켜온", "지켜왔습니다"),
        ("다져온", "다져왔습니다"),
        ("이어온", "이어왔습니다"),
        ("만들어온", "만들어왔습니다"),
        ("키워온", "키워왔습니다"),
        ("겪어온", "겪어왔습니다"),
        ("보아온", "보아왔습니다"),
        ("봐온", "봐왔습니다"),
        ("배워온", "배워왔습니다"),
    )
    for source, target in replacements:
        if text.endswith(source):
            return f"{text[:-len(source)]}{target}."

    if text.endswith("입니다") or text.endswith("입니다."):
        return text if text.endswith(".") else f"{text}."
    if text.endswith("했습니다") or text.endswith("했습니다."):
        return text if text.endswith(".") else f"{text}."
    if text.endswith("해왔습니다") or text.endswith("해왔습니다."):
        return text if text.endswith(".") else f"{text}."

    normalized_label = re.sub(r"\s+", " ", str(label or "")).strip()
    if text.endswith(normalized_label):
        text = text[: -len(normalized_label)].rstrip(" ,")
        if text.endswith("해온"):
            return f"{text[:-2]}해왔습니다."
        if text.endswith("해왔습니다"):
            return f"{text}."

    if text.endswith("이야기") or text.endswith("서사") or text.endswith("배경") or text.endswith("경험"):
        return f"{text}입니다."

    return f"{text}."


def _strip_self_analytical_story_effect_tail(text: str) -> tuple[str, int]:
    def _replace(match: re.Match[str]) -> str:
        prefix = str(match.group("prefix") or "")
        label = str(match.group("label") or "")
        normalized = _normalize_story_effect_prefix(prefix, label)
        return normalized or prefix.strip()

    return _SELF_ANALYTICAL_STORY_TAIL_PATTERN.subn(_replace, str(text or ""))


def _drop_low_signal_analysis_sentences_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    replacements: list[tuple[int, int, str]] = []
    dropped_count = 0
    trimmed_count = 0

    for para_match in PARAGRAPH_TAG_PATTERN.finditer(base):
        inner = str(para_match.group(1) or "")
        plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", inner))
        if not plain_inner:
            continue

        sentences = _split_sentence_like_units(plain_inner)
        updated_sentences: list[str] = []

        for sentence in sentences:
            normalized = _normalize_inline_whitespace(sentence)
            if not normalized:
                continue

            if (
                "결과로 나타났습니다" in normalized
                and "," in normalized
                and any(token in normalized for token in _SELF_ANALYTICAL_CAUSE_TOKENS)
            ):
                result_text = _normalize_inline_whitespace(normalized.rsplit(",", 1)[-1])
                if "결과로 나타났습니다" in result_text:
                    if not result_text.endswith((".", "!", "?")):
                        result_text = f"{result_text}."
                    updated_sentences.append(result_text)
                    trimmed_count += 1
                    continue

            trimmed_match = _SELF_ANALYTICAL_RESULT_TRIM_PATTERN.match(normalized)
            if trimmed_match:
                result_text = _normalize_inline_whitespace(str(trimmed_match.group("result") or ""))
                if result_text:
                    if not result_text.endswith((".", "!", "?")):
                        result_text = f"{result_text}."
                    updated_sentences.append(result_text)
                    trimmed_count += 1
                    continue

            polished_sentence = normalized
            for pattern in _LINK_EXPR_RE_LIST:
                if pattern.search(polished_sentence):
                    polished_sentence = pattern.sub("", polished_sentence, count=1)
            for pattern in _VERBOSE_POSTPOS_RE_LIST:
                if pattern.search(polished_sentence):
                    polished_sentence = pattern.sub("", polished_sentence)
            if _HOEKIJEOK_RE.search(polished_sentence):
                polished_sentence = _normalize_inline_whitespace(_HOEKIJEOK_RE.sub("", polished_sentence)).strip()
                if not polished_sentence:
                    dropped_count += 1
                    continue
            if _JEOKGEUKJEOK_RE.search(polished_sentence):
                polished_sentence = _normalize_inline_whitespace(_JEOKGEUKJEOK_RE.sub("", polished_sentence)).strip()
                if not polished_sentence:
                    dropped_count += 1
                    continue
            if _GYEOMHEO_CLAUSE_RE.search(polished_sentence):
                polished_sentence = _normalize_inline_whitespace(_GYEOMHEO_CLAUSE_RE.sub("", polished_sentence)).strip(" ,")
                if not polished_sentence:
                    dropped_count += 1
                    continue
            if _LOW_POSTURE_CLAUSE_RE.search(polished_sentence):
                polished_sentence = _normalize_inline_whitespace(_LOW_POSTURE_CLAUSE_RE.sub("", polished_sentence)).strip(" ,")
                if not polished_sentence:
                    dropped_count += 1
                    continue
            if _CONFIRMATION_PHRASE_RE.search(polished_sentence):
                polished_sentence = _normalize_inline_whitespace(
                    _CONFIRMATION_PHRASE_RE.sub("것입니다", polished_sentence)
                ).strip()
                if not polished_sentence:
                    dropped_count += 1
                    continue
            if _DOUBLE_PASSIVE_RE.search(polished_sentence):
                polished_sentence = _DOUBLE_PASSIVE_RE.sub(r"되\1", polished_sentence)
            polished_sentence = _normalize_inline_whitespace(polished_sentence).strip()
            if not polished_sentence:
                dropped_count += 1
                continue
            if any(pattern.search(polished_sentence) for pattern in _SIMPLE_NEGATION_FRAME_RE_LIST) or any(
                pattern.search(polished_sentence) for pattern in _NEGATION_FRAME_EXT_RE_LIST
            ):
                dropped_count += 1
                continue
            if any(pattern.search(polished_sentence) for pattern in _TRANSLATION_RE_LIST):
                dropped_count += 1
                continue

            has_cause_token = any(token in polished_sentence for token in _SELF_ANALYTICAL_CAUSE_TOKENS)
            has_effect_token = any(token in polished_sentence for token in _SELF_ANALYTICAL_EFFECT_TOKENS)

            if (has_cause_token and has_effect_token) or any(
                pattern.search(polished_sentence) for pattern in _SELF_ANALYTICAL_LOW_SIGNAL_RE_LIST
            ):
                dropped_count += 1
                continue

            if any(phrase in polished_sentence for phrase in _PROJECT_MANAGEMENT_SENTENCE_PHRASES) or any(
                pattern.search(polished_sentence) for pattern in _PROJECT_MANAGEMENT_SENTENCE_RE_LIST
            ):
                dropped_count += 1
                continue

            updated_sentences.append(polished_sentence)

        rebuilt_inner = " ".join(updated_sentences).strip()
        if rebuilt_inner == plain_inner:
            continue
        if not rebuilt_inner:
            replacements.append((para_match.start(), para_match.end(), ""))
        else:
            replacements.append((para_match.start(1), para_match.end(1), rebuilt_inner))

    if not replacements:
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    for start, end, replacement in sorted(replacements, key=lambda item: -item[0]):
        repaired = repaired[:start] + replacement + repaired[end:]

    actions: list[str] = []
    if trimmed_count > 0:
        actions.append(f"trim_self_analytical_result_clause:{trimmed_count}")
    if dropped_count > 0:
        actions.append(f"drop_low_signal_analysis_sentence:{dropped_count}")
    return {"content": repaired, "edited": repaired != base, "actions": actions}


def _drop_observer_frame_sentences_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    replacements: list[tuple[int, int, str]] = []
    dropped_count = 0

    for para_match in PARAGRAPH_TAG_PATTERN.finditer(base):
        plain_inner = re.sub(r"<[^>]*>", " ", str(para_match.group(1) or ""))
        plain_inner = re.sub(r"\s+", " ", plain_inner).strip()
        if not plain_inner:
            continue

        updated_sentences: list[str] = []
        for sentence in _split_sentence_like_units(plain_inner):
            polished_sentence = _normalize_inline_whitespace(sentence).strip()
            if not polished_sentence:
                continue
            if any(pattern.search(polished_sentence) for pattern in _OBSERVER_FRAME_SENTENCE_RE_LIST):
                dropped_count += 1
                continue
            updated_sentences.append(polished_sentence)

        rebuilt_inner = " ".join(updated_sentences).strip()
        if rebuilt_inner == plain_inner:
            continue
        if not rebuilt_inner:
            replacements.append((para_match.start(), para_match.end(), ""))
        else:
            replacements.append((para_match.start(1), para_match.end(1), rebuilt_inner))

    if not replacements:
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    for start, end, replacement in sorted(replacements, key=lambda item: -item[0]):
        repaired = repaired[:start] + replacement + repaired[end:]

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": [f"drop_observer_frame_sentence:{dropped_count}"] if dropped_count > 0 else [],
    }


_SECTION_LEADING_DEMONSTRATIVE_RE = re.compile(r"^(?P<lemma>이는|이것은)\s+(?P<rest>.+)$", re.IGNORECASE)
_SECTION_LEADING_DEMONSTRATIVE_NOUN_RE = re.compile(
    r"^(?:이러한|이런)\s+[^.!?]{0,28}?(?:은|는|이|가)\s+(?P<rest>.+)$",
    re.IGNORECASE,
)
_SECTION_LEADING_DEMONSTRATIVE_CONTEXT_RE = re.compile(
    r"^(?:(?:이는|이것은)\s+|(?:이러한|이런)\s+[^.!?]{0,28}?(?:은|는|이|가)\s+)"
    r"[^.!?]{0,120}"
    r"(?:선택지(?:를|가)?[^.!?]{0,24}\s+제공|선택의\s+기회(?:를|가)?[^.!?]{0,24}\s+제공|선택의\s+시작(?:을|이)?[^.!?]{0,24}\s+알리|제공하며|의미를\s+갖|보여주|이어지|흐름|전망|인정받은\s+결과|평가받은\s+결과)",
    re.IGNORECASE,
)
_HEADING_SUBJECT_CANDIDATE_RE = re.compile(
    r"([가-힣0-9][가-힣0-9\s]{0,24}(?:선택|해법|방안|비전|경선|선거|대결|변화|미래|전환|확정|시작))(?:은|는|이|가|을|를)?$",
    re.IGNORECASE,
)


def _build_section_opening_subject_from_heading(h2_text: str) -> str:
    heading = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(h2_text or ""))).strip(" .!?")
    if not heading:
        return ""

    clauses = [clause.strip(" .!?") for clause in re.split(r"[,;:·]\s*", heading) if clause.strip(" .!?")]
    if clauses and any(token in heading for token in ("확정", "시작")):
        return f"{_normalize_inline_whitespace(clauses[0])}은"
    for clause in reversed(clauses):
        if re.search(r"(?:은|는)$", clause):
            return _normalize_inline_whitespace(clause)
        candidate_match = _HEADING_SUBJECT_CANDIDATE_RE.search(clause)
        if candidate_match:
            return f"{_normalize_inline_whitespace(candidate_match.group(1))}은"
    if clauses:
        first_clause = _normalize_inline_whitespace(clauses[0])
        if any(token in first_clause for token in ("확정", "시작")):
            return f"{first_clause}은"

    if "경선" in heading:
        return "이번 경선은"
    if "선거" in heading:
        return "이번 선거는"
    if "대결" in heading:
        return "이번 대결은"
    if "해법" in heading:
        return "해법은"
    if "방안" in heading:
        return "구체적 방안은"
    if "비전" in heading:
        return "비전은"
    if "선택" in heading:
        return "이 선택은"
    return ""


def _repair_contextless_section_openers_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    sections = _split_into_sections(base)
    repaired_sections = list(sections)
    repaired_count = 0

    for index, section in enumerate(sections):
        if index == 0 or not section.get("has_h2"):
            continue

        section_html = str(section.get("html") or "")
        paragraph_match = PARAGRAPH_TAG_PATTERN.search(section_html)
        if not paragraph_match:
            continue

        inner = str(paragraph_match.group(1) or "")
        plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", inner))
        if not plain_inner:
            continue

        sentences = _split_sentence_like_units(plain_inner)
        if not sentences:
            continue

        first_sentence = _normalize_inline_whitespace(sentences[0]).strip()
        has_contextless_lead = bool(_SECTION_LEADING_DEMONSTRATIVE_CONTEXT_RE.search(first_sentence))
        if (
            not has_contextless_lead
            and first_sentence.startswith(("이는 ", "이것은 "))
            and "선택의 시작" in first_sentence
            and "알리" in first_sentence
        ):
            has_contextless_lead = True
        if not has_contextless_lead:
            continue

        subject = _build_section_opening_subject_from_heading(str(section.get("h2_text") or ""))
        if not subject:
            continue

        noun_match = _SECTION_LEADING_DEMONSTRATIVE_NOUN_RE.match(first_sentence)
        if noun_match:
            updated_first = f"{subject} {str(noun_match.group('rest') or '').lstrip()}".strip()
        else:
            updated_first = _SECTION_LEADING_DEMONSTRATIVE_RE.sub(
                lambda match: f"{subject} {str(match.group('rest') or '').lstrip()}",
                first_sentence,
                count=1,
            ).strip()
        if not updated_first or updated_first == first_sentence:
            continue

        rebuilt_inner = " ".join([updated_first, *sentences[1:]]).strip()
        if not rebuilt_inner or rebuilt_inner == plain_inner:
            continue

        updated_html = section_html[: paragraph_match.start(1)] + rebuilt_inner + section_html[paragraph_match.end(1) :]
        repaired_sections[index] = {**section, "html": updated_html}
        repaired_count += 1

    if repaired_count == 0:
        return {"content": base, "edited": False, "actions": []}

    repaired = _join_sections(repaired_sections)
    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": [f"repair_contextless_section_opener:{repaired_count}"],
    }


def _resolve_full_name(
    *,
    data: Dict[str, Any],
    user_profile: Dict[str, Any],
    pipeline_result: Dict[str, Any],
    provisional_name: str = "",
) -> str:
    direct_candidates = [
        provisional_name,
        data.get("fullName"),
        data.get("name"),
        user_profile.get("fullName"),
        user_profile.get("name"),
        pipeline_result.get("fullName"),
        pipeline_result.get("name"),
    ]
    for candidate in direct_candidates:
        cleaned = _clean_full_name_candidate(candidate)
        if cleaned:
            return cleaned

    text_candidates: list[str] = []
    for field in ("stanceText", "sourceInput", "sourceContent", "originalContent", "inputContent"):
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            text_candidates.append(value)

    instructions = data.get("instructions")
    if isinstance(instructions, list):
        for item in instructions:
            if isinstance(item, str) and item.strip():
                text_candidates.append(item)
    elif isinstance(instructions, str) and instructions.strip():
        text_candidates.append(instructions)

    for field in ("stanceText", "sourceInput"):
        value = pipeline_result.get(field)
        if isinstance(value, str) and value.strip():
            text_candidates.append(value)

    for text in text_candidates:
        candidate = _extract_name_from_signature_text(text)
        if candidate:
            return candidate
    return ""


def _is_same_speaker_name(candidate: str, full_name: str) -> bool:
    return is_same_speaker_name(candidate, full_name)


def _extract_speaker_consistency_issues(content: str, full_name: str) -> list[str]:
    speaker_name = _normalize_person_name(full_name)
    if not speaker_name:
        return ["화자 실명이 없어 1인칭 정체성 검증을 수행할 수 없음"]

    plain = re.sub(r"<[^>]*>", " ", str(content or ""))
    plain = re.sub(r"\s+", " ", plain).strip()
    if not plain:
        return []

    role_expr = r"(?:시장|부산시장|시장후보|후보|의원|위원장|대표|전\s*위원장)"
    role_plus_pronoun_expr = (
        r"(?:(?:현|전)\s*)?"
        r"(?:[가-힣]{1,12})?"
        r"(?:국회의원|시의원|도의원|구의원|군의원|광역의원|기초의원|"
        r"의원|시장후보|시장|도지사|지사|구청장|군수|위원장|대표|장관)"
    )
    patterns = [
        re.compile(
            rf"저는\s*([가-힣]{{2,8}})\s*(?:{role_expr})?\s*(?:로서|으로서|입니다|이라|라는)",
            re.IGNORECASE,
        ),
        re.compile(rf"저\s*([가-힣]{{2,8}})\s*(?:은|는)\s*(?:{role_expr})", re.IGNORECASE),
    ]

    issues: list[str] = []
    for pattern in patterns:
        for match in pattern.finditer(plain):
            detected_name = str(match.group(1) or "").strip()
            if not detected_name:
                continue
            if _is_same_speaker_name(detected_name, speaker_name):
                continue
            issues.append(f"1인칭 화자가 \"{detected_name}\"으로 표기됨")
            break
        if issues:
            break

    self_object_pattern = re.compile(rf"저는\s*{re.escape(speaker_name)}\s*(?:도|를|을)\s*", re.IGNORECASE)
    if self_object_pattern.search(plain):
        issues.append(f"1인칭 문장에서 \"{speaker_name}\" 이름 목적어 오용")

    reverse_pattern = re.compile(
        rf"([가-힣]{{2,8}})\s*(?:{role_expr})\s*로서\s*(저는|제가|저)\b",
        re.IGNORECASE,
    )
    reverse_match = reverse_pattern.search(plain)
    if reverse_match:
        reverse_name = str(reverse_match.group(1) or "").strip()
        if reverse_name and not _is_same_speaker_name(reverse_name, speaker_name):
            issues.append(f"화자 앞 수식어로 \"{reverse_name}\" 인명이 사용됨")

    unresolved_self_placeholder_patterns = (
        re.compile(
            r"저\s+이\s*(?:예비후보|후보|의원|위원장|대표)"
            r"(?:께서는|께서|에게|으로서|로서|으로|로|은|는|이|가|을|를|의|와|과|도)?",
            re.IGNORECASE,
        ),
        re.compile(
            r"이\s*(?:예비후보|후보|의원|위원장|대표)"
            r"(?:께서는|께서|에게|으로서|로서|으로|로|은|는|이|가|을|를|의|와|과|도)?"
            r"[^.!?]{0,40}(?:하겠습니다|이뤄내겠습니다|보여드리겠습니다|말씀드리겠습니다|약속드립니다)",
            re.IGNORECASE,
        ),
    )
    if any(pattern.search(plain) for pattern in unresolved_self_placeholder_patterns):
        issues.append('1인칭 화자 이름이 "이 후보" placeholder로 남음')
    if _has_generic_self_opponent_placeholder(plain):
        issues.append('화자 이름이 "상대" placeholder로 남음')

    named_pronoun_pattern = re.compile(
        rf"{re.escape(speaker_name)}\s*(?:부산시장|시장후보|후보|예비후보|의원|위원장|대표)?\s*(?:은|는|이|가)?\s*(저는|제가|저의|제)\b",
        re.IGNORECASE,
    )
    if named_pronoun_pattern.search(plain):
        issues.append("화자 실명 뒤에 1인칭 대명사가 중복됨")
    role_pronoun_pattern = re.compile(
        rf"(?<![가-힣]){role_plus_pronoun_expr}\s+(저는|제가|저의|제)\b",
        re.IGNORECASE,
    )
    if role_pronoun_pattern.search(plain):
        issues.append("직함 뒤에 1인칭 대명사가 중복됨")
    return issues


def _repair_speaker_consistency_once(content: str, full_name: str) -> Dict[str, Any]:
    base = str(content or "")
    speaker_name = _normalize_person_name(full_name)
    if not base.strip() or not speaker_name:
        return {"content": base, "edited": False, "appliedPatterns": []}

    applied_patterns: list[str] = []
    repaired = base
    role_expr = r"(?:부산시장|시장|시장후보|후보|의원|위원장|대표|전\s*위원장)"
    role_plus_pronoun_expr = (
        r"(?:(?:현|전)\s*)?"
        r"(?:[가-힣]{1,12})?"
        r"(?:국회의원|시의원|도의원|구의원|군의원|광역의원|기초의원|"
        r"의원|시장후보|시장|도지사|지사|구청장|군수|위원장|대표|장관)"
    )

    def _replace_first_person_named(match: re.Match[str]) -> str:
        pronoun = str(match.group(1) or "저는").strip()
        name = str(match.group(2) or "").strip()
        if not name or _is_same_speaker_name(name, speaker_name):
            return match.group(0)
        applied_patterns.append("first_person_named_role")
        return f"{pronoun} "

    pattern_first_person_named = re.compile(
        rf"(저는|제가|저)\s*([가-힣]{{2,8}})\s*(?:{role_expr})?\s*(?:로서|으로서|입니다|이라|라는|은|는)",
        re.IGNORECASE,
    )
    repaired = pattern_first_person_named.sub(_replace_first_person_named, repaired)

    def _replace_reverse_named(match: re.Match[str]) -> str:
        name = str(match.group(1) or "").strip()
        pronoun = str(match.group(2) or "저는").strip()
        if not name or _is_same_speaker_name(name, speaker_name):
            return match.group(0)
        applied_patterns.append("reverse_named_role")
        return f"{pronoun} "

    pattern_reverse_named = re.compile(
        rf"([가-힣]{{2,8}})\s*(?:{role_expr})\s*로서\s*(저는|제가|저)\b",
        re.IGNORECASE,
    )
    repaired = pattern_reverse_named.sub(_replace_reverse_named, repaired)

    self_object_pattern = re.compile(
        rf"(저는|제가)\s*{re.escape(speaker_name)}\s*(?:도|를|을)\s*",
        re.IGNORECASE,
    )

    def _replace_self_object(match: re.Match[str]) -> str:
        pronoun = str(match.group(1) or "저는").strip()
        applied_patterns.append("self_name_object")
        return f"{pronoun} "

    repaired = self_object_pattern.sub(_replace_self_object, repaired)

    named_pronoun_pattern = re.compile(
        rf"{re.escape(speaker_name)}\s*(?:부산시장|시장후보|후보|예비후보|의원|위원장|대표)?\s*(?:은|는|이|가)?\s*(저는|제가|저의|제)\b",
        re.IGNORECASE,
    )

    def _replace_named_pronoun(match: re.Match[str]) -> str:
        pronoun = str(match.group(1) or "저는").strip()
        applied_patterns.append("speaker_name_plus_pronoun")
        return f"{pronoun}"

    repaired = named_pronoun_pattern.sub(_replace_named_pronoun, repaired)
    role_pronoun_pattern = re.compile(
        rf"(?<![가-힣]){role_plus_pronoun_expr}\s+(저는|제가|저의|제)\b",
        re.IGNORECASE,
    )

    def _replace_role_pronoun(match: re.Match[str]) -> str:
        pronoun = str(match.group(1) or "저는").strip()
        applied_patterns.append("role_plus_pronoun")
        return pronoun

    repaired = role_pronoun_pattern.sub(_replace_role_pronoun, repaired)
    repaired = re.sub(r"(저는|제가)\s*[,，]\s*", r"\1 ", repaired)
    repaired = re.sub(r"\s{2,}", " ", repaired)

    return {
        "content": repaired,
        "edited": repaired != base,
        "appliedPatterns": sorted(set(applied_patterns)),
    }


def _canonical_role_label(role: str) -> str:
    return canonical_role_label(role)


def _extract_keyword_person_role(keyword: str) -> tuple[str, str]:
    return extract_keyword_person_role(keyword)


def _apply_speaker_name_keyword_max_override(
    user_keywords: Sequence[str],
    full_name: str,
    overrides: Dict[str, int],
    *,
    protected_max: int = 999,
) -> Dict[str, int]:
    if not isinstance(overrides, dict):
        return {}

    speaker_name = _clean_full_name_candidate(full_name)
    if not speaker_name:
        return overrides

    for raw_keyword in user_keywords or []:
        keyword = str(raw_keyword or "").strip()
        if not keyword:
            continue
        keyword_name, _keyword_role = _extract_keyword_person_role(keyword)
        candidate_name = keyword_name or _clean_full_name_candidate(keyword)
        if not candidate_name or not _is_same_speaker_name(candidate_name, speaker_name):
            continue
        current_value = overrides.get(keyword)
        try:
            current_max = int(current_value) if current_value is not None else 0
        except (TypeError, ValueError):
            current_max = 0
        overrides[keyword] = max(int(protected_max or 0), current_max)

    return overrides


def _find_conflicting_role_keyword(
    user_keywords: list[str],
    person_roles: Dict[str, str],
) -> str:
    normalized_user_keywords = [str(item or "").strip() for item in (user_keywords or []) if str(item or "").strip()]
    if not normalized_user_keywords or not person_roles:
        return ""

    for keyword in normalized_user_keywords:
        name, keyword_role = _extract_keyword_person_role(keyword)
        if not name or not keyword_role:
            continue
        expected_role = _canonical_role_label(person_roles.get(name) or "")
        if expected_role and not roles_equivalent_common(expected_role, keyword_role):
            return keyword
    return ""


def _collect_known_person_names(
    *,
    full_name: str,
    role_facts: Dict[str, str],
    user_keywords: list[str],
    poll_fact_table: Dict[str, Any],
) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    def _push(candidate: str) -> None:
        normalized = _normalize_person_name(candidate)
        if len(normalized) < 2 or len(normalized) > 8:
            return
        if normalized in seen:
            return
        seen.add(normalized)
        names.append(normalized)

    _push(full_name)
    for name in (role_facts or {}).keys():
        _push(str(name))
    for keyword in user_keywords or []:
        extracted_name, _ = _extract_keyword_person_role(str(keyword))
        if extracted_name:
            _push(extracted_name)

    pairs = _safe_dict(poll_fact_table).get("pairs") or {}
    if isinstance(pairs, dict):
        for pair_key in pairs.keys():
            key_text = str(pair_key or "").strip()
            if "__" in key_text:
                left, right = key_text.split("__", 1)
                _push(left)
                _push(right)
    return names


_HEADING_ALIGNMENT_STOPWORDS = {
    "이유",
    "배경",
    "무엇",
    "무엇인가",
    "무엇을",
    "어떻게",
    "왜",
    "지금",
    "해야",
    "하나",
    "대한",
    "위한",
    "통한",
    "관련",
    "에서",
    "하는",
}

_HEADING_ALIGNMENT_SUFFIXES = (
    "에서는",
    "과의",
    "와의",
    "으로는",
    "에게는",
    "에서",
    "으로",
    "에게",
    "에는",
    "부터",
    "까지",
    "처럼",
    "보다",
    "과",
    "와",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "로",
    "도",
    "만",
)


def _heading_alignment_tokens(text: str) -> set[str]:
    normalized = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not normalized:
        return set()
    tokens: set[str] = set()
    for raw in re.findall(r"[0-9A-Za-z가-힣]{2,}", normalized):
        token = raw.lower().strip()
        for suffix in _HEADING_ALIGNMENT_SUFFIXES:
            if token.endswith(suffix) and len(token) - len(suffix) >= 2:
                token = token[: -len(suffix)]
                break
        if not token or token in _HEADING_ALIGNMENT_STOPWORDS:
            continue
        if token.isdigit():
            continue
        tokens.add(token)
    return tokens


def _compute_heading_body_alignment_score(heading: str, body_text: str) -> float:
    heading_tokens = _heading_alignment_tokens(heading)
    if not heading_tokens:
        return 0.0
    body_tokens = _heading_alignment_tokens(body_text)
    if not body_tokens:
        return 0.0
    overlap = len(heading_tokens & body_tokens)
    return overlap / max(1, len(heading_tokens))


def _is_interrogative_heading(text: str) -> bool:
    normalized = _normalize_inline_whitespace(text)
    if not normalized:
        return False
    return bool(
        normalized.endswith("?")
        or normalized.startswith("왜 ")
        or any(token in normalized for token in ("무엇", "어떻게", "인가", "하나"))
    )


def _rewrite_paragraph_blocks(content: str, rewrite_fn) -> str:
    base = str(content or "")
    matches = list(PARAGRAPH_TAG_PATTERN.finditer(base))
    if not matches:
        return str(rewrite_fn(base))

    parts: list[str] = []
    cursor = 0
    for match in matches:
        parts.append(base[cursor: match.start(1)])
        rewritten_inner = str(rewrite_fn(str(match.group(1) or "")) or "")
        parts.append(rewritten_inner)
        cursor = match.end(1)
    parts.append(base[cursor:])
    return "".join(parts)


def _extract_role_check_plain_text(content: str) -> str:
    base = str(content or "")
    paragraph_texts = [
        re.sub(r"<[^>]*>", " ", str(match.group(1) or ""))
        for match in PARAGRAPH_TAG_PATTERN.finditer(base)
    ]
    if paragraph_texts:
        plain = " ".join(paragraph_texts)
    else:
        plain = re.sub(r"<[^>]*>", " ", base)
    return re.sub(r"\s+", " ", plain).strip()


def _is_protected_search_keyword_role_mention(text: str, start: int, end: int) -> bool:
    source = str(text or "")
    if not source or start < 0 or end <= start:
        return False

    before = source[max(0, start - 8) : start]
    after = source[end : min(len(source), end + 16)]
    quote_before = bool(QUOTE_CHAR_PATTERN.search(before[-2:]))
    if not quote_before:
        return False

    return bool(re.match(r"\s*[\"'“”‘’]?\s*(?:검색어|키워드|표현|문구)", after))


def _looks_like_person_name_token(token: Any) -> bool:
    normalized = re.sub(r"\s+", "", str(token or "")).strip()
    if len(normalized) < 2 or len(normalized) > 4:
        return False
    if normalized[-1] in "은는이가도를을와과의로":
        return False

    blocked_tokens = {
        "더불어민주당",
        "국민의힘",
        "민주당",
        "부산시당",
        "시당",
        "후보군",
        "예비후보",
        "캠프",
        "시민",
        "경제",
        "부산",
    }
    if normalized in blocked_tokens:
        return False

    blocked_suffixes = ("시당", "정당", "캠프", "후보군", "예비후보")
    return not any(normalized.endswith(suffix) for suffix in blocked_suffixes)


def _is_valid_person_role_chain_text(text: Any, *, min_pairs: int) -> bool:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain:
        return False

    pairs = PERSON_ROLE_PAIR_PATTERN.findall(plain)
    if len(pairs) < min_pairs:
        return False
    valid_count = sum(1 for name, _role in pairs if _looks_like_person_name_token(name))
    return valid_count >= min_pairs


def _find_valid_person_chain_match(text: Any) -> Optional[re.Match[str]]:
    source = str(text or "")
    for match in PERSON_ROLE_CHAIN_CANDIDATE_PATTERN.finditer(source):
        if _is_valid_person_role_chain_text(match.group(0), min_pairs=3):
            return match
    return None


def _find_valid_numeric_person_chain_match(text: Any) -> Optional[re.Match[str]]:
    source = str(text or "")
    for match in NUMERIC_PERSON_CHAIN_CANDIDATE_PATTERN.finditer(source):
        if _is_valid_person_role_chain_text(match.group(0), min_pairs=2):
            return match
    return None


def _normalize_inline_whitespace(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _content_log_preview(text: Any, limit: int = 220) -> str:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if len(plain) <= limit:
        return plain
    return f"{plain[:limit].rstrip()}..."


_NO_SPACE_COMPOUND_WARNING_RE = re.compile(r"(?P<token>[가-힣]{8,}(?:은|는|이|가|을|를|의))")


def _warn_if_no_space_compound(content: Any, stage: str) -> None:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(content or "")))
    if not plain:
        return
    for match in _NO_SPACE_COMPOUND_WARNING_RE.finditer(plain):
        token = str(match.group("token") or "").strip()
        if token:
            logger.warning("[%s] 공백 없는 복합 접합 감지: %s", stage, token)
            break


def _keyword_gate_log_summary(
    keyword_validation: Optional[Dict[str, Any]],
    keywords: Optional[list[str]],
) -> list[Dict[str, Any]]:
    validation = keyword_validation if isinstance(keyword_validation, dict) else {}
    user_keywords = [str(item).strip() for item in (keywords or []) if str(item).strip()]
    summary: list[Dict[str, Any]] = []
    for keyword in user_keywords:
        info = validation.get(keyword) if isinstance(validation.get(keyword), dict) else {}
        summary.append(
            {
                "keyword": keyword,
                "status": str(info.get("status") or ""),
                "count": int(info.get("count") or 0),
                "gateCount": int(info.get("gateCount") or 0),
                "expected": int(info.get("expected") or 0),
                "bodyCount": int(info.get("bodyCount") or 0),
                "bodyExpected": int(info.get("bodyExpected") or 0),
                "exactShortfall": int(info.get("exactShortfall") or 0),
            }
        )
    return summary


def _is_datetime_only_numeric_run(text: Any) -> bool:
    candidate = _normalize_inline_whitespace(text)
    if not candidate:
        return False
    return bool(DATETIME_ONLY_NUMERIC_RUN_PATTERN.fullmatch(candidate))


def _find_problematic_numeric_runs(text: Any) -> list[Dict[str, Any]]:
    source = str(text or "")
    if not source.strip():
        return []

    matches: list[Dict[str, Any]] = []
    for match in NUMERIC_UNIT_RUN_PATTERN.finditer(source):
        matched_text = _normalize_inline_whitespace(match.group(0))
        if not matched_text or _is_datetime_only_numeric_run(matched_text):
            continue
        matches.append(
            {
                "start": match.start(),
                "end": match.end(),
                "text": matched_text,
            }
        )
    return matches


def _extract_leading_datetime_prefix(text: Any) -> str:
    candidate = _normalize_inline_whitespace(text)
    if not candidate:
        return ""

    prefix_match = LEADING_DATETIME_PREFIX_PATTERN.match(candidate)
    if not prefix_match:
        return ""

    prefix = _normalize_inline_whitespace(prefix_match.group(0))
    if not prefix or not _is_datetime_only_numeric_run(prefix):
        return ""
    return prefix


def _scrub_suspicious_poll_residue_text(text: Any) -> Dict[str, Any]:
    base = str(text or "")
    if not base:
        return {"content": base, "edited": False, "actions": []}

    updated = base
    actions: list[str] = []
    for index, pattern in enumerate(SUSPICIOUS_POLL_RESIDUE_PATTERNS, start=1):
        updated, count = pattern.subn(" ", updated)
        if count > 0:
            actions.append(f"poll_residue:{index}:{count}")
    for index, pattern in enumerate(STRUCTURAL_MATCHUP_RESIDUE_PATTERNS, start=1):
        updated, count = pattern.subn(" ", updated)
        if count > 0:
            actions.append(f"matchup_residue:{index}:{count}")

    updated = re.sub(r"\s{2,}", " ", updated)
    updated = re.sub(r"\s+([,.;!?])", r"\1", updated)
    updated = updated.strip()
    return {
        "content": updated,
        "edited": updated != base,
        "actions": actions,
    }


def _looks_like_low_signal_residue_fragment(text: Any) -> bool:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain:
        return False

    noun_fragment = "|".join(re.escape(noun) for noun in LOW_SIGNAL_RESIDUE_NOUNS)
    short_name_noun_match = re.fullmatch(
        rf"(?P<name>[가-힣]{{2,4}})(?:도|은|는|이|가)?\s+(?P<noun>{noun_fragment})",
        plain,
        re.IGNORECASE,
    )
    if short_name_noun_match and _looks_like_person_name_token(short_name_noun_match.group("name") or ""):
        return True

    role_pairs = PERSON_ROLE_PAIR_PATTERN.findall(plain)
    cleaned_names = [
        cleaned
        for cleaned in (_clean_full_name_candidate(name) for name, _role in role_pairs)
        if cleaned and _looks_like_person_name_token(cleaned)
    ]
    if len(cleaned_names) < 2:
        return False

    if not any(noun in plain for noun in LOW_SIGNAL_RESIDUE_NOUNS):
        return False

    has_stable_predicate = bool(
        re.search(
            r"(?:입니다|됩니다|했습니다|하겠습니다|보입니다|보여줍니다|나타났습니다|의미합니다|전달하겠습니다|말씀드리겠습니다|강조하겠습니다)$",
            plain,
        )
    )
    repeated_name = any(cleaned_names.count(name) >= 2 for name in set(cleaned_names))
    trailing_noise = bool(re.search(rf"(?:{noun_fragment})\s*$", plain, re.IGNORECASE))
    return (repeated_name or len(cleaned_names) >= 2) and trailing_noise and not has_stable_predicate


def _prune_problematic_integrity_fragments(text: Any) -> Dict[str, Any]:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain:
        return {"content": "", "edited": False, "actions": []}

    fragments = [
        re.sub(r"\s+", " ", fragment).strip()
        for fragment in INTEGRITY_SENTENCE_SPLIT_PATTERN.split(plain)
        if re.sub(r"\s+", " ", fragment).strip()
    ]
    if not fragments:
        return {"content": html.escape(plain, quote=False), "edited": False, "actions": []}

    kept_fragments: list[str] = []
    removed_person_chain = 0
    removed_numeric_person_chain = 0
    removed_numeric_noise = 0
    removed_low_signal_residue = 0

    for fragment in fragments:
        if _find_valid_person_chain_match(fragment):
            removed_person_chain += 1
            continue
        if _find_valid_numeric_person_chain_match(fragment):
            removed_numeric_person_chain += 1
            continue
        if _looks_like_low_signal_residue_fragment(fragment):
            removed_low_signal_residue += 1
            continue

        problematic_runs = _find_problematic_numeric_runs(fragment)
        if problematic_runs:
            non_numeric_text = _normalize_inline_whitespace(
                re.sub(
                    rf"(?<!\S){_NUMERIC_UNIT_TOKEN_FRAGMENT}(?:\s+{_NUMERIC_UNIT_TOKEN_FRAGMENT})*",
                    " ",
                    fragment,
                )
            )
            has_meaningful_korean = bool(re.search(r"[가-힣]{2,}", non_numeric_text))
            if len(non_numeric_text) < 10 or not has_meaningful_korean:
                removed_numeric_noise += 1
                continue

        kept_fragments.append(fragment)

    actions: list[str] = []
    if removed_person_chain > 0:
        actions.append(f"drop_person_chain_fragment:{removed_person_chain}")
    if removed_numeric_person_chain > 0:
        actions.append(f"drop_numeric_person_chain_fragment:{removed_numeric_person_chain}")
    if removed_numeric_noise > 0:
        actions.append(f"drop_numeric_noise_fragment:{removed_numeric_noise}")
    if removed_low_signal_residue > 0:
        actions.append(f"drop_low_signal_residue_fragment:{removed_low_signal_residue}")

    rebuilt_plain = re.sub(r"\s{2,}", " ", " ".join(kept_fragments)).strip()
    poll_residue_fix = _scrub_suspicious_poll_residue_text(rebuilt_plain)
    if poll_residue_fix.get("edited"):
        rebuilt_plain = str(poll_residue_fix.get("content") or rebuilt_plain)
        poll_actions = poll_residue_fix.get("actions")
        if isinstance(poll_actions, list):
            for action in poll_actions:
                action_text = str(action).strip()
                if action_text:
                    actions.append(action_text)

    if not actions:
        return {"content": html.escape(plain, quote=False), "edited": False, "actions": []}

    return {
        "content": html.escape(rebuilt_plain, quote=False),
        "edited": True,
        "actions": actions,
    }


def _extract_person_role_facts_from_text(text: Any) -> Dict[str, str]:
    extracted = extract_person_role_facts_from_text_common(text)
    normalized: Dict[str, str] = {}
    for name, role in extracted.items():
        cleaned_name = _clean_full_name_candidate(name)
        normalized_role = re.sub(r"\s+", " ", str(role or "")).strip()
        if cleaned_name and normalized_role:
            normalized[cleaned_name] = normalized_role
    return normalized


def _repair_competitor_policy_phrase_legacy_once(
    content: str,
    *,
    full_name: str,
    person_roles: Dict[str, str],
) -> Dict[str, Any]:
    base = str(content or "")
    speaker_name = _clean_full_name_candidate(full_name)
    if not base.strip() or not speaker_name or not person_roles:
        return {"content": base, "edited": False, "replacements": []}

    competitor_names = sorted(
        {
            cleaned
            for cleaned in (_clean_full_name_candidate(name) for name in person_roles.keys())
            if cleaned and cleaned != speaker_name
        },
        key=len,
        reverse=True,
    )
    if not competitor_names:
        return {"content": base, "edited": False, "replacements": []}

    noun_fragment = "|".join(re.escape(noun) for noun in LOW_SIGNAL_RESIDUE_NOUNS)
    competitor_fragment = "|".join(re.escape(name) for name in competitor_names)
    first_person_pattern = re.compile(
        rf"(저는|제가|저의|저만의|저\s*{re.escape(speaker_name)}|{re.escape(speaker_name)}인\s*저)",
        re.IGNORECASE,
    )
    malformed_phrase_pattern = re.compile(
        rf"(?P<prefix>(?:과|와|및)\s+)(?P<name>{competitor_fragment})\s*"
        rf"(?:(?:현\s*)?(?:부산시장|국회의원|의원|후보|위원장|시장)\s+)?"
        rf"(?P<noun>{noun_fragment})",
        re.IGNORECASE,
    )
    chained_competitor_phrase_pattern = re.compile(
        rf"(?P<prefix>(?:과|와|및)\s+)"
        rf"(?P<chain>(?:(?:{competitor_fragment})"
        rf"(?:\s*(?:현\s*)?(?:부산시장|국회의원|의원|후보|위원장|시장))?"
        rf"(?:\s+|$)){{2,}})"
        rf"(?P<noun>{noun_fragment})",
        re.IGNORECASE,
    )

    first_person_chain_phrase_pattern = re.compile(
        rf"(?P<prefix>(?:????留뚯쓽|?쒓?)\s+(?:吏꾩떖怨?\s+)?)"
        rf"(?P<chain>(?:(?:{competitor_fragment}|[媛-??{2,4})"
        rf"(?:\s*(?:??s*)?(?:遺?곗떆??援?쉶?섏썝|?섏썝|?꾨낫|?꾩썝???쒖옣))?\s+){{1,2}})"
        rf"(?P<noun>{noun_fragment})",
        re.IGNORECASE,
    )

    replacements: list[str] = []

    def _rewrite_text(text: str) -> str:
        plain = re.sub(r"<[^>]*>", " ", str(text or ""))
        if not first_person_pattern.search(plain):
            return text

        def _replace(match: re.Match[str]) -> str:
            replacement = f"{str(match.group('prefix') or '')}{str(match.group('noun') or '').strip()}"
            if replacement.strip() == match.group(0).strip():
                return match.group(0)
            replacements.append(f"{str(match.group('name') or '').strip()}->{str(match.group('noun') or '').strip()}")
            return replacement

        updated_text = chained_competitor_phrase_pattern.sub(
            lambda match: f"{str(match.group('prefix') or '')}{str(match.group('noun') or '').strip()}",
            text,
        )
        if updated_text != text:
            replacements.append("competitor_chain->noun")
            text = updated_text

        updated_text = first_person_chain_phrase_pattern.sub(
            lambda match: f"{str(match.group('prefix') or '').strip()} {str(match.group('noun') or '').strip()}".strip(),
            text,
        )
        if updated_text != text:
            replacements.append("first_person_competitor_chain->noun")
            text = updated_text

        return malformed_phrase_pattern.sub(_replace, text)

    repaired = _rewrite_paragraph_blocks(base, _rewrite_text)
    return {
        "content": repaired,
        "edited": repaired != base,
        "replacements": replacements,
    }


def _repair_competitor_policy_phrase_once(
    content: str,
    *,
    full_name: str,
    person_roles: Dict[str, str],
) -> Dict[str, Any]:
    base = str(content or "")
    speaker_name = _clean_full_name_candidate(full_name)
    if not base.strip() or not speaker_name or not person_roles:
        return {"content": base, "edited": False, "replacements": []}

    competitor_names = sorted(
        {
            cleaned
            for cleaned in (_clean_full_name_candidate(name) for name in person_roles.keys())
            if cleaned and cleaned != speaker_name
        },
        key=len,
        reverse=True,
    )
    if not competitor_names:
        return {"content": base, "edited": False, "replacements": []}

    noun_fragment = "|".join(re.escape(noun) for noun in LOW_SIGNAL_RESIDUE_NOUNS)
    competitor_fragment = "|".join(re.escape(name) for name in competitor_names)
    first_person_pattern = re.compile(
        rf"(?:저|제|저의|제게|저는|제가|{re.escape(speaker_name)})",
        re.IGNORECASE,
    )
    malformed_phrase_pattern = re.compile(
        rf"(?P<prefix>(?:과\s+|와\s+|및\s+|비롯한\s+)(?P<name>{competitor_fragment})\s*"
        rf"(?:(?:전\s*)?(?:부산시장|국회의원|의원|후보|위원장|시장)\s+)?"
        rf"(?P<noun>{noun_fragment}))",
        re.IGNORECASE,
    )
    chained_competitor_phrase_pattern = re.compile(
        rf"(?P<prefix>(?:과\s+|와\s+|및\s+))"
        rf"(?P<chain>(?:(?:{competitor_fragment})"
        rf"(?:\s*(?:전\s*)?(?:부산시장|국회의원|의원|후보|위원장|시장))?"
        rf"(?:\s+|$)){{2,}})"
        rf"(?P<noun>{noun_fragment})",
        re.IGNORECASE,
    )
    first_person_chain_phrase_pattern = re.compile(
        rf"(?P<prefix>(?:저의|제)\s+(?:진심과\s+)?)"
        rf"(?P<chain>(?:(?:{competitor_fragment}|[가-힣]{{2,4}})"
        rf"(?:\s*(?:전\s*)?(?:부산시장|국회의원|의원|후보|위원장|시장))?\s+){{1,2}})"
        rf"(?:(?:[가-힣]{{1,4}}도\s*)?[가-힣]{{1,8}}도?\s*"
        rf"(?:후보군(?:\s*대결(?:에서도|에서)?)?|대결(?:에서도|에서)?)\s+)?"
        rf"(?P<noun>{noun_fragment})",
        re.IGNORECASE,
    )

    replacements: list[str] = []

    def _rewrite_text(text: str) -> str:
        plain = re.sub(r"<[^>]*>", " ", str(text or ""))
        if not first_person_pattern.search(plain):
            return text

        def _replace(match: re.Match[str]) -> str:
            replacement = f"{str(match.group('prefix') or '')}{str(match.group('noun') or '').strip()}"
            if replacement.strip() == match.group(0).strip():
                return match.group(0)
            replacements.append(f"{str(match.group('name') or '').strip()}->{str(match.group('noun') or '').strip()}")
            return replacement

        updated_text = chained_competitor_phrase_pattern.sub(
            lambda match: f"{str(match.group('prefix') or '')}{str(match.group('noun') or '').strip()}",
            text,
        )
        if updated_text != text:
            replacements.append("competitor_chain->noun")
            text = updated_text

        updated_text = first_person_chain_phrase_pattern.sub(
            lambda match: f"{str(match.group('prefix') or '').strip()} {str(match.group('noun') or '').strip()}".strip(),
            text,
        )
        if updated_text != text:
            replacements.append("first_person_competitor_chain->noun")
            text = updated_text

        return malformed_phrase_pattern.sub(_replace, text)

    repaired = _rewrite_paragraph_blocks(base, _rewrite_text)
    return {
        "content": repaired,
        "edited": repaired != base,
        "replacements": replacements,
    }


def _repair_terminal_sentence_spacing_once(text: Any) -> Dict[str, Any]:
    base = str(text or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    updated = base
    actions: list[str] = []
    spacing_patterns: list[tuple[re.Pattern[str], str, str]] = [
        (
            re.compile(r'(?<!\d)\.((?:["\'”’)\]])?)(?=[가-힣A-Za-z])'),
            r".\1 ",
            "sentence_spacing_after_period",
        ),
        (
            re.compile(r'([!?。])((?:["\'”’)\]])?)(?=[가-힣A-Za-z0-9])'),
            r"\1\2 ",
            "sentence_spacing_after_terminal_punctuation",
        ),
    ]
    for pattern, replacement, action_name in spacing_patterns:
        updated, changed = pattern.subn(replacement, updated)
        if changed > 0:
            actions.append(f"{action_name}:{changed}")

    if not actions:
        return {"content": base, "edited": False, "actions": []}

    return {
        "content": updated,
        "edited": updated != base,
        "actions": actions,
    }


def _build_person_role_facts(
    *,
    data: Dict[str, Any],
    pipeline_result: Dict[str, Any],
) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    source_texts = [
        data.get("newsDataText"),
        pipeline_result.get("newsDataText"),
        data.get("sourceInput"),
        pipeline_result.get("sourceInput"),
        data.get("sourceContent"),
        pipeline_result.get("sourceContent"),
    ]
    for text in source_texts:
        extracted = _extract_person_role_facts_from_text(text)
        for name, role in extracted.items():
            if name not in merged:
                merged[name] = role
                continue
            current = str(merged.get(name) or "")
            if roles_equivalent_common(current, role):
                if str(role).startswith("현 ") and not str(current).startswith("현 "):
                    merged[name] = role
                continue
            if str(role).startswith("현 "):
                merged[name] = role
    return merged


OFF_TOPIC_POLL_INTERNAL_MARKERS: tuple[str, ...] = (
    "당내 경쟁",
    "내 경쟁",
    "경선",
    "당내 경선",
    "후보군",
    "적합도",
    "지지층",
)
OFF_TOPIC_POLL_MATCHUP_MARKERS: tuple[str, ...] = (
    "양자대결",
    "가상대결",
    "맞대결",
    "대결",
    "오차 범위",
    "오차범위",
)
OFF_TOPIC_POLL_SIGNAL_MARKERS: tuple[str, ...] = (
    "여론조사",
    "조사",
    "지지율",
    "응답률",
    "표본오차",
    "%",
)
OFF_TOPIC_POLL_PARTY_SUPPORT_MARKERS: tuple[str, ...] = (
    "정당 지지율",
    "지지정당 없음",
    "더불어민주당",
    "국민의힘",
    "조국혁신당",
    "개혁신당",
)


def _collect_primary_topic_names(
    *,
    topic: str,
    title_text: str,
    user_keywords: list[str],
    full_name: str,
) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    def _push(candidate: Any) -> None:
        cleaned = _clean_full_name_candidate(candidate)
        if not cleaned or cleaned in seen:
            return
        seen.add(cleaned)
        names.append(cleaned)

    _push(full_name)
    for keyword in user_keywords or []:
        extracted_name, _ = _extract_keyword_person_role(str(keyword))
        _push(extracted_name)

    name_patterns = (
        re.compile(r"([가-힣]{2,4})(?=보다)"),
        re.compile(r"([가-힣]{2,4})(?=[와과])"),
        re.compile(r"([가-힣]{2,4})(?=의)"),
        re.compile(
            r"([가-힣]{2,4})(?=\s*(?:전\s*)?(?:현\s*)?(?:국회의원|의원|시장|지사|교육감|구청장|군수|대표|위원장|후보|예비후보))"
        ),
    )
    for text in (str(topic or ""), str(title_text or "")):
        for pattern in name_patterns:
            for match in pattern.findall(text):
                _push(match)

    return names


def _remove_off_topic_poll_sentences_once(
    content: str,
    *,
    full_name: str,
    topic: str,
    title_text: str,
    user_keywords: list[str],
    role_facts: Dict[str, str],
    poll_fact_table: Dict[str, Any],
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    primary_names = {
        _normalize_person_name(name)
        for name in _collect_primary_topic_names(
            topic=topic,
            title_text=title_text,
            user_keywords=user_keywords,
            full_name=full_name,
        )
        if _normalize_person_name(name)
    }
    if len(primary_names) < 2:
        return {"content": base, "edited": False, "actions": []}
    is_matchup_topic = any(
        token in str(topic or "") or token in str(title_text or "")
        for token in OFF_TOPIC_POLL_MATCHUP_MARKERS
    )

    known_names = set(primary_names)
    for name in (role_facts or {}).keys():
        normalized = _normalize_person_name(name)
        if normalized:
            known_names.add(normalized)
    for name in (_safe_dict(poll_fact_table).get("knownNames") or []):
        normalized = _normalize_person_name(name)
        if normalized:
            known_names.add(normalized)

    if len(known_names) <= len(primary_names):
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    actions: list[str] = []
    paragraph_matches = list(PARAGRAPH_TAG_PATTERN.finditer(repaired))
    for match in reversed(paragraph_matches):
        inner = str(match.group(1) or "")
        sentence_matches = list(SENTENCE_LIKE_UNIT_PATTERN.finditer(inner))
        if not sentence_matches:
            continue

        updated_inner = inner
        removed = 0
        for sentence_match in reversed(sentence_matches):
            sentence_html = str(sentence_match.group(0) or "")
            sentence_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", sentence_html))
            if not sentence_plain:
                continue

            mentioned_names = [
                name for name in known_names if name and name in _normalize_person_name(sentence_plain)
            ]
            off_topic_names = [name for name in mentioned_names if name not in primary_names]

            has_poll_signal = any(token in sentence_plain for token in OFF_TOPIC_POLL_SIGNAL_MARKERS) or bool(
                re.search(r"\d+(?:\.\d+)?\s*%", sentence_plain)
            )

            has_matchup_marker = any(token in sentence_plain for token in OFF_TOPIC_POLL_MATCHUP_MARKERS)
            has_internal_marker = any(token in sentence_plain for token in OFF_TOPIC_POLL_INTERNAL_MARKERS)
            has_party_support_marker = any(
                token in sentence_plain for token in OFF_TOPIC_POLL_PARTY_SUPPORT_MARKERS
            )
            has_primary_pair = sum(
                1 for name in primary_names if name and name in _normalize_person_name(sentence_plain)
            ) >= 2

            if (
                is_matchup_topic
                and not has_matchup_marker
                and has_party_support_marker
                and not has_primary_pair
            ):
                updated_inner = (
                    updated_inner[: sentence_match.start()] + updated_inner[sentence_match.end() :]
                )
                removed += 1
                continue

            if (
                is_matchup_topic
                and not has_matchup_marker
                and has_internal_marker
                and (
                    has_poll_signal
                    or any(token in sentence_plain for token in ("당내", "수치", "적합도", "지지율"))
                )
            ):
                updated_inner = (
                    updated_inner[: sentence_match.start()] + updated_inner[sentence_match.end() :]
                )
                removed += 1
                continue

            if not off_topic_names:
                continue

            if not has_poll_signal:
                continue

            if has_matchup_marker and not has_internal_marker:
                continue

            updated_inner = (
                updated_inner[: sentence_match.start()] + updated_inner[sentence_match.end() :]
            )
            removed += 1

        if removed <= 0:
            continue

        cleaned_inner = re.sub(r"\s{2,}", " ", str(updated_inner or ""))
        cleaned_inner = re.sub(r"\s+([,.;!?])", r"\1", cleaned_inner).strip()
        if _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", cleaned_inner)):
            repaired = repaired[: match.start(1)] + cleaned_inner + repaired[match.end(1) :]
        else:
            repaired = repaired[: match.start()] + repaired[match.end() :]
        actions.append(f"drop_off_topic_poll_sentence:{removed}")

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


def _extract_role_consistency_issues(
    content: str,
    person_roles: Dict[str, str],
) -> list[str]:
    if not person_roles:
        return []

    plain = _extract_role_check_plain_text(content)
    if not plain:
        return []

    issues: list[str] = []
    seen: set[str] = set()
    for match in ROLE_MENTION_PATTERN.finditer(plain):
        if _is_protected_search_keyword_role_mention(plain, match.start(), match.end()):
            continue
        if is_role_keyword_intent_surface(plain, match.start(), match.end()):
            continue
        name = _clean_full_name_candidate(match.group(1))
        if not name or name not in person_roles:
            continue
        expected_role = str(person_roles.get(name) or "").strip()
        expected = _canonical_role_label(expected_role)
        detected_raw = f"{str(match.group(2) or '').strip()} {str(match.group(3) or '').strip()}".strip()
        detected = _canonical_role_label(detected_raw)
        if not expected or not detected:
            continue
        if roles_equivalent_common(expected, detected):
            continue

        issue_key = f"{name}:{detected}->{expected}"
        if issue_key in seen:
            continue
        seen.add(issue_key)
        issues.append(f"\"{name} {detected_raw}\" 직함이 입력 근거(\"{expected_role}\")와 불일치")
        if len(issues) >= 3:
            break
    return issues


def _repair_role_consistency_once(
    content: str,
    person_roles: Dict[str, str],
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip() or not person_roles:
        return {"content": base, "edited": False, "replacements": []}

    replacements: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        if len(replacements) >= 8:
            return match.group(0)
        if _is_protected_search_keyword_role_mention(str(match.string or ""), match.start(), match.end()):
            return match.group(0)
        if is_role_keyword_intent_surface(str(match.string or ""), match.start(), match.end()):
            return match.group(0)

        name = _clean_full_name_candidate(match.group(1))
        if not name or name not in person_roles:
            return match.group(0)

        expected_role = str(person_roles.get(name) or "").strip()
        expected = _canonical_role_label(expected_role)
        detected_raw = f"{str(match.group(2) or '').strip()} {str(match.group(3) or '').strip()}".strip()
        detected = _canonical_role_label(detected_raw)
        if not expected or not detected:
            return match.group(0)
        if roles_equivalent_common(expected, detected):
            return match.group(0)

        target_role = expected_role or expected
        normalized_target = re.sub(r"\s+", " ", target_role).strip()
        replacements.append(f"{name}:{detected_raw}->{normalized_target}")
        return f"{name} {normalized_target}"

    def _rewrite_text(text: str) -> str:
        return ROLE_MENTION_PATTERN.sub(_replace, text)

    repaired = _rewrite_paragraph_blocks(base, _rewrite_text)
    return {
        "content": repaired,
        "edited": repaired != base,
        "replacements": replacements,
    }


INTENT_BODY_SKIP_TOKENS: tuple[str, ...] = (
    "가상대결",
    "양자대결",
    "대결",
    "여론조사",
    "지지율",
    "오차 범위",
    "오차범위",
)


def _has_final_consonant(text: Any) -> bool:
    candidate = re.sub(r"[^가-힣]", "", str(text or ""))
    if not candidate:
        return True
    last_char = candidate[-1]
    code = ord(last_char) - 0xAC00
    if code < 0 or code > 11171:
        return True
    return bool(code % 28)


def _normalize_matchup_pair_particle(base_text: Any, raw_pair: Any) -> str:
    suffix = "의" if str(raw_pair or "").strip().endswith("의") else ""
    return f"{'과' if _has_final_consonant(base_text) else '와'}{suffix}"


def _extract_inline_context_window(text: str, start: int, end: int) -> str:
    source = str(text or "")
    if not source:
        return ""
    left_boundary = max(
        source.rfind(".", 0, start),
        source.rfind("?", 0, start),
        source.rfind("!", 0, start),
        source.rfind("。", 0, start),
    )
    if left_boundary == -1:
        left_boundary = 0
    else:
        left_boundary += 1

    right_candidates = [source.find(token, end) for token in (".", "?", "!", "。")]
    right_candidates = [index for index in right_candidates if index != -1]
    right_boundary = min(right_candidates) if right_candidates else len(source)
    return str(source[left_boundary:right_boundary] or "")


def _repair_intent_only_role_keyword_mentions_once(
    content: str,
    role_keyword_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = str(content or "")
    entries = role_keyword_policy.get("entries") if isinstance(role_keyword_policy, dict) else {}
    if not base.strip() or not isinstance(entries, dict) or not entries:
        return {"content": base, "edited": False, "replacements": []}

    intent_entries = {
        str(keyword or "").strip(): raw_entry
        for keyword, raw_entry in entries.items()
        if str(keyword or "").strip()
        and isinstance(raw_entry, dict)
        and str(raw_entry.get("mode") or "").strip().lower() == "intent_only"
    }
    if not intent_entries:
        return {"content": base, "edited": False, "replacements": []}

    replacements: list[str] = []

    def _rewrite_inner(inner: str) -> str:
        updated_inner = str(inner or "")
        for keyword, entry in intent_entries.items():
            escaped_keyword = re.escape(keyword)
            match_pattern = re.compile(
                rf"(?P<keyword>{escaped_keyword})"
                rf"(?:\s*(?P<label>예비후보|후보)(?=(?:\s*(?:과|와)(?:의)?|[\s.,!?]|$)))?"
                rf"(?P<pair>\s*(?:과|와)(?:의)?)?",
            )
            name = _clean_full_name_candidate(entry.get("name"))
            source_role = str(entry.get("sourceRole") or "").strip()
            source_surface = ""
            if name and source_role:
                source_surface = _h2_repair_build_subheading_role_surface(name, role_facts={name: source_role}) or f"{name} {source_role}"

            def _replace(match: re.Match[str]) -> str:
                if len(replacements) >= 6:
                    return match.group(0)
                raw_source = str(match.string or "")
                keyword_start = match.start("keyword")
                keyword_end = match.end("keyword")
                if _is_protected_search_keyword_role_mention(raw_source, keyword_start, keyword_end):
                    return match.group(0)
                if is_role_keyword_intent_surface(raw_source, keyword_start, keyword_end):
                    return match.group(0)

                context_window = _normalize_inline_whitespace(
                    re.sub(r"<[^>]*>", " ", _extract_inline_context_window(raw_source, match.start(), match.end()))
                )
                if re.search(
                    r"(?:과|와)\s+같은\s+[^.!?]{0,20}(?:인물|역할|논의)|"
                    r"(?:의\s+역할|역할\s+또한\s+중요하게\s+논의|중심에서\s+[^.!?]{0,20}논의)",
                    context_window,
                    re.IGNORECASE,
                ):
                    return match.group(0)
                has_fact_context = any(token in context_window for token in INTENT_BODY_SKIP_TOKENS) or "%" in context_window
                if has_fact_context and source_surface:
                    pair = str(match.group("pair") or "").strip()
                    replacement = source_surface
                    if pair:
                        replacement = f"{replacement}{_normalize_matchup_pair_particle(source_surface, pair)}"
                    if replacement == match.group(0):
                        return match.group(0)
                    replacements.append(f"{keyword}->{replacement}")
                    return replacement

                if str(match.group("pair") or "").strip():
                    return match.group(0)

                replacement = build_role_keyword_intent_text(
                    keyword,
                    context="inline",
                    variant_index=len(replacements),
                )
                if not replacement or replacement == match.group(0):
                    return match.group(0)
                replacements.append(f"{keyword}->{replacement}")
                return replacement

            updated_inner = match_pattern.sub(_replace, updated_inner)
        return updated_inner

    repaired = _rewrite_paragraph_blocks(base, _rewrite_inner)
    return {
        "content": repaired,
        "edited": repaired != base,
        "replacements": replacements,
    }


def _normalize_lawmaker_honorifics_once(
    content: str,
    person_roles: Dict[str, str],
    full_name: str,
) -> Dict[str, Any]:
    """본문에서 국회의원 인물의 직함 표기를 '의원'으로 통일한다."""
    base = str(content or "")
    if not base.strip() or not person_roles:
        return {"content": base, "edited": False, "replacements": []}

    speaker_name = _clean_full_name_candidate(full_name)
    repaired = base
    replacements: list[str] = []

    def _normalize_text(text: str) -> str:
        updated = str(text or "")
        for name, role in person_roles.items():
            cleaned_name = _clean_full_name_candidate(name)
            if not cleaned_name:
                continue
            if speaker_name and cleaned_name == speaker_name:
                continue
            if _canonical_role_label(role) != "국회의원":
                continue

            role_patterns = (
                rf"{re.escape(cleaned_name)}\s*(?:현\s*)?부산시장(?:\s*후보)?",
                rf"{re.escape(cleaned_name)}\s*국회의원(?:\s*후보)?",
                rf"{re.escape(cleaned_name)}\s*의원(?:\s*후보)?",
                rf"{re.escape(cleaned_name)}\s*후보",
            )
            for pattern in role_patterns:
                changed = False

                def _replace(match: re.Match[str]) -> str:
                    nonlocal changed
                    if _is_protected_search_keyword_role_mention(str(match.string or ""), match.start(), match.end()):
                        return match.group(0)
                    changed = True
                    return f"{cleaned_name} 의원"

                updated = re.sub(pattern, _replace, updated)
                if changed:
                    replacements.append(pattern)
        return updated

    repaired = _rewrite_paragraph_blocks(base, _normalize_text)
    generic_candidate_cleanup = re.sub(r"([가-힣]{1,8}\s*의원)\s*후보(?!군|론|설)", r"\1", repaired)
    if generic_candidate_cleanup != repaired:
        repaired = generic_candidate_cleanup
        replacements.append("generic_lawmaker_candidate_chain")

    if repaired != base:
        repaired = repaired.replace("의원와", "의원과")
        repaired = repaired.replace("의원는", "의원은")
        repaired = repaired.replace("의원를", "의원을")
        repaired = repaired.replace("의원가", "의원이")

    return {
        "content": repaired,
        "edited": repaired != base,
        "replacements": replacements,
    }


def _extract_poll_explanation_signature(text: str) -> str:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain:
        return ""
    if "의뢰" not in plain or ("실시" not in plain and "조사" not in plain):
        return ""

    before_request = plain.split("에 의뢰", 1)[0]
    raw_tokens = [str(token).strip() for token in re.findall(r"\w+", before_request) if str(token).strip()]
    if len(raw_tokens) < 2:
        return ""
    tokens = [re.sub(r"(?:이|가)$", "", token) for token in raw_tokens if token not in {"최근", "이번", "여론조사", "조사"}]
    if len(tokens) < 2:
        return ""
    requester = str(tokens[-2] or "").strip()
    agency = str(tokens[-1] or "").strip()
    if not requester or not agency:
        return ""
    sample_match = re.search(r"(\d{3,4})명", plain)
    sample_size = str(sample_match.group(1) or "").strip() if sample_match else ""
    return "|".join(item for item in (requester, agency, sample_size) if item)


def _dedupe_poll_explanation_sentences_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    seen_signatures: set[str] = set()
    actions: list[str] = []
    edited = False

    def _rewrite_inner(inner: str) -> str:
        nonlocal edited
        sentence_matches = list(re.finditer(r"[^.!?。]+[.!?。]?", str(inner or "")))
        if not sentence_matches:
            return str(inner or "")

        kept_sentences: list[str] = []
        removed_count = 0
        for match in sentence_matches:
            sentence_html = str(match.group(0) or "")
            signature = _extract_poll_explanation_signature(sentence_html)
            if signature and signature in seen_signatures:
                removed_count += 1
                edited = True
                continue
            if signature:
                seen_signatures.add(signature)
            kept_sentences.append(sentence_html.strip())

        if removed_count <= 0:
            return str(inner or "")

        actions.append(f"poll_explanation_dedupe:{removed_count}")
        rebuilt = " ".join(item for item in kept_sentences if item)
        rebuilt = re.sub(r"\s{2,}", " ", rebuilt).strip()
        rebuilt = re.sub(r"\s+([,.;!?])", r"\1", rebuilt)
        return rebuilt

    repaired = _rewrite_paragraph_blocks(base, _rewrite_inner)
    repaired = re.sub(r"<p\b[^>]*>\s*</p\s*>", "", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired)
    return {
        "content": repaired,
        "edited": edited and repaired != base,
        "actions": actions,
    }


_POLL_REACTION_INTERPRETATION_RE_LIST: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:이는|이\s+수치는|이\s+숫자는|이\s+결과는|이번\s+여론조사\s+결과는)[^.!?]{0,72}"
        r"시민(?:들)?(?:\s+여러분)?(?:께서|의)?[^.!?]{0,48}"
        r"(?:변화\s+요구|주목|기대|지지|열망|갈망)[^.!?]{0,32}"
        r"(?:보여줍니다|보여주는\s+것|증거|신호|뜻|의미)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:이는|이\s+수치는|이\s+결과는|이번\s+여론조사\s+결과는)[^.!?]{0,72}"
        r"시민(?:들)?(?:\s+여러분)?(?:께서)?[^.!?]{0,40}"
        r"(?:저의|제)\s*(?:비전|메시지|진정성|역량|경쟁력)[^.!?]{0,32}"
        r"(?:주목|기대|지지|열망|신뢰)[^.!?]{0,32}(?:신호|뜻|의미)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:저의|제)\s*(?:경쟁력|비전|메시지)[^.!?]{0,64}"
        r"시민(?:들)?(?:\s+여러분)?[^.!?]{0,48}"
        r"(?:열망|기대|지지|주목)[^.!?]{0,24}(?:보여주는\s+것|보여주는\s+것입니다|의미하는\s+것)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:저의\s+이름(?:과\s+메시지)?(?:이|가)|제가|저는|이재성(?:의\s+이름(?:과\s+메시지)?(?:이|가)?))"
        r"[^.!?]{0,48}(?:조금씩\s+)?확실히\s+알려지고\s+(?:있(?:습니다|으며)|있다고)",
        re.IGNORECASE,
    ),
)


def _looks_like_poll_reaction_interpretation_sentence(text: Any) -> bool:
    normalized = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not normalized:
        return False

    compact = re.sub(r"\s+", "", normalized)
    if "조금씩확실히알려지고" in compact or "확실히알려지고있습니다" in compact:
        return True
    if (
        re.match(r"^이\s*(?:숫자|수치|결과)는", normalized)
        and "%" not in normalized
        and re.search(r"(?:보여줍니다|증거|신호|뜻|의미)", normalized)
    ):
        return True

    return any(pattern.search(normalized) for pattern in _POLL_REACTION_INTERPRETATION_RE_LIST)


def _drop_poll_reaction_interpretation_sentences_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    replacements: list[tuple[int, int, str]] = []
    dropped_count = 0

    for para_match in PARAGRAPH_TAG_PATTERN.finditer(base):
        inner = str(para_match.group(1) or "")
        if "<" in inner:
            continue
        plain_inner = _normalize_inline_whitespace(inner)
        if not plain_inner:
            continue

        sentences = _split_sentence_like_units(plain_inner)
        kept_sentences: list[str] = []
        for sentence in sentences:
            if _looks_like_poll_reaction_interpretation_sentence(sentence):
                dropped_count += 1
                continue
            kept_sentences.append(sentence)

        rebuilt_inner = " ".join(kept_sentences).strip()
        if rebuilt_inner == plain_inner:
            continue
        if not rebuilt_inner:
            replacements.append((para_match.start(), para_match.end(), ""))
        else:
            replacements.append((para_match.start(1), para_match.end(1), rebuilt_inner))

    if not replacements:
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    for start, end, replacement in sorted(replacements, key=lambda item: -item[0]):
        repaired = repaired[:start] + replacement + repaired[end:]
    repaired = re.sub(r"<p\b[^>]*>\s*</p\s*>", "", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired)
    actions = [f"poll_reaction_interpretation_drop:{dropped_count}"] if dropped_count > 0 else []
    return {"content": repaired, "edited": repaired != base, "actions": actions}


def _extract_career_fact_signature(text: Any) -> str:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain:
        return ""
    return extract_career_fact_signature_common(plain)


def _dedupe_repeated_career_fact_sentences_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    seen_signatures: set[str] = set()
    actions: list[str] = []
    edited = False

    def _rewrite_inner(inner: str) -> str:
        nonlocal edited
        plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(inner or "")))
        if not plain_inner:
            return str(inner or "")

        sentences = _split_sentence_like_units(plain_inner)
        kept_sentences: list[str] = []
        removed_count = 0
        for sentence in sentences:
            signature = _extract_career_fact_signature(sentence)
            if signature and signature in seen_signatures:
                removed_count += 1
                edited = True
                continue
            if signature:
                seen_signatures.add(signature)
            kept_sentences.append(sentence)

        if removed_count <= 0:
            return plain_inner

        actions.append(f"career_fact_dedupe:{removed_count}")
        rebuilt = " ".join(item for item in kept_sentences if item).strip()
        rebuilt = re.sub(r"\s{2,}", " ", rebuilt)
        rebuilt = re.sub(r"\s+([,.;!?])", r"\1", rebuilt)
        return rebuilt

    repaired = _rewrite_paragraph_blocks(base, _rewrite_inner)
    repaired = re.sub(r"<p\b[^>]*>\s*</p\s*>", "", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired)
    return {"content": repaired, "edited": edited and repaired != base, "actions": actions}


_REPEATED_POLICY_BUNDLE_TOKENS: tuple[str, ...] = (
    "북항 재개발",
    "제조업 혁신",
    "스타트업",
    "첨단금융",
    "관광 인프라",
)


def _extract_policy_bundle_signature(text: Any) -> str:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain:
        return ""

    hits = [token for token in _REPEATED_POLICY_BUNDLE_TOKENS if token in plain]
    if len(hits) >= 3:
        return "policy_bundle:busan_growth"
    return ""


def _extract_policy_evidence_signature(text: Any) -> str:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain:
        return ""
    return extract_policy_evidence_signature_common(plain)


def _dedupe_repeated_policy_evidence_sentences_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    seen_signatures: set[str] = set()
    actions: list[str] = []
    edited = False

    def _rewrite_inner(inner: str) -> str:
        nonlocal edited
        plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(inner or "")))
        if not plain_inner:
            return str(inner or "")

        sentences = _split_sentence_like_units(plain_inner)
        kept_sentences: list[str] = []
        removed_count = 0
        for sentence in sentences:
            signature = _extract_policy_evidence_signature(sentence)
            if signature and signature in seen_signatures:
                removed_count += 1
                edited = True
                continue
            if signature:
                seen_signatures.add(signature)
            kept_sentences.append(sentence)

        if removed_count <= 0:
            return plain_inner

        actions.append(f"policy_evidence_dedupe:{removed_count}")
        rebuilt = " ".join(item for item in kept_sentences if item).strip()
        rebuilt = re.sub(r"\s{2,}", " ", rebuilt)
        rebuilt = re.sub(r"\s+([,.;!?])", r"\1", rebuilt)
        return rebuilt

    repaired = _rewrite_paragraph_blocks(base, _rewrite_inner)
    repaired = re.sub(r"<p\b[^>]*>\s*</p\s*>", "", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired)
    return {"content": repaired, "edited": edited and repaired != base, "actions": actions}


def _build_cross_section_contract_sections(content: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for raw_section in _split_into_sections(str(content or "")):
        section_html = str(raw_section.get("html") or "")
        paragraphs: list[str] = []
        for match in PARAGRAPH_TAG_PATTERN.finditer(section_html):
            paragraph_text = _normalize_inline_whitespace(
                re.sub(r"<[^>]*>", " ", str(match.group(1) or ""))
            )
            if paragraph_text:
                paragraphs.append(paragraph_text)
        sections.append(
            {
                "heading": _normalize_inline_whitespace(str(raw_section.get("h2_text") or "")),
                "paragraphs": paragraphs,
            }
        )
    return sections


def _build_section_semantic_sections(content: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for raw_index, raw_section in enumerate(_split_into_sections(str(content or "")), start=1):
        if not bool(raw_section.get("has_h2")):
            continue
        section_html = str(raw_section.get("html") or "")
        paragraphs: list[str] = []
        for match in PARAGRAPH_TAG_PATTERN.finditer(section_html):
            paragraph_text = _normalize_inline_whitespace(
                re.sub(r"<[^>]*>", " ", str(match.group(1) or ""))
            )
            if paragraph_text:
                paragraphs.append(paragraph_text)
        heading_text = _normalize_inline_whitespace(str(raw_section.get("h2_text") or ""))
        if heading_text and paragraphs:
            sections.append(
                {
                    "heading": heading_text,
                    "paragraphs": paragraphs,
                    "rawSectionIndex": raw_index,
                }
            )
    return sections


def _remove_sentence_from_section_html(section_html: str, sentence: str) -> tuple[str, int]:
    target_sentence = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(sentence or "")))
    if not target_sentence:
        return str(section_html or ""), 0

    removed = 0

    def _rewrite_inner(inner: str) -> str:
        nonlocal removed
        plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(inner or "")))
        if not plain_inner:
            return str(inner or "")

        sentences = split_section_contract_sentences(plain_inner)
        if not sentences:
            return plain_inner

        kept_sentences: list[str] = []
        for current_sentence in sentences:
            normalized_sentence = _normalize_inline_whitespace(current_sentence)
            if removed == 0 and normalized_sentence == target_sentence:
                removed += 1
                continue
            kept_sentences.append(current_sentence)

        rebuilt = " ".join(item for item in kept_sentences if str(item).strip()).strip()
        rebuilt = re.sub(r"\s{2,}", " ", rebuilt)
        rebuilt = re.sub(r"\s+([,.;!?])", r"\1", rebuilt)
        return rebuilt

    repaired = _rewrite_paragraph_blocks(str(section_html or ""), _rewrite_inner)
    repaired = re.sub(r"<p\b[^>]*>\s*</p\s*>", "", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired)
    return repaired, removed


def _section_html_contains_sentence(section_html: str, sentence: str) -> bool:
    target_sentence = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(sentence or "")))
    if not target_sentence:
        return False

    for match in PARAGRAPH_TAG_PATTERN.finditer(str(section_html or "")):
        plain_inner = _normalize_inline_whitespace(
            re.sub(r"<[^>]*>", " ", str(match.group(1) or ""))
        )
        if not plain_inner:
            continue
        for current_sentence in split_section_contract_sentences(plain_inner):
            if _normalize_inline_whitespace(current_sentence) == target_sentence:
                return True
    return False


def _append_sentences_to_section_html(
    section_html: str,
    sentences: list[str],
) -> tuple[str, int]:
    base = str(section_html or "")
    if not base.strip():
        return base, 0

    existing_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", base))
    additions: list[str] = []
    for sentence in sentences:
        normalized_sentence = _normalize_inline_whitespace(sentence)
        if not normalized_sentence:
            continue
        if normalized_sentence in additions:
            continue
        if normalized_sentence in existing_plain:
            continue
        additions.append(normalized_sentence)

    if not additions:
        return base, 0

    insertion = f"\n<p>{' '.join(additions)}</p>"
    repaired = f"{base.rstrip()}{insertion}"
    return repaired, len(additions)


def _apply_section_semantic_lane_repair_once(
    content: str,
    *,
    category: str = "",
) -> Dict[str, Any]:
    base = str(content or "")
    normalized_category = str(category or "").strip().lower()
    if not base.strip() or not should_apply_section_lane_contracts(normalized_category):
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    actions: list[str] = []
    edited = False

    for _ in range(6):
        semantic_sections = _build_section_semantic_sections(repaired)
        if len(semantic_sections) < 2:
            break

        violation = find_section_semantic_mismatch(
            sections=semantic_sections,
            category=normalized_category,
        )
        if not isinstance(violation, dict):
            break

        section_index = _to_int(violation.get("sectionIndex"), 0)
        target_section_index = _to_int(violation.get("targetSectionIndex"), 0)
        if (
            section_index <= 0
            or target_section_index <= 0
            or section_index > len(semantic_sections)
            or target_section_index > len(semantic_sections)
            or section_index == target_section_index
        ):
            break

        sentence = str(violation.get("sentence") or "").strip()
        if not sentence:
            break

        source_raw_index = _to_int(semantic_sections[section_index - 1].get("rawSectionIndex"), 0)
        target_raw_index = _to_int(semantic_sections[target_section_index - 1].get("rawSectionIndex"), 0)
        raw_sections = _split_into_sections(repaired)
        if (
            source_raw_index <= 0
            or target_raw_index <= 0
            or source_raw_index > len(raw_sections)
            or target_raw_index > len(raw_sections)
            or source_raw_index == target_raw_index
        ):
            break

        source_html = str(raw_sections[source_raw_index - 1].get("html") or "")
        target_html = str(raw_sections[target_raw_index - 1].get("html") or "")
        target_has_sentence = _section_html_contains_sentence(target_html, sentence)

        updated_source_html, removed = _remove_sentence_from_section_html(source_html, sentence)
        if removed <= 0:
            break
        if not PARAGRAPH_TAG_PATTERN.search(updated_source_html):
            break

        updated_target_html = target_html
        if not target_has_sentence:
            updated_target_html, appended = _append_sentences_to_section_html(target_html, [sentence])
            if appended <= 0:
                break

        raw_sections[source_raw_index - 1] = {
            **raw_sections[source_raw_index - 1],
            "html": updated_source_html,
        }
        if not target_has_sentence:
            raw_sections[target_raw_index - 1] = {
                **raw_sections[target_raw_index - 1],
                "html": updated_target_html,
            }

        candidate = _join_sections(raw_sections).strip()
        if not candidate or candidate == repaired:
            break

        repaired = candidate
        edited = True
        actions.append(
            f"section_lane_move:section_{section_index}:to_section_{target_section_index}"
        )

    return {"content": repaired, "edited": edited and repaired != base, "actions": actions}


def _apply_cross_section_contract_once(
    content: str,
    *,
    category: str = "",
    full_name: str = "",
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    normalized_category = str(category or "").strip().lower()
    if not should_apply_cross_section_contracts(normalized_category):
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    actions: list[str] = []
    edited = False

    for _ in range(6):
        raw_sections = _split_into_sections(repaired)
        if len(raw_sections) < 2:
            break

        violation = validate_cross_section_contracts(
            sections=_build_cross_section_contract_sections(repaired),
            speaker=str(full_name or "").strip(),
            opponent="",
        )
        if not isinstance(violation, dict):
            break

        code = str(violation.get("code") or "").strip()
        if code not in {"duplicate_career_fact", "duplicate_policy_evidence_fact"}:
            break

        section_index = _to_int(violation.get("sectionIndex"), 0)
        if section_index <= 0 or section_index > len(raw_sections):
            break

        target_sentence = str(violation.get("sentence") or "").strip()
        section_offset = section_index - 1
        updated_html, removed = _remove_sentence_from_section_html(
            str(raw_sections[section_offset].get("html") or ""),
            target_sentence,
        )
        if removed <= 0:
            break

        raw_sections[section_offset] = {
            **raw_sections[section_offset],
            "html": updated_html,
        }
        candidate = _join_sections(raw_sections).strip()
        if not candidate or candidate == repaired:
            break

        repaired = candidate
        edited = True
        actions.append(f"cross_section_contract:{code}:section_{section_index}")

    return {"content": repaired, "edited": edited and repaired != base, "actions": actions}


def _dedupe_repeated_policy_bundle_sentences_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    seen_signatures: set[str] = set()
    actions: list[str] = []
    edited = False

    def _rewrite_inner(inner: str) -> str:
        nonlocal edited
        plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(inner or "")))
        if not plain_inner:
            return str(inner or "")

        sentences = _split_sentence_like_units(plain_inner)
        kept_sentences: list[str] = []
        removed_count = 0
        for sentence in sentences:
            signature = _extract_policy_bundle_signature(sentence)
            if signature and signature in seen_signatures:
                removed_count += 1
                edited = True
                continue
            if signature:
                seen_signatures.add(signature)
            kept_sentences.append(sentence)

        if removed_count <= 0:
            return plain_inner

        actions.append(f"policy_bundle_dedupe:{removed_count}")
        rebuilt = " ".join(item for item in kept_sentences if item).strip()
        rebuilt = re.sub(r"\s{2,}", " ", rebuilt)
        rebuilt = re.sub(r"\s+([,.;!?])", r"\1", rebuilt)
        return rebuilt

    repaired = _rewrite_paragraph_blocks(base, _rewrite_inner)
    repaired = re.sub(r"<p\b[^>]*>\s*</p\s*>", "", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired)
    return {"content": repaired, "edited": edited and repaired != base, "actions": actions}


_IDENTITY_SIGNATURE_VARIANT_RE = re.compile(
    r"뼛속까지\s+부산(?:\s+사람|사람)(?:으로서|으로|인|이자)?",
    re.IGNORECASE,
)
_SELF_REFERENCE_PLACEHOLDER_RE = re.compile(
    r"(?<![가-힣])이\s*(?P<label>예비후보|후보|의원|위원장|대표)"
    r"(?P<particle>께서는|께서|에게|으로서|로서|으로|로|은|는|이|가|을|를|의|와|과|도)?"
    r"(?=(?:\s|[,.!?]|$))",
    re.IGNORECASE,
)
_SELF_GENERIC_OPPONENT_PLACEHOLDER_RE = re.compile(
    r"(?<![가-힣])상대"
    r"(?!\s*(?:후보|주자|진영|당|와(?:의)?|과(?:의)?|비교|공세|공격|비판))"
    r"(?P<particle>입니다|이라|라는|께서는|께서|에게|으로서|로서|으로|로|은|는|이|가|을|를|의|와|과|도)?"
    r"(?=(?:\s|[,.!?]|$))",
    re.IGNORECASE,
)
_SELF_GENERIC_OPPONENT_EXCLUSION_RE = re.compile(
    r"(?:상대\s*(?:후보|주자|진영|당)|상대(?:와|과)(?:의)?|상대\s*(?:비교|공세|공격|비판)|"
    r"양자대결|가상대결|대결|경쟁|접전|승부|오차\s*범위)",
    re.IGNORECASE,
)
_SELF_GENERIC_OPPONENT_CUE_RE = re.compile(
    r"(?:뛰어온|헌신해\s+온|지켜온|활동해\s+온|함께해\s+온|매달려\s+온|소통해\s+온)\s+상대(?:입니다|은|는|이|가|으로서|로서)?|"
    r"(?:광역시의원|시의원|도의원|국회의원|의원|위원장|대표|후보|예비후보)\s+상대(?:입니다|은|는|이|가|으로서|로서)?|"
    r"것은\s+상대의\s+[^.!?]{0,24}(?:과제|역할|책무)|"
    r"상대(?:입니다|이라|라는|으로서|로서)",
    re.IGNORECASE,
)
_SELF_REFERENCE_PLEDGE_SIGNAL_RE = re.compile(
    r"(?:저는|제가|저의|제|하겠습니다|이뤄내겠습니다|보여드리겠습니다|말씀드리겠습니다|"
    r"약속드립니다|세우겠습니다|바꾸겠습니다|풀겠습니다|만들겠습니다)",
    re.IGNORECASE,
)


def _has_generic_self_opponent_placeholder(text: Any) -> bool:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain or "상대" not in plain:
        return False

    for sentence in re.split(r"(?<=[.!?。])\s+|\n+", plain):
        normalized_sentence = _normalize_inline_whitespace(sentence)
        if not normalized_sentence or "상대" not in normalized_sentence:
            continue
        if _SELF_GENERIC_OPPONENT_EXCLUSION_RE.search(normalized_sentence):
            continue
        if not _SELF_GENERIC_OPPONENT_PLACEHOLDER_RE.search(normalized_sentence):
            continue
        if _SELF_GENERIC_OPPONENT_CUE_RE.search(normalized_sentence):
            return True
    return False


def _build_first_person_surface_for_particle(particle: str) -> str:
    normalized = str(particle or "").strip()
    mapping = {
        "": "저",
        "께서는": "저는",
        "께서": "제가",
        "에게": "저에게",
        "으로서": "저로서",
        "로서": "저로서",
        "으로": "저로",
        "로": "저로",
        "은": "저는",
        "는": "저는",
        "이": "제가",
        "가": "제가",
        "을": "저를",
        "를": "저를",
        "의": "저의",
        "와": "저와",
        "과": "저와",
        "도": "저도",
    }
    return mapping.get(normalized, f"저{normalized}")


def _build_named_self_reference_surface(name: str, label: str, particle: str) -> str:
    base = f"{str(name or '').strip()} {str(label or '').strip()}".strip()
    normalized_particle = str(particle or "").strip()
    return f"{base}{normalized_particle}" if normalized_particle else base


def _repair_self_reference_placeholders_once(
    content: str,
    *,
    full_name: str = "",
) -> Dict[str, Any]:
    base = str(content or "")
    speaker_name = _clean_full_name_candidate(full_name)
    if not base.strip() or not speaker_name:
        return {"content": base, "edited": False, "actions": []}

    replacements: list[tuple[int, int, str]] = []
    replaced_count = 0
    prefixed_pattern = re.compile(
        r"(?<![가-힣])(?:저는|제가|저의|저)\s*[, ]*\s*이\s*(?P<label>예비후보|후보|의원|위원장|대표)"
        r"(?P<particle>께서는|께서|에게|으로서|로서|으로|로|은|는|이|가|을|를|의|와|과|도)?"
        r"(?=(?:\s|[,.!?]|$))",
        re.IGNORECASE,
    )
    first_person_context_pattern = re.compile(
        r"(?<![가-힣])(?:저는|제가|저의|저)\b",
        re.IGNORECASE,
    )
    placeholder_token_pattern = re.compile(
        r"이\s*(?:예비후보|후보|의원|위원장|대표)",
        re.IGNORECASE,
    )

    for match in reversed(list(CONTENT_BLOCK_WITH_TAG_PATTERN.finditer(base))):
        tag = str(match.group("tag") or "").strip().lower()
        inner = str(match.group("inner") or "")
        plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", inner))
        if not plain_inner:
            continue
        if not (
            placeholder_token_pattern.search(plain_inner)
            or prefixed_pattern.search(plain_inner)
            or _has_generic_self_opponent_placeholder(plain_inner)
        ):
            continue

        updated_inner = inner
        changed = False

        updated_inner, prefixed_count = prefixed_pattern.subn(
            lambda m: _build_first_person_surface_for_particle(m.group("particle") or ""),
            updated_inner,
        )
        if prefixed_count > 0:
            replaced_count += prefixed_count
            changed = True

        updated_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", updated_inner))
        has_placeholder = bool(_SELF_REFERENCE_PLACEHOLDER_RE.search(updated_plain))
        has_pledge_signal = bool(_SELF_REFERENCE_PLEDGE_SIGNAL_RE.search(updated_plain))
        has_first_person_context = bool(first_person_context_pattern.search(updated_plain))
        if has_placeholder:
            if tag == "h2" or not (has_pledge_signal or has_first_person_context):
                repl_fn = lambda m: _build_named_self_reference_surface(
                    speaker_name,
                    m.group("label") or "",
                    m.group("particle") or "",
                )
            else:
                repl_fn = lambda m: _build_first_person_surface_for_particle(m.group("particle") or "")
            updated_inner, placeholder_count = _SELF_REFERENCE_PLACEHOLDER_RE.subn(repl_fn, updated_inner)
            if placeholder_count > 0:
                replaced_count += placeholder_count
                changed = True

        if _has_generic_self_opponent_placeholder(updated_plain):
            updated_inner, generic_placeholder_count = _SELF_GENERIC_OPPONENT_PLACEHOLDER_RE.subn(
                lambda m: _build_named_self_reference_surface(
                    speaker_name,
                    "",
                    m.group("particle") or "",
                ),
                updated_inner,
            )
            if generic_placeholder_count > 0:
                replaced_count += generic_placeholder_count
                changed = True

        if changed and updated_inner != inner:
            replacements.append((match.start("inner"), match.end("inner"), updated_inner))

    if not replacements:
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    for start, end, replacement in sorted(replacements, key=lambda item: -item[0]):
        repaired = repaired[:start] + replacement + repaired[end:]

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": [f"repair_self_reference_placeholder:{replaced_count}"] if replaced_count > 0 else [],
    }


def _repair_identity_signature_exact_form_once(
    content: str,
    *,
    full_name: str = "",
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    speaker_name = str(full_name or "").strip()
    exact_signature = f"뼛속까지 부산사람, {speaker_name}입니다." if speaker_name else "뼛속까지 부산사람입니다."
    seen_signature = False
    actions: list[str] = []
    edited = False

    def _rewrite_inner(inner: str) -> str:
        nonlocal seen_signature, edited
        plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(inner or "")))
        if not plain_inner:
            return str(inner or "")

        sentences = _split_sentence_like_units(plain_inner)
        kept_sentences: list[str] = []
        for sentence in sentences:
            normalized = _normalize_inline_whitespace(sentence)
            if not normalized:
                continue
            if exact_signature in normalized or _IDENTITY_SIGNATURE_VARIANT_RE.search(normalized):
                if seen_signature:
                    edited = True
                    actions.append("identity_signature_dedupe")
                    continue
                seen_signature = True
                if normalized != exact_signature:
                    edited = True
                    actions.append("identity_signature_exact_form")
                kept_sentences.append(exact_signature)
                continue
            kept_sentences.append(normalized)

        rebuilt = " ".join(kept_sentences).strip()
        rebuilt = re.sub(r"\s{2,}", " ", rebuilt)
        rebuilt = re.sub(r"\s+([,.;!?])", r"\1", rebuilt)
        return rebuilt

    repaired = _rewrite_paragraph_blocks(base, _rewrite_inner)
    repaired = re.sub(r"<p\b[^>]*>\s*</p\s*>", "", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired)
    return {"content": repaired, "edited": edited and repaired != base, "actions": actions}


def _ensure_identity_signature_present_once(
    content: str,
    *,
    full_name: str = "",
    style_fingerprint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = str(content or "")
    speaker_name = str(full_name or "").strip()
    if not base.strip() or not speaker_name:
        return {"content": base, "edited": False, "actions": []}

    phrases = _safe_dict(_safe_dict(style_fingerprint).get("characteristicPhrases"))
    _, identity_signatures = _collect_style_phrase_examples(phrases)
    requires_identity_signature = any(
        _IDENTITY_SIGNATURE_VARIANT_RE.search(str(item or "")) or speaker_name in str(item or "")
        for item in identity_signatures
    )
    if not requires_identity_signature:
        return {"content": base, "edited": False, "actions": []}

    plain_text = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", base))
    exact_signature = f"뼛속까지 부산사람, {speaker_name}입니다."
    if exact_signature in plain_text or _IDENTITY_SIGNATURE_VARIANT_RE.search(plain_text):
        return {"content": base, "edited": False, "actions": []}

    paragraph_matches = list(PARAGRAPH_TAG_PATTERN.finditer(base))
    if not paragraph_matches:
        return {"content": base, "edited": False, "actions": []}

    target_match = paragraph_matches[0]
    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    if h2_matches:
        last_h2_end = h2_matches[-1].end()
        target_match = next(
            (match for match in paragraph_matches if match.start() >= last_h2_end),
            paragraph_matches[-1],
        )

    target_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(target_match.group(1) or "")))
    inserted_inner = f"{exact_signature} {target_inner}".strip()
    repaired = base[: target_match.start(1)] + inserted_inner + base[target_match.end(1) :]
    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": ["identity_signature_inserted"] if repaired != base else [],
    }


_BROKEN_POLL_ROLE_FRAGMENT = r"(?:전\s*)?(?:국회의원|의원|시장|지사|도지사|대표|위원장|후보|예비후보)"
_SAFE_SENTENCE_HTML_PATTERN = re.compile(r".+?(?:(?<!\d)[.!?。](?!\d)|$)", re.DOTALL)
_INCOMPLETE_NEWS_FRAGMENT_RE = re.compile(
    r"(?:(?:후보\s+공모|공모|경선|선거)[^.!?]{0,36})?"
    r"(?:참여|등록|신청|출마)한\s+(?:이번|이|해당)\s+"
    r"(?:결정|발표|선정|조치|결과)(?:은|는|으로)?",
    re.IGNORECASE,
)


def _has_malformed_double_name_matchup_phrase(text: Any) -> bool:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain:
        return False

    role_like_suffixes = ("시장", "지사", "도지사", "교육감", "구청장", "군수", "국회의원", "의원", "대표", "위원장", "장관", "후보", "예비후보")

    pattern = re.compile(
        r"(?P<left>[가-힣]{2,4})\s+(?:현|전)\s+(?P<right>[가-힣]{2,4})의\s+"
        r"(?:양자대결|가상대결|대결|오차 범위)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(plain):
        left = str(match.group("left") or "").strip()
        right = str(match.group("right") or "").strip()
        if right.endswith(role_like_suffixes):
            continue
        if _looks_like_person_name_token(left) and _looks_like_person_name_token(right):
            return True
    return False


def _looks_like_broken_poll_fragment_sentence(
    sentence: Any,
    *,
    known_names: Optional[list[str]] = None,
) -> bool:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(sentence or "")))
    if not plain:
        return False

    if _INCOMPLETE_NEWS_FRAGMENT_RE.search(plain):
        return True
    if re.search(r"(?:제가|저의)\s+비전에\s+대한", plain, re.IGNORECASE):
        return True
    if re.search(r"^\d+(?:\.\d+)?%\s*보다", plain, re.IGNORECASE):
        return True
    if re.search(
        rf"[가-힣]{{2,4}}(?:\s*{_BROKEN_POLL_ROLE_FRAGMENT})?(?:이|가)\s+\d+(?:\.\d+)?%보다",
        plain,
        re.IGNORECASE,
    ):
        return True
    if re.search(rf"\d+\.\s*$", plain) and re.search(_BROKEN_POLL_ROLE_FRAGMENT, plain, re.IGNORECASE):
        return True
    if _has_malformed_double_name_matchup_phrase(plain):
        return True
    normalized_plain = _normalize_person_name(plain)
    if re.search(
        r"[가-힣]{2,4}\s+(?:시장|지사|국회의원|의원|대표|위원장|후보|예비후보)과의\s+(?:양자대결|가상대결|대결)",
        plain,
        re.IGNORECASE,
    ) and known_names:
        normalized_known_names = [
            _normalize_person_name(item)
            for item in (known_names or [])
            if _normalize_person_name(item)
        ]
        if normalized_known_names and normalized_plain.startswith(normalized_known_names[0]):
            return True

    mentioned_known_names = [
        name
        for name in (
            _normalize_person_name(item)
            for item in (known_names or [])
        )
        if name and name in normalized_plain
    ]
    if len(set(mentioned_known_names)) >= 2 and re.search(r"\d+\.\s*$", plain):
        return True
    return False


def _scrub_broken_poll_fragments_once(
    content: str,
    *,
    known_names: Optional[list[str]] = None,
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    edited = False
    actions: list[str] = []

    def _rewrite_inner(inner: str) -> str:
        nonlocal edited
        sentence_matches = [
            match
            for match in _SAFE_SENTENCE_HTML_PATTERN.finditer(str(inner or ""))
            if str(match.group(0) or "").strip()
        ]
        if not sentence_matches:
            return str(inner or "")

        kept_sentences: list[str] = []
        removed_count = 0
        for match in sentence_matches:
            sentence_html = str(match.group(0) or "")
            if _looks_like_broken_poll_fragment_sentence(
                sentence_html,
                known_names=known_names,
            ):
                removed_count += 1
                edited = True
                continue
            kept_sentences.append(sentence_html.strip())

        if removed_count <= 0:
            return str(inner or "")

        actions.append(f"broken_poll_fragment_scrub:{removed_count}")
        rebuilt = " ".join(item for item in kept_sentences if item)
        rebuilt = re.sub(r"\s{2,}", " ", rebuilt).strip()
        rebuilt = re.sub(r"\s+([,.;!?])", r"\1", rebuilt)
        return rebuilt

    repaired = _rewrite_paragraph_blocks(base, _rewrite_inner)
    return {
        "content": repaired,
        "edited": edited and repaired != base,
        "actions": actions,
    }


def _extract_integrity_units(content: str) -> list[str]:
    return [str(item.get("text") or "") for item in _extract_integrity_unit_records(content)]


def _extract_integrity_unit_records(content: str) -> list[Dict[str, Any]]:
    base = str(content or "")
    if not base.strip():
        return []

    units: list[Dict[str, Any]] = []
    for block_index, match in enumerate(CONTENT_BLOCK_WITH_TAG_PATTERN.finditer(base)):
        tag = str(match.group("tag") or "").lower() or "block"
        plain = re.sub(r"<[^>]*>", " ", str(match.group("inner") or ""))
        plain = re.sub(r"\s+", " ", plain).strip()
        if not plain:
            continue
        fragments = [
            re.sub(r"\s+", " ", fragment).strip()
            for fragment in INTEGRITY_SENTENCE_SPLIT_PATTERN.split(plain)
            if re.sub(r"\s+", " ", fragment).strip()
        ]
        if fragments:
            for fragment_index, fragment in enumerate(fragments):
                units.append(
                    {
                        "tag": tag,
                        "blockIndex": block_index,
                        "fragmentIndex": fragment_index,
                        "text": fragment,
                    }
                )
        else:
            units.append(
                {
                    "tag": tag,
                    "blockIndex": block_index,
                    "fragmentIndex": 0,
                    "text": plain,
                }
            )

    if units:
        return units

    fallback_plain = re.sub(r"<[^>]*>", " ", base)
    fallback_plain = re.sub(r"\s+", " ", fallback_plain).strip()
    if not fallback_plain:
        return []
    return [
        {
            "tag": "document",
            "blockIndex": 0,
            "fragmentIndex": 0,
            "text": fallback_plain,
        }
    ]


def _detect_integrity_gate_issues(content: str) -> list[str]:
    text = str(content or "")
    if not text.strip():
        return ["본문이 비어 있습니다."]

    plain = re.sub(r"<[^>]*>", " ", text)
    plain = re.sub(r"[ \t]+", " ", plain)
    lines = [line.strip() for line in re.split(r"[\r\n]+", plain) if line.strip()]
    integrity_unit_records = _extract_integrity_unit_records(text)

    issues: list[str] = []
    if any(re.search(r"카테고리\s*:", line) for line in lines):
        issues.append("본문에 메타데이터 블록(카테고리/검색어/생성 시간)이 포함됨")
    if any(re.search(r"검색어\s*(?:삽입|반영)\s*횟수\s*:", line) for line in lines):
        issues.append("본문에 메타데이터 블록(카테고리/검색어/생성 시간)이 포함됨")
    if any(re.search(r"생성\s*시간\s*:", line) for line in lines):
        issues.append("본문에 메타데이터 블록(카테고리/검색어/생성 시간)이 포함됨")
    if any(re.search(r"^[\"'“”‘’]?\s*[^\"'“”‘’:\n]{1,80}\s*[\"'“”‘’]?\s*:\s*\d+\s*회$", line) for line in lines):
        issues.append("본문에 검색어 삽입 집계 라인이 포함됨")

    critical_sentence_patterns: tuple[tuple[re.Pattern[str], str], ...] = (
        (
            re.compile(r"선거까지\s+아직\s*[,，]", re.IGNORECASE),
            "문장 파손(선거까지 아직 ...)",
        ),
        (
            re.compile(r"제가\s+결과(?:는|가)", re.IGNORECASE),
            "문장 파손(제가 결과 ...)",
        ),
        (
            re.compile(r"선거까지\s+남은\s*[,，]", re.IGNORECASE),
            "문장 파손(선거까지 남은 ...)",
        ),
        (
            re.compile(
                rf"[가-힣]{{2,4}}(?:\s*{_BROKEN_POLL_ROLE_FRAGMENT})?(?:이|가)\s+\d+(?:\.\d+)?%보다",
                re.IGNORECASE,
            ),
            "문장 파손(비정상 여론조사 비교)",
        ),
        (
            re.compile(r"^\d+(?:\.\d+)?%\s*보다", re.IGNORECASE),
            "문장 파손(앞절이 잘린 수치 비교)",
        ),
        (
            re.compile(r"(?:제가|저의)\s+비전에\s+대한", re.IGNORECASE),
            "문장 파손(제가 비전에 대한 ...)",
        ),
        (
            _INCOMPLETE_NEWS_FRAGMENT_RE,
            "문장 파손(불완전 뉴스 절단 문장)",
        ),
    )
    for pattern, label in critical_sentence_patterns:
        if any(pattern.search(str(unit.get("text") or "")) for unit in integrity_unit_records):
            issues.append(label)

    if any(_has_malformed_double_name_matchup_phrase(str(unit.get("text") or "")) for unit in integrity_unit_records):
        issues.append("문장 파손(인명 결합 소제목/문장)")

    for unit_record in integrity_unit_records:
        unit = str(unit_record.get("text") or "")
        problematic_numeric_runs = _find_problematic_numeric_runs(unit)
        if problematic_numeric_runs:
            first_run = problematic_numeric_runs[0]
            start = max(0, int(first_run["start"]) - 30)
            end = min(len(unit), int(first_run["end"]) + 30)
            logger.warning(
                "INTEGRITY_TOKEN_MATCH: tag=%s block=%s fragment=%s matched=%r context=%r",
                unit_record.get("tag"),
                unit_record.get("blockIndex"),
                unit_record.get("fragmentIndex"),
                str(first_run.get("text") or ""),
                unit[start:end],
            )
            issues.append("숫자/단위 토큰이 비정상적으로 연속됨")
            break

    for unit_record in integrity_unit_records:
        unit = str(unit_record.get("text") or "")
        person_chain_match = _find_valid_person_chain_match(unit)
        if person_chain_match:
            start = max(0, person_chain_match.start() - 30)
            end = min(len(unit), person_chain_match.end() + 30)
            logger.warning(
                "INTEGRITY_PERSON_CHAIN_MATCH: tag=%s block=%s fragment=%s matched=%r context=%r",
                unit_record.get("tag"),
                unit_record.get("blockIndex"),
                unit_record.get("fragmentIndex"),
                person_chain_match.group(0),
                unit[start:end],
            )
            issues.append("고유명사/직함 토큰이 비정상적으로 연속됨")
            break

    for unit_record in integrity_unit_records:
        unit = str(unit_record.get("text") or "")
        numeric_person_match = _find_valid_numeric_person_chain_match(unit)
        if numeric_person_match:
            start = max(0, numeric_person_match.start() - 30)
            end = min(len(unit), numeric_person_match.end() + 30)
            logger.warning(
                "INTEGRITY_NUMERIC_PERSON_MATCH: tag=%s block=%s fragment=%s matched=%r context=%r",
                unit_record.get("tag"),
                unit_record.get("blockIndex"),
                unit_record.get("fragmentIndex"),
                numeric_person_match.group(0),
                unit[start:end],
            )
            issues.append("숫자+인명/직함 토큰이 비정상적으로 결합됨")
            break

    suspicious_tokens = ("이 사안", "관련 현안")
    suspicious_hits = sum(plain.count(token) for token in suspicious_tokens)
    if suspicious_hits >= 3:
        issues.append("비문 유발 토큰(이 사안/관련 현안) 반복 감지")

    deduped_issues: list[str] = []
    for issue in issues:
        if issue and issue not in deduped_issues:
            deduped_issues.append(issue)
    return deduped_issues


def _extract_blocking_integrity_issues(issues: list[str]) -> list[str]:
    blocking_markers = (
        "문장 파손(",
        "숫자/단위 토큰이 비정상적으로 연속됨",
        "고유명사/직함 토큰이 비정상적으로 연속됨",
        "숫자+인명/직함 토큰이 비정상적으로 결합됨",
        "비문 유발 토큰(이 사안/관련 현안) 반복 감지",
    )
    blocking: list[str] = []
    for issue in issues:
        normalized = str(issue or "").strip()
        if not normalized:
            continue
        if any(marker in normalized for marker in blocking_markers):
            blocking.append(normalized)
    return blocking


def _repair_integrity_noise_once(content: str) -> Dict[str, Any]:
    original_base = str(content or "")
    if not original_base.strip():
        return {"content": original_base, "edited": False, "actions": []}

    integrity_clause_repairs: tuple[tuple[re.Pattern[str], str, str], ...] = (
        (
            re.compile(
                r"((?:[가-힣]{1,8}\s*(?:의원|국회의원|시장|후보|위원장)?과의\s+)?"
                r"(?:가상대결|양자대결|대결))에서\s+제가\s+결과(?:는|가)\s+",
                re.IGNORECASE,
            ),
            r"\1 결과는 ",
            "integrity_matchup_result_clause_after_i",
        ),
        (
            re.compile(
                r"((?:[가-힣]{1,8}\s*(?:의원|국회의원|시장|후보|위원장)?과의\s+)?"
                r"(?:가상대결|양자대결|대결))에서\s+(?:제가\s*)?여론조사\s+결과(?:는|가)\s+",
                re.IGNORECASE,
            ),
            r"\1의 여론조사 결과는 ",
            "integrity_poll_result_clause_after_matchup",
        ),
        (
            re.compile(r"에서\s+제가\s+결과(?:는|가)\s+", re.IGNORECASE),
            "에서 결과가 ",
            "integrity_result_clause_after_i",
        ),
        (
            re.compile(r"제가\s+결과(?:는|가)\s+", re.IGNORECASE),
            "결과가 ",
            "integrity_result_clause",
        ),
    )

    person_role_token_html_fragment = (
        rf"[가-힣]{{2,8}}{_HTML_INLINE_GAP_FRAGMENT}(?:의원|위원장|장관|후보|시장)"
    )
    numeric_token_html_fragment = _NUMERIC_UNIT_TOKEN_FRAGMENT

    noise_pattern = re.compile(
        rf"{numeric_token_html_fragment}(?:{_HTML_INLINE_SEPARATOR_FRAGMENT}{numeric_token_html_fragment}){{1,}}"
        rf"{_HTML_INLINE_SEPARATOR_FRAGMENT}{person_role_token_html_fragment}"
        rf"(?:{_HTML_INLINE_SEPARATOR_FRAGMENT}{person_role_token_html_fragment}){{1,}}",
        re.IGNORECASE,
    )
    person_chain_pattern = re.compile(
        rf"{person_role_token_html_fragment}(?:{_HTML_INLINE_SEPARATOR_FRAGMENT}{person_role_token_html_fragment}){{2,}}",
        re.IGNORECASE,
    )
    matchup_tail_pattern = re.compile(
        r"(?:[가-힣]{1,8}도\s*){0,2}(?:후보군(?:\s*대결(?:에서도|에서)?)?|[가-힣]{1,4}\s*대결(?:에서도|에서))"
    )

    repaired = original_base
    actions: list[str] = []

    h2_matches = list(H2_TAG_PATTERN.finditer(repaired))
    for match in reversed(h2_matches):
        inner = str(match.group(1) or "")
        plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", inner))
        if not plain_inner:
            continue

        has_person_chain = _find_valid_person_chain_match(plain_inner) is not None
        has_numeric_person_chain = _find_valid_numeric_person_chain_match(plain_inner) is not None
        if not has_person_chain and not has_numeric_person_chain:
            continue

        role_pairs = PERSON_ROLE_PAIR_PATTERN.findall(plain_inner)
        heading_names: list[str] = []
        for raw_name, _role in role_pairs:
            cleaned_name = _clean_full_name_candidate(raw_name)
            if not cleaned_name or not _looks_like_person_name_token(cleaned_name):
                continue
            if cleaned_name not in heading_names:
                heading_names.append(cleaned_name)

        rewritten_heading = ""
        if len(heading_names) >= 3:
            rewritten_heading = f"{'·'.join(heading_names[:3])} 구도"
        elif len(heading_names) >= 2:
            rewritten_heading = f"{heading_names[0]} vs {heading_names[1]}"
        elif heading_names:
            rewritten_heading = f"{heading_names[0]} 쟁점"
        else:
            rewritten_heading = "핵심 쟁점"

        rewritten_heading = rewritten_heading.strip()
        if not rewritten_heading or rewritten_heading == plain_inner:
            continue

        repaired = repaired[: match.start(1)] + rewritten_heading + repaired[match.end(1) :]
        if has_numeric_person_chain:
            actions.append("numeric_person_chain_h2_rewrite")
        else:
            actions.append("person_role_chain_h2_rewrite")

    paragraph_matches = list(PARAGRAPH_TAG_PATTERN.finditer(repaired))
    for match in reversed(paragraph_matches):
        inner = str(match.group(1) or "")
        updated_inner = inner
        changed = False

        removed_noise = 0

        def _replace_noise_inner(match: re.Match[str]) -> str:
            nonlocal removed_noise
            if not _is_valid_person_role_chain_text(match.group(0), min_pairs=2):
                return match.group(0)
            removed_noise += 1
            return " "

        updated_inner = noise_pattern.sub(_replace_noise_inner, updated_inner)
        if removed_noise > 0:
            actions.append(f"numeric_person_chain:{removed_noise}")
            changed = True

        removed_person_chain = 0

        def _replace_person_chain_inner(match: re.Match[str]) -> str:
            nonlocal removed_person_chain
            if not _is_valid_person_role_chain_text(match.group(0), min_pairs=3):
                return match.group(0)
            removed_person_chain += 1
            return " "

        updated_inner = person_chain_pattern.sub(_replace_person_chain_inner, updated_inner)
        if removed_person_chain > 0:
            actions.append(f"person_role_chain:{removed_person_chain}")
            changed = True

        if changed:
            updated_inner, removed_matchup_tail = matchup_tail_pattern.subn(" ", updated_inner)
            if removed_matchup_tail > 0:
                actions.append(f"matchup_tail:{removed_matchup_tail}")

        problematic_runs = _find_problematic_numeric_runs(updated_inner)
        drop_paragraph = False
        if problematic_runs:
            for run in reversed(problematic_runs):
                run_start = int(run.get("start") or 0)
                run_end = int(run.get("end") or 0)
                before = updated_inner[:run_start]
                after = updated_inner[run_end:]
                if before.strip() and after.strip():
                    plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", updated_inner))
                    non_numeric_text = _normalize_inline_whitespace(
                        re.sub(
                            rf"(?<!\S){_NUMERIC_UNIT_TOKEN_FRAGMENT}(?:\s+{_NUMERIC_UNIT_TOKEN_FRAGMENT})*",
                            " ",
                            plain_inner,
                        )
                    )
                    has_meaningful_korean = bool(re.search(r"[가-힣]{2,}", non_numeric_text))
                    if len(non_numeric_text) < 10 or not has_meaningful_korean:
                        repaired = repaired[: match.start()] + repaired[match.end() :]
                        actions.append("drop_numeric_noise_paragraph")
                        changed = True
                        drop_paragraph = True
                        break
                    continue

                replacement_text = ""
                leading_datetime_prefix = _extract_leading_datetime_prefix(run.get("text"))
                if leading_datetime_prefix and leading_datetime_prefix != str(run.get("text") or ""):
                    replacement_text = leading_datetime_prefix
                    actions.append("numeric_run_datetime_prefix_preserved")

                updated_inner = before.rstrip()
                if replacement_text:
                    if updated_inner:
                        updated_inner += " "
                    updated_inner += replacement_text
                if (updated_inner or replacement_text) and after.lstrip():
                    updated_inner += " "
                updated_inner += after.lstrip()
                actions.append(f"numeric_run_edge_trim:{str(run.get('text') or '')[:48]}")
                changed = True

        if drop_paragraph:
            continue

        plain_candidate = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", updated_inner))
        if plain_candidate and (
            _find_valid_person_chain_match(plain_candidate) is not None
            or _find_valid_numeric_person_chain_match(plain_candidate) is not None
            or _looks_like_low_signal_residue_fragment(plain_candidate)
        ):
            fragment_repair = _prune_problematic_integrity_fragments(updated_inner)
            if fragment_repair.get("edited"):
                updated_inner = str(fragment_repair.get("content") or "")
                fragment_actions = fragment_repair.get("actions")
                if isinstance(fragment_actions, list):
                    for action in fragment_actions:
                        action_text = str(action).strip()
                        if action_text:
                            actions.append(action_text)
                changed = True

        residue_fix = _scrub_suspicious_poll_residue_text(updated_inner)
        if residue_fix.get("edited"):
            updated_inner = str(residue_fix.get("content") or updated_inner)
            residue_actions = residue_fix.get("actions")
            if isinstance(residue_actions, list):
                for action in residue_actions:
                        action_text = str(action).strip()
                        if action_text:
                            actions.append(action_text)
            changed = True

        for pattern, replacement, action_label in integrity_clause_repairs:
            updated_inner, repair_count = pattern.subn(replacement, updated_inner)
            if repair_count > 0:
                actions.append(f"{action_label}:{repair_count}")
                changed = True

        if not changed:
            continue

        updated_inner = re.sub(r"\s{2,}", " ", updated_inner).strip()
        plain_after = re.sub(r"<[^>]*>", " ", updated_inner)
        plain_after = re.sub(r"\s+", " ", plain_after).strip()
        if len(plain_after) < 24:
            has_meaningful_korean = bool(re.search(r"[가-힣]{2,}", plain_after))
            if len(plain_after) < 12 or not has_meaningful_korean:
                repaired = repaired[: match.start()] + repaired[match.end() :]
                actions.append("drop_short_noisy_paragraph")
                continue

        repaired = repaired[: match.start(1)] + updated_inner + repaired[match.end(1) :]

    return {
        "content": repaired,
        "edited": repaired != original_base,
        "actions": actions,
    }


def _split_sentence_like_units(text: str) -> list[str]:
    normalized = _normalize_inline_whitespace(text)
    if not normalized:
        return []

    parts = [
        str(match.group(0) or "").strip()
        for match in SENTENCE_LIKE_UNIT_PATTERN.finditer(normalized)
        if str(match.group(0) or "").strip()
    ]
    return parts or [normalized]


def _detect_targeted_sentence_polish_issue(text: str, *, tag: str) -> str:
    candidate = _normalize_inline_whitespace(text)
    if not candidate:
        return ""

    normalized_tag = str(tag or "").strip().lower()
    if normalized_tag == "h2":
        if TARGETED_POLISH_HEADING_PATTERN.search(candidate):
            return "heading_first_person_topic"
        return ""

    for pattern, reason in TARGETED_POLISH_SENTENCE_PATTERNS:
        if pattern.search(candidate):
            return reason
    return ""


def _targeted_sentence_reason_hint(reason: str) -> str:
    return TARGETED_POLISH_REASON_HINTS.get(str(reason or "").strip(), "")


def _targeted_sentence_reason_priority(reason: str) -> int:
    normalized = str(reason or "").strip().lower()
    if normalized in {"matchup_result_clause", "matchup_result_clause_spaced"}:
        return 100
    if normalized == "heading_first_person_topic":
        return 95
    if normalized == "ai_alternative_voice_overlay":
        return 90
    if normalized == "intro_voice_overlay":
        return 85
    if normalized == "closing_voice_overlay":
        return 80
    if normalized == "boilerplate_voice_overlay":
        return 75
    if normalized == "transition_voice_overlay":
        return 70
    if normalized == "jeonim_voice_overlay":
        return 65
    return 50


def _is_targeted_voice_overlay_reason(reason: str) -> bool:
    return str(reason or "").strip().endswith("_voice_overlay")


def _is_targeted_uncapped_style_reason(reason: str) -> bool:
    return str(reason or "").strip().lower() == "ai_alternative_voice_overlay"


def _resolve_targeted_sentence_style_limits(mode: str) -> Dict[str, Any]:
    normalized_mode = str(mode or "").strip().lower()
    if normalized_mode not in TARGETED_POLISH_STYLE_LIMITS:
        normalized_mode = "light"
    return TARGETED_POLISH_STYLE_LIMITS[normalized_mode]


def _extract_targeted_sentence_ai_alternative_rules(
    style_fingerprint: Optional[Dict[str, Any]] = None,
) -> list[Dict[str, str]]:
    fingerprint = _safe_dict(style_fingerprint)
    ai_alternatives = _safe_dict(fingerprint.get("aiAlternatives"))
    rules: list[Dict[str, str]] = []
    seen_sources: set[str] = set()

    for raw_key, raw_value in ai_alternatives.items():
        replacement = _normalize_inline_whitespace(raw_value)
        source = _normalize_inline_whitespace(
            str(raw_key or "").replace("instead_of_", "").replace("_", " ").strip()
        )
        if not source or not replacement or source == replacement or source in seen_sources:
            continue
        seen_sources.add(source)
        rules.append({"source": source, "target": replacement})

    rules.sort(key=lambda item: (-len(str(item.get("source") or "")), str(item.get("source") or "")))
    return rules


_GENERIC_BETTER_FUTURE_PATTERN = re.compile(
    r"(?:더|보다)\s+나(?:은|은)\s+(?P<noun>[가-힣A-Za-z0-9]+?)(?P<particle>으로|로|를|을|은|는|이|가|의)?(?=$|[\s,.;:!?])",
    re.IGNORECASE,
)


def _extract_generic_better_future_target(rules: list[Dict[str, str]]) -> str:
    for rule in rules:
        source = _normalize_inline_whitespace(rule.get("source"))
        target = _normalize_inline_whitespace(rule.get("target"))
        if not source or not target:
            continue
        if source.startswith("더 나은 ") or source.startswith("보다 나은 "):
            return target
    return ""


_STYLE_ALTERNATIVE_PARTICLE_PAIRS: tuple[tuple[str, str], ...] = (
    ("은", "는"),
    ("이", "가"),
    ("을", "를"),
    ("과", "와"),
)


def _normalize_style_alternative_particles(
    text: str,
    targets: Iterable[str],
) -> str:
    updated = str(text or "")
    normalized_targets = sorted(
        {
            _normalize_inline_whitespace(target)
            for target in (str(item or "").strip() for item in targets)
            if _normalize_inline_whitespace(target)
        },
        key=len,
        reverse=True,
    )
    if not updated or not normalized_targets:
        return updated

    for target in normalized_targets:
        for with_batchim, without_batchim in _STYLE_ALTERNATIVE_PARTICLE_PAIRS:
            pattern = re.compile(
                rf"(?P<lemma>{re.escape(target)})(?P<particle>{with_batchim}|{without_batchim})(?=$|[\s,.;:!?])"
            )

            def _replace(match: re.Match[str]) -> str:
                lemma = str(match.group("lemma") or target)
                particle = with_batchim if _has_final_consonant(lemma) else without_batchim
                return f"{lemma}{particle}"

            updated = pattern.sub(_replace, updated)
    return updated


def _normalize_style_alternative_surface_fixes(text: str) -> str:
    updated = str(text or "")
    if not updated:
        return updated
    updated = re.sub(r"부산의\s+부산경제", "부산경제", updated, flags=re.IGNORECASE)
    return updated


def _apply_generic_better_future_alternative(
    text: str,
    replacement: str,
) -> tuple[str, list[tuple[str, str]]]:
    updated = str(text or "")
    target = _normalize_inline_whitespace(replacement)
    if not updated or not target:
        return updated, []

    applied: list[tuple[str, str]] = []

    def _replace(match: re.Match[str]) -> str:
        particle = str(match.group("particle") or "")
        applied.append((str(match.group(0) or "").strip(), target))
        return f"{target}{particle}"

    rewritten, count = _GENERIC_BETTER_FUTURE_PATTERN.subn(_replace, updated)
    if count <= 0:
        return updated, []
    return rewritten, applied


def _find_targeted_sentence_ai_alternative_rules(
    text: str,
    rules: list[Dict[str, str]],
) -> list[Dict[str, str]]:
    candidate = _normalize_inline_whitespace(text)
    if not candidate or not rules:
        return []
    return [
        {"source": str(rule.get("source") or ""), "target": str(rule.get("target") or "")}
        for rule in rules
        if str(rule.get("source") or "") and str(rule.get("source") or "") in candidate
    ]


def _apply_targeted_sentence_ai_alternative_rules(
    text: str,
    rules: list[Dict[str, str]],
) -> tuple[str, list[tuple[str, str]]]:
    updated = _normalize_inline_whitespace(text)
    if not updated or not rules:
        return updated, []

    applied: list[tuple[str, str]] = []
    for rule in rules:
        source = str(rule.get("source") or "").strip()
        target = str(rule.get("target") or "").strip()
        if not source or not target or source not in updated:
            continue
        updated = updated.replace(source, target)
        applied.append((source, target))

    generic_better_future_target = _extract_generic_better_future_target(rules)
    updated, generic_applied = _apply_generic_better_future_alternative(updated, generic_better_future_target)
    applied.extend(generic_applied)
    updated = _normalize_style_alternative_particles(
        updated,
        [str(rule.get("target") or "") for rule in rules] + ([generic_better_future_target] if generic_better_future_target else []),
    )
    updated = _normalize_style_alternative_surface_fixes(updated)
    return updated, applied


def _apply_global_style_ai_alternative_rules_once(
    content: str,
    style_fingerprint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    rules = _extract_targeted_sentence_ai_alternative_rules(style_fingerprint)
    if not rules:
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    actions: list[str] = []
    generic_better_future_target = _extract_generic_better_future_target(rules)
    for match in reversed(list(CONTENT_BLOCK_WITH_TAG_PATTERN.finditer(base))):
        raw_inner = str(match.group("inner") or "")
        plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", raw_inner))
        if not plain_inner:
            continue
        if any(marker in plain_inner for marker in TARGETED_POLISH_EXCLUDED_MARKERS):
            continue
        if QUOTE_CHAR_PATTERN.search(plain_inner):
            continue

        matched_rules = _find_targeted_sentence_ai_alternative_rules(plain_inner, rules)
        if not matched_rules and not generic_better_future_target:
            continue

        updated_inner = raw_inner
        applied_pairs: list[tuple[str, str]] = []
        for rule in matched_rules:
            source = str(rule.get("source") or "").strip()
            target = str(rule.get("target") or "").strip()
            if not source or not target or source not in updated_inner:
                continue
            updated_inner = updated_inner.replace(source, target)
            applied_pairs.append((source, target))

        updated_inner, generic_applied = _apply_generic_better_future_alternative(
            updated_inner,
            generic_better_future_target,
        )
        applied_pairs.extend(generic_applied)
        updated_inner = _normalize_style_alternative_particles(
            updated_inner,
            [str(rule.get("target") or "") for rule in matched_rules]
            + ([generic_better_future_target] if generic_better_future_target else []),
        )
        updated_inner = _normalize_style_alternative_surface_fixes(updated_inner)

        if not applied_pairs or updated_inner == raw_inner:
            continue

        repaired = repaired[: match.start("inner")] + updated_inner + repaired[match.end("inner") :]
        actions.append(
            "global_style_ai_alternative:" + "|".join(f"{source}→{target}" for source, target in applied_pairs)
        )

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


def _build_section_overlap_tokens(text: str) -> set[str]:
    normalized = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not normalized:
        return set()
    stopwords = {
        "그리고",
        "하지만",
        "그러나",
        "이번",
        "최근",
        "이재성",
        "부산",
        "시민",
        "가능성",
        "주목해야",
        "이유는",
    }
    return {
        token
        for token in re.findall(r"[가-힣A-Za-z0-9%]{2,}", normalized)
        if token and token not in stopwords
    }


def _section_overlap_score(text_a: str, text_b: str) -> float:
    tokens_a = _build_section_overlap_tokens(text_a)
    tokens_b = _build_section_overlap_tokens(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    overlap = len(tokens_a & tokens_b)
    baseline = max(1, min(len(tokens_a), len(tokens_b)))
    return overlap / baseline


def _heading_semantic_family_key(text: str) -> str:
    normalized = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    compact = re.sub(r"\s+", "", normalized)
    if not compact:
        return ""
    if "주목" in compact and ("가능성" in compact or "이유" in compact):
        return "possibility_focus"
    return ""


def _dedupe_overlapping_sections_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    if len(h2_matches) < 2:
        return {"content": base, "edited": False, "actions": []}

    seen_headings: dict[str, Dict[str, Any]] = {}
    seen_heading_families: dict[str, Dict[str, Any]] = {}
    seen_first_sentences: dict[str, Dict[str, Any]] = {}
    removals: list[tuple[int, int]] = []
    actions: list[str] = []

    for index, match in enumerate(h2_matches):
        section_start = match.start()
        section_end = h2_matches[index + 1].start() if index + 1 < len(h2_matches) else len(base)
        heading_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(match.group(1) or "")))
        section_html = base[match.end() : section_end]
        section_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", section_html))
        if not heading_plain or not section_plain:
            continue

        first_paragraph_match = PARAGRAPH_TAG_PATTERN.search(section_html)
        first_paragraph_plain = ""
        if first_paragraph_match:
            first_paragraph_plain = _normalize_inline_whitespace(
                re.sub(r"<[^>]*>", " ", str(first_paragraph_match.group(1) or ""))
            )
        lead_sentences = _split_sentence_like_units(first_paragraph_plain or section_plain)
        lead_sentence = str(lead_sentences[0] or "").strip() if lead_sentences else ""
        signature_source = lead_sentence or section_plain[:140]

        duplicate_reason = ""
        previous_heading = seen_headings.get(heading_plain)
        if previous_heading:
            if lead_sentence and lead_sentence == str(previous_heading.get("leadSentence") or ""):
                duplicate_reason = "duplicate_heading_and_lead"
            elif _section_overlap_score(
                signature_source,
                str(previous_heading.get("signatureSource") or ""),
            ) >= 0.72:
                duplicate_reason = "duplicate_heading_overlap"

        heading_family = _heading_semantic_family_key(heading_plain)
        if not duplicate_reason and heading_family:
            previous_family = seen_heading_families.get(heading_family)
            if previous_family:
                duplicate_reason = "duplicate_heading_family"

        if not duplicate_reason and lead_sentence:
            previous_lead = seen_first_sentences.get(lead_sentence)
            if previous_lead and _section_overlap_score(
                section_plain,
                str(previous_lead.get("sectionPlain") or ""),
            ) >= 0.72:
                duplicate_reason = "duplicate_lead_section"

        if duplicate_reason:
            removals.append((section_start, section_end))
            actions.append(f"section_dedupe:{duplicate_reason}:{heading_plain}")
            continue

        info = {
            "headingPlain": heading_plain,
            "leadSentence": lead_sentence,
            "signatureSource": signature_source,
            "sectionPlain": section_plain,
        }
        seen_headings.setdefault(heading_plain, info)
        if heading_family and heading_family not in seen_heading_families:
            seen_heading_families[heading_family] = info
        if lead_sentence and lead_sentence not in seen_first_sentences:
            seen_first_sentences[lead_sentence] = info

    if not removals:
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    for start, end in sorted(removals, key=lambda item: item[0], reverse=True):
        repaired = repaired[:start] + repaired[end:]
    repaired = re.sub(r"\n{3,}", "\n\n", repaired).strip()
    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


_INTRO_BODY_DUPLICATE_MIN_CHARS = 18
_INTRO_BODY_DUPLICATE_SIMILARITY = 0.84
_INTRO_BODY_DUPLICATE_SOFT_SIMILARITY = 0.58
_INTRO_BODY_DUPLICATE_COMMON_BLOCK = 14


def _normalize_intro_body_sentence_surface(text: Any) -> str:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain:
        return ""
    plain = re.sub(r"[\"'“”‘’`´·•,.:;!?()\[\]{}<>《》「」『』…\-–—]", "", plain)
    return re.sub(r"\s+", "", plain).strip()


def _is_intro_body_duplicate_sentence(intro_sentence: str, candidate_sentence: str) -> bool:
    intro_norm = _normalize_intro_body_sentence_surface(intro_sentence)
    candidate_norm = _normalize_intro_body_sentence_surface(candidate_sentence)
    if not intro_norm or not candidate_norm:
        return False
    if intro_norm == candidate_norm:
        return True
    if min(len(intro_norm), len(candidate_norm)) < _INTRO_BODY_DUPLICATE_MIN_CHARS:
        return False

    matcher = SequenceMatcher(None, intro_norm, candidate_norm)
    similarity = matcher.ratio()
    if similarity >= _INTRO_BODY_DUPLICATE_SIMILARITY:
        return True

    longest_common = matcher.find_longest_match(0, len(intro_norm), 0, len(candidate_norm)).size
    return (
        similarity >= _INTRO_BODY_DUPLICATE_SOFT_SIMILARITY
        and longest_common >= _INTRO_BODY_DUPLICATE_COMMON_BLOCK
    )


def _dedupe_intro_body_overlap_sentences_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    sections = _split_into_sections(base)
    if len(sections) < 2 or bool(sections[0].get("has_h2")):
        return {"content": base, "edited": False, "actions": []}

    intro_html = str(sections[0].get("html") or "")
    intro_sentences: list[str] = []
    for match in PARAGRAPH_TAG_PATTERN.finditer(intro_html):
        intro_inner = str(match.group(1) or "")
        intro_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", intro_inner))
        if not intro_plain:
            continue
        for sentence in _split_sentence_like_units(intro_plain):
            sentence_text = _normalize_inline_whitespace(sentence)
            if len(sentence_text) >= _INTRO_BODY_DUPLICATE_MIN_CHARS:
                intro_sentences.append(sentence_text)

    if not intro_sentences:
        return {"content": base, "edited": False, "actions": []}

    removed_count = 0
    updated_sections: list[dict[str, Any]] = [dict(sections[0])]

    for section in sections[1:]:
        section_html = str(section.get("html") or "")
        local_removed = 0

        def _rewrite_inner(inner: str) -> str:
            nonlocal local_removed
            plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(inner or "")))
            if not plain_inner:
                return str(inner or "")

            sentences = _split_sentence_like_units(plain_inner)
            if not sentences:
                return plain_inner

            kept_sentences: list[str] = []
            for sentence in sentences:
                sentence_text = _normalize_inline_whitespace(sentence)
                if not sentence_text:
                    continue
                if any(
                    _is_intro_body_duplicate_sentence(intro_sentence, sentence_text)
                    for intro_sentence in intro_sentences
                ):
                    local_removed += 1
                    continue
                kept_sentences.append(sentence_text)

            return " ".join(kept_sentences).strip() if kept_sentences else ""

        updated_html = _rewrite_paragraph_blocks(section_html, _rewrite_inner)
        if local_removed > 0:
            updated_html = re.sub(r"<p\b[^>]*>\s*</p\s*>", "", updated_html, flags=re.IGNORECASE)
            updated_html = re.sub(r"\n{3,}", "\n\n", updated_html).strip()
            if updated_html and len(re.findall(r"<p\b[^>]*>[\s\S]*?</p\s*>", updated_html, re.IGNORECASE)) > 0:
                removed_count += local_removed
                updated_sections.append({**section, "html": updated_html})
                continue
        updated_sections.append(dict(section))

    if removed_count <= 0:
        return {"content": base, "edited": False, "actions": []}

    repaired = _join_sections(updated_sections)
    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": [f"intro_body_sentence_dedupe:{removed_count}"],
    }


def _dedupe_closing_appeal_sentences_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    appeal_pattern = re.compile(
        r"(?:많은\s+관심과\s+(?:응원|지지)|많은\s+지지와\s+성원).{0,8}부탁드립니다",
        re.IGNORECASE,
    )
    seen_appeal = False
    removed_count = 0

    def _rewrite_inner(inner: str) -> str:
        nonlocal seen_appeal, removed_count
        sentence_matches = list(SENTENCE_LIKE_UNIT_PATTERN.finditer(str(inner or "")))
        if not sentence_matches:
            return str(inner or "")

        if not any(
            appeal_pattern.search(
                _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(match.group(0) or "")))
            )
            for match in sentence_matches
        ):
            return str(inner or "")

        kept_sentences: list[str] = []
        for match in reversed(sentence_matches):
            sentence_html = str(match.group(0) or "")
            plain_sentence = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", sentence_html))
            if appeal_pattern.search(plain_sentence):
                if seen_appeal:
                    removed_count += 1
                    continue
                seen_appeal = True
            kept_sentences.append(sentence_html.strip())

        kept_sentences.reverse()
        rebuilt = " ".join(item for item in kept_sentences if item)
        rebuilt = re.sub(r"\s{2,}", " ", rebuilt).strip()
        rebuilt = re.sub(r"\s+([,.;!?])", r"\1", rebuilt)
        return rebuilt

    repaired = _rewrite_paragraph_blocks(base, _rewrite_inner)
    repaired = re.sub(r"<p\b[^>]*>\s*</p\s*>", "", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\n{3,}", "\n\n", repaired)
    actions = [f"closing_appeal_dedupe:{removed_count}"] if removed_count > 0 else []
    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


def _contains_targeted_style_marker(text: str, markers: tuple[str, ...]) -> bool:
    candidate = _normalize_inline_whitespace(text)
    if not candidate:
        return False
    return any(marker and marker in candidate for marker in markers)


def _contains_targeted_style_pattern(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    candidate = _normalize_inline_whitespace(text)
    if not candidate:
        return False
    return any(pattern.search(candidate) for pattern in patterns)


def _contains_targeted_beyond_boilerplate(text: str) -> bool:
    candidate = _normalize_inline_whitespace(text)
    if not candidate:
        return False
    return any(pattern.search(candidate) for pattern in _SIMPLE_NEGATION_FRAME_RE_LIST)


def _is_targeted_style_candidate_safe(text: str) -> bool:
    candidate = _normalize_inline_whitespace(text)
    if not candidate:
        return False
    if len(candidate) < 10 or len(candidate) > TARGETED_POLISH_MAX_TEXT_LENGTH:
        return False
    if _extract_targeted_polish_numeric_tokens(candidate):
        return False
    if QUOTE_CHAR_PATTERN.search(candidate):
        return False
    if any(marker in candidate for marker in TARGETED_POLISH_EXCLUDED_MARKERS):
        return False
    return True


def _detect_targeted_sentence_style_issue(
    text: str,
    *,
    paragraph_index: int,
    paragraph_count: int,
    sentence_index: int,
    sentence_count: int,
    paragraph_jeonim_count: int = 0,
    adjacent_jeonim: bool = False,
    ai_alternative_sources: tuple[str, ...] = (),
) -> str:
    candidate = _normalize_inline_whitespace(text)
    if not _is_targeted_style_candidate_safe(candidate):
        return ""

    if _contains_targeted_style_marker(candidate, ai_alternative_sources):
        return "ai_alternative_voice_overlay"

    if paragraph_index == 0 and sentence_index < min(2, max(1, sentence_count)):
        return "intro_voice_overlay"

    if _contains_targeted_style_marker(candidate, TARGETED_POLISH_CONCLUSION_MARKERS):
        return "closing_voice_overlay"

    if paragraph_count > 0 and paragraph_index >= max(0, paragraph_count - 2):
        if sentence_index >= max(0, sentence_count - 1):
            return "closing_voice_overlay"

    if (
        _contains_targeted_style_marker(candidate, TARGETED_POLISH_BOILERPLATE_MARKERS)
        or _contains_targeted_style_pattern(candidate, TARGETED_POLISH_BOILERPLATE_PATTERNS)
        or _contains_targeted_beyond_boilerplate(candidate)
        or _is_orphan_boilerplate_sentence(candidate)
    ):
        return "boilerplate_voice_overlay"

    if _contains_targeted_style_marker(candidate, TARGETED_POLISH_TRANSITION_MARKERS):
        return "transition_voice_overlay"

    if _contains_targeted_style_marker(candidate, TARGETED_POLISH_INTRO_MARKERS):
        return "intro_voice_overlay"

    # 본문 중간에서 저는/제가 시작 반복 감지 (도입·마무리는 위에서 이미 처리됨)
    if (
        paragraph_count > 3
        and 0 < paragraph_index < paragraph_count - 1
        and paragraph_jeonim_count >= 2
        and (adjacent_jeonim or paragraph_jeonim_count >= 3)
        and TARGETED_POLISH_JEONIM_START_RE.match(candidate)
        and not TARGETED_POLISH_POLICY_ACTION_RE.search(candidate)
    ):
        return "jeonim_voice_overlay"

    return ""


def _build_targeted_sentence_style_instruction(
    *,
    style_guide: str = "",
    style_fingerprint: Optional[Dict[str, Any]] = None,
    mode: str = "",
) -> str:
    fingerprint = _safe_dict(style_fingerprint)
    normalized_mode = mode if mode in TARGETED_POLISH_STYLE_LIMITS else "light"
    limits = TARGETED_POLISH_STYLE_LIMITS[normalized_mode]

    normalized_guide = re.sub(r"\s+", " ", str(style_guide or "")).strip()
    metadata = _safe_dict(fingerprint.get("analysisMetadata"))
    try:
        confidence = float(metadata.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0

    if not normalized_guide and confidence < TARGETED_POLISH_STYLE_FINGERPRINT_MIN_CONFIDENCE:
        return ""

    lines = [
        (
            f"- 최대 {limits['max_sentences']}문장 또는 전체의 {limits['max_ratio']} 이내에서만 적용."
        ),
        "- 사실·숫자·날짜·이름·직함·인용·정책·검색어는 절대 변경 금지.",
        "- 전체 문장 재작성 금지 — 어미·조사·상투 구절 치환만.",
    ]

    if normalized_guide:
        guide_excerpt = normalized_guide[:TARGETED_POLISH_STYLE_GUIDE_MAX_CHARS]
        if len(normalized_guide) > TARGETED_POLISH_STYLE_GUIDE_MAX_CHARS:
            guide_excerpt += "..."
        lines.append(f"\n[문체 방향]\n{guide_excerpt}")

    if confidence >= TARGETED_POLISH_STYLE_FINGERPRINT_MIN_CONFIDENCE:
        phrases = _safe_dict(fingerprint.get("characteristicPhrases"))
        sentence_patterns = _safe_dict(fingerprint.get("sentencePatterns"))
        tone = _safe_dict(fingerprint.get("toneProfile"))
        ai_alternative_rules = _extract_targeted_sentence_ai_alternative_rules(fingerprint)

        # 치환 규칙 (가장 구체적·실행 가능한 규칙을 앞에)
        replacement_pairs: list[str] = []
        for rule in ai_alternative_rules[:5]:
            source = str(rule.get("source") or "").strip()
            replacement = str(rule.get("target") or "").strip()
            if not replacement or not source:
                continue
            replacement_pairs.append(f'"{source}"→"{replacement}"')
            if len(replacement_pairs) >= 5:
                break
        if replacement_pairs:
            lines.append(f"- 치환 규칙: {', '.join(replacement_pairs)}")

        # 금지/회피 표현 (fingerprint avoidances)
        avoid_phrases: list[str] = []
        raw_phrase_avoidances = phrases.get("avoidances") or []
        if isinstance(raw_phrase_avoidances, list):
            for raw_val in raw_phrase_avoidances:
                val = str(raw_val or "").strip()
                if val and val not in avoid_phrases:
                    avoid_phrases.append(val)
                if len(avoid_phrases) >= 5:
                    break
        raw_top_avoidances = fingerprint.get("avoidances") or []
        if isinstance(raw_top_avoidances, list):
            for raw_val in raw_top_avoidances:
                val = str(raw_val or "").strip()
                if val and val not in avoid_phrases:
                    avoid_phrases.append(val)
                if len(avoid_phrases) >= 5:
                    break
        if avoid_phrases:
            lines.append(f"- 금지/회피 표현: {', '.join(avoid_phrases[:5])}")

        # 허용 시그니처 표현
        phrase_examples, identity_signatures = _collect_style_phrase_examples(phrases)
        if phrase_examples:
            lines.append(f"- 허용 시그니처: {', '.join(phrase_examples[:5])}")
        if identity_signatures:
            lines.append(
                "- 정체성 시그니처는 자기 이름/1인칭 선언 문장(도입·마감)에서만 사용하고 "
                f"타인 묘사·복수형·수식어로 변형하지 마세요: {', '.join(identity_signatures[:3])}"
            )

        # 선호 시작어
        starters = sentence_patterns.get("preferredStarters") or []
        if isinstance(starters, list):
            preferred_starters = [str(item).strip() for item in starters if str(item).strip()][:3]
            if preferred_starters:
                lines.append(f"- 선호 시작어: {', '.join(preferred_starters)}")

        # 어조
        tone_tags: list[str] = []
        try:
            formality = float(tone.get("formality") or 0)
        except (TypeError, ValueError):
            formality = 0.0
        try:
            directness = float(tone.get("directness") or 0)
        except (TypeError, ValueError):
            directness = 0.0
        try:
            optimism = float(tone.get("optimism") or 0)
        except (TypeError, ValueError):
            optimism = 0.0
        if formality >= 0.6:
            tone_tags.append("격식 유지, 딱딱하지 않게")
        elif 0 < formality <= 0.4:
            tone_tags.append("구어적 호흡 허용")
        if directness >= 0.6:
            tone_tags.append("직설적 전달")
        if optimism >= 0.6:
            tone_tags.append("낙관·자신감 표현")
        tone_description = str(tone.get("toneDescription") or "").strip()
        if tone_tags or tone_description:
            tone_text = ", ".join(tone_tags) if tone_tags else tone_description
            if tone_description and tone_description not in tone_text:
                tone_text = f"{tone_text}. {tone_description}"
            lines.append(f"- 어조: {tone_text}")

    return "\n".join(lines)


def _collect_targeted_sentence_polish_candidates(
    content: str,
    *,
    style_instruction: str = "",
    style_polish_mode: str = "",
    style_fingerprint: Optional[Dict[str, Any]] = None,
) -> list[Dict[str, Any]]:
    base = str(content or "")
    if not base.strip():
        return []

    candidates: list[Dict[str, Any]] = []
    style_enabled = bool(str(style_instruction or "").strip())
    style_limits = _resolve_targeted_sentence_style_limits(style_polish_mode)
    ai_alternative_rules = (
        _extract_targeted_sentence_ai_alternative_rules(style_fingerprint) if style_enabled else []
    )
    ai_alternative_sources = tuple(str(rule.get("source") or "") for rule in ai_alternative_rules)
    paragraph_order: Dict[str, int] = {}

    paragraph_counter = 0
    for block_index, match in enumerate(CONTENT_BLOCK_WITH_TAG_PATTERN.finditer(base)):
        tag = str(match.group("tag") or "").strip().lower()
        if tag != "p":
            continue
        raw_inner = str(match.group("inner") or "")
        if "<" in raw_inner:
            continue
        normalized_inner = _normalize_inline_whitespace(raw_inner)
        if not normalized_inner:
            continue
        paragraph_order[f"{tag}-{block_index}"] = paragraph_counter
        paragraph_counter += 1

    for block_index, match in enumerate(CONTENT_BLOCK_WITH_TAG_PATTERN.finditer(base)):
        tag = str(match.group("tag") or "").strip().lower()
        raw_inner = str(match.group("inner") or "")
        plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", raw_inner))
        if not plain_inner:
            continue

        block_key = f"{tag}-{block_index}"
        if tag == "h2":
            reason = _detect_targeted_sentence_polish_issue(plain_inner, tag=tag)
            if reason and len(plain_inner) <= TARGETED_POLISH_MAX_TEXT_LENGTH:
                candidates.append(
                    {
                        "id": block_key,
                        "tag": tag,
                        "reason": reason,
                        "hint": _targeted_sentence_reason_hint(reason),
                        "priority": _targeted_sentence_reason_priority(reason),
                        "text": plain_inner,
                        "blockIndex": block_index,
                        "sentenceIndex": -1,
                        "blockKey": block_key,
                        "blockInner": plain_inner,
                        "innerStart": match.start("inner"),
                        "innerEnd": match.end("inner"),
                    }
                )
            continue

        if tag != "p" or "<" in raw_inner:
            continue

        normalized_inner = _normalize_inline_whitespace(raw_inner)
        if not normalized_inner:
            continue

        paragraph_index = int(paragraph_order.get(block_key, -1))
        sentences = _split_sentence_like_units(normalized_inner)
        sentence_count = len(sentences)
        jeonim_sentence_indexes = {
            idx
            for idx, item in enumerate(sentences)
            if TARGETED_POLISH_JEONIM_START_RE.match(_normalize_inline_whitespace(item))
        }
        paragraph_jeonim_count = len(jeonim_sentence_indexes)

        for sentence_index, sentence in enumerate(sentences):
            if len(sentence) > TARGETED_POLISH_MAX_TEXT_LENGTH:
                continue

            matched_style_rules = _find_targeted_sentence_ai_alternative_rules(sentence, ai_alternative_rules)
            reason = _detect_targeted_sentence_polish_issue(sentence, tag=tag)
            if not reason and style_enabled:
                reason = _detect_targeted_sentence_style_issue(
                    sentence,
                    paragraph_index=paragraph_index,
                    paragraph_count=paragraph_counter,
                    sentence_index=sentence_index,
                    sentence_count=sentence_count,
                    paragraph_jeonim_count=paragraph_jeonim_count,
                    adjacent_jeonim=(
                        (sentence_index - 1) in jeonim_sentence_indexes
                        or (sentence_index + 1) in jeonim_sentence_indexes
                    ),
                    ai_alternative_sources=ai_alternative_sources,
                )
            if not reason:
                continue

            candidate = {
                "id": f"{block_key}-s{sentence_index}",
                "tag": tag,
                "reason": reason,
                "hint": _targeted_sentence_reason_hint(reason),
                "priority": _targeted_sentence_reason_priority(reason),
                "text": sentence,
                "blockIndex": block_index,
                "sentenceIndex": sentence_index,
                "blockKey": block_key,
                "blockInner": normalized_inner,
                "innerStart": match.start("inner"),
                "innerEnd": match.end("inner"),
            }
            if matched_style_rules:
                candidate["styleRulePairs"] = matched_style_rules
            candidates.append(candidate)
    candidates.sort(
        key=lambda item: (
            -int(item.get("priority") or 0),
            int(item.get("blockIndex") or 0),
            int(item.get("sentenceIndex") or -1),
        )
    )

    if not style_enabled:
        return candidates[:TARGETED_POLISH_MAX_CANDIDATES]

    overlay_limit = int(style_limits.get("max_sentences") or 0)
    non_overlay_candidates = [
        candidate
        for candidate in candidates
        if not _is_targeted_voice_overlay_reason(str(candidate.get("reason") or ""))
    ]
    overlay_candidates = [
        candidate
        for candidate in candidates
        if _is_targeted_voice_overlay_reason(str(candidate.get("reason") or ""))
    ]
    mandatory_overlay_candidates = [
        candidate
        for candidate in overlay_candidates
        if _is_targeted_uncapped_style_reason(str(candidate.get("reason") or ""))
    ]
    capped_overlay_candidates = [
        candidate
        for candidate in overlay_candidates
        if not _is_targeted_uncapped_style_reason(str(candidate.get("reason") or ""))
    ]
    normalized_mode = str(style_polish_mode or "").strip().lower()
    if normalized_mode not in TARGETED_POLISH_JEONIM_RESERVED_SLOTS:
        normalized_mode = "light"
    jeonim_reserved = min(
        overlay_limit,
        int(TARGETED_POLISH_JEONIM_RESERVED_SLOTS.get(normalized_mode) or 0),
    )
    selected_capped_overlay_candidates: list[Dict[str, Any]] = []
    if overlay_limit > 0:
        jeonim_candidates = [
            candidate
            for candidate in capped_overlay_candidates
            if str(candidate.get("reason") or "").strip() == "jeonim_voice_overlay"
        ]
        selected_capped_overlay_candidates.extend(jeonim_candidates[:jeonim_reserved])
        remaining_overlay_slots = max(0, overlay_limit - len(selected_capped_overlay_candidates))
        for candidate in capped_overlay_candidates:
            if remaining_overlay_slots <= 0:
                break
            if candidate in selected_capped_overlay_candidates:
                continue
            selected_capped_overlay_candidates.append(candidate)
            remaining_overlay_slots -= 1

    selected_overlay_candidates = mandatory_overlay_candidates + selected_capped_overlay_candidates
    non_overlay_limit = max(0, TARGETED_POLISH_MAX_CANDIDATES - len(selected_overlay_candidates))
    selected = non_overlay_candidates[:non_overlay_limit] + selected_overlay_candidates
    selected.sort(
        key=lambda item: (
            -int(item.get("priority") or 0),
            int(item.get("blockIndex") or 0),
            int(item.get("sentenceIndex") or -1),
        )
    )
    return selected[:TARGETED_POLISH_MAX_CANDIDATES]


def _normalize_numeric_token(text: Any) -> str:
    return re.sub(r"[,\s]", "", str(text or "")).strip()


def _extract_targeted_polish_numeric_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in TARGETED_POLISH_NUMERIC_TOKEN_PATTERN.finditer(str(text or "")):
        token = _normalize_numeric_token(match.group(0) or "")
        if not token or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _validate_targeted_sentence_rewrite(
    original: str,
    rewritten: str,
    *,
    tag: str,
    user_keywords: list[str],
    known_names: list[str],
) -> tuple[bool, str]:
    source = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(original or "")))
    candidate = _normalize_inline_whitespace(str(rewritten or ""))
    if not source:
        return False, "empty_source"
    if not candidate:
        return False, "empty_output"
    if "<" in candidate or ">" in candidate:
        return False, "html_output"

    source_len = len(source)
    candidate_len = len(candidate)
    if candidate_len < max(6, int(source_len * 0.55)):
        return False, "too_short"
    if candidate_len > max(source_len + 40, int(source_len * 1.6)):
        return False, "too_long"
    if str(tag or "").lower() == "h2" and source.endswith("?") and not candidate.endswith("?"):
        return False, "question_lost"

    normalized_source = _normalize_person_name(source)
    normalized_candidate = _normalize_person_name(candidate)
    candidate_numeric_surface = _normalize_numeric_token(candidate)
    for token in _extract_targeted_polish_numeric_tokens(source):
        if token not in candidate_numeric_surface:
            return False, f"number_missing:{token}"

    for keyword in user_keywords or []:
        normalized_keyword = _normalize_inline_whitespace(keyword)
        if normalized_keyword and normalized_keyword in source and normalized_keyword not in candidate:
            return False, f"keyword_missing:{normalized_keyword}"

    for name in known_names or []:
        normalized_name = _normalize_person_name(name)
        if normalized_name and normalized_name in normalized_source and normalized_name not in normalized_candidate:
            return False, f"name_missing:{normalized_name}"

    return True, ""


def _apply_targeted_sentence_rewrites(
    content: str,
    candidates: list[Dict[str, Any]],
    rewrite_map: Dict[str, str],
    *,
    user_keywords: list[str],
    known_names: list[str],
    style_fingerprint: Optional[Dict[str, Any]] = None,
    style_polish_mode: str = "",
) -> Dict[str, Any]:
    base = str(content or "")
    style_rules = _extract_targeted_sentence_ai_alternative_rules(style_fingerprint)
    if not base.strip() or not candidates or (not rewrite_map and not style_rules):
        return {"content": base, "edited": False, "actions": []}

    block_updates: Dict[str, str] = {}
    block_positions: Dict[str, Dict[str, Any]] = {}
    actions: list[str] = []
    style_limits = _resolve_targeted_sentence_style_limits(style_polish_mode)
    style_limit = int(style_limits.get("max_sentences") or 0)
    style_applied_count = 0

    for candidate in candidates:
        candidate_id = str(candidate.get("id") or "").strip()
        candidate_reason = str(candidate.get("reason") or "").strip() or "generic"
        is_style_overlay = _is_targeted_voice_overlay_reason(candidate_reason)
        is_uncapped_style_overlay = _is_targeted_uncapped_style_reason(candidate_reason)
        if not candidate_id:
            continue

        if is_style_overlay and not is_uncapped_style_overlay and style_applied_count >= style_limit:
            actions.append(f"targeted_sentence_style_skip_cap:{candidate_id}:{candidate_reason}")
            continue

        block_key = str(candidate.get("blockKey") or "").strip()
        original_block_inner = str(candidate.get("blockInner") or "")
        if not block_key or not original_block_inner:
            continue

        current_inner = block_updates.get(block_key, original_block_inner)
        original_fragment = str(candidate.get("text") or "")

        def _apply_rewrite_to_block(rewritten_text: str) -> tuple[bool, str]:
            nonlocal style_applied_count
            valid_local, reason_local = _validate_targeted_sentence_rewrite(
                original_fragment,
                rewritten_text,
                tag=str(candidate.get("tag") or ""),
                user_keywords=user_keywords,
                known_names=known_names,
            )
            if not valid_local:
                return False, reason_local

            if str(candidate.get("tag") or "").lower() == "h2":
                updated_inner_local = rewritten_text
            else:
                updated_inner_local = current_inner.replace(original_fragment, rewritten_text, 1)
                if updated_inner_local == current_inner:
                    return False, "replace_miss"

            block_updates[block_key] = updated_inner_local
            block_positions[block_key] = {
                "innerStart": int(candidate.get("innerStart") or 0),
                "innerEnd": int(candidate.get("innerEnd") or 0),
                "originalInner": original_block_inner,
            }
            if is_style_overlay and not is_uncapped_style_overlay:
                style_applied_count += 1
            return True, ""

        matched_style_rules = candidate.get("styleRulePairs")
        if not isinstance(matched_style_rules, list) or not matched_style_rules:
            matched_style_rules = _find_targeted_sentence_ai_alternative_rules(original_fragment, style_rules)
        if is_style_overlay and isinstance(matched_style_rules, list) and matched_style_rules:
            rule_rewrite, applied_pairs = _apply_targeted_sentence_ai_alternative_rules(
                original_fragment,
                matched_style_rules,
            )
            if applied_pairs and rule_rewrite != _normalize_inline_whitespace(original_fragment):
                applied, apply_reason = _apply_rewrite_to_block(rule_rewrite)
                if applied:
                    pair_text = "|".join(f"{source}→{target}" for source, target in applied_pairs)
                    actions.append(
                        f"targeted_sentence_rule_apply:{candidate_id}:{pair_text}:{candidate_reason}"
                    )
                    continue
                actions.append(f"targeted_sentence_rule_skip:{candidate_id}:{apply_reason}")

        rewritten = _normalize_inline_whitespace(rewrite_map.get(candidate_id))
        if not rewritten:
            continue

        applied, apply_reason = _apply_rewrite_to_block(rewritten)
        if not applied:
            actions.append(f"targeted_sentence_llm_skip:{candidate_id}:{apply_reason}")
            continue

        actions.append(f"targeted_sentence_llm:{candidate_id}:{candidate_reason}")

    repaired = base
    for block_key, info in sorted(
        block_positions.items(),
        key=lambda item: int(item[1].get("innerStart") or 0),
        reverse=True,
    ):
        updated_inner = str(block_updates.get(block_key) or "")
        original_inner = str(info.get("originalInner") or "")
        if not updated_inner or updated_inner == original_inner:
            continue
        repaired = (
            repaired[: int(info.get("innerStart") or 0)]
            + updated_inner
            + repaired[int(info.get("innerEnd") or 0) :]
        )

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


def _rewrite_targeted_sentence_issues_once(
    content: str,
    *,
    user_keywords: Optional[list[str]] = None,
    known_names: Optional[list[str]] = None,
    style_guide: str = "",
    style_fingerprint: Optional[Dict[str, Any]] = None,
    style_polish_mode: str = "",
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    style_instruction = _build_targeted_sentence_style_instruction(
        style_guide=style_guide,
        style_fingerprint=style_fingerprint,
        mode=style_polish_mode,
    )
    candidates = _collect_targeted_sentence_polish_candidates(
        base,
        style_instruction=style_instruction,
        style_polish_mode=style_polish_mode,
        style_fingerprint=style_fingerprint,
    )
    if not candidates:
        return {"content": base, "edited": False, "actions": []}

    prompt_items = [
        {
            "id": str(candidate.get("id") or ""),
            "tag": str(candidate.get("tag") or ""),
            "reason": str(candidate.get("reason") or ""),
            "hint": str(candidate.get("hint") or ""),
            "text": str(candidate.get("text") or ""),
        }
        for candidate in candidates
    ]
    style_block = ""
    if style_instruction:
        style_block = f"\n[사용자 문체 반영 지침]\n{style_instruction}\n"
    prompt = (
        "당신은 한국어 정치 원고의 마지막 문장 단위 교정기입니다.\n"
        "아래 fragment만 최소 수정으로 자연스럽게 고치세요.\n"
        "규칙:\n"
        "1. 각 fragment는 하나의 소제목 또는 한 문장만 다룹니다.\n"
        "2. 사실, 정치적 입장, 고유명사, 직함, 수치, 날짜, 검색어를 유지하세요.\n"
        "3. 새 사실을 추가하거나 논지의 방향을 바꾸지 마세요.\n"
        "4. HTML 태그를 넣지 마세요.\n"
        "5. 가능한 한 조사, 어미, 문장 호흡, 상투 표현만 손보고 전체를 새로 쓰지 마세요.\n"
        "6. reason이 *_voice_overlay 계열이면 [사용자 문체 반영 지침]의 치환 규칙을 먼저 적용하세요.\n"
        "   - intro/closing: 비교적 적극적으로 다듬되 전체 재작성은 금지.\n"
        "   - transition/boilerplate/jeonim: 상투 구절과 어미만 치환, 내용은 그대로.\n"
        "7. id는 그대로 두고 text만 반환하세요.\n"
        f"{style_block}\n"
        f"입력 JSON:\n{json.dumps(prompt_items, ensure_ascii=False, indent=2)}\n\n"
        '반드시 다음 JSON만 반환하세요: {"rewrites":[{"id":"...","text":"..."}]}'
    )

    response_schema = {
        "type": "object",
        "properties": {
            "rewrites": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                    },
                    "required": ["id", "text"],
                },
            }
        },
        "required": ["rewrites"],
    }

    try:
        from agents.common.gemini_client import DEFAULT_MODEL, generate_json_async

        payload = _run_async_sync(
            generate_json_async(
                prompt,
                model_name=DEFAULT_MODEL,
                temperature=0.0,
                max_output_tokens=1024,
                retries=1,
                options={"json_parse_retries": 1},
                response_schema=response_schema,
                required_keys=("rewrites",),
            )
        )
    except Exception as exc:
        logger.warning("Targeted sentence polish skipped: %s", exc)
        return {
            "content": base,
            "edited": False,
            "actions": [
                f"targeted_sentence_candidates:{len(candidates)}",
                f"targeted_sentence_llm_error:{type(exc).__name__}",
            ],
        }

    rewrite_map: Dict[str, str] = {}
    rewrites = payload.get("rewrites") if isinstance(payload, dict) else None
    if isinstance(rewrites, list):
        for item in rewrites:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "").strip()
            item_text = _normalize_inline_whitespace(item.get("text"))
            if item_id and item_text:
                rewrite_map[item_id] = item_text

    apply_result = _apply_targeted_sentence_rewrites(
        base,
        candidates,
        rewrite_map,
        user_keywords=[str(item or "").strip() for item in (user_keywords or []) if str(item or "").strip()],
        known_names=[str(item or "").strip() for item in (known_names or []) if str(item or "").strip()],
        style_fingerprint=style_fingerprint,
        style_polish_mode=style_polish_mode,
    )
    actions = [f"targeted_sentence_candidates:{len(candidates)}"]
    if style_instruction:
        style_limits = _resolve_targeted_sentence_style_limits(style_polish_mode)
        style_candidate_count = sum(
            1
            for candidate in candidates
            if _is_targeted_voice_overlay_reason(str(candidate.get("reason") or ""))
        )
        boilerplate_candidate_count = sum(
            1 for candidate in candidates
            if str(candidate.get("reason") or "") in {"boilerplate_voice_overlay", "jeonim_voice_overlay"}
        )
        ai_alternative_candidate_count = sum(
            1
            for candidate in candidates
            if str(candidate.get("reason") or "") == "ai_alternative_voice_overlay"
        )
        actions.append(f"targeted_sentence_style_mode:{style_polish_mode or 'light'}")
        actions.append(f"targeted_sentence_style_cap:{int(style_limits.get('max_sentences') or 0)}")
        actions.append(f"targeted_sentence_style_candidates:{style_candidate_count}")
        actions.append(f"targeted_sentence_boilerplate_candidates:{boilerplate_candidate_count}")
        actions.append(f"targeted_sentence_ai_alternative_candidates:{ai_alternative_candidate_count}")
        for candidate in candidates:
            candidate_reason = str(candidate.get("reason") or "").strip()
            if not _is_targeted_voice_overlay_reason(candidate_reason):
                continue
            actions.append(
                f"targeted_sentence_style_selected:{str(candidate.get('id') or '').strip()}:{candidate_reason}"
            )
    apply_actions = apply_result.get("actions")
    if isinstance(apply_actions, list):
        for action in apply_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
        applied_count = sum(
            1
            for action in apply_actions
            if str(action).startswith("targeted_sentence_llm:")
            or str(action).startswith("targeted_sentence_rule_apply:")
        )
        actions.append(f"targeted_sentence_applied:{applied_count}")
    if style_instruction and isinstance(apply_actions, list):
        style_applied_count = sum(
            1
            for action in apply_actions
            if (
                str(action).startswith("targeted_sentence_llm:")
                or str(action).startswith("targeted_sentence_rule_apply:")
            )
            and _is_targeted_voice_overlay_reason(str(action).rsplit(":", 1)[-1])
        )
        actions.append(f"targeted_sentence_style_applied:{style_applied_count}")
    return {
        "content": str(apply_result.get("content") or base),
        "edited": bool(apply_result.get("edited")),
        "actions": actions,
    }


def _drop_incomplete_paragraph_tail_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    actions: list[str] = []
    replacements: list[tuple[int, int, str]] = []
    incomplete_tail_pattern = re.compile(
        r"([.!?])(\s*)([^.!?<>]{1,36})\s*$",
        re.IGNORECASE,
    )
    for match in PARAGRAPH_TAG_PATTERN.finditer(base):
        inner = str(match.group(1) or "")
        plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", inner))
        if (
            plain_inner
            and not any(plain_inner.endswith(ending) for ending in _COMPLETE_SENTENCE_ENDINGS)
            and any(plain_inner.endswith(ending) for ending in _INCOMPLETE_SENTENCE_ENDINGS)
            and len(_split_sentence_like_units(plain_inner)) <= 1
        ):
            replacements.append((match.start(), match.end(), ""))
            actions.append("drop_incomplete_single_sentence_paragraph")
            continue
        tail_match = incomplete_tail_pattern.search(inner)
        if not tail_match:
            continue
        fragment_raw = str(tail_match.group(3) or "")
        fragment_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", fragment_raw))
        if not fragment_plain or len(fragment_plain) > 30:
            continue
        if any(fragment_plain.endswith(ending) for ending in _COMPLETE_SENTENCE_ENDINGS):
            continue
        if not any(fragment_plain.endswith(ending) for ending in _INCOMPLETE_SENTENCE_ENDINGS):
            continue

        updated_inner = inner[:tail_match.start(3)].rstrip()
        if not updated_inner or updated_inner == inner:
            continue
        replacements.append((match.start(1), match.end(1), updated_inner))
        actions.append("drop_incomplete_paragraph_tail")

    if not replacements:
        return {
            "content": base,
            "edited": False,
            "actions": actions,
        }

    repaired = base
    for start, end, replacement in sorted(replacements, key=lambda item: -item[0]):
        repaired = repaired[:start] + replacement + repaired[end:]

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


def _looks_like_predicateless_fragment_sentence(text: Any) -> bool:
    plain = _normalize_inline_whitespace(text)
    if not plain:
        return False
    if any(plain.endswith(ending) for ending in _COMPLETE_SENTENCE_ENDINGS):
        return False
    if _PREDICATE_SURFACE_RE.search(plain):
        return False
    return bool(_PREDICATELESS_FRAGMENT_ENDING_RE.search(plain))


def _drop_predicateless_fragment_sentences_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    replacements: list[tuple[int, int, str]] = []
    removed_count = 0
    for match in PARAGRAPH_TAG_PATTERN.finditer(base):
        inner = str(match.group(1) or "")
        sentence_units = _split_sentence_like_units(_normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", inner)))
        if not sentence_units:
            continue
        kept_units: list[str] = []
        local_removed = 0
        for unit in sentence_units:
            if _looks_like_predicateless_fragment_sentence(unit):
                local_removed += 1
                removed_count += 1
                continue
            kept_units.append(unit)
        if local_removed == 0:
            continue
        if not kept_units:
            replacements.append((match.start(), match.end(), ""))
            continue
        rebuilt_inner = " ".join(kept_units).strip()
        replacements.append((match.start(1), match.end(1), rebuilt_inner))

    if not replacements:
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    for start, end, replacement in sorted(replacements, key=lambda item: -item[0]):
        repaired = repaired[:start] + replacement + repaired[end:]

    actions = [f"drop_predicateless_fragment_sentence:{removed_count}"] if removed_count > 0 else []
    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


def _count_poll_focus_token_hits(text: str, tokens: tuple[str, ...]) -> int:
    normalized = _normalize_inline_whitespace(text)
    if not normalized:
        return 0
    return sum(1 for token in tokens if token and token in normalized)


def _is_unsupported_comparison_sentence(
    text: str,
    *,
    opponent_names: list[str],
    poll_number_tokens: tuple[str, ...] = (),
) -> bool:
    """원문 소스에 없는 경쟁자 비교 문장인지 판단한다.

    opponent_names 중 하나를 포함하고, 1인칭 비교 표현이 있으나
    소스 수치(poll_number_tokens)가 없으면 unsupported 비교로 간주한다.
    """
    normalized = _normalize_inline_whitespace(text)
    if not normalized or len(normalized) < 10:
        return False
    if not any(name and name in normalized for name in opponent_names):
        return False
    if re.search(
        r"(?:과|와)\s+같은\s+[^.!?]{0,20}(?:인물|역할)|"
        r"(?:역할(?:들)?\s+또한\s+중요하게\s+논의|인물들의\s+역할)",
        normalized,
        re.IGNORECASE,
    ):
        return True
    has_first_person_comparison = (
        any(fp in normalized for fp in ("저는", "제가", "저의"))
        and bool(_UNSUPPORTED_COMPARISON_FIRST_PERSON_RE.search(normalized))
    )
    has_opponent_clause_comparison = bool(_UNSUPPORTED_COMPARISON_OPPONENT_CLAUSE_RE.search(normalized))
    if not has_first_person_comparison and not has_opponent_clause_comparison:
        return False
    if any(token and token in normalized for token in poll_number_tokens):
        return False
    return True


def _is_orphan_boilerplate_sentence(text: str) -> bool:
    """앞 근거 문장이 제거되면 의미를 잃는 고아 상투 문장인지 판단한다."""
    normalized = _normalize_inline_whitespace(text)
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _ORPHAN_BOILERPLATE_RE_LIST)


def _remove_groundedness_violations_from_section(
    section_html: str,
    *,
    opponent_names: list[str] = (),
    poll_number_tokens: tuple[str, ...] = (),
) -> Dict[str, Any]:
    """섹션 HTML에서 소스 없는 비교 문장과 고아 상투 문장을 제거한다."""
    base = str(section_html or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    opponent_names_clean = [s for s in (str(n or "").strip() for n in opponent_names) if s]
    poll_tokens_clean = tuple(s for s in (str(t or "").strip() for t in poll_number_tokens) if s)

    replacements: list[tuple[int, int, str]] = []
    for para_match in PARAGRAPH_TAG_PATTERN.finditer(base):
        inner = str(para_match.group(1) or "")
        if "<" in inner:
            continue
        plain_inner = _normalize_inline_whitespace(inner)
        if not plain_inner:
            continue

        sentences = _split_sentence_like_units(plain_inner)
        kept: list[str] = []
        for sentence in sentences:
            remove = False
            if opponent_names_clean:
                remove = _is_unsupported_comparison_sentence(
                    sentence,
                    opponent_names=opponent_names_clean,
                    poll_number_tokens=poll_tokens_clean,
                )
            if not remove:
                remove = _is_orphan_boilerplate_sentence(sentence)
            if not remove:
                kept.append(sentence)

        if len(kept) == len(sentences):
            continue

        new_inner = " ".join(kept).strip()
        if not new_inner:
            replacements.append((para_match.start(), para_match.end(), ""))
        else:
            replacements.append((para_match.start(1), para_match.end(1), new_inner))

    if not replacements:
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    for start, end, replacement in sorted(replacements, key=lambda x: -x[0]):
        repaired = repaired[:start] + replacement + repaired[end:]

    edited = repaired != base
    removed_count = len(replacements)
    actions: list[str] = [f"groundedness_removed:{removed_count}"] if edited else []
    return {"content": repaired, "edited": edited, "actions": actions}


def _rewrite_first_paragraph_with_answer_lead(
    section_html: str,
    answer_lead: str,
    *,
    replace_whole_paragraph: bool = False,
) -> Dict[str, Any]:
    base = str(section_html or "")
    lead = _normalize_inline_whitespace(answer_lead)
    if not base or not lead:
        return {"content": base, "edited": False}

    paragraph_match = PARAGRAPH_TAG_PATTERN.search(base)
    if not paragraph_match:
        return {"content": base, "edited": False}

    inner = str(paragraph_match.group(1) or "")
    plain_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", inner))
    if not plain_inner or plain_inner.startswith(lead):
        return {"content": base, "edited": False}

    if replace_whole_paragraph:
        updated_inner = lead
    else:
        sentences = _split_sentence_like_units(plain_inner)
        remainder = " ".join(sentences[1:]).strip() if len(sentences) > 1 else ""
        updated_inner = lead if not remainder else f"{lead} {remainder}"

    if not updated_inner or _normalize_inline_whitespace(updated_inner) == plain_inner:
        return {"content": base, "edited": False}

    updated = base[: paragraph_match.start(1)] + updated_inner + base[paragraph_match.end(1) :]
    return {"content": updated, "edited": updated != base}


def _build_heading_based_answer_lead(h2_plain: str, *, full_name: str = "") -> str:
    heading = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(h2_plain or "")))
    if not heading:
        return ""

    speaker_name = _clean_full_name_candidate(full_name)
    if not speaker_name:
        speaker_match = re.search(r"(?:지금\s*)?([가-힣]{2,4})(?:에게|에|의)?\s+주목", heading)
        if speaker_match:
            speaker_name = _clean_full_name_candidate(speaker_match.group(1))

    if "주목" in heading and "이유" in heading:
        target_name = speaker_name or "이 인물"
        possessive_name = f"{target_name}의" if not target_name.endswith("의") else target_name
        return (
            f"지금 {possessive_name} 가능성에 주목해야 하는 이유는 "
            "여론조사에서 확인된 경쟁력과 변화 요구가 함께 드러났기 때문입니다."
        )

    if "해법" in heading or "비전" in heading:
        return "해법은 지역 산업과 일자리 문제를 함께 풀 수 있는 실질적 정책에 있습니다."

    if ("앞선" in heading and "이유" in heading) or ("가상대결" in heading and "이유" in heading):
        return "가상대결에서는 확인 가능한 수치와 현장 경험이 함께 드러났습니다."

    return ""


def _ensure_nonempty_h2_sections_once(
    content: str,
    *,
    poll_focus_bundle: Optional[Dict[str, Any]] = None,
    full_name: str = "",
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    if not h2_matches:
        return {"content": base, "edited": False, "actions": []}

    bundle = poll_focus_bundle if isinstance(poll_focus_bundle, dict) else {}
    allowed_h2_kinds = bundle.get("allowedH2Kinds") if isinstance(bundle.get("allowedH2Kinds"), list) else []
    answer_leads: list[str] = []
    for raw_kind in allowed_h2_kinds:
        kind = raw_kind if isinstance(raw_kind, dict) else {}
        answer_lead = _normalize_inline_whitespace(kind.get("answerLead"))
        if answer_lead:
            answer_leads.append(answer_lead)

    replacements: list[tuple[int, int, str]] = []
    actions: list[str] = []
    for index, match in enumerate(h2_matches):
        section_start = match.end()
        section_end = h2_matches[index + 1].start() if index + 1 < len(h2_matches) else len(base)
        section_html = base[section_start:section_end]
        if PARAGRAPH_TAG_PATTERN.search(section_html):
            continue

        answer_lead = answer_leads[index] if index < len(answer_leads) else ""
        if not answer_lead and index == len(h2_matches) - 1 and answer_leads:
            answer_lead = answer_leads[-1]
        if not answer_lead:
            answer_lead = _build_heading_based_answer_lead(
                str(match.group(1) or ""),
                full_name=full_name,
            )
        if not answer_lead:
            replacements.append((match.start(), section_end, ""))
            actions.append(f"drop_empty_section:{index + 1}")
            continue

        insertion = f"\n<p>{answer_lead}</p>\n"
        replacements.append((section_start, section_start, insertion))
        actions.append(f"restore_empty_section_paragraph:{index + 1}")

    if not replacements:
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    for start, end, replacement in sorted(replacements, key=lambda item: -item[0]):
        repaired = repaired[:start] + replacement + repaired[end:]
    repaired = re.sub(r"\n{3,}", "\n\n", repaired).strip()
    return {"content": repaired, "edited": repaired != base, "actions": actions}


def _build_closing_support_sentence(heading: str, body_text: str, *, full_name: str = "") -> str:
    heading_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(heading or "")))
    body_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(body_text or "")))
    if not heading_plain:
        heading_plain = ""
    if not body_plain:
        body_plain = ""

    candidates: list[str] = []
    if "주목" in heading_plain or "이유" in heading_plain:
        candidates.append("남은 것은 확인된 경쟁력을 부산의 변화로 이어가는 실행입니다.")
    if "함께" in heading_plain:
        candidates.append("시민 여러분과 함께 약속한 변화를 생활의 결과로 보여드리겠습니다.")
    if "이뤄내" in heading_plain or "해내" in heading_plain:
        candidates.append("말보다 실행으로 결과를 증명하겠습니다.")
    if "해법" in heading_plain or "비전" in heading_plain:
        candidates.append("우선순위와 실행 순서를 분명히 제시해 체감할 변화를 만들겠습니다.")
    candidates.append("결국 중요한 것은 시민의 삶에서 확인되는 변화와 실행입니다.")

    normalized_body = body_plain.replace(" ", "")
    for candidate in candidates:
        normalized_candidate = candidate.replace(" ", "")
        if normalized_candidate and normalized_candidate not in normalized_body:
            return candidate
    return ""


def _build_generic_closing_answer_lead(heading: str, *, full_name: str = "") -> str:
    heading_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(heading or "")))
    if not heading_plain:
        return "결국 중요한 것은 약속을 실행으로 연결해 시민이 체감할 변화를 만드는 일입니다."

    if any(token in heading_plain for token in ("이뤄내", "해내", "완수", "약속")):
        return "이 약속은 시민의 삶에 남는 결과로 이어질 때 비로소 의미를 갖습니다."
    if any(token in heading_plain for token in ("대혁신", "혁신", "변화", "도약", "회복")):
        return "변화는 구호가 아니라 생활 속에서 확인되는 실행과 성과로 증명되어야 합니다."
    if "함께" in heading_plain:
        return "결론은 시민 여러분과 함께 약속한 변화를 현실의 성과로 만드는 일입니다."
    if "미래" in heading_plain:
        return "부산의 미래는 선언이 아니라 준비된 실행과 책임 있는 추진으로 만들어집니다."

    return "결국 중요한 것은 약속을 실행으로 연결해 시민이 체감할 변화를 만드는 일입니다."


def _select_conclusion_anchor(
    body_text: str,
    *,
    user_keywords: Optional[list[str]] = None,
    full_name: str = "",
) -> str:
    body_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(body_text or "")))
    compact_body = body_plain.replace(" ", "")
    ignored = {str(full_name or "").replace(" ", "")}
    for raw_keyword in user_keywords or []:
        keyword = _normalize_inline_whitespace(str(raw_keyword or "").strip(" \"'“”‘’"))
        compact_keyword = keyword.replace(" ", "")
        if len(compact_keyword) < 2 or len(compact_keyword) > 30:
            continue
        if compact_keyword in ignored:
            continue
        if compact_keyword and compact_keyword in compact_body:
            return keyword
    return "이 과제"


def _conclusion_archetype_key(writing_method: str) -> str:
    normalized = str(writing_method or "").strip()
    if normalized == "logical_writing":
        return "pledge"
    if normalized in {"critical_writing", "diagnostic_writing"}:
        return "diagnosis"
    if normalized == "analytical_writing":
        return "action"
    return ""


def _closing_section_needs_archetype_repair(
    paragraphs: list[str],
    *,
    section_plain: str,
    writing_method: str = "",
) -> bool:
    if not get_conclusion_archetype(str(writing_method or "").strip()):
        return False
    if len(paragraphs) < 3:
        return True
    body_plain = _normalize_inline_whitespace(section_plain)
    if len(body_plain) < 210:
        return True
    short_count = sum(1 for paragraph in paragraphs if len(paragraph) < 45)
    if short_count >= 2:
        return True
    predicateless_count = sum(
        1
        for paragraph in paragraphs
        if paragraph and not re.search(r"[.!?。！？]$", paragraph.strip())
    )
    if predicateless_count >= 1 and len(body_plain) < 260:
        return True
    last_plain = paragraphs[-1].strip() if paragraphs else ""
    if last_plain in {"감사합니다.", "감사합니다", "고맙습니다.", "고맙습니다"}:
        return True
    return False


def _build_conclusion_archetype_paragraphs(
    *,
    writing_method: str,
    heading: str,
    body_text: str,
    user_keywords: Optional[list[str]] = None,
    full_name: str = "",
) -> list[str]:
    anchor = _select_conclusion_anchor(
        body_text,
        user_keywords=user_keywords,
        full_name=full_name,
    )
    subject = anchor if anchor != "이 과제" else "이 과제"
    archetype_key = _conclusion_archetype_key(writing_method)

    if archetype_key == "diagnosis":
        return [
            f"{subject}이 보여주는 핵심 진단은 분명합니다. 시민의 부담을 개인에게 떠넘기는 방식으로는 생활의 불안을 줄일 수 없습니다.",
            "지금 필요한 것은 문제를 축소하는 행정이 아니라 원인과 책임을 분명히 보고, 실행 가능한 대안을 제도와 예산으로 연결하는 일입니다.",
            "저는 시민 여러분의 목소리를 끝까지 듣고 필요한 변화를 책임 있게 추진하겠습니다. 좋은 정치로 시민의 삶에 보답하겠습니다. 감사합니다.",
        ]
    if archetype_key == "action":
        return [
            f"{subject}은 현장에서 확인한 문제의식을 더 미룰 수 없다는 신호입니다. 생활의 변화는 구체적인 행동과 후속 조치로 증명되어야 합니다.",
            "저는 현장 의견 수렴, 조례와 예산 점검, 관계 기관 협의를 함께 추진해 실행 경로를 분명히 만들겠습니다.",
            "주민 여러분과 함께 끝까지 확인하고 부족한 부분은 빠르게 보완하겠습니다. 좋은 정치로 지역의 변화를 만들겠습니다. 감사합니다.",
        ]
    return [
        f"{subject}은 말로 끝낼 약속이 아니라 시민 생활에서 확인되어야 할 민생 과제입니다. 본론에서 확인한 문제를 실행의 결과로 연결하겠습니다.",
        "저는 조례, 예산, 현장 점검을 함께 묶어 추진 경로를 분명히 세우겠습니다. 과정과 결과를 시민께 투명하게 보고드리겠습니다.",
        "주민 여러분의 의견을 끝까지 듣고 필요한 보완은 빠르게 이어가겠습니다. 좋은 정치로 시민의 삶에 남는 변화를 만들겠습니다. 감사합니다.",
    ]


def _ensure_closing_section_min_sentences_once(
    content: str,
    *,
    full_name: str = "",
    writing_method: str = "",
    user_keywords: Optional[list[str]] = None,
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    if not h2_matches:
        return {"content": base, "edited": False, "actions": []}

    last_match = h2_matches[-1]
    section_start = last_match.end()
    section_end = len(base)
    section_html = base[section_start:section_end]
    heading_inner = str(last_match.group(1) or "").strip()
    paragraph_matches = list(PARAGRAPH_TAG_PATTERN.finditer(section_html))
    support_sentence = _build_closing_support_sentence(heading_inner, section_html, full_name=full_name)

    if not paragraph_matches:
        answer_lead = _build_heading_based_answer_lead(heading_inner, full_name=full_name)
        if not answer_lead:
            answer_lead = _build_generic_closing_answer_lead(heading_inner, full_name=full_name)
        fallback_sentences: list[str] = []
        for sentence in (answer_lead, support_sentence):
            normalized_sentence = _normalize_inline_whitespace(str(sentence or ""))
            if not normalized_sentence:
                continue
            if normalized_sentence not in fallback_sentences:
                fallback_sentences.append(normalized_sentence)
        if len(fallback_sentences) < 2:
            backup_sentence = _build_generic_closing_answer_lead(heading_inner, full_name=full_name)
            if backup_sentence and backup_sentence not in fallback_sentences:
                fallback_sentences.append(backup_sentence)
        if len(fallback_sentences) < 2:
            return {"content": base, "edited": False, "actions": []}
        insertion = f"\n<p>{' '.join(fallback_sentences[:2])}</p>\n"
        repaired = base[:section_start] + insertion + section_html + base[section_end:]
        return {
            "content": repaired,
            "edited": repaired != base,
            "actions": ["restore_closing_min_sentences:empty_section"],
        }

    paragraph_texts: list[str] = []
    total_sentences = 0
    for match in paragraph_matches:
        plain_inner = re.sub(r"<[^>]*>", " ", str(match.group(1) or ""))
        plain_inner = _normalize_inline_whitespace(plain_inner)
        if not plain_inner:
            continue
        paragraph_texts.append(plain_inner)
        total_sentences += len(_split_sentence_like_units(plain_inner))

    section_plain = _normalize_inline_whitespace(" ".join(paragraph_texts))
    if _closing_section_needs_archetype_repair(
        paragraph_texts,
        section_plain=section_plain,
        writing_method=writing_method,
    ):
        rebuilt_paragraphs = _build_conclusion_archetype_paragraphs(
            writing_method=writing_method,
            heading=heading_inner,
            body_text=base[: last_match.start()],
            user_keywords=user_keywords,
            full_name=full_name,
        )
        if len(rebuilt_paragraphs) >= 3:
            rebuilt_section_html = "\n" + "\n".join(f"<p>{paragraph}</p>" for paragraph in rebuilt_paragraphs[:3])
            repaired = base[:section_start] + rebuilt_section_html + base[section_end:]
            return {
                "content": repaired,
                "edited": repaired != base,
                "actions": [f"restore_closing_archetype:{_conclusion_archetype_key(writing_method)}"],
            }

    if total_sentences >= 2:
        return {"content": base, "edited": False, "actions": []}

    last_paragraph = paragraph_matches[-1]
    last_inner = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(last_paragraph.group(1) or "")))
    if not last_inner:
        return {"content": base, "edited": False, "actions": []}

    normalized_last_inner = last_inner.replace(" ", "")
    supplement_candidates: list[str] = []
    for candidate in (
        support_sentence,
        _build_generic_closing_answer_lead(heading_inner, full_name=full_name),
        "시민의 삶에서 먼저 달라지는 변화로 끝까지 증명하겠습니다.",
    ):
        normalized_candidate = _normalize_inline_whitespace(str(candidate or ""))
        if not normalized_candidate:
            continue
        compact_candidate = normalized_candidate.replace(" ", "")
        if compact_candidate in normalized_last_inner:
            continue
        if normalized_candidate in supplement_candidates:
            continue
        supplement_candidates.append(normalized_candidate)

    if not supplement_candidates:
        return {"content": base, "edited": False, "actions": []}

    needed = max(1, 2 - total_sentences)
    updated_inner = f"{last_inner} {' '.join(supplement_candidates[:needed])}".strip()
    repaired_section_html = (
        section_html[: last_paragraph.start(1)]
        + updated_inner
        + section_html[last_paragraph.end(1) :]
    )
    repaired = base[:section_start] + repaired_section_html + base[section_end:]
    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": ["restore_closing_min_sentences:append_sentence"],
    }


def _apply_final_sentence_polish_once(
    content: str,
    *,
    category: str = "",
    writing_method: str = "",
    full_name: str = "",
    user_keywords: Optional[list[str]] = None,
    role_facts: Optional[Dict[str, str]] = None,
    poll_fact_table: Optional[Dict[str, Any]] = None,
    poll_focus_bundle: Optional[Dict[str, Any]] = None,
    style_guide: str = "",
    style_fingerprint: Optional[Dict[str, Any]] = None,
    style_polish_mode: str = "",
) -> Dict[str, Any]:
    """최종 단계에서 문장 파손 가능성이 낮은 경량 윤문만 1회 적용한다."""
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    repaired = remove_grammatical_errors(base)
    actions: list[str] = []
    if repaired != base:
        actions.append("grammar_pattern_rewrite")

    repaired, story_effect_trimmed = _strip_self_analytical_story_effect_tail(repaired)
    if story_effect_trimmed > 0:
        actions.append(f"strip_self_analytical_story_effect_tail:{story_effect_trimmed}")

    if full_name:
        repaired, changed = re.subn(
            rf"저\s+{re.escape(full_name)}(?:은|는)\s*",
            "저는 ",
            repaired,
        )
        if changed > 0:
            actions.append(f"repair_named_first_person_subject:{changed}")

    repaired, changed = re.subn(
        r"(?:이번|이)\s+보고(?:를|서를)?\s+통해\s*",
        "",
        repaired,
        flags=re.IGNORECASE,
    )
    if changed > 0:
        actions.append(f"strip_report_framing:{changed}")

    safe_patterns: list[tuple[re.Pattern[str], str, str]] = [
        (
            re.compile(r"(?:오늘\s+)?이\s+자리에서\s*", re.IGNORECASE),
            "이 글에서 ",
            "speech_stage_framing",
        ),
        (
            re.compile(r"상세히\s+보고드리(?:며|고)\s*", re.IGNORECASE),
            "함께 말씀드리며 ",
            "speech_report_verb",
        ),
        (
            re.compile(r"선거까지\s+남은\s+결코\s+", re.IGNORECASE),
            "선거까지 남은 시간은 결코 ",
            "missing_subject_after_remaining",
        ),
        (
            re.compile(r"선거까지\s+남은\s+아직\s+", re.IGNORECASE),
            "선거까지 남은 시간은 아직 ",
            "missing_subject_after_remaining_alt",
        ),
        (
            re.compile(r"(\d)\.\s+(\d)"),
            r"\1.\2",
            "decimal_spacing",
        ),
        (
            re.compile(r"선거까지\s+아직\s*[,，]\s*", re.IGNORECASE),
            "선거까지 아직 시간이 남았지만, ",
            "dangling_clause_after_still",
        ),
        (
            re.compile(r"선거까지\s+남은\s*[,，]\s*", re.IGNORECASE),
            "선거까지 남은 시간 동안, ",
            "dangling_clause_after_remaining",
        ),
        (
            re.compile(r"에서\s+제가\s+결과(?:는|가)\s+", re.IGNORECASE),
            "에서 결과가 ",
            "broken_result_clause_after_i",
        ),
        (
            re.compile(
                r"((?:[가-힣]{1,8}\s*(?:의원|국회의원|시장|후보|위원장)?과의\s+)?"
                r"(?:가상대결|양자대결|대결))에서\s+(?:제가\s*)?여론조사\s+결과(?:는|가)\s+",
                re.IGNORECASE,
            ),
            r"\1의 여론조사 결과는 ",
            "broken_poll_result_clause_after_matchup",
        ),
        (
            re.compile(r"제가\s+결과(?:는|가)\s+", re.IGNORECASE),
            "결과가 ",
            "broken_result_clause",
        ),
        (
            re.compile(
                r"((?:상대 후보와의\s+)?(?:가상대결|양자대결|대결))에서\s+결과(?:는|가)\s+",
                re.IGNORECASE,
            ),
            r"\1 결과는 ",
            "broken_matchup_result_clause",
        ),
        (
            re.compile(
                r"((?:상대 후보와의\s+)?(?:가상 대결|양자 대결))에서\s+결과(?:는|가)\s+",
                re.IGNORECASE,
            ),
            r"\1 결과는 ",
            "broken_matchup_result_clause_spaced",
        ),
        (
            re.compile(
                r"(?:제가|저는)\s+(비전|해법|대안|경쟁력|가능성|약속|역할|메시지|방향|해결책)은\?",
                re.IGNORECASE,
            ),
            r"제 \1은?",
            "broken_heading_first_person_topic",
        ),
        (
            re.compile(
                r"미래\s+([가-힣]{1,2}\s+(?:의원|시장|후보|위원장))(?=\s*과의\s+(?:경쟁|대결|가상대결|양자대결))",
                re.IGNORECASE,
            ),
            r"향후 \1",
            "awkward_future_role_fragment",
        ),
        (
            re.compile(
                r"(?:[가-힣]{2,8}\s*(?:의원|국회의원|후보|시장|지사|위원장)?)\s*(?:과|와)\s*"
                r"비교(?:했(?:을\s*때|을때|을\s*땐|을땐|을\s*경우|을경우)?|하면|해보면)[,，]?\s*",
                re.IGNORECASE,
            ),
            "",
            "strip_direct_competitor_comparison_clause",
        ),
        (
            re.compile(r"진정성\s+있는", re.IGNORECASE),
            "직접적인",
            "strip_generic_sincerity_modifier",
        ),
        (
            re.compile(r"(?:저의\s+)?진정성과\s+전문성", re.IGNORECASE),
            "실력과 전문성",
            "strip_generic_sincerity_pair",
        ),
        (
            re.compile(r"부산의\s+부산경제", re.IGNORECASE),
            "부산경제",
            "dedupe_busan_branding_phrase",
        ),
        (
            re.compile(r"((?:부산항\s+)?부두\s+노동자의)\s+막내들", re.IGNORECASE),
            r"\1 자녀들",
            "repair_awkward_signature_plural",
        ),
        (
            re.compile(r"뼛속까지\s+부산사람들(?=(?:과|과 함께|과의|이))", re.IGNORECASE),
            "부산 사람들",
            "repair_identity_signature_plural_misuse",
        ),
        (
            re.compile(r"뼛속까지\s+부산사람들(?=의\s+삶)", re.IGNORECASE),
            "부산 시민들",
            "repair_identity_signature_possessive_misuse",
        ),
    ]
    for pattern, replacement, action_name in safe_patterns:
        repaired, changed = pattern.subn(replacement, repaired)
        if changed > 0:
            actions.append(f"{action_name}:{changed}")

    low_signal_repair = _drop_low_signal_analysis_sentences_once(repaired)
    low_signal_actions = low_signal_repair.get("actions")
    if isinstance(low_signal_actions, list):
        for action in low_signal_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if low_signal_repair.get("edited"):
        low_signal_content = low_signal_repair.get("content")
        repaired = str(low_signal_content if low_signal_content is not None else repaired)

    observer_frame_repair = _drop_observer_frame_sentences_once(repaired)
    observer_frame_actions = observer_frame_repair.get("actions")
    if isinstance(observer_frame_actions, list):
        for action in observer_frame_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if observer_frame_repair.get("edited"):
        repaired = str(observer_frame_repair.get("content") or repaired)

    section_opener_repair = _repair_contextless_section_openers_once(repaired)
    section_opener_actions = section_opener_repair.get("actions")
    if isinstance(section_opener_actions, list):
        for action in section_opener_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if section_opener_repair.get("edited"):
        repaired = str(section_opener_repair.get("content") or repaired)

    pre_section_dedupe = _dedupe_overlapping_sections_once(repaired)
    pre_section_dedupe_actions = pre_section_dedupe.get("actions")
    if isinstance(pre_section_dedupe_actions, list):
        for action in pre_section_dedupe_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if pre_section_dedupe.get("edited"):
        repaired = str(pre_section_dedupe.get("content") or repaired)

    known_person_names = _collect_known_person_names(
        full_name=full_name,
        role_facts=role_facts or {},
        user_keywords=user_keywords or [],
        poll_fact_table=poll_fact_table or {},
    )
    targeted_rewrite = _rewrite_targeted_sentence_issues_once(
        repaired,
        user_keywords=user_keywords or [],
        known_names=known_person_names,
        style_guide=style_guide,
        style_fingerprint=style_fingerprint,
        style_polish_mode=style_polish_mode,
    )
    targeted_actions = targeted_rewrite.get("actions")
    if isinstance(targeted_actions, list):
        for action in targeted_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if targeted_rewrite.get("edited"):
        repaired = str(targeted_rewrite.get("content") or repaired)

    final_style_scrub = _apply_global_style_ai_alternative_rules_once(
        repaired,
        style_fingerprint=style_fingerprint,
    )
    final_style_actions = final_style_scrub.get("actions")
    if isinstance(final_style_actions, list):
        for action in final_style_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if final_style_scrub.get("edited"):
        repaired = str(final_style_scrub.get("content") or repaired)

    post_section_dedupe = _dedupe_overlapping_sections_once(repaired)
    post_section_dedupe_actions = post_section_dedupe.get("actions")
    if isinstance(post_section_dedupe_actions, list):
        for action in post_section_dedupe_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if post_section_dedupe.get("edited"):
        repaired = str(post_section_dedupe.get("content") or repaired)

    closing_appeal_dedupe = _dedupe_closing_appeal_sentences_once(repaired)
    closing_appeal_actions = closing_appeal_dedupe.get("actions")
    if isinstance(closing_appeal_actions, list):
        for action in closing_appeal_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if closing_appeal_dedupe.get("edited"):
        repaired = str(closing_appeal_dedupe.get("content") or repaired)

    poll_dedupe = _dedupe_poll_explanation_sentences_once(repaired)
    poll_dedupe_actions = poll_dedupe.get("actions")
    if isinstance(poll_dedupe_actions, list):
        for action in poll_dedupe_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if poll_dedupe.get("edited"):
        repaired = str(poll_dedupe.get("content") or repaired)

    poll_reaction_cleanup = _drop_poll_reaction_interpretation_sentences_once(repaired)
    poll_reaction_actions = poll_reaction_cleanup.get("actions")
    if isinstance(poll_reaction_actions, list):
        for action in poll_reaction_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if poll_reaction_cleanup.get("edited"):
        repaired = str(poll_reaction_cleanup.get("content") or repaired)

    intro_body_dedupe = _dedupe_intro_body_overlap_sentences_once(repaired)
    intro_body_dedupe_actions = intro_body_dedupe.get("actions")
    if isinstance(intro_body_dedupe_actions, list):
        for action in intro_body_dedupe_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if intro_body_dedupe.get("edited"):
        repaired = str(intro_body_dedupe.get("content") or repaired)

    section_lane_repair = _apply_section_semantic_lane_repair_once(
        repaired,
        category=category,
    )
    section_lane_actions = section_lane_repair.get("actions")
    if isinstance(section_lane_actions, list):
        for action in section_lane_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if section_lane_repair.get("edited"):
        repaired = str(section_lane_repair.get("content") or repaired)

    cross_section_contract_repair = _apply_cross_section_contract_once(
        repaired,
        category=category,
        full_name=full_name,
    )
    cross_section_contract_actions = cross_section_contract_repair.get("actions")
    if isinstance(cross_section_contract_actions, list):
        for action in cross_section_contract_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if cross_section_contract_repair.get("edited"):
        repaired = str(cross_section_contract_repair.get("content") or repaired)

    career_dedupe = _dedupe_repeated_career_fact_sentences_once(repaired)
    career_dedupe_actions = career_dedupe.get("actions")
    if isinstance(career_dedupe_actions, list):
        for action in career_dedupe_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if career_dedupe.get("edited"):
        repaired = str(career_dedupe.get("content") or repaired)

    policy_evidence_dedupe = _dedupe_repeated_policy_evidence_sentences_once(repaired)
    policy_evidence_actions = policy_evidence_dedupe.get("actions")
    if isinstance(policy_evidence_actions, list):
        for action in policy_evidence_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if policy_evidence_dedupe.get("edited"):
        repaired = str(policy_evidence_dedupe.get("content") or repaired)

    policy_bundle_dedupe = _dedupe_repeated_policy_bundle_sentences_once(repaired)
    policy_bundle_actions = policy_bundle_dedupe.get("actions")
    if isinstance(policy_bundle_actions, list):
        for action in policy_bundle_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if policy_bundle_dedupe.get("edited"):
        repaired = str(policy_bundle_dedupe.get("content") or repaired)

    identity_signature_repair = _repair_identity_signature_exact_form_once(
        repaired,
        full_name=full_name,
    )
    identity_signature_actions = identity_signature_repair.get("actions")
    if isinstance(identity_signature_actions, list):
        for action in identity_signature_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if identity_signature_repair.get("edited"):
        identity_signature_content = identity_signature_repair.get("content")
        repaired = str(identity_signature_content if identity_signature_content is not None else repaired)

    identity_signature_insert = _ensure_identity_signature_present_once(
        repaired,
        full_name=full_name,
        style_fingerprint=style_fingerprint,
    )
    identity_signature_insert_actions = identity_signature_insert.get("actions")
    if isinstance(identity_signature_insert_actions, list):
        for action in identity_signature_insert_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if identity_signature_insert.get("edited"):
        identity_signature_insert_content = identity_signature_insert.get("content")
        repaired = str(identity_signature_insert_content if identity_signature_insert_content is not None else repaired)

    broken_fragment_scrub = _scrub_broken_poll_fragments_once(
        repaired,
        known_names=known_person_names,
    )
    broken_fragment_actions = broken_fragment_scrub.get("actions")
    if isinstance(broken_fragment_actions, list):
        for action in broken_fragment_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if broken_fragment_scrub.get("edited"):
        repaired = str(broken_fragment_scrub.get("content") or repaired)

    spacing_repair = _repair_terminal_sentence_spacing_once(repaired)
    spacing_actions = spacing_repair.get("actions")
    if isinstance(spacing_actions, list):
        for action in spacing_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if spacing_repair.get("edited"):
        repaired = str(spacing_repair.get("content") or repaired)

    completion_repair = _drop_incomplete_paragraph_tail_once(repaired)
    completion_actions = completion_repair.get("actions")
    if isinstance(completion_actions, list):
        for action in completion_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if completion_repair.get("edited"):
        completion_content = completion_repair.get("content")
        repaired = str(completion_content if completion_content is not None else repaired)

    predicateless_fragment_repair = _drop_predicateless_fragment_sentences_once(repaired)
    predicateless_fragment_actions = predicateless_fragment_repair.get("actions")
    if isinstance(predicateless_fragment_actions, list):
        for action in predicateless_fragment_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if predicateless_fragment_repair.get("edited"):
        predicateless_fragment_content = predicateless_fragment_repair.get("content")
        repaired = str(predicateless_fragment_content if predicateless_fragment_content is not None else repaired)

    closing_style_scrub = _apply_global_style_ai_alternative_rules_once(
        repaired,
        style_fingerprint=style_fingerprint,
    )
    closing_style_actions = closing_style_scrub.get("actions")
    if isinstance(closing_style_actions, list):
        for action in closing_style_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if closing_style_scrub.get("edited"):
        repaired = str(closing_style_scrub.get("content") or repaired)

    empty_section_repair = _ensure_nonempty_h2_sections_once(
        repaired,
        poll_focus_bundle=poll_focus_bundle,
        full_name=full_name,
    )
    empty_section_actions = empty_section_repair.get("actions")
    if isinstance(empty_section_actions, list):
        for action in empty_section_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if empty_section_repair.get("edited"):
        repaired = str(empty_section_repair.get("content") or repaired)

    closing_sentence_repair = _ensure_closing_section_min_sentences_once(
        repaired,
        full_name=full_name,
        writing_method=writing_method,
        user_keywords=user_keywords,
    )
    closing_sentence_actions = closing_sentence_repair.get("actions")
    if isinstance(closing_sentence_actions, list):
        for action in closing_sentence_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if closing_sentence_repair.get("edited"):
        repaired = str(closing_sentence_repair.get("content") or repaired)

    duplicate_particle_repaired = repair_duplicate_particles_and_tokens(repaired)
    if duplicate_particle_repaired != repaired:
        repaired = duplicate_particle_repaired
        actions.append("repair_duplicate_particles_and_tokens")

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


def _extract_tag_text(text: str, tag: str) -> str:
    if not text:
        return ""
    source = str(text or "").strip()
    if not source:
        return ""

    # Remove markdown code fences first.
    source = re.sub(r"```(?:xml|html|json)?\s*([\s\S]*?)\s*```", r"\1", source, flags=re.IGNORECASE).strip()

    def _normalize_payload(payload: str) -> str:
        cleaned = str(payload or "").strip()
        if not cleaned:
            return ""

        # Remove optional XML declaration.
        cleaned = re.sub(r"^\s*<\?xml[^>]*\?>\s*", "", cleaned, flags=re.IGNORECASE)

        # Unwrap CDATA wrappers repeatedly.
        cdata_pattern = re.compile(r"^\s*<!\[CDATA\[(.*)\]\]>\s*$", re.DOTALL)
        while True:
            m = cdata_pattern.match(cleaned)
            if not m:
                break
            cleaned = str(m.group(1) or "").strip()

        # Guard against leaked CDATA delimiters from malformed outputs.
        cleaned = cleaned.replace("<![CDATA[", "").replace("]]>", "").strip()
        return cleaned

    def _extract_from(raw: str) -> str:
        pattern = re.compile(rf"<{tag}\b[^>]*>([\s\S]*?)</{tag}>", re.IGNORECASE)
        matches = list(pattern.finditer(raw))
        for match in reversed(matches):
            candidate = _normalize_payload(match.group(1) or "")
            if not candidate:
                continue
            # Skip obvious placeholder echoes from prompt examples.
            plain = re.sub(r"<[^>]*>", " ", candidate)
            plain = re.sub(r"\s+", " ", plain).strip().lower()
            if "html 본문" in plain and len(plain) < 40:
                continue
            if plain in {"...", "…"}:
                continue
            return candidate
        return ""

    extracted = _extract_from(source)
    if extracted:
        return extracted

    # Retry once with HTML-unescaped text (&lt;content&gt;...).
    unescaped = html.unescape(source)
    if unescaped != source:
        extracted = _extract_from(unescaped)
        if extracted:
            return extracted

    return ""


def _extract_content_payload(text: str) -> str:
    source = str(text or "").strip()
    if not source:
        return ""

    extracted = _extract_tag_text(source, "content")
    if extracted:
        return extracted

    # JSON fallback: {"content": "..."}
    stripped = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", source, flags=re.IGNORECASE).strip()
    json_candidate = ""
    if stripped.startswith("{") and stripped.endswith("}"):
        json_candidate = stripped
    else:
        match = re.search(r"\{[\s\S]*\}", stripped)
        if match:
            json_candidate = match.group(0)
    if json_candidate:
        try:
            parsed = json.loads(json_candidate)
            if isinstance(parsed, dict):
                content_value = parsed.get("content")
                if isinstance(content_value, str):
                    return content_value.strip()
        except Exception:
            pass

    return ""


def _run_async_sync(coro, timeout_sec=45):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout_sec))
    except asyncio.TimeoutError:
        logger.warning("[_run_async_sync] timeout (%ds) 초과", timeout_sec)
        return None
    finally:
        try:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)


def _extract_title_focus_people(topic: str) -> list[str]:
    topic_text = str(topic or "").strip()
    if not topic_text:
        return []

    try:
        from agents.common.title_generation import _extract_topic_person_names

        people = [str(item or "").strip() for item in _extract_topic_person_names(topic_text)]
        return [name for name in people if name][:3]
    except Exception:
        pass

    generic_tokens = {
        "선거",
        "양자대결",
        "가상대결",
        "대결",
        "가능성",
        "경쟁력",
        "지지율",
        "부산시장",
        "서울시장",
        "시장",
        "지사",
        "교육감",
        "후보",
        "예비후보",
        "부산",
        "서울",
        "인천",
        "대구",
        "대전",
        "광주",
        "울산",
        "세종",
        "제주",
    }
    compact_topic = re.sub(r"\s+", "", topic_text)
    people: list[str] = []
    for token in re.findall(r"[가-힣]{2,4}", compact_topic):
        if token in generic_tokens or token in people:
            continue
        people.append(token)
        if len(people) >= 3:
            break
    return people


def _looks_like_title_party_support_block(text: str) -> bool:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain:
        return False
    if "정당 지지율" in plain or "지지정당 없음" in plain:
        return True

    party_tokens = ("더불어민주당", "민주당", "국민의힘", "조국혁신당", "개혁신당")
    contest_tokens = ("양자대결", "가상대결", "대결", "접전", "승부", "오차 범위")
    return "%" in plain and any(token in plain for token in party_tokens) and not any(
        token in plain for token in contest_tokens
    )


def _looks_like_title_branding_block(text: str, focus_people: Optional[list[str]] = None) -> bool:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain:
        return False

    compact = re.sub(r"\s+", "", plain)
    if re.search(r"[가-힣]{2,8}도충분히이깁니다", compact):
        return True
    if re.search(r"[가-힣]{2,8}경제는[가-힣]{2,8}(?:입니다)?", compact):
        return True
    if "조금씩확실히알려지고" in compact or "확실히알려지고있습니다" in compact:
        return True
    if focus_people and any(name in plain for name in focus_people):
        if any(token in plain for token in ("적임자", "희망찬 미래", "믿고 지지", "변화의 중심")):
            return True
    return False


def _build_title_focus_content(topic: str, content: str) -> str:
    base = str(content or "").strip()
    if not base:
        return ""

    blocks: list[Dict[str, Any]] = []
    for idx, match in enumerate(CONTENT_BLOCK_WITH_TAG_PATTERN.finditer(base)):
        full_block = str(match.group(0) or "")
        plain_block = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(match.group("inner") or "")))
        if not full_block or not plain_block:
            continue
        blocks.append(
            {
                "index": idx,
                "tag": str(match.group("tag") or "").lower(),
                "full": full_block,
                "plain": plain_block,
            }
        )
    if not blocks:
        return base

    focus_people = _extract_title_focus_people(topic)
    contest_tokens = ("양자대결", "가상대결", "대결", "접전", "승부", "오차 범위", "앞섰", "밀렸", "경쟁력")
    is_matchup_topic = len(focus_people) >= 2 and any(token in str(topic or "") for token in contest_tokens)

    if not is_matchup_topic:
        filtered_blocks = [
            block["full"]
            for block in blocks
            if not _looks_like_title_branding_block(str(block.get("plain") or ""), focus_people)
        ]
        return "".join(filtered_blocks[:6]) or base

    selected_indices: set[int] = set()
    for idx, block in enumerate(blocks):
        plain = str(block.get("plain") or "")
        if _looks_like_title_branding_block(plain, focus_people):
            continue
        if _looks_like_title_party_support_block(plain):
            continue

        name_hits = sum(1 for name in focus_people if name and name in plain)
        has_contest = any(token in plain for token in contest_tokens)
        has_percent = "%" in plain
        if name_hits >= 2 and (has_contest or has_percent):
            selected_indices.add(idx)
            if idx > 0 and str(blocks[idx - 1].get("tag") or "") == "h2":
                selected_indices.add(idx - 1)

    if not selected_indices:
        for idx, block in enumerate(blocks):
            plain = str(block.get("plain") or "")
            if _looks_like_title_branding_block(plain, focus_people):
                continue
            if _looks_like_title_party_support_block(plain):
                continue
            name_hits = sum(1 for name in focus_people if name and name in plain)
            if name_hits >= 1 and ("%" in plain or any(token in plain for token in contest_tokens)):
                selected_indices.add(idx)
                if idx > 0 and str(blocks[idx - 1].get("tag") or "") == "h2":
                    selected_indices.add(idx - 1)

    if selected_indices:
        expanded_indices = set(selected_indices)
        for idx in list(selected_indices):
            if str(blocks[idx].get("tag") or "") != "h2":
                continue
            next_idx = idx + 1
            if next_idx >= len(blocks):
                continue
            next_block = blocks[next_idx]
            next_plain = str(next_block.get("plain") or "")
            if str(next_block.get("tag") or "") != "p":
                continue
            if _looks_like_title_branding_block(next_plain, focus_people):
                continue
            if _looks_like_title_party_support_block(next_plain):
                continue
            if "%" in next_plain or any(name in next_plain for name in focus_people):
                expanded_indices.add(next_idx)

        ordered_indices = sorted(expanded_indices)[:6]
        focused = "".join(str(blocks[idx].get("full") or "") for idx in ordered_indices)
        if focused.strip():
            return focused

    fallback_blocks = [
        block["full"]
        for block in blocks
        if not _looks_like_title_branding_block(str(block.get("plain") or ""), focus_people)
        and not _looks_like_title_party_support_block(str(block.get("plain") or ""))
    ]
    return "".join(fallback_blocks[:4]) or base


def _looks_like_title_stance_meta_line(text: str) -> bool:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain:
        return False
    if any(token in plain for token in ("방송분", "앵커", "기자", "CG", "촬영", "편집", "입력", "수정")):
        return True
    if "뉴스" in plain and re.search(r"\d{1,2}시|\d{4}[./-]\d{1,2}[./-]\d{1,2}|\d{1,2}월\s*\d{1,2}일", plain):
        return True
    return False


def _looks_like_title_stance_branding_line(text: str, full_name: str = "") -> bool:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(text or "")))
    if not plain:
        return False

    compact = re.sub(r"\s+", "", plain)
    normalized_name = re.sub(r"\s+", "", str(full_name or ""))
    if normalized_name:
        if normalized_name in compact and re.search(rf"{re.escape(normalized_name)}도충분히이깁니다", compact):
            return True
        if normalized_name in compact and re.search(rf"[가-힣]{{2,8}}경제는{re.escape(normalized_name)}(?:입니다)?", compact):
            return True
    if re.search(r"[가-힣]{2,8}도충분히이깁니다", compact):
        return True
    if re.search(r"[가-힣]{2,8}경제는[가-힣]{2,8}(?:입니다)?", compact):
        return True
    if "조금씩확실히알려지고" in compact or "확실히알려지고있습니다" in compact:
        return True
    return False


def _build_title_stance_summary(
    context_analysis: Dict[str, Any],
    raw_stance_text: Any,
    *,
    full_name: str = "",
) -> str:
    collected: list[str] = []

    def _append(candidate: Any) -> None:
        plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(candidate or "")))
        plain = re.sub(r"^[*\-•]+\s*", "", plain).strip()
        if len(plain) < 6:
            return
        if looks_like_hashtag_bullet_line(plain):
            return
        if _looks_like_title_stance_meta_line(plain):
            return
        if _looks_like_title_stance_branding_line(plain, full_name=full_name):
            return
        if plain not in collected:
            collected.append(plain)

    if isinstance(context_analysis, dict):
        for item in list(context_analysis.get("mustIncludeFromStance") or []):
            _append(item)

    if not collected:
        raw_text = str(raw_stance_text or "")
        segments = re.split(r"[\r\n]+", raw_text)
        if len(segments) <= 1:
            segments = re.split(r"(?<=[.!?])\s+", raw_text)
        for segment in segments:
            _append(segment)

    return "\n".join(collected[:3])


def _normalize_recent_title_memory_values(values: Any) -> list[str]:
    titles: list[str] = []
    seen: set[str] = set()

    if not isinstance(values, list):
        return titles

    for raw_value in values:
        title = ""
        if isinstance(raw_value, dict):
            title = str(raw_value.get("title") or "").strip()
        else:
            title = str(raw_value or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        titles.append(title)
    return titles


def _collect_recent_title_memory(
    *,
    data: Dict[str, Any],
    pipeline_result: Dict[str, Any],
    session: Optional[Dict[str, Any]] = None,
    draft_title: str = "",
    limit: int = 8,
    include_current_titles: bool = True,
    seed_titles: Optional[list[str]] = None,
) -> list[str]:
    collected: list[str] = []
    seen: set[str] = set()

    def _append(title: str) -> None:
        normalized = str(title or "").strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        collected.append(normalized)

    if draft_title:
        _append(draft_title)

    for title in seed_titles or []:
        _append(title)
        if len(collected) >= limit:
            return collected[:limit]

    sources = (
        _safe_dict(session).get("recentTitles"),
        data.get("recentTitles"),
        data.get("previousTitles"),
        data.get("titleHistory"),
        pipeline_result.get("recentTitles"),
        pipeline_result.get("previousTitles"),
        pipeline_result.get("titleHistory"),
    )
    for source in sources:
        for title in _normalize_recent_title_memory_values(source):
            _append(title)
            if len(collected) >= limit:
                return collected[:limit]

    if include_current_titles:
        for source in (data.get("title"), pipeline_result.get("title")):
            _append(str(source or "").strip())
            if len(collected) >= limit:
                return collected[:limit]

    return collected[:limit]


def _normalize_session_title_memory_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _should_carry_recent_titles_from_prior_session(
    prior_session: Optional[Dict[str, Any]],
    *,
    topic: str,
    category: str,
) -> bool:
    session_data = _safe_dict(prior_session)
    recent_titles = _normalize_recent_title_memory_values(session_data.get("recentTitles"))
    if not recent_titles:
        return False

    previous_category = _normalize_session_title_memory_key(session_data.get("category"))
    current_category = _normalize_session_title_memory_key(category)
    if previous_category and current_category and previous_category != current_category:
        return False

    previous_topic = _normalize_session_title_memory_key(session_data.get("topic"))
    current_topic = _normalize_session_title_memory_key(topic)
    if previous_topic and current_topic and previous_topic != current_topic:
        return False

    return True


def _build_independent_final_title_context(
    *,
    topic: str,
    category: str,
    content: str,
    user_keywords: list[str],
    full_name: str,
    user_profile: Dict[str, Any],
    status: str,
    data: Dict[str, Any],
    pipeline_result: Dict[str, Any],
    context_analysis: Dict[str, Any],
    auto_keywords: Optional[list[str]] = None,
    recent_titles: Optional[list[str]] = None,
    poll_focus_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    focused_content = _build_title_focus_content(topic, content)
    stance_summary = _build_title_stance_summary(
        context_analysis,
        data.get("stanceText") or pipeline_result.get("stanceText") or "",
        full_name=full_name,
    )
    context: Dict[str, Any] = {
        "topic": str(topic or ""),
        "category": str(category or ""),
        "content": focused_content,
        "optimizedContent": focused_content,
        "userKeywords": list(user_keywords or []),
        "keywords": list(user_keywords or []),
        "analysis": {"keywords": list(auto_keywords or [])},
        "userProfile": user_profile if isinstance(user_profile, dict) else {},
        "author": {"name": str(full_name or "").strip()} if str(full_name or "").strip() else {},
        "status": str(status or ""),
        "background": data.get("background") or pipeline_result.get("background") or "",
        "instructions": data.get("instructions") or pipeline_result.get("instructions"),
        "contextAnalysis": context_analysis if isinstance(context_analysis, dict) else {},
        "pollFocusBundle": poll_focus_bundle if isinstance(poll_focus_bundle, dict) else {},
        "config": data.get("config") if isinstance(data.get("config"), dict) else {},
        "newsDataText": data.get("newsDataText") or pipeline_result.get("newsDataText") or "",
        "stanceText": stance_summary,
        "sourceInput": data.get("sourceInput") or pipeline_result.get("sourceInput") or "",
        "sourceContent": data.get("sourceContent") or pipeline_result.get("sourceContent") or "",
        "originalContent": data.get("originalContent") or pipeline_result.get("originalContent") or "",
    }
    normalized_recent_titles = _normalize_recent_title_memory_values(list(recent_titles or []))
    if normalized_recent_titles:
        context["recentTitles"] = normalized_recent_titles[:8]
    return context


def _generate_independent_final_title(
    *,
    topic: str,
    category: str,
    content: str,
    user_keywords: list[str],
    full_name: str,
    user_profile: Dict[str, Any],
    status: str,
    data: Dict[str, Any],
    pipeline_result: Dict[str, Any],
    context_analysis: Dict[str, Any],
    auto_keywords: Optional[list[str]] = None,
    recent_titles: Optional[list[str]] = None,
    poll_focus_bundle: Optional[Dict[str, Any]] = None,
    model_name: str = "",
) -> Dict[str, Any]:
    context = _build_independent_final_title_context(
        topic=topic,
        category=category,
        content=content,
        user_keywords=user_keywords,
        full_name=full_name,
        user_profile=user_profile,
        status=status,
        data=data,
        pipeline_result=pipeline_result,
        context_analysis=context_analysis,
        auto_keywords=auto_keywords,
        recent_titles=recent_titles,
        poll_focus_bundle=poll_focus_bundle,
    )
    try:
        from agents.core.title_agent import TitleAgent

        options: Dict[str, Any] = {}
        normalized_model_name = str(model_name or "").strip()
        if normalized_model_name:
            options["modelName"] = normalized_model_name
        # 차선 통과 허용 — 최종 제목 단계에서 min_score 미달이어도 하드 게이트
        # (length/role/bodyAnchorCoverage) 통과한 best_result 가 있다면
        # draft_title 로 silently rollback 하지 않고 그걸 받는다. anchor 가
        # 붙은 차선 제목이 anchor 가 없는 초안 제목보다 AEO 관점에서 낫다.
        options["allowDegradedPass"] = True
        title_agent = TitleAgent(options=options)
        result = _run_async_sync(title_agent.run(context))
        raw_title = str((result or {}).get("title") or "").strip()
        normalized_title = _normalize_title_surface_local(raw_title) or raw_title
        return {
            "title": normalized_title,
            "history": list((result or {}).get("titleHistory") or []),
            "score": _to_int((result or {}).get("titleScore"), 0),
            "type": str((result or {}).get("titleType") or "").strip(),
            "context": context,
        }
    except Exception as exc:
        logger.warning("Independent final title generation failed: %s", exc)
        return {
            "title": "",
            "history": [],
            "score": 0,
            "type": "",
            "error": str(exc),
            "context": context,
        }


def _recover_short_content_once(
    *,
    content: str,
    title: str,
    topic: str,
    min_required_chars: int,
    target_word_count: int,
    user_keywords: list[str],
    auto_keywords: list[str],
    body_min_overrides: Dict[str, int],
    user_keyword_expected_overrides: Dict[str, int],
    user_keyword_max_overrides: Dict[str, int],
    skip_user_keywords: Optional[list[str]],
    role_keyword_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """분량 부족 시 1회 확장 보정."""
    base_content = str(content or "").strip()
    base_len = _count_chars_no_space(base_content)
    if not base_content or base_len >= min_required_chars:
        return {"content": base_content, "edited": False}

    max_chars = max(int(target_word_count * 1.2), min_required_chars + 220)
    section_spec = _build_terminal_section_length_spec(target_word_count=target_word_count)
    sections = _split_into_sections(base_content)
    short_sections: list[str] = []
    for index, section in enumerate(sections, start=1):
        if not section.get("has_h2"):
            continue
        section_html = str(section.get("html") or "")
        current_len = _plain_len(section_html)
        effective_min = (
            min(int(section_spec.get("per_section_min") or 0), 130)
            if index == len(sections)
            else int(section_spec.get("per_section_min") or 0)
        )
        if current_len >= effective_min or effective_min <= 0:
            continue
        heading_text = _normalize_inline_whitespace(str(section.get("h2_text") or "")).strip()
        section_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", section_html))
        short_sections.append(
            f"""
    <section index="{index}" current_chars="{current_len}" min_chars="{effective_min}">
      <heading>{html.escape(heading_text or '(소제목 없음)')}</heading>
      <body><![CDATA[{section_plain[:280]}]]></body>
      <repair_focus>이 섹션을 읽은 독자가 '그래서 구체적으로 어떻게 할 건데?'라고 물을 지점을 찾아, 실행 방식이나 구체 근거를 드러내는 문장을 보강할 것</repair_focus>
    </section>
""".rstrip()
        )
    short_section_block = "\n".join(short_sections).strip()
    default_short_section_block = (
        "    <section index=\"0\"><repair_focus>짧은 h2 섹션이 특정되지 않으면 전체 흐름을 유지하며 "
        "가장 설명이 부족한 문단을 구체화할 것</repair_focus></section>"
    )
    prompt = f"""
<length_repair_prompt version="xml-v1">
  <role>당신은 한국어 정치 콘텐츠 편집자입니다. 본문 의미를 유지한 채 분량만 확장하세요.</role>
  <goal>
    <current_chars>{base_len}</current_chars>
    <min_chars>{min_required_chars}</min_chars>
    <max_chars>{max_chars}</max_chars>
  </goal>
  <rules>
    <rule order="1">핵심 주장/사실을 삭제하거나 왜곡하지 말 것.</rule>
    <rule order="2">허용 태그는 &lt;h2&gt;와 &lt;p&gt;만 사용.</rule>
    <rule order="3">같은 문장/같은 구문 반복으로 분량을 채우지 말 것.</rule>
    <rule order="4">행사 일시+장소 결합 문구는 2회를 넘기지 말 것.</rule>
    <rule order="5">키워드 과잉 삽입 금지.</rule>
    <rule order="6">가능하면 아래 short_sections에 표시된 섹션부터 보강하고, 각 섹션에서 독자가 '그래서 구체적으로 어떻게 할 건데?'라고 물을 지점을 직접 답하는 문장을 추가할 것.</rule>
    <rule order="7">어떤 후보나 어떤 선거에도 붙일 수 있는 일반 공약 문장으로 분량을 채우지 말 것.</rule>
    <rule order="8">소제목과 이미 있는 사실을 기준으로 실행 방식, 대상, 순서, 근거 중 빠진 정보를 보강할 것.</rule>
  </rules>
  <topic>{topic}</topic>
  <title>{title}</title>
  <keywords>{', '.join(user_keywords)}</keywords>
  <short_sections>
{short_section_block or default_short_section_block}
  </short_sections>
  <draft><![CDATA[{base_content}]]></draft>
  <output_contract>
    <format>XML</format>
    <allowed_tags>content</allowed_tags>
    <example><![CDATA[<content>...HTML 본문...</content>]]></example>
  </output_contract>
</length_repair_prompt>
""".strip()

    try:
        from agents.common.gemini_client import DEFAULT_MODEL, generate_content_async

        response_text = _run_async_sync(
            generate_content_async(
                prompt,
                model_name=DEFAULT_MODEL,
                temperature=0.0,
                max_output_tokens=8192,
            )
        )
    except Exception as exc:
        logger.warning("분량 자동 보정 호출 실패: %s", exc)
        return {"content": base_content, "edited": False, "error": str(exc)}

    candidate = _extract_content_payload(response_text)
    if not candidate:
        logger.warning("Length auto-repair parse failed: no <content> payload extracted")
        return {"content": base_content, "edited": False}

    candidate_len = _count_chars_no_space(candidate)
    if candidate_len <= base_len:
        return {"content": base_content, "edited": False}

    if candidate_len < min_required_chars:
        retry_sections = _split_into_sections(candidate)
        retry_short_sections: list[str] = []
        for index, section in enumerate(retry_sections, start=1):
            if not section.get("has_h2"):
                continue
            section_html = str(section.get("html") or "")
            current_len = _plain_len(section_html)
            effective_min = (
                min(int(section_spec.get("per_section_min") or 0), 130)
                if index == len(retry_sections)
                else int(section_spec.get("per_section_min") or 0)
            )
            if current_len >= effective_min or effective_min <= 0:
                continue
            heading_text = _normalize_inline_whitespace(str(section.get("h2_text") or "")).strip()
            section_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", section_html))
            retry_short_sections.append(
                f"""
    <section index="{index}" current_chars="{current_len}" min_chars="{effective_min}">
      <heading>{html.escape(heading_text or '(소제목 없음)')}</heading>
      <body><![CDATA[{section_plain[:280]}]]></body>
      <repair_focus>이 섹션에서 아직 빠진 실행 방식, 대상, 근거를 직접 보강할 것</repair_focus>
    </section>
""".rstrip()
            )
        retry_short_section_block = "\n".join(retry_short_sections).strip()
        retry_remaining_chars = max(0, min_required_chars - candidate_len)
        retry_prompt = prompt.replace(
            f"<current_chars>{base_len}</current_chars>",
            f"<current_chars>{candidate_len}</current_chars>",
            1,
        )
        retry_prompt = retry_prompt.replace(
            f"<short_sections>\n{short_section_block or default_short_section_block}\n  </short_sections>",
            f"<short_sections>\n{retry_short_section_block or default_short_section_block}\n  </short_sections>",
            1,
        )
        retry_prompt = retry_prompt.replace(
            "  </rules>",
            (
                "    <rule order=\"9\">retry_hint가 있으면 부족한 글자 수를 실제로 메우도록 짧은 섹션부터 한 문장 이상 더 보강할 것.</rule>\n"
                "  </rules>"
            ),
            1,
        )
        retry_prompt = retry_prompt.replace(
            f"<draft><![CDATA[{base_content}]]></draft>",
            (
                f"<retry_hint>현재 초안이 최소 분량보다 {retry_remaining_chars}자 부족합니다. "
                "이미 있는 문장을 축약하지 말고, 짧은 섹션부터 구체 문장을 더 보강하세요.</retry_hint>\n"
                f"  <draft><![CDATA[{candidate}]]></draft>"
            ),
            1,
        )
        try:
            from agents.common.gemini_client import DEFAULT_MODEL, generate_content_async

            retry_response_text = _run_async_sync(
                generate_content_async(
                    retry_prompt,
                    model_name=DEFAULT_MODEL,
                    temperature=0.0,
                    max_output_tokens=8192,
                )
            )
            retry_candidate = _extract_content_payload(retry_response_text)
            retry_len = _count_chars_no_space(retry_candidate) if retry_candidate else 0
            if retry_candidate and retry_len > candidate_len:
                candidate = retry_candidate
                candidate_len = retry_len
        except Exception as exc:
            logger.warning("분량 자동 보정 2차 호출 실패: %s", exc)

    keyword_repair = _repair_keyword_gate_once(
        content=candidate,
        title_text=title,
        user_keywords=user_keywords,
        auto_keywords=auto_keywords,
        target_word_count=target_word_count,
        body_min_overrides=body_min_overrides,
        user_keyword_expected_overrides=user_keyword_expected_overrides,
        user_keyword_max_overrides=user_keyword_max_overrides,
        skip_user_keywords=skip_user_keywords,
        role_keyword_policy=role_keyword_policy,
    )
    repaired_content = str(keyword_repair.get("content") or candidate)
    keyword_validation = _safe_dict(keyword_repair.get("keywordValidation"))
    keyword_counts = keyword_repair.get("keywordCounts")
    if not isinstance(keyword_counts, dict):
        keyword_counts = {}

    return {
        "content": repaired_content,
        "edited": repaired_content != base_content,
        "keywordValidation": keyword_validation,
        "keywordCounts": keyword_counts,
        "before": base_len,
        "after": _count_chars_no_space(repaired_content),
    }


def _rescore_seo(content: str, title: str, user_keywords: list) -> bool:
    """최종 본문 기준으로 SEO 통과 여부를 재판정한다.

    SEOAgent와 동일한 기준(키워드 밀도 + 구조 + 반복)을 적용하되,
    Orchestrator 호출 없이 인라인으로 실행한다.
    """
    plain = re.sub(r'<[^>]+>', ' ', content or '')

    # 1) 키워드 밀도
    kw_count = len(user_keywords) if user_keywords else 0
    if kw_count >= 2:
        kw_min = int(KEYWORD_SPEC['perKeywordMin'])
        kw_max = int(KEYWORD_SPEC['perKeywordMax'])
    elif kw_count == 1:
        kw_min = int(KEYWORD_SPEC['singleKeywordMin'])
        kw_max = int(KEYWORD_SPEC['singleKeywordMax'])
    else:
        kw_min, kw_max = 0, 999

    kw_ok = True
    for kw in (user_keywords or []):
        cnt = plain.count(kw)
        if cnt < kw_min or cnt > kw_max:
            kw_ok = False
            break

    # 2) 구조 (H2 ≥ 2)
    h2_count = len(re.findall(r'<h2', content or '', re.IGNORECASE))
    struct_ok = h2_count >= 2

    # 3) 반복 문장
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', re.sub(r'\s+', ' ', plain).strip()) if len(s.strip()) > 20]
    seen: set[str] = set()
    has_repeat = False
    for s in sentences:
        norm = re.sub(r'\s+', '', s).lower()
        if norm in seen:
            has_repeat = True
            break
        seen.add(norm)

    return kw_ok and struct_ok and not has_repeat


def _repair_keyword_gate_once(
    *,
    content: str,
    title_text: str,
    user_keywords: list[str],
    auto_keywords: list[str],
    target_word_count: int,
    body_min_overrides: Dict[str, int],
    user_keyword_expected_overrides: Dict[str, int],
    user_keyword_max_overrides: Dict[str, int],
    skip_user_keywords: Optional[list[str]] = None,
    role_keyword_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """키워드 게이트 실패(부족/과다)를 1회 자동 보정한다."""
    base_content = str(content or "")
    pre_validation = validate_keyword_insertion(
        base_content,
        user_keywords=user_keywords,
        auto_keywords=auto_keywords,
        target_word_count=target_word_count,
        title_text=title_text,
        body_min_overrides=body_min_overrides,
        user_keyword_expected_overrides=user_keyword_expected_overrides,
        user_keyword_max_overrides=user_keyword_max_overrides,
    )
    pre_keyword_validation = build_keyword_validation(pre_validation)
    logger.info(
        "Keyword gate repair snapshot: preview=%s states=%s",
        _content_log_preview(base_content),
        _keyword_gate_log_summary(pre_keyword_validation, list(user_keywords or [])),
    )
    enforcement = enforce_keyword_requirements(
        base_content,
        user_keywords=user_keywords,
        auto_keywords=auto_keywords,
        target_word_count=target_word_count,
        title_text=title_text,
        body_min_overrides=body_min_overrides,
        user_keyword_expected_overrides=user_keyword_expected_overrides,
        user_keyword_max_overrides=user_keyword_max_overrides,
        skip_user_keywords=skip_user_keywords,
        role_keyword_policy=role_keyword_policy,
        max_iterations=2,
    )

    repaired_content = str(enforcement.get("content") or base_content)
    _warn_if_no_space_compound(repaired_content, "keyword_gate_repair")
    keyword_result = enforcement.get("keywordResult")
    if not isinstance(keyword_result, dict):
        keyword_result = validate_keyword_insertion(
            repaired_content,
            user_keywords=user_keywords,
            auto_keywords=auto_keywords,
            target_word_count=target_word_count,
            title_text=title_text,
            body_min_overrides=body_min_overrides,
            user_keyword_expected_overrides=user_keyword_expected_overrides,
            user_keyword_max_overrides=user_keyword_max_overrides,
        )

    keyword_validation = build_keyword_validation(keyword_result)
    keyword_details = (keyword_result.get("details") or {}).get("keywords") or {}
    keyword_counts = {
        keyword: int((info or {}).get("gateCount") or (info or {}).get("coverage") or (info or {}).get("count") or 0)
        for keyword, info in keyword_details.items()
        if isinstance(info, dict)
    }
    reductions = enforcement.get("reductions") if isinstance(enforcement.get("reductions"), list) else []
    logger.info(
        "Keyword gate repair result: edited=%s preview=%s states=%s",
        repaired_content != base_content,
        _content_log_preview(repaired_content),
        _keyword_gate_log_summary(keyword_validation, list(user_keywords or [])),
    )

    return {
        "content": repaired_content,
        "keywordValidation": keyword_validation,
        "keywordCounts": keyword_counts,
        "edited": repaired_content != base_content,
        "reductions": reductions,
    }


def _extract_repetition_gate_issues(heuristic_result: Dict[str, Any]) -> list[str]:
    issues = heuristic_result.get("issues") if isinstance(heuristic_result, dict) else []
    if not isinstance(issues, list):
        return []
    repetition_keywords = ("문장 반복 감지", "구문 반복 감지", "유사 문장 감지")
    return [
        str(item).strip()
        for item in issues
        if isinstance(item, str) and any(keyword in item for keyword in repetition_keywords)
    ]


def _extract_legal_gate_issues(heuristic_result: Dict[str, Any]) -> list[str]:
    issues = heuristic_result.get("issues") if isinstance(heuristic_result, dict) else []
    if not isinstance(issues, list):
        return []
    legal_keywords = ("선거법 위반",)
    return [
        str(item).strip()
        for item in issues
        if isinstance(item, str) and any(keyword in item for keyword in legal_keywords)
    ]


def _extract_legal_gate_items(heuristic_result: Dict[str, Any]) -> list[Dict[str, Any]]:
    if not isinstance(heuristic_result, dict):
        return []
    details = heuristic_result.get("details")
    if not isinstance(details, dict):
        return []
    election_law = details.get("electionLaw")
    if not isinstance(election_law, dict):
        return []
    items = election_law.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _format_legal_gate_item(item: Dict[str, Any]) -> str:
    reason = str(item.get("reason") or "선거법 위반 위험").strip()
    sentence = str(item.get("sentence") or "").strip()
    matched_text = str(item.get("matchedText") or "").strip()
    repair_hint = str(item.get("repairHint") or "").strip()

    parts = [reason]
    if sentence:
        parts.append(f'문제 문장: "{sentence}"')
    if matched_text:
        parts.append(f'문제 표현: "{matched_text}"')
    if repair_hint:
        parts.append(f"수정 가이드: {repair_hint}")
    return " | ".join(parts)


def _extract_legal_gate_issue_summaries(heuristic_result: Dict[str, Any]) -> list[str]:
    items = _extract_legal_gate_items(heuristic_result)
    if items:
        return [_format_legal_gate_item(item) for item in items]
    return _extract_legal_gate_issues(heuristic_result)


def _append_quality_warning(warnings: list[str], message: str) -> None:
    text = str(message or "").strip()
    if not text:
        return
    if text not in warnings:
        warnings.append(text)


def _detect_content_repair_corruption(before: str, after: str) -> tuple[bool, str]:
    before_text = str(before or "")
    after_text = str(after or "")
    if not after_text.strip():
        return True, "empty_output"

    before_len = _count_chars_no_space(before_text)
    after_len = _count_chars_no_space(after_text)
    if before_len >= 1200 and after_len < int(before_len * 0.78):
        return True, f"length_drop:{before_len}->{after_len}"

    suspicious_tokens = ("이 사안", "관련 현안")
    before_hits = sum(before_text.count(token) for token in suspicious_tokens)
    after_hits = sum(after_text.count(token) for token in suspicious_tokens)
    if after_hits >= max(3, before_hits + 2):
        return True, f"suspicious_token_spike:{before_hits}->{after_hits}"

    return False, ""


def _build_editor_keyword_feedback(
    keyword_validation: Dict[str, Any],
    gate_user_keywords: list[str],
) -> Dict[str, Any]:
    normalized_user_keywords = [str(item).strip() for item in (gate_user_keywords or []) if str(item).strip()]
    if not normalized_user_keywords:
        return {"passed": True, "issues": [], "softIssues": []}

    hard_issues: list[str] = []
    soft_issues: list[str] = []
    for index, keyword in enumerate(normalized_user_keywords):
        info = keyword_validation.get(keyword) if isinstance(keyword_validation, dict) else None
        if not isinstance(info, dict):
            if index == 0:
                hard_issues.append(f"키워드 \"{keyword}\" 검증 정보가 없습니다.")
            else:
                soft_issues.append(f"보조 키워드 \"{keyword}\" 검증 정보가 없습니다.")
            continue

        status = str(info.get("status") or "").strip().lower()
        count = _to_int(info.get("gateCount"), _to_int(info.get("count"), 0))
        expected = _to_int(info.get("expected"), 0)
        max_count = _to_int(info.get("max"), 0)
        exact_count = _to_int(info.get("exclusiveCount"), count)
        if status == "insufficient":
            message = f"키워드 \"{keyword}\"가 부족합니다 ({count}/{expected})."
            if index == 0:
                hard_issues.append(message)
            else:
                soft_issues.append(f"보조 {message}")
        elif status == "spam_risk":
            message = f"키워드 \"{keyword}\"가 과다합니다 ({exact_count}/{max_count})."
            if index == 0:
                hard_issues.append(message)
            else:
                soft_issues.append(f"보조 {message}")

    return {"passed": len(hard_issues) == 0, "issues": hard_issues, "softIssues": soft_issues}


def _score_title_compliance(
    *,
    title: str,
    topic: str,
    content: str,
    user_keywords: list[str],
    full_name: str,
    category: str,
    status: str,
    context_analysis: Dict[str, Any],
    role_keyword_policy: Optional[Dict[str, Any]] = None,
    poll_focus_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    candidate = _normalize_title_surface_local(title)
    if not candidate:
        return {"passed": False, "score": 0, "reason": "empty", "title": ""}
    try:
        from agents.common.title_generation import calculate_title_quality_score

        result = calculate_title_quality_score(
            candidate,
            {
                "topic": str(topic or ""),
                "contentPreview": str(content or ""),
                "userKeywords": list(user_keywords or []),
                "fullName": str(full_name or ""),
                "category": str(category or ""),
                "status": str(status or ""),
                "contextAnalysis": context_analysis if isinstance(context_analysis, dict) else {},
                "roleKeywordPolicy": role_keyword_policy if isinstance(role_keyword_policy, dict) else {},
                "pollFocusBundle": poll_focus_bundle if isinstance(poll_focus_bundle, dict) else {},
            },
        )
        if isinstance(result, dict):
            repaired_title = str(result.get("repairedTitle") or "").strip()
            if repaired_title and repaired_title != candidate and not bool(result.get("passed") is True):
                repaired_result = calculate_title_quality_score(
                    repaired_title,
                    {
                        "topic": str(topic or ""),
                        "contentPreview": str(content or ""),
                        "userKeywords": list(user_keywords or []),
                        "fullName": str(full_name or ""),
                        "category": str(category or ""),
                        "status": str(status or ""),
                        "contextAnalysis": context_analysis if isinstance(context_analysis, dict) else {},
                        "roleKeywordPolicy": role_keyword_policy if isinstance(role_keyword_policy, dict) else {},
                        "pollFocusBundle": poll_focus_bundle if isinstance(poll_focus_bundle, dict) else {},
                    },
                )
                if (
                    isinstance(repaired_result, dict)
                    and (
                        repaired_result.get("passed") is True
                        or _to_int(repaired_result.get("score"), 0) > _to_int(result.get("score"), 0)
                    )
                ):
                    result = dict(repaired_result)
                    result["repairedTitle"] = repaired_title
        repaired_title = ""
        if isinstance(result, dict):
            repaired_title = str(result.get("repairedTitle") or "").strip()
        final_title = candidate
        if repaired_title:
            final_title = _normalize_title_surface_local(repaired_title) or repaired_title or candidate
        score = _to_int(result.get("score"), 0) if isinstance(result, dict) else 0
        strict_pass = bool(result.get("passed") is True) if isinstance(result, dict) else False
        breakdown = result.get("breakdown") if isinstance(result, dict) else {}
        topic_match = breakdown.get("topicMatch") if isinstance(breakdown, dict) else {}
        keyword_requirement = breakdown.get("keywordRequirement") if isinstance(breakdown, dict) else {}
        length_info = breakdown.get("length") if isinstance(breakdown, dict) else {}
        topic_match_score = _to_int(
            topic_match.get("score") if isinstance(topic_match, dict) else 0,
            0,
        )
        keyword_requirement_score = _to_int(
            keyword_requirement.get("score") if isinstance(keyword_requirement, dict) else 0,
            0,
        )
        length_score = _to_int(
            length_info.get("score") if isinstance(length_info, dict) else 0,
            0,
        )
        soft_acceptable = (
            score >= 60
            and topic_match_score >= 15
            and keyword_requirement_score > 0
            and length_score > 0
        )
        # 최종 출력 가드는 하드 실패(score=0)만 차단한다.
        # 점수 70 미만의 소프트 이슈는 경고로 남기고 제목 생성은 계속 진행한다.
        passed = strict_pass
        suggestions = result.get("suggestions") if isinstance(result, dict) else []
        reason = ""
        if isinstance(suggestions, list) and suggestions:
            reason = str(suggestions[0] or "").strip()
        return {
            "passed": passed,
            "score": score,
            "reason": reason,
            "title": final_title,
            "strictPassed": strict_pass,
            "softAccepted": soft_acceptable,
            "topicMatchScore": topic_match_score,
            "keywordRequirementScore": keyword_requirement_score,
            "lengthScore": length_score,
        }
    except Exception as exc:
        logger.warning("Title compliance scoring failed (non-fatal): %s", exc)
        return {
            "passed": False,
            "score": 0,
            "reason": "scoring_error",
            "title": candidate,
            "strictPassed": False,
            "softAccepted": False,
            "topicMatchScore": 0,
            "keywordRequirementScore": 0,
            "lengthScore": 0,
        }


def _guard_title_after_editor(
    *,
    candidate_title: str,
    previous_title: str,
    topic: str,
    content: str,
    user_keywords: list[str],
    full_name: str,
    category: str,
    status: str,
    context_analysis: Dict[str, Any],
    role_keyword_policy: Optional[Dict[str, Any]] = None,
    poll_focus_bundle: Optional[Dict[str, Any]] = None,
    recent_titles: Optional[list[str]] = None,
) -> tuple[str, Dict[str, Any]]:
    candidate = _normalize_title_surface_local(candidate_title)
    previous = _normalize_title_surface_local(previous_title)

    def _compose_repaired_title_surface(base_title: str, start: int, end: int, replacement: str) -> str:
        prefix = str(base_title[:start] or "").rstrip(" ,·:;!?")
        suffix = re.sub(r"^[\s,·:;!?]+", "", str(base_title[end:] or ""))
        anchor_like_replacement = bool(re.search(r"(?:출마론|거론|출마 가능성|거론 속|구도)$", str(replacement or "").strip()))
        if anchor_like_replacement and suffix:
            candidate_surface = (
                f"{prefix} {replacement}, {suffix}".strip()
                if prefix else
                f"{replacement}, {suffix}".strip()
            )
            return _normalize_title_surface_local(candidate_surface) or candidate_surface
        parts = [part for part in (prefix, str(replacement or "").strip(), suffix) if str(part or "").strip()]
        candidate_surface = " ".join(parts).strip()
        return _normalize_title_surface_local(candidate_surface) or candidate_surface

    def _iter_role_policy_repair_candidates(title_text: str) -> list[str]:
        normalized_title = _normalize_title_surface_local(title_text)
        entries = role_keyword_policy.get("entries") if isinstance(role_keyword_policy, dict) else {}
        if not normalized_title or not isinstance(entries, dict) or not entries:
            return []

        candidates: list[str] = []
        seen_candidates: set[str] = set()
        for keyword, raw_entry in entries.items():
            entry = raw_entry if isinstance(raw_entry, dict) else {}
            normalized_keyword = str(keyword or "").strip()
            if not normalized_keyword or normalized_keyword not in normalized_title:
                continue
            start_index = normalized_title.find(normalized_keyword)
            end_index = start_index + len(normalized_keyword)
            mode = str(entry.get("mode") or "").strip().lower()

            replacements: list[str] = []
            if mode == "intent_only" and not is_role_keyword_intent_surface(
                normalized_title,
                start_index,
                end_index,
            ):
                replacements = order_role_keyword_intent_anchor_candidates(
                    normalized_keyword,
                    _normalize_recent_title_memory_values(recent_titles or []),
                ) or [build_role_keyword_intent_anchor_text(normalized_keyword, variant_index=0)]
            elif mode == "blocked":
                if bool(entry.get("allowTitleIntentAnchor")) and not is_role_keyword_intent_surface(
                    normalized_title,
                    start_index,
                    end_index,
                ):
                    replacements = order_role_keyword_intent_anchor_candidates(
                        normalized_keyword,
                        _normalize_recent_title_memory_values(recent_titles or []),
                    ) or [build_role_keyword_intent_anchor_text(normalized_keyword, variant_index=0)]
                elif not bool(entry.get("allowTitleIntentAnchor")):
                    source_role = str(entry.get("sourceRole") or "").strip()
                    person_name = str(entry.get("name") or "").strip()
                    if source_role and person_name:
                        replacements = [f"{person_name} {source_role}", person_name]
                    elif person_name:
                        replacements = [person_name]

            for replacement in replacements:
                repaired_candidate = _compose_repaired_title_surface(
                    normalized_title,
                    start_index,
                    end_index,
                    replacement,
                )
                if not repaired_candidate or repaired_candidate == normalized_title or repaired_candidate in seen_candidates:
                    continue
                seen_candidates.add(repaired_candidate)
                candidates.append(repaired_candidate)
        return candidates

    def _try_role_policy_title_repair(title_text: str, source_label: str, failed_reason: str) -> Optional[tuple[str, Dict[str, Any]]]:
        best_soft: Optional[tuple[str, Dict[str, Any]]] = None
        for repaired_candidate in _iter_role_policy_repair_candidates(title_text):
            repaired_score = _score_title_compliance(
                title=repaired_candidate,
                topic=topic,
                content=content,
                user_keywords=user_keywords,
                full_name=full_name,
                category=category,
                status=status,
                context_analysis=context_analysis,
                role_keyword_policy=role_keyword_policy,
                poll_focus_bundle=poll_focus_bundle,
            )
            repaired_title = (
                _normalize_title_surface_local(str(repaired_score.get("title") or repaired_candidate))
                or repaired_candidate
            )
            if repaired_score.get("passed"):
                return repaired_title, {
                    "accepted": True,
                    "source": f"{source_label}_role_policy_repair",
                    "score": repaired_score.get("score"),
                    "reason": failed_reason or repaired_score.get("reason"),
                    "repaired": True,
                }
            if repaired_score.get("softAccepted"):
                best_soft = (
                    repaired_title,
                    {
                        "accepted": True,
                        "source": f"{source_label}_role_policy_repair_soft",
                        "score": repaired_score.get("score"),
                        "reason": failed_reason or repaired_score.get("reason"),
                        "repaired": True,
                    },
                )
        return best_soft

    candidate_score = _score_title_compliance(
        title=candidate,
        topic=topic,
        content=content,
        user_keywords=user_keywords,
        full_name=full_name,
        category=category,
        status=status,
        context_analysis=context_analysis,
        role_keyword_policy=role_keyword_policy,
        poll_focus_bundle=poll_focus_bundle,
    )
    scored_title = (
        _normalize_title_surface_local(str(candidate_score.get("title") or candidate))
        or candidate
    )
    if candidate_score.get("passed"):
        repaired = scored_title != candidate
        if repaired:
            logger.info(
                "Title guard auto-repaired candidate title: \"%s\" -> \"%s\"",
                candidate,
                scored_title,
            )
        return scored_title, {
            "accepted": True,
            "source": "candidate",
            "score": candidate_score.get("score"),
            "reason": candidate_score.get("reason"),
            "repaired": repaired,
        }

    candidate_failure_reason = str(candidate_score.get("reason") or "candidate_failed")
    repaired_candidate_result = _try_role_policy_title_repair(
        candidate,
        "candidate",
        candidate_failure_reason,
    )
    if repaired_candidate_result is not None:
        return repaired_candidate_result

    previous_score: Dict[str, Any] = {}
    previous_scored_title = previous
    if previous and previous != candidate:
        previous_score = _score_title_compliance(
            title=previous,
            topic=topic,
            content=content,
            user_keywords=user_keywords,
            full_name=full_name,
            category=category,
            status=status,
            context_analysis=context_analysis,
            role_keyword_policy=role_keyword_policy,
            poll_focus_bundle=poll_focus_bundle,
        )
        previous_scored_title = (
            _normalize_title_surface_local(str(previous_score.get("title") or previous))
            or previous
        )
        if previous_score.get("passed"):
            return previous_scored_title, {
                "accepted": True,
                "source": "previous",
                "score": previous_score.get("score"),
                "reason": candidate_failure_reason or "candidate_failed",
                "repaired": previous_scored_title != previous,
            }

        repaired_previous_result = _try_role_policy_title_repair(
            previous,
            "previous",
            candidate_failure_reason or str(previous_score.get("reason") or "previous_failed"),
        )
        if repaired_previous_result is not None:
            return repaired_previous_result

    if candidate_score.get("softAccepted"):
        return scored_title, {
            "accepted": True,
            "source": "candidate_soft",
            "score": candidate_score.get("score"),
            "reason": candidate_failure_reason,
            "repaired": scored_title != candidate,
        }

    if previous and previous_score.get("softAccepted"):
        return previous_scored_title, {
            "accepted": True,
            "source": "previous_soft",
            "score": previous_score.get("score"),
            "reason": candidate_score.get("reason") or previous_score.get("reason"),
            "repaired": previous_scored_title != previous,
        }

    reason = candidate_failure_reason
    raise ApiError("internal", f"제목 검증 실패: {reason}")


def _repair_failed_possessive_title_surface(title: str) -> str:
    candidate = _normalize_title_surface_local(title)
    if not candidate or not any(token in candidate for token in ("그의", "그녀의")):
        return ""
    repaired = re.sub(r"(?:그의|그녀의)\s*", "", candidate)
    repaired = re.sub(r"선택은\??$", "선택의 이유", repaired)
    repaired = _normalize_title_surface_local(repaired) or repaired
    return repaired if repaired and repaired != candidate else ""


def _try_inject_missing_required_keywords(
    *,
    title: str,
    content: str,
    user_keywords: list[str],
    topic: str,
    full_name: str,
    category: str,
    status: str,
    context_analysis: Dict[str, Any],
    role_keyword_policy: Optional[Dict[str, Any]] = None,
    poll_focus_bundle: Optional[Dict[str, Any]] = None,
) -> Optional[tuple[str, Dict[str, Any]]]:
    """패스스루 직전, 필수 키워드가 빠진 제목에 키워드를 삽입해 재채점한다.

    성공하면 (repaired_title, score_dict) 반환, 실패 시 None.
    """
    normalized_title = _normalize_title_surface_local(title)
    if not normalized_title or not user_keywords:
        return None
    try:
        from agents.common.title_common import (
            split_title_user_keywords_by_grounding,
            TITLE_LENGTH_HARD_MAX,
            TITLE_LENGTH_HARD_MIN,
        )

        grounding = split_title_user_keywords_by_grounding(
            user_keywords,
            content_preview=content,
            role_keyword_policy=role_keyword_policy,
        )
        required_keywords = grounding.get("required") or []
        if not required_keywords:
            return None

        compact_title = re.sub(r"\s+", "", normalized_title).lower()
        missing = [
            kw for kw in required_keywords
            if re.sub(r"\s+", "", kw).lower() not in compact_title
        ]
        if not missing:
            return None

        # 삽입 전략: 제목 내 fullName 뒤 또는 쉼표 뒤에 키워드를 자연스럽게 삽입
        candidates: list[str] = []
        for kw in missing[:2]:
            # 전략 1: fullName 뒤 쉼표 다음에 삽입
            if full_name and full_name in normalized_title:
                idx = normalized_title.find(full_name) + len(full_name)
                after = normalized_title[idx:].lstrip()
                if after.startswith(",") or after.startswith("，"):
                    insert_pos = idx + 1 + (len(normalized_title[idx:]) - len(normalized_title[idx:].lstrip()))
                    patched = f"{normalized_title[:idx]}, {kw} {normalized_title[idx:].lstrip(', ，')}"
                else:
                    patched = f"{normalized_title[:idx]}, {kw} {normalized_title[idx:].lstrip()}"
                patched = _normalize_title_surface_local(patched) or patched
                if TITLE_LENGTH_HARD_MIN <= len(patched) <= TITLE_LENGTH_HARD_MAX:
                    candidates.append(patched)

            # 전략 2: 첫 쉼표/콜론 직후 삽입
            comma_match = re.search(r"[,，:]\s*", normalized_title)
            if comma_match:
                pos = comma_match.end()
                patched = f"{normalized_title[:pos]}{kw} {normalized_title[pos:]}"
                patched = _normalize_title_surface_local(patched) or patched
                if TITLE_LENGTH_HARD_MIN <= len(patched) <= TITLE_LENGTH_HARD_MAX:
                    candidates.append(patched)

            # 전략 3: 제목 앞에 "kw," 프리픽스
            patched = f"{kw}, {normalized_title}"
            patched = _normalize_title_surface_local(patched) or patched
            if TITLE_LENGTH_HARD_MIN <= len(patched) <= TITLE_LENGTH_HARD_MAX:
                candidates.append(patched)

        best_result: Optional[tuple[str, Dict[str, Any]]] = None
        best_score = -1
        for cand in candidates:
            cand = repair_duplicate_particles_and_tokens(cand)
            cand = _normalize_title_surface_local(cand) or cand
            score = _score_title_compliance(
                title=cand,
                topic=topic,
                content=content,
                user_keywords=user_keywords,
                full_name=full_name,
                category=category,
                status=status,
                context_analysis=context_analysis,
                role_keyword_policy=role_keyword_policy,
                poll_focus_bundle=poll_focus_bundle,
            )
            s = _to_int(score.get("score"), 0)
            if score.get("passed") and s > best_score:
                best_score = s
                best_result = (
                    _normalize_title_surface_local(str(score.get("title") or cand)) or cand,
                    score,
                )
            elif not best_result and score.get("softAccepted") and s > best_score:
                best_score = s
                best_result = (
                    _normalize_title_surface_local(str(score.get("title") or cand)) or cand,
                    score,
                )

        return best_result
    except Exception as exc:
        logger.debug("Keyword injection repair failed: %s", exc)
        return None


def _guard_draft_title_nonfatal(
    *,
    phase: str,
    candidate_title: str,
    previous_title: str,
    topic: str,
    content: str,
    user_keywords: list[str],
    full_name: str,
    category: str,
    status: str,
    context_analysis: Dict[str, Any],
    role_keyword_policy: Optional[Dict[str, Any]] = None,
    recent_titles: Optional[list[str]] = None,
    poll_fact_table: Optional[Dict[str, Any]] = None,
    poll_focus_bundle: Optional[Dict[str, Any]] = None,
) -> tuple[str, Dict[str, Any]]:
    raw_candidate = str(candidate_title or "").strip()
    raw_previous = str(previous_title or "").strip()
    candidate = _normalize_title_surface_local(
        repair_duplicate_particles_and_tokens(candidate_title)
    )
    previous = _normalize_title_surface_local(
        repair_duplicate_particles_and_tokens(previous_title)
    )
    try:
        guarded_title, guard_info = _guard_title_after_editor(
            candidate_title=candidate,
            previous_title=previous,
            topic=topic,
            content=content,
            user_keywords=user_keywords,
            full_name=full_name,
            category=category,
            status=status,
            context_analysis=context_analysis,
            role_keyword_policy=role_keyword_policy,
            poll_focus_bundle=poll_focus_bundle,
            recent_titles=recent_titles,
        )
        guarded_title = _normalize_title_surface_local(
            repair_duplicate_particles_and_tokens(guarded_title)
        ) or guarded_title
        raw_reference_title = raw_candidate or raw_previous
        guard_info["phase"] = phase
        guard_info["nonFatal"] = True
        guard_info["validated"] = True
        guard_info["repaired"] = bool(guard_info.get("repaired")) or (
            bool(raw_reference_title) and guarded_title != raw_reference_title
        )
        return guarded_title, guard_info
    except ApiError as exc:
        reason = str(exc or "").strip()
        if reason.startswith("제목 검증 실패:"):
            reason = reason.split(":", 1)[1].strip()
        minimal_repair = _repair_failed_possessive_title_surface(candidate or previous)
        if minimal_repair:
            repaired_score = _score_title_compliance(
                title=minimal_repair,
                topic=topic,
                content=content,
                user_keywords=user_keywords,
                full_name=full_name,
                category=category,
                status=status,
                context_analysis=context_analysis,
                role_keyword_policy=role_keyword_policy,
                poll_focus_bundle=poll_focus_bundle,
            )
            repaired_title = (
                _normalize_title_surface_local(str(repaired_score.get("title") or minimal_repair))
                or minimal_repair
            )
            return repaired_title, {
                "accepted": True,
                "source": "candidate_failed_possessive_repair",
                "score": repaired_score.get("score"),
                "reason": reason or repaired_score.get("reason") or "third_person_possessive_repair",
                "repaired": True,
                "phase": phase,
                "nonFatal": True,
                "fallbackUsed": False,
                "validated": bool(repaired_score.get("passed")),
            }
        # -- 패스스루 전 필수 키워드 삽입 시도 --
        keyword_injected_result = _try_inject_missing_required_keywords(
            title=candidate or previous,
            content=content,
            user_keywords=user_keywords,
            topic=topic,
            full_name=full_name,
            category=category,
            status=status,
            context_analysis=context_analysis,
            role_keyword_policy=role_keyword_policy,
            poll_focus_bundle=poll_focus_bundle,
        )
        if keyword_injected_result is not None:
            injected_title, injected_score = keyword_injected_result
            logger.info(
                "Passthrough avoided: keyword injection repair succeeded (phase=%s, title=%s)",
                phase,
                injected_title,
            )
            return injected_title, {
                "accepted": True,
                "source": "candidate_failed_keyword_inject",
                "score": injected_score.get("score", 0),
                "reason": reason or "keyword_injection_repair",
                "repaired": True,
                "phase": phase,
                "nonFatal": True,
                "fallbackUsed": False,
                "validated": bool(injected_score.get("passed")),
            }

        logger.warning(
            "Draft title guard failure downgraded to passthrough (phase=%s, reason=%s, title=%s)",
            phase,
            reason,
            candidate,
        )
        passthrough_title = _normalize_title_surface_local(
            repair_duplicate_particles_and_tokens(candidate or previous)
        ) or (candidate or previous)
        raw_reference_title = raw_candidate or raw_previous
        return passthrough_title, {
            "accepted": True,
            "source": "candidate_failed_passthrough",
            "score": 0,
            "reason": reason or "draft_title_guard_failed",
            "repaired": bool(raw_reference_title) and passthrough_title != raw_reference_title,
            "phase": phase,
            "nonFatal": True,
            "fallbackUsed": False,
            "validated": False,
        }


def _extract_keyword_counts(keyword_result: Dict[str, Any] | None) -> Dict[str, int]:
    details = ((keyword_result or {}).get("details") or {}).get("keywords") or {}
    if not isinstance(details, dict):
        return {}

    counts: Dict[str, int] = {}
    for raw_keyword, raw_info in details.items():
        if not isinstance(raw_info, dict):
            continue

        keyword = str(raw_keyword or "").strip()
        if not keyword:
            continue

        keyword_type = str(raw_info.get("type") or "").strip().lower()
        # user 키워드는 비중첩 exclusive count 사용, auto 키워드는 coverage 사용
        exclusive_count = _to_int(raw_info.get("exclusiveCount"), _to_int(raw_info.get("count"), 0))
        gate_count = _to_int(raw_info.get("gateCount"), exclusive_count)
        coverage_count = _to_int(raw_info.get("coverage"), exclusive_count)
        counts[keyword] = gate_count if keyword_type == "user" else coverage_count

    return counts


def _resolve_output_format_options(
    *,
    data: Dict[str, Any],
    pipeline_result: Dict[str, Any],
    user_profile: Dict[str, Any],
    category: str,
) -> Dict[str, Any]:
    sub_category = str(
        pipeline_result.get("subCategory")
        or data.get("subCategory")
        or ""
    )
    allow_diagnostic_tail = (
        str(category or "").strip() == "current-affairs"
        and sub_category == "current_affairs_diagnosis"
    )

    slogan = str(
        pipeline_result.get("slogan")
        or data.get("slogan")
        or user_profile.get("slogan")
        or ""
    )
    slogan_enabled = bool(
        pipeline_result.get("sloganEnabled") is True
        or data.get("sloganEnabled") is True
        or user_profile.get("sloganEnabled") is True
    )
    donation_info = str(
        pipeline_result.get("donationInfo")
        or data.get("donationInfo")
        or user_profile.get("donationInfo")
        or ""
    )
    donation_enabled = bool(
        pipeline_result.get("donationEnabled") is True
        or data.get("donationEnabled") is True
        or user_profile.get("donationEnabled") is True
    )
    poll_citation = build_poll_citation_text(
        data.get("newsDataText"),
        pipeline_result.get("newsDataText"),
        data.get("stanceText"),
        pipeline_result.get("stanceText"),
        _safe_dict(_safe_dict(pipeline_result.get("contextAnalysis")).get("mustPreserve")).get("eventDate"),
        _safe_dict(pipeline_result.get("contextAnalysis")).get("eventDate"),
        data.get("eventDate"),
        data.get("sourceInput"),
        pipeline_result.get("sourceInput"),
        data.get("sourceContent"),
        data.get("originalContent"),
        data.get("inputContent"),
        data.get("rawContent"),
    )
    embed_poll_citation = _to_bool(
        data.get("embedPollCitation")
        if data.get("embedPollCitation") is not None
        else pipeline_result.get("embedPollCitation"),
        False,
    )
    if poll_citation:
        embed_poll_citation = True

    return {
        "allowDiagnosticTail": allow_diagnostic_tail,
        "slogan": slogan,
        "sloganEnabled": slogan_enabled,
        "donationInfo": donation_info,
        "donationEnabled": donation_enabled,
        "pollCitation": poll_citation,
        "embedPollCitation": embed_poll_citation,
        "topic": str(pipeline_result.get("topic") or data.get("prompt") or data.get("topic") or ""),
        "bookTitleHint": str(
            (
                (_safe_dict(pipeline_result.get("contextAnalysis")).get("mustPreserve") or {})
                if isinstance(_safe_dict(pipeline_result.get("contextAnalysis")).get("mustPreserve"), dict)
                else {}
            ).get("bookTitle")
            or ""
        ),
        "contextAnalysis": _safe_dict(pipeline_result.get("contextAnalysis")),
        "fullName": str(
            pipeline_result.get("fullName")
            or data.get("fullName")
            or data.get("name")
            or user_profile.get("fullName")
            or user_profile.get("name")
            or ""
        ).strip(),
    }


def _apply_last_mile_postprocess(
    *,
    content: str,
    title_text: str,
    target_word_count: int,
    user_keywords: list[str],
    auto_keywords: list[str],
    body_min_overrides: Dict[str, int],
    user_keyword_expected_overrides: Dict[str, int],
    user_keyword_max_overrides: Dict[str, int],
    output_options: Dict[str, Any],
    fallback_keyword_validation: Dict[str, Any],
    fallback_keyword_counts: Dict[str, Any],
) -> Dict[str, Any]:
    base_content = str(content or "").strip()
    fallback_counts = (
        fallback_keyword_counts
        if isinstance(fallback_keyword_counts, dict)
        else {}
    )
    if not base_content:
        return {
            "content": base_content,
            "wordCount": 0,
            "keywordValidation": fallback_keyword_validation if isinstance(fallback_keyword_validation, dict) else {},
            "keywordCounts": fallback_counts,
            "meta": {},
            "edited": False,
            "error": None,
        }

    try:
        cleaned = cleanup_post_content(base_content)
        interim_keyword_result = validate_keyword_insertion(
            cleaned,
            user_keywords,
            auto_keywords,
            target_word_count,
            title_text=title_text,
            body_min_overrides=body_min_overrides,
            user_keyword_expected_overrides=user_keyword_expected_overrides,
            user_keyword_max_overrides=user_keyword_max_overrides,
        )
        finalized = finalize_output(
            cleaned,
            slogan=str(output_options.get("slogan") or ""),
            slogan_enabled=bool(output_options.get("sloganEnabled") is True),
            donation_info=str(output_options.get("donationInfo") or ""),
            donation_enabled=bool(output_options.get("donationEnabled") is True),
            poll_citation=str(output_options.get("pollCitation") or ""),
            embed_poll_citation=bool(output_options.get("embedPollCitation") is True),
            allow_diagnostic_tail=bool(output_options.get("allowDiagnosticTail") is True),
            keyword_result=interim_keyword_result,
            topic=str(output_options.get("topic") or ""),
            book_title_hint=str(output_options.get("bookTitleHint") or ""),
            context_analysis=(
                output_options.get("contextAnalysis")
                if isinstance(output_options.get("contextAnalysis"), dict)
                else None
            ),
            full_name=str(output_options.get("fullName") or ""),
            target_word_count=target_word_count,
            append_terminal_addons=False,
        )
        finalized_content = str(finalized.get("content") or cleaned).strip()

        final_keyword_result = validate_keyword_insertion(
            finalized_content,
            user_keywords,
            auto_keywords,
            target_word_count,
            title_text=title_text,
            body_min_overrides=body_min_overrides,
            user_keyword_expected_overrides=user_keyword_expected_overrides,
            user_keyword_max_overrides=user_keyword_max_overrides,
        )
        final_keyword_validation = build_keyword_validation(final_keyword_result)
        final_keyword_counts = _extract_keyword_counts(final_keyword_result)

        return {
            "content": finalized_content,
            "wordCount": _count_chars_no_space(finalized_content),
            "keywordValidation": final_keyword_validation,
            "keywordCounts": final_keyword_counts,
            "meta": _safe_dict(finalized.get("meta")),
            "edited": finalized_content != base_content,
            "error": None,
        }
    except Exception as exc:
        logger.warning("Last-mile cleanup/finalize failed (non-fatal): %s", exc)
        return {
            "content": base_content,
            "wordCount": _count_chars_no_space(base_content),
            "keywordValidation": fallback_keyword_validation if isinstance(fallback_keyword_validation, dict) else {},
            "keywordCounts": fallback_counts,
            "meta": {},
            "edited": False,
            "error": str(exc),
        }


def _run_editor_repair_once(
    *,
    content: str,
    title: str,
    full_name: str,
    status: str,
    target_word_count: int,
    user_keywords: list[str],
    gate_user_keywords: Optional[list[str]] = None,
    validation_result: Dict[str, Any],
    keyword_validation: Dict[str, Any],
    extra_issues: Optional[list[str]] = None,
    purpose: str = "repair",
    style_guide: str = "",
    style_fingerprint: Optional[Dict[str, Any]] = None,
    generation_profile: Optional[Dict[str, Any]] = None,
    style_polish_mode: str = "",
    keyword_aliases: Optional[Dict[str, Any]] = None,
    source_texts: Optional[list[str]] = None,
) -> Dict[str, Any]:
    """기준 미충��� 시 EditorAgent로 1회 교정 시도."""
    base_content = str(content or "")
    base_title = str(title or "")
    keyword_feedback = _build_editor_keyword_feedback(
        keyword_validation,
        gate_user_keywords if isinstance(gate_user_keywords, list) else user_keywords,
    )
    if extra_issues:
        normalized_extra_issues = [str(item).strip() for item in extra_issues if str(item).strip()]
        if normalized_extra_issues:
            feedback_issues = list(keyword_feedback.get("issues") or [])
            for issue in normalized_extra_issues:
                tagged_issue = f"품질 무결성: {issue}"
                if tagged_issue not in feedback_issues:
                    feedback_issues.append(tagged_issue)
            keyword_feedback["issues"] = feedback_issues
            keyword_feedback["passed"] = False
    else:
        normalized_extra_issues = []
    normalized_purpose = str(purpose or "repair").strip().lower()
    resolved_style_fingerprint = style_fingerprint if isinstance(style_fingerprint, dict) else {}
    resolved_generation_profile = generation_profile if isinstance(generation_profile, dict) else {}
    resolved_style_guide = str(style_guide or "").strip()
    resolved_style_polish_mode = str(style_polish_mode or "").strip().lower()
    if resolved_style_polish_mode not in {"light", "medium"}:
        resolved_style_polish_mode = "light"
    allow_style_polish = (
        normalized_purpose == "polish"
        and not normalized_extra_issues
        and bool(resolved_style_guide or resolved_style_fingerprint)
    )

    try:
        from agents.core.editor_agent import EditorAgent

        agent = EditorAgent()
        editor_input = {
            "content": base_content,
            "title": base_title,
            "fullName": str(full_name or "").strip(),
            "validationResult": validation_result if isinstance(validation_result, dict) else {},
            "keywordResult": keyword_feedback,
            "keywords": user_keywords,
            "status": status,
            "targetWordCount": int(target_word_count or 2000),
            "polishMode": normalized_purpose == "polish",
            "styleGuide": resolved_style_guide if allow_style_polish else "",
            "styleFingerprint": resolved_style_fingerprint if allow_style_polish else {},
            "generationProfile": resolved_generation_profile if allow_style_polish else {},
            "stylePolishMode": resolved_style_polish_mode if allow_style_polish else "",
            "keywordAliases": keyword_aliases if isinstance(keyword_aliases, dict) else {},
            "sourceTexts": [s for s in (source_texts or []) if s],
        }
        result = _run_async_sync(agent.run(editor_input))
        if not isinstance(result, dict):
            result = {}

        repaired_content = str(result.get("content") or base_content).strip()
        repaired_title = str(result.get("title") or base_title).strip() or base_title
        edit_summary = result.get("editSummary")
        if not isinstance(edit_summary, list):
            edit_summary = []

        return {
            "content": repaired_content,
            "title": repaired_title,
            "edited": (repaired_content != base_content) or (repaired_title != base_title),
            "editSummary": edit_summary,
            "error": None,
        }
    except Exception as exc:
        logger.warning("EditorAgent auto-repair failed (non-fatal): %s", exc)
        return {
            "content": base_content,
            "title": base_title,
            "edited": False,
            "editSummary": [],
            "error": str(exc),
        }


def _recover_repetition_issues_once(
    *,
    content: str,
    title: str,
    topic: str,
    repetition_issues: list[str],
    min_required_chars: int,
    target_word_count: int,
    user_keywords: list[str],
    auto_keywords: list[str],
    body_min_overrides: Dict[str, int],
    user_keyword_expected_overrides: Dict[str, int],
    user_keyword_max_overrides: Dict[str, int],
    skip_user_keywords: Optional[list[str]],
    role_keyword_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """반복 품질 실패 시 LLM 재작성으로 1회 자동 교정."""
    base_content = str(content or "").strip()
    base_len = _count_chars_no_space(base_content)
    if not base_content or not repetition_issues:
        return {"content": base_content, "edited": False}

    issue_lines = "\n".join(f"- {item}" for item in repetition_issues[:4])
    keyword_text = ", ".join(str(item).strip() for item in user_keywords if str(item).strip())
    prompt = f"""
<repetition_repair_prompt version="xml-v1">
  <role>당신은 한국어 정치 콘텐츠 교열자입니다. 반복 문제만 해결하고 의미/사실은 유지하세요.</role>
  <goal>
    <current_chars>{base_len}</current_chars>
    <min_chars>{min_required_chars}</min_chars>
    <target_chars>{int(target_word_count * 0.9)}~{int(target_word_count * 1.2)}</target_chars>
  </goal>
  <issues>
{issue_lines}
  </issues>
  <rules>
    <rule order="1">핵심 주장, 일정, 장소, 고유명사, 수치 사실을 삭제/왜곡하지 말 것.</rule>
    <rule order="2">문장/구문 반복 문제만 해결하고, 동일 어구 연쇄 반복을 피할 것.</rule>
    <rule order="3">허용 태그는 &lt;h2&gt;, &lt;p&gt;만 사용.</rule>
    <rule order="4">검증 규칙 설명문(메타 문장)이나 템플릿 문장을 본문에 쓰지 말 것.</rule>
    <rule order="5">사용자 키워드가 있다면 문맥 안에서 자연스럽게 유지할 것.</rule>
  </rules>
  <topic>{topic}</topic>
  <title>{title}</title>
  <keywords>{keyword_text}</keywords>
  <draft><![CDATA[{base_content}]]></draft>
  <output_contract>
    <format>XML</format>
    <allowed_tags>content</allowed_tags>
    <example><![CDATA[<content>...HTML 본문...</content>]]></example>
  </output_contract>
</repetition_repair_prompt>
""".strip()

    try:
        from agents.common.gemini_client import DEFAULT_MODEL, generate_content_async

        response_text = _run_async_sync(
            generate_content_async(
                prompt,
                model_name=DEFAULT_MODEL,
                temperature=0.1,
                max_output_tokens=8192,
            )
        )
    except Exception as exc:
        logger.warning("반복 품질 자동 보정 호출 실패: %s", exc)
        return {"content": base_content, "edited": False, "error": str(exc)}

    candidate = _extract_content_payload(response_text)
    if not candidate:
        logger.warning("Repetition auto-repair parse failed: no <content> payload extracted")
        return {"content": base_content, "edited": False}

    candidate_len = _count_chars_no_space(candidate)
    if candidate_len < min_required_chars:
        logger.warning(
            "반복 품질 자동 보정 결과 분량 미달로 폐기: before=%s after=%s min=%s",
            base_len,
            candidate_len,
            min_required_chars,
        )
        return {"content": base_content, "edited": False}
    if base_len >= 1600 and candidate_len < int(base_len * 0.8):
        logger.warning(
            "반복 품질 자동 보정 결과 과축약으로 폐기: before=%s after=%s",
            base_len,
            candidate_len,
        )
        return {"content": base_content, "edited": False}

    keyword_repair = _repair_keyword_gate_once(
        content=candidate,
        title_text=title,
        user_keywords=user_keywords,
        auto_keywords=auto_keywords,
        target_word_count=target_word_count,
        body_min_overrides=body_min_overrides,
        user_keyword_expected_overrides=user_keyword_expected_overrides,
        user_keyword_max_overrides=user_keyword_max_overrides,
        skip_user_keywords=skip_user_keywords,
        role_keyword_policy=role_keyword_policy,
    )
    repaired_content = str(keyword_repair.get("content") or candidate)
    keyword_validation = _safe_dict(keyword_repair.get("keywordValidation"))
    keyword_counts = keyword_repair.get("keywordCounts")
    if not isinstance(keyword_counts, dict):
        keyword_counts = {}

    return {
        "content": repaired_content,
        "edited": repaired_content != base_content,
        "keywordValidation": keyword_validation,
        "keywordCounts": keyword_counts,
        "before": base_len,
        "after": _count_chars_no_space(repaired_content),
    }


def _recover_legal_issues_once(
    *,
    content: str,
    title: str,
    legal_items: list[Dict[str, Any]],
    status: str,
    target_word_count: int,
    user_keywords: list[str],
) -> Dict[str, Any]:
    """선거법 차단 이슈를 문장 단위로 1회 자동 교정."""
    base_content = str(content or "").strip()
    if not base_content or not legal_items:
        return {"content": base_content, "edited": False, "summary": []}

    issue_lines: list[str] = []
    for item in legal_items[:4]:
        if not isinstance(item, dict):
            continue
        issue_lines.append(f"- 사유: {str(item.get('reason') or '').strip()}")
        sentence = str(item.get("sentence") or "").strip()
        matched_text = str(item.get("matchedText") or "").strip()
        repair_hint = str(item.get("repairHint") or "").strip()
        if sentence:
            issue_lines.append(f'  문제 문장: "{sentence}"')
        if matched_text:
            issue_lines.append(f'  문제 표현: "{matched_text}"')
        if repair_hint:
            issue_lines.append(f"  수정 가이드: {repair_hint}")
    issue_block = "\n".join(issue_lines).strip()
    keyword_text = ", ".join(str(item).strip() for item in user_keywords if str(item).strip())
    prompt = f"""
<election_law_repair_prompt version="xml-v1">
  <role>당신은 대한민국 선거법 표현을 교정하는 한국어 정치 원고 편집자입니다.</role>
  <goal>
    <status>{status}</status>
    <target_chars>{int(target_word_count * 0.9)}~{int(target_word_count * 1.2)}</target_chars>
    <instruction>선거법에 걸린 문장만 최소 수정하고, 나머지 의미·사실·구조는 유지하세요.</instruction>
  </goal>
  <issues>
{issue_block}
  </issues>
  <rules>
    <rule order="1">문제 문장만 고치고, 새로운 인물·사실·수치·일정은 추가하지 말 것.</rule>
    <rule order="2">"~라고 알려져", "~라는 말이 있다", "들은 바" 같은 전언/소문/간접전언 표현은 완전히 제거할 것.</rule>
    <rule order="3">확인 가능한 사실은 직접 서술로, 확인이 어려운 평가는 삭제 또는 본인 판단 표현으로 축소할 것.</rule>
    <rule order="4">허용 태그는 &lt;h2&gt;, &lt;p&gt;만 사용.</rule>
    <rule order="5">제공된 키워드는 가능한 한 자연스럽게 유지할 것.</rule>
    <rule order="6">문장만 고치고 원고 전체 구조를 다시 쓰지 말 것.</rule>
  </rules>
  <title>{title}</title>
  <keywords>{keyword_text}</keywords>
  <draft><![CDATA[{base_content}]]></draft>
  <output_contract>
    <format>XML</format>
    <allowed_tags>content</allowed_tags>
    <example><![CDATA[<content>...HTML 본문...</content>]]></example>
  </output_contract>
</election_law_repair_prompt>
""".strip()

    try:
        from agents.common.gemini_client import DEFAULT_MODEL, generate_content_async

        response_text = _run_async_sync(
            generate_content_async(
                prompt,
                model_name=DEFAULT_MODEL,
                temperature=0.1,
                max_output_tokens=8192,
            )
        )
    except Exception as exc:
        logger.warning("선거법 자동 보정 호출 실패: %s", exc)
        return {"content": base_content, "edited": False, "summary": [], "error": str(exc)}

    candidate = _extract_content_payload(response_text)
    if not candidate:
        logger.warning("선거법 자동 보정 parse failed: no <content> payload extracted")
        return {"content": base_content, "edited": False, "summary": []}

    return {
        "content": candidate,
        "edited": candidate != base_content,
        "summary": [_format_legal_gate_item(item) for item in legal_items[:3]],
        "error": None,
    }


def _choose_pipeline_route(raw_route: Any, *, is_admin: bool, is_tester: bool) -> str:
    return str(raw_route or "modular").strip() or "modular"


def handle_generate_posts_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    started_ms = int(time.time() * 1000)
    uid = req.auth.uid if req.auth else ""
    _ensure_user(uid)

    data = req.data if isinstance(req.data, dict) else {}
    if isinstance(data.get("data"), dict):
        data = data["data"]

    topic, category, sub_category, classification_meta = _resolve_request_intent_with_meta(data)
    target_word_count = _target_word_count(data, category)
    logger.info(
        "CATEGORY_CLASSIFICATION generate_posts requested=%s/%s resolved=%s/%s writingMethod=%s source=%s confidence=%.3f stance=%s",
        classification_meta.get("requestedCategory"),
        classification_meta.get("requestedSubCategory"),
        classification_meta.get("resolvedCategory"),
        classification_meta.get("resolvedSubCategory"),
        classification_meta.get("writingMethod"),
        classification_meta.get("source"),
        float(classification_meta.get("confidence") or 0.0),
        bool(classification_meta.get("hasStanceSignal")),
    )

    progress_session_id = str(data.get("progressSessionId") or f"{uid}_{int(time.time() * 1000)}")
    progress = ProgressTracker(progress_session_id)
    progress.step_preparing()

    # 프로필 로드 (권한/세션/경고/응답 메타데이터용)
    profile_bundle = load_user_profile(uid, category=category, topic=topic, options={"strictSourceOnly": True})
    user_profile = _safe_dict(profile_bundle.get("userProfile"))
    is_admin = is_admin_user(user_profile)
    is_tester = is_tester_user(user_profile)
    if not is_admin and not is_tester:
        eligibility = check_election_eligibility(user_profile)
        if not eligibility.get("allowed"):
            raise https_fn.HttpsError(
                "permission-denied",
                str(eligibility.get("message") or "원고 생성 자격이 없습니다."),
                details={"reason": eligibility.get("reason")},
            )
    full_name = str(
        data.get("fullName")
        or user_profile.get("fullName")
        or user_profile.get("name")
        or ""
    ).strip()
    daily_limit_warning = _calc_daily_limit_warning(user_profile)
    editor_polish_enabled = _to_bool(data.get("editorPolish"), False)
    editor_second_pass_enabled = _to_bool(data.get("editorSecondPass"), False)
    style_guide = str(data.get("styleGuide") or profile_bundle.get("styleGuide") or "").strip()
    raw_style_fingerprint = data.get("styleFingerprint")
    if not isinstance(raw_style_fingerprint, dict):
        raw_style_fingerprint = profile_bundle.get("styleFingerprint")
    style_fingerprint = _safe_dict(raw_style_fingerprint)
    raw_generation_profile = data.get("generationProfile")
    if not isinstance(raw_generation_profile, dict):
        raw_generation_profile = profile_bundle.get("generationProfile")
    generation_profile = _safe_dict(raw_generation_profile)
    keyword_aliases = _safe_dict(profile_bundle.get("keywordAliases"))
    # 캐싱된 별칭이 없으면 현재 요청 텍스트에서 즉시 추출
    if not keyword_aliases:
        try:
            _alias_corpus_parts = []
            _raw_stance = str(data.get("stanceText") or "").strip()
            if _raw_stance:
                _alias_corpus_parts.append(_raw_stance)
            for _bio_entry in (profile_bundle.get("bioEntries") or []):
                _bio_text = str((_bio_entry if isinstance(_bio_entry, dict) else {}).get("content") or "").strip()
                if _bio_text:
                    _alias_corpus_parts.append(_bio_text)
            _alias_corpus = "\n\n".join(_alias_corpus_parts)
            if _alias_corpus and len(_alias_corpus) >= 50:
                from rag_manager import extract_keyword_aliases as _extract_aliases
                keyword_aliases = _safe_dict(
                    _run_async_sync(_extract_aliases(_alias_corpus, user_keywords=_normalize_keywords(data.get("keywords"))))
                )
                if keyword_aliases and uid:
                    try:
                        firestore.client().collection("bios").document(uid).set(
                            {"keywordAliases": keyword_aliases}, merge=True
                        )
                        logger.info("[AliasExtract] 생성 시점 추출 %d건 — uid=%s", len(keyword_aliases), uid)
                    except Exception:
                        pass
        except Exception as _alias_exc:
            logger.warning("[AliasExtract] 생성 시점 추출 실패(무시): %s", _alias_exc)
            keyword_aliases = {}
    style_polish_mode = str(data.get("stylePolishMode") or "light").strip().lower()
    if style_polish_mode not in {"light", "medium"}:
        style_polish_mode = "light"

    saved_recent_titles: list[str] = []
    if uid and not is_admin:
        try:
            saved_recent_titles = get_recent_selected_titles(uid, limit=5)
        except Exception as exc:
            logger.warning("선택 제목 메모리 조회 실패(무시): %s", exc)

    requested_session_id = str(data.get("sessionId") or "").strip()
    prior_session_snapshot: Dict[str, Any] = {}
    carried_recent_titles: list[str] = list(saved_recent_titles)
    if not requested_session_id:
        prior_session_snapshot = _safe_dict(
            peek_active_generation_session(
                uid,
                is_admin=is_admin,
            )
        )
        if _should_carry_recent_titles_from_prior_session(
            prior_session_snapshot,
            topic=topic,
            category=category,
        ):
            for item in reversed(_normalize_recent_title_memory_values(prior_session_snapshot.get("recentTitles"))[:5]):
                if item in carried_recent_titles:
                    carried_recent_titles.remove(item)
                carried_recent_titles.insert(0, item)
            carried_recent_titles = carried_recent_titles[:5]
        _clear_active_session(uid)

    request_recent_titles = _normalize_recent_title_memory_values(data.get("recentTitles"))[:5]
    if request_recent_titles:
        for item in reversed(request_recent_titles):
            if item in carried_recent_titles:
                carried_recent_titles.remove(item)
            carried_recent_titles.insert(0, item)
        carried_recent_titles = carried_recent_titles[:5]

    session = get_or_create_session(
        uid,
        is_admin=is_admin,
        is_tester=is_tester,
        category=category,
        topic=topic,
        seed_recent_titles=carried_recent_titles,
    )
    session = _safe_dict(session)
    attempts = _to_int(session.get("attempts"), 0)
    max_attempts = _to_int(session.get("maxAttempts"), 3)
    if attempts >= max_attempts:
        raise ApiError(
            "resource-exhausted",
            f"최대 {max_attempts}회까지만 재생성할 수 있습니다. 새로운 원고를 생성해주세요.",
        )

    progress.step_collecting()
    progress.step_generating()

    user_keywords = _normalize_keywords(data.get("keywords"))
    pipeline_route = _choose_pipeline_route(data.get("pipeline"), is_admin=is_admin, is_tester=is_tester)
    start_payload = _extract_start_payload(
        uid,
        data,
        topic=topic,
        category=category,
        sub_category=sub_category,
        classification_meta=classification_meta,
        target_word_count=target_word_count,
        user_keywords=user_keywords,
        pipeline_route=pipeline_route,
        recent_titles=_normalize_recent_title_memory_values(
            [*(session.get("recentTitles") or []), *carried_recent_titles]
        )[:8],
    )

    job_id = _call_pipeline_start(start_payload)
    pipeline_result = _poll_pipeline(job_id, progress)
    pipeline_user_keywords = _normalize_keywords(
        pipeline_result.get("userKeywords") or pipeline_result.get("keywords")
    )
    if not user_keywords and pipeline_user_keywords:
        user_keywords = pipeline_user_keywords
        logger.info(
            "요청 본문에서 추출된 userKeywords를 후처리 게이트에 반영: %s",
            user_keywords[:5],
        )
    output_format_options = _resolve_output_format_options(
        data=data,
        pipeline_result=pipeline_result if isinstance(pipeline_result, dict) else {},
        user_profile=user_profile,
        category=category,
    )

    generated_content = str(pipeline_result.get("content") or "").strip()
    if not generated_content:
        raise ApiError("internal", "원고 생성 실패 - 콘텐츠가 생성되지 않았습니다.")
    logger.info(
        "Raw draft snapshot captured: chars=%s preview=%s",
        _count_chars_no_space(generated_content),
        _content_log_preview(generated_content),
    )

    full_name = _resolve_full_name(
        data=data,
        user_profile=user_profile,
        pipeline_result=pipeline_result if isinstance(pipeline_result, dict) else {},
        provisional_name=full_name,
    )
    if not full_name:
        raise ApiError(
            "failed-precondition",
            "화자 이름을 확인할 수 없습니다. 프로필 이름 또는 fullName을 설정한 뒤 다시 시도해 주세요.",
        )
    output_format_options["fullName"] = full_name
    role_facts = _build_person_role_facts(
        data=data if isinstance(data, dict) else {},
        pipeline_result=pipeline_result if isinstance(pipeline_result, dict) else {},
    )
    role_keyword_policy = build_role_keyword_policy(
        user_keywords,
        person_roles=role_facts,
        source_texts=[
            data.get("newsDataText"),
            pipeline_result.get("newsDataText"),
            data.get("stanceText"),
            data.get("sourceInput"),
            pipeline_result.get("sourceInput"),
            data.get("sourceContent"),
            pipeline_result.get("sourceContent"),
        ],
    )
    poll_fact_table = build_poll_matchup_fact_table(
        [
            data.get("newsDataText"),
            pipeline_result.get("newsDataText"),
            data.get("stanceText"),
            data.get("sourceInput"),
            pipeline_result.get("sourceInput"),
        ],
        known_names=[*list(role_facts.keys()), full_name],
    )
    poll_focus_bundle = build_poll_focus_bundle(
        topic=topic,
        user_keywords=user_keywords,
        full_name=full_name,
        text_sources=[
            data.get("newsDataText"),
            pipeline_result.get("newsDataText"),
            data.get("stanceText"),
            data.get("sourceInput"),
            pipeline_result.get("sourceInput"),
        ],
        poll_fact_table=poll_fact_table,
    )
    conflicting_role_keyword = _find_conflicting_role_keyword(user_keywords, role_facts)
    keyword_gate_policy = _resolve_keyword_gate_policy(
        user_keywords,
        conflicting_role_keyword=conflicting_role_keyword,
        role_keyword_policy=role_keyword_policy,
    )
    gate_user_keywords = list(keyword_gate_policy.get("hardKeywords") or [])
    soft_gate_keywords = list(keyword_gate_policy.get("softKeywords") or [])
    if soft_gate_keywords:
        logger.info(
            "Keyword hard-gate softening applied: hard=%s soft=%s shadowed=%s conflicting=%s",
            gate_user_keywords,
            soft_gate_keywords,
            keyword_gate_policy.get("shadowedMap") or {},
            conflicting_role_keyword or "",
        )
    body_min_overrides: Dict[str, int] = {}
    user_keyword_expected_overrides: Dict[str, int] = {}
    user_keyword_max_overrides: Dict[str, int] = {}
    policy_entries = role_keyword_policy.get("entries") if isinstance(role_keyword_policy, dict) else {}
    if isinstance(policy_entries, dict):
        for keyword, entry in policy_entries.items():
            if not isinstance(entry, dict):
                continue
            mode = str(entry.get("mode") or "").strip()
            if mode == "intent_only":
                body_min_overrides[str(keyword)] = 0
                user_keyword_expected_overrides[str(keyword)] = 1
                user_keyword_max_overrides[str(keyword)] = 2
            elif mode == "blocked":
                body_min_overrides[str(keyword)] = 0
                user_keyword_expected_overrides[str(keyword)] = 0
                user_keyword_max_overrides[str(keyword)] = 0
    _apply_speaker_name_keyword_max_override(
        user_keywords,
        full_name,
        user_keyword_max_overrides,
    )

    quality_warnings: list[str] = []
    request_recent_title_memory = _collect_recent_title_memory(
        data=data if isinstance(data, dict) else {},
        pipeline_result={},
        session=session,
        draft_title="",
        include_current_titles=False,
        seed_titles=saved_recent_titles,
    )
    _raw_pipeline_title = str(pipeline_result.get("title") or "").strip()
    if not _raw_pipeline_title:
        raise ApiError("internal", "제목 생성에 실패했습니다. 다시 시도해 주세요.")
    generated_title = _normalize_title_surface_local(_raw_pipeline_title) or _raw_pipeline_title
    seo_passed = pipeline_result.get("seoPassed")
    compliance_passed = pipeline_result.get("compliancePassed")
    writing_method = str(pipeline_result.get("writingMethod") or pipeline_route or "modular")
    context_analysis_for_title = _safe_dict(pipeline_result.get("contextAnalysis"))
    must_preserve_for_title = _safe_dict(context_analysis_for_title.get("mustPreserve"))
    event_date_hint_for_guard = str(must_preserve_for_title.get("eventDate") or "").strip()
    auto_keywords = _sanitize_auto_keywords(
        pipeline_result.get("autoKeywords"),
        user_keywords=user_keywords,
    )
    generated_title = _normalize_title_surface_local(generated_title) or generated_title
    draft_title = generated_title
    initial_keyword_result = validate_keyword_insertion(
        generated_content,
        user_keywords=user_keywords,
        auto_keywords=auto_keywords,
        target_word_count=target_word_count,
        title_text=generated_title,
        body_min_overrides=body_min_overrides,
        user_keyword_expected_overrides=user_keyword_expected_overrides,
        user_keyword_max_overrides=user_keyword_max_overrides,
        keyword_aliases=keyword_aliases,
    )
    keyword_validation = build_keyword_validation(initial_keyword_result)
    keyword_counts = _extract_keyword_counts(initial_keyword_result)
    word_count = _to_int(pipeline_result.get("wordCount"), _count_chars_no_space(generated_content))
    stance_count = _extract_stance_count(pipeline_result)
    min_required_chars = _calc_min_required_chars(target_word_count, stance_count)
    status_for_validation = str(data.get("status") or user_profile.get("status") or "")
    # 사용자 원문 텍스트: stanceText, newsDataText, 프로필 bioEntries 에 포함된
    # 수치는 사용자 본인이 제공한 것이므로 선거법 수치 출처 검증에서 면제한다.
    _source_texts_for_heuristic = [
        str(data.get("stanceText") or "").strip(),
        str(data.get("newsDataText") or "").strip(),
    ]
    for _bio_entry in (profile_bundle.get("bioEntries") or []):
        _bio_text = str((_bio_entry if isinstance(_bio_entry, dict) else {}).get("content") or "").strip()
        if _bio_text:
            _source_texts_for_heuristic.append(_bio_text)
    _source_texts_for_heuristic = [t for t in _source_texts_for_heuristic if t]
    title_last_valid = ""
    title_guard_trace: list[Dict[str, Any]] = []
    independent_final_title: Dict[str, Any] = {
        "attempted": False,
        "applied": False,
        "fallbackUsed": False,
        "draftTitle": draft_title,
        "candidate": "",
        "error": "",
        "score": 0,
        "type": "",
    }
    speaker_gate: Dict[str, Any] = {
        "checked": False,
        "fullName": full_name,
        "initialIssues": [],
        "repairAttempted": False,
        "repairApplied": False,
        "repairPatterns": [],
        "finalIssues": [],
        "blocked": False,
    }
    role_gate: Dict[str, Any] = {
        "enabled": bool(role_facts),
        "facts": role_facts,
        "initialIssues": [],
        "repairAttempted": False,
        "repairApplied": False,
        "replacements": [],
        "honorificRepairApplied": False,
        "honorificReplacements": [],
        "finalIssues": [],
    }
    poll_fact_guard: Dict[str, Any] = {
        "enabled": bool((_safe_dict(poll_fact_table).get("pairs") or {})),
        "pairCount": len((_safe_dict(poll_fact_table).get("pairs") or {})),
        "title": {"checked": 0, "edited": False, "blockingIssues": [], "repairs": []},
        "content": {"checked": 0, "edited": False, "blockingIssues": [], "warnings": [], "repairs": []},
    }
    date_weekday_guard: Dict[str, Any] = {
        "applied": False,
        "yearHint": "",
        "title": {"edited": False, "changes": [], "issues": []},
        "content": {"edited": False, "changes": [], "issues": []},
    }
    length_repair_applied = False
    keyword_repair_applied = False
    repetition_rule_repair_applied = False
    repetition_llm_repair_applied = False
    legal_repair_applied = False
    editor_keyword_repair_applied = False
    max_content_repair_steps = 4
    content_repair_steps = 0
    content_repair_rollbacks: list[Dict[str, Any]] = []
    content_meta: Dict[str, Any] = {}
    final_sentence_polish: Dict[str, Any] = {
        "attempted": False,
        "applied": False,
        "actions": [],
        "skippedReason": "",
    }
    final_section_length_backstop: Dict[str, Any] = {
        "attempted": False,
        "applied": False,
        "actions": [],
    }
    final_structure_gate: Dict[str, Any] = {
        "attempted": False,
        "normalized": False,
        "issues": [],
    }
    subheading_entity_gate: Dict[str, Any] = {
        "attempted": False,
        "applied": False,
        "replacements": [],
        "skippedReason": "",
    }
    subheading_guard: Dict[str, Any] = {
        "applied": False,
        "trace": [],
        "stats": {},
        "skippedReason": "",
    }
    integrity_editor_repair: Dict[str, Any] = {
        "attempted": 0,
        "applied": 0,
        "error": None,
        "summary": [],
    }
    legal_targeted_repair: Dict[str, Any] = {
        "attempted": False,
        "applied": False,
        "summary": [],
        "error": None,
    }

    def _apply_content_repair(stage: str, candidate_content: str, *, force: bool = False) -> bool:
        nonlocal generated_content, word_count, content_repair_steps

        candidate = str(candidate_content or "").strip()
        if not candidate or candidate == generated_content:
            return False

        if not force and content_repair_steps >= max_content_repair_steps:
            logger.info(
                "Content repair skipped(stage=%s): budget exhausted (%s/%s)",
                stage,
                content_repair_steps,
                max_content_repair_steps,
            )
            return False

        corrupted, reason = _detect_content_repair_corruption(generated_content, candidate)
        if corrupted:
            logger.warning("Content repair rollback(stage=%s): %s", stage, reason)
            content_repair_rollbacks.append({"stage": stage, "reason": reason})
            return False

        logger.info(
            "Content repair apply(stage=%s): before_chars=%s after_chars=%s before=%s after=%s",
            stage,
            _count_chars_no_space(generated_content),
            _count_chars_no_space(candidate),
            _content_log_preview(generated_content),
            _content_log_preview(candidate),
        )
        generated_content = candidate
        word_count = _count_chars_no_space(generated_content)
        content_repair_steps += 1
        return True

    def _refresh_terminal_validation_state() -> None:
        nonlocal word_count
        nonlocal keyword_validation
        nonlocal keyword_counts
        nonlocal final_heuristic
        nonlocal legal_issues
        nonlocal final_speaker_issues
        nonlocal final_role_issues
        nonlocal final_integrity_issues
        nonlocal final_blocking_integrity_issues

        word_count = _count_chars_no_space(generated_content)
        refreshed_keyword_result = validate_keyword_insertion(
            generated_content,
            user_keywords=user_keywords,
            auto_keywords=auto_keywords,
            target_word_count=target_word_count,
            title_text=generated_title,
            body_min_overrides=body_min_overrides,
            user_keyword_expected_overrides=user_keyword_expected_overrides,
            user_keyword_max_overrides=user_keyword_max_overrides,
        )
        keyword_validation = build_keyword_validation(refreshed_keyword_result)
        refreshed_keyword_counts = _extract_keyword_counts(refreshed_keyword_result)
        if isinstance(refreshed_keyword_counts, dict):
            keyword_counts = refreshed_keyword_counts

        final_heuristic = run_heuristic_validation_sync(
            generated_content,
            status_for_validation,
            generated_title,
            options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
        )
        legal_issues = _extract_legal_gate_issues(final_heuristic)
        final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
        final_role_issues = _extract_role_consistency_issues(
            generated_content,
            role_facts,
        )
        final_integrity_issues = _detect_integrity_gate_issues(generated_content)
        final_blocking_integrity_issues = _extract_blocking_integrity_issues(final_integrity_issues)

    integrity_repair = _repair_integrity_noise_once(generated_content)
    if integrity_repair.get("edited"):
        integrity_candidate = str(integrity_repair.get("content") or generated_content)
        if _apply_content_repair("integrity_noise_repair", integrity_candidate):
            logger.info(
                "무결성 노이즈 자동 보정 적용: actions=%s",
                integrity_repair.get("actions"),
            )

    style_generation_scrub = _apply_global_style_ai_alternative_rules_once(
        generated_content,
        style_fingerprint=style_fingerprint,
    )
    if style_generation_scrub.get("edited"):
        style_generation_candidate = str(style_generation_scrub.get("content") or generated_content)
        if _apply_content_repair("style_generation_scrub", style_generation_candidate):
            logger.info(
                "초안 단계 문체 대체표현 사전 치환 적용: actions=%s",
                style_generation_scrub.get("actions"),
            )

    initial_keyword_gate_ok, initial_keyword_gate_msg = _validate_keyword_gate(keyword_validation, gate_user_keywords)
    initial_heuristic = run_heuristic_validation_sync(
        generated_content,
        status_for_validation,
        generated_title,
        options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
    )
    initial_repetition_issues = _extract_repetition_gate_issues(initial_heuristic)
    initial_legal_issues = _extract_legal_gate_issues(initial_heuristic)
    initial_length_ok = word_count >= min_required_chars
    first_pass_failure_reasons: list[str] = []
    if not initial_length_ok:
        first_pass_failure_reasons.append("length")
    if not initial_keyword_gate_ok:
        first_pass_failure_reasons.append("keyword")
    if initial_repetition_issues:
        first_pass_failure_reasons.append("repetition")
    if initial_legal_issues:
        first_pass_failure_reasons.append("election_law")
    first_pass_passed = len(first_pass_failure_reasons) == 0

    logger.info(
        "분량 게이트 계산: target=%s, stance_count=%s, min_required=%s, actual=%s",
        target_word_count,
        stance_count,
        min_required_chars,
        word_count,
    )
    logger.info(
        "QUALITY_METRIC generate_posts first_pass=%s reason=%s length_ok=%s keyword_ok=%s repetition=%s legal=%s",
        int(first_pass_passed),
        ",".join(first_pass_failure_reasons) if first_pass_failure_reasons else "none",
        initial_length_ok,
        initial_keyword_gate_ok,
        len(initial_repetition_issues),
        len(initial_legal_issues),
    )
    if word_count < min_required_chars:
        length_repair = _recover_short_content_once(
            content=generated_content,
            title=generated_title,
            topic=topic,
            min_required_chars=min_required_chars,
            target_word_count=target_word_count,
            user_keywords=user_keywords,
            auto_keywords=auto_keywords,
            body_min_overrides=body_min_overrides,
            user_keyword_expected_overrides=user_keyword_expected_overrides,
            user_keyword_max_overrides=user_keyword_max_overrides,
            skip_user_keywords=soft_gate_keywords,
            role_keyword_policy=role_keyword_policy,
        )
        if length_repair.get("edited"):
            candidate_content = str(length_repair.get("content") or generated_content)
            if _apply_content_repair("length_repair", candidate_content):
                length_repair_applied = True
                repaired_keyword_validation = length_repair.get("keywordValidation")
                if isinstance(repaired_keyword_validation, dict) and repaired_keyword_validation:
                    keyword_validation = repaired_keyword_validation
                repaired_keyword_counts = length_repair.get("keywordCounts")
                if isinstance(repaired_keyword_counts, dict) and repaired_keyword_counts:
                    keyword_counts = repaired_keyword_counts
                logger.info(
                    "분량 자동 보정 완료: %s자 -> %s자",
                    length_repair.get("before"),
                    length_repair.get("after"),
                )
            else:
                logger.info("분량 자동 보정 결과 미적용(stage=length_repair)")

    if word_count < min_required_chars:
        _append_quality_warning(
            quality_warnings,
            f"분량 권장치 미달 ({word_count}자 < {min_required_chars}자)",
        )
        logger.warning(
            "Soft gate - length below recommended threshold: actual=%s, min=%s",
            word_count,
            min_required_chars,
        )
    keyword_gate_ok, keyword_gate_msg = _validate_keyword_gate(keyword_validation, gate_user_keywords)
    if not keyword_gate_ok:
        logger.info("키워드 자동 보정 시작: %s", keyword_gate_msg)
        repaired = _repair_keyword_gate_once(
            content=generated_content,
            title_text=generated_title,
            user_keywords=user_keywords,
            auto_keywords=auto_keywords,
            target_word_count=target_word_count,
            body_min_overrides=body_min_overrides,
            user_keyword_expected_overrides=user_keyword_expected_overrides,
            user_keyword_max_overrides=user_keyword_max_overrides,
            skip_user_keywords=soft_gate_keywords,
            role_keyword_policy=role_keyword_policy,
        )
        candidate_content = str(repaired.get("content") or generated_content)
        applied = bool(repaired.get("edited")) and _apply_content_repair("keyword_repair", candidate_content)
        keyword_repair_applied = applied
        if applied:
            keyword_validation = _safe_dict(repaired.get("keywordValidation"))
            repaired_counts = repaired.get("keywordCounts")
            keyword_counts = repaired_counts if isinstance(repaired_counts, dict) else keyword_counts
            logger.info(
                "키워드 자동 보정 완료: edited=%s, reductions=%s, new_word_count=%s",
                bool(repaired.get("edited")),
                repaired.get("reductions"),
                word_count,
            )
        else:
            logger.info(
                "키워드 자동 보정 결과 미적용(stage=keyword_repair, edited=%s)",
                bool(repaired.get("edited")),
            )
        keyword_gate_ok, keyword_gate_msg = _validate_keyword_gate(keyword_validation, gate_user_keywords)

    if not keyword_gate_ok:
        _append_quality_warning(
            quality_warnings,
            f"키워드 권장 기준 미충족: {keyword_gate_msg}",
        )
        logger.warning("Soft gate - keyword criteria not satisfied: %s", keyword_gate_msg)

    # 최종 반복 품질 게이트: 반복 이슈는 우선 자동 보정하고 경고로 남긴다.
    heuristic_result = run_heuristic_validation_sync(
        generated_content,
        status_for_validation,
        generated_title,
        options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
    )
    repetition_issues = _extract_repetition_gate_issues(heuristic_result)
    if repetition_issues:
        repetition_fix = enforce_repetition_requirements(generated_content)
        if repetition_fix.get("edited"):
            candidate_content = str(repetition_fix.get("content") or generated_content)
            if _apply_content_repair("repetition_rule_repair", candidate_content):
                repetition_rule_repair_applied = True
                logger.info(
                    "반복 품질 자동 보정 적용: actions=%s, new_word_count=%s",
                    repetition_fix.get("actions"),
                    word_count,
                )

                post_fix_keyword_result = validate_keyword_insertion(
                    generated_content,
                    user_keywords,
                    auto_keywords,
                    target_word_count,
                    title_text=generated_title,
                    body_min_overrides=body_min_overrides,
                    user_keyword_expected_overrides=user_keyword_expected_overrides,
                    user_keyword_max_overrides=user_keyword_max_overrides,
                )
                keyword_validation = build_keyword_validation(post_fix_keyword_result)
                post_fix_keyword_gate_ok, post_fix_keyword_gate_msg = _validate_keyword_gate(
                    keyword_validation,
                    gate_user_keywords,
                )
                if not post_fix_keyword_gate_ok:
                    keyword_repair = _repair_keyword_gate_once(
                        content=generated_content,
                        title_text=generated_title,
                        user_keywords=user_keywords,
                        auto_keywords=auto_keywords,
                        target_word_count=target_word_count,
                        body_min_overrides=body_min_overrides,
                        user_keyword_expected_overrides=user_keyword_expected_overrides,
                        user_keyword_max_overrides=user_keyword_max_overrides,
                        skip_user_keywords=soft_gate_keywords,
                        role_keyword_policy=role_keyword_policy,
                    )
                    keyword_candidate = str(keyword_repair.get("content") or generated_content)
                    keyword_applied = bool(keyword_repair.get("edited")) and _apply_content_repair(
                        "keyword_repair_after_repetition",
                        keyword_candidate,
                    )
                    if keyword_applied:
                        keyword_validation = _safe_dict(keyword_repair.get("keywordValidation"))
                        repaired_counts = keyword_repair.get("keywordCounts")
                        keyword_counts = repaired_counts if isinstance(repaired_counts, dict) else keyword_counts
                        post_fix_keyword_gate_ok, post_fix_keyword_gate_msg = _validate_keyword_gate(
                            keyword_validation,
                            gate_user_keywords,
                        )
                    if not post_fix_keyword_gate_ok:
                        _append_quality_warning(
                            quality_warnings,
                            f"키워드 권장 기준 미충족: {post_fix_keyword_gate_msg}",
                        )
                        logger.warning(
                            "Soft gate - keyword criteria still not satisfied after repetition fix: %s",
                            post_fix_keyword_gate_msg,
                        )

                heuristic_result = run_heuristic_validation_sync(
                    generated_content,
                    status_for_validation,
                    generated_title,
                    options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
                )
                repetition_issues = _extract_repetition_gate_issues(heuristic_result)
            else:
                logger.info("반복 품질 자동 보정 결과 미적용(stage=repetition_rule_repair)")

        if repetition_issues:
            issue_text = "; ".join(repetition_issues[:2])
            logger.info("반복 품질 LLM 자동 보정 시작: %s", issue_text)
            repetition_llm_fix = _recover_repetition_issues_once(
                content=generated_content,
                title=generated_title,
                topic=topic,
                repetition_issues=repetition_issues,
                min_required_chars=min_required_chars,
                target_word_count=target_word_count,
                user_keywords=user_keywords,
                auto_keywords=auto_keywords,
                body_min_overrides=body_min_overrides,
                user_keyword_expected_overrides=user_keyword_expected_overrides,
                user_keyword_max_overrides=user_keyword_max_overrides,
                skip_user_keywords=soft_gate_keywords,
                role_keyword_policy=role_keyword_policy,
            )
            if repetition_llm_fix.get("edited"):
                candidate_content = str(repetition_llm_fix.get("content") or generated_content)
                if _apply_content_repair("repetition_llm_repair", candidate_content):
                    repaired_keyword_validation = repetition_llm_fix.get("keywordValidation")
                    if isinstance(repaired_keyword_validation, dict) and repaired_keyword_validation:
                        keyword_validation = repaired_keyword_validation
                    repaired_keyword_counts = repetition_llm_fix.get("keywordCounts")
                    if isinstance(repaired_keyword_counts, dict) and repaired_keyword_counts:
                        keyword_counts = repaired_keyword_counts
                    repetition_llm_repair_applied = True
                    logger.info(
                        "반복 품질 LLM 자동 보정 완료: %s자 -> %s자",
                        repetition_llm_fix.get("before"),
                        repetition_llm_fix.get("after"),
                    )

                    heuristic_result = run_heuristic_validation_sync(
                        generated_content,
                        status_for_validation,
                        generated_title,
                        options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
                    )
                    repetition_issues = _extract_repetition_gate_issues(heuristic_result)
                else:
                    logger.info("반복 품질 LLM 자동 보정 결과 미적용(stage=repetition_llm_repair)")

        if repetition_issues:
            issue_text = "; ".join(repetition_issues[:2])
            _append_quality_warning(
                quality_warnings,
                f"반복 품질 권장 기준 미충족: {issue_text}",
            )
            logger.warning("Soft gate - repetition criteria not satisfied: %s", issue_text)

    # 기준 미충족 시 EditorAgent가 1회 교정하도록 한다.
    speaker_gate["checked"] = True
    initial_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
    speaker_gate["initialIssues"] = initial_speaker_issues
    initial_role_issues = _extract_role_consistency_issues(
        generated_content,
        role_facts,
    )
    role_gate["initialIssues"] = initial_role_issues

    final_heuristic = run_heuristic_validation_sync(
        generated_content,
        status_for_validation,
        generated_title,
        options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
    )
    legal_issues = _extract_legal_gate_issues(final_heuristic)
    integrity_issues = _detect_integrity_gate_issues(generated_content)
    speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
    role_issues = _extract_role_consistency_issues(
        generated_content,
        role_facts,
    )
    pre_editor_extra_issues = [*integrity_issues, *speaker_issues, *role_issues]
    if pre_editor_extra_issues:
        heuristic_issues = list(final_heuristic.get("issues") or [])
        for issue in pre_editor_extra_issues:
            tagged = f"⚠️ 무결성 점검: {issue}"
            if tagged not in heuristic_issues:
                heuristic_issues.append(tagged)
        final_heuristic["issues"] = heuristic_issues

    editor_should_run = True  # EditorAgent 상시 호출 (humanize + TV 약어 + AI 수사 탐지)
    editor_purpose = "repair" if (legal_issues or pre_editor_extra_issues) else "polish"
    editor_auto_repair = {
        "attempted": False,
        "applied": False,
        "purpose": editor_purpose,
        "summary": [],
        "error": None,
    }
    editor_second_pass = {
        "attempted": False,
        "applied": False,
        "summary": [],
        "error": None,
    }
    last_mile_postprocess_applied = False
    if editor_should_run:
        editor_auto_repair["attempted"] = True
        editor_fix = _run_editor_repair_once(
            content=generated_content,
            title=generated_title,
            full_name=full_name,
            status=status_for_validation,
            target_word_count=target_word_count,
            user_keywords=user_keywords,
            gate_user_keywords=gate_user_keywords,
            validation_result=final_heuristic,
            keyword_validation=keyword_validation,
            extra_issues=pre_editor_extra_issues,
            purpose=editor_purpose,
            style_guide=style_guide,
            style_fingerprint=style_fingerprint,
            generation_profile=generation_profile,
            style_polish_mode=style_polish_mode,
            keyword_aliases=keyword_aliases,
            source_texts=[
                data.get("stanceText"),
                data.get("newsDataText"),
                pipeline_result.get("newsDataText"),
                data.get("sourceInput"),
                pipeline_result.get("sourceInput"),
            ],
        )
        editor_auto_repair["error"] = editor_fix.get("error")
        summary = editor_fix.get("editSummary")
        if isinstance(summary, list):
            editor_auto_repair["summary"] = [str(item).strip() for item in summary if str(item).strip()]

        if editor_fix.get("edited"):
            editor_candidate_content = str(editor_fix.get("content") or generated_content)
            if _apply_content_repair("editor_auto_repair", editor_candidate_content):
                editor_candidate_title = str(editor_fix.get("title") or generated_title).strip() or generated_title
                guarded_title, guard_info = _guard_draft_title_nonfatal(
                    phase="editor_auto_repair",
                    candidate_title=editor_candidate_title,
                    previous_title=title_last_valid,
                    topic=topic,
                    content=generated_content,
                    user_keywords=user_keywords,
                    full_name=full_name,
                    category=category,
                    status=status_for_validation,
                    context_analysis=context_analysis_for_title,
                    role_keyword_policy=role_keyword_policy,
                    recent_titles=request_recent_title_memory,
                    poll_fact_table=poll_fact_table,
                    poll_focus_bundle=poll_focus_bundle,
                )
                title_guard_trace.append(guard_info)
                generated_title = guarded_title
                if guard_info.get("validated") is True:
                    title_last_valid = generated_title
                elif guard_info.get("source") != "candidate":
                    logger.info(
                        "Title guard replaced editor title (phase=%s, source=%s, reason=%s)",
                        guard_info.get("phase"),
                        guard_info.get("source"),
                        guard_info.get("reason"),
                    )
                editor_auto_repair["applied"] = True
                logger.info("EditorAgent auto-repair applied before final blocker check")

                post_editor_keyword_result = validate_keyword_insertion(
                    generated_content,
                    user_keywords,
                    auto_keywords,
                    target_word_count,
                    title_text=generated_title,
                    body_min_overrides=body_min_overrides,
                    user_keyword_expected_overrides=user_keyword_expected_overrides,
                    user_keyword_max_overrides=user_keyword_max_overrides,
                )
                keyword_validation = build_keyword_validation(post_editor_keyword_result)
                post_editor_keyword_gate_ok, _ = _validate_keyword_gate(
                    keyword_validation,
                    gate_user_keywords,
                )
                if not post_editor_keyword_gate_ok:
                    editor_keyword_repair = _repair_keyword_gate_once(
                        content=generated_content,
                        title_text=generated_title,
                        user_keywords=user_keywords,
                        auto_keywords=auto_keywords,
                        target_word_count=target_word_count,
                        body_min_overrides=body_min_overrides,
                        user_keyword_expected_overrides=user_keyword_expected_overrides,
                        user_keyword_max_overrides=user_keyword_max_overrides,
                        skip_user_keywords=soft_gate_keywords,
                        role_keyword_policy=role_keyword_policy,
                    )
                    keyword_candidate = str(editor_keyword_repair.get("content") or generated_content)
                    keyword_applied = bool(editor_keyword_repair.get("edited")) and _apply_content_repair(
                        "keyword_repair_after_editor",
                        keyword_candidate,
                    )
                    if keyword_applied:
                        keyword_validation = _safe_dict(editor_keyword_repair.get("keywordValidation"))
                        repaired_counts = editor_keyword_repair.get("keywordCounts")
                        if isinstance(repaired_counts, dict):
                            keyword_counts = repaired_counts
                        editor_keyword_repair_applied = True
                        logger.info(
                            "Post-editor keyword auto-repair applied: edited=%s",
                            bool(editor_keyword_repair.get("edited")),
                        )

                final_heuristic = run_heuristic_validation_sync(
                    generated_content,
                    status_for_validation,
                    generated_title,
                    options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
                )
                legal_issues = _extract_legal_gate_issues(final_heuristic)
            else:
                logger.info("EditorAgent 자동 보정 결과 미적용(stage=editor_auto_repair)")

    # Editor 이후에는 마지막 후처리(cleanup/finalize)를 다시 태운다.
    before_postprocess_word_count = word_count
    postprocess_result = _apply_last_mile_postprocess(
        content=generated_content,
        title_text=generated_title,
        target_word_count=target_word_count,
        user_keywords=user_keywords,
        auto_keywords=auto_keywords,
        body_min_overrides=body_min_overrides,
        user_keyword_expected_overrides=user_keyword_expected_overrides,
        user_keyword_max_overrides=user_keyword_max_overrides,
        output_options=output_format_options,
        fallback_keyword_validation=keyword_validation,
        fallback_keyword_counts=keyword_counts,
    )
    generated_content = str(postprocess_result.get("content") or generated_content)
    postprocess_meta = _safe_dict(postprocess_result.get("meta"))
    if postprocess_meta:
        content_meta = postprocess_meta
    keyword_validation = _safe_dict(postprocess_result.get("keywordValidation"))
    processed_keyword_counts = postprocess_result.get("keywordCounts")
    if isinstance(processed_keyword_counts, dict):
        keyword_counts = processed_keyword_counts
    word_count = _to_int(postprocess_result.get("wordCount"), _count_chars_no_space(generated_content))
    if postprocess_result.get("edited"):
        last_mile_postprocess_applied = True
        logger.info(
            "Post-editor cleanup/finalize reapplied: %s -> %s chars",
            before_postprocess_word_count,
            word_count,
        )

    final_heuristic = run_heuristic_validation_sync(
        generated_content,
        status_for_validation,
        generated_title,
        options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
    )
    legal_issues = _extract_legal_gate_issues(final_heuristic)
    if legal_issues:
        legal_targeted_repair["attempted"] = True
        legal_items_for_repair = _extract_legal_gate_items(final_heuristic)
        logger.info(
            "선거법 자동 보정 시작: %s",
            "; ".join(_extract_legal_gate_issue_summaries(final_heuristic)[:2]),
        )
        legal_fix = _recover_legal_issues_once(
            content=generated_content,
            title=generated_title,
            legal_items=legal_items_for_repair,
            status=status_for_validation,
            target_word_count=target_word_count,
            user_keywords=user_keywords,
        )
        legal_targeted_repair["error"] = legal_fix.get("error")
        legal_summary = legal_fix.get("summary")
        if isinstance(legal_summary, list):
            legal_targeted_repair["summary"] = [
                str(item).strip()
                for item in legal_summary
                if str(item).strip()
            ]
        if legal_fix.get("edited"):
            legal_candidate = str(legal_fix.get("content") or generated_content)
            if _apply_content_repair("election_law_repair", legal_candidate):
                legal_targeted_repair["applied"] = True
                legal_repair_applied = True
                logger.info("선거법 자동 보정 적용 완료")
                final_heuristic = run_heuristic_validation_sync(
                    generated_content,
                    status_for_validation,
                    generated_title,
                    options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
                )
                legal_issues = _extract_legal_gate_issues(final_heuristic)
            else:
                logger.info("선거법 자동 보정 결과 미적용(stage=election_law_repair)")
    residual_repetition_issues = _extract_repetition_gate_issues(final_heuristic)
    residual_integrity_issues = _detect_integrity_gate_issues(generated_content)
    residual_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
    residual_role_issues = _extract_role_consistency_issues(
        generated_content,
        role_facts,
    )
    residual_legal_issues = _extract_legal_gate_issue_summaries(final_heuristic)
    residual_extra_issues = [*residual_integrity_issues, *residual_speaker_issues, *residual_role_issues]
    if editor_second_pass_enabled and (residual_repetition_issues or residual_extra_issues or residual_legal_issues):
        editor_second_pass["attempted"] = True
        logger.info(
            "EditorAgent second-pass repair triggered: %s",
            "; ".join([*(residual_repetition_issues[:2]), *(residual_extra_issues[:2]), *(residual_legal_issues[:2])]),
        )
        second_editor_fix = _run_editor_repair_once(
            content=generated_content,
            title=generated_title,
            full_name=full_name,
            status=status_for_validation,
            target_word_count=target_word_count,
            user_keywords=user_keywords,
            gate_user_keywords=gate_user_keywords,
            validation_result=final_heuristic,
            keyword_validation=keyword_validation,
            extra_issues=residual_extra_issues,
            purpose="repair",
            style_guide=style_guide,
            style_fingerprint=style_fingerprint,
            generation_profile=generation_profile,
            style_polish_mode=style_polish_mode,
            keyword_aliases=keyword_aliases,
        )
        editor_second_pass["error"] = second_editor_fix.get("error")
        second_summary = second_editor_fix.get("editSummary")
        if isinstance(second_summary, list):
            editor_second_pass["summary"] = [
                str(item).strip()
                for item in second_summary
                if str(item).strip()
            ]

        if second_editor_fix.get("edited"):
            second_editor_candidate_content = str(second_editor_fix.get("content") or generated_content)
            if _apply_content_repair("editor_second_pass", second_editor_candidate_content):
                second_editor_candidate_title = str(second_editor_fix.get("title") or generated_title).strip() or generated_title
                guarded_title, guard_info = _guard_draft_title_nonfatal(
                    phase="editor_second_pass",
                    candidate_title=second_editor_candidate_title,
                    previous_title=title_last_valid,
                    topic=topic,
                    content=generated_content,
                    user_keywords=user_keywords,
                    full_name=full_name,
                    category=category,
                    status=status_for_validation,
                    context_analysis=context_analysis_for_title,
                    role_keyword_policy=role_keyword_policy,
                    recent_titles=request_recent_title_memory,
                    poll_fact_table=poll_fact_table,
                    poll_focus_bundle=poll_focus_bundle,
                )
                title_guard_trace.append(guard_info)
                generated_title = guarded_title
                if guard_info.get("validated") is True:
                    title_last_valid = generated_title
                elif guard_info.get("source") != "candidate":
                    logger.info(
                        "Title guard replaced second-pass editor title (source=%s, reason=%s)",
                        guard_info.get("source"),
                        guard_info.get("reason"),
                    )
                editor_second_pass["applied"] = True
                logger.info("EditorAgent second-pass repair applied")

                second_postprocess = _apply_last_mile_postprocess(
                    content=generated_content,
                    title_text=generated_title,
                    target_word_count=target_word_count,
                    user_keywords=user_keywords,
                    auto_keywords=auto_keywords,
                    body_min_overrides=body_min_overrides,
                    user_keyword_expected_overrides=user_keyword_expected_overrides,
                    user_keyword_max_overrides=user_keyword_max_overrides,
                    output_options=output_format_options,
                    fallback_keyword_validation=keyword_validation,
                    fallback_keyword_counts=keyword_counts,
                )
                generated_content = str(second_postprocess.get("content") or generated_content)
                second_post_meta = _safe_dict(second_postprocess.get("meta"))
                if second_post_meta:
                    content_meta = second_post_meta
                keyword_validation = _safe_dict(second_postprocess.get("keywordValidation"))
                second_keyword_counts = second_postprocess.get("keywordCounts")
                if isinstance(second_keyword_counts, dict):
                    keyword_counts = second_keyword_counts
                word_count = _to_int(second_postprocess.get("wordCount"), _count_chars_no_space(generated_content))
                if second_postprocess.get("edited"):
                    last_mile_postprocess_applied = True
                    logger.info("Post-second-pass cleanup/finalize reapplied")

                second_keyword_gate_ok, _ = _validate_keyword_gate(keyword_validation, gate_user_keywords)
                if not second_keyword_gate_ok:
                    second_keyword_repair = _repair_keyword_gate_once(
                        content=generated_content,
                        title_text=generated_title,
                        user_keywords=user_keywords,
                        auto_keywords=auto_keywords,
                        target_word_count=target_word_count,
                        body_min_overrides=body_min_overrides,
                        user_keyword_expected_overrides=user_keyword_expected_overrides,
                        user_keyword_max_overrides=user_keyword_max_overrides,
                        skip_user_keywords=soft_gate_keywords,
                        role_keyword_policy=role_keyword_policy,
                    )
                    second_keyword_candidate = str(second_keyword_repair.get("content") or generated_content)
                    second_keyword_applied = bool(second_keyword_repair.get("edited")) and _apply_content_repair(
                        "keyword_repair_after_second_editor",
                        second_keyword_candidate,
                    )
                    if second_keyword_applied:
                        keyword_validation = _safe_dict(second_keyword_repair.get("keywordValidation"))
                        second_repaired_counts = second_keyword_repair.get("keywordCounts")
                        if isinstance(second_repaired_counts, dict):
                            keyword_counts = second_repaired_counts
                        editor_keyword_repair_applied = True
                        logger.info(
                            "Post-second-pass keyword auto-repair applied: edited=%s",
                            bool(second_keyword_repair.get("edited")),
                        )

                final_heuristic = run_heuristic_validation_sync(
                    generated_content,
                    status_for_validation,
                    generated_title,
                    options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
                )
                legal_issues = _extract_legal_gate_issues(final_heuristic)
            else:
                logger.info("EditorAgent second-pass 보정 결과 미적용(stage=editor_second_pass)")

    date_year_hint = " ".join(
        item.strip()
        for item in [event_date_hint_for_guard, topic]
        if str(item or "").strip()
    ).strip()
    title_date_repair = repair_date_weekday_pairs(
        generated_title,
        year_hint=(date_year_hint or None),
    )
    title_repaired_text = _normalize_title_surface_local(
        str(title_date_repair.get("text") or generated_title)
    )
    if title_repaired_text:
        generated_title = title_repaired_text

    content_date_repair = repair_date_weekday_pairs(
        generated_content,
        year_hint=(date_year_hint or None),
    )
    generated_content = str(content_date_repair.get("text") or generated_content)
    if content_date_repair.get("edited"):
        word_count = _count_chars_no_space(generated_content)

    title_validation = (
        title_date_repair.get("validation")
        if isinstance(title_date_repair.get("validation"), dict)
        else {}
    )
    content_validation = (
        content_date_repair.get("validation")
        if isinstance(content_date_repair.get("validation"), dict)
        else {}
    )
    date_weekday_guard = {
        "applied": bool(title_date_repair.get("edited") or content_date_repair.get("edited")),
        "yearHint": date_year_hint,
        "title": {
            "edited": bool(title_date_repair.get("edited")),
            "changes": title_date_repair.get("changes") if isinstance(title_date_repair.get("changes"), list) else [],
            "issues": title_validation.get("issues") if isinstance(title_validation.get("issues"), list) else [],
        },
        "content": {
            "edited": bool(content_date_repair.get("edited")),
            "changes": content_date_repair.get("changes") if isinstance(content_date_repair.get("changes"), list) else [],
            "issues": content_validation.get("issues") if isinstance(content_validation.get("issues"), list) else [],
        },
    }
    if date_weekday_guard.get("applied"):
        logger.info(
            "Date-weekday guard applied: title=%s content=%s",
            bool(date_weekday_guard.get("title", {}).get("edited")),
            bool(date_weekday_guard.get("content", {}).get("edited")),
        )

    title_date_repair = repair_date_weekday_pairs(
        title_last_valid,
        year_hint=(date_year_hint or None),
    )
    title_for_guard = _normalize_title_surface_local(
        str(title_date_repair.get("text") or title_last_valid)
    ) or title_last_valid

    final_guarded_title, final_title_guard = _guard_draft_title_nonfatal(
        phase="draft_output",
        candidate_title=generated_title,
        previous_title=title_for_guard,
        topic=topic,
        content=generated_content,
        user_keywords=user_keywords,
        full_name=full_name,
        category=category,
        status=status_for_validation,
        context_analysis=context_analysis_for_title,
        role_keyword_policy=role_keyword_policy,
        recent_titles=request_recent_title_memory,
        poll_fact_table=poll_fact_table,
        poll_focus_bundle=poll_focus_bundle,
    )
    title_guard_trace.append(final_title_guard)
    generated_title = final_guarded_title
    if final_title_guard.get("validated") is True:
        title_last_valid = generated_title
    elif final_title_guard.get("source") != "candidate":
        logger.info(
            "Title guard adjusted final output title (source=%s, reason=%s)",
            final_title_guard.get("source"),
            final_title_guard.get("reason"),
        )

    # 최종 반환 직전 따옴표 표면을 ASCII(U+0022)로 통일한다.
    generated_title = normalize_ascii_double_quotes(generated_title)
    generated_content = normalize_ascii_double_quotes(generated_content)
    generated_title = normalize_book_title_notation(
        generated_title,
        topic=topic,
        context_analysis=context_analysis_for_title,
        full_name=full_name,
    )
    generated_title = repair_duplicate_particles_and_tokens(generated_title)
    generated_title = _normalize_title_surface_local(generated_title) or generated_title
    generated_content = normalize_book_title_notation(
        generated_content,
        topic=topic,
        context_analysis=context_analysis_for_title,
        full_name=full_name,
    )

    final_heuristic = run_heuristic_validation_sync(
        generated_content,
        status_for_validation,
        generated_title,
        options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
    )
    legal_issues = _extract_legal_gate_issues(final_heuristic)
    final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
    if final_speaker_issues:
        speaker_gate["repairAttempted"] = True
        final_speaker_repair = _repair_speaker_consistency_once(generated_content, full_name)
        repair_candidate = str(final_speaker_repair.get("content") or generated_content).strip()
        if repair_candidate and repair_candidate != generated_content:
            corrupted, reason = _detect_content_repair_corruption(generated_content, repair_candidate)
            if not corrupted:
                generated_content = repair_candidate
                word_count = _count_chars_no_space(generated_content)
                speaker_gate["repairApplied"] = True
                repair_patterns = list(speaker_gate.get("repairPatterns") or [])
                for pattern in final_speaker_repair.get("appliedPatterns") or []:
                    if pattern not in repair_patterns:
                        repair_patterns.append(pattern)
                speaker_gate["repairPatterns"] = repair_patterns
                final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
                final_heuristic = run_heuristic_validation_sync(
                    generated_content,
                    status_for_validation,
                    generated_title,
                    options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
                )
                legal_issues = _extract_legal_gate_issues(final_heuristic)
            else:
                logger.warning("Final speaker repair skipped due to corruption risk: %s", reason)
    speaker_gate["finalIssues"] = final_speaker_issues

    final_role_issues = _extract_role_consistency_issues(
        generated_content,
        role_facts,
    )
    if final_role_issues:
        role_gate["repairAttempted"] = True
        final_role_repair = _repair_role_consistency_once(
            generated_content,
            role_facts,
        )
        role_repair_candidate = str(final_role_repair.get("content") or generated_content).strip()
        if role_repair_candidate and role_repair_candidate != generated_content:
            corrupted, reason = _detect_content_repair_corruption(generated_content, role_repair_candidate)
            if not corrupted:
                generated_content = role_repair_candidate
                word_count = _count_chars_no_space(generated_content)
                role_gate["repairApplied"] = True
                role_gate["replacements"] = list(final_role_repair.get("replacements") or [])
                final_role_issues = _extract_role_consistency_issues(
                    generated_content,
                    role_facts,
                )
                final_heuristic = run_heuristic_validation_sync(
                    generated_content,
                    status_for_validation,
                    generated_title,
                    options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
                )
                legal_issues = _extract_legal_gate_issues(final_heuristic)
            else:
                logger.warning("Final role repair skipped due to corruption risk: %s", reason)
    role_gate["finalIssues"] = final_role_issues

    if poll_fact_guard.get("enabled"):
        title_poll_result = enforce_poll_fact_consistency(
            generated_title,
            poll_fact_table,
            full_name=full_name,
            field="title",
            allow_repair=True,
        )
        repaired_title = _normalize_title_surface_local(str(title_poll_result.get("text") or generated_title))
        if repaired_title:
            generated_title = repaired_title
        poll_fact_guard["title"] = {
            "checked": int(title_poll_result.get("checked") or 0),
            "edited": bool(title_poll_result.get("edited")),
            "blockingIssues": list(title_poll_result.get("blockingIssues") or []),
            "repairs": list(title_poll_result.get("repairs") or []),
        }
        title_poll_issues = list(title_poll_result.get("blockingIssues") or [])
        if title_poll_issues:
            raise ApiError("internal", f"제목 사실관계 불일치: {title_poll_issues[0]}")

        content_poll_result = enforce_poll_fact_consistency(
            generated_content,
            poll_fact_table,
            full_name=full_name,
            field="content",
            allow_repair=True,
        )
        content_poll_text = str(content_poll_result.get("text") or generated_content).strip()
        if content_poll_text and content_poll_text != generated_content:
            generated_content = content_poll_text
            word_count = _count_chars_no_space(generated_content)
        poll_fact_guard["content"] = {
            "checked": int(content_poll_result.get("checked") or 0),
            "edited": bool(content_poll_result.get("edited")),
            "blockingIssues": list(content_poll_result.get("blockingIssues") or []),
            "warnings": list(content_poll_result.get("warnings") or []),
            "repairs": list(content_poll_result.get("repairs") or []),
        }
        content_poll_issues = list(content_poll_result.get("blockingIssues") or [])
        if content_poll_issues:
            raise ApiError("internal", f"본문 사실관계 불일치: {content_poll_issues[0]}")

        final_heuristic = run_heuristic_validation_sync(
            generated_content,
            status_for_validation,
            generated_title,
            options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
        )
        legal_issues = _extract_legal_gate_issues(final_heuristic)

    honorific_repair = _normalize_lawmaker_honorifics_once(
        generated_content,
        role_facts,
        full_name,
    )
    honorific_candidate = str(honorific_repair.get("content") or generated_content).strip()
    if honorific_candidate and honorific_candidate != generated_content:
        generated_content = honorific_candidate
        word_count = _count_chars_no_space(generated_content)
        role_gate["honorificRepairApplied"] = True
        role_gate["honorificReplacements"] = list(honorific_repair.get("replacements") or [])
        final_heuristic = run_heuristic_validation_sync(
            generated_content,
            status_for_validation,
            generated_title,
            options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
        )
        legal_issues = _extract_legal_gate_issues(final_heuristic)

    competitor_policy_repair = _repair_competitor_policy_phrase_once(
        generated_content,
        full_name=full_name,
        person_roles=role_facts,
    )
    competitor_policy_candidate = str(competitor_policy_repair.get("content") or generated_content).strip()
    if competitor_policy_candidate and competitor_policy_candidate != generated_content:
        corrupted, reason = _detect_content_repair_corruption(generated_content, competitor_policy_candidate)
        if not corrupted:
            generated_content = competitor_policy_candidate
            word_count = _count_chars_no_space(generated_content)
            role_replacements = list(role_gate.get("replacements") or [])
            for item in competitor_policy_repair.get("replacements") or []:
                text_item = str(item).strip()
                if text_item and text_item not in role_replacements:
                    role_replacements.append(text_item)
            role_gate["replacements"] = role_replacements
            final_heuristic = run_heuristic_validation_sync(
                generated_content,
                status_for_validation,
                generated_title,
                options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
            )
            legal_issues = _extract_legal_gate_issues(final_heuristic)
            final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
            final_role_issues = _extract_role_consistency_issues(
                generated_content,
                role_facts,
            )
        else:
            logger.warning("Competitor policy phrase repair skipped due to corruption risk: %s", reason)

    off_topic_poll_repair = _remove_off_topic_poll_sentences_once(
        generated_content,
        full_name=full_name,
        topic=topic,
        title_text=generated_title,
        user_keywords=user_keywords,
        role_facts=role_facts,
        poll_fact_table=poll_fact_table,
    )
    off_topic_poll_candidate = str(off_topic_poll_repair.get("content") or generated_content).strip()
    if off_topic_poll_candidate and off_topic_poll_candidate != generated_content:
        corrupted, reason = _detect_content_repair_corruption(generated_content, off_topic_poll_candidate)
        if not corrupted:
            generated_content = off_topic_poll_candidate
            word_count = _count_chars_no_space(generated_content)
            poll_actions = list(poll_fact_guard.get("offTopicSentenceActions") or [])
            for item in off_topic_poll_repair.get("actions") or []:
                text_item = str(item).strip()
                if text_item and text_item not in poll_actions:
                    poll_actions.append(text_item)
            poll_fact_guard["offTopicSentenceActions"] = poll_actions
            final_heuristic = run_heuristic_validation_sync(
                generated_content,
                status_for_validation,
                generated_title,
                options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
            )
            legal_issues = _extract_legal_gate_issues(final_heuristic)
            final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
            final_role_issues = _extract_role_consistency_issues(
                generated_content,
                role_facts,
            )
        else:
            logger.warning("Off-topic poll sentence repair skipped due to corruption risk: %s", reason)

    intent_body_repair = _repair_intent_only_role_keyword_mentions_once(
        generated_content,
        role_keyword_policy=role_keyword_policy,
    )
    intent_body_candidate = str(intent_body_repair.get("content") or generated_content).strip()
    if intent_body_candidate and intent_body_candidate != generated_content:
        corrupted, reason = _detect_content_repair_corruption(generated_content, intent_body_candidate)
        if not corrupted:
            generated_content = intent_body_candidate
            word_count = _count_chars_no_space(generated_content)
            role_replacements = list(role_gate.get("replacements") or [])
            for item in intent_body_repair.get("replacements") or []:
                text_item = str(item).strip()
                if text_item and text_item not in role_replacements:
                    role_replacements.append(text_item)
            role_gate["replacements"] = role_replacements
            final_heuristic = run_heuristic_validation_sync(
                generated_content,
                status_for_validation,
                generated_title,
                options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
            )
            legal_issues = _extract_legal_gate_issues(final_heuristic)
            final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
            final_role_issues = _extract_role_consistency_issues(
                generated_content,
                role_facts,
            )
        else:
            logger.warning("Intent-only body keyword repair skipped due to corruption risk: %s", reason)

    final_sentence_polish["attempted"] = True
    sentence_polish_result = _apply_final_sentence_polish_once(
        generated_content,
        category=category,
        writing_method=writing_method,
        full_name=full_name,
        user_keywords=user_keywords,
        role_facts=role_facts,
        poll_fact_table=poll_fact_table,
        poll_focus_bundle=poll_focus_bundle,
        style_guide=style_guide,
        style_fingerprint=style_fingerprint,
        style_polish_mode=style_polish_mode,
    )
    sentence_polish_candidate = str(sentence_polish_result.get("content") or generated_content).strip()
    final_sentence_polish["actions"] = list(sentence_polish_result.get("actions") or [])
    if sentence_polish_candidate and sentence_polish_candidate != generated_content:
        corrupted, reason = _detect_content_repair_corruption(generated_content, sentence_polish_candidate)
        if not corrupted:
            generated_content = sentence_polish_candidate
            word_count = _count_chars_no_space(generated_content)
            final_sentence_polish["applied"] = True
            final_heuristic = run_heuristic_validation_sync(
                generated_content,
                status_for_validation,
                generated_title,
                options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
            )
            legal_issues = _extract_legal_gate_issues(final_heuristic)
            final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
            final_role_issues = _extract_role_consistency_issues(
                generated_content,
                role_facts,
            )
        else:
            final_sentence_polish["skippedReason"] = str(reason or "corruption-risk")
            logger.warning("Final sentence polish skipped due to corruption risk: %s", reason)

    subheading_entity_gate["attempted"] = True
    known_person_names = _collect_known_person_names(
        full_name=full_name,
        role_facts=role_facts,
        user_keywords=user_keywords,
        poll_fact_table=poll_fact_table,
    )
    subheading_context = {
        "content": generated_content,
        "topic": topic,
        "category": category,
        "userKeywords": user_keywords,
        "knownPersonNames": known_person_names,
        "roleFacts": role_facts,
        "fullName": full_name,
        "userProfile": user_profile,
        "stanceText": str((data.get("stanceText") if isinstance(data, dict) else "") or ""),
        "preferredKeyword": (
            conflicting_role_keyword
            if conflicting_role_keyword and conflicting_role_keyword in gate_user_keywords
            else ""
        ),
    }
    try:
        subheading_result = _run_async_sync(SubheadingAgent(options={}).process(subheading_context))
    except Exception as subheading_error:  # pragma: no cover - defensive
        logger.error("SubheadingAgent 실행 실패: %s", subheading_error)
        subheading_result = {}

    subheading_result = subheading_result or {}
    subheading_candidate = str(subheading_result.get("content") or generated_content).strip()
    subheading_trace = list(subheading_result.get("h2Trace") or [])
    subheading_stats = dict(subheading_result.get("subheadingStats") or {})
    subheading_guard["trace"] = subheading_trace
    subheading_guard["stats"] = subheading_stats

    entity_replacements: list = []
    for step in subheading_stats.get("h2_repair_chain") or []:
        if isinstance(step, dict) and step.get("step") == "entity_consistency":
            reps = step.get("replacements")
            if isinstance(reps, list):
                entity_replacements.extend(reps)
    subheading_entity_gate["replacements"] = entity_replacements

    if subheading_candidate and subheading_candidate != generated_content:
        corrupted, reason = _detect_content_repair_corruption(generated_content, subheading_candidate)
        if not corrupted:
            generated_content = subheading_candidate
            word_count = _count_chars_no_space(generated_content)
            subheading_entity_gate["applied"] = bool(entity_replacements)
            subheading_guard["applied"] = True
            final_heuristic = run_heuristic_validation_sync(
                generated_content,
                status_for_validation,
                generated_title,
                options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
            )
            legal_issues = _extract_legal_gate_issues(final_heuristic)
            final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
            final_role_issues = _extract_role_consistency_issues(
                generated_content,
                role_facts,
            )
        else:
            subheading_entity_gate["skippedReason"] = str(reason or "corruption-risk")
            subheading_guard["skippedReason"] = str(reason or "corruption-risk")
            logger.warning(
                "SubheadingAgent 결과 corruption check 차단: actions=%s reason=%s",
                subheading_stats.get("actions"),
                reason,
            )

    final_integrity_issues = _detect_integrity_gate_issues(generated_content)
    final_blocking_integrity_issues = _extract_blocking_integrity_issues(final_integrity_issues)
    if final_blocking_integrity_issues:
        final_noise_fix = _repair_integrity_noise_once(generated_content)
        if final_noise_fix.get("edited"):
            final_noise_candidate = str(final_noise_fix.get("content") or generated_content)
            if _apply_content_repair("integrity_final_noise_repair", final_noise_candidate, force=True):
                noise_actions = final_noise_fix.get("actions")
                if isinstance(noise_actions, list):
                    merged_summary = list(integrity_editor_repair.get("summary") or [])
                    for item in noise_actions:
                        text_item = str(item).strip()
                        if text_item and text_item not in merged_summary:
                            merged_summary.append(text_item)
                    integrity_editor_repair["summary"] = merged_summary
                    logger.warning(
                        "Final integrity deterministic repair applied: %s",
                        ", ".join(str(item).strip() for item in noise_actions if str(item).strip()),
                    )
                _refresh_terminal_validation_state()

    if final_blocking_integrity_issues and not legal_issues:
        max_integrity_editor_passes = 2
        for pass_no in range(1, max_integrity_editor_passes + 1):
            if not final_blocking_integrity_issues or legal_issues:
                break

            integrity_editor_repair["attempted"] = int(integrity_editor_repair.get("attempted") or 0) + 1
            logger.info(
                "Final integrity editor repair triggered(pass=%s): %s",
                pass_no,
                "; ".join(final_blocking_integrity_issues[:2]),
            )
            integrity_fix = _run_editor_repair_once(
                content=generated_content,
                title=generated_title,
                full_name=full_name,
                status=status_for_validation,
                target_word_count=target_word_count,
                user_keywords=user_keywords,
                gate_user_keywords=gate_user_keywords,
                validation_result=final_heuristic,
                keyword_validation=keyword_validation,
                extra_issues=final_blocking_integrity_issues,
                purpose="polish",
                style_guide=style_guide,
                style_fingerprint=style_fingerprint,
                generation_profile=generation_profile,
                style_polish_mode=style_polish_mode,
                keyword_aliases=keyword_aliases,
            )
            integrity_editor_repair["error"] = integrity_fix.get("error")
            summary_items = integrity_fix.get("editSummary")
            if isinstance(summary_items, list):
                merged_summary = list(integrity_editor_repair.get("summary") or [])
                for item in summary_items:
                    text_item = str(item).strip()
                    if text_item and text_item not in merged_summary:
                        merged_summary.append(text_item)
                integrity_editor_repair["summary"] = merged_summary

            integrity_candidate_content = str(integrity_fix.get("content") or generated_content)
            noise_fix = _repair_integrity_noise_once(integrity_candidate_content)
            if noise_fix.get("edited"):
                integrity_candidate_content = str(noise_fix.get("content") or integrity_candidate_content)
                noise_actions = noise_fix.get("actions")
                if isinstance(noise_actions, list):
                    merged_summary = list(integrity_editor_repair.get("summary") or [])
                    for item in noise_actions:
                        text_item = str(item).strip()
                        if text_item and text_item not in merged_summary:
                            merged_summary.append(text_item)
                    integrity_editor_repair["summary"] = merged_summary
                    logger.info(
                        "Final integrity deterministic repair triggered(pass=%s): %s",
                        pass_no,
                        ", ".join(str(item).strip() for item in noise_actions if str(item).strip()),
                    )

            if not integrity_fix.get("edited") and not noise_fix.get("edited"):
                logger.info("Final integrity editor repair produced no changes(pass=%s)", pass_no)
                break

            if not _apply_content_repair(f"integrity_editor_pass_{pass_no}", integrity_candidate_content):
                logger.info("Final integrity editor repair result skipped(pass=%s)", pass_no)
                break

            integrity_editor_repair["applied"] = int(integrity_editor_repair.get("applied") or 0) + 1
            integrity_candidate_title = str(integrity_fix.get("title") or generated_title).strip() or generated_title
            guarded_title, guard_info = _guard_draft_title_nonfatal(
                phase=f"integrity_editor_pass_{pass_no}",
                candidate_title=integrity_candidate_title,
                previous_title=title_last_valid,
                topic=topic,
                content=generated_content,
                user_keywords=user_keywords,
                full_name=full_name,
                category=category,
                status=status_for_validation,
                context_analysis=context_analysis_for_title,
                role_keyword_policy=role_keyword_policy,
                recent_titles=request_recent_title_memory,
                poll_fact_table=poll_fact_table,
                poll_focus_bundle=poll_focus_bundle,
            )
            title_guard_trace.append(guard_info)
            generated_title = guarded_title
            if guard_info.get("validated") is True:
                title_last_valid = generated_title

            integrity_postprocess = _apply_last_mile_postprocess(
                content=generated_content,
                title_text=generated_title,
                target_word_count=target_word_count,
                user_keywords=user_keywords,
                auto_keywords=auto_keywords,
                body_min_overrides=body_min_overrides,
                user_keyword_expected_overrides=user_keyword_expected_overrides,
                user_keyword_max_overrides=user_keyword_max_overrides,
                output_options=output_format_options,
                fallback_keyword_validation=keyword_validation,
                fallback_keyword_counts=keyword_counts,
            )
            generated_content = str(integrity_postprocess.get("content") or generated_content).strip()
            integrity_post_meta = _safe_dict(integrity_postprocess.get("meta"))
            if integrity_post_meta:
                content_meta = integrity_post_meta
            keyword_validation = _safe_dict(integrity_postprocess.get("keywordValidation"))
            integrity_keyword_counts = integrity_postprocess.get("keywordCounts")
            if isinstance(integrity_keyword_counts, dict):
                keyword_counts = integrity_keyword_counts
            word_count = _to_int(integrity_postprocess.get("wordCount"), _count_chars_no_space(generated_content))

            _refresh_terminal_validation_state()

    speaker_gate["finalIssues"] = final_speaker_issues
    role_gate["finalIssues"] = final_role_issues

    draft_title = generated_title
    independent_final_title["draftTitle"] = draft_title
    independent_final_title["attempted"] = True
    recent_title_memory = _collect_recent_title_memory(
        data=data if isinstance(data, dict) else {},
        pipeline_result=pipeline_result if isinstance(pipeline_result, dict) else {},
        session=session,
        draft_title=draft_title,
        seed_titles=saved_recent_titles,
    )
    final_title_candidate_result = _generate_independent_final_title(
        topic=topic,
        category=category,
        content=generated_content,
        user_keywords=user_keywords,
        full_name=full_name,
        user_profile=user_profile,
        status=status_for_validation,
        data=data if isinstance(data, dict) else {},
        pipeline_result=pipeline_result if isinstance(pipeline_result, dict) else {},
        context_analysis=context_analysis_for_title,
        auto_keywords=auto_keywords,
        recent_titles=recent_title_memory,
        poll_focus_bundle=poll_focus_bundle,
        model_name=str(data.get("modelName") or ""),
    )
    independent_final_title["candidate"] = str(final_title_candidate_result.get("title") or "").strip()
    independent_final_title["score"] = _to_int(final_title_candidate_result.get("score"), 0)
    independent_final_title["type"] = str(final_title_candidate_result.get("type") or "").strip()
    independent_final_title["error"] = str(final_title_candidate_result.get("error") or "").strip()

    final_title_candidate = str(final_title_candidate_result.get("title") or "").strip()
    if final_title_candidate:
        try:
            candidate_title_date_repair = repair_date_weekday_pairs(
                final_title_candidate,
                year_hint=(date_year_hint or None),
            )
            candidate_title = _normalize_title_surface_local(
                str(candidate_title_date_repair.get("text") or final_title_candidate)
            ) or final_title_candidate
            candidate_title_validation = (
                candidate_title_date_repair.get("validation")
                if isinstance(candidate_title_date_repair.get("validation"), dict)
                else {}
            )
            date_weekday_guard["title"] = {
                "edited": bool(candidate_title_date_repair.get("edited")),
                "changes": (
                    candidate_title_date_repair.get("changes")
                    if isinstance(candidate_title_date_repair.get("changes"), list)
                    else []
                ),
                "issues": (
                    candidate_title_validation.get("issues")
                    if isinstance(candidate_title_validation.get("issues"), list)
                    else []
                ),
            }
            date_weekday_guard["applied"] = bool(
                bool(date_weekday_guard.get("content", {}).get("edited"))
                or bool(date_weekday_guard.get("title", {}).get("edited"))
            )

            independent_guarded_title, independent_title_guard = _guard_title_after_editor(
                candidate_title=candidate_title,
                previous_title="",
                topic=topic,
                content=generated_content,
                user_keywords=user_keywords,
                full_name=full_name,
                category=category,
                status=status_for_validation,
                context_analysis=context_analysis_for_title,
                role_keyword_policy=role_keyword_policy,
                poll_focus_bundle=poll_focus_bundle,
                recent_titles=recent_title_memory,
            )
            independent_title_guard["phase"] = "final_output"
            title_guard_trace.append(independent_title_guard)
            final_title_guard = independent_title_guard
            generated_title = independent_guarded_title
            title_last_valid = generated_title

            title_poll_result = enforce_poll_fact_consistency(
                generated_title,
                poll_fact_table,
                full_name=full_name,
                field="title",
                allow_repair=True,
            )
            repaired_title = _normalize_title_surface_local(str(title_poll_result.get("text") or generated_title))
            if repaired_title:
                generated_title = repaired_title
                title_last_valid = generated_title
            poll_fact_guard["title"] = {
                "checked": int(title_poll_result.get("checked") or 0),
                "edited": bool(title_poll_result.get("edited")),
                "blockingIssues": list(title_poll_result.get("blockingIssues") or []),
                "repairs": list(title_poll_result.get("repairs") or []),
            }
            title_poll_issues = list(title_poll_result.get("blockingIssues") or [])
            if title_poll_issues:
                raise ApiError("internal", f"제목 사실관계 불일치: {title_poll_issues[0]}")

            independent_final_title["applied"] = True
        except Exception as exc:
            independent_final_title["error"] = str(exc)
            independent_final_title["fallbackUsed"] = True
            rollback_title = _normalize_title_surface_local(draft_title) or draft_title
            rollback_guarded_title, rollback_guard_info = _guard_draft_title_nonfatal(
                phase="independent_final_rollback",
                candidate_title=rollback_title,
                previous_title=title_last_valid,
                topic=topic,
                content=generated_content,
                user_keywords=user_keywords,
                full_name=full_name,
                category=category,
                status=status_for_validation,
                context_analysis=context_analysis_for_title,
                role_keyword_policy=role_keyword_policy,
                recent_titles=recent_title_memory,
                poll_fact_table=poll_fact_table,
                poll_focus_bundle=poll_focus_bundle,
            )
            title_guard_trace.append(rollback_guard_info)
            generated_title = rollback_guarded_title
            if rollback_guard_info.get("validated") is True:
                title_last_valid = generated_title
            logger.warning("Independent final title rejected; using draft title: %s", exc)
    else:
        independent_final_title["fallbackUsed"] = True

    # 최종 제목이 본문 앵커(정책·기관·수치·연도) 중 하나라도 인용했는지 확인.
    # allowDegradedPass 경로가 열려 있어도 후보가 전무하거나 rollback 으로
    # draft_title 이 채택된 경로에서는 "본문 앵커 전무" 제목이 남을 수 있다.
    # 여기서 최종 content 기준으로 누수를 검출해 quality_warning 으로 노출한다
    # (배포는 막지 않되 관측 가능하게).
    final_title_anchor_warning: str = ""
    try:
        from agents.common.title_scoring import _assess_body_anchor_coverage
        anchor_params_check: Dict[str, Any] = {
            "topic": topic,
            "stanceText": str((data or {}).get("stanceText") or ""),
            "contentPreview": generated_content,
            "fullName": full_name,
            "regionLocal": str(user_profile.get("regionLocal") or ""),
            "regionMetro": str(user_profile.get("regionMetro") or ""),
            "category": category,
        }
        anchor_probe = _assess_body_anchor_coverage(generated_title, anchor_params_check)
        if (
            anchor_probe
            and not anchor_probe.get("skipped")
            and not anchor_probe.get("passed", True)
        ):
            available_map = anchor_probe.get("available") or {}
            hint_tokens: list[str] = []
            for bucket_name in ("policy", "institution", "numeric", "year"):
                for tok in (available_map.get(bucket_name) or [])[:2]:
                    tok_s = str(tok or "").strip()
                    if tok_s and tok_s not in hint_tokens:
                        hint_tokens.append(tok_s)
                if len(hint_tokens) >= 3:
                    break
            hint_suffix = (
                f" 후보: {', '.join(hint_tokens[:3])}" if hint_tokens else ""
            )
            final_title_anchor_warning = (
                "최종 제목이 본문의 구체 앵커(정책·기관·수치·연도)를 "
                "하나도 인용하지 않아 AEO 가 약합니다." + hint_suffix
            )
            logger.warning(
                "[FinalTitle] body anchor coverage 실격: title=%r anchors=%s",
                generated_title,
                available_map,
            )
            independent_final_title["finalAnchorWarning"] = final_title_anchor_warning
    except Exception as anchor_probe_exc:
        logger.debug(
            "[FinalTitle] anchor coverage probe failed: %s", anchor_probe_exc
        )

    final_heuristic = run_heuristic_validation_sync(
        generated_content,
        status_for_validation,
        generated_title,
        options={"sourceTexts": _source_texts_for_heuristic} if _source_texts_for_heuristic else None,
    )
    legal_issues = _extract_legal_gate_issues(final_heuristic)

    final_keyword_result = validate_keyword_insertion(
        generated_content,
        user_keywords=user_keywords,
        auto_keywords=auto_keywords,
        target_word_count=target_word_count,
        title_text=generated_title,
        body_min_overrides=body_min_overrides,
        user_keyword_expected_overrides=user_keyword_expected_overrides,
        user_keyword_max_overrides=user_keyword_max_overrides,
        keyword_aliases=keyword_aliases,
    )
    keyword_validation = build_keyword_validation(final_keyword_result)
    keyword_counts = _extract_keyword_counts(final_keyword_result)

    # 최종 경고는 최종 산출물 기준으로 다시 계산한다.
    quality_warnings = []
    if date_weekday_guard.get("applied"):
        _append_quality_warning(
            quality_warnings,
            "날짜-요일 불일치가 감지되어 자동 보정되었습니다.",
        )
    if independent_final_title.get("attempted") and not independent_final_title.get("applied"):
        _append_quality_warning(
            quality_warnings,
            "최종 제목 독립 생성이 실패해 가제를 유지했습니다.",
        )
    if final_title_guard.get("source") != "candidate":
        _append_quality_warning(
            quality_warnings,
            "제목 규칙 보정을 위해 자동 롤백이 적용되었습니다.",
        )
    if final_title_anchor_warning:
        _append_quality_warning(quality_warnings, final_title_anchor_warning)
    poll_content_warnings = list((_safe_dict(poll_fact_guard.get("content")).get("warnings") or []))
    if poll_content_warnings:
        _append_quality_warning(
            quality_warnings,
            f"여론조사 사실관계 경고: {'; '.join(poll_content_warnings[:2])}",
        )
    if word_count < min_required_chars:
        _append_quality_warning(
            quality_warnings,
            f"분량 권장치 미달 ({word_count}자 < {min_required_chars}자)",
        )
    # 구조 검증 경고: 섹션당 3문단 미달 체크
    _struct_h2_blocks = re.split(r'(?=<h2\b)', generated_content or '', flags=re.IGNORECASE)
    _struct_sections = [_struct_h2_blocks[0]] + _struct_h2_blocks[1:] if _struct_h2_blocks else []
    for _si, _sblock in enumerate(_struct_sections):
        _sp_count = len(re.findall(r'<p\b[^>]*>', _sblock, re.IGNORECASE))
        if _sp_count > 0 and _sp_count < 3:
            _append_quality_warning(
                quality_warnings,
                f"섹션 {_si + 1} 문단 수 부족 ({_sp_count}개 < 3개)",
            )
    final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(keyword_validation, gate_user_keywords)
    final_over_max_keywords = _collect_over_max_keywords(keyword_validation, user_keywords)
    if final_over_max_keywords:
        logger.info(
            "Keyword over-max repair snapshot: preview=%s states=%s",
            _content_log_preview(generated_content),
            _keyword_gate_log_summary(keyword_validation, user_keywords),
        )
        over_max_repair = enforce_keyword_requirements(
            generated_content,
            user_keywords=user_keywords,
            auto_keywords=auto_keywords,
            target_word_count=target_word_count,
            title_text=generated_title,
            body_min_overrides=body_min_overrides,
            user_keyword_expected_overrides=user_keyword_expected_overrides,
            user_keyword_max_overrides=user_keyword_max_overrides,
            skip_user_keywords=soft_gate_keywords,
            role_keyword_policy=role_keyword_policy,
            max_iterations=1,
        )
        over_max_candidate = str(over_max_repair.get("content") or generated_content)
        if over_max_candidate != generated_content:
            generated_content = over_max_candidate
            _warn_if_no_space_compound(generated_content, "over_max_repair")
            _refresh_terminal_validation_state()
            final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
                keyword_validation,
                gate_user_keywords,
            )
            final_over_max_keywords = _collect_over_max_keywords(keyword_validation, user_keywords)
            logger.info(
                "키워드 과다 감산 적용: remaining=%s reductions=%s",
                final_over_max_keywords,
                over_max_repair.get("reductions"),
            )
    if not final_keyword_gate_ok and "과다" not in final_keyword_gate_msg:
        # insufficient → 섹션 구조 의존 없이 마지막 <p>에 직접 강제 삽입 (last-resort backstop)
        backstop_content = force_insert_insufficient_keywords(
            generated_content,
            user_keywords=user_keywords,
            keyword_validation=keyword_validation,
            skip_user_keywords=soft_gate_keywords,
            role_keyword_policy=role_keyword_policy,
        )
        if backstop_content != generated_content:
            generated_content = backstop_content
            _warn_if_no_space_compound(generated_content, "last_resort_backstop")
            _refresh_terminal_validation_state()
            final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
                keyword_validation, gate_user_keywords
            )
            logger.info(
                "키워드 last-resort backstop 적용: %s",
                "성공" if final_keyword_gate_ok else final_keyword_gate_msg,
            )
    final_exact_preference_keywords = _collect_exact_preference_keywords(keyword_validation, gate_user_keywords)
    if final_exact_preference_keywords:
        logger.info(
            "Keyword exact-preference repair snapshot: preview=%s states=%s",
            _content_log_preview(generated_content),
            _keyword_gate_log_summary(keyword_validation, user_keywords),
        )
        exact_preference_repair = enforce_keyword_requirements(
            generated_content,
            user_keywords=user_keywords,
            auto_keywords=auto_keywords,
            target_word_count=target_word_count,
            title_text=generated_title,
            body_min_overrides=body_min_overrides,
            user_keyword_expected_overrides=user_keyword_expected_overrides,
            user_keyword_max_overrides=user_keyword_max_overrides,
            skip_user_keywords=soft_gate_keywords,
            role_keyword_policy=role_keyword_policy,
            max_iterations=1,
        )
        exact_preference_candidate = str(exact_preference_repair.get("content") or generated_content)
        if exact_preference_candidate != generated_content:
            generated_content = exact_preference_candidate
            _warn_if_no_space_compound(generated_content, "exact_preference_repair")
            _refresh_terminal_validation_state()
            final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
                keyword_validation,
                gate_user_keywords,
            )
            logger.info(
                "키워드 exact 선호 보정 적용: remaining=%s",
                _collect_exact_preference_keywords(keyword_validation, gate_user_keywords),
            )
        final_exact_preference_keywords = _collect_exact_preference_keywords(keyword_validation, gate_user_keywords)
    if final_exact_preference_keywords:
        exact_backstop_content = force_insert_preferred_exact_keywords(
            generated_content,
            user_keywords=user_keywords,
            keyword_validation=keyword_validation,
            skip_user_keywords=soft_gate_keywords,
            role_keyword_policy=role_keyword_policy,
        )
        if exact_backstop_content != generated_content:
            generated_content = exact_backstop_content
            _warn_if_no_space_compound(generated_content, "exact_backstop")
            _refresh_terminal_validation_state()
            final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
                keyword_validation,
                gate_user_keywords,
            )
            logger.info(
                "키워드 exact backstop 적용: remaining=%s",
                _collect_exact_preference_keywords(keyword_validation, gate_user_keywords),
            )
        final_exact_preference_keywords = _collect_exact_preference_keywords(keyword_validation, gate_user_keywords)
    final_over_max_keywords = _collect_over_max_keywords(keyword_validation, user_keywords)
    if final_over_max_keywords:
        logger.info(
            "Keyword trailing over-max repair snapshot: preview=%s states=%s",
            _content_log_preview(generated_content),
            _keyword_gate_log_summary(keyword_validation, user_keywords),
        )
        final_over_max_repair = enforce_keyword_requirements(
            generated_content,
            user_keywords=user_keywords,
            auto_keywords=auto_keywords,
            target_word_count=target_word_count,
            title_text=generated_title,
            body_min_overrides=body_min_overrides,
            user_keyword_expected_overrides=user_keyword_expected_overrides,
            user_keyword_max_overrides=user_keyword_max_overrides,
            skip_user_keywords=soft_gate_keywords,
            role_keyword_policy=role_keyword_policy,
            max_iterations=1,
        )
        final_over_max_candidate = str(final_over_max_repair.get("content") or generated_content)
        if final_over_max_candidate != generated_content:
            generated_content = final_over_max_candidate
            _warn_if_no_space_compound(generated_content, "final_over_max_repair")
            _refresh_terminal_validation_state()
            final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
                keyword_validation,
                gate_user_keywords,
            )
            final_exact_preference_keywords = _collect_exact_preference_keywords(keyword_validation, gate_user_keywords)
            final_over_max_keywords = _collect_over_max_keywords(keyword_validation, user_keywords)
            logger.info(
                "키워드 backstop 후행 과다 감산 적용: remaining=%s reductions=%s",
                final_over_max_keywords,
                final_over_max_repair.get("reductions"),
            )

    tail_intent_body_repair = _repair_intent_only_role_keyword_mentions_once(
        generated_content,
        role_keyword_policy=role_keyword_policy,
    )
    tail_intent_candidate = str(tail_intent_body_repair.get("content") or generated_content).strip()
    if tail_intent_candidate and tail_intent_candidate != generated_content:
        corrupted, reason = _detect_content_repair_corruption(generated_content, tail_intent_candidate)
        if not corrupted:
            generated_content = tail_intent_candidate
            role_replacements = list(role_gate.get("replacements") or [])
            for item in tail_intent_body_repair.get("replacements") or []:
                text_item = str(item).strip()
                if text_item and text_item not in role_replacements:
                    role_replacements.append(text_item)
            role_gate["replacements"] = role_replacements
            _refresh_terminal_validation_state()
            final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
                keyword_validation,
                gate_user_keywords,
            )
            logger.info(
                "키워드 후행 intent-only 본문 표면 보정 적용: %s",
                tail_intent_body_repair.get("replacements") or [],
            )
        else:
            logger.warning("Tail intent-only body repair skipped due to corruption risk: %s", reason)

    tail_role_issues = _extract_role_consistency_issues(
        generated_content,
        role_facts,
    )
    if tail_role_issues:
        role_gate["repairAttempted"] = True
        tail_role_repair = _repair_role_consistency_once(
            generated_content,
            role_facts,
        )
        tail_role_candidate = str(tail_role_repair.get("content") or generated_content).strip()
        if tail_role_candidate and tail_role_candidate != generated_content:
            corrupted, reason = _detect_content_repair_corruption(generated_content, tail_role_candidate)
            if not corrupted:
                generated_content = tail_role_candidate
                role_gate["repairApplied"] = True
                role_replacements = list(role_gate.get("replacements") or [])
                for item in tail_role_repair.get("replacements") or []:
                    text_item = str(item).strip()
                    if text_item and text_item not in role_replacements:
                        role_replacements.append(text_item)
                role_gate["replacements"] = role_replacements
                _refresh_terminal_validation_state()
                final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
                    keyword_validation,
                    gate_user_keywords,
                )
                logger.info(
                    "키워드 후행 직함 정합성 보정 적용: %s",
                    tail_role_repair.get("replacements") or [],
                )
            else:
                logger.warning("Tail role consistency repair skipped due to corruption risk: %s", reason)

    late_observer_scrub = _drop_observer_frame_sentences_once(generated_content)
    if late_observer_scrub.get("edited"):
        generated_content = str(late_observer_scrub.get("content") or generated_content)
        _refresh_terminal_validation_state()
        final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
            keyword_validation,
            gate_user_keywords,
        )
        logger.info(
            "최종 관찰자 시점 문장 제거 적용: %s",
            late_observer_scrub.get("actions") or [],
        )

    final_self_reference_repair = _repair_self_reference_placeholders_once(
        generated_content,
        full_name=full_name,
    )
    if final_self_reference_repair.get("edited"):
        generated_content = str(final_self_reference_repair.get("content") or generated_content)
        _refresh_terminal_validation_state()
        final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
            keyword_validation,
            gate_user_keywords,
        )
        logger.info(
            "최종 자기지시 placeholder 복원 적용: %s",
            final_self_reference_repair.get("actions") or [],
        )

    final_identity_signature_repair = _repair_identity_signature_exact_form_once(
        generated_content,
        full_name=full_name,
    )
    if final_identity_signature_repair.get("edited"):
        generated_content = str(final_identity_signature_repair.get("content") or generated_content)
        _refresh_terminal_validation_state()
        final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
            keyword_validation,
            gate_user_keywords,
        )
        logger.info(
            "최종 정체성 시그니처 복원 적용: %s",
            final_identity_signature_repair.get("actions") or [],
        )

    final_career_dedupe = _dedupe_repeated_career_fact_sentences_once(generated_content)
    if final_career_dedupe.get("edited"):
        generated_content = str(final_career_dedupe.get("content") or generated_content)
        _refresh_terminal_validation_state()
        final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
            keyword_validation,
            gate_user_keywords,
        )
        logger.info(
            "최종 이력 문장 중복 제거 적용: %s",
            final_career_dedupe.get("actions") or [],
        )

    final_section_lane_repair = _apply_section_semantic_lane_repair_once(
        generated_content,
        category=category,
    )
    if final_section_lane_repair.get("edited"):
        generated_content = str(final_section_lane_repair.get("content") or generated_content)
        _refresh_terminal_validation_state()
        final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
            keyword_validation,
            gate_user_keywords,
        )
        logger.info(
            "Final section lane repair applied: %s",
            final_section_lane_repair.get("actions") or [],
        )

    final_cross_section_contract = _apply_cross_section_contract_once(
        generated_content,
        category=category,
        full_name=full_name,
    )
    if final_cross_section_contract.get("edited"):
        generated_content = str(final_cross_section_contract.get("content") or generated_content)
        _refresh_terminal_validation_state()
        final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
            keyword_validation,
            gate_user_keywords,
        )
        logger.info(
            "Final cross-section contract dedupe applied: %s",
            final_cross_section_contract.get("actions") or [],
        )

    final_fragment_scrub = _scrub_broken_poll_fragments_once(
        generated_content,
        known_names=known_person_names,
    )
    if final_fragment_scrub.get("edited"):
        generated_content = str(final_fragment_scrub.get("content") or generated_content)
        _refresh_terminal_validation_state()
        final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
            keyword_validation,
            gate_user_keywords,
        )
        logger.info(
            "최종 poll/news fragment scrub 적용: %s",
            final_fragment_scrub.get("actions") or [],
        )

    terminal_spacing_cleanup = _repair_terminal_sentence_spacing_once(generated_content)
    if terminal_spacing_cleanup.get("edited"):
        generated_content = str(terminal_spacing_cleanup.get("content") or generated_content)
        _refresh_terminal_validation_state()
        final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
            keyword_validation,
            gate_user_keywords,
        )
        logger.info(
            "최종 문장부호 공백 복원 적용: %s",
            terminal_spacing_cleanup.get("actions") or [],
        )

    final_closing_sentence_repair = _ensure_closing_section_min_sentences_once(
        generated_content,
        full_name=full_name,
        writing_method=writing_method,
        user_keywords=user_keywords,
    )
    if final_closing_sentence_repair.get("edited"):
        generated_content = str(final_closing_sentence_repair.get("content") or generated_content)
        _refresh_terminal_validation_state()
        final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
            keyword_validation,
            gate_user_keywords,
        )
        logger.info(
            "최종 결론 최소 문장 복원 적용: %s",
            final_closing_sentence_repair.get("actions") or [],
        )

    final_section_length_backstop["attempted"] = True
    section_length_backstop_result = _apply_terminal_section_length_backstop_once(
        generated_content,
        length_spec=_build_terminal_section_length_spec(
            target_word_count=target_word_count,
            stance_count=stance_count,
        ),
    )
    final_section_length_backstop["actions"] = list(section_length_backstop_result.get("actions") or [])
    if section_length_backstop_result.get("edited"):
        generated_content = str(section_length_backstop_result.get("content") or generated_content)
        final_section_length_backstop["applied"] = True
        _refresh_terminal_validation_state()
        final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
            keyword_validation,
            gate_user_keywords,
        )
        post_backstop_low_signal = _drop_low_signal_analysis_sentences_once(generated_content)
        if post_backstop_low_signal.get("edited"):
            generated_content = str(post_backstop_low_signal.get("content") or generated_content)
            _refresh_terminal_validation_state()
            final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
                keyword_validation,
                gate_user_keywords,
            )
            logger.info(
                "최종 길이 보정 후 generic 문장 제거 적용: %s",
                post_backstop_low_signal.get("actions") or [],
            )
    if not final_keyword_gate_ok:
        _append_quality_warning(
            quality_warnings,
            f"키워드 권장 기준 미충족: {final_keyword_gate_msg}",
        )
    if final_over_max_keywords:
        _append_quality_warning(
            quality_warnings,
            f"키워드 과다 감산 미해결: {', '.join(final_over_max_keywords[:2])}",
        )
    if final_exact_preference_keywords:
        _append_quality_warning(
            quality_warnings,
            f"정확 일치 검색어 1회 미확보: {', '.join(final_exact_preference_keywords[:2])}",
        )
    final_secondary_keyword_issues = _collect_secondary_keyword_soft_issues(keyword_validation, gate_user_keywords)
    if final_secondary_keyword_issues:
        _append_quality_warning(
            quality_warnings,
            f"보조 키워드 권장 기준 미충족: {'; '.join(final_secondary_keyword_issues[:2])}",
        )
    final_repetition_issues = _extract_repetition_gate_issues(final_heuristic)
    if final_repetition_issues:
        _append_quality_warning(
            quality_warnings,
            f"반복 품질 권장 기준 미충족: {'; '.join(final_repetition_issues[:2])}",
        )
    if final_integrity_issues:
        _append_quality_warning(
            quality_warnings,
            f"문장 무결성 점검 경고: {'; '.join(final_integrity_issues[:2])}",
        )
    if final_speaker_issues:
        _append_quality_warning(
            quality_warnings,
            f"화자 정체성 점검 경고: {'; '.join(final_speaker_issues[:2])}",
        )
    if final_role_issues:
        _append_quality_warning(
            quality_warnings,
            f"직함 정합성 점검 경고: {'; '.join(final_role_issues[:2])}",
        )
    if content_repair_rollbacks:
        _append_quality_warning(
            quality_warnings,
            "문장 파손 위험이 감지된 일부 자동 보정은 롤백되었습니다.",
        )
    if bool(content_meta.get("metaRemoved") is True):
        _append_quality_warning(
            quality_warnings,
            "본문에 섞인 메타 블록(조사개요/카테고리/검색어 집계 등)을 분리했습니다.",
        )
    if final_sentence_polish.get("applied") is True:
        _append_quality_warning(
            quality_warnings,
            "최종 문장 윤문 안전망이 적용되었습니다.",
        )
    if final_section_length_backstop.get("applied") is True:
        _append_quality_warning(
            quality_warnings,
            "최종 섹션 길이 보정이 적용되었습니다.",
        )
    if subheading_entity_gate.get("applied") is True:
        _append_quality_warning(
            quality_warnings,
            "소제목-본문 인물 불일치를 자동 보정했습니다.",
        )
    if speaker_gate.get("repairApplied") is True:
        _append_quality_warning(
            quality_warnings,
            "화자 정체성 불일치 문장을 자동 보정했습니다.",
        )
    if role_gate.get("repairApplied") is True:
        _append_quality_warning(
            quality_warnings,
            "인물 직함 불일치 문장을 입력 근거 기준으로 자동 보정했습니다.",
        )
    if int(integrity_editor_repair.get("applied") or 0) > 0:
        _append_quality_warning(
            quality_warnings,
            "최종 무결성 게이트에서 문장 윤문 재검사가 자동 적용되었습니다.",
        )
    if legal_targeted_repair.get("applied") is True:
        _append_quality_warning(
            quality_warnings,
            "선거법 차단 표현을 문장 단위로 자동 보정했습니다.",
        )

    if final_speaker_issues and any("placeholder" in str(issue or "") for issue in final_speaker_issues):
        terminal_self_reference_repair = _repair_self_reference_placeholders_once(
            generated_content,
            full_name=full_name,
        )
        terminal_self_reference_candidate = str(
            terminal_self_reference_repair.get("content") or generated_content
        ).strip()
        if terminal_self_reference_candidate and terminal_self_reference_candidate != generated_content:
            corrupted, reason = _detect_content_repair_corruption(
                generated_content,
                terminal_self_reference_candidate,
            )
            if not corrupted:
                generated_content = terminal_self_reference_candidate
                _refresh_terminal_validation_state()
                final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
                    keyword_validation,
                    gate_user_keywords,
                )
                logger.info(
                    "최종 speaker placeholder terminal repair 적용: %s",
                    terminal_self_reference_repair.get("actions") or [],
                )
            else:
                logger.warning(
                    "Terminal speaker placeholder repair skipped due to corruption risk: %s",
                    reason,
                )

    final_structure_gate["attempted"] = True
    structure_base_content = str(generated_content or "").strip()
    normalized_structure_content = normalize_section_p_count(structure_base_content)
    if normalized_structure_content != structure_base_content:
        generated_content = normalized_structure_content
        word_count = _count_chars_no_space(generated_content)
        final_structure_gate["normalized"] = True
        _refresh_terminal_validation_state()
        final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(
            keyword_validation,
            gate_user_keywords,
        )
        logger.info("최종 구조 정규화 적용: 섹션 문단 수 재분배")

    final_structure_issues = _collect_section_paragraph_issues(
        str(generated_content or "").strip(),
        min_p=3,
    )
    final_structure_gate["issues"] = final_structure_issues
    if final_structure_gate.get("normalized") is True:
        _append_quality_warning(
            quality_warnings,
            "최종 구조 게이트에서 섹션 문단 수 정규화가 적용되었습니다.",
        )

    # 하드 차단: 화자 정체성 불일치, 문장 무결성 치명 오류, 선거법 위반.
    if final_structure_issues:
        issue_text = "; ".join(final_structure_issues[:2])
        logger.warning(
            "QUALITY_METRIC generate_posts outcome=blocked reason=structure warnings=%s issues=%s",
            len(quality_warnings),
            len(final_structure_issues),
        )
        raise ApiError(
            "failed-precondition",
            f"[BLOCKER:STRUCTURE] {issue_text}",
        )

    if final_speaker_issues:
        speaker_gate["blocked"] = True
        issue_text = "; ".join(final_speaker_issues[:2])
        logger.warning(
            "QUALITY_METRIC generate_posts outcome=blocked reason=speaker_identity warnings=%s repairs=%s",
            len(quality_warnings),
            int(speaker_gate.get("repairApplied") is True),
        )
        raise ApiError(
            "failed-precondition",
            f"[BLOCKER:SPEAKER_IDENTITY] {issue_text}",
        )

    if final_blocking_integrity_issues:
        issue_text = "; ".join(final_blocking_integrity_issues[:2])
        logger.warning(
            "QUALITY_METRIC generate_posts outcome=blocked reason=integrity warnings=%s repairs=%s",
            len(quality_warnings),
            int(integrity_editor_repair.get("applied") or 0),
        )
        raise ApiError(
            "failed-precondition",
            f"[BLOCKER:INTEGRITY] {issue_text}",
        )

    if legal_issues:
        legal_issue_summaries = _extract_legal_gate_issue_summaries(final_heuristic)
        issue_text = "; ".join((legal_issue_summaries or legal_issues)[:2])
        logger.warning(
            "QUALITY_METRIC generate_posts outcome=blocked first_pass=%s blockers=%s warnings=%s repairs=%s",
            int(first_pass_passed),
            len(legal_issue_summaries or legal_issues),
            len(quality_warnings),
            int(
                any(
                    [
                        length_repair_applied,
                        keyword_repair_applied,
                        repetition_rule_repair_applied,
                        repetition_llm_repair_applied,
                        legal_repair_applied,
                        bool(editor_auto_repair.get("applied")),
                        bool(editor_second_pass.get("applied")),
                        int(integrity_editor_repair.get("applied") or 0) > 0,
                        editor_keyword_repair_applied,
                        last_mile_postprocess_applied,
                    ]
                )
            ),
        )
        raise ApiError(
            "failed-precondition",
            f"[BLOCKER:ELECTION_LAW] {issue_text}",
        )

    session = remember_session_generated_title(
        uid,
        session,
        generated_title,
        is_admin=is_admin,
    )

    # 생성 성공 후 attempts / 사용량 업데이트
    session = increment_session_attempts(uid, session, is_admin=is_admin, is_tester=is_tester)
    session = _safe_dict(session)
    _apply_usage_updates_after_success(uid, is_admin=is_admin, is_tester=is_tester, session=session)

    progress.step_validating()
    progress.step_finalizing()
    progress.complete()

    terminal_output_addons = _restore_terminal_output_addons_once(
        generated_content,
        output_options=output_format_options,
        content_meta=content_meta,
    )
    if terminal_output_addons.get("edited"):
        generated_content = str(terminal_output_addons.get("content") or generated_content)
        word_count = _count_chars_no_space(generated_content)
        logger.info(
            "Terminal output addons restored: %s",
            terminal_output_addons.get("actions") or [],
        )

    generated_at = datetime.utcnow().isoformat() + "Z"
    now_ms = int(time.time() * 1000)
    display_keyword_validation = _build_display_keyword_validation(
        keyword_validation,
        soft_keywords=soft_gate_keywords,
        shadowed_map=keyword_gate_policy.get("shadowedMap") if isinstance(keyword_gate_policy, dict) else None,
    )
    source_input = str(
        data.get("sourceInput")
        or data.get("sourceContent")
        or data.get("originalContent")
        or data.get("inputContent")
        or data.get("rawContent")
        or data.get("prompt")
        or data.get("topic")
        or ""
    ).strip()
    source_type = str(
        data.get("sourceType")
        or data.get("inputType")
        or data.get("contentType")
        or data.get("writingSource")
        or "blog_draft"
    ).strip()
    draft_data = {
        "id": f"draft_{now_ms}",
        "title": generated_title,
        "content": generated_content,
        "wordCount": word_count,
        "category": category,
        "subCategory": str(sub_category or ""),
        "keywords": data.get("keywords") or "",
        "sourceInput": source_input,
        "sourceType": source_type,
        "generatedAt": generated_at,
    }

    attempts_after = _to_int(session.get("attempts"), attempts + 1)
    can_regenerate = attempts_after < max_attempts

    message = "원고가 성공적으로 생성되었습니다"
    if daily_limit_warning:
        message += (
            "\n\n⚠️ 하루 3회 이상 원고를 생성하셨습니다. 네이버 블로그 정책상 과도한 발행은 스팸으로 "
            "분류될 수 있으므로, 반드시 마지막 포스팅으로부터 3시간 경과 후 발행해 주세요"
        )
    if quality_warnings:
        message += "\n\n⚠️ 자동 품질 보정 후에도 일부 권장 기준이 남아 있으니 발행 전 확인해 주세요."
    if can_regenerate:
        message += f"\n\n💡 마음에 들지 않으시면 재생성을 {max_attempts - attempts_after}회 더 하실 수 있습니다."

    logger.info(
        "QUALITY_METRIC generate_posts outcome=success first_pass=%s warnings=%s repairs=%s editor_applied=%s",
        int(first_pass_passed),
        len(quality_warnings),
        int(
            any(
                [
                    length_repair_applied,
                    keyword_repair_applied,
                    repetition_rule_repair_applied,
                    repetition_llm_repair_applied,
                    legal_repair_applied,
                    bool(editor_auto_repair.get("applied")),
                    bool(editor_second_pass.get("applied")),
                    editor_keyword_repair_applied,
                    last_mile_postprocess_applied,
                ]
            )
        ),
        bool(editor_auto_repair.get("applied")),
    )

    # ── 최종 본문 기준 SEO 재채점 ──
    # Orchestrator 단계의 seoPassed는 후처리 전 상태 기준이므로,
    # 최종 generated_content로 키워드·구조·반복을 재검증한다.
    _seo_final = _rescore_seo(generated_content, generated_title, user_keywords)
    seo_passed = _seo_final

    return {
        "success": True,
        "message": message,
        "dailyLimitWarning": daily_limit_warning,
        "drafts": draft_data,
        "sessionId": session.get("sessionId"),
        "attempts": attempts_after,
        "maxAttempts": max_attempts,
        "canRegenerate": can_regenerate,
        "metadata": {
            "generatedAt": generated_at,
            "userId": uid,
            "processingTime": started_ms,
            "classification": pipeline_result.get("classificationMeta") or classification_meta,
            "multiAgent": {
                "enabled": True,
                "pipeline": "python-step-functions",
                "compliancePassed": compliance_passed,
                "complianceIssues": 0,
                "seoPassed": seo_passed,
                "keywords": pipeline_result.get("keywords") or user_keywords,
                "keywordValidation": display_keyword_validation or None,
                "duration": None,
                "partial": bool(pipeline_result.get("partial") is True),
                "partialReason": pipeline_result.get("partialReason"),
                "timeoutMs": None,
                "agentsCompleted": pipeline_result.get("agentsCompleted") or [],
                "lastAgent": pipeline_result.get("lastAgent"),
                "appliedStrategy": writing_method,
                "keywordCounts": keyword_counts,
                "wordCount": word_count,
                "qualityGate": {
                    "mode": "soft-first",
                    "hardBlockers": ["STRUCTURE", "SPEAKER_IDENTITY", "INTEGRITY", "ELECTION_LAW"],
                    "warnings": quality_warnings,
                    "warningCount": len(quality_warnings),
                    "titleGuard": {
                        "applied": any(
                            str(item.get("source") or "") != "candidate"
                            for item in title_guard_trace
                            if isinstance(item, dict)
                        ),
                        "trace": title_guard_trace,
                    },
                    "independentFinalTitle": independent_final_title,
                    "dateWeekdayGuard": date_weekday_guard,
                    "editorPolishEnabled": editor_polish_enabled,
                    "firstPass": {
                        "passed": first_pass_passed,
                        "failureReasons": first_pass_failure_reasons,
                        "signals": {
                            "lengthOk": initial_length_ok,
                            "keywordOk": initial_keyword_gate_ok,
                            "repetitionIssueCount": len(initial_repetition_issues),
                            "legalIssueCount": len(initial_legal_issues),
                            "keywordMessage": initial_keyword_gate_msg if not initial_keyword_gate_ok else "",
                        },
                    },
                    "repairTrace": {
                        "lengthRepairApplied": length_repair_applied,
                        "keywordRepairApplied": keyword_repair_applied,
                        "repetitionRuleRepairApplied": repetition_rule_repair_applied,
                        "repetitionLlmRepairApplied": repetition_llm_repair_applied,
                        "legalRepairApplied": legal_repair_applied,
                        "legalTargetedRepairAttempted": bool(legal_targeted_repair.get("attempted")),
                        "legalTargetedRepairSummary": list(legal_targeted_repair.get("summary") or []),
                        "legalTargetedRepairError": str(legal_targeted_repair.get("error") or ""),
                        "editorKeywordRepairApplied": editor_keyword_repair_applied,
                        "editorSecondPassApplied": bool(editor_second_pass.get("applied")),
                        "finalSentencePolishApplied": bool(final_sentence_polish.get("applied")),
                        "finalSentencePolishActions": list(final_sentence_polish.get("actions") or []),
                        "finalSentencePolishSkippedReason": str(
                            final_sentence_polish.get("skippedReason") or ""
                        ),
                        "subheadingEntityRepairApplied": bool(subheading_entity_gate.get("applied")),
                        "subheadingEntityReplacements": list(subheading_entity_gate.get("replacements") or []),
                        "subheadingEntitySkippedReason": str(
                            subheading_entity_gate.get("skippedReason") or ""
                        ),
                        "subheadingGuardApplied": bool(subheading_guard.get("applied")),
                        "subheadingTrace": list(subheading_guard.get("trace") or []),
                        "subheadingStats": dict(subheading_guard.get("stats") or {}),
                        "subheadingGuardSkippedReason": str(
                            subheading_guard.get("skippedReason") or ""
                        ),
                        "integrityEditorRepairAttempted": int(integrity_editor_repair.get("attempted") or 0),
                        "integrityEditorRepairApplied": int(integrity_editor_repair.get("applied") or 0),
                        "integrityEditorRepairError": str(integrity_editor_repair.get("error") or ""),
                        "integrityEditorRepairSummary": list(integrity_editor_repair.get("summary") or []),
                        "lastMilePostprocessApplied": last_mile_postprocess_applied,
                        "finalStructureGate": final_structure_gate,
                        "contentRepairSteps": content_repair_steps,
                        "contentRepairMaxSteps": max_content_repair_steps,
                        "contentRepairRollbacks": content_repair_rollbacks,
                    },
                    "editorAutoRepair": editor_auto_repair,
                    "editorSecondPass": editor_second_pass,
                    "speakerGate": speaker_gate,
                    "roleGate": role_gate,
                    "pollFactGuard": poll_fact_guard,
                    "contentMeta": content_meta or None,
                },
            },
            "seo": {
                "passed": seo_passed,
                "keywordValidation": display_keyword_validation or None,
            },
        },
    }


def handle_generate_posts(req: https_fn.CallableRequest) -> Dict[str, Any]:
    progress: Optional[ProgressTracker] = None
    try:
        data = req.data if isinstance(req.data, dict) else {}
        if isinstance(data.get("data"), dict):
            data = data["data"]
        uid = req.auth.uid if req.auth else ""
        progress_session_id = str(data.get("progressSessionId") or f"{uid}_{int(time.time() * 1000)}")
        progress = ProgressTracker(progress_session_id)
        return handle_generate_posts_call(req)
    except ApiError as exc:
        logger.warning("generatePosts 처리 실패(ApiError): %s", exc)
        if progress:
            progress.error(str(exc))
        raise https_fn.HttpsError(exc.code, str(exc)) from exc
    except Exception as exc:
        logger.exception("generatePosts 처리 실패")
        if progress:
            progress.error(str(exc))
        raise https_fn.HttpsError("internal", f"원고 생성에 실패했습니다: {exc}") from exc


class _FakeCallableAuth:
    __slots__ = ("uid", "token")

    def __init__(self, uid: str, token: Dict[str, Any]):
        self.uid = uid
        self.token = token


class _FakeCallableRequest:
    __slots__ = ("data", "auth", "raw_request")

    def __init__(self, data: Dict[str, Any], auth: Optional[_FakeCallableAuth], raw_request: Any):
        self.data = data
        self.auth = auth
        self.raw_request = raw_request


def _error_body(status: str, message: str) -> str:
    return json.dumps({"error": {"status": status, "message": message}}, ensure_ascii=False)


def handle_generate_posts_request(req: https_fn.Request) -> https_fn.Response:
    """on_request 래퍼 — heartbeat 스트리밍으로 idle TCP reset 방지.

    on_call 프로토콜(요청 body: {"data": {...}}, 응답 body: {"result": {...}} or {"error": {...}})을
    그대로 유지하되, 백그라운드 스레드에서 파이프라인을 돌리면서 상위 HTTP 본문에는 ~25초 간격으로
    공백 1바이트를 흘려 보낸다. JSON 파서는 선두 공백을 무시하므로 최종 응답 파싱은 영향이 없다.

    Why: 파이프라인 runtime이 ~120s를 넘길 때 일부 NAT/ISP가 idle TCP를 RST로 끊어서
    ERR_CONNECTION_RESET이 클라이언트에 뜨는 문제(서버는 정상 완료) 방지용.
    """
    import queue
    import threading
    from firebase_admin import auth as fb_auth

    if req.method == "OPTIONS":
        return https_fn.Response("", status=204)

    if req.method != "POST":
        return https_fn.Response(
            _error_body("INVALID_ARGUMENT", "POST 요청만 허용됩니다."),
            status=405,
            mimetype="application/json",
        )

    auth_header = req.headers.get("Authorization") or req.headers.get("authorization") or ""
    if not auth_header.startswith("Bearer "):
        return https_fn.Response(
            _error_body("UNAUTHENTICATED", "로그인이 필요합니다."),
            status=401,
            mimetype="application/json",
        )

    id_token = auth_header.split("Bearer ", 1)[1].strip()
    try:
        decoded = fb_auth.verify_id_token(id_token)
    except Exception as exc:
        logger.warning("[generatePosts] ID 토큰 검증 실패: %s", exc)
        return https_fn.Response(
            _error_body("UNAUTHENTICATED", "인증 토큰 검증 실패"),
            status=401,
            mimetype="application/json",
        )

    uid = str(decoded.get("uid") or decoded.get("user_id") or "").strip()
    if not uid:
        return https_fn.Response(
            _error_body("UNAUTHENTICATED", "사용자 식별 불가"),
            status=401,
            mimetype="application/json",
        )

    body = req.get_json(silent=True) or {}
    if not isinstance(body, dict):
        body = {}
    inner_data = body.get("data", body)
    if not isinstance(inner_data, dict):
        inner_data = {}

    fake_req = _FakeCallableRequest(
        data=inner_data,
        auth=_FakeCallableAuth(uid=uid, token=decoded),
        raw_request=req,
    )

    result_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue(maxsize=1)

    def _worker() -> None:
        try:
            result = handle_generate_posts(fake_req)
            result_queue.put(("ok", result))
        except https_fn.HttpsError as exc:
            code = getattr(exc, "code", None)
            code_name = getattr(code, "name", None) or str(code) or "INTERNAL"
            message = str(getattr(exc, "message", None) or exc)
            result_queue.put(("err", {"status": code_name.upper(), "message": message}))
        except Exception as exc:  # noqa: BLE001
            logger.exception("[generatePosts stream] worker 미처리 예외")
            result_queue.put(("err", {"status": "INTERNAL", "message": f"원고 생성에 실패했습니다: {exc}"}))

    worker_thread = threading.Thread(target=_worker, name="generatePosts-worker", daemon=True)
    worker_thread.start()

    HEARTBEAT_INTERVAL_SEC = 25

    def _stream():
        yield " "  # 초기 flush로 헤더/상태 커밋
        while True:
            try:
                kind, payload = result_queue.get(timeout=HEARTBEAT_INTERVAL_SEC)
            except queue.Empty:
                yield " "
                continue
            if kind == "ok":
                yield json.dumps({"result": payload}, ensure_ascii=False)
            else:
                yield json.dumps({"error": payload}, ensure_ascii=False)
            return

    return https_fn.Response(
        _stream(),
        status=200,
        mimetype="application/json",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Content-Type-Options": "nosniff",
            "X-Accel-Buffering": "no",
        },
    )
