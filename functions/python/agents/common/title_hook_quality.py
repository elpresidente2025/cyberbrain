"""제목 후킹 품질 rubric — 생성 프롬프트와 scorer 가 공유하는 단일 진실.

이 모듈이 존재하는 이유:
  - few-shot good 예시는 공통적으로 (1) 정보 격차, (2) 구체 슬롯, (3) 변화/대비
    서사, (4) 본문 고유 명사 인용 을 2~3개 묶어 쓴다.
  - 과거 scorer 의 impact 블록은 단순 정규식 3~4개만 보고 "질문/미완결" 여부만
    체크해서, 평탄한 선언형 제목이 구체 슬롯이 하나도 없어도 그냥 통과했다.
  - 생성기가 few-shot 을 장식으로만 참조해 "통과선에 정확히 걸치는 평탄한 제목"
    만 뽑아내는 국소 최적화가 굳어졌다.

해결 전략:
  - 후킹 품질을 4 차원 rubric 으로 쪼갠다 — info_gap / concrete_slot /
    narrative_arc / specificity. 각 차원은 독립 가산.
  - `extract_slot_opportunities(topic, content, params)` 는 본문·토픽에서
    현재 이 글이 "사용 가능"한 구체 재료(수치·지역·기관·연도·정책명 후보)를
    뽑아 준다. 이걸 generator 에게 직접 보여주고, scorer 는 제목이 이 재료
    중 최소 하나라도 활용했는지 검증한다.
  - generator 와 scorer 는 반드시 동일한 함수를 호출한다. 그러면 "프롬프트는
    A 를 요구하는데 채점은 B 를 기준으로 감점" 하는 자기모순을 원천 차단한다.

CLAUDE.md 범용성 원칙 준수:
  - 지역명 리스트·인물명·정당명·정책명은 코드에 하드코드하지 않는다.
  - 모든 슬롯 추출은 패턴 기반(예: "~구/~군/~시/~도" 접미, "~주년", "~제/~법")
    이거나 params 에서 내려오는 사용자 프로필 필드(regionMetro, regionDistrict,
    affiliation 등) 만 읽는다.
"""

from __future__ import annotations

import re
from typing import Any, Dict, FrozenSet, List, Optional, Pattern, Tuple


# ---------------------------------------------------------------------------
# INFO GAP — 독자가 "그래서?" "왜?" 를 떠올리게 하는 표면 단서
# ---------------------------------------------------------------------------

INFO_GAP_PATTERNS: List[Pattern[str]] = [
    re.compile(r'\?\s*$'),                                   # 물음표 종결
    re.compile(r'(나|까|는가|을까|ㄹ까|할까|될까)\s*$'),     # 미완결 종결 어미
    re.compile(r'(?:^|[\s,])왜\s'),                           # 왜 질문
    re.compile(r'(?:^|[\s,])어떻게\s'),                       # 어떻게 질문
    re.compile(r'(?:^|[\s,])(?:무엇이|무엇을|얼마(?:나|까지)|'
               r'어디서?|언제|어느)'),                        # 기타 의문사
    re.compile(r'(이유|비결|비책|속내|답은|선택은|판단은|한\s*수|'
               r'이정표|전환점)\s*$'),                        # 미완결 명사 마무리
    re.compile(r'(그\s*이유|그\s*속내|그\s*답|그\s*선택)'),  # 지시어 미완결
    # "N가지 [X]" 는 독자가 "그 N개가 뭔지" 궁금해하는 info_gap 장치.
    # 단, 모호한 X("것/점/사항") 는 제외 — 구체 명사(조건/과제/이유/방법/
    # 쟁점/원칙/단계/기준/지표) 와 함께 있어야 함.
    re.compile(r'\d+\s*가지\s*(?:조건|과제|방법|이유|쟁점|원칙|축|단계|기준|지표)'),
]


# ---------------------------------------------------------------------------
# NARRATIVE ARC — 변화/대비/구도 서사 단서
# ---------------------------------------------------------------------------

NARRATIVE_ARC_PATTERNS: List[Pattern[str]] = [
    re.compile(r'→'),
    re.compile(r'(?:^|\s)vs(?:\s|$)', re.IGNORECASE),
    re.compile(r'에서\s*[^\s]+\s*까지'),
    re.compile(r'(이전|과거|작년|지난\s*해|종전).*(현재|지금|올해|이번)'),
    re.compile(r'(\d+(?:년|월|일|주년|분기|개월))\s*만에'),   # "12개월 만에"
    re.compile(r'(\d+(?:억|만원|%|명|건|가구|곳))\s*(증가|감소|개선|확대|절감|확보|달성)'),
]


# ---------------------------------------------------------------------------
# CONCRETE SLOT — 제목에 들어가면 즉시 구체성이 살아나는 고정 사실 슬롯
# ---------------------------------------------------------------------------

# 지역명 접미사 (행정구역 단위) — 한국 지명 패턴 기반, 특정 지역 하드코드 없음
_REGION_SUFFIX_PATTERNS: List[Pattern[str]] = [
    # 광역 단위
    re.compile(r'[가-힣]{1,4}(?:특별시|광역시|특별자치시|특별자치도)'),
    re.compile(r'[가-힣]{1,3}(?:도|시)(?=[\s,.에의은는이가을를]|$)'),
    # 기초 단위
    re.compile(r'[가-힣]{1,4}(?:구|군|시)(?=[\s,.에의은는이가을를]|$)'),
    # 하위 단위
    re.compile(r'[가-힣]{1,4}(?:동|읍|면|리)(?=[\s,.에의은는이가을를]|$)'),
]

# 접미사는 맞지만 지역이 아닌 일반 명사 블랙리스트 — 단순 표면 매칭 오탐 방지
# (CLAUDE.md: 범용 한국어 어휘만, 특정 지명 하드코드 없음)
_REGION_FALSE_POSITIVES: FrozenSet[str] = frozenset({
    # ~리 일반 명사
    '처리', '관리', '정리', '수리', '거리', '자리', '머리', '우리',
    '소리', '다리', '도리', '진리', '원리', '논리', '윤리', '부리',
    '종리', '분리', '무리', '뿌리', '다리', '사리',
    # ~도 일반 명사
    '정도', '제도', '강도', '각도', '태도', '속도', '기도', '인도',
    '용도', '위도', '경도', '보도', '지도', '고도',
    # ~시 일반 명사 (실제 시 이름은 보통 2글자 이상)
    '수시', '당시', '즉시', '동시', '이시', '일시', '시시',
    # ~동 일반 명사
    '행동', '감동', '운동', '활동', '노동', '충동', '이동',
    '독립운동', '민주운동', '사회운동', '시민운동', '학생운동',
    '노동운동', '농민운동', '여성운동', '환경운동',
    # ~구 일반 명사
    '연구', '도구', '요구', '가구', '기구', '용구',
    # ~군 일반 명사
    '아군', '적군', '장군', '해군', '육군', '공군',
    # ~면 일반 명사
    '측면', '표면', '국면', '일면', '정면', '이면',
})

# 기관 접미사 오탐 블랙리스트 — "~정부", "~부" 로 끝나는 일반명사
_INSTITUTION_FALSE_POSITIVES: FrozenSet[str] = frozenset({
    '정부', '임시정부', '대한민국임시정부',
    '외부', '내부', '일부', '전부', '대부', '상부', '하부',
    '서부', '동부', '남부', '북부', '각부', '본부',
    '일원', '지원', '공원', '병원', '학원', '정원',
    '과정', '과목', '팀원', '구성원',
})

# 수치 + 단위 (제목에 실제로 들어갔을 때 효과가 있는 단위들)
_NUMERIC_UNIT_PATTERN = re.compile(
    r'(\d+(?:\.\d+)?)\s*'
    r'(억원|억|만원|만|천만원|조|%|퍼센트|명|건|가구|곳|대|개|호|주년|년|월|일|'
    r'기|차|세|회|번|위|석|권|종|세대|시|분|초|km|킬로|배|시간|가지|단계|개월)'
)

# 기관·법인 접미 (위원회/회의체/부서/법안 등)
# 주의: '과', '팀' 은 조사·일반어와 혼동이 심해 의도적으로 제외.
# '원' 도 공원/병원/일원 등 일반 명사가 많아 FALSE_POSITIVES 로 걸러낸다.
_INSTITUTION_SUFFIX_PATTERNS: List[Pattern[str]] = [
    re.compile(r'[가-힣A-Za-z0-9]{2,}(?:위원회|협의회|의회|추진단|자문단|연구원|공단|기금|재단)'),
    re.compile(r'[가-힣A-Za-z0-9]{2,}(?:청|국|부|처|센터|본부)(?=[\s,.은는이가을를에의]|$)'),
]

# 정책·법안·제도 접미
_POLICY_SUFFIX_PATTERNS: List[Pattern[str]] = [
    re.compile(r'[가-힣A-Za-z0-9]{2,}(?:법|법안|조례|특별법|기본법|개정안|시행령|시행규칙)'),
    re.compile(r'[가-힣A-Za-z0-9]{2,}(?:제도|제|정책|사업|프로젝트|이니셔티브|기획|공약)'),
]

# 연도·기념일
_YEAR_PATTERNS: List[Pattern[str]] = [
    re.compile(r'(19|20)\d{2}\s*년'),
    re.compile(r'\d+\s*주년'),
    re.compile(r'\d+\s*(?:분기|반기)'),
]


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        key = str(item or '').strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _extract_by_patterns(
    text: str,
    patterns: List[Pattern[str]],
    *,
    blacklist: Optional[FrozenSet[str]] = None,
) -> List[str]:
    if not text:
        return []
    found: List[str] = []
    for pat in patterns:
        for m in pat.finditer(text):
            token = m.group(0).strip()
            if not token:
                continue
            if blacklist and token in blacklist:
                continue
            found.append(token)
    return _dedupe_preserve_order(found)


def extract_slot_opportunities(
    topic: Optional[str],
    content: Optional[str],
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, List[str]]:
    """본문·토픽·프로필에서 "제목에 넣을 수 있는 구체 슬롯 재료" 를 뽑는다.

    generator 프롬프트는 이 결과를 그대로 LLM 에게 보여 주고, scorer 는
    제목이 이 중 하나라도 실제로 인용했는지 검증한다. 두 경로가 같은 함수를
    쓰기 때문에 "프롬프트엔 없는 재료를 채점표가 요구" 하는 일이 없다.

    반환 예 (형태만 참고 — 실제 값은 본문에서 추출)::

        {
          'region': ['[지역명]'],
          'numeric': ['[N]주년', '[N]명', '[N]억'],
          'institution': ['[기관명]'],
          'year': ['[YYYY]년', '[N]주년'],
          'policy': ['[정책명]', '[법안명]'],
        }

    빈 카테고리는 빈 리스트로 유지한다(호출부 안정성).
    """
    topic_text = str(topic or '')
    content_text = str(content or '')
    combined = f'{topic_text}\n{content_text}'
    params_dict = params if isinstance(params, dict) else {}

    # 지역 — params 의 사용자 프로필에서 우선 읽고, 없으면 본문 패턴 추출
    region_hints: List[str] = []
    for key in ('regionDistrict', 'regionTown', 'regionMetro', 'region'):
        val = str(params_dict.get(key) or '').strip()
        if val:
            region_hints.append(val)
    region_surface = _extract_by_patterns(
        combined, _REGION_SUFFIX_PATTERNS, blacklist=_REGION_FALSE_POSITIVES
    )
    # 본문 패턴이 프로필과 겹치면 중복 제거
    region_all = _dedupe_preserve_order(region_hints + region_surface)

    # 수치 + 단위 — 매칭된 원문 텍스트를 그대로 보존
    numeric_tokens: List[str] = []
    for m in _NUMERIC_UNIT_PATTERN.finditer(combined):
        numeric_tokens.append(m.group(0).replace(' ', ''))
    numeric_all = _dedupe_preserve_order(numeric_tokens)

    institutions = _extract_by_patterns(
        combined, _INSTITUTION_SUFFIX_PATTERNS, blacklist=_INSTITUTION_FALSE_POSITIVES
    )
    policies = _extract_by_patterns(combined, _POLICY_SUFFIX_PATTERNS)
    years = _extract_by_patterns(combined, _YEAR_PATTERNS)

    return {
        'region': region_all[:4],
        'numeric': numeric_all[:6],
        'institution': institutions[:3],
        'policy': policies[:3],
        'year': years[:3],
    }


def _slot_token_used_in_title(title: str, token: str) -> bool:
    if not title or not token:
        return False
    # 전체 매칭이 우선, 그 다음 핵심 어근(접미 1~2자 제거) 매칭 허용
    if token in title:
        return True
    # "주민참여예산시민위원회" → "주민참여예산" 같은 핵심 어근만 써도 인정
    stems: List[str] = []
    for suffix in ('위원회', '협의회', '의회', '재단', '공단', '기금',
                   '법안', '특별법', '기본법', '개정안', '조례',
                   '제도', '정책', '사업', '프로젝트', '공약',
                   '특별시', '광역시', '특별자치시', '특별자치도'):
        if token.endswith(suffix) and len(token) - len(suffix) >= 2:
            stems.append(token[: -len(suffix)])
    for stem in stems:
        if stem and stem in title:
            return True
    return False


def count_slots_used_in_title(title: str, opportunities: Dict[str, List[str]]) -> Dict[str, Any]:
    """제목이 slot_opportunities 중 몇 개를 인용했는지 센다."""
    if not title or not opportunities:
        return {'used': 0, 'matched': {}, 'total': 0}

    matched: Dict[str, List[str]] = {}
    total = 0
    used = 0
    for category, tokens in opportunities.items():
        token_list = [t for t in (tokens or []) if isinstance(t, str) and t.strip()]
        total += len(token_list)
        hit = [t for t in token_list if _slot_token_used_in_title(title, t)]
        if hit:
            matched[category] = hit
            used += 1   # 카테고리 단위 카운트 (한 카테고리에서 여러 토큰은 1로)
    return {'used': used, 'matched': matched, 'total': total}


# ---------------------------------------------------------------------------
# ANSWER ANCHOR — AEO 관점에서 "답변 엔진이 매칭할 수 있는" 앵커 단서
# ---------------------------------------------------------------------------
#
# concrete_slot 은 "본문 재료를 인용했나" 만 본다. 그런데 재료만 인용하고
# 쿼리 형태가 수사적 반문(`완성할까?`) 으로 끝나면 답변 엔진이 이 제목을
# 실사용자 쿼리에 매칭할 수 없다. answer_anchor 는 "쿼리 형태 자체의
# 구체성" 을 본다:
#   - 수치 + 단위 (25% 감면, 3가지 조건, 60만 개 일자리)
#   - 답변 예고 리스트 (N가지 조건/방법/이유/과제/쟁점)
#   - 구체 선택지 제시 ("A·B 중 어디로", "A vs B")
#   - 정책 행동 동사 (감면·개정·발의·공백 해소·직결·유치)
#
# 신호 1개당 +1, 최대 3. narrative_arc 는 2 로 축소해 총점 15 를 유지.

ANSWER_ANCHOR_PATTERNS: List[Pattern[str]] = [
    # N가지 답변 예고 리스트 — "3가지 조건", "5가지 과제", "4가지 쟁점"
    re.compile(r'\d+\s*가지\s*(?:조건|과제|방법|이유|쟁점|원칙|축|단계|기준|지표)'),
    # 수치 + 정책 행동 — "25% 감면", "274명 창출", "60만 개 일자리"
    re.compile(
        r'\d+(?:,\d{3})*\s*(?:%|퍼센트|억|만원|원|명|건|가구|곳|개|회|배|위|종)\s*'
        r'(?:감면|창출|확보|유치|절감|달성|개정|발의|시행|배정|지원|투입|증액)'
    ),
    # 구체 선택지 제시 — "A·B 중 어디로", "A·B 중 무엇이" (A·B 는 다어절 허용)
    re.compile(
        r'[가-힣A-Za-z0-9]{2,}(?:\s+[가-힣A-Za-z0-9]+){0,3}\s*[·•]\s*'
        r'[가-힣A-Za-z0-9]{2,}(?:\s+[가-힣A-Za-z0-9]+){0,3}\s*중\s*'
        r'(?:어디로?|어느|무엇이|누가|언제)'
    ),
    # 비교 앵커 — "[기준] 수준 [행동]", "A vs B"
    re.compile(r'[가-힣A-Za-z0-9]{2,}\s*(?:수준|대비|수준으로)\s*'
               r'(?:도약|진입|추격|견인|근접|추월)'),
    # 정책 행동 동사 단독 (수치 없이도 구체성 강함)
    re.compile(r'(취득세\s*감면|조례\s*개정안\s*(?:발의|통과|시행)|'
               r'광역교통망\s*확정|공백\s*해소|앵커기업\s*유치|'
               r'직결\s*노선|역세권\s*지정|도첨산단\s*지정)'),
    # "N개 중 유일" / "N중 최초" — 답변 엔진이 매우 선호하는 랭킹 쿼리
    re.compile(r'\d+\s*(?:개|곳|시도|시·도|개\s*시도)\s*(?:중\s*)?(?:유일|최초|최다|최대|최소)'),
]


# ---------------------------------------------------------------------------
# HOOK QUALITY ASSESSMENT — 차원별 독립 가산
# ---------------------------------------------------------------------------

HOOK_DIMENSION_MAX: Dict[str, int] = {
    'info_gap': 4,        # 질문/미완결 서사 1개라도 있으면 +4
    'concrete_slot': 6,   # 본문 고유 재료를 n개 인용 → n * 2 (최대 6)
    'narrative_arc': 2,   # 변화/대비 구조 (축소: 3 → 2)
    'specificity': 1,     # 제목 길이 대비 고유명사 비중 (축소: 2 → 1)
    'answer_anchor': 2,   # AEO 앵커 (신규)
}
HOOK_TOTAL_MAX: int = sum(HOOK_DIMENSION_MAX.values())  # 15


def _count_info_gap_signals(title: str) -> Tuple[int, List[str]]:
    if not title:
        return 0, []
    hits: List[str] = []
    for pat in INFO_GAP_PATTERNS:
        if pat.search(title):
            hits.append(pat.pattern)
    return len(hits), hits


def _count_narrative_arc_signals(title: str) -> Tuple[int, List[str]]:
    if not title:
        return 0, []
    hits: List[str] = []
    for pat in NARRATIVE_ARC_PATTERNS:
        if pat.search(title):
            hits.append(pat.pattern)
    return len(hits), hits


def _count_answer_anchor_signals(title: str) -> Tuple[int, List[str]]:
    """AEO 답변 앵커 신호 개수를 반환.

    answer_anchor 차원은 (수치+단위+행동, N가지 리스트, 선택지, 비교,
    정책 행동 동사, 랭킹 쿼리) 중 독립적으로 걸리는 신호를 센다.
    """
    if not title:
        return 0, []
    hits: List[str] = []
    for pat in ANSWER_ANCHOR_PATTERNS:
        if pat.search(title):
            hits.append(pat.pattern)
    return len(hits), hits


def _estimate_specificity(title: str) -> Tuple[int, Dict[str, Any]]:
    """제목 내 "고유 명사" 밀도 간이 추정.

    - 숫자+단위 토큰 1개 이상 → +1
    - 따옴표/괄호로 감싼 고유어 → +1
    - 둘 다 있으면 최대 2.
    CLAUDE.md 준수: 특정 지명·인명 하드코드 없음, 순수 표면 패턴.
    """
    if not title:
        return 0, {}
    score = 0
    hits: List[str] = []
    if _NUMERIC_UNIT_PATTERN.search(title):
        score += 1
        hits.append('numeric_unit')
    if re.search(r'[\'""‘’“”][^\'""‘’“”]{2,}[\'""‘’“”]', title):
        score += 1
        hits.append('quoted')
    return min(score, HOOK_DIMENSION_MAX['specificity']), {'signals': hits}


def assess_title_hook_quality(
    title: str,
    topic: Optional[str] = None,
    content: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    *,
    opportunities: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """제목이 few-shot 수준의 후킹을 갖추고 있는지 평가한다.

    반환:
        {
          'score': int,            # 0~HOOK_TOTAL_MAX
          'max': HOOK_TOTAL_MAX,
          'dimensions': {
            'info_gap': {'score': int, 'max': int, 'signals': [...]},
            'concrete_slot': {'score': int, 'max': int, 'matched': {...}},
            'narrative_arc': {'score': int, 'max': int, 'signals': [...]},
            'specificity': {'score': int, 'max': int, 'signals': [...]},
          },
          'features': [str, ...],        # 사람이 읽는 태그 리스트
          'missed_opportunities': [str, ...],  # 쓸 수 있었는데 안 쓴 슬롯
          'status': 'strong' | 'ok' | 'flat',
        }
    """
    clean_title = str(title or '').strip()
    features: List[str] = []

    # AEO hollow 는 info_gap 을 무효화한다 — "완성할까?" 같은 수사적 반문은
    # 표면만 물음표일 뿐 실제 정보 격차가 없다. 제목이 family-독립적으로
    # aeo_hollow 로 걸리면 info_gap 점수를 0 으로 밀어서 "수사적 반문으로
    # 4점 챙기는" 경로를 막는다.
    try:
        from .title_family_rules import assess_universal_aeo_hollow
        aeo_hollow_check = assess_universal_aeo_hollow(clean_title)
    except Exception:
        aeo_hollow_check = {'hollow': False}
    is_aeo_hollow = bool(aeo_hollow_check.get('hollow'))

    # info_gap
    gap_count, gap_signals = _count_info_gap_signals(clean_title)
    info_gap_score = HOOK_DIMENSION_MAX['info_gap'] if gap_count >= 1 else 0
    if is_aeo_hollow and info_gap_score:
        info_gap_score = 0
        features.append('AEO공허(질문무효)')
    elif info_gap_score:
        features.append('정보격차')

    # concrete_slot
    if opportunities is None:
        opportunities = extract_slot_opportunities(topic, content, params)
    slot_usage = count_slots_used_in_title(clean_title, opportunities)
    slot_used_categories = int(slot_usage.get('used', 0) or 0)
    concrete_slot_score = min(slot_used_categories * 2, HOOK_DIMENSION_MAX['concrete_slot'])
    if slot_used_categories:
        features.append(f'구체슬롯×{slot_used_categories}')

    # narrative_arc
    arc_count, arc_signals = _count_narrative_arc_signals(clean_title)
    narrative_arc_score = HOOK_DIMENSION_MAX['narrative_arc'] if arc_count >= 1 else 0
    if narrative_arc_score:
        features.append('서사아크')

    # specificity
    specificity_score, specificity_meta = _estimate_specificity(clean_title)
    if specificity_score:
        features.append('고유밀도')

    # answer_anchor — AEO 관점의 "답변 엔진이 매칭할 수 있는" 앵커
    anchor_count, anchor_signals = _count_answer_anchor_signals(clean_title)
    answer_anchor_score = min(anchor_count, HOOK_DIMENSION_MAX['answer_anchor'])
    if answer_anchor_score:
        features.append(f'답변앵커×{min(anchor_count, HOOK_DIMENSION_MAX["answer_anchor"])}')

    total = (
        info_gap_score
        + concrete_slot_score
        + narrative_arc_score
        + specificity_score
        + answer_anchor_score
    )

    # 누락된 slot 재료 — 제목이 "쓸 수 있었는데 안 쓴" 카테고리만 뽑는다
    missed: List[str] = []
    matched_categories = set((slot_usage.get('matched') or {}).keys())
    for category, tokens in (opportunities or {}).items():
        token_list = [t for t in (tokens or []) if isinstance(t, str) and t.strip()]
        if token_list and category not in matched_categories:
            sample = ', '.join(token_list[:2])
            missed.append(f'{category}({sample})')

    # body_reuse pressure — 본문에 수치/정책 재료가 풍부한데 제목이 하나도
    # 재사용하지 않으면 "flat" 으로 강등. concrete_slot 이 이미 카테고리
    # 단위로만 보상하기 때문에, 본문이 아무리 풍부해도 한 토큰만 살짝 건드리고
    # 끝나는 타이틀이 '턱걸이 ok' 로 올라오는 걸 방지한다.
    total_tokens_available = int(slot_usage.get('total', 0) or 0)
    body_reuse_penalty = 0
    has_answer_anchor = answer_anchor_score >= 1
    # 강한 AEO 조합(정보격차 만점 + 답변앵커)은 penalty 면제.
    # 이 경우 제목이 본문 고유명사 대신 질의 프레임으로 AEO 가치를 제공한다.
    strong_aeo_composition = info_gap_score >= 4 and has_answer_anchor
    if strong_aeo_composition:
        pass
    elif total_tokens_available >= 5 and slot_used_categories == 0:
        body_reuse_penalty = 1 if has_answer_anchor else 3
        features.append('본문재활용부족' if has_answer_anchor else '본문재활용없음')
    elif total_tokens_available >= 8 and slot_used_categories <= 1:
        body_reuse_penalty = 1 if has_answer_anchor else 2
        features.append('본문재활용희박')
    total = max(0, total - body_reuse_penalty)

    if total >= 9:
        status = 'strong'
    elif total >= 5:
        status = 'ok'
    else:
        status = 'flat'

    return {
        'score': total,
        'max': HOOK_TOTAL_MAX,
        'dimensions': {
            'info_gap': {
                'score': info_gap_score,
                'max': HOOK_DIMENSION_MAX['info_gap'],
                'signals': gap_signals,
            },
            'concrete_slot': {
                'score': concrete_slot_score,
                'max': HOOK_DIMENSION_MAX['concrete_slot'],
                'used_categories': slot_used_categories,
                'matched': slot_usage.get('matched') or {},
                'total_available': int(slot_usage.get('total', 0) or 0),
            },
            'narrative_arc': {
                'score': narrative_arc_score,
                'max': HOOK_DIMENSION_MAX['narrative_arc'],
                'signals': arc_signals,
            },
            'specificity': {
                'score': specificity_score,
                'max': HOOK_DIMENSION_MAX['specificity'],
                'signals': list(specificity_meta.get('signals') or []),
            },
            'answer_anchor': {
                'score': answer_anchor_score,
                'max': HOOK_DIMENSION_MAX['answer_anchor'],
                'signals': anchor_signals,
            },
        },
        'body_reuse_penalty': body_reuse_penalty,
        'features': features,
        'missed_opportunities': missed,
        'opportunities': opportunities or {},
        'status': status,
    }


# ---------------------------------------------------------------------------
# SLOT PREFERENCE — "이 글에서 가장 구체적인 재료 1개" 를 카테고리별로 선정
# ---------------------------------------------------------------------------
#
# extract_slot_opportunities 는 "쓸 수 있는" 재료를 모두 모은다. 그런데 LLM 은
# 때때로 더 넓은 범위 토큰(예: 광역시 이름)으로 도피해서 제목이 평탄해진다.
# compute_slot_preferences 는 각 카테고리에서 "우선 인용할 토큰 1개" 를
# 선정해 generator 에게 별도로 마킹해 준다.
#
# 현재는 region 카테고리만 구현한다. 다른 카테고리(numeric/institution/
# policy/year) 는 preferred 없이 유지하며, 관찰된 열화가 있을 때 확장한다.
#
# 설계 원칙:
#   - policy-aware: 광역 후보(titleScope.avoidLocalInTitle=true) 에게는
#     광역명이 preferred, 기초 후보에게는 구/군 명이 preferred. 좁을수록
#     구체적이라는 단순 휴리스틱은 광역 후보에게 역효과다.
#   - content-aware: 본문 언급 빈도 가중치를 합산한다. 본문이 실제로 강조
#     하는 스코프가 우선. granularity 는 tie-breaker 역할.
#   - 범용: 지역명·정당명·인물명 하드코드 없음. 순수 패턴 + params 필드.


def _region_granularity_rank(token: str) -> int:
    """좁은 행정단위일수록 높은 점수. 1(광역) ~ 4(하위단위).

    알 수 없는/접미사 없는 토큰은 광역 추정(1).
    """
    if not token:
        return 1
    if re.search(r'(?:동|읍|면|리)$', token):
        return 4
    if re.search(r'(?:구|군)$', token):
        return 3
    if re.search(r'(?:특별시|광역시|특별자치시|특별자치도)$', token):
        return 1
    if re.search(r'(?:도|시)$', token):
        return 2
    return 1


def _compute_region_preference(
    region_tokens: List[str],
    content: str,
    avoid_local: bool,
) -> Optional[str]:
    """지역 후보 중 "이 글·이 화자에게 가장 구체적" 인 토큰 1개를 고른다.

    - avoid_local=True (광역 후보): 이는 정책상 "구/군/동/읍/면/리 금지" 를
      의미한다. 따라서 granularity 1~2(광역·시/도) 토큰만 필터링 후보에
      남기고, 그 안에서 본문 빈도가 가장 높은 것을 preferred 로 삼는다.
      가중치 방식은 본문이 기초 단위를 많이 언급할 경우(광역 후보여도
      사례로 구/군명을 여러 번 인용) 정책을 덮어쓸 수 있어 위험하다.
    - avoid_local=False (기초 후보): 본문 빈도 × 2 + granularity × 1 가중합.
      본문이 실제로 강조하는 스코프를 우선하되, 동점이면 좁은 단위 우선.
    동점은 본문 등장 순서(extract 결과 순)로 tie-break.
    """
    if not region_tokens:
        return None
    content_text = content or ''

    if avoid_local:
        metro_candidates = [
            t for t in region_tokens if _region_granularity_rank(t) <= 2
        ]
        if not metro_candidates:
            return None

        def metro_score(token: str) -> Tuple[int, int, int]:
            freq = content_text.count(token) if token else 0
            # granularity 가 1(광역시/도) 인 쪽 우선, 그다음 빈도, 그다음 등장 순서
            gran_priority = 2 - _region_granularity_rank(token)  # 1→1, 2→0
            return (gran_priority, freq, -region_tokens.index(token))

        return sorted(metro_candidates, key=metro_score, reverse=True)[0]

    def score(token: str) -> Tuple[int, int]:
        freq = content_text.count(token) if token else 0
        gran = _region_granularity_rank(token)
        return (freq * 2 + gran, -region_tokens.index(token))

    return sorted(region_tokens, key=score, reverse=True)[0]


def compute_slot_preferences(
    opportunities: Dict[str, List[str]],
    *,
    topic: Optional[str] = None,
    content: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[str]]:
    """각 카테고리별로 "제목에 우선 인용할 토큰 1개" 를 반환.

    현재는 region 만 계산한다. 다른 카테고리는 None.
    반환: {'region': '[지역명]' or None, 'numeric': None, ...}
    """
    params_dict = params if isinstance(params, dict) else {}
    title_scope = params_dict.get('titleScope') if isinstance(params_dict.get('titleScope'), dict) else {}
    avoid_local = bool(title_scope and title_scope.get('avoidLocalInTitle'))

    combined_content = f'{topic or ""}\n{content or ""}'
    region_pref = _compute_region_preference(
        list(opportunities.get('region') or []),
        combined_content,
        avoid_local,
    )

    return {
        'region': region_pref,
        'numeric': None,
        'institution': None,
        'policy': None,
        'year': None,
    }


# ---------------------------------------------------------------------------
# PROMPT RENDERERS — generator 프롬프트에 주입할 XML 블록
# ---------------------------------------------------------------------------

_CATEGORY_LABEL: Dict[str, str] = {
    'region': '지역·행정구역',
    'numeric': '수치·단위',
    'institution': '기관·조직',
    'policy': '정책·법안',
    'year': '연도·기념일',
}


def render_slot_opportunities_block(
    opportunities: Dict[str, List[str]],
    *,
    require_min: int = 1,
    preferences: Optional[Dict[str, Optional[str]]] = None,
) -> str:
    """generator 프롬프트에 주입할 <slot_opportunities> XML 블록.

    preferences 가 주어지면 각 카테고리에서 우선 인용할 토큰을 preferred="true"
    로 마킹하고, 해당 토큰을 목록 맨 앞으로 정렬해 시각적으로 강조한다.
    """
    if not opportunities:
        return ''
    has_any = any(
        [t for t in (tokens or []) if isinstance(t, str) and t.strip()]
        for tokens in opportunities.values()
    )
    if not has_any:
        return ''

    preferences = preferences or {}
    lines: List[str] = []
    for category, tokens in opportunities.items():
        token_list = [t for t in (tokens or []) if isinstance(t, str) and t.strip()]
        if not token_list:
            continue
        label = _CATEGORY_LABEL.get(category, category)
        preferred_token = preferences.get(category)
        if preferred_token and preferred_token in token_list:
            token_list = [preferred_token] + [t for t in token_list if t != preferred_token]
        items_xml = ''.join(
            (f'<item preferred="true">{t}</item>' if t == preferred_token else f'<item>{t}</item>')
            for t in token_list
        )
        lines.append(f'  <category id="{category}" label="{label}">{items_xml}</category>')

    has_any_preferred = any(preferences.values()) if preferences else False
    preferred_hint = (
        ' 일부 토큰에는 preferred="true" 가 달려 있다 — 그 토큰이 "이 글의 진짜 스코프" 와 '
        '"화자의 직책 정책" 을 반영한 최우선 재료다.'
        if has_any_preferred else ''
    )
    note = (
        f'아래는 본문·토픽·프로필에서 자동 추출한 "제목에 넣을 수 있는 구체 재료" 다. '
        f'제목은 이 중 최소 {require_min} 개 카테고리에서 한 토큰 이상을 그대로 '
        f'인용해야 한다. 여기 없는 재료를 지어내지 말고, 이 재료를 few-shot good '
        f'예시처럼 자연스럽게 배치하라. 재료가 여러 개라면 정보 요소 3개 이하 '
        f'규칙과 상충하지 않는 선에서 조합한다.{preferred_hint}'
    )
    return (
        f'<slot_opportunities require_min="{require_min}">\n'
        f'  <note>{note}</note>\n'
        + '\n'.join(lines)
        + '\n</slot_opportunities>\n'
    )


def render_hook_rubric_block() -> str:
    """scorer 가 사용하는 rubric 을 LLM 에게 동일한 차원/토큰/패턴으로 공개한다.

    Why: 프롬프트와 scorer 가 따로 운영되면 LLM 은 산문 규칙만 보고 regex 를
    회피한다. 이 블록은 실제 채점 코드에서 쓰는 HOLLOW_POLICY_ABSTRACTION_TOKENS
    와 ANSWER_ANCHOR_PATTERNS 를 그대로 꺼내 보여 주고, flat = 실격이라는
    통과선을 명시해 generation 기준 = scoring 기준 = 하나가 되도록 한다.
    """
    # 실제 채점에서 쓰는 토큰/패턴을 직접 import — 이 블록의 내용과 scorer 가
    # 분기하는 일이 생기지 않도록.
    from .title_family_rules import HOLLOW_POLICY_ABSTRACTION_TOKENS

    forbidden_tokens = " / ".join(sorted(HOLLOW_POLICY_ABSTRACTION_TOKENS))
    forbidden_patterns = (
        '(a) 정책 추상 honorific: "숙원 사업", "숙원 과제", "최대 현안", '
        '"핵심 과제", "주요 쟁점", "중점 과제", "주요 과제"\n'
        '    (b) "N년 숙원/현안/과제/비전" 같은 기간+추상어 조합\n'
        '    (c) "완성할까?", "해내겠습니다", "이뤄내겠습니다", "만들어가겠습니다" '
        '같은 추상 상태 변화 (구체 대상 없이)'
    )
    required_anchors = (
        '(i) "[N]가지 조건/과제/방법/이유/쟁점/원칙/단계/기준/지표" 리스트 예고형\n'
        '    (ii) "[수치][단위] 감면/유치/확보/절감/배정/지급" 처럼 '
        '숫자+행동 동사\n'
        '    (iii) "[고유명 A]·[고유명 B] 중 어디로/어느" 선택지 질문형\n'
        '    (iv) "[상위 기준] 수준 도약/진입/추격/근접" 비교 앵커\n'
        '    (v) "취득세 감면", "조례 개정안 발의/통과/시행", "광역교통망 확정", '
        '"공백 해소", "앵커기업 유치", "직결 노선", "역세권 지정", '
        '"도첨산단 지정" 같은 구체 정책 행동\n'
        '    (vi) "17개 시도 중 유일/최초/최다" 순위 질의'
    )

    return (
        '<hook_quality_rubric enforce="strict" shared_with="scorer">\n'
        '  <contract>이 블록은 scorer(title_hook_quality.assess_title_hook_quality) '
        '가 사용하는 rubric 을 그대로 노출한다. 아래 forbidden / required 규칙은 '
        '프롬프트 장식이 아니라 실제 regex 채점으로 강제된다. '
        'status == "flat" 으로 채점되면 calculate_title_quality_score 가 '
        '자동 실격(0점) 처리하고 재생성을 트리거한다. '
        '통과선: status &gt;= "ok" (총점 &gt;= 5 / 15).</contract>\n'
        '  <note>concrete_slot + specificity 조합만으로는 부족하다. '
        'info_gap / narrative_arc / answer_anchor 중 최소 하나는 반드시 같이 '
        '채워야 few-shot 수준의 제목이다. '
        'body_reuse: &lt;slot_opportunities&gt; 에 5개 이상 재료가 있는데 '
        '제목이 하나도 재사용하지 않으면 -3점 자동 감점.</note>\n'
        '  <forbidden_tokens reason="hollow_policy_abstraction">\n'
        f'    <list>{forbidden_tokens}</list>\n'
        '    <rule>위 토큰이 제목에 들어가면 hollow=True, info_gap_score 강제 0, '
        'status=flat 으로 채점된다. 본문의 구체 정책·수치로 대체하라.</rule>\n'
        '  </forbidden_tokens>\n'
        '  <forbidden_patterns reason="universal_aeo_hollow">\n'
        f'    <list>{forbidden_patterns}</list>\n'
        '    <rule>위 패턴은 family 와 무관하게 모든 제목에 적용된다. '
        '구체 수치(25%, 17개 등) 또는 구체 행동 동사(감면/발의/유치 등) 가 '
        '같이 있으면 면제되지만, 없으면 자동 실격.</rule>\n'
        '  </forbidden_patterns>\n'
        '  <required_answer_anchors>\n'
        f'    <list>{required_anchors}</list>\n'
        '    <rule>answer_anchor &gt;= 1 이 되도록 위 유형 중 최소 1개를 반드시 '
        '포함하라. 없으면 info_gap 만으로 통과할 수 없고 flat 으로 실격된다.</rule>\n'
        '  </required_answer_anchors>\n'
        f'  <dimension id="info_gap" max="{HOOK_DIMENSION_MAX["info_gap"]}">'
        '질문/미완결 서사 — "왜", "어떻게", "얼마나", "무엇이 달라졌나" 같은 '
        '의문사 기반 실질 질문. 수사적 반문("완성할까?", "가능할까?") 은 '
        'hollow 로 탈락된다.</dimension>\n'
        f'  <dimension id="concrete_slot" max="{HOOK_DIMENSION_MAX["concrete_slot"]}">'
        'slot_opportunities 에서 뽑아 쓴 지역·수치·기관·연도·정책명. '
        '카테고리 1개당 +2 (최대 3 카테고리).</dimension>\n'
        f'  <dimension id="narrative_arc" max="{HOOK_DIMENSION_MAX["narrative_arc"]}">'
        '변화/대비 구조 — "→", "vs", "에서 ~까지", "12개월 만에", '
        '"274명 창출".</dimension>\n'
        f'  <dimension id="specificity" max="{HOOK_DIMENSION_MAX["specificity"]}">'
        '숫자+단위 토큰, 따옴표/괄호 고유어 인용.</dimension>\n'
        f'  <dimension id="answer_anchor" max="{HOOK_DIMENSION_MAX["answer_anchor"]}">'
        'AEO 답변 앵커 — 위 required_answer_anchors 참조. 신호 1개당 +1.</dimension>\n'
        '  <pass_gate>status=flat → 실격. 반드시 ok(&gt;=5/15) 이상.</pass_gate>\n'
        '</hook_quality_rubric>\n'
    )


__all__ = [
    'HOOK_DIMENSION_MAX',
    'HOOK_TOTAL_MAX',
    'INFO_GAP_PATTERNS',
    'NARRATIVE_ARC_PATTERNS',
    'assess_title_hook_quality',
    'compute_slot_preferences',
    'count_slots_used_in_title',
    'extract_slot_opportunities',
    'render_hook_rubric_block',
    'render_slot_opportunities_block',
]
