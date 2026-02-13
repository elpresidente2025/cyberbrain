from dataclasses import dataclass
from ..common.editorial import get_active_strategies

@dataclass
class PromptOption:
    id: str
    name: str
    instruction: str = ""
    thematic_guidance: str = ""

WRITING_EXAMPLES = {
    "SOLUTION_FIRST": """
<reference_example type="대안 우선 구조">
  <background>정책/인물/사건에 대한 구체적 정보</background>
  <sample_output format="json">
    <title>[제목]</title>
    <content><![CDATA[<p>존경하는 [지역] 여러분, [이름]입니다.</p><h2>[대안 제목 - 이렇게 해야 합니다]</h2><p>[구체적 대안: 수치, 연도, 계획 포함]</p><h2>[비판 제목 - 그런데 현재는]</h2><p>[문제 지적 및 대비]</p><h2>[다짐 제목]</h2><p>[대안 재강조]</p>]]></content>
    <word_count>1500</word_count>
  </sample_output>
  <guidance>
    <item>대안을 먼저 제시 (구체적 수치 포함)</item>
    <item>그 다음 문제를 대비시킴</item>
    <item>마지막에 다짐으로 대안 재강조</item>
  </guidance>
</reference_example>
""",
    "PROBLEM_FIRST": """
<reference_example type="문제 우선 구조 (전통적)">
  <background>문제 상황에 대한 구체적 정보</background>
  <sample_output format="json">
    <title>[제목]</title>
    <content><![CDATA[<p>존경하는 [지역] 여러분, [이름]입니다.</p><h2>[문제 제목]</h2><p>[문제 현상 및 데이터]</p><h2>[원인 분석]</h2><p>[왜 이런 일이 발생했는가]</p><h2>[대안 제시]</h2><p>[구체적 해결 방안]</p>]]></content>
    <word_count>1500</word_count>
  </sample_output>
</reference_example>
"""
}

def get_relevant_example(critical_structure_id: str) -> str:
    if critical_structure_id == 'solution_first_criticism':
        return WRITING_EXAMPLES["SOLUTION_FIRST"]
    elif critical_structure_id in ['problem_first_criticism', 'policy_failure_criticism']:
        return WRITING_EXAMPLES["PROBLEM_FIRST"]
    return WRITING_EXAMPLES["SOLUTION_FIRST"]

CRITICAL_STRUCTURES = {
    "SOLUTION_FIRST_CRITICISM": PromptOption(id='solution_first_criticism', name='대안 우선 비판 구조 (두괄식)', instruction="글을 다음 3단계로 구성하세요:\n\n1. 대안 제시 (앞쪽 비중, 구체적으로)\n   - 먼저 \"이렇게 해야 합니다\"를 명확히 제시\n   - 구체적 수치/연도는 배경정보에 있는 것만 사용\n   - 독자에게 \"이 사람은 준비된 리더\"라는 인상을 각인\n\n2. 문제 지적 (중간 비중, 대비 강화)\n   - \"그런데 현재는/상대방은 이렇게 하고 있습니다\"로 전환\n   - 앞서 제시한 올바른 방법과 대비시켜 상대의 무능/무책임 부각\n   - 팩트 기반으로 냉정하게 비판\n\n3. 다짐 강화 (마무리 비중, 재확인)\n   - 대안을 다시 한 번 강조하며 마무리\n   - \"저는 준비되어 있습니다\", \"성과로 보여드리겠습니다\"\n\n핵심: 독자가 기억하는 것은 \"비판받는 사람\"이 아니라 \"대안을 가진 당신\"이어야 합니다."),
    "MEDIA_FRAME_CRITICISM": PromptOption(id='media_frame_criticism', name='언론 프레이밍 비판 구조', instruction="글을 '문제 보도 인용 → 숨은 의도 및 프레임 지적 → 대중에게 질문'의 3단계로 구성하세요. 언론의 보도가 단순한 실수가 아닌, 의도적인 프레임을 갖고 있음을 암시하며 여론전을 유도해야 합니다."),
    "FACT_CHECK_REBUTTAL": PromptOption(id='fact_check_rebuttal', name='가짜뉴스 반박 구조', instruction="글을 '허위 주장 요약 → 명백한 사실/데이터 제시 → 법적/정치적 책임 경고'의 순서로 구성하세요. 감정적 대응을 자제하고, 명확한 증거를 통해 상대 주장의 신뢰도를 완전히 무너뜨려야 합니다."),
    "PROBLEM_FIRST_CRITICISM": PromptOption(id='problem_first_criticism', name='문제 우선 비판 구조 (전통식)', instruction="글을 '문제 현상 제시 → 데이터/통계를 통한 원인 분석 → 구체적인 정책 대안 촉구'의 흐름으로 구성하세요. 단순한 비난이 아닌, 대안을 가진 책임 있는 비판의 모습을 보여주어야 합니다."),
    "POLICY_FAILURE_CRITICISM": PromptOption(id='policy_failure_criticism', name='정책 실패 비판 구조', instruction="글을 '문제 현상 제시 → 데이터/통계를 통한 원인 분석 → 구체적인 정책 대안 촉구'의 흐름으로 구성하세요. 단순한 비난이 아닌, 대안을 가진 책임 있는 비판의 모습을 보여주어야 합니다."),
    "OFFICIAL_MISCONDUCT_CRITICISM": PromptOption(id='official_misconduct_criticism', name='공직자 비위 비판 구조', instruction="글을 '의혹 사실 요약 → 법적/윤리적 문제점 지적 → 사퇴/징계 등 구체적인 책임 요구' 순으로 구성하세요. 개인적인 비난이 아닌, 공직자로서의 책임을 묻는다는 점을 명확히 해야 합니다.")
}

OFFENSIVE_TACTICS = {
    "METAPHORICAL_STRIKE": PromptOption(id='metaphorical_strike', name='은유와 상징을 통한 공격', instruction="비판 대상을 부정적인 의미를 가진 단어나 상황(예: '커밍아웃', '소설쓰기')에 빗대어 표현하세요. 직접적인 비난보다 더 큰 모욕감과 압박감을 주는 효과를 노립니다."),
    "INDIRECT_CRITICISM_BY_SHARING": PromptOption(id='indirect_criticism_by_sharing', name='기사/타인 글 공유를 통한 간접 비판', instruction="당신의 입장과 유사한 제3자(언론, 전문가 등)의 글을 공유한 뒤, '이 정도일 줄은 몰랐다'와 같이 짧은 코멘트를 덧붙여 비판의 책임을 분산시키고 객관성을 확보하는 전략을 사용하세요."),
    "SATIRE_AND_PARODY": PromptOption(id='satire_and_parody', name='풍자와 패러디를 통한 조롱', instruction="상대방의 행동이나 발언을 익살스럽게 따라하거나(패러디), 과장하여 웃음거리로 만드세요. 이를 통해 상대의 권위를 실추시키고, 지지층에게는 카타르시스를 제공합니다."),
    "EXPOSING_CONTRADICTION": PromptOption(id='exposing_contradiction', name='내로남불/모순 지적', instruction="상대방이 과거에 했던 발언이나 행동을 현재의 입장과 비교하여, 그들의 모순과 이중성을 명확하게 드러내세요. '그들 자신의 논리'로 그들을 공격하여 반박의 여지를 차단합니다.")
}

VOCABULARY_MODULES = {
    "AGGRESSIVE_ATTACK": PromptOption(id='aggressive_attack', name='공격적/도발적 어휘', thematic_guidance="강하고 때로는 자극적인 단어를 사용하여 이슈를 선점하고 주목도를 높이세요. '망언', '내란', '참사', '심판' 등 선명하고 단호한 표현으로 비판의 강도를 극대화합니다."),
    "LEGAL_FACTUAL": PromptOption(id='legal_factual', name='법률적/사실적 어휘', thematic_guidance="감정적 표현을 배제하고, 법률 용어, 통계, 데이터 등 객관적인 사실에만 기반하여 비판하세요. '직권남용', '허위사실공표', '통계에 따르면' 등 차분하고 논리적인 표현으로 신뢰도를 높입니다."),
    "SARCASTIC_IRONIC": PromptOption(id='sarcastic_ironic', name='풍자적/반어적 어휘', thematic_guidance="상대방을 비꼬거나 반어적인 표현을 사용하여 비판의 날을 세우세요. '대단한 업적', '그냥 웃습니다', '잘하는 짓이다' 등 우회적인 표현으로 상대의 권위를 조롱합니다."),
    "FORMAL_OFFICIAL": PromptOption(id='formal_official', name='공식적/점잖은 어휘', thematic_guidance="공식적인 입장문이나 논평의 격식을 갖추어 비판하세요. '깊은 유감을 표합니다', '~할 것을 촉구합니다', '매우 우려스럽습니다' 등 절제되고 품위 있는 표현을 사용합니다.")
}

def build_critical_writing_prompt(options: dict) -> str:
    topic = options.get('topic', '')
    author_bio = options.get('authorBio', '')
    instructions = options.get('instructions', '')
    keywords = options.get('keywords', [])
    target_word_count = options.get('targetWordCount', 2000)
    personalized_hints = options.get('personalizedHints', '')
    critical_structure_id = options.get('criticalStructureId')
    offensive_tactic_id = options.get('offensiveTacticId')
    vocabulary_module_id = options.get('vocabularyModuleId')
    user_profile = options.get('userProfile', {})
    negative_persona = options.get('negativePersona', '')

    # Select components with defaults
    critical_structure = next((v for v in CRITICAL_STRUCTURES.values() if v.id == critical_structure_id), CRITICAL_STRUCTURES["SOLUTION_FIRST_CRITICISM"])
    offensive_tactic = next((v for v in OFFENSIVE_TACTICS.values() if v.id == offensive_tactic_id), OFFENSIVE_TACTICS["EXPOSING_CONTRADICTION"])
    vocabulary_module = next((v for v in VOCABULARY_MODULES.values() if v.id == vocabulary_module_id), VOCABULARY_MODULES["LEGAL_FACTUAL"])

    relevant_example = get_relevant_example(critical_structure.id)

    # Rhetorical Strategy
    rhetorical_strategy = get_active_strategies(topic, instructions, user_profile)
    rhetorical_section = ""
    if rhetorical_strategy['promptInjection']:
        rhetorical_section = f"\n<rhetorical_strategy description=\"설득력 강화\">\n{rhetorical_strategy['promptInjection']}\n</rhetorical_strategy>\n"

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

    negative_persona_str = f'"{negative_persona}"' if negative_persona else "'참고자료에 등장하는 타인들'"
    negative_persona_val = negative_persona if negative_persona else '상대방'

    prompt = f"""
<task type="비판적 글쓰기" system="전자두뇌비서관">

<basic_info>
  <author>{author_bio}</author>
  <topic>{topic}</topic>
  <target_length unit="자(공백 제외)">{target_word_count or 2000}</target_length>
  <negative_persona>{negative_persona_str}</negative_persona>
</basic_info>

<negative_identity_constraint priority="critical" description="부정 정체성 제약 - 절대 어김 금지">
  <rule>당신은 절대 {negative_persona_val}이 아닙니다.</rule>
  <rule type="must-not">"저는 {negative_persona_val}로서..." (절대 금지)</rule>
  <rule>글 도중에 문맥이 바뀌더라도, 당신은 끝까지 "{author_bio}"의 정체성을 유지해야 합니다.</rule>
  <rule>{negative_persona_val}을 언급할 때는 반드시 3인칭으로만 지칭하십시오.</rule>
</negative_identity_constraint>

{keywords_section}{hints_section}{rhetorical_section}

<writing_example description="올바른 작성 예시 - 구조와 스타일 참고용">
{relevant_example}
<instruction>위 예시의 구조와 스타일을 참고하되, 제공된 배경 정보를 바탕으로 완전히 새로운 원고를 작성하라. 배경정보를 그대로 복사하지 말고, 자연스럽게 재구성하여 본론에 녹여내라.</instruction>
</writing_example>

<hallucination_guardrail priority="critical" description="사실 기반 글쓰기">
  <rule>절대로 사실을 지어내거나 추측해서는 안 된다.</rule>
  <rule>모든 비판과 주장은 오직 기본 정보 및 배경 정보에 제공한 내용에만 100% 근거해야 한다.</rule>
  <rule>구체적인 사실, 통계, 인용문이 제공되었다면 반드시 활용하라.</rule>
  <rule>구체적인 사실이 제공되지 않았다면, 사실을 날조하지 말고 원칙적인 수준의 비판만 수행하라.</rule>
</hallucination_guardrail>

<logic_guard priority="critical" description="논리 비약 절대 금지">
  <category name="주제 외 효과 주장 금지">
    <item type="must-not">"특검법 → 경제 발전/투자 유치" (법률 수사와 경제는 무관)</item>
    <item type="must-not">"투명한 사회 → 관광객 증가" (논리적 연결 없음)</item>
    <item type="must-not">"공정한 정치 → 일자리 창출" (직접적 인과관계 없음)</item>
    <item type="must">참조자료의 주제 범위 내에서만 논의</item>
  </category>
  <category name="새로운 주장 생성 금지">
    <item type="must-not">입장문에 없는 주장을 창작하여 추가</item>
    <item type="must-not">"따라서 X는 Y에 도움이 될 것입니다" 패턴 (근거 없는 결론)</item>
    <item type="must-not">"이는 곧 Z로 이어질 것입니다" 패턴 (추측성 예측)</item>
    <item type="must">입장문의 핵심 논지만 확장/구체화</item>
  </category>
  <category name="AI 슬롭 표현 금지">
    <item type="must-not">"투명하고 공정한 사회를 만들겠습니다"</item>
    <item type="must-not">"밝은 미래를 위해 노력하겠습니다"</item>
    <item type="must-not">"함께 만들어 나가겠습니다"</item>
    <item type="must-not">"필수적인 투자입니다"</item>
    <item type="must-not">"부산 경제 활성화에 기여할 것입니다"</item>
    <item type="must">구체적 사실과 논리적 주장만 사용</item>
  </category>
</logic_guard>

<source_preservation priority="absolute" description="참조자료 핵심 논지 보존 - 다른 모든 규칙보다 우선">
  <rule id="preserve_core" priority="critical" description="입장문의 핵심 문구 그대로 반영">
    참조자료에 입장문이 포함되어 있다면, 핵심 주장과 논리 구조를 반드시 유지하세요.
    입장문의 날카로운 표현, 수사적 질문, 반어법 등은 그대로 살려서 본문에 녹여내세요.
    <item type="must-not">입장문의 핵심 메시지를 일반론으로 희석하거나 다른 주제로 대체</item>
  </rule>
  <rule id="exact_keywords" priority="critical" description="구체적 키워드/법안명/인물명 정확히 사용">
    참조자료에 등장하는 구체적인 명칭(법안명, 인물명, 기관명, 사건명)을 반드시 그대로 사용하세요.
    <item type="must-not">"2차 특검법" → "2차 이슈", "해당 법안" 등으로 회피</item>
    <item type="must-not">"박형준 시장" → "해당 인물", "관계자" 등으로 익명화</item>
    <item type="must-not">키워드를 따옴표로 감싸기 - 자연스럽게 본문에 녹여야 함</item>
    <item type="must">참조자료에 명시된 고유명사는 원문 그대로 본문에 포함</item>
  </rule>
  <rule id="no_external_topics" priority="critical" description="참조자료 외 주제 삽입 금지">
    참조자료에 언급되지 않은 주제를 본문에 끌어오지 마세요.
    분량 확보가 필요하면 참조자료의 논점을 더 깊이 분석하거나 다양한 각도에서 해석하세요.
  </rule>
  <rule id="rhetorical_mirroring" priority="critical" description="입장문의 수사적 구조 모방">
    입장문이 강력한 문장으로 시작했다면, 그 논조와 리듬을 유지하세요.
    입장문이 반복적 대구법을 사용했다면, 그 수사적 기법을 본문에도 적용하세요.
  </rule>
</source_preservation>

<writing_blueprint description="글쓰기 설계도 - 3가지 부품을 조립하여 날카롭고 설득력 있는 비판의 글 생성">
  <component id="structure" name="전체 뼈대 (비판 구조): {critical_structure.name}">
    {critical_structure.instruction}
  </component>
  <component id="tactic" name="핵심 기술 (공격 전술): {offensive_tactic.name}">
    {offensive_tactic.instruction}
  </component>
  <component id="vocabulary" name="표현 방식 (어휘 모듈): {vocabulary_module.name}">
    <theme>{vocabulary_module.thematic_guidance}</theme>
    위 어휘 테마에 맞는 단어와 표현을 사용하여 글 전체의 톤앤매너를 형성하라.
  </component>
</writing_blueprint>

<output_format_rules>
  <rule id="html">p 태그로 문단 구성, h2/h3 태그로 소제목, ul/ol 태그로 목록, strong 태그로 강조. CSS 인라인 스타일 절대 금지. 마크다운 형식 절대 금지 - 반드시 HTML 태그만 사용</rule>
  <rule id="tone">반드시 존댓말 사용 ("~입니다", "~합니다"). "저는", "제가" 사용. 비판적이되 논리적인 어조 유지</rule>
</output_format_rules>

<quality_verification description="품질 검증 필수사항">
  <rule id="sentence_completeness">모든 문장이 완전한 구조를 갖추고 있는지 확인</rule>
  <rule id="particles">조사 누락 절대 금지</rule>
  <rule id="specificity">괄호 안 예시가 아닌 실제 구체적 내용으로 작성</rule>
  <rule id="logical_flow">도입-전개-결론의 자연스러운 흐름 구성</rule>
  <rule id="style_consistency">존댓말 통일 및 어색한 표현 제거</rule>
  <rule id="actual_content">모든 괄호 표현 제거하고 실제 구체적인 문장으로 작성</rule>
  <rule id="fact_based">제공된 정보에만 근거한 비판, 추측이나 날조 금지</rule>
  <rule id="no_repetition">동일하거나 유사한 문장, 문단 반복 금지. 각 문장과 문단은 새로운 정보나 관점을 제공</rule>
  <rule id="structure_integrity">마무리 인사 후에는 절대로 본문이 다시 시작되지 않아야 함</rule>
  <rule id="no_section_conclusion" priority="critical">본론 섹션별 미니결론(요약/다짐) 절대 금지. 각 본론(H2) 섹션은 팩트나 주장으로 담백하게 끝내야 하며, "앞으로 ~하겠습니다", "기대됩니다", "노력하겠습니다" 등의 맺음말은 오직 글의 맨 마지막 결론 섹션에만 작성</rule>
</quality_verification>

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

주의사항:
- 반드시 위 세 개의 태그로 감싸서 출력할 것
- 태그 외부에는 어떤 설명도 작성하지 말 것
- 마크다운 코드블록 사용 금지
</output_format>

<final_mission>
위 절대 원칙과 글쓰기 설계도, 그리고 모든 규칙을 준수하여, 주어진 기본 정보와 배경 정보를 바탕으로 논리정연하고 강력하며 완성도 높은 비판 원고를 작성하라.
필수 키워드에 명시된 모든 키워드를 원고에 자연스럽게 포함시켜야 한다.
출력은 반드시 title, content, hashtags 태그로 감싸서 제공하라.
</final_mission>

</task>
"""
    return prompt.strip()

def build_diagnosis_writing_prompt(options: dict) -> str:
    topic = options.get('topic', '')
    author_bio = options.get('authorBio', '')
    instructions = options.get('instructions', '')
    keywords = options.get('keywords', [])
    target_word_count = options.get('targetWordCount', 2000)
    personalized_hints = options.get('personalizedHints', '')
    user_profile = options.get('userProfile', {})
    negative_persona = options.get('negativePersona', '')

    # Rhetorical Strategy
    rhetorical_strategy = get_active_strategies(topic, instructions, user_profile)
    rhetorical_section = ""
    if rhetorical_strategy['promptInjection']:
        rhetorical_section = f"\n<rhetorical_strategy description=\"설득력 강화\">\n{rhetorical_strategy['promptInjection']}\n</rhetorical_strategy>\n"

    keywords_section = ""
    if keywords:
        keywords_str = ", ".join(keywords)
        keywords_section = f"""
<context_keywords usage="맥락 파악과 표현 다양화에만 참고">
{keywords_str}
</context_keywords>
"""

    hints_section = ""
    if personalized_hints:
        hints_section = f"""
<personalization_guide>
{personalized_hints}
</personalization_guide>
"""

    negative_persona_str = f'"{negative_persona}"' if negative_persona else "'참고자료에 등장하는 타인들'"
    negative_persona_val = negative_persona if negative_persona else '상대방'

    prompt = f"""
<task type="현안 진단" system="전자두뇌비서관">

<basic_info>
  <author>{author_bio}</author>
  <topic>{topic}</topic>
  <target_length unit="자(공백 제외)">{target_word_count or 2000}</target_length>
  <negative_persona>{negative_persona_str}</negative_persona>
</basic_info>

<negative_identity_constraint priority="critical" description="부정 정체성 제약 - 절대 어김 금지">
  <rule>당신은 절대 {negative_persona_val}이 아닙니다.</rule>
  <rule type="must-not">"저는 {negative_persona_val}로서..." (절대 금지)</rule>
  <rule>글 도중에 문맥이 바뀌더라도, 당신은 끝까지 "{author_bio}"의 정체성을 유지해야 합니다.</rule>
  <rule>{negative_persona_val}을 언급할 때는 반드시 3인칭으로만 지칭하십시오.</rule>
</negative_identity_constraint>

{keywords_section}{hints_section}{rhetorical_section}

<diagnosis_rules priority="critical" description="진단 전용 규칙">
  <rule type="must-not">해법/대안/정책 제안/요구/추진 계획/약속은 절대 포함하지 않는다.</rule>
  <rule type="must-not">"해야 한다/추진하겠다/대책을 마련하겠다" 같은 처방형 문구 금지.</rule>
  <rule>결론은 '진단 요약'으로 마무리하고 행동 촉구를 넣지 않는다.</rule>
  <rule>비난보다 진단에 집중하며, 단정적 인신공격은 금지한다.</rule>
</diagnosis_rules>

<writing_structure>
  <section order="1" name="현안 개요">핵심 사실과 범위를 요약</section>
  <section order="2" name="핵심 지표/사실">제공된 자료 기반으로 정리</section>
  <section order="3" name="구조적 원인">제도·산업·인구·시장 등 원인 분석</section>
  <section order="4" name="이해관계/책임 구조">관련 주체와 역할/책임 정리</section>
  <section order="5" name="영향과 위험">단기/중장기 파급</section>
  <section order="6" name="불확실성 및 추가 확인 필요">데이터 공백, 확인해야 할 점</section>
</writing_structure>

<hallucination_guardrail priority="critical" description="사실 기반 원칙">
  <rule>제공된 정보에 없는 수치, 고유명사, 사건을 만들지 않는다.</rule>
  <rule>배경 정보에 없는 사실은 추정하지 말고 일반론 수준에서만 언급한다.</rule>
  <rule>인용·통계·연도·비율 등 구체 데이터는 제공된 내용에만 근거한다.</rule>
</hallucination_guardrail>

<logic_guard priority="critical" description="논리 비약 절대 금지">
  <item type="must-not">"이 현안 → 경제 발전/투자 유치" (주제와 무관한 효과 주장 금지)</item>
  <item type="must-not">"따라서 X는 Y에 도움이 될 것입니다" (근거 없는 결론 금지)</item>
  <item type="must-not">"투명하고 공정한 사회", "밝은 미래" (추상적 레토릭 금지)</item>
  <item type="must">참조자료의 주제 범위 내에서만 진단, 분석</item>
</logic_guard>

<output_format_rules>
  <rule id="html">p 문단, h2/h3 소제목, ul/ol 목록, strong 강조. 마크다운 기호 금지</rule>
  <rule id="tone">존댓말, 분석적·중립적 톤 유지</rule>
  <rule id="no_repetition">동일·유사 문장 반복 금지</rule>
</output_format_rules>

<output_format>
출력 시 반드시 아래 XML 태그 형식을 사용하라:

<title>
[여기에 제목 작성 - 25자 이내, 진단 결과 요약]
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

<final_mission>
위 규칙과 구조를 모두 준수하여, 주어진 기본 정보와 배경 정보만을 근거로 현안 진단 원고를 작성하라.
출력은 반드시 title, content, hashtags 태그로 감싸서 제공하라.
</final_mission>

</task>
"""
    return prompt.strip()
