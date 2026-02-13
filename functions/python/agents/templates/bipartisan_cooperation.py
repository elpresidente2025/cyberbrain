from dataclasses import dataclass
from typing import List, Dict, Optional
import re

@dataclass
class ToneLevel:
    id: str
    name: str
    when: str
    tone: str
    template: str
    caution: str = ""
    connection: str = ""
    required: str = ""
    structure: str = ""

@dataclass
class GenerationTemplate:
    id: str
    name: str
    structure: str
    example: str

TONE_LEVELS = {
    "LEVEL_1_OBJECTIVE": ToneLevel(
        id='objective_acknowledgment',
        name='1단계: 객관적 인정 (가장 안전)',
        when='팩트만 전달할 때',
        tone='감정 배제, 절제됨',
        template='○○ 의원이 제시한 [구체적 내용]의 문제 지적은 근거가 있다.',
        caution='감탄·칭찬 톤 최소화'
    ),
    "LEVEL_2_SPECIFIC": ToneLevel(
        id='specific_acknowledgment',
        name='2단계: 구체적 인정 (권장)',
        when='특정 행동·성과를 긍정할 때',
        tone='구체적 근거 + 범위 한정',
        template='[구체적 행동]을 보여준 ○○ 의원의 노력만큼은 진심으로 인정할 수 있다.',
        connection='+ 이런 부분은 여야가 함께 배워야 한다'
    ),
    "LEVEL_3_POLITE": ToneLevel(
        id='polite_with_difference',
        name='3단계: 정중한 인정 + 차이 명시',
        when='의견은 다르지만 인물·과정은 인정할 때',
        structure='차이 먼저 → 구체적 인정 → 인격 존중',
        tone='차이 먼저 → 구체적 인정 → 인격 존중', # Using structure as tone for consistency if needed
        template='정책 방향은 다르지만, ○○ 의원의 [구체적 행동]은 바람직하다고 본다.'
    ),
    "LEVEL_4_LIMITED_COOPERATION": ToneLevel(
        id='limited_cooperation',
        name='4단계: 한정적 협력 제안',
        when='공동 이익이 있을 때만',
        required='협력 범위를 명확히 한정',
        tone='협력 범위를 명확히 한정', # Using required as tone
        template='[특정 사안]만큼은 여야가 함께 논의할 가치가 있다.',
        caution='"정책 기조의 차이는 남아 있다" 명시 필수'
    )
}

GENERATION_TEMPLATES = {
    "POLICY_ACHIEVEMENT": GenerationTemplate(
        id='policy_achievement',
        name='정책 성과 인정',
        structure="""[차이 인정] 정책 방향은 다를 수 있지만,
[구체적 근거] ○○ 의원이 [구체적 행동/성과]
[존중 표현] 점은 높이 평가한다.
[초당 연결] 이런 부분은 여야가 함께 배워야 한다.""",
        example='정책 방향은 다를 수 있지만, ○○ 의원이 일 년간 중소상인들을 직접 방문해 현황을 청취하는 모습은 진심으로 인정할 수 있습니다. 이런 현장 중심의 의정활동은 여야가 함께 배워야 한다고 봅니다.'
    ),
    "CRISIS_RESPONSE": GenerationTemplate(
        id='crisis_response',
        name='위기 대응/인물 인정',
        structure="""[상황] 이번 [사건]에서
[인물 행동] ○○ 시장의 [구체적 행동]은
[절제된 인정] 시민 안전을 우선한 선택이다.
[협력 제안] 이런 부분에서는 정파를 넘어 함께 움직일 가치가 있다.""",
        example='이번 재난 대응에서 ○○ 시장이 신속하게 현장에 나가 여야 구분 없이 피해자를 챙긴 모습은 시민 안전을 우선한 선택이라고 봅니다. 이런 순간에는 정파를 넘어 함께 움직여야 한다고 생각합니다.'
    ),
    "LIMITED_COOPERATION": GenerationTemplate(
        id='limited_cooperation',
        name='한정적 협력 제안',
        structure="""[입장 차이] ○○ 의원과는 [쟁점]에서 입장이 다르지만,
[공동 이익] [국익/민생/안보]에서는
[협력 범위] 이 부분만큼은 함께 논의할 가치가 있다.
[한계 명시] 정책 기조의 차이는 남아 있다.""",
        example='재정 정책에서는 입장이 다르지만, 국가 채무 투명성 강화 차원에서는 ○○ 의원의 제안을 함께 검토할 가치가 있다고 봅니다. 정책 시행 방식에서는 여전히 입장 차이가 있습니다.'
    ),
    "PRINCIPLED_STANCE": GenerationTemplate(
        id='principled_stance',
        name='소신 발언 인정',
        structure="""[상황] 이번 [사안]에서
[인물 행동] ○○ 의원이 [소신 발언/행동]한 점은
[범위 한정] 이 부분만큼은 높이 평가한다.
[자기 PR] 저 또한 이러한 원칙 위에서 [화자의 비전/정책]을 추진한다.""",
        example='이번 헌정 위기 상황에서 조경태 의원이 당을 넘어 원칙을 지킨 점은 높이 평가합니다. 저 또한 이러한 원칙 위에서 부산의 미래를 위한 정책을 추진하겠습니다.'
    )
}

KOREAN_POLITICAL_CONTEXT = """
<korean_political_context description="한국 정치 문화의 특수성 - LLM 생성 시 반드시 반영">
  <factor order="1">팬덤 정치의 강력함: 과한 인물 띄우기는 정치적 실수로 읽힌다.</factor>
  <factor order="2">강성 지지층의 민감도: 자당 폄하는 배신으로 해석될 수 있다.</factor>
  <factor order="3">초당적 협력의 실질성: 추상적 함께하자보다 구체적 사안 제시가 중요하다.</factor>
  <factor order="4">현장 중심 평가: 무엇을 했는가가 얼마나 훌륭한가보다 더 설득력 있다.</factor>
  <factor order="5">상위 정체성 활용: 지역에는 여야가 없다, 국가 이익 우선 같은 프레임을 활용할 수 있다.</factor>
</korean_political_context>
""".strip()

def build_bipartisan_cooperation_prompt(options: dict = None) -> str:
    options = options or {}
    
    defaults = {
        'topic': '',
        'targetCount': 1800,
        'authorBio': '이재성',
        'instructions': '',
        'newsContext': '',
        'templateId': 'principled_stance',
        'toneLevel': 'LEVEL_2_SPECIFIC',
        'personalizedHints': ''
    }
    
    # Merge defaults
    merged_options = {**defaults, **options}
    
    topic = merged_options['topic']
    target_count = merged_options['targetCount']
    author_bio = merged_options['authorBio']
    instructions = merged_options['instructions']
    news_context = merged_options['newsContext']
    template_id = merged_options['templateId']
    tone_level = merged_options['toneLevel']
    personalized_hints = merged_options['personalizedHints']

    # Validation
    valid_target_count = target_count if 500 <= target_count <= 5000 else 1800

    template_key = template_id.upper()
    template = GENERATION_TEMPLATES.get(template_key, GENERATION_TEMPLATES['PRINCIPLED_STANCE'])

    tone_key = tone_level.upper()
    tone = TONE_LEVELS.get(tone_key, TONE_LEVELS['LEVEL_2_SPECIFIC'])

    comp_praise_chars = round(valid_target_count * 0.2)
    self_pr_chars = round(valid_target_count * 0.5)
    situation_chars = round(valid_target_count * 0.15)
    conclusion_chars = round(valid_target_count * 0.2)
    instructions_section = f"<background_instructions>{instructions}</background_instructions>" if instructions else ""
    personalized_hints_section = (
        f"<self_pr_source priority=\"critical\">{personalized_hints}</self_pr_source>" if personalized_hints else ""
    )
    news_context_section = f"<reference_news>{news_context[:500]}...</reference_news>" if news_context else ""
    tone_caution_section = f"<caution>{tone.caution}</caution>" if tone.caution else ""
    tone_connection_section = f"<connection>{tone.connection}</connection>" if tone.connection else ""

    prompt = f"""
<task type="초당적 협력 원고" system="전자두뇌비서관">

  <priority_ratio_guard priority="critical" description="경쟁자 칭찬 비중 10-20% 제한">
    <rule>경쟁자(조경태 등) 언급은 최대 {comp_praise_chars}자(20%)</rule>
    <rule>자기PR은 최소 {self_pr_chars}자(50%) 이상</rule>
    <rule type="must-not">경쟁자 칭찬 비중 초과 또는 자기PR 비중 부족 시 원고 폐기</rule>
  </priority_ratio_guard>

{KOREAN_POLITICAL_CONTEXT}

  <forbidden_replacement_guide priority="critical" description="금지 표현과 대체 표현">
    <pair><forbidden>전적으로 동의한다</forbidden><replacement>이 부분만큼은 인정할 수 있다</replacement></pair>
    <pair><forbidden>전적으로 공감한다</forbidden><replacement>이번 사안에 한해 공감한다</replacement></pair>
    <pair><forbidden>본받아야 한다</forbidden><replacement>이 점은 참고할 수 있다</replacement></pair>
    <pair><forbidden>깊이 공감한다</forbidden><replacement>이번 발언은 주목할 만하다</replacement></pair>
    <pair><forbidden>깊은 울림</forbidden><replacement>주목할 만한 발언</replacement></pair>
    <pair><forbidden>용기에 박수</forbidden><replacement>원칙을 지킨 점은 인정</replacement></pair>
    <pair><forbidden>귀감이 됩니다</forbidden><replacement>참고할 만합니다</replacement></pair>
    <pair><forbidden>동력이 될 것</forbidden><replacement>긍정적 계기</replacement></pair>
    <pair><forbidden>나침반이 될 것</forbidden><replacement>방향 제시</replacement></pair>
    <pair><forbidden>충격적인 소식</forbidden><replacement>주목할 만한 소식</replacement></pair>
    <pair><forbidden>마음이 무겁다</forbidden><replacement>엄중하게 받아들인다</replacement></pair>
    <pair><forbidden>안타깝다</forbidden><replacement>유감스럽다</replacement></pair>
  </forbidden_replacement_guide>

  <logic_guide priority="critical" subject="윤석열 사태 관련 논리 구조">
    <rule id="causality">
      <must-not>"사형 구형 소식이 충격적이다/민주주의 위기다" (구형을 비판하는 것처럼 읽힘)</must-not>
      <must>"12.3 내란(범죄)이 민주주의 위기였으며, 사형 구형(심판)은 정의의 실현이다."</must>
    </rule>
    <rule id="emotion_control">"안타깝다", "마음이 무겁다", "충격" 같은 표현은 피해자 코스프레로 오해될 수 있으므로 사용 금지. "사필귀정", "엄정한 법의 심판", "당연한 귀결"로만 표현.</rule>
    <rule id="term_consistency">"전 대통령" 호칭은 유지하되, 예우나 동정 수식어는 제거.</rule>
  </logic_guide>

  <core_principles>
    <principle order="1">차이 먼저 명시하고 인물은 분리: 정책 방향은 달라도 인격·행동·노력은 존중.</principle>
    <principle order="2">구체성 필수, 추상 극찬 금지: "정말 훌륭하다"보다 "○○를 지속적으로 제기해 온 점".</principle>
    <principle order="3">칭찬 후 바로 초당적 공동목표(민생, 안보, 국익)로 연결.</principle>
  </core_principles>

  <tone_profile>
    <current_level>{tone.name}</current_level>
    <when_to_use>{tone.when}</when_to_use>
    <tone_characteristic>{tone.tone}</tone_characteristic>
    <template_sentence>{tone.template}</template_sentence>
{tone_caution_section}
{tone_connection_section}
  </tone_profile>

  <forbidden_expression_levels priority="critical" description="5단계 금지 표현">
    <level><type>자진영 폄하</type><expression>"우리보다 낫다", "우리는 저렇게 못한다"</expression><reason>지지층 배신 신호</reason></level>
    <level><type>전면적 동의</type><expression>"전적으로 동의/공감", "정책이 100% 맞다"</expression><reason>입장 혼선</reason></level>
    <level><type>과장 극찬</type><expression>"정치인 중 최고", "유일하게 믿을 수 있다"</expression><reason>팬덤 자극</reason></level>
    <level><type>추상 극찬</type><expression>"정신을 이어받아", "본받아", "귀감"</expression><reason>구체성 없음</reason></level>
    <level><type>감정 과잉</type><expression>"깊이 공감", "동력", "나침반", "큰 울림"</expression><reason>과도한 감정</reason></level>
  </forbidden_expression_levels>

  <generation_template name="{template.name}">
    <template_structure>
{template.structure}
    </template_structure>
    <template_example>{template.example}</template_example>
  </generation_template>

  <example_comparison>
    <good_example description="경쟁자 인정 150자, 10%">
이번 헌정 위기에서 조경태 의원이 당을 넘어 원칙을 지킨 점만큼은 인정합니다.
저 또한 이러한 원칙 위에서 부산의 미래를 위한 AI 정책을 추진하겠습니다.
    </good_example>
    <good_example_note>이후 자기PR 900자(50%) 필수</good_example_note>
    <bad_example description="경쟁자 칭찬 800자, 74% - 폐기 대상">
조경태 의원의 용기에 깊이 공감합니다... 본받아야 합니다...
전적으로 동의합니다... 동력이 될 것입니다...
    </bad_example>
    <bad_example_note>자기PR 300자(25%) 부족으로 폐기</bad_example_note>
  </example_comparison>

  <input_info>
    <topic>{topic}</topic>
    <target_length unit="자">{valid_target_count}</target_length>
    <speaker>{author_bio}</speaker>
{instructions_section}
{personalized_hints_section}
{news_context_section}
  </input_info>

  <ratio_allocation_guide description="{valid_target_count}자 기준" priority="critical">
    <section><name>상황 설명</name><ratio>15%</ratio><length>약 {situation_chars}자</length></section>
    <section><name>경쟁자 인정</name><ratio>10-20%</ratio><length>최대 {comp_praise_chars}자</length></section>
    <section><name>자기PR/비전</name><ratio>50% 이상</ratio><length>최소 {self_pr_chars}자</length></section>
    <section><name>차별화/마무리</name><ratio>15-25%</ratio><length>약 {conclusion_chars}자</length></section>
    <rule type="must-not">경쟁자 칭찬이 20% 초과 또는 자기PR이 50% 미만이면 원고 폐기</rule>
  </ratio_allocation_guide>

  <writing_sequence priority="critical" description="작성 순서">
    <step order="1">자기PR ({self_pr_chars}자, 50%) - 가장 먼저, 가장 많이</step>
    <step order="2">상황 설명 (15%)</step>
    <step order="3">차별화/마무리 (15-25%)</step>
    <step order="4">경쟁자 인정 (10-20%, 최대 {comp_praise_chars}자) - 마지막에 짧게</step>
  </writing_sequence>

  <output_requirements>
    <format>HTML</format>
    <rule>본문은 p 태그로 문단을 구성할 것</rule>
  </output_requirements>

</task>
"""
    return prompt.strip()
