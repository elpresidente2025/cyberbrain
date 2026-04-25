from dataclasses import dataclass
from ..common.editorial import STRUCTURE_SPEC, TITLE_SPEC
from ..common.election_rules import get_election_stage
from ..common.speaker_identity import build_speaker_identity_xml


@dataclass
class PromptOption:
    id: str
    name: str
    instruction: str = ""
    thematic_guidance: str = ""


STORY_FRAMES = {
    "GRASSROOTS": PromptOption(
        id="grassroots",
        name="지역 밀착형",
        instruction=(
            "이 지역에서 오래 살고, 일하고, 이웃과 부대껴 온 사람임을 중심 이야기로 세우세요. "
            "지역의 구체적 현장—골목, 시장, 학교, 주민 센터—에서 느낀 공감을 서사의 뼈대로 삼으세요. "
            "'저도 여기서 함께 살아온 사람입니다'라는 연대 감각이 자연스럽게 전해져야 합니다."
        ),
    ),
    "YOUTH_VOICE": PromptOption(
        id="youth_voice",
        name="청년 대표형",
        instruction=(
            "청년 세대가 겪는 취업·주거·부채·불안의 현실을 화자 본인의 경험에 연결하세요. "
            "'청년으로서 이 자리에 섰다'는 당사자 선언이 설득력의 핵심입니다. "
            "미래에 대한 구체적 희망을 마지막 호소로 연결하세요."
        ),
    ),
    "CHALLENGER": PromptOption(
        id="challenger",
        name="도전자형",
        instruction=(
            "기존 정치에 대한 실망, 변화에 대한 갈망을 공유하는 감정에서 출발하세요. "
            "도전자로서의 두려움을 솔직하게 인정하면서도 '그럼에도 나선 이유'를 담담하게 서술하세요. "
            "독자가 화자의 결기를 느끼고 함께 걸어가고 싶다는 마음이 들어야 합니다."
        ),
    ),
    "SERVANT": PromptOption(
        id="servant",
        name="헌신·봉사형",
        instruction=(
            "화자가 이미 해 온 일—봉사, 돌봄, 지역 활동—을 구체 장면으로 보여주세요. "
            "'하겠습니다'보다 '해 왔습니다'의 증거가 호소의 근거가 됩니다. "
            "결론에서는 '이 봉사를 더 크게 이어가겠습니다'는 확장 다짐으로 CTA를 연결하세요."
        ),
    ),
}

APPEAL_MODES = {
    "EMOTIONAL_PLEA": PromptOption(
        id="emotional_plea",
        name="진심 호소",
        instruction=(
            "논리보다 진심을 앞세우세요. '왜 내가 이 일을 하고 싶은가'를 솔직하게 풀어내세요. "
            "완벽한 수사보다 진심에서 나온 투박한 문장이 더 강하게 울립니다."
        ),
    ),
    "VISION_APPEAL": PromptOption(
        id="vision_appeal",
        name="비전 호소",
        instruction=(
            "지금이 아닌 미래를 그려주세요. '선택해 주시면 이런 내일이 됩니다'라는 "
            "구체적 청사진이 독자의 상상력을 자극해야 합니다. "
            "비전은 추상어가 아니라 일상 언어로 묘사하세요."
        ),
    ),
    "COMMUNITY_BOND": PromptOption(
        id="community_bond",
        name="연대 호소",
        instruction=(
            "'함께'라는 단어가 구호가 아니라 실질적 연대를 뜻하도록 쓰세요. "
            "독자를 '이 문제를 함께 겪어온 우리'로 포용하세요. "
            "CTA는 '지지해 주세요'보다 '함께 만들어가겠습니다'에 가까워야 합니다."
        ),
    ),
}

VOCABULARY_MODULES = {
    "SINCERITY_APPEAL": PromptOption(
        id="sincerity_appeal",
        name="진정성",
        thematic_guidance=(
            "과장하지 않고 솔직한 언어를 쓰세요. 진심이 묻어나는 구체적 묘사가 "
            "직접적인 '진심입니다' 선언보다 효과적입니다. "
            "예: '완벽하지 않습니다만, 이 일을 외면하지 않겠습니다.'"
        ),
    ),
    "HOPE_CHANGE": PromptOption(
        id="hope_change",
        name="희망·변화",
        thematic_guidance=(
            "막연한 희망이 아닌, 변화가 실현된 구체적 장면을 묘사하세요. "
            "'더 나은 미래'가 아닌 '아이들이 안심하고 다닐 수 있는 골목길'처럼 감각적으로 써야 합니다."
        ),
    ),
    "TOGETHER_SOLIDARITY": PromptOption(
        id="together_solidarity",
        name="함께·연대",
        thematic_guidance=(
            "연대는 선언이 아니라 행동입니다. '함께합시다'보다 '제가 먼저 걷겠습니다, 따라와 주십시오'가 "
            "더 강한 연대 감각을 만듭니다."
        ),
    ),
}


def build_support_appeal_prompt(options: dict) -> str:
    topic = options.get('topic', '')
    author_bio = options.get('authorBio', '')
    author_name = options.get('authorName', '')
    user_profile = options.get('userProfile', {})
    keywords = options.get('keywords', [])
    target_word_count = options.get('targetWordCount', int(STRUCTURE_SPEC['idealTotalMin']))
    personalized_hints = options.get('personalizedHints', '')
    current_status = options.get('currentStatus', '') or (
        user_profile.get('status', '') if isinstance(user_profile, dict) else ''
    )

    story_frame_id = options.get('narrativeFrameId')
    appeal_mode_id = options.get('emotionalArchetypeId')
    vocabulary_module_id = options.get('vocabularyModuleId')

    story_frame = next(
        (v for v in STORY_FRAMES.values() if v.id == story_frame_id),
        STORY_FRAMES["GRASSROOTS"],
    )
    appeal_mode = next(
        (v for v in APPEAL_MODES.values() if v.id == appeal_mode_id),
        APPEAL_MODES["EMOTIONAL_PLEA"],
    )
    vocabulary_module = next(
        (v for v in VOCABULARY_MODULES.values() if v.id == vocabulary_module_id),
        VOCABULARY_MODULES["TOGETHER_SOLIDARITY"],
    )

    speaker_name = author_name if author_name else '화자'

    speaker_identity_xml = build_speaker_identity_xml(
        full_name=author_name,
        author_bio=author_bio,
        user_profile=user_profile,
    )

    election_stage = get_election_stage(current_status)
    election_compliance_section = ""
    if election_stage and election_stage.get('promptInstruction'):
        election_compliance_section = f"""
<election_compliance priority="critical" description="선거법 준수 필수 - 위반 시 법적 책임 발생">
{election_stage['promptInstruction']}
</election_compliance>
"""

    keywords_section = ""
    if keywords:
        keywords_list = ", ".join(keywords)
        keywords_section = f"""
<context_keywords usage="필수 삽입 - 원문 그대로">
{keywords_list}
아래 키워드를 원문 그대로 본문에 삽입하세요. 조사(의/은/는/을/를)를 붙이거나 어순을 바꾸지 마세요.
</context_keywords>
"""

    hints_section = ""
    if personalized_hints:
        hints_section = f"""
<personalization_guide>
{personalized_hints}
주의: 위 가이드는 글쓰기 방향 지시입니다. 이 문구를 본문에 직접 인용하거나 복사하지 마세요.
</personalization_guide>
"""

    prompt = f"""
<task type="지지 호소" system="전자두뇌비서관">

{election_compliance_section}
{speaker_identity_xml}

<basic_info>
  <author>{author_bio}</author>
  <speaker_name usage="서론 1회, 결론 1회만">{speaker_name}</speaker_name>
  <topic>{topic}</topic>
  <target_length unit="자(공백 제외)">{target_word_count or int(STRUCTURE_SPEC['idealTotalMin'])}</target_length>
</basic_info>

{keywords_section}{hints_section}

<source_constraint priority="critical" description="소재 순도 규칙">
  <rule id="input_only">본문의 서사 골격(인물, 사건, 동기, 지역 연결고리)은 반드시 입장문(stanceText)에서 가져와야 합니다.</rule>
  <rule id="no_rag_section">RAG 맥락·프로필 공약 항목을 소재로 독립 H2 섹션을 신설하지 마세요. 정책은 화자의 배경이나 다짐을 뒷받침하는 맥락으로 1~2개 간략 언급에 그쳐야 합니다.</rule>
  <rule id="policy_as_evidence">공약은 "이러한 삶을 살아왔기에 이런 준비를 했다"는 서사의 증거로만 사용하세요. 공약 목록을 나열하거나 정책 설명 섹션을 만드는 것은 금지입니다.</rule>
  <rule id="sparse_input_allowed">입장문 소재가 1~2개뿐이어도 강제로 3개 섹션을 채우지 마세요. 2개 H2로도 완성된 글이 됩니다.</rule>
</source_constraint>

<writing_blueprint description="Hook → Story → Vision → CTA 4단 흐름">

  <component id="story_frame" name="스토리 프레임: {story_frame.name}">
    {story_frame.instruction}
  </component>

  <component id="appeal_mode" name="호소 방식: {appeal_mode.name}">
    {appeal_mode.instruction}
  </component>

  <component id="vocabulary" name="어휘 모듈: {vocabulary_module.name}">
    <theme>{vocabulary_module.thematic_guidance}</theme>
    위 어휘 테마에 맞는 단어와 표현을 사용하여 글 전체의 감성을 형성하라.
  </component>

  <component id="structure" name="4단 서사 구조 (Hook → Story → Vision → CTA)">
    <section order="1" name="서론 (Hook)">
      감각적이고 구체적인 장면이나 질문으로 시작하세요. 일반 인삿말로 시작하지 마세요.
      화자 소개는 1문장 이내로 제한하고, 왜 이 글을 쓰게 됐는지를 바로 연결하세요.
    </section>
    <section order="2" name="본론 1 (Story/Why)" subheading="h2 소제목 필수 — 서사형·선언형으로 작성 (질문형 금지)">
      화자가 이 일에 나선 이유, 지역·사람·사건과의 개인적 연결고리를 구체 장면으로 풀어내세요.
      소재가 1개뿐이면 이 섹션에 집중하고 억지로 분리하지 마세요.
    </section>
    <section order="3" name="본론 2 (Vision/Promise, 선택적)" subheading="h2 소제목 필수 — 서사형·선언형으로 작성 (질문형 금지)">
      입장문에 비전·약속 소재가 있을 경우에만 작성하세요. 소재가 없으면 이 섹션을 생략하고
      2개 본론으로 완성하세요. RAG/프로필 보강으로 채우는 것은 금지합니다.
    </section>
    <section order="4" name="결론 (CTA)">
      결론 마지막 문단에 지지 호소 문장을 반드시 1~2개 포함하세요.
      호소는 "~해 주십시오" 또는 "~해 주세요" 형식의 직접 요청이어야 합니다.
    </section>

    <rules>
      <rule id="h2_style">H2 소제목은 서사형·선언형으로 작성. 질문형("왜~", "어떻게~", "무엇이~") 금지.</rule>
      <rule id="body_count">본론은 2개 또는 3개. 소재가 충분하면 3개, 부족하면 2개로 완성. 3개 강제 금지.</rule>
      <rule id="cta_mandatory">결론 마지막 문단에 지지·동참 호소 문장이 없으면 불합격.</rule>
      <rule id="no_section_mini_conclusion">각 본론 섹션 말미에 "앞으로 ~하겠습니다" 식의 미니 결론 금지. 다짐·호소는 결론에만.</rule>
    </rules>
  </component>

</writing_blueprint>

<output_format_rules>
  <rule id="html">p 태그로 문단 구성, h2 태그로 소제목, strong 태그로 강조. CSS 인라인 스타일·마크다운 절대 금지</rule>
  <rule id="tone">반드시 존댓말 ("~입니다", "~합니다"). "저는", "제가" 사용. 진솔하고 간절한 어조 유지</rule>
  <rule id="no_repetition">동일하거나 유사한 문장·문단 반복 금지. 각 문장과 문단은 새로운 정보나 관점을 제공</rule>
  <rule id="structure_integrity">마무리 인사 후 본문 재시작 금지</rule>
</output_format_rules>

<quality_verification description="품질 검증">
  <rule id="cta_check">결론에 지지·동참 호소 문장 확인</rule>
  <rule id="h2_style_check">H2가 서사형·선언형인지 확인</rule>
  <rule id="source_purity_check">입장문에 없는 소재(정책 공약, 수치)가 생성되지 않았는지 확인</rule>
  <rule id="sentence_completeness">모든 문장 완전한 구조 확인</rule>
  <rule id="particles">조사 누락 절대 금지</rule>
</quality_verification>

<final_mission>
위 글쓰기 설계도와 모든 규칙을 준수하여, 입력 소재만으로 진솔하고 설득력 있는 지지 호소 원고를 작성하라.
소재가 적더라도 강제로 보강하지 말고, 있는 소재로 완성도 높은 글을 완성하라.
출력은 반드시 title, content, hashtags 태그로 감싸서 제공하라.
</final_mission>

<output_format>
출력 시 반드시 아래 XML 태그 형식을 사용하라:

<title>
[여기에 제목 작성 - {TITLE_SPEC['hardMax']}자 이내, 화자의 진심이 느껴지는 제목]
</title>

<content>
[여기에 HTML 본문 작성 - p, h2, strong 태그 사용]
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
