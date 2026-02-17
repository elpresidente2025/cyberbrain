from dataclasses import dataclass
from ..common.editorial import get_active_strategies

@dataclass
class PromptOption:
    id: str
    name: str
    instruction: str = ""
    thematic_guidance: str = ""

ANALYTICAL_STRUCTURES = {
    "ISSUE_ANALYSIS": PromptOption(id='issue_analysis', name='현안별 이슈 분석 구조', instruction="글을 '현안 문제 정의 및 현황 파악 → 근본 원인 분석(정부 정책, 지역 여건 등) → 구체적인 해결 방안 제시 → 기대 효과 및 향후 계획'의 순서로 체계적으로 구성하세요."),
    "BUDGET_PERFORMANCE_ANALYSIS": PromptOption(id='budget_performance_analysis', name='예산 확보 성과 분석 구조', instruction="확보한 예산을 '총액 및 건수 명시 → 분야별/지역별 배분 현황 분석 → 과거 데이터와 비교 분석 → 집행 계획 및 기대 효과' 순으로 구성하여 성과를 구체적인 수치로 증명하세요."),
    "LEGISLATIVE_BASIS_ANALYSIS": PromptOption(id='legislative_basis_analysis', name='법안 발의 근거 분석 구조', instruction="발의할 법안에 대해 '현행 법령의 한계 및 문제점 → 해외/모범 사례 검토 → 개정안의 핵심 내용과 필요성 → 예상되는 기대 효과' 순으로 구성하여 입법의 정당성을 논리적으로 증명하세요."),
    "DATA_COMPARATIVE_ANALYSIS": PromptOption(id='data_comparative_analysis', name='데이터 기반 비교 분석 구조', instruction="특정 주제에 대해 통계나 객관적 자료를 활용하여 '지역 간', '시기별', 또는 '정당별' 성과를 비교 분석하는 구조를 사용하세요. 표나 그래프를 설명하는 듯이 명확하게 차이점을 부각해야 합니다."),
    "PERFORMANCE_EVALUATION": PromptOption(id='performance_evaluation', name='성과 검증 및 평가 구조', instruction="기존 정책이나 사업에 대해 '사업 목표 재확인 → 예산 집행률 등 성과 지표 분석 → 긍정적 효과 및 한계점 평가 → 향후 개선 방향 제시' 순으로 구성하여 객관적인 평가와 대안을 담아내세요."),
    "TRANSPARENCY_REPORT": PromptOption(id='transparency_report', name='의정활동 투명성 보고 구조', instruction="의정활동에 대해 '상임위 출석률', '법안 발의 현황', '주민 면담 실적' 등 구체적인 수치를 항목별로 나열하여 투명성과 신뢰성을 강조하는 보고서 형식으로 글을 구성하세요."),
    "CUSTOMIZED_POLICY_PROPOSAL": PromptOption(id='customized_policy_proposal', name='지역 맞춤형 정책 제안 구조', instruction="글을 '우리 지역의 특성 및 데이터 분석 → 주민 수요 조사 및 의견 수렴 결과 → 지역에 최적화된 맞춤형 정책 제안 → 재원 조달 방안 및 기대 효과' 순으로 구성하여 실현 가능성을 강조하세요.")
}

EXPLANATORY_TACTICS = {
    "FACTS_AND_FIGURES": PromptOption(id='facts_and_figures', name='데이터 및 수치 제시', instruction="주장의 신뢰도를 높이기 위해, 예산 규모, 사업 기간, 통계 자료, 집행률 등 구체적인 숫자와 데이터를 적극적으로 활용하여 설명하세요."),
    "DETAILED_ENUMERATION": PromptOption(id='detailed_enumeration', name='구체적 항목 나열', instruction="제시하는 정책 제안이나 성과를 '첫째, 둘째...' 또는 글머리 기호를 사용하여 명확하게 구분하고 상세하게 나열하세요. 정보의 체계성을 높여 독자의 이해를 돕습니다."),
    "ROOT_CAUSE_ANALYSIS": PromptOption(id='root_cause_analysis', name='근본 원인 분석', instruction="표면적인 현상 너머에 있는 구조적, 제도적, 정책적 문제 등 근본적인 원인을 깊이 있게 파고들어 분석의 깊이를 더하고, 문제 해결의 정당성을 확보하세요."),
    "TRANSPARENCY_EMPHASIS": PromptOption(id='transparency_emphasis', name='투명성 강조', instruction="분석에 사용된 데이터의 출처를 명확히 밝히거나, 활동 내역을 상세히 공개하여 의정활동의 투명성을 강조하고 독자의 신뢰를 얻으세요.")
}

VOCABULARY_MODULES = {
    "DATA_DRIVEN_OBJECTIVE": PromptOption(id='data_driven_objective', name='데이터 기반/객관적 어휘', thematic_guidance="객관적이고 중립적인 연구원의 톤을 유지하세요. '데이터에 따르면', '분석 결과', '객관적 지표', '통계적으로 유의미한' 등 감정을 배제하고 사실에 기반한 표현을 사용합니다."),
    "LEGISLATIVE_AND_FORMAL": PromptOption(id='legislative_and_formal', name='입법/공식적 어휘', thematic_guidance="보도자료나 공식 보고서의 톤을 유지하세요. '법안 발의 취지는', '기대효과는', '~할 것을 제안합니다' 등 격식 있고 신뢰감 있는 표현을 사용하여 전문성을 부각합니다."),
    "LOCAL_AND_CONCRETE": PromptOption(id='local_and_concrete', name='지역 밀착형/구체적 어휘', thematic_guidance="지역 주민들이 일상에서 접하는 구체적인 지명, 시설 이름, 도로명 등을 사용하여 분석이 피부에 와 닿도록 하세요. '주민 여러분의 숙원 사업인', '체감할 수 있는 변화' 등 현장감 있는 표현을 사용합니다."),
    "PROBLEM_SOLVING_ORIENTED": PromptOption(id='problem_solving_oriented', name='문제 해결 지향 어휘', thematic_guidance="문제점을 지적하는 데 그치지 않고, 해결을 위한 긍정적이고 적극적인 톤을 유지하세요. '개선 방안', '해결책', '지속 가능한 발전', '새로운 대안' 등 대안을 제시하는 표현을 사용합니다."),
    "COMMUNICATIVE_AND_FRIENDLY": PromptOption(id='communicative_and_friendly', name='소통/친화적 어휘', thematic_guidance="SNS를 통해 소통하는 상황을 가정하여, 다소 부드럽고 친근한 어조를 사용하세요. '#핵심정책', '쉽게 설명해드림' 등 해시태그나 구어체 표현을 활용하여 대중과의 거리감을 좁힙니다.")
}

def build_local_issues_prompt(options: dict) -> str:
    topic = options.get('topic', '')
    author_bio = options.get('authorBio', '')
    instructions = options.get('instructions', '')
    keywords = options.get('keywords', [])
    target_word_count = options.get('targetWordCount', 2000)
    personalized_hints = options.get('personalizedHints', '')
    analytical_structure_id = options.get('analyticalStructureId')
    explanatory_tactic_id = options.get('explanatoryTacticId')
    vocabulary_module_id = options.get('vocabularyModuleId')
    user_profile = options.get('userProfile', {})

    # Select components with defaults
    analytical_structure = next((v for v in ANALYTICAL_STRUCTURES.values() if v.id == analytical_structure_id), ANALYTICAL_STRUCTURES["ISSUE_ANALYSIS"])
    explanatory_tactic = next((v for v in EXPLANATORY_TACTICS.values() if v.id == explanatory_tactic_id), EXPLANATORY_TACTICS["FACTS_AND_FIGURES"])
    vocabulary_module = next((v for v in VOCABULARY_MODULES.values() if v.id == vocabulary_module_id), VOCABULARY_MODULES["DATA_DRIVEN_OBJECTIVE"])

    # Rhetorical Strategy
    rhetorical_strategy = get_active_strategies(topic, instructions, user_profile)
    rhetorical_section = ""
    if rhetorical_strategy['promptInjection']:
        rhetorical_section = f"\n<rhetorical_strategy description=\"설득력 강화\">\n{rhetorical_strategy['promptInjection']}\n</rhetorical_strategy>\n"

    keywords_section = ""
    if keywords:
        keywords_list = ", ".join(keywords)
        keywords_section = f"""
<context_keywords usage="참고용 - 삽입 강제 아님">
{keywords_list}
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

    prompt = f"""
<task type="분석적 글쓰기 (지역 현안)" system="전자두뇌비서관">

<basic_info>
  <author>{author_bio}</author>
  <topic>{topic}</topic>
  <target_length unit="자(공백 제외)">{target_word_count or 2000}</target_length>
</basic_info>

{keywords_section}{hints_section}{rhetorical_section}

<writing_blueprint description="글쓰기 설계도 - 3가지 부품을 조립하여 구체적이고 전문적인 글 생성">
  <component id="structure" name="전체 뼈대 (분석 구조): {analytical_structure.name}">
    {analytical_structure.instruction}
  </component>
  <component id="tactic" name="핵심 기술 (설명 전술): {explanatory_tactic.name}">
    {explanatory_tactic.instruction}
  </component>
  <component id="vocabulary" name="표현 방식 (어휘 모듈): {vocabulary_module.name}">
    <theme>{vocabulary_module.thematic_guidance}</theme>
    위 어휘 테마에 맞는 단어와 표현을 사용하여 글 전체의 톤앤매너를 형성하라.
  </component>
</writing_blueprint>

<output_format_rules>
  <rule id="html">p 태그로 문단 구성, h2/h3 태그로 소제목, ul/ol 태그로 목록, strong 태그로 강조. CSS 인라인 스타일 절대 금지. 마크다운 형식 절대 금지 - 반드시 HTML 태그만 사용</rule>
  <rule id="tone">반드시 존댓말 사용 ("~입니다", "~합니다"). "저는", "제가" 사용. 객관적이고 전문적인 어조 유지</rule>
</output_format_rules>

<quality_verification description="품질 검증 필수사항">
  <rule id="sentence_completeness">모든 문장이 완전한 구조를 갖추고 있는지 확인</rule>
  <rule id="particles">조사 누락 절대 금지</rule>
  <rule id="specificity">괄호 안 예시가 아닌 실제 구체적 내용으로 작성 (예: "지난 10월 12일 시흥시 체육관에서 열린")</rule>
  <rule id="logical_flow">도입-전개-결론의 자연스러운 흐름 구성</rule>
  <rule id="style_consistency">존댓말 통일 및 어색한 표현 제거</rule>
  <rule id="actual_content">모든 괄호 표현 제거하고 실제 구체적인 문장으로 작성</rule>
  <rule id="data_accuracy">수치나 날짜 등 구체적 정보는 반드시 제공된 배경 정보에 근거</rule>
  <rule id="no_repetition">동일하거나 유사한 문장, 문단 반복 금지. 각 문장과 문단은 새로운 정보나 관점을 제공</rule>
  <rule id="structure_integrity">마무리 인사 후에는 절대로 본문이 다시 시작되지 않아야 함</rule>
  <rule id="no_section_conclusion" priority="critical">본론 섹션별 미니결론(요약/다짐) 절대 금지. 각 본론(H2) 섹션은 팩트나 주장으로 담백하게 끝내야 하며, "앞으로 ~하겠습니다", "기대됩니다", "노력하겠습니다" 등의 맺음말은 오직 글의 맨 마지막 결론 섹션에만 작성</rule>
</quality_verification>

<final_mission>
위 글쓰기 설계도와 모든 규칙을 준수하여, 주어진 기본 정보와 배경 정보를 바탕으로 신뢰도 높고 전문적이며 완성도 높은 원고를 작성하라.
필수 키워드에 명시된 모든 키워드를 원고에 자연스럽게 포함시켜야 한다.
</final_mission>

<output_format>
출력 시 반드시 아래 XML 태그 형식을 사용하라:

<title>
[여기에 제목 작성 - 35자 이내, 데이터/숫자 포함 권장]
</title>

<content>
[여기에 HTML 본문 작성 - p, h2, strong 등 태그 사용]
</content>

<hashtags>
[여기에 해시태그 작성 - 콤마 또는 줄바꿈으로 구분, 3~5개]
</hashtags>

주의사항:
- 반드시 위 세 개의 태그로 감싸서 출력할 것
- 태그 외부에는 어떤 설명도 작성하지 말 것
- 마크다운 코드블록 사용 금지
</output_format>

</task>
"""
    return prompt.strip()
