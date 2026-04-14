# functions/python/agents/common/h2_guide.py
"""AEO+SEO 최적화 H2 소제목 단일 원칙 소스 (Single Source of Truth)

모든 H2 관련 상수, 규칙, few-shot 예시, 길이 보정 로직을 이 파일에서 관리한다.
소비처: prompt_builder.py (StructureAgent), SubheadingAgent, content_validator.py, structure_normalizer.py
"""

import re

# ---------------------------------------------------------------------------
# 상수 (validator, normalizer, agent 공통)
# ---------------------------------------------------------------------------
H2_MIN_LENGTH = 10      # content_validator: 이 미만이면 H2_TEXT_SHORT
H2_MAX_LENGTH = 25      # content_validator: 이 초과이면 H2_TEXT_LONG
H2_OPTIMAL_MIN = 12     # 프롬프트 권장 최소
H2_OPTIMAL_MAX = 25     # 프롬프트 권장 최대
H2_BEST_RANGE = "15~22" # 네이버 최적 범위
H2_TRUNCATION_RSTRIP_CHARS = " -_.,:;!?"
H2_DUPLICATED_PARTICLES = (
    "으로",
    "에게",
    "에서",
    "까지",
    "부터",
    "처럼",
    "보다",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "과",
    "와",
    "의",
    "도",
    "만",
    "에",
    "로",
)
_H2_DUPLICATED_PARTICLE_RE = re.compile(
    rf"(?P<stem>[가-힣A-Za-z0-9]+?)(?P<particle>{'|'.join(H2_DUPLICATED_PARTICLES)})(?P=particle)(?=$|[\s,.:;!?])"
)
_H2_CONSECUTIVE_DUPLICATE_TOKEN_RE = re.compile(
    r"\b(?P<token>[가-힣A-Za-z0-9]{2,})\s+(?P=token)\b"
)
_H2_TRAILING_INCOMPLETE_ENDING_RE = re.compile(
    r"(?:"
    r"으로|에서|에게|까지|부터|처럼|보다|과|와|의|은|는|이|가|을|를|에|도|만|로|"
    r"겠(?:다|습)?|하는|있는|없는"
    r")$"
)


def normalize_h2_style(style: str = 'aeo') -> str:
    """지원하는 H2 스타일 키를 정규화한다."""
    normalized = str(style or '').strip().lower()
    return 'assertive' if normalized == 'assertive' else 'aeo'


def has_incomplete_h2_ending(text: str) -> bool:
    """조사/미완결 어미/잘린 한 글자 토큰으로 끝나는 H2를 감지한다."""
    candidate = re.sub(r'\s+', ' ', str(text or '').strip())
    if not candidate:
        return True

    last_token = candidate.split(' ')[-1]
    if len(last_token) <= 1:
        return True

    return bool(_H2_TRAILING_INCOMPLETE_ENDING_RE.search(last_token))


def sanitize_h2_text(
    text: str,
    *,
    min_length: int = H2_MIN_LENGTH,
    max_length: int = H2_MAX_LENGTH,
) -> str:
    """H2 길이/공백/잘림 정책을 공통 정규화한다."""
    candidate = re.sub(r'\s+', ' ', str(text or '').strip().strip('"\'')) 
    candidate = candidate.strip(H2_TRUNCATION_RSTRIP_CHARS)
    if not candidate:
        raise ValueError("h2 텍스트가 비어 있습니다.")

    for _ in range(3):
        repaired = _H2_DUPLICATED_PARTICLE_RE.sub(
            lambda match: f"{match.group('stem')}{match.group('particle')}",
            candidate,
        )
        repaired = _H2_CONSECUTIVE_DUPLICATE_TOKEN_RE.sub(
            lambda match: str(match.group("token") or ""),
            repaired,
        )
        repaired = re.sub(r"\s+", " ", repaired).strip()
        if repaired == candidate:
            break
        candidate = repaired

    candidate = re.sub(r'\s+', ' ', candidate).strip()
    return candidate


# ---------------------------------------------------------------------------
# build_h2_rules: 프롬프트용 H2 규칙 블록
# ---------------------------------------------------------------------------
def build_h2_rules(style: str = 'aeo') -> str:
    """H2 규칙 + few-shot 예시를 합친 완전한 블록을 반환한다.

    Args:
        style: 'aeo' (일반 AEO+SEO) 또는 'assertive' (논평/시사 주장형)
    """
    normalized_style = normalize_h2_style(style)
    if normalized_style == 'assertive':
        return f"""{_build_assertive_rules()}

{build_h2_examples(normalized_style)}"""
    return f"""{_build_aeo_rules()}

{build_h2_examples(normalized_style)}"""


def _build_aeo_rules() -> str:
    return f"""<h2_rules name="소제목 작성 규칙 (AEO+SEO)" severity="critical">
  <length min="{H2_OPTIMAL_MIN}" max="{H2_MAX_LENGTH}" optimal="{H2_BEST_RANGE}"/>
  <keyword_position>핵심 키워드를 문장 앞쪽 1/3에 배치</keyword_position>

  <types>
    <type name="질문형" strength="AEO 최강" ratio="40% 이상 권장">
      <good>청년 기본소득, 신청 방법은?</good>
      <good>전세 사기 피해, 어떻게 보상받나요?</good>
      <bad>이것을 꼭 알아야 합니다</bad>
    </type>
    <type name="명사형" strength="SEO 기본">
      <good>분당구 정자동 주차장 신설 위치</good>
      <bad>정책 안내</bad>
    </type>
    <type name="데이터형" strength="신뢰성">
      <good>청년 일자리 274명 창출 방법</good>
      <bad>좋은 성과를 냈습니다</bad>
    </type>
    <type name="절차형" strength="실용성">
      <good>청년 기본소득 신청 3단계 절차</good>
      <bad>신청하는 방법</bad>
    </type>
    <type name="비교형" strength="차별화">
      <good>기존 정책 대비 개선된 3가지</good>
      <bad>비교해 보겠습니다</bad>
    </type>
  </types>

  <banned>
    추상적 표현("노력", "열전", "마음"),
    모호한 지시어("이것", "그것", "관련 내용"),
    과장 표현("최고", "혁명적", "놀라운"),
    서술어 포함("~에 대한 설명", "~을 알려드립니다"),
    키워드 없는 짧은 제목("정책", "방법", "소개"),
    1인칭 표현("저는", "제가", "나는", "내가")
    후보명+약속형 선언("이름이 반드시 해내겠습니다" 등 - 소제목은 주장형이 아닌 정보형)
  </banned>

  <aeo_rule>H2 바로 아래 첫 문장(40~60자)은 해당 질문/주제에 대한 직접 답변으로 작성할 것.</aeo_rule>
</h2_rules>"""


def _build_assertive_rules() -> str:
    return f"""<h2_rules name="논평용 소제목 작성 규칙" severity="critical">
  <length min="{H2_OPTIMAL_MIN}" max="{H2_MAX_LENGTH}" optimal="{H2_BEST_RANGE}"/>
  <style>주장형 또는 명사형 (질문형 절대 금지)</style>
  <tone>단정적, 비판적, 명확한 입장 표명</tone>

  <types>
    <type name="단정형" pattern="~이다, ~해야 한다">
      <good>특검은 정치 보복이 아니다</good>
      <good>당당하면 피할 이유 없다</good>
    </type>
    <type name="비판형" pattern="대상을 명시한 비판">
      <good>진실 규명을 거부하는 태도</good>
    </type>
    <type name="명사형" pattern="핵심 쟁점 명시">
      <good>특검법의 정당성과 의의</good>
    </type>
  </types>

  <forbidden>질문형 소제목 ("~인가요?", "~일까요?", "~는?", "~할까?") 절대 금지</forbidden>
</h2_rules>"""


# ---------------------------------------------------------------------------
# build_h2_examples: few-shot 교정 예시 (50개)
# ---------------------------------------------------------------------------
def build_h2_examples(style: str = 'aeo') -> str:
    """H2 소제목 few-shot 예시 XML 블록을 반환한다."""
    if normalize_h2_style(style) == 'assertive':
        return _build_assertive_examples()
    return _build_aeo_examples()


def _build_aeo_examples() -> str:
    return """
<h2_examples name="소제목 교정 예시 (bad → good)">
  <type name="질문형" strength="AEO 최강">
    <good>청년 기본소득, 신청 방법은 무엇인가요?</good>
    <good>분당구 주차장, 어디에 새로 생기나요?</good>
    <good>보육료 지원, 얼마까지 받을 수 있나요?</good>
    <good>전세 사기 피해, 어떻게 보상받나요?</good>
    <good>2025년 예산안, 무엇이 달라졌나요?</good>
    <correction before="청년 기본소득에 대한 상세한 설명" after="청년 기본소득, 신청 방법은?"/>
    <correction before="이것을 꼭 알아야 합니다" after="보육료 지원 자격, 확인 방법은?"/>
    <correction before="청년 지원 정책에 관한 모든 것을 알려드립니다" after="청년 기본소득, 어떻게 신청하나요?"/>
  </type>

  <type name="명사형" strength="SEO 기본">
    <good>청년 기본소득 신청 자격 조건</good>
    <good>분당구 정자동 주차장 신설 위치</good>
    <good>2025년 상반기 예산 집행 현황</good>
    <good>청년 창업 지원 정책 상세 안내</good>
    <good>민원 처리 평균 소요 기간</good>
    <correction before="정책" after="청년 기본소득 신청 자격"/>
    <correction before="우리 지역의 발전을 위한 노력" after="분당구 주차장 50면 추가 건설"/>
    <correction before="여러 가지 사업들" after="청년 일자리·주거 지원 사업"/>
  </type>

  <type name="데이터" strength="신뢰성">
    <good>2025년 상반기 5대 주요 성과</good>
    <good>청년 일자리 274명 창출 방법</good>
    <good>민원 처리 14일→3일 단축 과정</good>
    <good>국비 120억 확보 세부 내역</good>
    <good>교통 사고율 40% 감소 요인 분석</good>
    <correction before="좋은 성과를 냈습니다" after="청년 일자리 274명 창출 성과"/>
    <correction before="예산을 많이 확보했어요" after="국비 120억 확보 성공"/>
    <correction before="개선되었습니다" after="민원 처리 14일→3일 개선"/>
  </type>

  <type name="절차" strength="실용성">
    <good>청년 기본소득 신청 3단계 절차</good>
    <good>온라인 민원 신청 필수 서류 목록</good>
    <good>보육료 지원금 수령까지 소요 기간</good>
    <good>주차장 건설 추진 일정 및 완공일</good>
    <good>전세 사기 피해 신고 방법 안내</good>
    <correction before="신청하는 방법" after="청년 기본소득 신청 3단계"/>
    <correction before="이렇게 하면 됩니다" after="온라인 민원 신청 필수 서류"/>
    <correction before="준비 사항에 대하여" after="청년 창업 지원 신청 준비 서류"/>
  </type>

  <type name="비교" strength="차별화">
    <good>청년 기본소득 vs 청년 수당 차이점</good>
    <good>2024년 vs 2025년 예산 변화 분석</good>
    <good>기존 정책 대비 개선된 3가지</good>
    <good>온라인 vs 오프라인 신청 장단점</good>
    <good>vs 주진우, 이재성의 약진</good>
    <good>타 지역 대비 분당구만의 특징</good>
    <correction before="비교해 보겠습니다" after="청년 기본소득 vs 청년수당 비교"/>
    <correction before="다른 정책들과의 차이" after="기존 정책 대비 개선된 5가지"/>
    <correction before="장점과 단점" after="온라인 vs 오프라인 신청 비교"/>
    <correction before="주진우 의원과의 가상대결, 제가 앞서가다" after="vs 주진우, 이재성의 약진"/>
  </type>

  <checklist>
    <must>12~25자 범위 (네이버 최적 15~22자)</must>
    <must>핵심 키워드를 앞 1/3에 배치</must>
    <must>질문형 또는 명확한 명사형 구조</must>
    <must>H2 바로 아래 첫 문장(40~60자)은 직접 답변</must>
    <ban>10자 미만 또는 25자 초과</ban>
    <ban>"이것", "그것", "관련" 등 모호한 지시어</ban>
    <ban>"최고", "혁명적", "놀라운" 등 과장 표현</ban>
    <ban>키워드 없는 추상적 표현 ("노력", "열심히")</ban>
    <ban>"~에 대한", "~관련" 등 불필요한 접속사</ban>
    <ban>"저는/제가/나는/내가" 같은 1인칭 표현</ban>
  </checklist>
</h2_examples>
"""


def _build_assertive_examples() -> str:
    return """
<h2_examples name="논평용 소제목 교정 예시 (bad → good)">
  <type name="단정형" strength="입장 선명화">
    <good>특검은 정치 보복이 아니다</good>
    <good>당당하면 피할 이유 없다</good>
    <good>권한 남용은 바로잡아야 한다</good>
    <correction before="특검에 대해 생각해 봅시다" after="특검은 정치 보복이 아니다"/>
    <correction before="이 사안을 어떻게 봐야 할까?" after="권한 남용은 바로잡아야 한다"/>
  </type>

  <type name="비판형" strength="쟁점 압축">
    <good>진실 규명을 거부하는 태도</good>
    <good>책임 회피로는 해명되지 않는다</good>
    <good>국민 신뢰를 무너뜨린 결정</good>
    <correction before="문제가 있어 보입니다" after="국민 신뢰를 무너뜨린 결정"/>
    <correction before="여러 논란이 이어지고 있습니다" after="책임 회피로는 해명되지 않는다"/>
  </type>

  <type name="명사형" strength="핵심 쟁점 명시">
    <good>특검법의 정당성과 의의</good>
    <good>거짓 해명의 구조적 한계</good>
    <good>민주주의 질서를 지키는 기준</good>
    <correction before="논평" after="특검법의 정당성과 의의"/>
    <correction before="관련 입장 정리" after="거짓 해명의 구조적 한계"/>
  </type>

  <checklist>
    <must>12~25자 범위 (네이버 최적 15~22자)</must>
    <must>질문형 대신 주장형 또는 명사형 사용</must>
    <must>핵심 쟁점을 직접 드러내는 표현 사용</must>
    <ban>"~인가요?", "~일까요?" 같은 질문형 어미</ban>
    <ban>"생각해 봅시다", "함께 보시죠" 같은 완곡한 유도문</ban>
    <ban>"정책", "입장", "논평"처럼 내용 없는 추상 제목</ban>
  </checklist>
</h2_examples>
"""


# ---------------------------------------------------------------------------
# Category Tone Anchor — SUBHEADING_STYLES.examples 흡수 (카테고리별 톤 예시)
# ---------------------------------------------------------------------------
CATEGORY_TONE_EXAMPLES = {
    'current-affairs': {
        'style': 'assertive',
        'description': '논평/시사 카테고리는 주장형 소제목을 사용합니다.',
        'preferred_types': ['주장형', '명사형'],
        'examples': [
            '"신공안 프레임"은 책임 회피에 불과하다',
            '특검은 정치 보복이 아니다',
            '당당하면 피할 이유 없다',
            '민주주의의 기본 질서를 지켜야',
        ],
    },
    'policy-proposal': {
        'style': 'aeo',
        'description': '정책 제안 카테고리는 구체적인 정보형 소제목을 사용합니다.',
        'preferred_types': ['데이터형', '명사형', '절차형'],
        'examples': [
            '청년 일자리 3대 핵심 전략',
            '국비 100억 확보 내역',
            '교통 체계 개편 5단계 로드맵',
        ],
    },
    'activity-report': {
        'style': 'aeo',
        'description': '의정활동 보고는 성과 중심 소제목을 사용합니다.',
        'preferred_types': ['데이터형', '명사형'],
        'examples': [
            '국정감사 5대 핵심 성과',
            '지역 현안 해결 실적',
            '국회 발의 법안 현황',
        ],
    },
    'daily-communication': {
        'style': 'aeo',
        'description': '일상 소통은 친근한 질문형도 허용됩니다.',
        'preferred_types': ['질문형', '명사형'],
        'examples': [
            '요즘 어떻게 지내시나요?',
            '함께 나눈 이야기들',
            '시민 여러분께 전하는 말씀',
        ],
    },
    'default': {
        'style': 'aeo',
        'description': '기본 AEO 최적화 스타일을 사용합니다.',
        'preferred_types': ['질문형', '명사형', '데이터형'],
        'examples': [],
    },
}


def get_category_tone(category: str) -> dict:
    """카테고리별 톤 앵커(description/preferred_types/examples/style)를 반환한다."""
    key = str(category or '').strip()
    if key in CATEGORY_TONE_EXAMPLES:
        return CATEGORY_TONE_EXAMPLES[key]
    return CATEGORY_TONE_EXAMPLES['default']


def build_category_tone_block(category: str) -> str:
    """카테고리별 톤 예시를 프롬프트용 XML 블록으로 반환한다.

    h2_guide의 일반 few-shot과 별도로, 카테고리마다 고유한 어조 앵커를 제공한다.
    예시 목록이 비어 있는 카테고리(default)에는 빈 문자열을 반환해 프롬프트 노이즈를
    방지한다.
    """
    tone = get_category_tone(category)
    examples = [str(item).strip() for item in (tone.get('examples') or []) if str(item).strip()]
    if not examples:
        return ''

    style = normalize_h2_style(tone.get('style'))
    description = str(tone.get('description') or '').strip()
    preferred_types = ', '.join(
        str(item).strip() for item in (tone.get('preferred_types') or []) if str(item).strip()
    )

    lines = [
        f'<h2_category_tone category="{category}" style="{style}">',
    ]
    if description:
        lines.append(f'  <description>{description}</description>')
    if preferred_types:
        lines.append(f'  <preferred_types>{preferred_types}</preferred_types>')
    for example in examples:
        safe = example.replace('<', '&lt;').replace('>', '&gt;')
        lines.append(f'  <good>{safe}</good>')
    lines.append('</h2_category_tone>')
    return '\n'.join(lines)
