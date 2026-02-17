from dataclasses import dataclass

@dataclass
class PromptOption:
    id: str
    name: str
    instruction: str = ""
    thematic_guidance: str = ""

EMOTIONAL_ARCHETYPES = {
    "PERSONAL_NARRATIVE": PromptOption(id='personal_narrative', name='개인 서사형', instruction="당신의 개인적인 경험, 특히 어려움을 극복했거나 특별한 깨달음을 얻었던 순간의 서사를 진솔하게 풀어내세요. 독자가 당신의 삶의 한 조각을 직접 엿보는 것처럼 느끼게 하여 인간적인 공감대를 형성해야 합니다."),
    "COMMUNITY_APPEAL": PromptOption(id='community_appeal', name='공동체 정서 호명형', instruction="시민들, 또는 특정 집단을 '우리'로 명확히 호명하고, 그들이 공유하는 집단적 기억이나 감정(예: 분노, 슬픔, 희망)을 직접적으로 자극하세요. 공동의 목표를 향한 연대와 결속을 강화하는 메시지를 전달해야 합니다."),
    "POETIC_LYRICISM": PromptOption(id='poetic_lyricism', name='시적 서정형', instruction="직설적인 표현 대신, 문학적 비유, 상징, 서정적인 묘사를 사용하여 당신의 감정을 은유적으로 표현하세요. 한 편의 시나 수필처럼, 독자에게 깊은 감성적 여운을 남겨야 합니다."),
    "STORYTELLING_PERSUASION": PromptOption(id='storytelling_persuasion', name='사연 설득형', instruction="당신이 직접 겪거나 들은 제3자의 구체적인 사연을 한 편의 이야기처럼 생생하게 전달하세요. 독자가 그 이야기의 주인공에게 감정적으로 이입하게 만들어, 당신이 전달하려는 메시지를 자연스럽게 설득시켜야 합니다."),
    "EMOTIONAL_INTERPRETATION": PromptOption(id='emotional_interpretation', name='감정 해석형', instruction="현재 상황이나 특정 사건을 '두려움', '억울함', '희망' 등 당신이 느끼는 감정의 틀로 직접 해석하여 제시하세요. 사실을 나열하는 대신, 당신의 감정을 통해 독자들이 상황의 본질을 감정적으로 이해하도록 이끌어야 합니다."),
    "PLEA_AND_PETITION": PromptOption(id='plea_and_petition', name='호소와 탄원형', instruction="당신의 진심과 절박함을 담아, 독자들에게 관심, 동참, 또는 의견을 겸손하고 간절하게 호소하세요. '도와주십시오', '죄송합니다'와 같이 낮은 자세와 진솔한 마음을 직접적으로 드러내어 독자의 마음을 움직여야 합니다.")
}

NARRATIVE_FRAMES = {
    "OVERCOMING_HARDSHIP": PromptOption(id='overcoming_hardship', name='고난 극복 서사', instruction='당신의 과거 힘들었던 시절(역경, 실패 등)을 구체적으로 묘사하고, 그것을 어떻게 극복하여 현재의 신념을 가지게 되었는지 이야기의 흐름을 만드세요.'),
    "RELENTLESS_FIGHTER": PromptOption(id='relentless_fighter', name='강인한 투사 서사', instruction='현재 우리가 맞서 싸워야 할 대상(예: 불공정, 부조리)을 명확히 설정하고, 이에 굴하지 않고 끝까지 전진하겠다는 강한 의지를 보여주는 서사를 구성하세요.'),
    "SERVANT_LEADER": PromptOption(id='servant_leader', name='서민의 동반자 서사', instruction='스스로를 ‘평범한 사람들의 보호자’로 위치시키고, ‘월급봉투’, ‘아이들의 안전’ 등 서민들의 삶과 직결된 구체적인 요소를 지켜내겠다는 다짐을 중심으로 이야기를 풀어가세요.'),
    "YOUTH_REPRESENTATIVE": PromptOption(id='youth_representative', name='청년 세대 대표 서사', instruction='당신의 힘들었던 청년 시절의 에피소드를 통해, 현재 청년들이 겪는 문제에 깊이 공감하고 있음을 보여주고 그들의 목소리를 대변하겠다는 의지를 밝히세요.')
}

VOCABULARY_MODULES = {
    "HARDSHIP_AND_FAMILY": PromptOption(id='hardship_and_family', name='고난과 가족', instruction="", thematic_guidance="가족의 소중함, 과거의 어려움과 역경, 그리고 그것을 이겨내는 과정에서의 희생과 극복의 감정이 느껴지는 어휘를 사용하세요. (예: '어머니의 헌신', '힘들었던 시절', '그럼에도 불구하고')"),
    "REFORM_AND_STRUGGLE": PromptOption(id='reform_and_struggle', name='개혁과 투쟁', instruction="", thematic_guidance="사회적 부조리에 맞서는 투쟁, 정의를 바로 세우려는 개혁 의지, 그리고 그 과정에서의 어려움과 전진의 느낌을 주는 단어를 사용하세요. (예: '기득권의 저항', '반드시 바로잡겠습니다', '한 걸음 더 나아가')"),
    "SOLIDARITY_AND_PEOPLE": PromptOption(id='solidarity_and_people', name='연대와 서민', instruction="", thematic_guidance="'우리'라는 공동체 의식과 연대, 평범한 사람들의 삶을 지키겠다는 다짐, 그리고 함께할 때 더 나아질 수 있다는 희망을 담은 따뜻한 어휘를 사용하세요. (예: '함께 손잡고', '평범한 이웃들의', '더 나은 내일을 위해')"),
    "RESPONSIBILITY_AND_PLEDGE": PromptOption(id='responsibility_and_pledge', name='책임과 의지', instruction="", thematic_guidance="리더로서의 책임감과 의지를 드러내되 공약성 표현은 피하고, 중립적으로 방향을 제시하는 어휘를 사용하세요. (예: '책임 있게 살펴보겠습니다', '끝까지 챙기겠습니다', '함께 방향을 잡아가겠습니다')"),
    "SINCERITY_AND_APPEAL": PromptOption(id='sincerity_and_appeal', name='진정성과 호소', instruction="", thematic_guidance="자신을 낮추는 겸손함, 잘못에 대한 진솔한 성찰, 그리고 독자들에게 진심으로 도움을 구하는 절박함이 느껴지는 호소력 있는 어휘를 사용하세요. (예: '저의 부족함입니다', '깊이 성찰하겠습니다', '여러분의 힘이 필요합니다')")
}

def build_daily_communication_prompt(options: dict) -> str:
    topic = options.get('topic', '')
    author_bio = options.get('authorBio', '')
    author_name = options.get('authorName', '')
    # user_profile = options.get('userProfile', {}) # Not used in JS template explicitly but passed in options
    instructions = options.get('instructions', '')
    keywords = options.get('keywords', [])
    target_word_count = options.get('targetWordCount', 2000)
    personalized_hints = options.get('personalizedHints', '')
    # news_context = options.get('newsContext', '') # Not used in JS template
    narrative_frame_id = options.get('narrativeFrameId')
    emotional_archetype_id = options.get('emotionalArchetypeId')
    vocabulary_module_id = options.get('vocabularyModuleId')
    negative_persona = options.get('negativePersona')

    speaker_name = author_name if author_name else '화자'

    # Select components with defaults
    narrative_frame = next((v for v in NARRATIVE_FRAMES.values() if v.id == narrative_frame_id), NARRATIVE_FRAMES["SERVANT_LEADER"])
    emotional_archetype = next((v for v in EMOTIONAL_ARCHETYPES.values() if v.id == emotional_archetype_id), EMOTIONAL_ARCHETYPES["PERSONAL_NARRATIVE"])
    vocabulary_module = next((v for v in VOCABULARY_MODULES.values() if v.id == vocabulary_module_id), VOCABULARY_MODULES["SOLIDARITY_AND_PEOPLE"])

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

    negative_persona_val = negative_persona if negative_persona else '상대방'
    negative_persona_quoted = f'"{negative_persona}"' if negative_persona else "'참고자료에 등장하는 타인들'"

    prompt = f"""
<task type="일상 소통" system="전자두뇌비서관">

<speaker_identity priority="critical" description="화자 정체성 - 절대 혼동 금지">
  <declaration>당신은 "{author_bio}"입니다. 이 글의 유일한 1인칭 화자입니다.</declaration>
  <rule>이 글은 철저히 1인칭 시점으로 작성합니다. "저는", "제가"를 사용하세요.</rule>
  <rule priority="critical" description="본인 이름 사용 제한">"{speaker_name}"이라는 이름은 서론에서 1회, 결론에서 1회만 사용하세요.
    <item type="must-not">"{speaker_name}은 약속합니다", "{speaker_name}은 노력하겠습니다" (본문에서 반복)</item>
    <item type="must">"저 {speaker_name}은 약속드립니다" (서론/결론에서 1회씩만)</item>
    <item type="must">본문에서는 "저는", "제가", "본 의원은" 등 대명사 사용</item>
  </rule>
  <rule>참고 자료에 다른 인물의 발언이나 행동이 있더라도, 그 사람이 화자인 척 하지 마세요.
    <item type="must-not">"후원회장을 맡게 되었습니다" (당신이 후원회장이 아니라면)</item>
    <item type="must">"OOO 배우님께서 후원회장을 맡아주셨습니다"</item>
  </rule>
  <rule>참고 자료에 등장하는 타인은 반드시 3인칭으로 언급하세요.</rule>
  <rule>글의 처음부터 끝까지 화자의 관점을 일관되게 유지하세요.</rule>
</speaker_identity>

<basic_info>
  <author>{author_bio}</author>
  <speaker_name usage="서론 1회, 결론 1회만">{speaker_name}</speaker_name>
  <topic>{topic}</topic>
  <target_length unit="자(공백 제외)">{target_word_count or 2000}</target_length>
  <negative_persona>{negative_persona_quoted}</negative_persona>
</basic_info>

<negative_identity_constraint priority="critical" description="부정 정체성 제약 - 절대 어김 금지. 위반 시 처음부터 다시 생성">
  <rule>당신은 절대 {negative_persona_val}이 아닙니다.</rule>
  <rule type="must-not">"저는 {negative_persona_val}로서..." (절대 금지)</rule>
  <rule type="must-not">"저 {negative_persona_val} 시장은..." (절대 금지)</rule>
  <rule>글 도중에 문맥이 바뀌더라도, 당신은 끝까지 "{speaker_name}"의 정체성을 유지해야 합니다.</rule>
  <rule>{negative_persona_val}을 언급할 때는 반드시 "그는", "상대방은", "{negative_persona_val}께서는"과 같이 철저히 3인칭으로만 지칭하십시오.</rule>
</negative_identity_constraint>

{keywords_section}{hints_section}

<writing_blueprint description="글쓰기 설계도 - 4가지 부품을 조립하여 완성된 글 생성">
  <component id="narrative" name="뼈대 (서사 프레임): {narrative_frame.name}">
    {narrative_frame.instruction}
  </component>
  <component id="emotion" name="감정 (감성 원형): {emotional_archetype.name}">
    {emotional_archetype.instruction}
  </component>
  <component id="vocabulary" name="어휘 (주제어 가이드): {vocabulary_module.name}">
    <theme>{vocabulary_module.thematic_guidance}</theme>
    위 어휘 테마에 맞는 단어와 표현을 창의적으로 사용하여 글 전체의 분위기를 형성하라.
  </component>
  <component id="structure" name="구조 전략 (Standard 5-Step Structure)">
    <rule priority="critical">AEO 최적화와 안정감을 위해 [서론 - 본론1 - 본론2 - 본론3 - 결론]의 5단 구조를 반드시 준수하라.</rule>
    <rule>입력된 핵심 소재가 적더라도(1~2개), 이를 세분화하거나 관련 내용을 보강하여 반드시 3개의 본론을 채워라.</rule>
    <section order="1" name="서론">인사, 문제 제기, 공감 형성</section>
    <section order="2" name="본론 1" subheading="h2 소제목 필수">첫 번째 핵심 주장 / 현황 분석</section>
    <section order="3" name="본론 2" subheading="h2 소제목 필수">두 번째 핵심 주장 / 구체적 해결책</section>
    <section order="4" name="본론 3" subheading="h2 소제목 필수">세 번째 핵심 주장 / 미래 비전 및 기대효과</section>
    <section order="5" name="결론">요약, 다짐, 마무리 인사</section>
  </component>
</writing_blueprint>

<output_format_rules>
  <rule id="html">p 태그로 문단 구성, h2/h3 태그로 소제목, ul/ol 태그로 목록, strong 태그로 강조. CSS 인라인 스타일 절대 금지. 마크다운 형식 절대 금지 - 반드시 HTML 태그만 사용</rule>
  <rule id="tone">반드시 존댓말 사용 ("~입니다", "~합니다"). "저는", "제가" 사용. 서민적이고 친근하며 진솔한 어조 유지</rule>
</output_format_rules>

<quality_verification description="품질 검증 필수사항">
  <rule id="sentence_completeness">모든 문장이 완전한 구조를 갖추고 있는지 확인. "주민여하여" (X) → "주민 여러분께서" (O)</rule>
  <rule id="particles">조사 누락 절대 금지. "주민소리에" (X) → "주민들의 소리에" (O)</rule>
  <rule id="specificity">괄호 안 예시가 아닌 실제 구체적 내용으로 작성. "(구체적 사례)" (X) → "지난 10월 12일 시흥시 체육관에서 열린" (O)</rule>
  <rule id="date_preservation">주제에 구체적인 날짜나 시간이 명시되어 있으면 반드시 그대로 사용. "10월 12일 일요일" (O), "10월의 어느 날" (X)</rule>
  <rule id="logical_flow">도입-전개-결론의 자연스러운 흐름 구성</rule>
  <rule id="style_consistency">존댓말 통일 및 어색한 표현 제거</rule>
  <rule id="actual_content">모든 괄호 표현 제거하고 실제 구체적인 문장으로 작성</rule>
  <rule id="emotional_authenticity">형식적인 표현이 아닌, 진심이 느껴지는 구체적인 감정 표현 사용</rule>
  <rule id="no_repetition">동일하거나 유사한 문장, 문단 반복 금지. 각 문장과 문단은 새로운 정보나 관점을 제공</rule>
  <rule id="structure_integrity">마무리 인사 후에는 절대로 본문이 다시 시작되지 않아야 함</rule>
  <rule id="no_section_conclusion" priority="critical">본론 섹션별 미니결론(요약/다짐) 절대 금지. 각 본론(H2) 섹션은 팩트나 주장으로 담백하게 끝내야 하며, "앞으로 ~하겠습니다", "기대됩니다", "노력하겠습니다" 등의 맺음말은 오직 글의 맨 마지막 결론 섹션에만 작성</rule>
</quality_verification>

<final_mission>
위 글쓰기 설계도와 모든 규칙을 준수하여, 주어진 기본 정보와 배경 정보를 바탕으로 진솔하고 울림 있으며 완성도 높은 SNS 원고를 작성하라.
</final_mission>

<output_format>
출력 시 반드시 아래 XML 태그 형식을 사용하라:

<title>
[여기에 제목 작성 - 35자 이내, 감성적이고 공감가는 제목]
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
