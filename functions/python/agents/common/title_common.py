"""?? ?? ?? ??? ?? ??."""

import logging
from difflib import SequenceMatcher
import re
from typing import Any, Dict, List, Optional

from .election_rules import get_election_stage
from .editorial import TITLE_SPEC
from .role_keyword_policy import should_block_role_keyword

logger = logging.getLogger(__name__)

TITLE_LENGTH_HARD_MIN = TITLE_SPEC['hardMin']
TITLE_LENGTH_HARD_MAX = TITLE_SPEC['hardMax']
TITLE_LENGTH_OPTIMAL_MIN = TITLE_SPEC['optimalMin']
TITLE_LENGTH_OPTIMAL_MAX = TITLE_SPEC['optimalMax']

EVENT_NAME_MARKERS = (
    '출판기념회',
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
        has_question = re.search(r'\?|어떻게|무엇|왜|얼마|언제', text)
        has_legal_terms = re.search(r'법안|조례|법률|제도|개정|발의|통과', text)
        has_time_terms = re.search(r'2025년|상반기|하반기|분기|월간|연간|보고서|리포트', text)
        has_local_terms = re.search(r'[가-힣]+(동|구|군|시|읍|면|리)(?:[가-힣]|\s|,|$)', content_preview)
        has_issue_terms = re.search(r'개혁|분권|양극화|격차|투명성|문제점|대안', text)
        has_commentary_terms = re.search(r'칭찬|질타|비판|논평|평가|소신|침묵|역부족|낙제|심판', text)
        has_politician_names = re.search(r'박형준|조경태|윤석열|이재명|한동훈', content_preview)
        
        # Priority for user content signals
        if has_time_terms and ('보고' in text or '리포트' in text or '현황' in text):
            return 'TIME_BASED'
        if has_legal_terms:
            return 'EXPERT_KNOWLEDGE'
        if has_commentary_terms and has_politician_names:
            return 'COMMENTARY'
        if has_comparison and has_numbers:
            return 'COMPARISON'
        if has_question:
            return 'QUESTION_ANSWER'
        if has_numbers and not has_issue_terms:
            return 'DATA_BASED'
        if has_issue_terms and not has_local_terms:
            return 'ISSUE_ANALYSIS'
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
