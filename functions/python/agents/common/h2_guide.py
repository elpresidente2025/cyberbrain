# functions/python/agents/common/h2_guide.py
"""AEO+SEO 최적화 H2 소제목 단일 원칙 소스 (Single Source of Truth)

모든 H2 관련 상수, 규칙, few-shot 예시, 길이 보정 로직을 이 파일에서 관리한다.
소비처: prompt_builder.py (StructureAgent), SubheadingAgent, content_validator.py, structure_normalizer.py
"""

import re
from typing import Dict, List

from . import korean_morph

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
# 조건부/가정 접속 어미 "~면" 계열. 종속절 접속어라 주절이 없으면 문장 미완결.
# 예: "대장지구와 비교하면" → 주절 누락. "학생이면" → 주절 누락.
# 반드시 stem (1+ 한글 음절) 이 선행해야 매칭되도록 `[가-힣]+` 앵커를 둔다.
# 이렇게 하면 "측면/국면/방면/이면(뒷면)/라면(음식)" 같은 명사 단독형은 제외되고
# 오직 용언 어간 + 조건부 어미 결합형만 잡힌다.
_H2_CONDITIONAL_TAIL_RE = re.compile(
    r"[가-힣]+(?:하|되|이|라|려|으려|으)면$"
)
# 관형형 어미 `-(으)ㄹ` 단독 종결 감지. 용언(하다/가다/내다/되다/오다/보다/치다/키다)
# 의 관형형이 수식 대상 없이 H2 끝에 남으면 미완결이다.
# 예: "공동체 책임 다할", "정신을 이어갈", "꿈을 펼칠"
# 비교 대상인 명사(길, 달, 발, 물 등)와 혼동하지 않도록 마지막 음절이
# 할/갈/낼/될/올/볼/칠/킬 인 2음절 이상 토큰만 매칭.
_H2_TRAILING_VERBAL_MODIFIER_RE = re.compile(
    r"[가-힣]{1,}(?:할|갈|낼|될|올|볼|칠|킬)$"
)

# 주어 조사 `가`가 문장 중간에 나타나지만 술어가 전혀 없는 경우를 감지한다.
# 예: "청년의 목소리가 실질적 변화" — "목소리가" 뒤에 동사/서술어가 없음.
# 직업 접미사 `-가`로 끝나는 일반명사(정치가, 전문가 등)는 false-positive를 피하기 위해 제외.
_PROFESSION_GA_SUFFIX = frozenset({
    "정치가", "전문가", "작곡가", "소설가", "만화가", "애호가",
    "평론가", "예술가", "작가", "화가", "대가", "명가",
    "건축가", "사진가", "조각가", "음악가", "무용가",
    "성악가", "연출가", "문학가", "번역가", "수필가",
    "미술가", "안무가", "공예가", "여행가", "이론가",
    "사상가", "교육가", "혁명가", "운동가", "탐험가",
    "독립운동가", "사업가", "기업가", "자선가",
})
_DANGLING_SUBJECT_PARTICLE_RE = re.compile(
    r"(?<![가-힣])(?P<stem>[가-힣]{2,})가(?=\s+[가-힣])"
)
# "앞으로도 기업", "계속 청년" 처럼 시간 지속·미래 지향 부사가 서술어 없이
# bare 명사구로만 끝나는 H2 를 감지한다. 이런 부사는 반드시 동사/형용사
# 서술어를 동반해야 의미가 완결된다.
_TIME_CONTINUATION_ADVERB_RE = re.compile(
    r"(?:^|[\s,])(?:앞으로도|앞으로|이제는|이제|계속|꾸준히|지속적으로|끝까지)(?=\s|$)"
)
_HEADING_PREDICATE_MARKER_RE = re.compile(
    r"(?:"
    r"다|까|요|죠|냐|여|네|지|"
    r"니다|니까|까요|나요|인가|이다|"
    r"했다|됐다|간다|온다|된다|한다|"
    r"습니다|습니까|입니다|입니까|"
    r"겠다|겠어|겠죠|겠지|겠네|겠나|겠습|"
    r"하는|되는|있는|없는|싶은|"
    r"[?!]"
    r")"
)


def _has_dangling_subject_particle(heading: str) -> bool:
    stripped = re.sub(r"\s+", " ", str(heading or "")).strip()
    if len(stripped) < 5:
        return False
    if "'" in stripped or '"' in stripped or "“" in stripped:
        return False

    for match in _DANGLING_SUBJECT_PARTICLE_RE.finditer(stripped):
        stem = str(match.group("stem") or "")
        if (stem + "가") in _PROFESSION_GA_SUFFIX:
            continue
        tail = stripped[match.end():]
        if not _HEADING_PREDICATE_MARKER_RE.search(tail):
            return True
    return False


def normalize_h2_style(style: str = 'aeo') -> str:
    """지원하는 H2 스타일 키를 정규화한다."""
    normalized = str(style or '').strip().lower()
    return 'assertive' if normalized == 'assertive' else 'aeo'


def has_incomplete_h2_ending(text: str) -> bool:
    """조사/미완결 어미/잘린 한 글자 토큰으로 끝나는 H2를 감지한다.

    또한 주어 조사(`가`)만 있고 서술어가 전혀 없는 '문장 끊김'도 미완결로 본다.
    예: "청년의 목소리가 실질적 변화" — 술어 누락으로 hard-fail.
    """
    candidate = re.sub(r'\s+', ' ', str(text or '').strip())
    if not candidate:
        return True

    # Kiwi 형태소 분석: ETM(관형형), EC(연결어미), 명사구 파일업, 조사 단독 종결.
    # 실패 시 None 반환 — regex fallback 으로 내려간다.
    kiwi_verdict = korean_morph.is_incomplete_ending(candidate)
    if kiwi_verdict is True:
        return True

    last_token = candidate.split(' ')[-1]
    if len(last_token) <= 1:
        return True

    if _H2_TRAILING_INCOMPLETE_ENDING_RE.search(last_token):
        return True

    if _H2_CONDITIONAL_TAIL_RE.search(last_token):
        return True

    if len(last_token) >= 2 and _H2_TRAILING_VERBAL_MODIFIER_RE.search(last_token):
        return True

    if _has_dangling_subject_particle(candidate):
        return True

    if _has_dangling_time_continuation_adverb(candidate):
        return True

    return False


def _has_dangling_time_continuation_adverb(heading: str) -> bool:
    """시간 지속 부사(앞으로도/계속/끝까지 등) + bare 명사 조합을 탐지.

    예: "앞으로도 기업" → 부사 뒤에 서술어 없이 명사만 있어 의미 미완결.
    부사 뒤에 서술어 마커(다/까/요, 하는/되는 등) 또는 물음표가 존재하면 정상.
    """
    stripped = re.sub(r"\s+", " ", str(heading or "")).strip()
    if len(stripped) < 5:
        return False

    match = _TIME_CONTINUATION_ADVERB_RE.search(stripped)
    if not match:
        return False

    tail = stripped[match.end():].strip()
    if not tail:
        return True

    if _HEADING_PREDICATE_MARKER_RE.search(tail):
        return False

    return True


def sanitize_h2_text(
    text: str,
    *,
    min_length: int = H2_MIN_LENGTH,
    max_length: int = H2_MAX_LENGTH,
) -> str:
    """H2 길이/공백/잘림 정책을 공통 정규화한다."""
    raw = str(text or '').strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ('"', "'"):
        raw = raw[1:-1].strip()
    candidate = re.sub(r'\s+', ' ', raw)
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
  <principle>소제목은 '약속(promise)', 본문은 '이행(fulfillment)'. 7 아키타입 중 하나를 골라 본문이 답할 약속을 던진다.</principle>

  <surface_diversity severity="critical">
    6개 H2 전체에서 **같은 표면형**이 3개 이상 반복되면 본문이 단조롭게 읽힌다. 특히 쉼표(,)로 두 구를 끊어 잇는 형태("X, Y입니다" / "X, Y인가요?")는 AEO에 강력하지만 **6개 중 최대 2개까지만** 사용하고, 나머지는 아래 형태를 섞어 분산할 것:
    (a) 완결형 서술문: "청년 기본소득은 필수다"
    (b) 완결형 질문문: "보육료 지원 한도는 얼마인가요"
    (c) 구두점 없는 명사구: "2024년 상반기 5대 성과"
    (d) 동사 종결형: "통학로 안전을 반드시 지키겠습니다"
    한 가지 형태만 6번 반복하면 품질 실패로 간주한다.
  </surface_diversity>

  <archetypes>
    <archetype name="질문형" strength="AEO 최강">
      <good>청년 기본소득, 신청 방법은?</good>
      <good>보육료 지원 한도는 얼마까지 가능한가요</good>
      <bad>이것을 꼭 알아야 합니다</bad>
    </archetype>
    <archetype name="목표형" strength="약속·다짐">
      <good>청년 일자리를 위한 3가지 약속</good>
      <good>통학로 안전을 반드시 지키겠습니다</good>
      <bad>열심히 노력하겠습니다</bad>
    </archetype>
    <archetype name="주장형" strength="입장 선명화">
      <good>청년 기본소득은 필수다</good>
      <bad>청년 정책에 대한 생각</bad>
    </archetype>
    <archetype name="이유형" strength="배경·근거">
      <good>청년 기본소득이 필요한 이유</good>
      <bad>배경 설명</bad>
    </archetype>
    <archetype name="대조형" strength="차별화">
      <good>기존 정책과 청년 기본소득은 어떻게 다른가</good>
      <bad>비교해 보겠습니다</bad>
    </archetype>
    <archetype name="사례형" strength="증거·현장">
      <good>청년 일자리 274명 창출 현장</good>
      <bad>좋은 성과를 냈습니다</bad>
    </archetype>
    <archetype name="서술형" strength="담담한 사태 제시" limit="글당 0~1회">
      <good>지역 경제의 새 판을 열다</good>
      <good>주민 목소리에 귀를 기울이다</good>
      <bad>열심히 하다</bad>
      <note>동사 사전형(기본형) 종결. 절제된 톤으로 임팩트를 주지만 남용하면 단조로워진다. 6개 H2 중 0~1개만 사용할 것.</note>
    </archetype>
  </archetypes>

  <banned>
    추상적 표현("노력", "열전", "마음"),
    모호한 지시어("이것", "그것", "관련 내용"),
    과장 표현("최고", "혁명적", "놀라운"),
    서술어 포함("~에 대한 설명", "~을 알려드립니다"),
    키워드 없는 짧은 제목("정책", "방법", "소개"),
    1인칭 표현("저는", "제가", "나는", "내가")
  </banned>

  <aeo_rule>H2 바로 아래 첫 문장(40~60자)은 해당 소제목(약속)에 대한 직접 답변으로 작성할 것.</aeo_rule>
</h2_rules>"""


def _build_assertive_rules() -> str:
    return f"""<h2_rules name="논평용 소제목 작성 규칙" severity="critical">
  <length min="{H2_OPTIMAL_MIN}" max="{H2_MAX_LENGTH}" optimal="{H2_BEST_RANGE}"/>
  <style>주장·이유·질문 아키타입 중에서 선택</style>
  <tone>단정적, 논리적, 명확한 입장 표명</tone>

  <archetypes>
    <archetype name="주장형" pattern="~이다, ~해야 한다, 바로잡/회피/한계">
      <good>특검은 정치 보복이 아니다</good>
      <good>당당하면 피할 이유 없다</good>
      <good>권한 남용은 바로잡아야 한다</good>
    </archetype>
    <archetype name="이유형" pattern="배경/까닭/원인/이유">
      <good>권한 남용을 묵인할 수 없는 이유</good>
      <good>왜 진실 규명이 지금 필요한가</good>
    </archetype>
    <archetype name="질문형" pattern="본문이 답할 질문">
      <good>특검은 누구를 위한 절차인가</good>
    </archetype>
  </archetypes>

  <forbidden>어조만 모방한 단정("최고", "혁명적") 금지. 추상 제목("논평", "입장") 금지.</forbidden>
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
  <archetype name="질문형" strength="AEO 최강">
    <!-- 쉼표형·완결형·의문구형을 섞어라. 한 형태만 반복하면 본문 전체가 단조로워진다. -->
    <good form="쉼표형">청년 기본소득, 신청 방법은 무엇인가요?</good>
    <good form="완결형">보육료 지원 한도는 얼마까지 가능한가요?</good>
    <good form="의문구형">{지역} 주차장은 어디에 새로 들어서나</good>
    <correction before="청년 기본소득에 대한 상세한 설명" after="청년 기본소득은 어떻게 신청하나요?"/>
    <correction before="이것을 꼭 알아야 합니다" after="보육료 지원 자격은 어떻게 확인하나"/>
  </archetype>

  <archetype name="목표형" strength="약속·다짐">
    <!-- 명사구·쉼표형·동사종결형을 섞어라. -->
    <good form="명사구형">청년 일자리를 위한 3가지 약속</good>
    <good form="쉼표형">통학로 안전, 이렇게 지키겠습니다</good>
    <good form="명사구형">지역 의료 공백 해소 로드맵</good>
    <good form="동사종결형">청년 주거 문제를 함께 풀어가겠습니다</good>
    <correction before="열심히 노력하겠습니다" after="청년 일자리를 위한 3가지 약속"/>
    <correction before="최선을 다하겠습니다" after="통학로 안전을 이렇게 지키겠습니다"/>
  </archetype>

  <archetype name="주장형" strength="입장 선명화">
    <good>청년 기본소득은 필수다</good>
    <good>지역 격차는 바로잡아야 한다</good>
    <correction before="청년 정책에 대한 입장" after="청년 기본소득은 필수다"/>
    <correction before="지역 격차 문제" after="지역 격차는 바로잡아야 한다"/>
  </archetype>

  <archetype name="이유형" strength="배경·근거">
    <good>청년 기본소득이 필요한 이유</good>
    <good>국비 120억 확보의 배경</good>
    <good>왜 지금 개편이 필요한가</good>
    <correction before="배경 설명" after="청년 기본소득이 필요한 이유"/>
    <correction before="왜 이걸 해야 할까" after="왜 지금 개편이 필요한가"/>
  </archetype>

  <archetype name="대조형" strength="차별화">
    <!-- vs 표기·쉼표형·완결형을 섞어라. 전부 "X vs Y, Z?" 형태면 독자가 피로해진다. -->
    <good form="쉼표형">청년 기본소득 vs 청년 수당, 무엇이 다른가</good>
    <good form="명사구형">2024년 vs 2025년 예산 변화</good>
    <good form="명사구형">기존 정책 대비 개선된 3가지</good>
    <good form="완결형">작년 예산과 올해 예산은 어떻게 달라졌나</good>
    <correction before="비교해 보겠습니다" after="청년 기본소득과 청년수당은 어떻게 다른가"/>
    <correction before="장점과 단점" after="온라인 신청과 오프라인 신청을 비교합니다"/>
  </archetype>

  <archetype name="사례형" strength="증거·현장">
    <good>2025년 상반기 5대 주요 성과</good>
    <good>청년 일자리 274명 창출 현장</good>
    <good>민원 처리 14일→3일 단축 사례</good>
    <correction before="좋은 성과를 냈습니다" after="청년 일자리 274명 창출 현장"/>
    <correction before="개선되었습니다" after="민원 처리 14일→3일 단축 사례"/>
  </archetype>

  <archetype name="서술형" strength="담담한 사태 제시" limit="글당 0~1회">
    <good>지역 경제의 새 판을 열다</good>
    <good>주민 목소리에 귀를 기울이다</good>
    <good>도시 재생이 현장을 바꾸다</good>
    <correction before="열심히 하다" after="지역 경제의 새 판을 열다"/>
    <note>동사 사전형(기본형) 종결. 절제된 톤으로 임팩트를 주지만 남용하면 단조로워진다. 6개 H2 중 0~1개만 사용할 것.</note>
  </archetype>

  <checklist>
    <must>12~25자 범위 (네이버 최적 15~22자)</must>
    <must>핵심 키워드를 앞 1/3에 배치</must>
    <must>7 아키타입 중 하나로 본문이 답할 약속을 던질 것</must>
    <must>H2 바로 아래 첫 문장(40~60자)은 직접 답변</must>
    <must>문장 형태 다양성: 6개 H2 전체에서 쉼표(,)로 두 구를 끊어 잇는 형태(예: "X, Y합니다" / "X, Y인가요?")는 **최대 2개**. 나머지는 완결형 서술문·완결형 질문문·구두점 없는 명사구·동사종결형 등 서로 다른 형태로 분산할 것. 같은 표면형이 3개 이상 반복되면 본문 전체가 단조롭게 보인다.</must>
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
  <archetype name="주장형" strength="입장 선명화">
    <good>특검은 정치 보복이 아니다</good>
    <good>당당하면 피할 이유 없다</good>
    <good>권한 남용은 바로잡아야 한다</good>
    <correction before="특검에 대해 생각해 봅시다" after="특검은 정치 보복이 아니다"/>
    <correction before="이 사안을 어떻게 봐야 할까" after="권한 남용은 바로잡아야 한다"/>
  </archetype>

  <archetype name="이유형" strength="배경·근거">
    <good>권한 남용을 묵인할 수 없는 이유</good>
    <good>왜 진실 규명이 지금 필요한가</good>
    <good>책임 회피가 부른 구조적 한계</good>
    <correction before="여러 논란이 이어지고 있습니다" after="책임 회피가 부른 구조적 한계"/>
    <correction before="배경 정리" after="권한 남용을 묵인할 수 없는 이유"/>
  </archetype>

  <archetype name="질문형" strength="쟁점 제기">
    <good>특검은 누구를 위한 절차인가</good>
    <good>민주주의 질서, 어디까지 지킬 것인가</good>
    <correction before="관련 입장 정리" after="특검은 누구를 위한 절차인가"/>
  </archetype>

  <checklist>
    <must>12~25자 범위 (네이버 최적 15~22자)</must>
    <must>주장·이유·질문 아키타입 중 하나로 쟁점을 명시</must>
    <must>핵심 쟁점을 직접 드러내는 표현 사용</must>
    <ban>"생각해 봅시다", "함께 보시죠" 같은 완곡한 유도문</ban>
    <ban>"정책", "입장", "논평"처럼 내용 없는 추상 제목</ban>
  </checklist>
</h2_examples>
"""


# ---------------------------------------------------------------------------
# H2 Archetype System — "소제목이 약속, 본문이 이행" AEO 구조 (7 아키타입)
# ---------------------------------------------------------------------------
#
# Why: 전통적 표면 분류(명사형/단정형/데이터형…)는 어조/문장 형태만 구분할 뿐
#      소제목이 본문과 맺는 Q/A 계약을 드러내지 못했다. AEO 효과는 "소제목이
#      예고(질문/목표/주장/이유/대조/사례), 본문 첫 문장이 그 예고에 직답"
#      구조에서 나온다. 6 아키타입은 각 소제목이 만드는 '약속의 종류' 를
#      의미 기능 단위로 고정한다.
#
# 탐지 우선순위(먼저 매치된 아키타입 승):
#   질문형 → 대조형 → 사례형 → 목표형 → 이유형 → 주장형
#   (overlap 시 더 구체적인 쪽 우선)

H2_ARCHETYPE_NAMES = ("질문형", "목표형", "주장형", "이유형", "대조형", "사례형", "서술형")

H2_ARCHETYPE_DESCRIPTIONS = {
    "질문형": "본문이 답해야 할 질문을 소제목으로 던진다. PAA·스니펫에 가장 강함.",
    "목표형": "약속/목표/다짐을 소제목으로 선언하고 본문에서 이행 방안을 제시한다.",
    "주장형": "명확한 입장·단정을 소제목으로 던지고 본문에서 근거로 뒷받침한다.",
    "이유형": "왜 그런지/배경이 무엇인지를 소제목으로 예고하고 본문에서 원인을 풀어낸다.",
    "대조형": "두 대상을 맞붙여 비교를 예고하고 본문에서 대비를 전개한다.",
    "사례형": "숫자·실적·현장 데이터를 예고하고 본문에서 증거를 나열한다.",
}

# Regex detectors — heading 1개를 주면 어떤 아키타입인지 판정한다.
#
# 설계: kiwi 형태소 분석이 가능하면 `_detect_archetype_kiwi` 가 1차 판정
# (종결어미 EF 태그 기반). kiwi 불가 환경(Windows 한글 username 등) 에서는
# 아래 regex 가 fallback 으로 동작한다. regex 는 빈출 surface form 위주로
# 확장돼 있으며, 드문 표면형은 kiwi 에 의존한다.

_H2_ARCH_QUESTION_RE = re.compile(
    r"(?:\?$|"
    # "-요/-까" 어말 결합형
    r"[나까]요\??$|인가요?\??$|인가\??$|"
    # 받침 있는 어간 + -을까: 벗을까, 찾을까, 먹을까, 읽을까, 물을까
    r"[가-힣]+을까\??$|"
    # 빈출 ㄹ 받침 용언 어간 + 까 (갈까/올까/볼까/될까/할까/풀까/만들까 등)
    r"[가-힣]*(?:갈|걸|골|굴|길|날|놀|달|돌|들|말|몰|물|밀|발|볼|불|살|설|솔|쓸|"
    r"알|얼|열|올|울|일|잘|절|졸|줄|질|찰|칠|탈|털|팔|풀|할|홀)까\??$|"
    # 의문 종결 복합 어미
    r"는가\??$|는지\??$|을지\??$|"
    # 의문 대명사·부사 (본문 어디에나 존재하면 질문 성격)
    r"어떻게|무엇|언제|어디|어디서|왜)"
)
_H2_ARCH_GOAL_RE = re.compile(
    r"(약속|목표|다짐|하겠|내겠|만들겠|지키겠|추진|실행|계획|비전|로드맵|이행|해내)"
)
_H2_ARCH_CLAIM_RE = re.compile(
    r"("
    # 단정/선언 종결어미 (literal)
    # Note: 독립 "이다$" 제거 — "기울이다"/"줄이다" 등 사동사 오매칭 방지.
    # 긍정 지정사(copula) 패턴은 아니다/뿐이다/마땅하다 + 주장형 키워드로 커버.
    r"아니다$|한다$|된다$|없다$|있다$|"
    r"해야(?:\s?한다)?$|않다$|뿐이다$|마땅하다$|"
    # -는다 (받침 있는 어간 + 는다): 찾는다, 읽는다, 받는다, 짓는다
    r"는다\.?$|"
    # -ㄴ다 (받침 ㄴ + 다) 빈출 음절 enum: 만든다/이끈다/펼친다/나선다/돈다/
    # 간다/온다/준다/탄다/쏜다/튼다/쩐다/찐다/빈다/본다/편다/앞선다
    r"[가-힣]*(?:든|끈|친|선|돈|간|온|준|큰|탄|쏜|튼|찬|빈|편|본)다\.?$|"
    # 과거형 논평조: ~했다/~됐다/~졌다 (피동 포함: 해졌다/높아졌다/바뀌어졌다)
    r"[가-힣]*했다\.?$|[가-힣]*됐다\.?$|[가-힣]*졌다\.?$|"
    # 주장형 어휘 키워드 (종결 무관)
    r"거부|회피|남용|파괴|왜곡|무너|실패|한계|정당|필수|핵심|바로잡)"
)
# 서술형: 동사/형용사 사전형(기본형) 종결 — 열다, 묻다, 잇다, 나서다, 돌아보다
# 주장형(한다/된다/이다 등 단정 패턴)에 매치되지 않은 나머지 "~다" 종결을 포착.
# 우선순위상 주장형 뒤에 위치하므로 단정 패턴이 먼저 잡힌다.
_H2_ARCH_NARRATIVE_RE = re.compile(r"[가-힣]+다\.?$")
_H2_ARCH_REASON_RE = re.compile(
    r"(^왜\s|왜\s[가-힣]|이유|까닭|배경|원인|까닭은|왜냐|때문)"
)
_H2_ARCH_CONTRAST_RE = re.compile(
    r"(vs|VS|대비|차이|비교|맞대결|대결|대조|양자|맞붙)"
)
# 사례형 엄격화: 숫자 단독으로는 매치 안 시킴.
# 숫자 + 이산(countable) 수량 단위 동반 OR 증거 키워드 동반 시에만 사례형.
# Why: 기존 `\d` 는 "RE100" 의 100, "4년간" 의 4 만 보고도 사례형 판정 →
# 주장형·목표형이 사례형에 삼켜졌다. AEO 사례형은 "숫자·실적·현장 데이터"
# 라는 증거 예고 성격이므로, 실제 **갯수/비율/금액** 컨텍스트를 요구한다.
#
# 제외 (의도적): 년/년간/개월/달/일/주/시간/분/초 같은 **기간** 단위.
# "지난 4년간 조성" / "3개월 동안" 은 단순 서사 배경이지 증거 예고가 아니다.
# 진짜 기간형 evidence 는 대부분 증거 키워드(실적/성과/기록) 를 동반하므로
# 그쪽 분기에서 커버된다.
_H2_ARCH_EVIDENCE_RE = re.compile(
    r"(?:"
    # 숫자 + 이산 수량 단위 (기존 유지)
    r"\d+\s*(?:건|명|회|차례|차|대|개|곳|"
    r"%|퍼센트|억|만|천|원|조|달러|배|위|등|명당|건당|인|명분)|"
    # 강한 증거 키워드 (무조건 사례형)
    r"현장|사례|실적|성과|통계|데이터|실태|현황|내역|명단|집계|기록|"
    # 약한 키워드(분석/결과): 숫자 동반 필수 — "설문 결과를 정책에 반영" 오매칭 방지
    r"\d[^가-힣]*(?:분석|결과)|(?:분석|결과)[^가-힣]*\d|"
    r"확보\s*\d|체결\s*\d"
    r")"
)

_H2_ARCHETYPE_DETECTORS = (
    ("질문형", _H2_ARCH_QUESTION_RE),
    ("대조형", _H2_ARCH_CONTRAST_RE),
    ("사례형", _H2_ARCH_EVIDENCE_RE),
    ("목표형", _H2_ARCH_GOAL_RE),
    ("이유형", _H2_ARCH_REASON_RE),
    ("주장형", _H2_ARCH_CLAIM_RE),
    ("서술형", _H2_ARCH_NARRATIVE_RE),
)


def _detect_archetype_kiwi(text: str) -> "str | None":
    """Kiwi 형태소 분석 기반 아키타입 판정. None 이면 kiwi 불가 → regex fallback.

    우선순위(regex 와 동일): 질문형 > 대조형 > 사례형 > 목표형 > 이유형 > 주장형.

    - 질문형: `is_question_form` True (EF ∈ _QUESTION_EF_FORMS 또는 `?` 종결)
    - 대조형/이유형: surface keyword (kiwi 개입 없음, regex 와 동일)
    - 사례형: 엄격화된 evidence regex
    - 목표형: goal keyword 또는 commitment EF
    - 주장형: declarative EF 또는 claim keyword
    """
    plain = str(text or "").strip()
    if not plain:
        return None

    # 1. 질문형 — kiwi EF 판정 (kiwi 불가 시 None 반환 → fallback)
    qf = korean_morph.is_question_form(plain)
    if qf is None:
        return None
    if qf:
        return "질문형"

    # 2. 대조형 — surface keyword
    if _H2_ARCH_CONTRAST_RE.search(plain):
        return "대조형"

    # 3. 사례형 — 엄격화된 evidence regex
    if _H2_ARCH_EVIDENCE_RE.search(plain):
        return "사례형"

    # 이후 분기에서 EF class 를 재사용
    cls = korean_morph.classify_title_ending(plain)
    cls_class = (cls or {}).get("class", "")

    # 4. 목표형 — surface keyword OR commitment EF
    if _H2_ARCH_GOAL_RE.search(plain):
        return "목표형"
    if cls_class == "commitment":
        return "목표형"

    # 5. 이유형 — surface keyword
    if _H2_ARCH_REASON_RE.search(plain):
        return "이유형"

    # 6. 주장형 — claim regex (surface) 먼저 체크
    if _H2_ARCH_CLAIM_RE.search(plain):
        return "주장형"

    # 7. 서술형 — declarative EF 이지만 주장형 claim 패턴이 아닌 사전형 종결
    #    (열다, 묻다, 잇다, 나서다 등)
    if cls_class == "declarative":
        return "서술형"
    if _H2_ARCH_NARRATIVE_RE.search(plain):
        return "서술형"

    return ""


def detect_h2_archetype(heading: str) -> str:
    """단일 heading 이 어느 아키타입에 해당하는지 판정한다.

    우선순위: 질문형 > 대조형 > 사례형 > 목표형 > 이유형 > 주장형.
    하나도 매치되지 않으면 빈 문자열("").

    kiwi 사용 가능: 형태소 분석(EF 태그) 기반 우선 판정. 종결어미 다양성을
    정확히 커버한다 ("벗을까"/"만든다" 등).
    kiwi 불가: regex fallback — 빈출 surface form 를 enum 으로 매칭.
    """
    text = re.sub(r"\s+", " ", str(heading or "")).strip()
    if not text:
        return ""

    # Kiwi 우선
    kiwi_result = _detect_archetype_kiwi(text)
    if kiwi_result is not None:
        return kiwi_result

    # Regex fallback
    for name, pattern in _H2_ARCHETYPE_DETECTORS:
        if pattern.search(text):
            return name
    return ""


def is_h2_archetype(heading: str, archetype: str) -> bool:
    """heading 이 특정 아키타입 패턴에 해당하는지 검사(우선순위 무시).

    kiwi 가능 시 kiwi 1차 판정이 target 과 일치하면 True.
    kiwi 불가 또는 kiwi 가 빈 문자열을 반환(아키타입 미매치) 하면 regex 폴백.
    """
    text = re.sub(r"\s+", " ", str(heading or "")).strip()
    target = str(archetype or "").strip()
    if not text or not target:
        return False

    kiwi_result = _detect_archetype_kiwi(text)
    if kiwi_result is not None and kiwi_result != "":
        # kiwi 가 구체 아키타입을 반환 → 그 결과를 우선 신뢰
        if kiwi_result == target:
            return True
        # 다른 아키타입이 매치됐다면, target 도 동시에 매치될 수 있는지
        # regex 로 재확인 (우선순위 무시). 예: "~만든다" 는 주장형이지만
        # target="주장형" 체크 시 True 가 돼야 함.
        for name, pattern in _H2_ARCHETYPE_DETECTORS:
            if name == target:
                return bool(pattern.search(text))
        return False

    # kiwi 불가 또는 kiwi 미매치 → 순수 regex
    for name, pattern in _H2_ARCHETYPE_DETECTORS:
        if name == target:
            return bool(pattern.search(text))
    return False


# ---------------------------------------------------------------------------
# Category → Archetype Map
# ---------------------------------------------------------------------------
#
# 각 카테고리는 주 아키타입 2~4개 + 보조 0~2개. LLM 은 이 안에서만 선택한다.
# 오버라이드:
#   - 기념/추념/성찰 주제: 주장형·이유형만 허용 (보조 없음)
#   - 여론조사 매치업: 질문형·대조형 주, 사례형 보조

CATEGORY_ARCHETYPE_MAP = {
    "current-affairs": {"primary": ["질문형", "주장형", "이유형"], "auxiliary": ["대조형", "사례형", "서술형"]},
    "policy-proposal": {"primary": ["질문형", "목표형", "주장형", "이유형"], "auxiliary": ["사례형", "서술형"]},
    "activity-report": {"primary": ["목표형", "이유형"], "auxiliary": ["사례형", "서술형"]},
    "daily-communication": {"primary": ["질문형", "이유형"], "auxiliary": ["사례형", "서술형"]},
    "local-issues": {"primary": ["질문형", "목표형", "주장형", "이유형"], "auxiliary": ["사례형", "서술형"]},
    "educational-content": {"primary": ["질문형", "이유형"], "auxiliary": ["대조형", "사례형", "서술형"]},
    "default": {"primary": ["질문형", "주장형", "이유형"], "auxiliary": ["대조형", "사례형", "서술형"]},
}

_COMMEMORATIVE_ARCHETYPES = {"primary": ["주장형", "이유형"], "auxiliary": []}
_MATCHUP_ARCHETYPES = {"primary": ["질문형", "대조형"], "auxiliary": ["사례형"]}


def resolve_category_archetypes(
    category: str,
    *,
    commemorative: bool = False,
    matchup: bool = False,
) -> Dict[str, List[str]]:
    """카테고리 + 주제 플래그로 허용 아키타입 풀(primary, auxiliary)을 결정한다.

    우선순위: 매치업 > 기념/성찰 > 카테고리 기본.
    """
    if matchup:
        return {
            "primary": list(_MATCHUP_ARCHETYPES["primary"]),
            "auxiliary": list(_MATCHUP_ARCHETYPES["auxiliary"]),
        }
    if commemorative:
        return {
            "primary": list(_COMMEMORATIVE_ARCHETYPES["primary"]),
            "auxiliary": list(_COMMEMORATIVE_ARCHETYPES["auxiliary"]),
        }
    key = str(category or "").strip()
    pool = CATEGORY_ARCHETYPE_MAP.get(key) or CATEGORY_ARCHETYPE_MAP["default"]
    return {"primary": list(pool["primary"]), "auxiliary": list(pool["auxiliary"])}


# ---------------------------------------------------------------------------
# Category Tone Anchor — SUBHEADING_STYLES.examples 흡수 (카테고리별 톤 예시)
# ---------------------------------------------------------------------------
CATEGORY_TONE_EXAMPLES = {
    'current-affairs': {
        'style': 'assertive',
        'description': '시사 비평은 주장·이유·질문 아키타입을 사용합니다.',
        'examples': [
            '특검은 정치 보복이 아니다',
            '왜 진실 규명이 지금 필요한가',
            '권한 남용을 묵인할 수 없는 이유',
            '당당하면 피할 이유 없다',
        ],
    },
    'policy-proposal': {
        'style': 'aeo',
        'description': '정책 제안은 질문·목표·주장·이유 아키타입을 사용합니다.',
        'examples': [
            '청년 기본소득, 어떻게 신청하나요?',
            '청년 일자리를 위한 3대 약속',
            '교통 체계 개편이 필요한 이유',
            '국비 100억 확보의 배경',
        ],
    },
    'activity-report': {
        'style': 'aeo',
        'description': '의정 활동 보고는 목표·이유 아키타입을 사용합니다.',
        'examples': [
            '국정감사에서 지켜낸 3가지 약속',
            '발의 법안의 추진 배경',
            '지역 현안 해결을 위한 다음 단계',
        ],
    },
    'daily-communication': {
        'style': 'aeo',
        'description': '일상 소통은 질문·이유 아키타입을 사용합니다.',
        'examples': [
            '요즘 시민들께 가장 많이 듣는 말은?',
            '이 약속을 다시 새기는 이유',
            '현장에서 만난 목소리, 무엇을 배웠나',
        ],
    },
    'local-issues': {
        'style': 'aeo',
        'description': '지역 현안은 질문·목표·주장·이유 아키타입을 사용합니다.',
        'examples': [
            '주차난, 가장 시급한 해법은?',
            '통학로 안전을 위한 3가지 약속',
            '예산 재배분이 필요한 이유',
        ],
    },
    'educational-content': {
        'style': 'aeo',
        'description': '교육/설명 콘텐츠는 질문·이유 아키타입을 사용합니다.',
        'examples': [
            '이 제도, 무엇이 달라졌나요?',
            '규정 개정의 핵심 배경',
            '기존 제도 vs 개정안, 무엇이 다른가',
        ],
    },
    'default': {
        'style': 'aeo',
        'description': '기본 AEO 최적화 스타일 — 질문·주장·이유 아키타입을 사용합니다.',
        'examples': [],
    },
}


def get_category_tone(category: str) -> dict:
    """카테고리별 톤 앵커(description/preferred_types/examples/style)를 반환한다."""
    key = str(category or '').strip()
    if key in CATEGORY_TONE_EXAMPLES:
        return CATEGORY_TONE_EXAMPLES[key]
    return CATEGORY_TONE_EXAMPLES['default']


def build_category_tone_block(
    category: str,
    *,
    commemorative: bool = False,
    matchup: bool = False,
) -> str:
    """카테고리별 톤 예시를 프롬프트용 XML 블록으로 반환한다.

    h2_guide의 일반 few-shot과 별도로, 카테고리마다 고유한 어조 앵커를 제공한다.
    주 아키타입/보조 아키타입 목록을 함께 노출해 LLM 이 어떤 '약속의 종류' 안에서
    선택해야 하는지 명시한다. 예시 목록이 비어 있는 카테고리(default)에도 아키타입
    정보는 내보낸다.
    """
    tone = get_category_tone(category)
    pool = resolve_category_archetypes(
        category, commemorative=commemorative, matchup=matchup
    )
    primary = pool["primary"]
    auxiliary = pool["auxiliary"]
    examples = [str(item).strip() for item in (tone.get('examples') or []) if str(item).strip()]

    style = normalize_h2_style(tone.get('style'))
    description = str(tone.get('description') or '').strip()

    lines = [
        f'<h2_category_tone category="{category}" style="{style}">',
    ]
    if description:
        lines.append(f'  <description>{description}</description>')
    if primary:
        joined = ', '.join(primary)
        lines.append(f'  <primary_archetypes>{joined}</primary_archetypes>')
    if auxiliary:
        joined = ', '.join(auxiliary)
        lines.append(f'  <auxiliary_archetypes>{joined}</auxiliary_archetypes>')
    for archetype in primary + auxiliary:
        desc = H2_ARCHETYPE_DESCRIPTIONS.get(archetype, '')
        if desc:
            lines.append(f'  <archetype name="{archetype}">{desc}</archetype>')
    for example in examples:
        safe = example.replace('<', '&lt;').replace('>', '&gt;')
        lines.append(f'  <good>{safe}</good>')
    lines.append('</h2_category_tone>')
    return '\n'.join(lines)
