from dataclasses import dataclass
from ..common.editorial import STRUCTURE_SPEC, TITLE_SPEC
from ..common.election_rules import get_election_stage
from ..common.speaker_identity import build_speaker_identity_xml
from ..common.leadership import LEADERSHIP_PHILOSOPHY
from ..common.support_appeal_bio_sanitizer import sanitize_support_appeal_author_bio


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
    author_bio = sanitize_support_appeal_author_bio(options.get('authorBio', ''))
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

    _core = LEADERSHIP_PHILOSOPHY.get('coreApproach', {})
    _field_based = _core.get('fieldBased', {}).get('meaning', '현장에서 답을 찾고 현실에 기반한 정치')
    _result_oriented = _core.get('resultOriented', {}).get('meaning', '화려한 말보다 실질적 변화와 성과')
    _tone = LEADERSHIP_PHILOSOPHY.get('communicationStyle', {}).get('tone', {})
    _humble = _tone.get('humble', '겸손하고 진솔한 자세')
    _empathetic = _tone.get('empathetic', '서민의 아픔에 공감')

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
  <philosophy>
    {_field_based} — 화자가 직접 경험하고 현장에서 목격한 것만이 이 글의 뼈대가 될 수 있다.
    {_result_oriented} — 추상적 선언이 아닌 감각적 장면으로 변화를 묘사해야 한다.
  </philosophy>
  <rule id="no_fabrication">없는 사실을 지어내는 것은 금지. 입장문과 화자 프로필에 있는 소재만 사용.</rule>
  <rule id="no_rag_section">RAG 정책 항목을 소재로 독립 H2 섹션 신설 금지. 정책명은 전체 최대 2개, 각 1문장 이내.</rule>
  <rule id="policy_as_evidence">정책은 "이런 삶을 살아왔기에 이런 준비를 했다"는 사람 증명의 증거로만 사용. 목록 나열·설명 섹션 금지.</rule>
  <rule id="community_context_allowed">RAG의 지역 현실·주민 생활 맥락 청크는 공동체 서사 소재로 허용.</rule>
  <rule id="deep_not_wide">소재가 적을수록 새 소재를 추가하지 말고 있는 소재를 깊게 전개할 것.</rule>
</source_constraint>

<material_usage_lock priority="critical" description="입력 소재별 활용 범위 잠금">
  <rule id="identity_only">
    author, speaker_identity, stanceText 안의 정보 중 직책·지역 연고·현장 경험·주민 접점·활동 이력만 본문 구조의 중심 소재로 사용한다.
  </rule>
  <rule id="policy_not_section">
    정책명·사업명·바우처·수당·조례·시스템·플랫폼·지급·지원·구축·도입 같은 항목이 author나 stanceText에 보이더라도 본론 H2 주제로 삼지 않는다.
  </rule>
  <rule id="policy_cap">
    정책 항목은 전체 본문에서 최대 2개만, 각각 1문장 이내로 보조 근거로만 언급한다. 정책 카드 나열·열거·설명은 금지.
  </rule>
  <rule id="stance_handling">
    stanceText에 정책 표현이 많아도 그 정책을 본론 주제로 삼지 말고, 공동체 서사·화자의 책임·말할 자격을 설명하는 보조 문장으로만 사용한다.
  </rule>
</material_usage_lock>

<h2_examples priority="critical" description="본론 H2 형식 — 정책명 없이 사람·현장·책임 중심">
  <bad reason="질문형 + 정책어 동반">청년 자립 지원 방안은?</bad>
  <bad reason="정책 1개 H2 헌정 + 설명형">지역화폐, 골목경제 활력 불어넣는 이유</bad>
  <bad reason="정책 카드 나열">스마트 시스템 도입과 사업 확대</bad>
  <bad reason="질문형 종결">왜 이 지역이 변해야 하는가</bad>

  <good>이 거리에서 마주한 외로움</good>
  <good>골목에서 배운 책임</good>
  <good>주민 곁에 먼저 서겠습니다</good>
  <good>여기서 살아온 사람의 약속</good>
  <good>멈춘 심장을 다시 뛰게 한다</good>
</h2_examples>

<narrative_expansion_guide description="있는 소재로 분량을 만드는 방법">
  소재 하나를 3개 문단으로 전개하는 원칙:
  - 문단 1 (배경·현장): 이 소재가 존재하는 공간과 상황을 감각적으로 묘사
  - 문단 2 (화자의 접점): 화자가 이 현실을 어떻게 목격하거나 체험했는가
  - 문단 3 (책임과 다짐): 그래서 화자가 왜 지금 이 자리에 서 있는가

  입장문에 공동체 현실 묘사가 있는 경우: 그 내용을 직접 위 3문단으로 확장.
  입장문에 이미지·은유 표현만 있는 경우: 그 표현의 감정적 무게와 화자의 책임감을 풀어쓰되,
    구체적 사실은 지어내지 말 것. 이미지가 내포하는 공동체의 감정 상태를 서술.

  "분량을 버티는 것은 화자의 자의식이 아니라 공동체의 문제 서사다."
  새 소재를 추가하는 대신 있는 소재를 장면·감정·책임으로 세분화하는 것이 분량의 원칙.
</narrative_expansion_guide>

<emotion_arc description="섹션별 감정 역할">
  서론 (호명+상황): 공적 엄숙함·위기감·책임감 → 글 전체를 사적 자기 PR이 아닌 공적 발언으로 프레이밍
  본론 (자격+공동체): 자부심·현장성·공감 → 낯선 정치인이 아닌 이미 지역 안에 있던 사람으로 인식
  결론 (CTA): {_humble}, {_empathetic} → 부탁 전 몸을 낮춰 심리적 거부감을 줄인 뒤 직접 요청
</emotion_arc>

<writing_blueprint description="한국 정치 지지 호소 5단 구조">

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

  <component id="structure" name="5단 서사 구조">
    <section order="1" name="서론: 호명 + 상황 제시">
      "주민 여러분", "시민 여러분"처럼 독자를 먼저 부른다.
      자기소개보다 먼저 지금 이 말을 왜 해야 하는지 상황·책임감을 제시한다.
      공적 엄숙함으로 글 전체를 사적 PR이 아닌 공적 발언으로 프레이밍한다.
      일반 인삿말로 시작하지 말 것.
    </section>
    <section order="2" name="본론 1: 말할 자격" subheading="h2 소제목 필수 — 서사형·선언형, 질문형 금지">
      연고·현장 경험·활동 이력을 통해 "낯선 정치인이 아닌 이미 지역 안에 있던 사람"임을 증명한다.
      "이 지역에서 오래 살았다", "이 일을 오래 했다", "이 현장을 오래 봤다"가 이 섹션의 핵심.
      authorBio의 직함·경력·지역 연고를 narrative_expansion_guide의 3문단 전개법으로 깊게 펼친다.
    </section>
    <section order="3" name="본론 2: 공동체 서사" subheading="h2 소제목 필수 — 서사형·선언형, 질문형 금지">
      "우리 지역은 왜 지금 이 상태인가"를 화자의 눈으로 묘사한다.
      입장문에 공동체 현실 묘사가 있으면 그것을 3문단으로 확장한다.
      입장문에 이미지·은유만 있으면 그 표현의 감정적 무게를 풀어쓴다 — 없는 사실을 만들지 말 것.
      이 섹션이 분량의 핵심이다. 공동체 서사가 충분히 깊어야 독자가 화자를 신뢰한다.
    </section>
    <section order="4" name="본론 3: 핵심 증빙 (선택적)" subheading="h2 소제목 필수 — 서사형·선언형, 질문형 금지">
      입장문 또는 RAG에 정책·약속 소재가 있을 때만 작성한다.
      정책은 목록이 아니라 "이런 사람이기 때문에 이런 준비를 했다"는 사람 증명의 증거로 제시한다.
      소재가 없으면 이 섹션을 생략하고 2개 본론으로 완성한다.
    </section>
    <section order="5" name="결론: 겸손 + CTA">
      부탁하기 전에 먼저 감사와 겸손으로 몸을 낮춘다.
      마지막 문단에 직접 지지 요청 1~2문장이 반드시 있어야 한다.
      "~해 주십시오" 또는 "~해 주세요" 형식의 직접 요청.
    </section>

    <rules>
      <rule id="h2_style">H2 소제목은 서사형·선언형. 질문형("왜~", "어떻게~", "무엇이~") 금지.</rule>
      <rule id="body_count">본론은 2~3개. 소재 충분 시 3개, 부족 시 2개. 3개 강제 금지.</rule>
      <rule id="cta_mandatory">결론 마지막 문단에 직접 지지 호소 문장 없으면 불합격.</rule>
      <rule id="no_section_mini_conclusion">각 본론 말미에 "앞으로 ~하겠습니다" 식 미니 결론 금지. 다짐·호소는 결론에만.</rule>
      <rule id="structure_integrity">마무리 인사 후 본문 재시작 금지.</rule>
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
  <rule id="no_fabrication_check">입장문·프로필에 없는 구체적 사실이 생성되지 않았는지 확인</rule>
  <rule id="narrative_depth_check">본론 섹션이 새 소재 추가가 아닌 깊은 전개로 구성됐는지 확인</rule>
  <rule id="sentence_completeness">모든 문장 완전한 구조 확인</rule>
  <rule id="particles">조사 누락 절대 금지</rule>
</quality_verification>

<final_mission>
위 글쓰기 설계도에 따라, 입장문과 화자 프로필에 있는 소재만으로 진솔하고 설득력 있는 지지 호소 원고를 작성하라.
없는 사실을 만들어내지 말고, 있는 소재를 감각·감정·책임으로 깊게 전개하라.
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
