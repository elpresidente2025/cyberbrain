from dataclasses import dataclass
from ..common.editorial import get_active_strategies
from ..common.election_rules import get_election_stage

@dataclass
class PromptOption:
    id: str
    name: str
    instruction: str = ""
    thematic_guidance: str = ""

LOGICAL_STRUCTURES = {
    "STEP_BY_STEP": PromptOption(id='step_by_step', name='단계적 논증 구조', instruction="글을 '문제 제시 → 근거/원인 분석 → 명료한 결론'의 3단계로 명확하게 구성하세요. 각 단계가 논리적으로 연결되어 독자가 자연스럽게 결론에 도달하도록 이끌어야 합니다."),
    "ENUMERATIVE": PromptOption(id='enumerative', name='열거식 병렬 구조', instruction="하나의 핵심 주장을 뒷받침하는 여러 근거나 문제점을 '첫째, 둘째, 셋째...' 또는 글머리 기호 방식으로 조목조목 나열하세요. 다양한 각도에서 주장을 증명하여 논리의 깊이를 더해야 합니다."),
    "PROBLEM_SOLUTION": PromptOption(id='problem_solution', name='문제 해결형 구조', instruction="먼저 시급히 해결해야 할 문제를 명확히 제시하고, 이에 대한 구체적인 해결책을 제안한 뒤, 마지막으로 독자나 특정 대상의 행동(예: 동참, 시정)을 강력하게 촉구하는 흐름으로 글을 구성하세요."),
    "CLIMACTIC_SANDWICH": PromptOption(id='climactic_sandwich', name='두괄식/양괄식 구조', instruction="글의 가장 중요한 핵심 주장이나 결론을 첫 문단(두괄식) 또는 첫 문단과 마지막 문단(양괄식)에 배치하여 메시지를 강력하게 각인시키세요. 본문은 그 주장에 대한 부연 설명으로 채워야 합니다."),
    "COMPREHENSIVE": PromptOption(id='comprehensive', name='포괄적 구성', instruction="하나의 중심 주제를 설정하고, 관련된 다양한 각도의 논거, 통계, 국내외 사례, 현장 목소리 등을 풍부하게 제시하여 전체 그림을 보여주세요. 서론에서 제기한 문제를 결론에서 다시 한번 환기하며 깊이 있는 설득을 이끌어냅니다."),
    "PRINCIPLE_BASED": PromptOption(id='principle_based', name='원칙 기반 논증', instruction="법률적, 철학적, 혹은 헌법적 '원칙'을 먼저 제시하고, 현재의 사안이 그 원칙에 어떻게 부합하는지를 논증하세요. 과거의 유사 사례를 유추(analogy)하여 주장의 정당성을 강화하는 방식을 사용합니다.")
}

ARGUMENTATION_TACTICS = {
    "EVIDENCE_CITATION": PromptOption(id='evidence_citation', name='사례 및 데이터 인용', instruction="당신의 주장을 뒷받침할 수 있는 구체적인 통계, 연구 결과, 실제 사례, 전문가 의견 등을 풍부하게 인용하여 글의 객관성과 신뢰도를 높여야 합니다."),
    "ANALOGY": PromptOption(id='analogy', name='유추 기반 논증', instruction="과거의 유사한 역사적 사례나 다른 영역의 원칙을 끌어와 현재의 문제에 적용(유추)하여 주장의 정당성을 확보하세요. 독자가 익숙한 사례를 통해 새로운 문제를 쉽게 이해하도록 돕습니다."),
    "BENEFIT_EMPHASIS": PromptOption(id='benefit_emphasis', name='기대효과 강조', instruction="정책이 시행되었을 때 국민들의 삶이 어떻게 긍정적으로 변화하는지를 구체적인 예시와 함께 생생하게 묘사하세요. '만약 ~된다면, 우리 아이들은...'과 같이 미래의 긍정적 모습을 그려주어 설득력을 높입니다.")
}

VOCABULARY_MODULES = {
    "POLICY_ANALYSIS": PromptOption(id='policy_analysis', name='정책 분석 어휘', thematic_guidance="객관적이고 신뢰감 있는 정책 전문가의 톤을 유지하세요. '통계에 따르면', '장기적인 관점에서', '체계적인 접근', '합리적인 대안' 등 분석적이고 전문적인 어휘를 사용해야 합니다."),
    "RATIONAL_PERSUASION": PromptOption(id='rational_persuasion', name='합리적 설득 어휘', thematic_guidance="독자를 가르치려 하지 말고, 차분하고 논리적인 어조로 설득하세요. '함께 고민해볼 문제입니다', '우리가 주목해야 할 부분은', '더 나은 방향은' 등 합리적이고 균형 잡힌 어휘를 사용하세요."),
    "VISION_AND_HOPE": PromptOption(id='vision_and_hope', name='비전과 희망 어휘', thematic_guidance="미래에 대한 긍정적인 비전과 희망을 담은 어휘를 사용하세요. '새로운 미래를 열겠습니다', '희망의 씨앗을 심겠습니다', '함께 꿈꾸는 대한민국' 등 진취적이고 포용적인 표현을 사용합니다."),
    "ACTION_URGING": PromptOption(id='action_urging', name='행동 촉구 어휘', thematic_guidance="강력하고 호소력 있는 어조로 독자들의 행동과 참여를 유도하세요. '지금 바로 행동해야 합니다', '여러분의 힘이 필요합니다', '함께 바꿔나갑시다' 등 동기를 부여하는 어휘를 사용하세요.")
}

def build_policy_proposal_prompt(options: dict) -> str:
    topic = options.get('topic', '')
    author_bio = options.get('authorBio', '')
    author_name = options.get('authorName', '')
    instructions = options.get('instructions', '')
    keywords = options.get('keywords', [])
    target_word_count = options.get('targetWordCount', 2000)
    personalized_hints = options.get('personalizedHints', '')
    logical_structure_id = options.get('logicalStructureId')
    argumentation_tactic_id = options.get('argumentationTacticId')
    vocabulary_module_id = options.get('vocabularyModuleId')
    current_status = options.get('currentStatus', '')
    user_profile = options.get('userProfile', {})

    speaker_name = author_name if author_name else '화자'

    # Rhetorical strategy
    rhetorical_strategy = get_active_strategies(topic, instructions, user_profile)
    
    # Election compliance
    election_stage = get_election_stage(current_status)
    election_compliance_section = ""
    if election_stage and election_stage.get('promptInstruction'):
        election_compliance_section = f"""
<election_compliance priority="critical" description="선거법 준수 필수 - 위반 시 법적 책임 발생">
{election_stage['promptInstruction']}
</election_compliance>
"""

    # Select components with defaults
    logical_structure = next((v for v in LOGICAL_STRUCTURES.values() if v.id == logical_structure_id), LOGICAL_STRUCTURES["STEP_BY_STEP"])
    argumentation_tactic = next((v for v in ARGUMENTATION_TACTICS.values() if v.id == argumentation_tactic_id), ARGUMENTATION_TACTICS["EVIDENCE_CITATION"])
    vocabulary_module = next((v for v in VOCABULARY_MODULES.values() if v.id == vocabulary_module_id), VOCABULARY_MODULES["RATIONAL_PERSUASION"])

    keywords_section = ""
    if keywords:
        keywords_str = ", ".join(keywords)
        keywords_section = f"""
<context_keywords usage="참고용 - 삽입 강제 아님">
{keywords_str}
이 키워드들을 참고하여 글의 방향과 맥락을 잡으세요. 억지로 삽입할 필요 없습니다.
</context_keywords>
"""

    hints_section = ""
    if personalized_hints:
        hints_section = f"""
<personalization_guide>
{personalized_hints}
</personalization_guide>
"""

    rhetorical_section = ""
    if rhetorical_strategy['promptInjection']:
        rhetorical_section = f"""
<rhetorical_strategy description="설득력 강화">
{rhetorical_strategy['promptInjection']}
</rhetorical_strategy>
"""

    prompt = f"""
<task type="논리적 글쓰기 (정책/비전)" system="전자두뇌비서관">

{election_compliance_section}
<speaker_identity priority="critical" description="화자 정체성 - 절대 혼동 금지">
  <declaration>당신은 "{author_bio}"입니다. 이 글의 유일한 1인칭 화자입니다.</declaration>
  <rule>이 글은 철저히 1인칭 시점으로 작성합니다. "저는", "제가"를 사용하세요.</rule>
  <rule priority="critical" description="본인 이름 사용 제한">"{speaker_name}"이라는 이름은 서론에서 1회, 결론에서 1회만 사용하세요.
    <item type="must-not">"{speaker_name}은 약속합니다", "{speaker_name}은 노력하겠습니다" (본문에서 반복)</item>
    <item type="must">"저 {speaker_name}은 약속드립니다" (서론/결론에서 1회씩만)</item>
    <item type="must">본문에서는 "저는", "제가", "본 의원은" 등 대명사 사용</item>
  </rule>
  <rule>참고 자료에 등장하는 다른 정치인은 관찰과 평가의 대상(3인칭)입니다.
    <item type="must-not">"조경태는 최선을 다할 것입니다." (작성자가 대변인이 아님)</item>
    <item type="must">"조경태 의원의 소신에 박수를 보냅니다." (작성자가 평가함)</item>
  </rule>
  <rule>절대 다른 정치인의 입장에서 공약을 내거나 다짐하지 마십시오.</rule>
  <rule>칭찬할 대상이 있다면, "경쟁자이지만 훌륭하다" 식으로 화자와의 관계성을 명확히 하십시오.</rule>
</speaker_identity>

<basic_info>
  <author>{author_bio}</author>
  <speaker_name usage="서론 1회, 결론 1회만">{speaker_name}</speaker_name>
  <topic>{topic}</topic>
  <target_length unit="자(공백 제외)">{target_word_count or 2000}</target_length>
</basic_info>

{keywords_section}{hints_section}{rhetorical_section}

<writing_blueprint description="글쓰기 설계도 - 3가지 부품을 조립하여 체계적이고 설득력 있는 글 생성">
  <component id="structure" name="전체 뼈대 (논리 구조): {logical_structure.name}">
    {logical_structure.instruction}
  </component>
  <component id="tactic" name="핵심 기술 (논증 전술): {argumentation_tactic.name}">
    {argumentation_tactic.instruction}
  </component>
  <component id="vocabulary" name="표현 방식 (어휘 모듈): {vocabulary_module.name}">
    <theme>{vocabulary_module.thematic_guidance}</theme>
    위 어휘 테마에 맞는 단어와 표현을 사용하여 글 전체의 톤앤매너를 형성하라.
  </component>
</writing_blueprint>

<output_format_rules>
  <rule id="html">p 태그로 문단 구성, h2/h3 태그로 소제목, ul/ol 태그로 목록, strong 태그로 강조. CSS 인라인 스타일 절대 금지. 마크다운 형식 절대 금지 - 반드시 HTML 태그만 사용</rule>
  <rule id="tone">반드시 존댓말 사용 ("~입니다", "~합니다"). "저는", "제가" 사용. 합리적이고 설득력 있는 어조 유지</rule>
</output_format_rules>

<persuasion_techniques priority="should" description="자연스러운 설득">
  <rule id="specificity">추상적인 개념보다는 구체적인 사례와 숫자를 사용</rule>
  <rule id="empathy">독자의 감정에 호소할 수 있는 진정성 있는 표현을 사용</rule>
  <rule id="vision">문제 지적에 그치지 않고, 반드시 희망적인 대안과 미래를 제시</rule>
</persuasion_techniques>

<quality_verification description="품질 검증 필수사항">
  <rule id="sentence_completeness">모든 문장이 완전한 구조를 갖추고 있는지 확인</rule>
  <rule id="particles">조사 누락 절대 금지</rule>
  <rule id="specificity">괄호 안 예시가 아닌 실제 구체적 내용으로 작성</rule>
  <rule id="logical_flow">도입-전개-결론의 자연스러운 흐름 구성</rule>
  <rule id="style_consistency">존댓말 통일 및 어색한 표현 제거</rule>
  <rule id="actual_content">모든 괄호 표현 제거하고 실제 구체적인 문장으로 작성</rule>
  <rule id="no_repetition">동일하거나 유사한 문장, 문단 반복 금지. 각 문장과 문단은 새로운 정보나 관점을 제공</rule>
  <rule id="structure_integrity">마무리 인사 후에는 절대로 본문이 다시 시작되지 않아야 함</rule>
  <rule id="no_section_conclusion" priority="critical">본론 섹션별 미니결론(요약/다짐) 절대 금지. 각 본론(H2) 섹션은 팩트나 주장으로 담백하게 끝내야 하며, "앞으로 ~하겠습니다", "기대됩니다", "노력하겠습니다" 등의 맺음말은 오직 글의 맨 마지막 결론 섹션에만 작성</rule>
</quality_verification>

<final_mission>
위 글쓰기 설계도와 모든 규칙을 준수하여, 주어진 기본 정보와 배경 정보를 바탕으로 논리정연하고 설득력 있으며 완성도 높은 원고를 작성하라.
필수 키워드에 명시된 모든 키워드를 원고에 자연스럽게 포함시켜야 한다.
출력은 반드시 title, content, hashtags 태그로 감싸서 제공하라.
</final_mission>

<output_format>
출력 시 반드시 아래 XML 태그 형식을 사용하라:

<title>
[여기에 제목 작성 - 25자 이내, 숫자 포함 권장]
</title>

<content>
[여기에 HTML 본문 작성 - p, h2, strong 등 태그 사용]
</content>

<hashtags>
[여기에 해시태그 작성 - 콤마 또는 줄바꿈으로 구분, 3~5개]
</hashtags>
</output_format>

</task>
"""
    return prompt.strip()
