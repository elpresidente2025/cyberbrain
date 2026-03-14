"""
generatePosts Python onCall handler.

Node `handlers/posts.js`의 generatePosts 엔트리 역할을 Python으로 이관한다.
핵심 생성 로직은 기존 Step Functions 파이프라인(`pipeline_start` + Cloud Tasks)을 재사용한다.
"""

from __future__ import annotations

import asyncio
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

from agents.common.poll_citation import build_poll_citation_text
from agents.common.role_keyword_policy import (
    ROLE_KEYWORD_PATTERN as COMMON_ROLE_KEYWORD_PATTERN,
    ROLE_SURFACE_PATTERN as COMMON_ROLE_SURFACE_PATTERN,
    build_role_keyword_intent_text,
    build_role_keyword_policy,
    extract_person_role_facts_from_text as extract_person_role_facts_from_text_common,
    extract_role_keyword_parts,
    is_role_keyword_intent_surface,
    normalize_role_label as normalize_role_label_common,
    roles_equivalent as roles_equivalent_common,
)
from services.posts.content_processor import cleanup_post_content, remove_grammatical_errors
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
    normalize_ascii_double_quotes,
    normalize_book_title_notation,
)
from services.posts.poll_fact_guard import (
    build_poll_matchup_fact_table,
    enforce_poll_fact_consistency,
)
from services.posts.poll_focus_bundle import build_poll_focus_bundle
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
ROLE_TOKEN_PRIORITY: tuple[tuple[str, str], ...] = (
    ("국회의원", "국회의원"),
    ("의원", "국회의원"),
    ("당대표", "당대표"),
    ("원내대표", "원내대표"),
    ("대표", "대표"),
    ("위원장", "위원장"),
    ("장관", "장관"),
    ("구청장", "구청장"),
    ("군수", "군수"),
    ("교육감", "교육감"),
)
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
TARGETED_POLISH_MAX_CANDIDATES = 4
TARGETED_POLISH_MAX_TEXT_LENGTH = 180
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

    # system/config testMode 조회
    test_mode = False
    try:
        system_doc = db.collection("system").document("config").get()
        if system_doc.exists:
            system_data = _safe_dict(system_doc.to_dict())
            test_mode = bool(system_data.get("testMode") is True)
    except Exception:
        test_mode = False

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
    target_word_count: int,
    user_keywords: list[str],
    pipeline_route: str,
    recent_titles: Optional[list[str]] = None,
) -> Dict[str, Any]:
    payload = dict(data)
    payload["topic"] = topic
    payload["category"] = category
    payload["subCategory"] = str(data.get("subCategory") or "")
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


def _topic_and_category(data: Dict[str, Any]) -> tuple[str, str]:
    topic = str(data.get("prompt") or data.get("topic") or "").strip()
    if not topic:
        raise ApiError("invalid-argument", "주제를 입력해주세요.")
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
    return re.sub(r"\s+", "", str(text or "")).strip()


def _clean_full_name_candidate(raw_name: Any) -> str:
    text = str(raw_name or "").strip()
    if not text:
        return ""
    text = re.sub(r"[^가-힣A-Za-z\s]", "", text).strip()
    compact = _normalize_person_name(text)
    if len(compact) < 2 or len(compact) > 12:
        return ""
    return compact


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
    cand = _normalize_person_name(candidate)
    full = _normalize_person_name(full_name)
    if not cand or not full:
        return False
    return cand == full or cand in full or full in cand


def _extract_speaker_consistency_issues(content: str, full_name: str) -> list[str]:
    speaker_name = _normalize_person_name(full_name)
    if not speaker_name:
        return ["화자 실명이 없어 1인칭 정체성 검증을 수행할 수 없음"]

    plain = re.sub(r"<[^>]*>", " ", str(content or ""))
    plain = re.sub(r"\s+", " ", plain).strip()
    if not plain:
        return []

    role_expr = r"(?:시장|부산시장|시장후보|후보|의원|위원장|대표|전\s*위원장)"
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
    return issues


def _repair_speaker_consistency_once(content: str, full_name: str) -> Dict[str, Any]:
    base = str(content or "")
    speaker_name = _normalize_person_name(full_name)
    if not base.strip() or not speaker_name:
        return {"content": base, "edited": False, "appliedPatterns": []}

    applied_patterns: list[str] = []
    repaired = base
    role_expr = r"(?:부산시장|시장|시장후보|후보|의원|위원장|대표|전\s*위원장)"

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
    repaired = re.sub(r"(저는|제가)\s*[,，]\s*", r"\1 ", repaired)
    repaired = re.sub(r"\s{2,}", " ", repaired)

    return {
        "content": repaired,
        "edited": repaired != base,
        "appliedPatterns": sorted(set(applied_patterns)),
    }


def _canonical_role_label(role: str) -> str:
    return normalize_role_label_common(role)


def _extract_keyword_person_role(keyword: str) -> tuple[str, str]:
    parts = extract_role_keyword_parts(keyword)
    name = _clean_full_name_candidate(parts.get("name"))
    role_label = _canonical_role_label(parts.get("role") or parts.get("roleCanonical") or "")
    if not role_label:
        normalized = re.sub(r"\s+", " ", str(keyword or "")).strip()
        for token, mapped in ROLE_TOKEN_PRIORITY:
            if token in normalized:
                role_label = mapped
                break
    return name, role_label


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


def _build_keyword_intent_h2(keyword: str) -> str:
    normalized = re.sub(r"\s+", " ", str(keyword or "")).strip()
    if not normalized:
        return ""

    if ROLE_KEYWORD_PATTERN.fullmatch(normalized):
        quoted_candidate = f"'{normalized}' 검색어가 거론되는 이유"
        if 10 <= len(quoted_candidate) <= 25:
            return quoted_candidate

    candidates = (
        f"{normalized} 왜 거론되나?",
        f"{normalized} 경쟁력은?",
        f"{normalized} 쟁점은?",
    )
    for candidate in candidates:
        if 10 <= len(candidate) <= 25:
            return candidate

    fallback = f"{normalized} 쟁점"
    if len(fallback) > 25:
        trimmed = normalized[: max(8, 25 - len(" 쟁점"))].rstrip(" ,.:;!?")
        fallback = f"{trimmed} 쟁점"
    if len(fallback) < 10:
        fallback = (fallback + " 분석")[:25]
    return fallback


def _ensure_keyword_in_subheading_once(content: str, keyword: str) -> Dict[str, Any]:
    base = str(content or "")
    target_keyword = str(keyword or "").strip()
    if not base or not target_keyword:
        return {"content": base, "edited": False}

    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    if not h2_matches:
        return {"content": base, "edited": False}

    # 이미 소제목에 키워드가 있으면 유지.
    for match in h2_matches:
        heading = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", str(match.group(1) or ""))).strip()
        if target_keyword in heading:
            return {"content": base, "edited": False}

    replacement = _build_keyword_intent_h2(target_keyword)
    if not replacement:
        return {"content": base, "edited": False}

    person_name, _ = _extract_keyword_person_role(target_keyword)
    target_index = 0
    if person_name:
        for idx, match in enumerate(h2_matches):
            heading = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", str(match.group(1) or ""))).strip()
            if person_name in heading:
                target_index = idx
                break

    target_match = h2_matches[target_index]
    updated = base[: target_match.start(1)] + replacement + base[target_match.end(1) :]
    return {
        "content": updated,
        "edited": updated != base,
        "keyword": target_keyword,
        "headingBefore": str(target_match.group(1) or "").strip(),
        "headingAfter": replacement,
    }


def _ensure_user_keyword_in_subheading_once(
    content: str,
    user_keywords: list[str],
    *,
    preferred_keyword: str = "",
) -> Dict[str, Any]:
    base = str(content or "")
    normalized_keywords = [str(item or "").strip() for item in (user_keywords or []) if str(item or "").strip()]
    if not base or not normalized_keywords:
        return {"content": base, "edited": False}

    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    if not h2_matches:
        return {"content": base, "edited": False}

    for match in h2_matches:
        heading = re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", str(match.group(1) or ""))).strip()
        if any(keyword in heading for keyword in normalized_keywords):
            return {"content": base, "edited": False}

    target_keyword = ""
    preferred = str(preferred_keyword or "").strip()
    if preferred and preferred in normalized_keywords:
        target_keyword = preferred
    else:
        target_keyword = normalized_keywords[0]

    target_person_name, target_role = _extract_keyword_person_role(target_keyword)
    if target_person_name or target_role or ROLE_KEYWORD_PATTERN.fullmatch(target_keyword):
        return {"content": base, "edited": False}

    return _ensure_keyword_in_subheading_once(base, target_keyword)


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


def _pick_matchup_counterpart_name(
    section_html: str,
    *,
    speaker_name: str,
    known_names: list[str],
) -> str:
    plain = re.sub(r"<[^>]*>", " ", str(section_html or ""))
    plain = re.sub(r"\s+", " ", plain).strip()
    normalized_speaker_name = _normalize_person_name(speaker_name)
    if not plain or not normalized_speaker_name:
        return ""
    if normalized_speaker_name not in _normalize_person_name(plain):
        return ""
    if not any(token in plain for token in ("양자대결", "가상대결", "대결", "접전", "승부")):
        return ""

    best_name = ""
    best_score = 0
    for name in known_names or []:
        normalized_name = _normalize_person_name(name)
        if not normalized_name or normalized_name == normalized_speaker_name:
            continue
        score = plain.count(normalized_name)
        if re.search(
            rf"{re.escape(normalized_name)}\s+(?:현\s*)?(?:전\s*)?"
            rf"(?:국회의원|의원|시장|지사|도지사|대표|위원장|장관|후보|예비후보)",
            plain,
            re.IGNORECASE,
        ):
            score += 2
        if score > best_score:
            best_name = normalized_name
            best_score = score
    return best_name if best_score > 0 else ""


def _pick_primary_person_name(text: str, known_names: list[str]) -> str:
    plain = re.sub(r"<[^>]*>", " ", str(text or ""))
    plain = re.sub(r"\s+", " ", plain).strip()
    if not plain or not known_names:
        return ""

    best_name = ""
    best_score = 0
    for name in known_names:
        normalized = _normalize_person_name(name)
        if len(normalized) < 2:
            continue
        score = plain.count(normalized)
        if score > best_score:
            best_name = normalized
            best_score = score
    return best_name if best_score > 0 else ""


def _is_subheading_subject_noise_sentence(
    sentence: str,
    *,
    known_names: list[str],
    preferred_names: list[str],
) -> bool:
    plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(sentence or "")))
    if not plain:
        return True

    if any(marker in plain for marker in SUBHEADING_SUBJECT_NOISE_MARKERS):
        return True

    if (
        any(marker in plain for marker in ("검색어", "키워드", "표현", "문구"))
        and any(verb in plain for verb in ("거론", "언급", "주목"))
    ):
        return True

    preferred_set = {
        _normalize_person_name(item)
        for item in preferred_names
        if len(_normalize_person_name(item)) >= 2
    }
    mentioned_non_preferred = any(
        normalized_name
        and normalized_name not in preferred_set
        and normalized_name in plain
        for normalized_name in (
            _normalize_person_name(item)
            for item in known_names
        )
    )
    if mentioned_non_preferred and any(marker in plain for marker in SUBHEADING_LOW_SIGNAL_MARKERS):
        return True

    numeric_tokens = SUBHEADING_NUMERIC_TOKEN_PATTERN.findall(plain)
    if len(numeric_tokens) >= 2 and ("여론조사" in plain or "조사" in plain):
        return True
    return False


def _score_subheading_body_names(
    section_html: str,
    *,
    known_names: list[str],
    preferred_names: list[str],
) -> Dict[str, Any]:
    paragraph_matches = list(PARAGRAPH_TAG_PATTERN.finditer(str(section_html or "")))
    if not paragraph_matches:
        return {"scores": {}, "filteredText": "", "firstPersonSignal": False}

    filtered_sentences: list[str] = []
    first_person_signal = False
    for paragraph_match in paragraph_matches[:SUBHEADING_SIGNAL_PARAGRAPH_LIMIT]:
        paragraph_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(paragraph_match.group(1) or "")))
        if not paragraph_plain:
            continue

        for sentence in _split_sentence_like_units(paragraph_plain):
            if SUBHEADING_FIRST_PERSON_SIGNAL_PATTERN.search(sentence):
                first_person_signal = True
            if _is_subheading_subject_noise_sentence(
                sentence,
                known_names=known_names,
                preferred_names=preferred_names,
            ):
                continue
            filtered_sentences.append(sentence)
            if len(filtered_sentences) >= SUBHEADING_SIGNAL_SENTENCE_LIMIT:
                break
        if len(filtered_sentences) >= SUBHEADING_SIGNAL_SENTENCE_LIMIT:
            break

    filtered_text = " ".join(filtered_sentences).strip()
    scores: Dict[str, int] = {}
    for name in known_names:
        normalized_name = _normalize_person_name(name)
        if len(normalized_name) < 2:
            continue
        score = filtered_text.count(normalized_name) * 3
        if score > 0:
            scores[normalized_name] = score

    if first_person_signal:
        for preferred in preferred_names:
            normalized_preferred = _normalize_person_name(preferred)
            if len(normalized_preferred) < 2:
                continue
            scores[normalized_preferred] = int(scores.get(normalized_preferred) or 0) + 2

    return {
        "scores": scores,
        "filteredText": filtered_text,
        "firstPersonSignal": first_person_signal,
    }


def _pick_scored_primary_person_name(
    scores: Dict[str, int],
    *,
    preferred_names: list[str],
) -> str:
    if not scores:
        return ""

    preferred_set = {
        _normalize_person_name(item)
        for item in preferred_names
        if len(_normalize_person_name(item)) >= 2
    }
    best_name = ""
    best_score = 0
    for name, score in scores.items():
        normalized_name = _normalize_person_name(name)
        score_value = int(score or 0)
        if score_value <= 0 or len(normalized_name) < 2:
            continue
        if score_value > best_score:
            best_name = normalized_name
            best_score = score_value
            continue
        if score_value == best_score and normalized_name in preferred_set and best_name not in preferred_set:
            best_name = normalized_name
    return best_name if best_score > 0 else ""


def _third_personize_first_person_subheading_text(
    heading_inner: str,
    *,
    speaker_name: str,
) -> tuple[str, bool]:
    normalized_speaker_name = _clean_full_name_candidate(speaker_name)
    if not heading_inner or not normalized_speaker_name:
        return heading_inner, False

    updated_heading = str(heading_inner)
    changed = False
    direct_replacements: tuple[tuple[re.Pattern[str], str], ...] = (
        (re.compile(r"(?<![가-힣])저만의", re.IGNORECASE), f"{normalized_speaker_name}만의"),
        (re.compile(r"(?<![가-힣])저의", re.IGNORECASE), f"{normalized_speaker_name}의"),
        (re.compile(r"(?<![가-힣])제가", re.IGNORECASE), f"{normalized_speaker_name}이"),
        (re.compile(r"(?<![가-힣])저는", re.IGNORECASE), f"{normalized_speaker_name}은"),
        (re.compile(r"(?<![가-힣])나의", re.IGNORECASE), f"{normalized_speaker_name}의"),
        (re.compile(r"(?<![가-힣])내가", re.IGNORECASE), f"{normalized_speaker_name}이"),
        (re.compile(r"(?<![가-힣])나는", re.IGNORECASE), f"{normalized_speaker_name}은"),
    )
    for pattern, replacement in direct_replacements:
        updated_heading, count = pattern.subn(replacement, updated_heading)
        if count > 0:
            changed = True

    updated_heading, possessive_count = SUBHEADING_FIRST_PERSON_POSSESSIVE_PATTERN.subn(
        f"{normalized_speaker_name}의",
        updated_heading,
    )
    if possessive_count > 0:
        changed = True

    awkward_possessive_pattern = re.compile(
        rf"(?<![가-힣]){re.escape(normalized_speaker_name)}이\s+"
        r"((?:[가-힣]{2,8}\s+)?(?:비전|해법|대안|정책|생각|진심|메시지|방향|해결책|경쟁력|가능성|역할))은\?",
        re.IGNORECASE,
    )
    updated_heading, awkward_possessive_count = awkward_possessive_pattern.subn(
        rf"{normalized_speaker_name}의 \1은?",
        updated_heading,
    )
    if awkward_possessive_count > 0:
        changed = True

    return updated_heading, changed


def _build_subheading_role_surface(name: str, role_facts: Optional[Dict[str, str]] = None) -> str:
    normalized_name = _normalize_person_name(name)
    if not normalized_name:
        return ""
    raw_role = str(_safe_dict(role_facts).get(normalized_name) or "").strip()
    role_label = _canonical_role_label(raw_role)
    if role_label == "국회의원":
        return f"{normalized_name} 의원"
    if raw_role.endswith("시장") and role_label not in {"국회의원", "의원"}:
        return f"{normalized_name} 시장"
    if raw_role.endswith("지사") and role_label not in {"국회의원", "의원"}:
        return f"{normalized_name} 지사"
    if role_label in {"시장", "지사", "대표", "위원장", "장관", "예비후보", "후보"}:
        return f"{normalized_name} {role_label}"
    return normalized_name


def _repair_malformed_matchup_subheading_text(
    heading_inner: str,
    *,
    speaker_name: str,
    known_names: list[str],
    role_facts: Optional[Dict[str, str]] = None,
) -> tuple[str, Optional[Dict[str, str]]]:
    heading_plain = re.sub(r"<[^>]*>", " ", str(heading_inner or ""))
    heading_plain = re.sub(r"\s+", " ", heading_plain).strip()
    normalized_speaker_name = _normalize_person_name(speaker_name)
    if not heading_plain or not normalized_speaker_name:
        return heading_inner, None
    if not any(token in heading_plain for token in ("양자대결", "가상대결", "대결", "접전", "승부", "오차 범위")):
        return heading_inner, None

    normalized_known_names = [
        _normalize_person_name(item)
        for item in (known_names or [])
        if _normalize_person_name(item) and _normalize_person_name(item) != normalized_speaker_name
    ]
    for other_name in normalized_known_names:
        role_surface = _build_subheading_role_surface(other_name, role_facts=role_facts) or other_name
        patterns = (
            re.compile(
                rf"{re.escape(other_name)}\s+(?:현|전)\s+{re.escape(normalized_speaker_name)}의\s+"
                rf"(?P<tail>(?:양자대결|가상대결|대결|접전|승부|오차 범위)[^<]*)",
                re.IGNORECASE,
            ),
            re.compile(
                rf"{re.escape(other_name)}\s+(?:현|전)\s+{re.escape(normalized_speaker_name)}\s+"
                rf"(?P<tail>(?:양자대결|가상대결|대결|접전|승부|오차 범위)[^<]*)",
                re.IGNORECASE,
            ),
        )
        for pattern in patterns:
            updated_heading, count = pattern.subn(
                lambda match: f"{role_surface}과의 {str(match.group('tail') or '').strip()}",
                heading_inner,
                count=1,
            )
            if count > 0 and updated_heading != heading_inner:
                return updated_heading, {
                    "from": heading_plain,
                    "to": re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", updated_heading)).strip(),
                    "type": "malformed_matchup_heading",
                }
    return heading_inner, None


def _repair_speaker_role_mismatch_matchup_subheading_text(
    heading_inner: str,
    *,
    speaker_name: str,
    body_name: str,
    role_facts: Optional[Dict[str, str]] = None,
) -> tuple[str, Optional[Dict[str, str]]]:
    heading_plain = re.sub(r"<[^>]*>", " ", str(heading_inner or ""))
    heading_plain = re.sub(r"\s+", " ", heading_plain).strip()
    normalized_speaker_name = _normalize_person_name(speaker_name)
    normalized_body_name = _normalize_person_name(body_name)
    if not heading_plain or not normalized_speaker_name or not normalized_body_name:
        return heading_inner, None
    if normalized_speaker_name == normalized_body_name:
        return heading_inner, None
    if not any(token in heading_plain for token in ("양자대결", "가상대결", "대결", "접전", "승부", "오차 범위")):
        return heading_inner, None

    role_surface = _build_subheading_role_surface(normalized_body_name, role_facts=role_facts) or normalized_body_name
    pattern = re.compile(
        rf"{re.escape(normalized_speaker_name)}\s+(?:현\s*)?(?:전\s*)?"
        rf"(?:국회의원|의원|시장|지사|도지사|대표|위원장|장관|후보|예비후보)"
        rf"(?P<tail>\s*(?:과의|와의)?\s*(?:양자대결|가상대결|대결|접전|승부|오차 범위)[^<]*)",
        re.IGNORECASE,
    )
    updated_heading, count = pattern.subn(
        lambda match: f"{role_surface}{str(match.group('tail') or '')}",
        heading_inner,
        count=1,
    )
    if count > 0 and updated_heading != heading_inner:
        return updated_heading, {
            "from": heading_plain,
            "to": re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", updated_heading)).strip(),
            "type": "speaker_role_mismatch_matchup_heading",
        }
    return heading_inner, None


def _repair_subheading_entity_consistency_once(
    content: str,
    known_names: list[str],
    *,
    preferred_names: Optional[list[str]] = None,
    role_facts: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip() or not known_names:
        return {"content": base, "edited": False, "replacements": []}

    normalized_preferred_names = [
        _normalize_person_name(item)
        for item in (preferred_names or [])
        if len(_normalize_person_name(item)) >= 2
    ]
    preferred_name_set = set(normalized_preferred_names)
    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    if not h2_matches:
        return {"content": base, "edited": False, "replacements": []}

    replacements: list[Dict[str, str]] = []
    repaired = base
    speaker_name = normalized_preferred_names[0] if normalized_preferred_names else ""
    for idx in range(len(h2_matches) - 1, -1, -1):
        match = h2_matches[idx]
        heading_inner = str(match.group(1) or "")
        heading_plain = re.sub(r"<[^>]*>", " ", heading_inner)
        heading_plain = re.sub(r"\s+", " ", heading_plain).strip()
        if not heading_plain:
            continue

        updated_heading_inner, renamed_first_person = _third_personize_first_person_subheading_text(
            heading_inner,
            speaker_name=speaker_name,
        )
        if renamed_first_person:
            repaired = repaired[:match.start(1)] + updated_heading_inner + repaired[match.end(1):]
            replacements.append(
                {
                    "from": "first_person_pronoun",
                    "to": speaker_name,
                    "headingBefore": heading_plain,
                    "headingAfter": re.sub(
                        r"\s+",
                        " ",
                        re.sub(r"<[^>]*>", " ", updated_heading_inner),
                    ).strip(),
                }
            )
            heading_inner = updated_heading_inner
            heading_plain = re.sub(r"<[^>]*>", " ", updated_heading_inner)
            heading_plain = re.sub(r"\s+", " ", heading_plain).strip()
        if re.search(r"(검색어|키워드|표현|문구)", heading_plain):
            continue

        integrity_heading_inner, malformed_replacement = _repair_malformed_matchup_subheading_text(
            heading_inner,
            speaker_name=speaker_name,
            known_names=known_names,
            role_facts=role_facts,
        )
        if malformed_replacement:
            repaired = repaired[:match.start(1)] + integrity_heading_inner + repaired[match.end(1):]
            replacements.append(malformed_replacement)
            heading_inner = integrity_heading_inner
            heading_plain = re.sub(r"<[^>]*>", " ", integrity_heading_inner)
            heading_plain = re.sub(r"\s+", " ", heading_plain).strip()

        section_start = match.end()
        section_end = h2_matches[idx + 1].start() if idx < len(h2_matches) - 1 else len(repaired)
        section_html = repaired[section_start:section_end]
        matchup_counterpart_name = _pick_matchup_counterpart_name(
            section_html,
            speaker_name=speaker_name,
            known_names=known_names,
        )
        heading_name = _pick_primary_person_name(heading_plain, known_names)
        subject_signal = _score_subheading_body_names(
            section_html,
            known_names=known_names,
            preferred_names=normalized_preferred_names,
        )
        body_scores = subject_signal.get("scores") if isinstance(subject_signal, dict) else {}
        if not isinstance(body_scores, dict):
            body_scores = {}
        body_name = _pick_scored_primary_person_name(
            {
                _normalize_person_name(name): int(score or 0)
                for name, score in body_scores.items()
                if len(_normalize_person_name(name)) >= 2
            },
            preferred_names=normalized_preferred_names,
        )
        if matchup_counterpart_name:
            body_name = matchup_counterpart_name
        mismatch_heading_inner, mismatch_replacement = _repair_speaker_role_mismatch_matchup_subheading_text(
            heading_inner,
            speaker_name=speaker_name,
            body_name=body_name,
            role_facts=role_facts,
        )
        if mismatch_replacement:
            repaired = repaired[:match.start(1)] + mismatch_heading_inner + repaired[match.end(1):]
            replacements.append(mismatch_replacement)
            continue
        if not heading_name or not body_name or heading_name == body_name:
            continue
        if heading_name in preferred_name_set and body_name not in preferred_name_set:
            continue
        body_name_score = int(body_scores.get(body_name) or 0)
        heading_name_score = int(body_scores.get(heading_name) or 0)
        if body_name_score <= heading_name_score:
            continue

        updated_heading_inner, changed = re.subn(
            re.escape(heading_name),
            body_name,
            heading_inner,
            count=1,
        )
        if changed <= 0:
            continue

        repaired = repaired[:match.start(1)] + updated_heading_inner + repaired[match.end(1):]
        replacements.append(
            {
                "from": heading_name,
                "to": body_name,
                "headingBefore": heading_plain,
                "headingAfter": re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", updated_heading_inner)).strip(),
            }
        )

    return {
        "content": repaired,
        "edited": repaired != base,
        "replacements": replacements,
    }


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
                source_surface = _build_subheading_role_surface(name, role_facts={name: source_role}) or f"{name} {source_role}"

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


_BROKEN_POLL_ROLE_FRAGMENT = r"(?:전\s*)?(?:국회의원|의원|시장|지사|도지사|대표|위원장|후보|예비후보)"
_SAFE_SENTENCE_HTML_PATTERN = re.compile(r".+?(?:(?<!\d)[.!?。](?!\d)|$)", re.DOTALL)


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
    if any(re.search(r"검색어\s*삽입\s*횟수\s*:", line) for line in lines):
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


def _collect_targeted_sentence_polish_candidates(content: str) -> list[Dict[str, Any]]:
    base = str(content or "")
    if not base.strip():
        return []

    candidates: list[Dict[str, Any]] = []
    for block_index, match in enumerate(CONTENT_BLOCK_WITH_TAG_PATTERN.finditer(base)):
        if len(candidates) >= TARGETED_POLISH_MAX_CANDIDATES:
            break

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
                        "text": plain_inner,
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

        for sentence_index, sentence in enumerate(_split_sentence_like_units(normalized_inner)):
            if len(candidates) >= TARGETED_POLISH_MAX_CANDIDATES:
                break
            if len(sentence) > TARGETED_POLISH_MAX_TEXT_LENGTH:
                continue

            reason = _detect_targeted_sentence_polish_issue(sentence, tag=tag)
            if not reason:
                continue

            candidates.append(
                {
                    "id": f"{block_key}-s{sentence_index}",
                    "tag": tag,
                    "reason": reason,
                    "text": sentence,
                    "blockKey": block_key,
                    "blockInner": normalized_inner,
                    "innerStart": match.start("inner"),
                    "innerEnd": match.end("inner"),
                }
            )
    return candidates


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
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip() or not candidates or not rewrite_map:
        return {"content": base, "edited": False, "actions": []}

    block_updates: Dict[str, str] = {}
    block_positions: Dict[str, Dict[str, Any]] = {}
    actions: list[str] = []

    for candidate in candidates:
        candidate_id = str(candidate.get("id") or "").strip()
        rewritten = _normalize_inline_whitespace(rewrite_map.get(candidate_id))
        if not candidate_id or not rewritten:
            continue

        valid, reason = _validate_targeted_sentence_rewrite(
            str(candidate.get("text") or ""),
            rewritten,
            tag=str(candidate.get("tag") or ""),
            user_keywords=user_keywords,
            known_names=known_names,
        )
        if not valid:
            actions.append(f"targeted_sentence_llm_skip:{candidate_id}:{reason}")
            continue

        block_key = str(candidate.get("blockKey") or "").strip()
        original_block_inner = str(candidate.get("blockInner") or "")
        if not block_key or not original_block_inner:
            continue

        current_inner = block_updates.get(block_key, original_block_inner)
        if str(candidate.get("tag") or "").lower() == "h2":
            updated_inner = rewritten
        else:
            original_fragment = str(candidate.get("text") or "")
            updated_inner = current_inner.replace(original_fragment, rewritten, 1)
            if updated_inner == current_inner:
                actions.append(f"targeted_sentence_llm_skip:{candidate_id}:replace_miss")
                continue

        block_updates[block_key] = updated_inner
        block_positions[block_key] = {
            "innerStart": int(candidate.get("innerStart") or 0),
            "innerEnd": int(candidate.get("innerEnd") or 0),
            "originalInner": original_block_inner,
        }
        actions.append(f"targeted_sentence_llm:{candidate_id}")

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
) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    candidates = _collect_targeted_sentence_polish_candidates(base)
    if not candidates:
        return {"content": base, "edited": False, "actions": []}

    prompt_items = [
        {
            "id": str(candidate.get("id") or ""),
            "tag": str(candidate.get("tag") or ""),
            "reason": str(candidate.get("reason") or ""),
            "text": str(candidate.get("text") or ""),
        }
        for candidate in candidates
    ]
    prompt = (
        "당신은 한국어 정치 원고의 파손 문장 교정기입니다.\n"
        "아래 fragment만 최소 수정으로 자연스럽게 고치세요.\n"
        "규칙:\n"
        "1. 각 fragment는 하나의 소제목 또는 한 문장만 다룹니다.\n"
        "2. 의미, 정치적 입장, 고유명사, 직함, 수치, 검색어를 유지하세요.\n"
        "3. 새 사실을 추가하지 마세요.\n"
        "4. HTML 태그를 넣지 마세요.\n"
        "5. 가능한 한 조사/어순만 고치고 과하게 다시 쓰지 마세요.\n"
        "6. id는 그대로 두고 text만 반환하세요.\n\n"
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
    )
    actions = [f"targeted_sentence_candidates:{len(candidates)}"]
    apply_actions = apply_result.get("actions")
    if isinstance(apply_actions, list):
        for action in apply_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    return {
        "content": str(apply_result.get("content") or base),
        "edited": bool(apply_result.get("edited")),
        "actions": actions,
    }


def _repair_awkward_h2_phrases_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    actions: list[str] = []

    for match in reversed(list(H2_TAG_PATTERN.finditer(base))):
        inner = str(match.group(1) or "")
        plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", inner))
        if not plain:
            continue

        updated = plain
        local_actions: list[str] = []

        if re.search(r"필요성을\s+말씀드립니다$", updated):
            updated = re.sub(r"필요성을\s+말씀드립니다$", "말씀드립니다", updated)
            local_actions.append("awkward_h2_pledge_neutralization")
        if re.search(r"알려지고$", updated):
            updated = re.sub(r"알려지고$", "알려지고 있습니다", updated)
            local_actions.append("awkward_h2_incomplete_progressive")
        if re.search(r":\s*실질적인\s+변화를\s+비$", updated):
            updated = re.sub(
                r":\s*실질적인\s+변화를\s+비$",
                ": 실질적인 변화를 위한 비전",
                updated,
            )
            local_actions.append("awkward_h2_truncated_vision")

        if updated == plain:
            continue

        repaired = repaired[:match.start(1)] + updated + repaired[match.end(1):]
        actions.extend(local_actions)

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


def _repair_branding_h2_phrases_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    actions: list[str] = []
    contest_tokens = ("양자대결", "가상대결", "대결", "접전", "승부", "오차 범위", "지지율")
    recognition_pattern = re.compile(
        r"^(?P<name>[가-힣]{2,8})\s*,?\s*(?:(?P<region>[가-힣]{2,8})\s*)?시민(?:여러분)?에게\s*"
        r"(?:조금씩\s*)?(?:더\s*)?확실히\s*알려지(?:고|며)(?:\s*있습니다)?(?:.*)?$"
    )
    economy_pattern = re.compile(
        r"^(?P<region>[가-힣]{2,8})\s*경제는\s*(?P<name>[가-힣]{2,8})(?:입니다)?(?:\s*[:：,，-]\s*.*)?$"
    )

    for match in reversed(list(H2_TAG_PATTERN.finditer(base))):
        inner = str(match.group(1) or "")
        plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", inner))
        if not plain or "%" in plain or any(token in plain for token in contest_tokens):
            continue

        updated = plain
        local_actions: list[str] = []

        recognition_match = recognition_pattern.fullmatch(updated)
        if recognition_match:
            name = str(recognition_match.group("name") or "").strip()
            region = str(recognition_match.group("region") or "").strip()
            audience = f"{region} 시민 접점 확대" if region else "시민 접점 확대"
            updated = f"{name} 인지도 상승, {audience}"
            local_actions.append("branding_h2_recognition_rewrite")
        else:
            economy_match = economy_pattern.fullmatch(updated)
            if economy_match:
                region = str(economy_match.group("region") or "").strip()
                name = str(economy_match.group("name") or "").strip()
                if name.endswith("입니다") and len(name) > 3:
                    name = name[:-3]
                updated = f"{region} 경제 재도약, {name}의 정책 비전"
                local_actions.append("branding_h2_economy_rewrite")

        if updated == plain:
            continue

        repaired = repaired[:match.start(1)] + updated + repaired[match.end(1):]
        actions.extend(local_actions)

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


def _build_poll_focus_pair_sentence(pair: Optional[Dict[str, Any]]) -> str:
    pair_dict = pair if isinstance(pair, dict) else {}
    speaker = str(pair_dict.get("speaker") or "").strip()
    opponent = str(pair_dict.get("opponent") or "").strip()
    speaker_percent = str(pair_dict.get("speakerPercent") or pair_dict.get("speakerScore") or "").strip()
    opponent_percent = str(pair_dict.get("opponentPercent") or pair_dict.get("opponentScore") or "").strip()
    if not speaker or not opponent or not speaker_percent or not opponent_percent:
        return ""
    return f"{speaker}·{opponent} 가상대결에서는 {speaker_percent} 대 {opponent_percent}로 나타났습니다."


def _drop_incomplete_paragraph_tail_once(content: str) -> Dict[str, Any]:
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    repaired = base
    actions: list[str] = []
    incomplete_tail_pattern = re.compile(
        r"([.!?])(\s*)([^.!?<>]{1,36})\s*$",
        re.IGNORECASE,
    )
    incomplete_endings = (
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
    complete_endings = (
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

    for match in reversed(list(PARAGRAPH_TAG_PATTERN.finditer(base))):
        inner = str(match.group(1) or "")
        tail_match = incomplete_tail_pattern.search(inner)
        if not tail_match:
            continue
        fragment_raw = str(tail_match.group(3) or "")
        fragment_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", fragment_raw))
        if not fragment_plain or len(fragment_plain) > 30:
            continue
        if any(fragment_plain.endswith(ending) for ending in complete_endings):
            continue
        if not any(fragment_plain.endswith(ending) for ending in incomplete_endings):
            continue

        updated_inner = inner[:tail_match.start(3)].rstrip()
        if not updated_inner or updated_inner == inner:
            continue
        repaired = repaired[:match.start(1)] + updated_inner + repaired[match.end(1):]
        actions.append("drop_incomplete_paragraph_tail")

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


def _apply_poll_focus_contract_once(
    content: str,
    *,
    poll_focus_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = str(content or "")
    bundle = poll_focus_bundle if isinstance(poll_focus_bundle, dict) else {}
    if not base.strip() or str(bundle.get("scope") or "").strip().lower() != "matchup":
        return {"content": base, "edited": False, "actions": []}

    primary_pair = bundle.get("primaryPair") if isinstance(bundle.get("primaryPair"), dict) else {}
    secondary_pairs = bundle.get("secondaryPairs") if isinstance(bundle.get("secondaryPairs"), list) else []
    primary_sentence = _build_poll_focus_pair_sentence(primary_pair)
    speaker = str(primary_pair.get("speaker") or bundle.get("speaker") or "").strip()
    primary_opponent = str(primary_pair.get("opponent") or "").strip()
    speaker_percent = str(primary_pair.get("speakerPercent") or primary_pair.get("speakerScore") or "").strip()
    opponent_percent = str(primary_pair.get("opponentPercent") or primary_pair.get("opponentScore") or "").strip()
    if not primary_sentence or not speaker or not primary_opponent:
        return {"content": base, "edited": False, "actions": []}

    allowed_h2_kinds = bundle.get("allowedH2Kinds") if isinstance(bundle.get("allowedH2Kinds"), list) else []
    h2_template_map: Dict[str, str] = {}
    for raw_kind in allowed_h2_kinds:
        kind = raw_kind if isinstance(raw_kind, dict) else {}
        kind_id = str(kind.get("id") or "").strip()
        kind_template = str(kind.get("template") or "").strip()
        if kind_id and kind_template and kind_id not in h2_template_map:
            h2_template_map[kind_id] = kind_template

    contest_tokens = ("가상대결", "양자대결", "대결", "접전", "경쟁력", "약진")
    policy_tokens = ("경제", "비전", "정책", "산업", "일자리", "미래", "혁신", "발전")
    recognition_tokens = ("인지도", "알려", "각인", "진정성", "소통", "접점", "현장")
    closing_tokens = ("함께", "미래", "약속", "부산 시민", "마무리", "끝으로")

    repaired = base
    actions: list[str] = []
    h2_matches = list(H2_TAG_PATTERN.finditer(base))
    total_h2 = len(h2_matches)
    for index in range(total_h2 - 1, -1, -1):
        match = h2_matches[index]
        next_start = h2_matches[index + 1].start() if index + 1 < total_h2 else len(repaired)
        section_html = repaired[match.end():next_start]
        h2_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", str(match.group(1) or "")))
        section_plain = _normalize_inline_whitespace(re.sub(r"<[^>]*>", " ", section_html))

        section_kind = ""
        if index == total_h2 - 1 and h2_template_map.get("closing"):
            section_kind = "closing"
        if not section_kind:
            if (
                primary_opponent
                and primary_opponent in section_plain
                and (
                    speaker_percent in section_plain
                    or opponent_percent in section_plain
                    or any(token in section_plain for token in contest_tokens)
                )
            ):
                section_kind = "primary_matchup"
            else:
                for pair in secondary_pairs[:2]:
                    pair_dict = pair if isinstance(pair, dict) else {}
                    secondary_opponent = str(pair_dict.get("opponent") or "").strip()
                    secondary_speaker_percent = str(pair_dict.get("speakerPercent") or pair_dict.get("speakerScore") or "").strip()
                    secondary_opponent_percent = str(pair_dict.get("opponentPercent") or pair_dict.get("opponentScore") or "").strip()
                    if (
                        secondary_opponent
                        and secondary_opponent in section_plain
                        and (
                            secondary_speaker_percent in section_plain
                            or secondary_opponent_percent in section_plain
                            or any(token in section_plain for token in contest_tokens)
                        )
                    ):
                        section_kind = "secondary_matchup"
                        break
        if not section_kind:
            if any(token in f"{h2_plain} {section_plain}" for token in policy_tokens):
                section_kind = "policy"
            elif any(token in f"{h2_plain} {section_plain}" for token in recognition_tokens):
                section_kind = "recognition"
            elif index == total_h2 - 1 or any(token in f"{h2_plain} {section_plain}" for token in closing_tokens):
                section_kind = "closing"

        h2_template = h2_template_map.get(section_kind)
        updated_h2_inner = h2_plain
        if h2_template and h2_plain and h2_plain != h2_template:
            updated_h2_inner = h2_template
            actions.append(f"poll_focus_h2:{section_kind}")

        first_paragraph_match = PARAGRAPH_TAG_PATTERN.search(section_html)
        updated_section_html = section_html
        if first_paragraph_match:
            replacement_sentence = ""
            if section_kind == "primary_matchup":
                replacement_sentence = primary_sentence
            elif section_kind == "secondary_matchup" and secondary_pairs:
                replacement_sentence = _build_poll_focus_pair_sentence(secondary_pairs[0])

            if replacement_sentence:
                paragraph_plain = _normalize_inline_whitespace(
                    re.sub(r"<[^>]*>", " ", str(first_paragraph_match.group(1) or ""))
                )
                if (
                    paragraph_plain != replacement_sentence
                    and any(token in paragraph_plain for token in (primary_opponent, speaker_percent, opponent_percent, *contest_tokens))
                ):
                    updated_section_html = (
                        section_html[:first_paragraph_match.start(1)]
                        + replacement_sentence
                        + section_html[first_paragraph_match.end(1):]
                    )
                    actions.append(f"poll_focus_fact:{section_kind}")

        if updated_section_html != section_html:
            repaired = repaired[:match.end()] + updated_section_html + repaired[next_start:]
        if updated_h2_inner != h2_plain:
            repaired = repaired[:match.start(1)] + updated_h2_inner + repaired[match.end(1):]

    completion_repair = _drop_incomplete_paragraph_tail_once(repaired)
    if completion_repair.get("edited"):
        repaired = str(completion_repair.get("content") or repaired)
        for action in completion_repair.get("actions") or []:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)

    return {
        "content": repaired,
        "edited": repaired != base,
        "actions": actions,
    }


def _apply_final_sentence_polish_once(
    content: str,
    *,
    full_name: str = "",
    user_keywords: Optional[list[str]] = None,
    role_facts: Optional[Dict[str, str]] = None,
    poll_fact_table: Optional[Dict[str, Any]] = None,
    poll_focus_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """최종 단계에서 문장 파손 가능성이 낮은 경량 윤문만 1회 적용한다."""
    base = str(content or "")
    if not base.strip():
        return {"content": base, "edited": False, "actions": []}

    repaired = remove_grammatical_errors(base)
    actions: list[str] = []
    if repaired != base:
        actions.append("grammar_pattern_rewrite")

    safe_patterns: list[tuple[re.Pattern[str], str, str]] = [
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
    ]
    for pattern, replacement, action_name in safe_patterns:
        repaired, changed = pattern.subn(replacement, repaired)
        if changed > 0:
            actions.append(f"{action_name}:{changed}")

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
    )
    targeted_actions = targeted_rewrite.get("actions")
    if isinstance(targeted_actions, list):
        for action in targeted_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if targeted_rewrite.get("edited"):
        repaired = str(targeted_rewrite.get("content") or repaired)

    h2_phrase_repair = _repair_awkward_h2_phrases_once(repaired)
    h2_phrase_actions = h2_phrase_repair.get("actions")
    if isinstance(h2_phrase_actions, list):
        for action in h2_phrase_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if h2_phrase_repair.get("edited"):
        repaired = str(h2_phrase_repair.get("content") or repaired)

    branding_h2_repair = _repair_branding_h2_phrases_once(repaired)
    branding_h2_actions = branding_h2_repair.get("actions")
    if isinstance(branding_h2_actions, list):
        for action in branding_h2_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if branding_h2_repair.get("edited"):
        repaired = str(branding_h2_repair.get("content") or repaired)

    poll_focus_contract_repair = _apply_poll_focus_contract_once(
        repaired,
        poll_focus_bundle=poll_focus_bundle,
    )
    poll_focus_contract_actions = poll_focus_contract_repair.get("actions")
    if isinstance(poll_focus_contract_actions, list):
        for action in poll_focus_contract_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if poll_focus_contract_repair.get("edited"):
        repaired = str(poll_focus_contract_repair.get("content") or repaired)

    poll_dedupe = _dedupe_poll_explanation_sentences_once(repaired)
    poll_dedupe_actions = poll_dedupe.get("actions")
    if isinstance(poll_dedupe_actions, list):
        for action in poll_dedupe_actions:
            action_text = str(action).strip()
            if action_text:
                actions.append(action_text)
    if poll_dedupe.get("edited"):
        repaired = str(poll_dedupe.get("content") or repaired)

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


def _run_async_sync(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
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


def _compute_title_repeat_meta(title: str, recent_titles: list[str]) -> Dict[str, Any]:
    normalized_title = _normalize_title_surface_local(title)
    normalized_recent_titles = _normalize_recent_title_memory_values(list(recent_titles or []))
    if not normalized_title or not normalized_recent_titles:
        return {
            "penalty": 0,
            "maxSimilarity": 0.0,
            "against": "",
            "framePenalty": 0,
            "frameScore": 0,
            "frameAgainst": "",
            "frameReasons": [],
        }

    try:
        from agents.common.title_generation import _compute_similarity_penalty

        return _compute_similarity_penalty(
            normalized_title,
            normalized_recent_titles,
            threshold=0.68,
            max_penalty=20,
        )
    except Exception as exc:
        logger.warning("Title repeat meta computation failed (non-fatal): %s", exc)
        return {
            "penalty": 0,
            "maxSimilarity": 0.0,
            "against": "",
            "framePenalty": 0,
            "frameScore": 0,
            "frameAgainst": "",
            "frameReasons": [],
        }


def _title_repeat_needs_fallback(meta: Dict[str, Any]) -> bool:
    penalty = _to_int(meta.get("penalty"), 0)
    frame_penalty = _to_int(meta.get("framePenalty"), 0)
    frame_score = _to_int(meta.get("frameScore"), 0)
    max_similarity = float(meta.get("maxSimilarity") or 0.0)
    return bool(
        frame_score >= 5
        or frame_penalty >= 4
        or penalty >= 8
        or max_similarity >= 0.82
    )


def _normalize_person_name_for_title(value: Any) -> str:
    normalized = re.sub(r"[^가-힣]", "", str(value or ""))
    if 2 <= len(normalized) <= 8:
        return normalized
    return ""


def _format_title_percent(value: Any) -> str:
    try:
        number = round(float(value), 1)
    except (TypeError, ValueError):
        return ""
    if abs(number - int(number)) < 0.05:
        return f"{int(number)}%"
    return f"{number:.1f}%"


def _select_title_fallback_pair(
    *,
    poll_fact_table: Optional[Dict[str, Any]],
    full_name: str,
    user_keywords: list[str],
) -> Optional[Dict[str, Any]]:
    speaker = _normalize_person_name_for_title(full_name)
    pairs = _safe_dict(_safe_dict(poll_fact_table).get("pairs"))
    if not speaker or not pairs:
        return None

    keyword_names: set[str] = set()
    for raw_keyword in user_keywords or []:
        keyword = str(raw_keyword or "").strip()
        if not keyword:
            continue
        parts = extract_role_keyword_parts(keyword)
        name = _normalize_person_name_for_title(parts.get("name") or keyword)
        if name:
            keyword_names.add(name)

    selected: Optional[Dict[str, Any]] = None
    selected_key: tuple[int, float, int] | None = None
    for raw_entry in pairs.values():
        entry = _safe_dict(raw_entry)
        left = _normalize_person_name_for_title(entry.get("left"))
        right = _normalize_person_name_for_title(entry.get("right"))
        if speaker not in {left, right}:
            continue
        opponent = right if speaker == left else left
        speaker_score = entry.get("leftScore") if speaker == left else entry.get("rightScore")
        opponent_score = entry.get("rightScore") if speaker == left else entry.get("leftScore")
        try:
            margin = abs(float(speaker_score) - float(opponent_score))
        except (TypeError, ValueError):
            margin = 99.0
        relevance = 1 if opponent in keyword_names else 0
        record_count = len(entry.get("records") or [])
        sort_key = (relevance, -margin, record_count)
        if selected is None or sort_key > selected_key:
            selected = {
                "speaker": speaker,
                "opponent": opponent,
                "speakerScore": speaker_score,
                "opponentScore": opponent_score,
            }
            selected_key = sort_key

    return selected


def _build_repeat_safe_title_fallback(
    *,
    current_title: str,
    recent_titles: list[str],
    topic: str,
    content: str,
    user_keywords: list[str],
    full_name: str,
    category: str,
    status: str,
    context_analysis: Dict[str, Any],
    role_keyword_policy: Optional[Dict[str, Any]] = None,
    poll_fact_table: Optional[Dict[str, Any]] = None,
    poll_focus_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized_recent_titles = _normalize_recent_title_memory_values(list(recent_titles or []))
    pair = _select_title_fallback_pair(
        poll_fact_table=poll_fact_table,
        full_name=full_name,
        user_keywords=user_keywords,
    )
    speaker = _normalize_person_name_for_title(full_name)
    role_entries = role_keyword_policy.get("entries") if isinstance(role_keyword_policy, dict) else {}

    prefix_candidates: list[str] = []
    seen_prefixes: set[str] = set()

    for raw_keyword in user_keywords or []:
        keyword = str(raw_keyword or "").strip()
        if not keyword:
            continue
        entry = _safe_dict(role_entries.get(keyword)) if isinstance(role_entries, dict) else {}
        mode = str(entry.get("mode") or "").strip().lower()
        parts = extract_role_keyword_parts(keyword)
        if mode == "intent_only" and parts.get("name") and parts.get("role"):
            for prefix in (
                f"{keyword} 출마론",
                f"{keyword} 거론 속",
                f"{keyword} 구도",
            ):
                normalized_prefix = _normalize_title_surface_local(prefix) or prefix
                if normalized_prefix and normalized_prefix not in seen_prefixes:
                    seen_prefixes.add(normalized_prefix)
                    prefix_candidates.append(normalized_prefix)
        else:
            normalized_prefix = _normalize_title_surface_local(keyword) or keyword
            if normalized_prefix and normalized_prefix not in seen_prefixes:
                seen_prefixes.add(normalized_prefix)
                prefix_candidates.append(normalized_prefix)

    if not prefix_candidates and speaker:
        prefix_candidates.append(f"{speaker} 여론조사")
    if not prefix_candidates and topic:
        prefix_candidates.append(str(topic).strip())

    suffix_candidates: list[str] = []
    if pair:
        speaker_score = _format_title_percent(pair.get("speakerScore"))
        opponent_score = _format_title_percent(pair.get("opponentScore"))
        if speaker and speaker_score and opponent_score:
            suffix_candidates.extend(
                [
                    f"{speaker}과 가상대결 {speaker_score} 대 {opponent_score}",
                    f"{speaker}과 가상대결서 드러난 접전",
                    f"{speaker}과 양자대결서 확인된 경쟁력",
                ]
            )
    if speaker and not suffix_candidates:
        suffix_candidates.extend(
            [
                f"{speaker}과 가상대결서 드러난 접전",
                f"{speaker}의 경쟁력",
            ]
        )
    if not suffix_candidates:
        suffix_candidates.append("여론조사에서 드러난 변화")

    candidate_titles: list[str] = []
    seen_titles: set[str] = set()
    for prefix in prefix_candidates[:4]:
        for suffix in suffix_candidates[:4]:
            title = _normalize_title_surface_local(f"{prefix}, {suffix}") or f"{prefix}, {suffix}"
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            candidate_titles.append(title)

    if current_title:
        candidate_titles.append(_normalize_title_surface_local(current_title) or current_title)

    best: Optional[Dict[str, Any]] = None
    for candidate in candidate_titles:
        compliance = _score_title_compliance(
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
        repeat_meta = _compute_title_repeat_meta(candidate, normalized_recent_titles)
        repeat_risky = _title_repeat_needs_fallback(repeat_meta)
        sort_key = (
            int(bool(compliance.get("passed")) and not repeat_risky),
            int(bool(compliance.get("passed"))),
            max(0, 100 - _to_int(repeat_meta.get("penalty"), 0)),
            max(0, 100 - _to_int(repeat_meta.get("frameScore"), 0)),
            _to_int(compliance.get("score"), 0),
        )
        record = {
            "title": candidate,
            "compliance": compliance,
            "repeatMeta": repeat_meta,
            "repeatRisk": repeat_risky,
            "sortKey": sort_key,
        }
        if best is None or sort_key > best.get("sortKey", ()):
            best = record

    if not best:
        normalized_current = _normalize_title_surface_local(current_title) or current_title
        return {
            "title": normalized_current,
            "usedFallback": False,
            "repeatMeta": _compute_title_repeat_meta(normalized_current, normalized_recent_titles),
            "reason": "no_repeat_safe_candidate",
        }

    selected_title = str(best.get("title") or "").strip()
    normalized_current = _normalize_title_surface_local(current_title) or current_title
    return {
        "title": selected_title or normalized_current,
        "usedFallback": bool(selected_title and selected_title != normalized_current),
        "repeatMeta": best.get("repeatMeta") or {},
        "reason": "repeat_safe_fallback",
    }


def _stabilize_repeated_title(
    *,
    candidate_title: str,
    recent_titles: list[str],
    topic: str,
    content: str,
    user_keywords: list[str],
    full_name: str,
    category: str,
    status: str,
    context_analysis: Dict[str, Any],
    role_keyword_policy: Optional[Dict[str, Any]] = None,
    poll_fact_table: Optional[Dict[str, Any]] = None,
    poll_focus_bundle: Optional[Dict[str, Any]] = None,
) -> tuple[str, Dict[str, Any]]:
    normalized_candidate = _normalize_title_surface_local(candidate_title) or candidate_title
    repeat_meta = _compute_title_repeat_meta(normalized_candidate, recent_titles)
    if not _title_repeat_needs_fallback(repeat_meta):
        return normalized_candidate, {
            "repeated": False,
            "applied": False,
            "repeatMeta": repeat_meta,
            "reason": "",
        }

    fallback = _build_repeat_safe_title_fallback(
        current_title=normalized_candidate,
        recent_titles=recent_titles,
        topic=topic,
        content=content,
        user_keywords=user_keywords,
        full_name=full_name,
        category=category,
        status=status,
        context_analysis=context_analysis,
        role_keyword_policy=role_keyword_policy,
        poll_fact_table=poll_fact_table,
        poll_focus_bundle=poll_focus_bundle,
    )
    stabilized_title = _normalize_title_surface_local(fallback.get("title") or normalized_candidate) or normalized_candidate
    return stabilized_title, {
        "repeated": True,
        "applied": stabilized_title != normalized_candidate,
        "repeatMeta": repeat_meta,
        "fallbackReason": str(fallback.get("reason") or "").strip(),
        "fallbackRepeatMeta": fallback.get("repeatMeta") if isinstance(fallback.get("repeatMeta"), dict) else {},
    }


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
  </rules>
  <topic>{topic}</topic>
  <title>{title}</title>
  <keywords>{', '.join(user_keywords)}</keywords>
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
        return {"passed": True, "score": 0, "reason": "scoring_error", "title": candidate}


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
) -> tuple[str, Dict[str, Any]]:
    candidate = _normalize_title_surface_local(candidate_title)
    previous = _normalize_title_surface_local(previous_title)

    def _compose_repaired_title_surface(base_title: str, start: int, end: int, replacement: str) -> str:
        prefix = str(base_title[:start] or "").rstrip(" ,·:;!?")
        suffix = re.sub(r"^[\s,·:;!?]+", "", str(base_title[end:] or ""))
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
                replacements = [
                    build_role_keyword_intent_text(normalized_keyword, context="title", variant_index=0),
                    build_role_keyword_intent_text(normalized_keyword, context="title", variant_index=1),
                    build_role_keyword_intent_text(normalized_keyword, context="title", variant_index=2),
                ]
            elif mode == "blocked":
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
    poll_focus_bundle: Optional[Dict[str, Any]] = None,
) -> tuple[str, Dict[str, Any]]:
    candidate = _normalize_title_surface_local(candidate_title)
    previous = _normalize_title_surface_local(previous_title)
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
        )
        guard_info["phase"] = phase
        return guarded_title, guard_info
    except ApiError as exc:
        reason = str(exc or "").strip()
        if reason.startswith("제목 검증 실패:"):
            reason = reason.split(":", 1)[1].strip()
        fallback_title = previous or candidate
        fallback_source = "previous_fallback" if previous else "candidate_fallback"
        logger.warning(
            "Draft title guard failure downgraded to fallback (phase=%s, source=%s, reason=%s)",
            phase,
            fallback_source,
            reason,
        )
        return fallback_title, {
            "accepted": True,
            "source": fallback_source,
            "score": 0,
            "reason": reason or "draft_title_guard_failed",
            "repaired": False,
            "phase": phase,
            "nonFatal": True,
            "fallbackUsed": True,
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
) -> Dict[str, Any]:
    """기준 미충족 시 EditorAgent로 1회 교정 시도."""
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
    normalized_purpose = str(purpose or "repair").strip().lower()

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


def _choose_pipeline_route(raw_route: Any, *, is_admin: bool, is_tester: bool) -> str:
    return str(raw_route or "modular").strip() or "modular"


def handle_generate_posts_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    started_ms = int(time.time() * 1000)
    uid = req.auth.uid if req.auth else ""
    _ensure_user(uid)

    data = req.data if isinstance(req.data, dict) else {}
    if isinstance(data.get("data"), dict):
        data = data["data"]

    topic, category = _topic_and_category(data)
    target_word_count = _target_word_count(data, category)

    progress_session_id = str(data.get("progressSessionId") or f"{uid}_{int(time.time() * 1000)}")
    progress = ProgressTracker(progress_session_id)
    progress.step_preparing()

    # 프로필 로드 (권한/세션/경고/응답 메타데이터용)
    profile_bundle = load_user_profile(uid, category=category, topic=topic, options={"strictSourceOnly": True})
    user_profile = _safe_dict(profile_bundle.get("userProfile"))
    is_admin = bool(profile_bundle.get("isAdmin") is True)
    is_tester = bool(profile_bundle.get("isTester") is True)
    full_name = str(
        data.get("fullName")
        or user_profile.get("fullName")
        or user_profile.get("name")
        or ""
    ).strip()
    daily_limit_warning = _calc_daily_limit_warning(user_profile)
    editor_polish_enabled = _to_bool(data.get("editorPolish"), False)
    editor_second_pass_enabled = _to_bool(data.get("editorSecondPass"), False)

    requested_session_id = str(data.get("sessionId") or "").strip()
    prior_session_snapshot: Dict[str, Any] = {}
    carried_recent_titles: list[str] = []
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
            carried_recent_titles = _normalize_recent_title_memory_values(
                prior_session_snapshot.get("recentTitles")
            )[:5]
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

    quality_warnings: list[str] = []
    request_recent_title_memory = _collect_recent_title_memory(
        data=data if isinstance(data, dict) else {},
        pipeline_result={},
        session=session,
        draft_title="",
        include_current_titles=False,
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
    stabilized_draft_title, draft_repeat_meta = _stabilize_repeated_title(
        candidate_title=generated_title,
        recent_titles=request_recent_title_memory,
        topic=topic,
        content=generated_content,
        user_keywords=user_keywords,
        full_name=full_name,
        category=category,
        status=str(data.get("status") or user_profile.get("status") or ""),
        context_analysis=context_analysis_for_title,
        role_keyword_policy=role_keyword_policy,
        poll_fact_table=poll_fact_table,
        poll_focus_bundle=poll_focus_bundle,
    )
    if draft_repeat_meta.get("applied"):
        logger.info(
            "Draft title repetition fallback applied: \"%s\" -> \"%s\"",
            generated_title,
            stabilized_draft_title,
        )
        _append_quality_warning(
            quality_warnings,
            "반복 제목을 피하기 위해 초안 제목을 다른 안전한 표현으로 조정했습니다.",
        )
    generated_title = stabilized_draft_title
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
    )
    keyword_validation = build_keyword_validation(initial_keyword_result)
    keyword_counts = _extract_keyword_counts(initial_keyword_result)
    word_count = _to_int(pipeline_result.get("wordCount"), _count_chars_no_space(generated_content))
    stance_count = _extract_stance_count(pipeline_result)
    min_required_chars = _calc_min_required_chars(target_word_count, stance_count)
    status_for_validation = str(data.get("status") or user_profile.get("status") or "")
    title_last_valid = generated_title
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
    subheading_entity_gate: Dict[str, Any] = {
        "attempted": False,
        "applied": False,
        "replacements": [],
        "skippedReason": "",
    }
    integrity_editor_repair: Dict[str, Any] = {
        "attempted": 0,
        "applied": 0,
        "error": None,
        "summary": [],
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
        )
        legal_issues = _extract_legal_gate_issues(final_heuristic)
        final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
        final_role_issues = _extract_role_consistency_issues(
            generated_content,
            role_facts,
        )
        final_integrity_issues = _detect_integrity_gate_issues(generated_content)
        final_blocking_integrity_issues = _extract_blocking_integrity_issues(final_integrity_issues)

    heading_anchor = _ensure_user_keyword_in_subheading_once(
        generated_content,
        gate_user_keywords,
        preferred_keyword=conflicting_role_keyword if conflicting_role_keyword in gate_user_keywords else "",
    )
    if heading_anchor.get("edited"):
        candidate_content = str(heading_anchor.get("content") or generated_content)
        if _apply_content_repair("keyword_heading_anchor", candidate_content):
            logger.info(
                "검색어 소제목 앵커링 적용: keyword=%s before=%s after=%s",
                heading_anchor.get("keyword"),
                heading_anchor.get("headingBefore"),
                heading_anchor.get("headingAfter"),
            )

    integrity_repair = _repair_integrity_noise_once(generated_content)
    if integrity_repair.get("edited"):
        integrity_candidate = str(integrity_repair.get("content") or generated_content)
        if _apply_content_repair("integrity_noise_repair", integrity_candidate):
            logger.info(
                "무결성 노이즈 자동 보정 적용: actions=%s",
                integrity_repair.get("actions"),
            )

    initial_keyword_gate_ok, initial_keyword_gate_msg = _validate_keyword_gate(keyword_validation, gate_user_keywords)
    initial_heuristic = run_heuristic_validation_sync(
        generated_content,
        status_for_validation,
        generated_title,
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

    editor_should_run = bool(legal_issues or pre_editor_extra_issues) or editor_polish_enabled
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
                    poll_focus_bundle=poll_focus_bundle,
                )
                title_guard_trace.append(guard_info)
                generated_title = guarded_title
                if guard_info.get("source") == "candidate":
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
    )
    legal_issues = _extract_legal_gate_issues(final_heuristic)
    residual_repetition_issues = _extract_repetition_gate_issues(final_heuristic)
    residual_integrity_issues = _detect_integrity_gate_issues(generated_content)
    residual_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
    residual_role_issues = _extract_role_consistency_issues(
        generated_content,
        role_facts,
    )
    residual_extra_issues = [*residual_integrity_issues, *residual_speaker_issues, *residual_role_issues]
    if editor_second_pass_enabled and (residual_repetition_issues or residual_extra_issues) and not legal_issues:
        editor_second_pass["attempted"] = True
        logger.info(
            "EditorAgent second-pass repair triggered: %s",
            "; ".join([*(residual_repetition_issues[:2]), *(residual_extra_issues[:2])]),
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
                    poll_focus_bundle=poll_focus_bundle,
                )
                title_guard_trace.append(guard_info)
                generated_title = guarded_title
                if guard_info.get("source") == "candidate":
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
        poll_focus_bundle=poll_focus_bundle,
    )
    title_guard_trace.append(final_title_guard)
    generated_title = final_guarded_title
    if final_title_guard.get("source") == "candidate":
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
        full_name=full_name,
        user_keywords=user_keywords,
        role_facts=role_facts,
        poll_fact_table=poll_fact_table,
        poll_focus_bundle=poll_focus_bundle,
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
    h2_entity_repair = _repair_subheading_entity_consistency_once(
        generated_content,
        known_person_names,
        preferred_names=[full_name],
        role_facts=role_facts,
    )
    h2_entity_candidate = str(h2_entity_repair.get("content") or generated_content).strip()
    subheading_entity_gate["replacements"] = list(h2_entity_repair.get("replacements") or [])
    if h2_entity_candidate and h2_entity_candidate != generated_content:
        corrupted, reason = _detect_content_repair_corruption(generated_content, h2_entity_candidate)
        if not corrupted:
            generated_content = h2_entity_candidate
            word_count = _count_chars_no_space(generated_content)
            subheading_entity_gate["applied"] = True
            final_heuristic = run_heuristic_validation_sync(
                generated_content,
                status_for_validation,
                generated_title,
            )
            legal_issues = _extract_legal_gate_issues(final_heuristic)
            final_speaker_issues = _extract_speaker_consistency_issues(generated_content, full_name)
            final_role_issues = _extract_role_consistency_issues(
                generated_content,
                role_facts,
            )
        else:
            subheading_entity_gate["skippedReason"] = str(reason or "corruption-risk")
            logger.warning("Subheading entity repair skipped due to corruption risk: %s", reason)

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
                poll_focus_bundle=poll_focus_bundle,
            )
            title_guard_trace.append(guard_info)
            generated_title = guarded_title
            if guard_info.get("source") == "candidate":
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

            stabilized_final_title, final_repeat_meta = _stabilize_repeated_title(
                candidate_title=generated_title,
                recent_titles=recent_title_memory,
                topic=topic,
                content=generated_content,
                user_keywords=user_keywords,
                full_name=full_name,
                category=category,
                status=status_for_validation,
                context_analysis=context_analysis_for_title,
                role_keyword_policy=role_keyword_policy,
                poll_fact_table=poll_fact_table,
                poll_focus_bundle=poll_focus_bundle,
            )
            if final_repeat_meta.get("applied"):
                logger.info(
                    "Independent final title repetition fallback applied: \"%s\" -> \"%s\"",
                    generated_title,
                    stabilized_final_title,
                )
                generated_title = stabilized_final_title
                title_last_valid = generated_title

            independent_final_title["applied"] = True
        except Exception as exc:
            independent_final_title["error"] = str(exc)
            independent_final_title["fallbackUsed"] = True
            rollback_title, rollback_repeat_meta = _stabilize_repeated_title(
                candidate_title=draft_title,
                recent_titles=recent_title_memory,
                topic=topic,
                content=generated_content,
                user_keywords=user_keywords,
                full_name=full_name,
                category=category,
                status=status_for_validation,
                context_analysis=context_analysis_for_title,
                role_keyword_policy=role_keyword_policy,
                poll_fact_table=poll_fact_table,
                poll_focus_bundle=poll_focus_bundle,
            )
            generated_title = rollback_title
            if rollback_repeat_meta.get("applied"):
                _append_quality_warning(
                    quality_warnings,
                    "최종 제목 재생성 실패 시 같은 제목으로 되돌아가지 않도록 다른 안전한 제목으로 보정했습니다.",
                )
            logger.warning("Independent final title rejected; using draft/repeat-safe title: %s", exc)
    else:
        independent_final_title["fallbackUsed"] = True

    final_heuristic = run_heuristic_validation_sync(
        generated_content,
        status_for_validation,
        generated_title,
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
    final_keyword_gate_ok, final_keyword_gate_msg = _validate_keyword_gate(keyword_validation, gate_user_keywords)
    final_over_max_keywords = _collect_over_max_keywords(keyword_validation, user_keywords)
    if final_over_max_keywords:
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

    # 하드 차단: 화자 정체성 불일치, 문장 무결성 치명 오류, 선거법 위반.
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
        issue_text = "; ".join(legal_issues[:2])
        logger.warning(
            "QUALITY_METRIC generate_posts outcome=blocked first_pass=%s blockers=%s warnings=%s repairs=%s",
            int(first_pass_passed),
            len(legal_issues),
            len(quality_warnings),
            int(
                any(
                    [
                        length_repair_applied,
                        keyword_repair_applied,
                        repetition_rule_repair_applied,
                        repetition_llm_repair_applied,
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
        "subCategory": str(data.get("subCategory") or ""),
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
                    bool(editor_auto_repair.get("applied")),
                    bool(editor_second_pass.get("applied")),
                    editor_keyword_repair_applied,
                    last_mile_postprocess_applied,
                ]
            )
        ),
        bool(editor_auto_repair.get("applied")),
    )

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
                    "hardBlockers": ["SPEAKER_IDENTITY", "INTEGRITY", "ELECTION_LAW"],
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
                        "integrityEditorRepairAttempted": int(integrity_editor_repair.get("attempted") or 0),
                        "integrityEditorRepairApplied": int(integrity_editor_repair.get("applied") or 0),
                        "integrityEditorRepairError": str(integrity_editor_repair.get("error") or ""),
                        "integrityEditorRepairSummary": list(integrity_editor_repair.get("summary") or []),
                        "lastMilePostprocessApplied": last_mile_postprocess_applied,
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
