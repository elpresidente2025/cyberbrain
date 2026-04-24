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
    # 수사적 반문("할까?/될까?/을까?") 은 info_gap 보상에서 제거.
    # 답변 엔진이 매칭 못하는 감상형 꼬리를 모델이 재생산하지 않도록
    # 종결 어미 리워드는 "~인가/~는가/~나" 계열(의문사 기반) 로만 한정한다.
    re.compile(r'(?:는가|인가|었나|했나)\s*$'),
    re.compile(r'(?:^|[\s,])왜\s'),                           # 왜 질문
    re.compile(r'(?:^|[\s,])어떻게\s'),                       # 어떻게 질문
    re.compile(r'(?:^|[\s,])(?:무엇이|무엇을|얼마(?:나|까지)|'
               r'어디서?|언제|어느)'),                        # 기타 의문사
    re.compile(r'(?:^|[\s,])어떤\s'),                         # 영향형: "어떤 변화가", "어떤 영향이"
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
# POLITICAL SAFETY — 정치 콘텐츠에서 금지해야 할 상업형/음모론형 패턴
# ---------------------------------------------------------------------------
#
# HIGH_RISK: 충격·폭로·음모론형 — 정치 콘텐츠 신뢰 파괴 및 선거 리스크.
#   매칭 시 assess_title_hook_quality() 에서 -5 감점.
# CAUTION: 공포 유발형 조건문 — 단독으로는 큰 문제가 없으나 맥락에 따라 위험.
#   매칭 시 -2 감점.
# 범용성 원칙: 정당·인물·지역 하드코드 없음. 표현 패턴만.

POLITICAL_HIGH_RISK_PATTERNS: List[Pattern[str]] = [
    re.compile(r'충격[!！]?|경악|소름|발칵'),
    re.compile(r'망합니다|끝장|폭망|대참사'),
    re.compile(r'숨겨진\s*진실|아무도\s*말하지\s*않는|진짜\s*속내|진짜\s*진실'),
    re.compile(r'상대(?:는|가).{0,10}(?:숨기|감추|외면|말하지\s*않)'),
]

POLITICAL_CAUTION_PATTERNS: List[Pattern[str]] = [
    re.compile(r'절대\s*(?:모르면|놓치면|하면\s*안\s*되는)'),
    re.compile(r'반드시\s*(?:알아야|봐야|해야\s*하는)'),
]

POLITICAL_RISK_PENALTY: Dict[str, int] = {
    'high': 5,
    'caution': 2,
}


# ---------------------------------------------------------------------------
# CONCRETE SLOT — 제목에 들어가면 즉시 구체성이 살아나는 고정 사실 슬롯
# ---------------------------------------------------------------------------

# 지역명 접미사 (행정구역 단위) — 한국 지명 패턴 기반, 특정 지역 하드코드 없음
# 🔑 두 가지 경계 강제:
#   1) negative lookbehind `(?<![가-힣])` — 왼쪽 단어 경계. 이게 없으면
#      "인천광역시의원" 안에서 "천광역시" 가 substring 으로 잡힌다.
#   2) prefix 최소 길이 2 — 한국 행정구역 이름에 1자 prefix 는 사실상
#      존재하지 않는다("서울특별시"·"인천광역시"·"경기도"·"제주시"·"강남구"
#      모두 2자 이상). 이걸 풀어두면 "감면"(→ 감+면), "이동"(→ 이+동),
#      "수리"(→ 수+리) 같은 1자 prefix 일반어가 끝없이 오탐으로 들어온다.
_REGION_SUFFIX_PATTERNS: List[Pattern[str]] = [
    # 광역 단위
    re.compile(r'(?<![가-힣])[가-힣]{2,4}(?:특별시|광역시|특별자치시|특별자치도)'),
    # 도 — 실제 도 이름(9개) 화이트리스트. "철도/제도/감면도" 같은 일반어 오탐 차단.
    re.compile(r'(?:경기|강원|충청?북|충청?남|전라?북|전라?남|경상?북|경상?남|제주)도(?=[\s,.에의은는이가을를]|$)'),
    # 시 — 2~3자 한글 + 시 (블랙리스트로 일반어 필터)
    re.compile(r'(?<![가-힣])[가-힣]{2,3}시(?=[\s,.에의은는이가을를]|$)'),
    # 기초 단위
    re.compile(r'(?<![가-힣])[가-힣]{2,4}(?:구|군|시)(?=[\s,.에의은는이가을를]|$)'),
    # 하위 단위
    re.compile(r'(?<![가-힣])[가-힣]{2,4}(?:동|읍|면|리)(?=[\s,.에의은는이가을를]|$)'),
]

# 접미사는 맞지만 지역이 아닌 일반 명사 블랙리스트 — 단순 표면 매칭 오탐 방지
# (CLAUDE.md: 범용 한국어 어휘만, 특정 지명 하드코드 없음)
_REGION_FALSE_POSITIVES: FrozenSet[str] = frozenset({
    # ~리 일반 명사
    '처리', '관리', '정리', '수리', '거리', '자리', '머리', '우리',
    '소리', '다리', '도리', '진리', '원리', '논리', '윤리', '부리',
    '종리', '분리', '무리', '뿌리', '다리', '사리',
    # ~리 외래어 복합어 (~valley 음차) — 지역명이 아니라 단지/산단 이름
    '테크노밸리', '실리콘밸리', '바이오밸리', '그린밸리', '디지털밸리',
    # ~도 — 화이트리스트 전환(도 패턴 자체가 9개 실제 도명만 매칭)으로
    # 대부분 불필요해졌으나, 특별자치도 패턴 등 다른 경로의 안전망으로 유지.
    '정도', '제도', '강도', '각도', '태도', '속도', '기도', '인도',
    '용도', '위도', '경도', '보도', '지도', '고도',
    # ~도 조사형 일반어
    '유치에도', '추진에도', '조성에도', '지정에도', '완성에도', '발표에도',
    # ~시 일반 명사 (실제 시 이름은 보통 2글자 이상)
    '수시', '당시', '즉시', '동시', '이시', '일시', '시시',
    # ~도시 복합어 — "자족도시/신도시" 등은 도시 유형 일반어이지 지명이 아니다
    '도시', '자족도시', '신도시', '계획도시', '혁신도시',
    '스마트도시', '위성도시', '전원도시', '미래도시', '생태도시',
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
# + "~역" 으로 끝나지만 고유 역명이 아닌 일반어
_INSTITUTION_FALSE_POSITIVES: FrozenSet[str] = frozenset({
    '정부', '임시정부', '대한민국임시정부',
    '외부', '내부', '일부', '전부', '대부', '상부', '하부',
    '서부', '동부', '남부', '북부', '각부', '본부',
    '일원', '지원', '공원', '병원', '학원', '정원',
    '과정', '과목', '팀원', '구성원',
    # ~역 일반 명사 — 역명 패턴이 걸러 내지 못하는 동음이의
    '지역', '영역', '광역', '수역', '전역', '구역', '권역', '성역',
    '경역', '감역', '관역', '기역', '인역', '유역',
    # ~타운 오탐 (고유 타운 이름이 아닌 일반어)
    '다운타운', '올드타운', '뉴타운',
})

# 수치 + 단위 — **정책 수량/규모** 만 포함한다.
# 중요: 순수 시간·기간 단위(년/월/일/기/차/개월/시/분/초/시간/세) 는 여기서
# 제외한다. "지난 4년간", "9월 시행", "9대 의회" 같은 문구는 어떤 활동보고에도
# 자연히 들어가는 표현이라, 이걸 numeric 버킷에 넣으면 본문 앵커 인용 게이트가
# "4년 숙원" 같은 hollow 제목을 통과시켜 버린다. 연도·기념일(YYYY년, N주년,
# N분기) 은 아래 _YEAR_PATTERNS 가 별도 버킷으로 받는다.
_NUMERIC_UNIT_PATTERN = re.compile(
    r'(\d+(?:\.\d+)?)\s*'
    r'(억원|억|만원|만|천만원|조|%|퍼센트|명|건|가구|곳|대|개|호|주년|'
    r'회|번|위|석|권|종|세대|km|킬로|배|가지|단계)'
)

# 기관·법인 접미 (위원회/회의체/부서/법안 등)
# 주의: '과', '팀' 은 조사·일반어와 혼동이 심해 의도적으로 제외.
# '원' 도 공원/병원/일원 등 일반 명사가 많아 FALSE_POSITIVES 로 걸러낸다.
#
# 🔑 시설·인프라 고유명(산업단지/테크노밸리/캠퍼스/타운/특화지구 및 역명)은
# "본문에만 등장하는 구체 재료" 로 제목 AEO 에 결정적이라 institution bucket
# 에 합류시킨다. 단, 역명은 "지역·영역·광역" 같은 흔한 일반어와 충돌하므로
# 전용 blacklist (_STATION_FALSE_POSITIVES) 를 거친다.
_INSTITUTION_SUFFIX_PATTERNS: List[Pattern[str]] = [
    re.compile(r'[가-힣A-Za-z0-9]{2,}(?:위원회|협의회|의회|추진단|자문단|연구원|공단|기금|재단)'),
    re.compile(r'[가-힣A-Za-z0-9]{2,}(?:청|국|부|처|센터|본부)(?=[\s,.은는이가을를에의]|$)'),
    # 시설·인프라 고유명 — 산업단지/산단/테크노밸리/캠퍼스/타운/특화지구
    re.compile(r'[가-힣A-Za-z0-9]{2,}(?:산업단지|산단|테크노밸리|캠퍼스|타운|특화지구)'),
    # 교통 인프라 — 광역철도/도시철도/노선/도로/고속도로/철도망/교통망
    # lazy {2,}? 로 "광역"+"철도" 를 "광역철"+"도로" 보다 우선 매칭.
    re.compile(
        r'[가-힣A-Za-z0-9]{2,}?(?:철도|노선|도로|고속도로|철도망|교통망)'
        r'(?=[\s,.·\-은는이가을를에의로와과도]|$)'
    ),
    # 역명 — 2~3자 한글 + 역. 다만 역 직전 글자가 지/영/광/수/전/구/권/성
    # 이면 "공업지역", "자치권역" 같은 지대·범위 일반어라 배제.
    re.compile(
        r'(?<![가-힣])[가-힣]{2,3}(?<![지영광수전구권성])역'
        r'(?=[\s,.·\-은는이가을를에의]|$)'
    ),
]

# 정책·법안·제도 접미 — "취득세 감면 조례" 처럼 띄어쓴 다단어 정책명도
# 잡도록 공백 토큰 1~2개를 허용한다. 단일 글자 `제` 는 "산업경제" 같은
# 일반 명사를 false positive 로 삼키므로 제외한다(`제도` 는 유지).
_POLICY_SUFFIX_PATTERNS: List[Pattern[str]] = [
    re.compile(
        r'(?:[가-힣A-Za-z0-9]{2,}\s*){1,2}'
        r'(?:법|법안|조례|특별법|기본법|개정안|시행령|시행규칙)'
    ),
    re.compile(
        r'(?:[가-힣A-Za-z0-9]{2,}\s*){1,2}'
        r'(?:제도|정책|사업|프로젝트|이니셔티브|기획|공약)'
    ),
    # 계획·전략·방안 — "구축계획", "발전전략" 등 복합명사만.
    # 다단어 허용(`{1,3}\s*`) 은 "분석은 사업" / "BRT로 계획" 같은
    # 문장 조각 오탐을 유발하므로, 접두 한글 + 접미 복합어만 매칭.
    re.compile(r'[가-힣]{2,}(?:계획|방안|전략|로드맵)'),
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


def _substring_dedupe_preserve_order(items: List[str]) -> List[str]:
    """다른 항목의 진부분집합(proper substring) 인 토큰을 제거한다.

    "인천광역시" + "천광역시" 처럼 lookbehind 를 뚫고 들어온 오탐이 남아
    있어도 최종 단계에서 더 긴 쪽만 남겨 LLM 프롬프트·스코어러에 일관된
    앵커만 노출되도록 한다. 길이가 같은 완전 중복은 이미 상위 함수
    `_dedupe_preserve_order` 에서 제거된 상태로 들어온다.
    """
    out: List[str] = []
    for item in items:
        if any(item != other and item in other for other in items):
            continue
        out.append(item)
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
    stance_text = str(params_dict.get('stanceText') or '')

    # 지역 — params 의 사용자 프로필에서 우선 읽고, 없으면 본문 패턴 추출.
    # 🔑 필드명은 Firestore canonical(handlers/profile.py) 그대로:
    #   regionMetro(광역) / regionLocal(기초).
    #   electoralDistrict(선거구)는 내부 메타데이터이므로 제목 재료에서 제외.
    # 과거 이름이던 regionDistrict/regionTown 은 DB 에 존재하지 않는 유령
    # 필드라 읽지 않는다.
    region_hints: List[str] = []
    for key in ('regionLocal', 'regionMetro'):
        val = str(params_dict.get(key) or '').strip()
        if val:
            region_hints.append(val)
    region_surface = _extract_by_patterns(
        combined, _REGION_SUFFIX_PATTERNS, blacklist=_REGION_FALSE_POSITIVES
    )
    # 본문 패턴이 프로필과 겹치면 중복 제거 + "천광역시 ⊂ 인천광역시"
    # 형태의 substring 오탐까지 최종 단계에서 걷어낸다.
    region_all = _substring_dedupe_preserve_order(
        _dedupe_preserve_order(region_hints + region_surface)
    )

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

    buckets: Dict[str, List[str]] = {
        'region': region_all[:4],
        'numeric': numeric_all[:6],
        # institution cap 은 시설·인프라 고유명(산단/역명 등) 수용을 위해 5로 확장.
        # 기존 3은 위원회·센터 등 "기관명" 만 가정한 값이었다.
        'institution': institutions[:5],
        'policy': policies[:3],
        'year': years[:3],
    }

    # 🔑 body-exclusive 메타 — topic/stanceText 에는 없고 본문에서만 발견된
    # 고유 토큰을 bucket 별로 분리해 둔다. generator 프롬프트와 scorer 모두
    # 이 메타 필드를 읽어 "topic 재포장" 과 "본문 재료 실사용" 을 구분한다.
    # 언더스코어 접두로 시작하는 메타 키라 기존 bucket 소비자(bucket name
    # 화이트리스트로 iterate 하는 title_keywords / title_prompt_parts) 에는
    # 영향을 주지 않는다.
    body_exclusive_meta: Dict[str, List[str]] = {}
    for bucket_name, tokens in buckets.items():
        exclusive = [t for t in tokens if _is_body_exclusive(t, topic_text, stance_text)]
        if exclusive:
            body_exclusive_meta[bucket_name] = exclusive
    buckets['_bodyExclusive'] = body_exclusive_meta  # type: ignore[assignment]
    return buckets


_SLOT_STEM_SUFFIXES = (
    # 길이 내림차순 — 긴 접미사가 먼저 매칭되도록 배열.
    '특별자치도', '특별자치시', '광역시', '특별시',
    '위원회', '협의회', '개정안', '기본법', '특별법',
    '프로젝트',
    '의회', '재단', '공단', '기금',
    '법안', '조례', '제도', '정책', '사업', '공약',
    # 기초 행정구역 접미 — "계양구" stem "계양", "해운대구" stem "해운대"
    # 같은 축약이 topic/title 매칭에 반영되도록. len(stem) >= 2 가드가
    # "연구/도구/관리" 같은 1자 stem 일반어를 자동 차단한다.
    '구', '시', '군', '동', '읍', '면', '리',
)


def _slot_token_used_in_title(title: str, token: str) -> bool:
    if not title or not token:
        return False
    compact_title = re.sub(r'\s+', '', title)
    compact_token = re.sub(r'\s+', '', token)
    if compact_token and compact_token in compact_title:
        return True
    for suffix in _SLOT_STEM_SUFFIXES:
        if compact_token.endswith(suffix) and len(compact_token) - len(suffix) >= 2:
            stem = compact_token[: -len(suffix)]
            if stem and stem in compact_title:
                return True
    return False


def _is_body_exclusive(token: str, topic: str, stance: str) -> bool:
    """token 이 topic/stanceText 에 compact substring 으로 등장하지 않으면 body-exclusive.

    "본문에서 뽑혔는데 topic/stanceText 입력에는 없는 고유 재료" 를 식별하는 게
    목적이다. compact 비교(공백 제거) 로 띄어쓰기 차이를 흡수하고, stem
    stripping 으로 "테크노밸리 사업" 같은 접미사 확장형이 topic "테크노밸리"
    에 먹히도록 한다 — 이 경우 token 은 topic 의 단순 확장이라 body-exclusive
    가 아니다.

    - 빈 토큰 → False (애초에 앵커 후보가 아님)
    - topic/stance 모두 비어 있음 → True (비교할 참조가 없으므로 기본은 exclusive)
    """
    compact_token = re.sub(r'\s+', '', token or '')
    if not compact_token:
        return False
    compact_ref = re.sub(r'\s+', '', (topic or '') + (stance or ''))
    if not compact_ref:
        return True
    if compact_token in compact_ref:
        return False
    for suffix in _SLOT_STEM_SUFFIXES:
        if compact_token.endswith(suffix):
            stem = compact_token[: -len(suffix)]
            if len(stem) >= 2 and stem in compact_ref:
                return False
    return True


def count_slots_used_in_title(title: str, opportunities: Dict[str, List[str]]) -> Dict[str, Any]:
    """제목이 slot_opportunities 중 몇 개를 인용했는지 센다."""
    if not title or not opportunities:
        return {'used': 0, 'matched': {}, 'total': 0}

    matched: Dict[str, List[str]] = {}
    total = 0
    used = 0
    for category, tokens in opportunities.items():
        # 언더스코어 접두 키(`_bodyExclusive` 등) 는 bucket 이 아닌 메타라 스킵.
        if isinstance(category, str) and category.startswith('_'):
            continue
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

    # Kiwi-first: 수사적 반문은 info_gap 보상에서 제외, 실질 질문은 보장 가산.
    # Kiwi 실패(verdict=None) 시에는 regex fallback 만 실행.
    try:
        from agents.common import korean_morph  # local import to avoid cycle
        verdict = korean_morph.classify_title_ending(title)
    except Exception:
        verdict = None

    verdict_class = verdict.get("class") if isinstance(verdict, dict) else None

    if verdict_class == "real_question":
        hits.append("kiwi:real_question")
    # rhetorical_question 이면 어미 regex 축("는가|인가|었나|했나" / "\?$") 은 건너뛴다.
    skip_ending_regex = verdict_class == "rhetorical_question"

    for pat in INFO_GAP_PATTERNS:
        if skip_ending_regex and pat.pattern in (
            r'\?\s*$',
            r'(?:는가|인가|었나|했나)\s*$',
        ):
            continue
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

    # info_gap — 수사적 반문("완성할까?") 도 1차적으로는 정보 격차로 보상하지만,
    # 본문 구체 앵커가 하나도 없으면 scorer 상위의 body_anchor_coverage gate
    # (title_scoring._assess_body_anchor_coverage) 에서 어차피 실격 처리된다.
    # hollow regex 블랙리스트는 여기서 들지 않는다.
    gap_count, gap_signals = _count_info_gap_signals(clean_title)
    info_gap_score = HOOK_DIMENSION_MAX['info_gap'] if gap_count >= 1 else 0
    if info_gap_score:
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

    # political_risk — 상업형/음모론형 표현 감점
    political_risk_level = None
    political_risk_penalty = 0
    for pat in POLITICAL_HIGH_RISK_PATTERNS:
        if pat.search(clean_title):
            political_risk_level = 'high'
            political_risk_penalty = POLITICAL_RISK_PENALTY['high']
            features.append('political_high_risk')
            break
    if not political_risk_level:
        for pat in POLITICAL_CAUTION_PATTERNS:
            if pat.search(clean_title):
                political_risk_level = 'caution'
                political_risk_penalty = POLITICAL_RISK_PENALTY['caution']
                features.append('political_caution')
                break
    total = max(0, total - political_risk_penalty)

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
        'political_risk_level': political_risk_level,
        'political_risk_penalty': political_risk_penalty,
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
        for key, tokens in opportunities.items()
        if not (isinstance(key, str) and key.startswith('_'))
    )
    if not has_any:
        return ''

    preferences = preferences or {}
    # body_exclusive 메타는 `_bodyExclusive` 키에 bucket 별 리스트로 담겨 있다.
    # 없거나 형태가 다르면 안전하게 빈 맵으로 취급.
    body_exclusive_raw = opportunities.get('_bodyExclusive') if isinstance(opportunities, dict) else None
    body_exclusive_map: Dict[str, set] = {}
    if isinstance(body_exclusive_raw, dict):
        for key, vals in body_exclusive_raw.items():
            if isinstance(key, str) and isinstance(vals, list):
                body_exclusive_map[key] = {v for v in vals if isinstance(v, str)}

    lines: List[str] = []
    for category, tokens in opportunities.items():
        # 언더스코어 접두 메타 키는 렌더링에서 제외.
        if isinstance(category, str) and category.startswith('_'):
            continue
        token_list = [t for t in (tokens or []) if isinstance(t, str) and t.strip()]
        if not token_list:
            continue
        label = _CATEGORY_LABEL.get(category, category)
        preferred_token = preferences.get(category)
        if preferred_token and preferred_token in token_list:
            token_list = [preferred_token] + [t for t in token_list if t != preferred_token]
        exclusive_set = body_exclusive_map.get(category, set())

        def _item_xml(tok: str) -> str:
            attrs = ''
            if tok == preferred_token:
                attrs += ' preferred="true"'
            if tok in exclusive_set:
                attrs += ' body_exclusive="true"'
            return f'<item{attrs}>{tok}</item>'

        items_xml = ''.join(_item_xml(t) for t in token_list)
        lines.append(f'  <category id="{category}" label="{label}">{items_xml}</category>')

    has_any_preferred = any(preferences.values()) if preferences else False
    preferred_hint = (
        ' 일부 토큰에는 preferred="true" 가 달려 있다 — 그 토큰이 "이 글의 진짜 스코프" 와 '
        '"화자의 직책 정책" 을 반영한 최우선 재료다.'
        if has_any_preferred else ''
    )
    has_any_body_exclusive = any(body_exclusive_map.values())
    body_exclusive_hint = (
        ' body_exclusive="true" 가 달린 토큰은 topic 에는 없고 본문에서만 발견된 '
        '구체 재료다. 이런 토큰이 하나라도 있으면 제목은 그 중 최소 1개를 반드시 '
        '인용해야 한다 — topic 에 있던 단어만 재조합하면 "재료 재포장" 이라 '
        '제목이 구체성을 얻지 못한다.'
        if has_any_body_exclusive else ''
    )
    note = (
        f'아래는 본문·토픽·프로필에서 자동 추출한 "제목에 넣을 수 있는 구체 재료" 다. '
        f'제목은 이 중 최소 {require_min} 개 카테고리에서 한 토큰 이상을 그대로 '
        f'인용해야 한다. 여기 없는 재료를 지어내지 말고, 이 재료를 few-shot good '
        f'예시처럼 자연스럽게 배치하라. 재료가 여러 개라면 정보 요소 3개 이하 '
        f'규칙과 상충하지 않는 선에서 조합한다.{preferred_hint}{body_exclusive_hint}'
    )
    return (
        f'<slot_opportunities require_min="{require_min}">\n'
        f'  <note>{note}</note>\n'
        + '\n'.join(lines)
        + '\n</slot_opportunities>\n'
    )


def render_hook_rubric_block() -> str:
    """scorer 가 사용하는 rubric 을 LLM 에게 동일한 차원/신호로 공개한다.

    Why: 프롬프트와 scorer 가 분기하면 LLM 은 산문 규칙만 보고 실제 채점을
    회피한다. 이 블록은 scorer 의 dimension/신호 정의만 그대로 노출한다. 정적
    forbidden regex 는 쓰지 않고, 본문 구체 앵커 인용 여부는 별도의
    <available_slots> / body_anchor_coverage 게이트가 본문 추출 기반으로
    강제한다.
    """
    required_anchors = (
        '(i) "[N]가지 조건/과제/방법/이유/쟁점/원칙/단계/기준/지표" 리스트 예고형\n'
        '    (ii) "[수치][단위] 감면/유치/확보/절감/배정/지급" 처럼 '
        '숫자+행동 동사\n'
        '    (iii) "[고유명 A]·[고유명 B] 중 어디로/어느" 선택지 질문형\n'
        '    (iv) "[상위 기준] 수준 도약/진입/추격/근접" 비교 앵커\n'
        '    (v) 본문에서 뽑힌 구체 정책·조례·사업·행동 동사를 그대로 인용\n'
        '    (vi) "17개 시도 중 유일/최초/최다" 순위 질의'
    )

    return (
        '<hook_quality_rubric enforce="strict" shared_with="scorer">\n'
        '  <contract>이 블록은 scorer(title_hook_quality.assess_title_hook_quality) '
        '가 사용하는 rubric 을 그대로 노출한다. 아래 required / dimension 정의는 '
        '프롬프트 장식이 아니라 실제 신호 채점으로 강제된다. '
        '통과선: status &gt;= "ok" (총점 &gt;= 5 / 15). '
        '추가로 본문에서 뽑힌 구체 앵커(정책·기관·수치·연도) 중 최소 1개를 '
        '제목에 직접 인용해야 하며, 없으면 body_anchor_coverage 게이트에서 '
        '자동 실격 처리된다.</contract>\n'
        '  <note>concrete_slot + specificity 조합만으로는 부족하다. '
        'info_gap / narrative_arc / answer_anchor 중 최소 하나는 반드시 같이 '
        '채워야 few-shot 수준의 제목이다. '
        'body_reuse: &lt;slot_opportunities&gt; 에 5개 이상 재료가 있는데 '
        '제목이 하나도 재사용하지 않으면 -3점 자동 감점.</note>\n'
        '  <required_answer_anchors>\n'
        f'    <list>{required_anchors}</list>\n'
        '    <rule>answer_anchor &gt;= 1 이 되도록 위 유형 중 최소 1개를 반드시 '
        '포함하라. 없으면 info_gap 만으로 통과할 수 없고 flat 으로 실격된다.</rule>\n'
        '  </required_answer_anchors>\n'
        f'  <dimension id="info_gap" max="{HOOK_DIMENSION_MAX["info_gap"]}">'
        '질문/미완결 서사 — "왜", "어떻게", "얼마나", "무엇이 달라졌나" 같은 '
        '의문사 기반 실질 질문. 본문 구체 앵커가 없는 수사적 반문은 '
        'body_anchor_coverage 게이트에서 실격된다.</dimension>\n'
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
        '  <hook_selection_tracks priority="high">\n'
        '    <principle>제목은 먼저 답변 가능성을 확보하고, 그다음 독자 관심을 유도한다. '
        '정치 콘텐츠에서는 상업형 후킹을 쓰지 않는다.</principle>\n'
        '    <track type="aeo_priority" maps_to="QUESTION_ANSWER|DATA_BASED|COMPARISON"\n'
        '           when="본문에 수치·정책명·기관명·비교 재료가 있을 때">\n'
        '      <rule>구체 재료를 제목에 최소 1개 이상 반영한다.</rule>\n'
        '      <rule>왜/어떻게/어떤 변화가/무엇이 달라지나 중 하나의 답변 구조를 만든다.</rule>\n'
        '      <good>[정책명], 왜 지금 필요한지 설명드립니다</good>\n'
        '      <good>[이슈], 주민 생활에 어떤 변화가 생기나</good>\n'
        '      <good>[지표] [이전값]→[현재값], 무엇이 달라졌나</good>\n'
        '    </track>\n'
        '    <track type="engagement_first" maps_to="VIRAL_HOOK|ISSUE_ANALYSIS"\n'
        '           when="서사·현장 중심이고 수치 재료가 희박할 때">\n'
        '      <rule>폭로·공포·상대 공격 없이 문제의식과 대안을 연결한다.</rule>\n'
        '      <good>현장에서 확인한 [이슈], 대안은 무엇인가</good>\n'
        '      <good>[이슈], 왜 지금 주목해야 하나</good>\n'
        '      <acceptable>주민 여러분이 가장 자주 말씀하신 문제부터 살펴보겠습니다</acceptable>\n'
        '    </track>\n'
        '    <banned reason="정치 콘텐츠 신뢰 파괴·선거 리스크 — scorer에서 political_high_risk 감점">\n'
        '      <bad>충격! [이슈]의 숨겨진 진실</bad>\n'
        '      <bad>이 정책 모르면 주민들이 손해봅니다</bad>\n'
        '      <bad>상대가 절대 말하지 않는 비밀</bad>\n'
        '    </banned>\n'
        '  </hook_selection_tracks>\n'
        '</hook_quality_rubric>\n'
    )


__all__ = [
    'HOOK_DIMENSION_MAX',
    'HOOK_TOTAL_MAX',
    'INFO_GAP_PATTERNS',
    'NARRATIVE_ARC_PATTERNS',
    'POLITICAL_HIGH_RISK_PATTERNS',
    'POLITICAL_CAUTION_PATTERNS',
    'POLITICAL_RISK_PENALTY',
    'assess_title_hook_quality',
    'compute_slot_preferences',
    'count_slots_used_in_title',
    'extract_slot_opportunities',
    'render_hook_rubric_block',
    'render_slot_opportunities_block',
]
