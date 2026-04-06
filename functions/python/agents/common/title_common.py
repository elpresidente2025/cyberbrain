"""?? ?? ?? ??? ?? ??."""

import logging
from difflib import SequenceMatcher
import re
from typing import Any, Dict, List, Optional

from .election_rules import get_election_stage
from .editorial import TITLE_SPEC
from .role_keyword_policy import extract_role_keyword_parts, should_block_role_keyword

logger = logging.getLogger(__name__)

TITLE_LENGTH_HARD_MIN = TITLE_SPEC['hardMin']
TITLE_LENGTH_HARD_MAX = TITLE_SPEC['hardMax']
TITLE_LENGTH_OPTIMAL_MIN = TITLE_SPEC['optimalMin']
TITLE_LENGTH_OPTIMAL_MAX = TITLE_SPEC['optimalMax']

EVENT_NAME_MARKERS = (
    '출판기념회',
    '방송토론',
    '간담회',
    '설명회',
    '토론회',
    '기자회견',
    '세미나',
    '강연',
    '북토크',
    '토크콘서트',
    '팬미팅',
)

SLOT_PLACEHOLDER_NAMES = (
    '지역명', '장소명', '인물명', '행사명', '날짜', '주제명', '정책명', '사업명',
    '수치', '수량', '금액', '단위', '성과지표', '지원항목', '현안', '민원주제',
    '이슈명', '정책쟁점', '문제명', '대안수', '이전값', '현재값', '개선폭',
    '기존안', '개선안', '비용항목', '이전금액', '현재금액', '개관시기', '기간',
    '개선수치', '법안명', '핵심지원', '조례명', '핵심변경', '숫자', '핵심혜택',
    '핵심변화', '연도/분기', '보고서명', '핵심성과수', '월/분기', '업무명',
    '건수', '정기브리핑명', '월호', '핵심주제', '예산항목', '혜택수치', '성과수',
)

COMPETITOR_INTENT_TAIL_FORBIDDEN_TOKENS = (
    "비전",
    "가능성",
    "가상대결",
    "양자대결",
    "접전",
    "경쟁력",
    "득표율",
)

TITLE_FIRST_PERSON_PATTERN = re.compile(
    r"(저는|제가|저의|저만의|나는|내가|나의|제\s*(?:정책|공약|해법|비전|생각|진심|메시지|약속)|내\s*(?:정책|공약|해법|비전|생각|진심|메시지|약속))",
    re.IGNORECASE,
)

def detect_content_type(content_preview: str, category: str) -> str:
    try:
        text = content_preview.lower()
        
        has_numbers = re.search(r'\d+억|\d+만원|\d+%|\d+명|\d+건|\d+가구|\d+곳', content_preview)
        has_comparison = re.search(r'→|에서|으로|전년|대비|개선|감소|증가|변화', text)
        has_question = bool(
            re.search(r'[?？]', content_preview)
            or re.search(
                r'(?:어떻게\s*(?:풀|해결|바꿀|달라|해야)|'
                r'무엇(?:이|을)\s*(?:달라|해결|바꿀|지원|의미)|'
                r'왜\s*(?:지금|필요|중요|시급|달라)|'
                r'얼마(?:나|까지)?\s*(?:지원|혜택|보상|들|주)|'
                r'언제\s*(?:해결|완료|되|바뀌|시작))',
                text,
            )
        )
        has_legal_terms = re.search(r'법안|조례|법률|제도|개정|발의|통과|제정', text)
        has_policy_terms = re.search(r'정책|공약|비전|예산|입법|의정|추진|현안|민생|지역화폐|기본소득', text)
        has_time_terms = re.search(r'2025년|상반기|하반기|분기|월간|연간|보고서|리포트', text)
        has_local_terms = re.search(r'[가-힣]+(동|구|군|시|읍|면|리)(?:[가-힣]|\s|,|$)', content_preview)
        has_issue_terms = re.search(r'개혁|분권|양극화|격차|투명성|문제점|대안', text)
        has_commentary_terms = re.search(r'칭찬|질타|비판|논평|평가|소신|침묵|역부족|낙제|심판', text)
        has_politician_names = re.search(r'박형준|조경태|윤석열|이재명|한동훈', content_preview)
        has_first_person = re.search(r'저는|제가|저의|저\b', content_preview)
        has_profile_terms = re.search(r'의원|위원장|보좌관|사무국장|대통령|지역구|당원|시민|주민|구민', content_preview)
        has_profile_narrative = bool(has_first_person and has_profile_terms)
        
        # Priority for user content signals
        if has_time_terms and ('보고' in text or '리포트' in text or '현황' in text):
            return 'TIME_BASED'
        if has_legal_terms or (has_policy_terms and not has_question):
            return 'EXPERT_KNOWLEDGE'
        if has_commentary_terms and has_politician_names:
            return 'COMMENTARY'
        if has_comparison and has_numbers:
            return 'COMPARISON'
        if has_question and not (has_policy_terms or has_profile_narrative or has_local_terms):
            return 'QUESTION_ANSWER'
        if has_numbers and not has_issue_terms and not has_profile_narrative:
            return 'DATA_BASED'
        if has_issue_terms and not has_local_terms and not has_profile_narrative:
            return 'ISSUE_ANALYSIS'
        if has_profile_narrative:
            return 'COMMENTARY'
        if has_local_terms:
            return 'LOCAL_FOCUSED'
        
        category_mapping = {
            'activity-report': 'DATA_BASED',
            'policy-proposal': 'EXPERT_KNOWLEDGE',
            'local-issues': 'LOCAL_FOCUSED',
            'current-affairs': 'ISSUE_ANALYSIS',
            'daily-communication': 'VIRAL_HOOK', # Changed to VIRAL_HOOK for daily coms
            'bipartisan-cooperation': 'COMMENTARY'
        }
        
        return category_mapping.get(category, 'VIRAL_HOOK') # Default to VIRAL_HOOK
    except Exception as e:
        logger.error(f'Error in detect_content_type: {e}')
        return 'VIRAL_HOOK'


_TITLE_FAMILY_IDS = (
    'SLOGAN_COMMITMENT',
    'VIRAL_HOOK',
    'DATA_BASED',
    'QUESTION_ANSWER',
    'COMPARISON',
    'LOCAL_FOCUSED',
    'EXPERT_KNOWLEDGE',
    'TIME_BASED',
    'ISSUE_ANALYSIS',
    'COMMENTARY',
)

_TITLE_FAMILY_PRIORITY = (
    'SLOGAN_COMMITMENT',
    'EXPERT_KNOWLEDGE',
    'DATA_BASED',
    'QUESTION_ANSWER',
    'COMPARISON',
    'LOCAL_FOCUSED',
    'ISSUE_ANALYSIS',
    'TIME_BASED',
    'COMMENTARY',
    'VIRAL_HOOK',
)

_SLOGAN_COMMITMENT_PATTERN = re.compile(
    r'(책임감|지켜온|지켜온\s+책임감|곁을\s+지키|곁에|끝까지|해내겠|다하겠|되겠|약속|다짐|함께\s+하겠|역할을\s+해내겠)',
    re.IGNORECASE,
)
_SLOGAN_RELATION_PATTERN = re.compile(r'(구민|시민|주민|당원)')
_GENERIC_REPORT_SURFACE_PATTERN = re.compile(
    r'(현안\s*해결|미래\s*비전|비전\s*제시|정책\s*방향|실행\s*과제|의정활동\s*성과)',
    re.IGNORECASE,
)


def _build_title_family_source_text(params: Optional[Dict[str, Any]]) -> str:
    params_dict = params if isinstance(params, dict) else {}
    source_text = " ".join(
        str(params_dict.get(key) or "")
        for key in ("topic", "stanceText", "contentPreview", "backgroundText")
        if str(params_dict.get(key) or "").strip()
    )
    source_text = re.sub(r"<[^>]*>", " ", source_text)
    return re.sub(r"\s+", " ", source_text).strip()


def select_title_family(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    params_dict = params if isinstance(params, dict) else {}
    forced_type = str(
        params_dict.get("_forcedType")
        or params_dict.get("selectedTitleFamily")
        or ""
    ).strip()
    if forced_type in _TITLE_FAMILY_IDS:
        return {
            "selectedFamily": forced_type,
            "scores": {family: int(family == forced_type) * 100 for family in _TITLE_FAMILY_IDS},
            "prior": forced_type,
            "reasons": {forced_type: ["forced title family"]},
        }

    category = str(params_dict.get("category") or "").strip()
    content_preview = str(params_dict.get("contentPreview") or "")
    topic = str(params_dict.get("topic") or "")
    stance_text = str(params_dict.get("stanceText") or "")
    source_text = _build_title_family_source_text(params_dict)
    lowered_source = source_text.lower()

    prior = detect_content_type(content_preview, category)
    scores: Dict[str, int] = {family: 0 for family in _TITLE_FAMILY_IDS}
    reasons: Dict[str, List[str]] = {family: [] for family in _TITLE_FAMILY_IDS}

    def _boost(family: str, score: int, reason: str) -> None:
        if family not in scores or score <= 0:
            return
        scores[family] += score
        if reason and len(reasons[family]) < 4:
            reasons[family].append(reason)

    if prior in scores:
        _boost(prior, 3, f"detect_content_type prior={prior}")

    has_numbers = bool(re.search(r'\d+(?:억|만원|%|명|건|가구|곳|개|회|일|년|개월|분기)', source_text))
    has_question = bool(
        re.search(r'[?？]', source_text)
        or re.search(r'(어떻게|무엇|왜|얼마|언제|어떤)', source_text)
    )
    has_comparison = bool(re.search(r'(→|vs|대비|격차|앞섰|추월|개선|감소|증가|변화)', source_text, re.IGNORECASE))
    has_legal_terms = bool(re.search(r'(법안|조례|법률|제도|개정|발의|통과|제정)', source_text))
    has_policy_terms = bool(re.search(r'(정책|공약|비전|예산|입법|의정|추진|현안|민생|기본소득|지역화폐)', source_text))
    has_time_terms = bool(re.search(r'(상반기|하반기|분기|월간|연간|보고서|리포트|브리핑|뉴스레터)', source_text))
    has_local_terms = bool(re.search(r'[가-힣]+(동|구|군|시|읍|면|리)(?:[가-힣]|\s|,|$)', source_text))
    has_issue_terms = bool(re.search(r'(개혁|분권|양극화|격차|투명성|문제점|대안|위기|침체|부담|부진)', source_text))
    has_commentary_terms = bool(re.search(r'(논평|질타|비판|평가|반박|지적|소신|판단|입장)', source_text))
    has_profile_terms = bool(re.search(r'(의원|위원장|보좌관|사무국장|대통령|지역구|당원|시민|주민|구민)', source_text))
    has_first_person = bool(re.search(r'(저는|제가|저의|저\b)', source_text))
    has_profile_narrative = has_first_person and has_profile_terms
    has_slogan_commitment = bool(_SLOGAN_COMMITMENT_PATTERN.search(source_text))
    has_relation_target = bool(_SLOGAN_RELATION_PATTERN.search(source_text))
    has_generic_report_surface = bool(_GENERIC_REPORT_SURFACE_PATTERN.search(source_text))
    topic_has_slogan_commitment = bool(_SLOGAN_COMMITMENT_PATTERN.search(topic) or _SLOGAN_COMMITMENT_PATTERN.search(stance_text))

    if has_numbers:
        _boost("DATA_BASED", 4, "수치/단위 신호")
    if has_question:
        _boost("QUESTION_ANSWER", 4, "질문형 신호")
    if has_comparison and has_numbers:
        _boost("COMPARISON", 6, "비교/대조 수치 신호")
    elif has_comparison:
        _boost("COMPARISON", 3, "비교/대조 신호")
    if has_local_terms:
        _boost("LOCAL_FOCUSED", 4, "지역 단위 신호")
    if has_legal_terms:
        _boost("EXPERT_KNOWLEDGE", 6, "법안/조례 신호")
    elif has_policy_terms and not has_question:
        _boost("EXPERT_KNOWLEDGE", 3, "정책/추진 신호")
    if has_time_terms:
        _boost("TIME_BASED", 5, "정기 보고/시점 신호")
    if has_issue_terms and not has_profile_narrative:
        _boost("ISSUE_ANALYSIS", 4, "현안/문제 분석 신호")
    if has_commentary_terms:
        _boost("COMMENTARY", 5, "논평/평가 신호")
    elif has_profile_narrative:
        _boost("COMMENTARY", 2, "화자 자기서술 신호")
    if has_question and not (has_numbers or has_legal_terms or has_time_terms):
        _boost("VIRAL_HOOK", 2, "질문형 후킹")
    if re.search(r'(왜\s+지금|왜\s+다른가|선택의\s+이유|무엇이\s+다른가|주목받)', lowered_source):
        _boost("VIRAL_HOOK", 3, "서사 후킹 표현")

    if topic_has_slogan_commitment:
        _boost("SLOGAN_COMMITMENT", 6, "주제/입장문 다짐형 신호")
    if has_slogan_commitment:
        _boost("SLOGAN_COMMITMENT", 5, "책임/다짐 표현")
    if has_relation_target:
        _boost("SLOGAN_COMMITMENT", 2, "주민/당원 관계 표현")
    if has_profile_narrative and not (has_numbers or has_legal_terms or has_time_terms):
        _boost("SLOGAN_COMMITMENT", 3, "자기소개형 입장문")
    if has_generic_report_surface and not has_slogan_commitment:
        _boost("DATA_BASED", 1, "보고서형 표면")

    if category == "daily-communication":
        _boost("SLOGAN_COMMITMENT", 2, "일상 소통 카테고리")
        _boost("VIRAL_HOOK", 1, "일상 소통 카테고리")
    elif category == "activity-report":
        _boost("DATA_BASED", 2, "의정활동 보고 카테고리")
    elif category == "policy-proposal":
        _boost("EXPERT_KNOWLEDGE", 2, "정책 제안 카테고리")
    elif category == "current-affairs":
        _boost("ISSUE_ANALYSIS", 2, "현안 카테고리")

    best_family = "VIRAL_HOOK"
    best_score = -1
    for family in _TITLE_FAMILY_PRIORITY:
        score = int(scores.get(family, 0))
        if score > best_score:
            best_score = score
            best_family = family

    if best_score <= 0 and prior in scores:
        best_family = prior
    if best_score <= 0:
        best_family = "VIRAL_HOOK"

    return {
        "selectedFamily": best_family,
        "scores": scores,
        "prior": prior,
        "reasons": reasons,
        "sourceText": source_text,
    }


def resolve_title_family(params: Optional[Dict[str, Any]]) -> str:
    family_meta = select_title_family(params)
    selected_family = str(family_meta.get("selectedFamily") or "").strip()
    if selected_family in _TITLE_FAMILY_IDS:
        return selected_family
    return "VIRAL_HOOK"

def extract_numbers_from_content(content: str) -> Dict[str, Any]:
    if not content:
        return {'numbers': [], 'instruction': ''}
        
    try:
        patterns = [
            r'\d+(?:,\d{3})*억원?',
            r'\d+(?:,\d{3})*만원?',
            r'\d+(?:\.\d+)?%',
            r'\d+(?:,\d{3})*명',
            r'\d+(?:,\d{3})*건',
            r'\d+(?:,\d{3})*가구',
            r'\d+(?:,\d{3})*곳',
            r'\d+(?:,\d{3})*개',
            r'\d+(?:,\d{3})*회',
            r'\d+배',
            r'\d+(?:,\d{3})*원',
            r'\d+일',
            r'\d+개월',
            r'\d+년',
            r'\d+분기'
        ]
        
        all_matches = set()
        for pattern in patterns:
            matches = re.findall(pattern, content)
            all_matches.update(matches)
            
        numbers = list(all_matches)
        
        if not numbers:
            return {
                'numbers': [],
                'instruction': '\\n【숫자 제약】본문에 구체적 수치가 없습니다. 숫자 없이 제목을 작성하세요.\\n'
            }
            
        formatted_numbers = ', '.join(numbers[:10])
        if len(numbers) > 10:
            formatted_numbers += f' (외 {len(numbers) - 10}개)'
            
        instruction = f"""
<number_validation priority="critical">
  <description>본문에 등장하는 숫자만 사용 가능</description>
  <allowed_numbers>{formatted_numbers}</allowed_numbers>
  <rule type="must-not">위 목록에 없는 숫자는 절대 제목에 넣지 마세요</rule>
  <examples>
    <good>본문에 "274명"이 있으면 "청년 일자리 274명"</good>
    <bad reason="날조">본문에 "85억"이 없는데 "지원금 85억"</bad>
  </examples>
</number_validation>
"""
        return {'numbers': numbers, 'instruction': instruction}
    except Exception as e:
        logger.error(f'Error in extract_numbers_from_content: {e}')
        return {'numbers': [], 'instruction': ''}

def get_election_compliance_instruction(status: str) -> str:
    try:
        election_stage = get_election_stage(status)
        is_pre_candidate = election_stage.get('name') == 'STAGE_1'
        
        if not is_pre_candidate: return ''
        
        return f"""
<election_compliance status="{status}" stage="pre-candidate" priority="critical">
  <description>선거법 준수 (현재 상태: {status} - 예비후보 등록 이전)</description>
  <banned_expressions>
    <expression>"약속", "공약", "약속드립니다"</expression>
    <expression>"당선되면", "당선 후"</expression>
    <expression>"~하겠습니다" (공약성 미래 약속)</expression>
    <expression>"지지해 주십시오"</expression>
  </banned_expressions>
  <allowed_expressions>
    <expression>"정책 방향", "정책 제시", "비전 공유"</expression>
    <expression>"연구하겠습니다", "노력하겠습니다"</expression>
    <expression>"추진", "추구", "검토"</expression>
  </allowed_expressions>
  <examples>
    <bad>"청년 기본소득, 꼭 약속드리겠습니다"</bad>
    <good>"청년 기본소득, 정책 방향 제시"</good>
  </examples>
</election_compliance>
"""
    except Exception as e:
        logger.error(f'Error in get_election_compliance_instruction: {e}')
        return ''

def are_keywords_similar(kw1: str, kw2: str) -> bool:
    """
    두 키워드가 유사한지 판별 (공통 어절이 있는지)
    예: "서면 영광도서", "부산 영광도서" → 공통 "영광도서" → 유사
    예: "계양산 러브버그 방역", "계양구청" → 공통 없음 → 독립
    """
    if not kw1 or not kw2:
        return False
    words1 = kw1.split()
    words2 = kw2.split()
    return any(w in words2 and len(w) >= 2 for w in words1)

def _collect_recent_title_values(params: Optional[Dict[str, Any]], *, limit: int = 5) -> List[str]:
    params_dict = params if isinstance(params, dict) else {}
    values: List[str] = []
    seen: set[str] = set()
    for key in ("recentTitles", "previousTitles"):
        raw_items = params_dict.get(key)
        if not isinstance(raw_items, list):
            continue
        for raw_item in raw_items:
            title = ""
            if isinstance(raw_item, dict):
                title = str(raw_item.get("title") or "").strip()
            else:
                title = str(raw_item or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            values.append(title)
            if len(values) >= limit:
                return values
    return values

def _split_title_anchor_and_tail(title: str, *, primary_keyword: str = "") -> Dict[str, str]:
    normalized_title = normalize_title_surface(title) or str(title or "").strip()
    if not normalized_title:
        return {"anchor": "", "tail": ""}

    for separator in (",", ":", ";"):
        if separator in normalized_title:
            left, right = normalized_title.split(separator, 1)
            return {"anchor": left.strip(), "tail": right.strip()}

    normalized_primary = str(primary_keyword or "").strip()
    if normalized_primary and normalized_primary in normalized_title:
        split_index = normalized_title.find(normalized_primary) + len(normalized_primary)
        tail = normalized_title[split_index:]
        tail = re.sub(
            r"^[\s,·:;!?]*(?:출마(?:설|론|가능성)?|거론(?:\s*속|\s*이유|되나|되는)?|하마평|후보론|가능성|구도|변수)?[\s,·:;!?]*",
            "",
            tail,
        ).strip()
        return {"anchor": normalized_title[:split_index].strip(), "tail": tail}

    return {"anchor": normalized_title, "tail": ""}

def _find_title_first_person_expression(text: Any) -> str:
    normalized_text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized_text:
        return ""
    match = TITLE_FIRST_PERSON_PATTERN.search(normalized_text)
    return str(match.group(0) or "").strip() if match else ""

def _contains_competitor_tail_forbidden_token(text: Any) -> bool:
    normalized_text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized_text:
        return False
    return any(token in normalized_text for token in COMPETITOR_INTENT_TAIL_FORBIDDEN_TOKENS)

def _filter_required_title_keywords(
    user_keywords: List[str],
    role_keyword_policy: Optional[Dict[str, Any]] = None,
) -> List[str]:
    filtered: List[str] = []
    for item in user_keywords or []:
        keyword = str(item or "").strip()
        if not keyword:
            continue
        if should_block_role_keyword(role_keyword_policy, keyword):
            continue
        filtered.append(keyword)
    return filtered

def normalize_title_surface(title: str) -> str:
    cleaned = str(title or '').translate(
        str.maketrans(
            {
                '“': '"',
                '”': '"',
                '„': '"',
                '‟': '"',
            }
        )
    )
    cleaned = cleaned.strip().strip('"\'')
    if not cleaned:
        return ''

    candidate = cleaned
    # 소수점 앞뒤 공백 정리: "0. 7%" -> "0.7%", "3 .5" -> "3.5"
    candidate = re.sub(r'(\d)\s*\.\s*(\d)', r'\1.\2', candidate)
    cleaned = candidate

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'\s+([,.:;!?])', r'\1', cleaned)
    cleaned = re.sub(r'([,:;!?])(?=[^\s\]\)\}])', r'\1 ', cleaned)
    # 마침표는 소수점/날짜 숫자 구간을 제외하고만 뒤 공백을 부여한다.
    cleaned = re.sub(r'(\d)\.(?=[^\s\]\)\}\d])', r'\1. ', cleaned)
    cleaned = re.sub(r'(?<!\d)\.(?=[^\s\]\)\}\d])', '. ', cleaned)
    cleaned = re.sub(r'\(\s+', '(', cleaned)
    cleaned = re.sub(r'\s+\)', ')', cleaned)
    cleaned = re.sub(r'\[\s+', '[', cleaned)
    cleaned = re.sub(r'\s+\]', ']', cleaned)
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    cleaned = re.sub(r',(?:\s*,)+', ', ', cleaned)
    cleaned = re.sub(r'[!?]{2,}', '?', cleaned)
    return cleaned.strip(' ,')

def _fit_title_length(title: str) -> str:
    if not title:
        return ''
    normalized = re.sub(r'\s+', ' ', title).strip()
    if len(normalized) <= TITLE_LENGTH_HARD_MAX:
        return normalized
    compact = normalized.replace(' 핵심 메시지', '').replace(' 핵심', '').replace(' 현장', '')
    compact = re.sub(r'\s+', ' ', compact).strip()
    return compact

def _detect_truncated_title_reason(title: str) -> str:
    normalized = normalize_title_surface(title)
    if not normalized:
        return ''

    stripped = normalized.strip()
    if not stripped:
        return ''
    if '...' in stripped or '…' in stripped:
        return '말줄임표 포함'
    if re.search(r'(?:^|[\s,:;!?])\d{1,3}$', stripped):
        return '숫자로 비정상 종료'

    wrapper_pairs = (
        ('(', ')'),
        ('[', ']'),
        ('<', '>'),
        ('《', '》'),
        ('"', '"'),
        ("'", "'"),
    )
    for opener, closer in wrapper_pairs:
        if opener == closer:
            if stripped.count(opener) % 2 == 1:
                return f'{opener} 인용부호 불균형'
            continue
        if stripped.count(opener) > stripped.count(closer):
            return f'{opener} 닫힘 누락'

    return ''


_CONSECUTIVE_DUPLICATE_TOKEN_RE = re.compile(
    r"(?<![0-9A-Za-z가-힣])(?P<token>[0-9A-Za-z가-힣]{2,})(?:\s+(?P=token))+(?![0-9A-Za-z가-힣])",
    re.IGNORECASE,
)
_MISSING_OBJECT_PARTICLE_TITLE_RE = re.compile(
    r"(?P<head>[0-9A-Za-z가-힣]{2,16})\s+위한\s+(?P<tail>[0-9A-Za-z가-힣]{2,24})",
    re.IGNORECASE,
)
_DUPLICATED_POSSESSIVE_FOCUS_NAME_TITLE_RE = re.compile(
    r"^(?P<name>[0-9A-Za-z가-힣]{2,16})[,，]\s+(?P=name)의\s+\S+",
    re.IGNORECASE,
)
_POSSESSIVE_EMPTY_MODIFIER_TITLE_RE = re.compile(
    r"(?P<head>[0-9A-Za-z가-힣]{2,16})의\s+없는\s+(?P<tail>[0-9A-Za-z가-힣]{2,24})",
    re.IGNORECASE,
)
_POSSESSIVE_AWKWARD_MODIFIER_TITLE_RE = re.compile(
    r"(?P<head>[0-9A-Za-z가-힣]{2,16})의\s+(?P<modifier>(?:되는|하는|있는|존중하는))\s+(?P<tail>[0-9A-Za-z가-힣]{2,24})",
    re.IGNORECASE,
)
_BARE_DAY_FRAGMENT_TITLE_RE = re.compile(
    r"(?P<day>\d{1,2}\s*일)(?P<tail>\s*[?？])",
    re.IGNORECASE,
)


def _pick_object_particle(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return "을"
    last_char = normalized[-1]
    code = ord(last_char)
    if 0xAC00 <= code <= 0xD7A3:
        has_batchim = (code - 0xAC00) % 28 != 0
        return "을" if has_batchim else "를"
    return "을"


def _collapse_consecutive_duplicate_title_tokens(title: str) -> str:
    updated = normalize_title_surface(title) or str(title or "").strip()
    if not updated:
        return ""

    for _ in range(4):
        collapsed = _CONSECUTIVE_DUPLICATE_TOKEN_RE.sub(lambda match: str(match.group("token") or "").strip(), updated)
        collapsed = normalize_title_surface(collapsed) or collapsed
        if collapsed == updated:
            break
        updated = collapsed
    return updated


def _repair_missing_object_particle_title_surface(title: str) -> str:
    normalized = normalize_title_surface(title) or str(title or "").strip()
    if not normalized:
        return ""

    def _replace(match: re.Match[str]) -> str:
        head = str(match.group("head") or "").strip()
        tail = str(match.group("tail") or "").strip()
        if not head or not tail:
            return match.group(0)
        return f"{head}{_pick_object_particle(head)} 위한 {tail}"

    repaired = _MISSING_OBJECT_PARTICLE_TITLE_RE.sub(_replace, normalized, count=1)
    return normalize_title_surface(repaired) or repaired


def _repair_possessive_empty_modifier_title_surface(
    title: str,
    params: Optional[Dict[str, Any]] = None,
) -> str:
    normalized = normalize_title_surface(title) or str(title or "").strip()
    if not normalized:
        return ""

    match = _POSSESSIVE_EMPTY_MODIFIER_TITLE_RE.search(normalized)
    if not match:
        return normalized

    tail = str(match.group("tail") or "").strip()
    if not tail:
        return normalized

    params_dict = params if isinstance(params, dict) else {}
    topic = normalize_title_surface(str(params_dict.get("topic") or "").strip())
    if topic:
        topic_match = re.search(
            rf"(?P<modifier>[0-9A-Za-z가-힣·\-\s]{{2,24}}?)\s+없는\s+{re.escape(tail)}",
            topic,
            re.IGNORECASE,
        )
        if topic_match:
            modifier = normalize_title_surface(str(topic_match.group("modifier") or "").strip())
            if modifier and modifier != str(match.group("head") or "").strip():
                repaired = (
                    normalized[: match.start()]
                    + f"{modifier} 없는 {tail}"
                    + normalized[match.end() :]
                )
                return normalize_title_surface(repaired) or repaired

    return normalized


def _looks_like_focus_name_surface(head: str, params: Optional[Dict[str, Any]]) -> bool:
    normalized_head = normalize_title_surface(head) or str(head or "").strip()
    if not normalized_head:
        return False

    params_dict = params if isinstance(params, dict) else {}
    focus_names = collect_title_focus_names(params_dict, limit=8)
    full_name = _normalize_focus_person_name(params_dict.get("fullName"))
    if full_name:
        focus_names.append(full_name)
    return normalized_head in _dedupe_preserve_order(focus_names)


def _assess_duplicate_focus_possessive_title_surface(
    title: str,
    params: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    normalized_title = normalize_title_surface(title) or str(title or "").strip()
    match = _DUPLICATED_POSSESSIVE_FOCUS_NAME_TITLE_RE.match(normalized_title)
    if not match:
        return {"passed": True, "reason": "", "repairedTitle": "", "issue": ""}

    head = str(match.group("name") or "").strip()
    if not _looks_like_focus_name_surface(head, params):
        return {"passed": True, "reason": "", "repairedTitle": "", "issue": ""}

    return {
        "passed": False,
        "reason": '제목이 "이름, 이름의 ..." 구조로 시작해 의미가 무너집니다. 이름은 한 번만 쓰고 새 문장으로 다시 작성하세요.',
        "repairedTitle": "",
        "issue": "duplicate_focus_name_possessive",
    }


def _assess_focus_name_possessive_modifier_title_surface(
    title: str,
    params: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    normalized_title = normalize_title_surface(title) or str(title or "").strip()
    match = _POSSESSIVE_AWKWARD_MODIFIER_TITLE_RE.search(normalized_title)
    if not match:
        return {"passed": True, "reason": "", "repairedTitle": "", "issue": ""}

    head = str(match.group("head") or "").strip()
    if not _looks_like_focus_name_surface(head, params):
        return {"passed": True, "reason": "", "repairedTitle": "", "issue": ""}

    return {
        "passed": False,
        "reason": '제목이 "[이름]의 되는/하는/있는 ..." 구조로 비문입니다. 본문 구절 조각을 이름 뒤에 붙이지 말고 새 문장으로 다시 작성하세요.',
        "repairedTitle": "",
        "issue": "focus_name_possessive_modifier",
    }


def _repair_bare_day_fragment_title_surface(title: str) -> str:
    normalized = normalize_title_surface(title) or str(title or "").strip()
    if not normalized:
        return normalized

    repaired = _BARE_DAY_FRAGMENT_TITLE_RE.sub(" 이후?", normalized, count=1)
    repaired = re.sub(r"\s{2,}", " ", repaired).strip(" ,")
    repaired = re.sub(r"\s+\?", "?", repaired)
    return repaired


def _repair_adjacent_focus_keyword_surface(
    title: str,
    params: Optional[Dict[str, Any]] = None,
) -> str:
    normalized = normalize_title_surface(title) or str(title or "").strip()
    if not normalized:
        return normalized

    params_dict = params if isinstance(params, dict) else {}
    user_keywords = [
        str(item or "").strip()
        for item in (params_dict.get("userKeywords") if isinstance(params_dict.get("userKeywords"), list) else [])
        if str(item or "").strip()
    ]
    if len(user_keywords) < 2:
        return normalized

    left = user_keywords[0]
    right = user_keywords[1]
    if not left or not right or are_keywords_similar(left, right):
        return normalized

    patterns = (
        (left, right),
        (right, left),
    )
    repaired = normalized
    for first, second in patterns:
        repaired = re.sub(
            rf"(?<![0-9A-Za-z가-힣]){re.escape(first)}\s+{re.escape(second)}(?=\s|$|[,:])",
            f"{first}·{second}",
            repaired,
            count=1,
        )
    return normalize_title_surface(repaired) or repaired


def _assess_matchup_possessive_title_surface(
    title: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    normalized = normalize_title_surface(title) or str(title or "").strip()
    if not normalized:
        return {"passed": True, "reason": "", "repairedTitle": "", "issue": ""}
    if _POSSESSIVE_EMPTY_MODIFIER_TITLE_RE.search(normalized):
        return {"passed": True, "reason": "", "repairedTitle": "", "issue": ""}

    focus_names = collect_title_focus_names(params if isinstance(params, dict) else {}, limit=2)
    unique_focus_names = [name for name in focus_names if len(str(name or "").strip()) >= 2]
    if len(unique_focus_names) < 2:
        return {"passed": True, "reason": "", "repairedTitle": "", "issue": ""}

    name_pattern = "|".join(re.escape(name) for name in unique_focus_names)
    pattern = re.compile(
        rf"^(?P<left>{name_pattern})\s*,\s*(?P<right>{name_pattern})의\s+(?P<tail>[0-9A-Za-z가-힣·\-\s]{{2,40}})$",
        re.IGNORECASE,
    )
    match = pattern.search(normalized)
    if not match:
        return {"passed": True, "reason": "", "repairedTitle": "", "issue": ""}

    left = str(match.group("left") or "").strip()
    right = str(match.group("right") or "").strip()
    tail = normalize_title_surface(str(match.group("tail") or "").strip())
    if not left or not right or not tail or left == right:
        return {"passed": True, "reason": "", "repairedTitle": "", "issue": ""}

    repaired = normalize_title_surface(f"{left}·{right}, {tail}") or f"{left}·{right}, {tail}"
    return {
        "passed": False,
        "reason": "대결 구도 제목에서 인명 뒤 소유격 '의'가 붙어 의미가 모호합니다. 두 인물은 병렬로 두고 핵심 쟁점을 뒤에 붙이세요.",
        "repairedTitle": repaired if repaired != normalized else "",
        "issue": "matchup_possessive_surface",
    }


def _has_bare_day_fragment_title_issue(title: str) -> bool:
    normalized = normalize_title_surface(title) or str(title or "").strip()
    if not normalized:
        return False
    if re.search(r"\d{1,2}\s*월\s*\d{1,2}\s*일", normalized):
        return False
    if re.search(r"\d{4}[./-]\d{1,2}[./-]\d{1,2}", normalized):
        return False

    for match in _BARE_DAY_FRAGMENT_TITLE_RE.finditer(normalized):
        start = int(match.start("day"))
        prefix = normalized[max(0, start - 8):start]
        if re.search(r"(?:월\s*|년\s*|매달\s*|이달\s*|다음\s*|오는\s*|지난\s*)$", prefix):
            continue
        return True
    return False


def assess_malformed_title_surface(title: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    normalized = normalize_title_surface(title) or str(title or "").strip()
    if not normalized:
        return {"passed": True, "reason": "", "repairedTitle": "", "issue": ""}

    duplicate_focus_possessive = _assess_duplicate_focus_possessive_title_surface(normalized, params)
    if not duplicate_focus_possessive.get("passed", True):
        return duplicate_focus_possessive

    awkward_focus_modifier = _assess_focus_name_possessive_modifier_title_surface(normalized, params)
    if not awkward_focus_modifier.get("passed", True):
        return awkward_focus_modifier

    adjacent_keyword_repaired = _repair_adjacent_focus_keyword_surface(normalized, params)
    if adjacent_keyword_repaired and adjacent_keyword_repaired != normalized:
        return {
            "passed": False,
            "reason": "독립 검색어가 공백만으로 이어져 제목 표면이 어색합니다. 두 검색어를 구분해 다시 작성하세요.",
            "repairedTitle": adjacent_keyword_repaired,
            "issue": "adjacent_focus_keywords",
        }

    collapsed = _collapse_consecutive_duplicate_title_tokens(normalized)
    if collapsed and collapsed != normalized:
        return {
            "passed": False,
            "reason": "제목에 같은 단어가 연속 반복돼 의미가 무너집니다.",
            "repairedTitle": collapsed,
            "issue": "consecutive_duplicate_token",
        }

    particle_repaired = _repair_missing_object_particle_title_surface(normalized)
    if particle_repaired and particle_repaired != normalized:
        return {
            "passed": False,
            "reason": '제목의 수식 관계가 어색합니다. "무엇을 위한" 구조를 완결해 다시 작성하세요.',
            "repairedTitle": particle_repaired,
            "issue": "missing_object_particle",
        }

    matchup_possessive = _assess_matchup_possessive_title_surface(normalized, params)
    if not matchup_possessive.get("passed", True):
        return matchup_possessive

    if _POSSESSIVE_EMPTY_MODIFIER_TITLE_RE.search(normalized):
        repaired = _repair_possessive_empty_modifier_title_surface(normalized, params)
        return {
            "passed": False,
            "reason": '제목의 "의 없는" 구문이 비문입니다. 빠진 수식어를 복원해 다시 작성하세요.',
            "repairedTitle": repaired if repaired != normalized else "",
            "issue": "empty_modifier_after_possessive",
        }

    if _has_bare_day_fragment_title_issue(normalized):
        repaired = _repair_bare_day_fragment_title_surface(normalized)
        return {
            "passed": False,
            "reason": "제목의 날짜 조각이 문장 안에 떠 있습니다. 날짜를 완결된 정보로 쓰거나 제거해 다시 작성하세요.",
            "repairedTitle": repaired if repaired != normalized else "",
            "issue": "bare_day_fragment",
        }

    return {"passed": True, "reason": "", "repairedTitle": "", "issue": ""}

def _normalize_title_for_similarity(title: str) -> str:
    normalized = str(title or '').lower().strip()
    normalized = re.sub(r'[\s\W_]+', '', normalized, flags=re.UNICODE)
    return normalized

def _title_similarity(a: str, b: str) -> float:
    norm_a = _normalize_title_for_similarity(a)
    norm_b = _normalize_title_for_similarity(b)
    if not norm_a or not norm_b:
        return 0.0
    return SequenceMatcher(None, norm_a, norm_b).ratio()

def _extract_title_repeat_signature(title: str) -> Dict[str, Any]:
    title_text = str(title or '').strip()
    compact_title = re.sub(r'\s+', '', title_text)
    if not compact_title:
        return {}

    normalized_prefix = title_text
    for separator in (',', ':', ';'):
        if separator in normalized_prefix:
            normalized_prefix = normalized_prefix.split(separator, 1)[0]
            break
    normalized_prefix = normalized_prefix.split('?', 1)[0].split('？', 1)[0]
    prefix = _normalize_title_for_similarity(normalized_prefix)[:18]

    intent = 'none'
    if any(token in compact_title for token in ('출마론', '출마', '거론', '구도', '변수')):
        intent = 'role_intent'

    question = 'none'
    question_groups = (
        ('why', ('왜', '이유')),
        ('how', ('어떻게',)),
        ('what', ('무엇', '뭐가', '무슨')),
        ('whether', ('일까', '인가', '되나')),
    )
    for label, tokens in question_groups:
        if any(token in title_text for token in tokens):
            question = label
            break

    direction = 'none'
    direction_groups = (
        ('wobble', ('흔들리나', '흔들렸나', '밀리나', '주춤', '휘청')),
        ('rise', ('약진', '부상', '급부상')),
        ('lead', ('앞섰나', '앞서', '우세', '리드')),
        ('contest', ('접전', '각축', '초접전')),
        ('viability', ('가능성', '경쟁력')),
    )
    for label, tokens in direction_groups:
        if any(token in title_text for token in tokens):
            direction = label
            break

    contest = 'none'
    if any(token in title_text for token in ('양자대결', '가상대결', '대결', '맞대결', '접전')):
        contest = 'contest'

    percent_count = len(re.findall(r'([0-9]{1,2}(?:\.[0-9])?)\s*%', title_text))
    percent_shape = 'pair' if percent_count >= 2 else ('single' if percent_count == 1 else 'none')

    return {
        'prefix': prefix,
        'intent': intent,
        'question': question,
        'direction': direction,
        'contest': contest,
        'percentShape': percent_shape,
    }

def _compare_title_repeat_signature(title: str, previous_title: str) -> Dict[str, Any]:
    signature = _extract_title_repeat_signature(title)
    previous_signature = _extract_title_repeat_signature(previous_title)
    if not signature or not previous_signature:
        return {'score': 0, 'reasons': []}

    score = 0
    reasons: List[str] = []
    if (
        signature.get('prefix')
        and signature.get('prefix') == previous_signature.get('prefix')
        and len(str(signature.get('prefix') or '')) >= 8
    ):
        score += 3
        reasons.append('same_prefix')
    if signature.get('intent') != 'none' and signature.get('intent') == previous_signature.get('intent'):
        score += 2
        reasons.append('same_intent')
    if signature.get('question') != 'none' and signature.get('question') == previous_signature.get('question'):
        score += 2
        reasons.append('same_question')
    if signature.get('direction') != 'none' and signature.get('direction') == previous_signature.get('direction'):
        score += 2
        reasons.append('same_direction')
    if signature.get('contest') != 'none' and signature.get('contest') == previous_signature.get('contest'):
        score += 1
        reasons.append('same_contest')
    if (
        signature.get('percentShape') != 'none'
        and signature.get('percentShape') == previous_signature.get('percentShape')
    ):
        score += 1
        reasons.append('same_percent_shape')
    return {'score': score, 'reasons': reasons}


def _normalize_focus_person_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    had_whitespace = " " in text
    if " " in text:
        parts = extract_role_keyword_parts(text)
        candidate = str(parts.get("name") or text.split(" ", 1)[0]).strip()
    else:
        candidate = text
    normalized = re.sub(r"[^가-힣]", "", candidate)
    if re.fullmatch(r"[가-힣]{2,4}", normalized):
        return normalized
    if had_whitespace and 2 <= len(normalized) <= 8:
        return normalized
    return ""


def _dedupe_preserve_order(items: List[str], *, limit: int = 0) -> List[str]:
    deduped: List[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
        if limit > 0 and len(deduped) >= limit:
            break
    return deduped


def collect_title_focus_names(params: Optional[Dict[str, Any]], *, limit: int = 6) -> List[str]:
    params_dict = params if isinstance(params, dict) else {}
    bundle = params_dict.get("pollFocusBundle") if isinstance(params_dict.get("pollFocusBundle"), dict) else {}
    primary_pair = bundle.get("primaryPair") if isinstance(bundle.get("primaryPair"), dict) else {}
    priority_items = bundle.get("titleNamePriority") if isinstance(bundle.get("titleNamePriority"), list) else []
    focus_names = bundle.get("focusNames") if isinstance(bundle.get("focusNames"), list) else []
    user_keywords = params_dict.get("userKeywords") if isinstance(params_dict.get("userKeywords"), list) else []

    raw_names: List[str] = []
    raw_names.extend(_normalize_focus_person_name(item) for item in priority_items)
    raw_names.append(_normalize_focus_person_name(primary_pair.get("speaker")))
    raw_names.append(_normalize_focus_person_name(primary_pair.get("opponent")))
    raw_names.append(_normalize_focus_person_name(params_dict.get("fullName")))
    raw_names.extend(_normalize_focus_person_name(item) for item in focus_names)
    raw_names.extend(_normalize_focus_person_name(item) for item in user_keywords)
    return _dedupe_preserve_order(raw_names, limit=limit)


_TITLE_PLAN_CONFIRM_MARKERS = (
    "경선 확정",
    "후보 확정",
    "후보 선정",
    "확정",
)
_TITLE_PLAN_POLICY_MARKERS = (
    "정책",
    "공약",
    "비전",
    "해법",
)
_TITLE_PLAN_ECONOMY_MARKERS = (
    "경제",
    "산업",
    "일자리",
    "민생",
)
_TITLE_PLAN_POLITICS_MARKERS = (
    "정치 지형",
    "정치지형",
    "선거 구도",
    "구도",
    "판세",
)
_TITLE_PLAN_COMPETITION_MARKERS = (
    "대결",
    "승부",
    "경쟁",
    "맞대결",
)
_TITLE_PLAN_ELECTION_MARKERS = (
    "경선",
    "선거",
    "후보",
)
_TITLE_EVENT_EXTRA_MARKERS = (
    "방송토론",
    "토론",
    "행사",
    "안내",
    "초청",
    "간담회",
    "설명회",
)
_TITLE_PLAN_REGION_STOPWORDS = {
    "더불어민주당",
    "국민의힘",
    "민주당",
    "대한민국",
}


def _compact_title_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _contains_compact_marker(text: str, markers: List[str] | tuple[str, ...]) -> bool:
    compact = _compact_title_text(text)
    if not compact:
        return False
    return any(_compact_title_text(marker) in compact for marker in markers if marker)


def _extract_title_region_hint(params: Optional[Dict[str, Any]]) -> str:
    params_dict = params if isinstance(params, dict) else {}
    title_scope = params_dict.get("titleScope") if isinstance(params_dict.get("titleScope"), dict) else {}
    for key in ("regionMetro", "region", "metroRegion"):
        raw_value = str(title_scope.get(key) or "").strip()
        normalized = re.sub(r"[^가-힣A-Za-z0-9]", "", raw_value)
        if 2 <= len(normalized) <= 12 and normalized not in _TITLE_PLAN_REGION_STOPWORDS:
            return normalized

    combined = " ".join(
        str(params_dict.get(key) or "").strip()
        for key in ("topic", "contentPreview", "backgroundText", "stanceText")
        if str(params_dict.get(key) or "").strip()
    )
    patterns = (
        r"([가-힣]{2,8})시장",
        r"([가-힣]{2,8})경제",
        r"([가-힣]{2,8})정치",
        r"([가-힣]{2,8})선거",
    )
    for pattern in patterns:
        match = re.search(pattern, combined)
        if not match:
            continue
        candidate = re.sub(r"[^가-힣A-Za-z0-9]", "", str(match.group(1) or "").strip())
        if 2 <= len(candidate) <= 12 and candidate not in _TITLE_PLAN_REGION_STOPWORDS:
            return candidate
    return ""


def _build_matchup_title_anchors(params: Optional[Dict[str, Any]], focus_names: List[str]) -> List[str]:
    if len(focus_names) < 2:
        return []
    params_dict = params if isinstance(params, dict) else {}
    combined = " ".join(
        str(params_dict.get(key) or "").strip()
        for key in ("topic", "contentPreview", "backgroundText", "stanceText")
        if str(params_dict.get(key) or "").strip()
    )
    pair_label = "·".join(focus_names[:2])
    anchors: List[str] = []
    if _contains_compact_marker(combined, _TITLE_PLAN_CONFIRM_MARKERS):
        anchors.append(f"{pair_label} 경선 확정")
    if (
        _contains_compact_marker(combined, _TITLE_PLAN_POLICY_MARKERS)
        or _contains_compact_marker(combined, _TITLE_PLAN_COMPETITION_MARKERS)
        or _contains_compact_marker(combined, _TITLE_PLAN_ELECTION_MARKERS)
    ):
        anchors.append(f"{pair_label} 경선")
    anchors.append(f"{pair_label} 맞대결")
    return _dedupe_preserve_order([normalize_title_surface(item) for item in anchors if item], limit=4)


def _build_matchup_issue_tails(params: Optional[Dict[str, Any]]) -> List[str]:
    params_dict = params if isinstance(params, dict) else {}
    combined = " ".join(
        str(params_dict.get(key) or "").strip()
        for key in ("topic", "contentPreview", "backgroundText", "stanceText")
        if str(params_dict.get(key) or "").strip()
    )
    region = _extract_title_region_hint(params_dict)
    tails: List[str] = []

    has_policy = _contains_compact_marker(combined, _TITLE_PLAN_POLICY_MARKERS)
    has_economy = _contains_compact_marker(combined, _TITLE_PLAN_ECONOMY_MARKERS)
    has_politics = _contains_compact_marker(combined, _TITLE_PLAN_POLITICS_MARKERS)
    has_competition = _contains_compact_marker(combined, _TITLE_PLAN_COMPETITION_MARKERS)
    has_confirm = _contains_compact_marker(combined, _TITLE_PLAN_CONFIRM_MARKERS)

    if has_policy and has_economy:
        if region:
            tails.append(f"{region} 경제 해법 경쟁")
        tails.append("경제 해법 경쟁")
    if has_policy:
        tails.append("정책 대결의 쟁점")
        tails.append("정책 경쟁의 핵심")
    if has_politics:
        if region:
            tails.append(f"{region} 정치 지형 변화")
        tails.append("정치 지형 변화")
    if has_economy and not has_policy:
        if region:
            tails.append(f"{region} 경제 비전 경쟁")
        tails.append("경제 비전 경쟁")
    if has_confirm:
        if region:
            tails.append(f"{region} 선거 구도의 관전 포인트")
        tails.append("경선 이후의 경쟁 구도")
    if has_competition:
        tails.append("경선의 핵심 쟁점")

    if not tails:
        if region:
            tails.append(f"{region} 선거 구도의 쟁점")
        tails.append("경선의 핵심 쟁점")

    return _dedupe_preserve_order([normalize_title_surface(item) for item in tails if item], limit=6)


def _extract_event_date_hint_from_text(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""

    patterns = (
        (re.compile(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})"), 2, 3),
        (re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일"), 1, 2),
        (re.compile(r"(\d{1,2})\s*/\s*(\d{1,2})"), 1, 2),
        (re.compile(r"(\d{1,2})\s*-\s*(\d{1,2})"), 1, 2),
    )
    for pattern, month_group, day_group in patterns:
        match = pattern.search(normalized)
        if not match:
            continue
        month = str(match.group(month_group) or "").lstrip("0") or "0"
        day = str(match.group(day_group) or "").lstrip("0") or "0"
        return f"{month}월 {day}일"
    return ""


def _extract_structured_event_date_hint(params: Optional[Dict[str, Any]]) -> str:
    params_dict = params if isinstance(params, dict) else {}
    context_analysis = params_dict.get("contextAnalysis") if isinstance(params_dict.get("contextAnalysis"), dict) else {}
    must_preserve = context_analysis.get("mustPreserve") if isinstance(context_analysis.get("mustPreserve"), dict) else {}

    for raw_source in (
        must_preserve.get("eventDate"),
        params_dict.get("topic"),
        params_dict.get("contentPreview"),
        params_dict.get("backgroundText"),
        params_dict.get("stanceText"),
    ):
        hint = _extract_event_date_hint_from_text(str(raw_source or ""))
        if hint:
            return hint
    return ""


def _extract_structured_event_location_hint(params: Optional[Dict[str, Any]]) -> str:
    params_dict = params if isinstance(params, dict) else {}
    context_analysis = params_dict.get("contextAnalysis") if isinstance(params_dict.get("contextAnalysis"), dict) else {}
    must_preserve = context_analysis.get("mustPreserve") if isinstance(context_analysis.get("mustPreserve"), dict) else {}
    explicit = normalize_title_surface(str(must_preserve.get("eventLocation") or "").strip())
    if explicit:
        return explicit

    combined = " ".join(
        str(params_dict.get(key) or "").strip()
        for key in ("topic", "contentPreview", "backgroundText", "stanceText")
        if str(params_dict.get(key) or "").strip()
    )
    broadcast_match = re.search(r"\b([A-Z]{2,6})\b", combined)
    if broadcast_match:
        return str(broadcast_match.group(1) or "").strip()

    korean_place_match = re.search(
        r"([가-힣A-Za-z0-9]{2,16}(?:홀|회관|센터|광장|스튜디오|방송국|극장))",
        combined,
    )
    if korean_place_match:
        return normalize_title_surface(str(korean_place_match.group(1) or "").strip())

    return ""


def _extract_structured_event_label(params: Optional[Dict[str, Any]]) -> str:
    params_dict = params if isinstance(params, dict) else {}
    combined = " ".join(
        str(params_dict.get(key) or "").strip()
        for key in ("topic", "contentPreview", "backgroundText", "stanceText")
        if str(params_dict.get(key) or "").strip()
    )
    compact = _compact_title_text(combined)
    if not compact:
        return ""

    priority_markers = (
        "방송토론",
        "토론회",
        "토론",
        "기자회견",
        "설명회",
        "간담회",
        "세미나",
        "강연",
        "북토크",
        "토크콘서트",
        "팬미팅",
        "출판기념회",
    )
    for marker in priority_markers:
        if _compact_title_text(marker) in compact:
            return marker

    for marker in EVENT_NAME_MARKERS + _TITLE_EVENT_EXTRA_MARKERS:
        if _compact_title_text(marker) in compact:
            return marker

    return ""


def _build_event_title_anchor(params: Optional[Dict[str, Any]]) -> str:
    params_dict = params if isinstance(params, dict) else {}
    focus_names = collect_title_focus_names(params_dict, limit=3)
    unique_names: List[str] = []
    for name in focus_names:
        normalized = normalize_title_surface(name)
        if not normalized:
            continue
        if any(are_keywords_similar(normalized, existing) for existing in unique_names):
            continue
        unique_names.append(normalized)
    if len(unique_names) >= 2:
        return f"{unique_names[0]}·{unique_names[1]} 경선"
    if unique_names:
        return unique_names[0]
    return ""


def _build_structured_event_title_candidates(params: Optional[Dict[str, Any]]) -> List[str]:
    params_dict = params if isinstance(params, dict) else {}
    date_hint = _extract_structured_event_date_hint(params_dict)
    location_hint = _extract_structured_event_location_hint(params_dict)
    event_label = _extract_structured_event_label(params_dict)
    anchor = _build_event_title_anchor(params_dict)
    combined = " ".join(
        str(params_dict.get(key) or "").strip()
        for key in ("topic", "contentPreview", "backgroundText", "stanceText")
        if str(params_dict.get(key) or "").strip()
    )
    has_confirm = _contains_compact_marker(combined, _TITLE_PLAN_CONFIRM_MARKERS)
    if not anchor:
        full_name = normalize_title_surface(str(params_dict.get("fullName") or "").strip())
        anchor = full_name

    if not event_label:
        return []

    event_label_variants = [event_label]
    if "토론" in event_label and "토론" not in event_label_variants:
        event_label_variants.append("토론")
    if event_label == "방송토론":
        event_label_variants.append("토론")
    if "안내" not in event_label:
        event_label_variants.append(f"{event_label} 안내")

    anchor_variants = [anchor] if anchor else []
    if anchor and has_confirm and "경선" in anchor:
        anchor_variants.append(anchor.replace("경선", "경선 확정"))
    elif anchor and has_confirm:
        anchor_variants.append(f"{anchor} 경선 확정")

    info_parts = [part for part in (date_hint, location_hint) if part]
    info_block = " ".join(info_parts).strip()
    candidate_pool: List[str] = []
    for anchor_text in anchor_variants or [""]:
        for label in event_label_variants:
            normalized_label = normalize_title_surface(label)
            if not normalized_label:
                continue
            if anchor_text and info_block:
                candidate_pool.append(f"{anchor_text}, {info_block} {normalized_label}")
                candidate_pool.append(f"{info_block} {normalized_label}, {anchor_text}")
            if anchor_text and date_hint:
                candidate_pool.append(f"{anchor_text}, {date_hint} {normalized_label}")
            if anchor_text and location_hint:
                candidate_pool.append(f"{anchor_text}, {location_hint} {normalized_label}")
            if info_block and normalized_label:
                candidate_pool.append(f"{info_block} {normalized_label}")
            if anchor_text and normalized_label:
                candidate_pool.append(f"{anchor_text}, {normalized_label}")

    normalized_candidates: List[str] = []
    for raw_candidate in candidate_pool:
        candidate = _fit_title_length(normalize_title_surface(raw_candidate) or str(raw_candidate or "").strip())
        if not candidate:
            continue
        candidate_length = len(candidate)
        if TITLE_LENGTH_HARD_MIN <= candidate_length <= TITLE_LENGTH_HARD_MAX:
            normalized_candidates.append(candidate)

    return _dedupe_preserve_order(normalized_candidates, limit=8)


def build_structured_title_candidates(
    params: Optional[Dict[str, Any]],
    *,
    title_purpose: str = "",
    limit: int = 8,
) -> List[str]:
    params_dict = params if isinstance(params, dict) else {}
    if str(title_purpose or "").strip() == "event_announcement":
        return _build_structured_event_title_candidates(params_dict)[:limit]

    focus_names = collect_title_focus_names(params_dict, limit=2)
    bundle = params_dict.get("pollFocusBundle") if isinstance(params_dict.get("pollFocusBundle"), dict) else {}
    allowed_title_lanes = bundle.get("allowedTitleLanes") if isinstance(bundle.get("allowedTitleLanes"), list) else []

    candidate_pool: List[str] = []
    for raw_lane in allowed_title_lanes:
        lane = raw_lane if isinstance(raw_lane, dict) else {}
        template = normalize_title_surface(str(lane.get("template") or "").strip())
        if template:
            candidate_pool.append(template)

    if len(focus_names) >= 2:
        anchors = _build_matchup_title_anchors(params_dict, focus_names)
        tails = _build_matchup_issue_tails(params_dict)
        for anchor in anchors:
            for tail in tails:
                if not anchor or not tail:
                    continue
                if tail in anchor:
                    candidate_pool.append(anchor)
                else:
                    candidate_pool.append(f"{anchor}, {tail}")
    elif focus_names:
        tails = _build_matchup_issue_tails(params_dict)
        for tail in tails:
            candidate_pool.append(f"{focus_names[0]}, {tail}")

    normalized_candidates: List[str] = []
    for raw_candidate in candidate_pool:
        candidate = _fit_title_length(normalize_title_surface(raw_candidate) or str(raw_candidate or "").strip())
        if not candidate:
            continue
        candidate_length = len(candidate)
        if TITLE_LENGTH_HARD_MIN <= candidate_length <= TITLE_LENGTH_HARD_MAX:
            normalized_candidates.append(candidate)

    return _dedupe_preserve_order(normalized_candidates, limit=limit)


def assess_title_focus_name_repetition(title: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    normalized_title = normalize_title_surface(title) or str(title or "").strip()
    if not normalized_title:
        return {"passed": True, "duplicateNames": [], "counts": {}, "reason": ""}

    params_dict = params if isinstance(params, dict) else {}
    bundle = params_dict.get("pollFocusBundle") if isinstance(params_dict.get("pollFocusBundle"), dict) else {}
    repeat_limit = max(1, int(bundle.get("titleNameRepeatLimit") or 1))
    focus_names = collect_title_focus_names(params_dict)
    if not focus_names:
        return {"passed": True, "duplicateNames": [], "counts": {}, "reason": ""}

    counts: Dict[str, int] = {}
    duplicate_names: List[str] = []
    for name in focus_names:
        count = len(re.findall(re.escape(name), normalized_title))
        if count <= 0:
            continue
        counts[name] = count
        if count > repeat_limit:
            duplicate_names.append(name)

    if not duplicate_names:
        return {"passed": True, "duplicateNames": [], "counts": counts, "reason": ""}

    joined = ", ".join(duplicate_names[:2])
    repeat_count = max(int(counts.get(name) or 0) for name in duplicate_names)
    return {
        "passed": False,
        "duplicateNames": duplicate_names,
        "counts": counts,
        "reason": (
            f'제목에 동일 인물명 "{joined}"이 {repeat_count}회 반복됐습니다. '
            f"인물명은 제목에서 최대 {repeat_limit}회만 사용하세요."
        ),
    }


def _strip_repeated_focus_names(title: str, duplicate_names: List[str]) -> str:
    candidate = str(title or "")
    for duplicate_name in duplicate_names:
        seen = False
        pattern = re.compile(rf"(?:\s*[·,:]\s*)?{re.escape(duplicate_name)}")

        def _replace(match: re.Match) -> str:
            nonlocal seen
            matched = match.group(0) or ""
            if not seen:
                seen = True
                return matched.lstrip(" ,·:")
            return ""

        candidate = pattern.sub(_replace, candidate)
    candidate = normalize_title_surface(candidate) or candidate
    candidate = re.sub(r"\s{2,}", " ", candidate).strip(" ,·:")
    return candidate


def repair_title_focus_name_repetition(title: str, params: Optional[Dict[str, Any]]) -> str:
    normalized_title = normalize_title_surface(title) or str(title or "").strip()
    validation = assess_title_focus_name_repetition(normalized_title, params)
    if validation.get("passed", True):
        return normalized_title

    params_dict = params if isinstance(params, dict) else {}
    bundle = params_dict.get("pollFocusBundle") if isinstance(params_dict.get("pollFocusBundle"), dict) else {}
    primary_pair = bundle.get("primaryPair") if isinstance(bundle.get("primaryPair"), dict) else {}
    allowed_title_lanes = bundle.get("allowedTitleLanes") if isinstance(bundle.get("allowedTitleLanes"), list) else []
    primary_fact_template = (
        bundle.get("primaryFactTemplate") if isinstance(bundle.get("primaryFactTemplate"), dict) else {}
    )

    candidate_pool: List[str] = []
    for raw_lane in allowed_title_lanes:
        lane = raw_lane if isinstance(raw_lane, dict) else {}
        lane_template = normalize_title_surface(str(lane.get("template") or "").strip())
        if lane_template:
            candidate_pool.append(lane_template)
    heading = normalize_title_surface(str(primary_fact_template.get("heading") or "").strip())
    if heading:
        candidate_pool.append(heading)

    speaker = str(primary_pair.get("speaker") or "").strip()
    opponent = str(primary_pair.get("opponent") or "").strip()
    speaker_percent = str(primary_pair.get("speakerPercent") or primary_pair.get("speakerScore") or "").strip()
    opponent_percent = str(primary_pair.get("opponentPercent") or primary_pair.get("opponentScore") or "").strip()
    if speaker and opponent and speaker_percent and opponent_percent:
        candidate_pool.append(f"{speaker}·{opponent} 가상대결 {speaker_percent} 대 {opponent_percent}")

    stripped = _strip_repeated_focus_names(
        normalized_title,
        [str(item).strip() for item in validation.get("duplicateNames") or [] if str(item).strip()],
    )
    if stripped:
        candidate_pool.append(stripped)

    topic = normalize_title_surface(str(params_dict.get("topic") or "").strip())
    primary_keyword = collect_title_focus_names(params_dict, limit=1)
    if topic:
        topic_candidate = topic
        for focus_name in collect_title_focus_names(params_dict):
            if focus_name and topic_candidate.count(focus_name) > 1:
                topic_candidate = _strip_repeated_focus_names(topic_candidate, [focus_name])
        if primary_keyword:
            topic_candidate = re.sub(re.escape(primary_keyword[0]), "", topic_candidate, count=1).strip(" ,·:")
            topic_candidate = normalize_title_surface(
                f"{primary_keyword[0]}, {topic_candidate}" if topic_candidate else primary_keyword[0]
            )
        candidate_pool.append(topic_candidate)
    elif primary_keyword:
        candidate_pool.append(primary_keyword[0])

    if primary_keyword:
        stripped_title = _strip_repeated_focus_names(
            normalized_title,
            [str(item).strip() for item in validation.get("duplicateNames") or [] if str(item).strip()],
        )
        stripped_title = re.sub(r"\s+", " ", stripped_title).strip(" ,·:")
        if stripped_title and stripped_title != primary_keyword[0]:
            candidate_pool.append(f"{primary_keyword[0]}, {stripped_title}")

    for raw_candidate in candidate_pool:
        candidate = _fit_title_length(normalize_title_surface(raw_candidate) or str(raw_candidate or "").strip())
        if not candidate:
            continue
        candidate_validation = assess_title_focus_name_repetition(candidate, params_dict)
        candidate_length = len(candidate)
        if candidate_validation.get("passed") and TITLE_LENGTH_HARD_MIN <= candidate_length <= TITLE_LENGTH_HARD_MAX:
            return candidate

    return ""
