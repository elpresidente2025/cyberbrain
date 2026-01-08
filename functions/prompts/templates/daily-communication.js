/**
 * functions/prompts/templates/daily-communication.js
 * '감성적 글쓰기' 작법 전용 프롬프트 생성 모듈입니다.
 */

'use strict';

const EMOTIONAL_ARCHETYPES = {
  PERSONAL_NARRATIVE: { id: 'personal_narrative', name: '개인 서사형', instruction: "당신의 개인적인 경험, 특히 어려움을 극복했거나 특별한 깨달음을 얻었던 순간의 서사를 진솔하게 풀어내세요. 독자가 당신의 삶의 한 조각을 직접 엿보는 것처럼 느끼게 하여 인간적인 공감대를 형성해야 합니다." },
  COMMUNITY_APPEAL: { id: 'community_appeal', name: '공동체 정서 호명형', instruction: "시민들, 또는 특정 집단을 '우리'로 명확히 호명하고, 그들이 공유하는 집단적 기억이나 감정(예: 분노, 슬픔, 희망)을 직접적으로 자극하세요. 공동의 목표를 향한 연대와 결속을 강화하는 메시지를 전달해야 합니다." },
  POETIC_LYRICISM: { id: 'poetic_lyricism', name: '시적 서정형', instruction: "직설적인 표현 대신, 문학적 비유, 상징, 서정적인 묘사를 사용하여 당신의 감정을 은유적으로 표현하세요. 한 편의 시나 수필처럼, 독자에게 깊은 감성적 여운을 남겨야 합니다." },
  STORYTELLING_PERSUASION: { id: 'storytelling_persuasion', name: '사연 설득형', instruction: "당신이 직접 겪거나 들은 제3자의 구체적인 사연을 한 편의 이야기처럼 생생하게 전달하세요. 독자가 그 이야기의 주인공에게 감정적으로 이입하게 만들어, 당신이 전달하려는 메시지를 자연스럽게 설득시켜야 합니다." },
  EMOTIONAL_INTERPRETATION: { id: 'emotional_interpretation', name: '감정 해석형', instruction: "현재 상황이나 특정 사건을 '두려움', '억울함', '희망' 등 당신이 느끼는 감정의 틀로 직접 해석하여 제시하세요. 사실을 나열하는 대신, 당신의 감정을 통해 독자들이 상황의 본질을 감정적으로 이해하도록 이끌어야 합니다." },
  PLEA_AND_PETITION: { id: 'plea_and_petition', name: '호소와 탄원형', instruction: "당신의 진심과 절박함을 담아, 독자들에게 관심, 동참, 또는 의견을 겸손하고 간절하게 호소하세요. '도와주십시오', '죄송합니다'와 같이 낮은 자세와 진솔한 마음을 직접적으로 드러내어 독자의 마음을 움직여야 합니다." },
};

const NARRATIVE_FRAMES = {
  OVERCOMING_HARDSHIP: { id: 'overcoming_hardship', name: '고난 극복 서사', instruction: '당신의 과거 힘들었던 시절(역경, 실패 등)을 구체적으로 묘사하고, 그것을 어떻게 극복하여 현재의 신념을 가지게 되었는지 이야기의 흐름을 만드세요.' },
  RELENTLESS_FIGHTER: { id: 'relentless_fighter', name: '강인한 투사 서사', instruction: '현재 우리가 맞서 싸워야 할 대상(예: 불공정, 부조리)을 명확히 설정하고, 이에 굴하지 않고 끝까지 전진하겠다는 강한 의지를 보여주는 서사를 구성하세요.' },
  SERVANT_LEADER: { id: 'servant_leader', name: '서민의 동반자 서사', instruction: '스스로를 ‘평범한 사람들의 보호자’로 위치시키고, ‘월급봉투’, ‘아이들의 안전’ 등 서민들의 삶과 직결된 구체적인 요소를 지켜내겠다는 다짐을 중심으로 이야기를 풀어가세요.' },
  YOUTH_REPRESENTATIVE: { id: 'youth_representative', name: '청년 세대 대표 서사', instruction: '당신의 힘들었던 청년 시절의 에피소드를 통해, 현재 청년들이 겪는 문제에 깊이 공감하고 있음을 보여주고 그들의 목소리를 대변하겠다는 의지를 밝히세요.' }
};

const VOCABULARY_MODULES = {
  HARDSHIP_AND_FAMILY: { id: 'hardship_and_family', name: '고난과 가족', thematic_guidance: "가족의 소중함, 과거의 어려움과 역경, 그리고 그것을 이겨내는 과정에서의 희생과 극복의 감정이 느껴지는 어휘를 사용하세요. (예: '어머니의 헌신', '힘들었던 시절', '그럼에도 불구하고')" },
  REFORM_AND_STRUGGLE: { id: 'reform_and_struggle', name: '개혁과 투쟁', thematic_guidance: "사회적 부조리에 맞서는 투쟁, 정의를 바로 세우려는 개혁 의지, 그리고 그 과정에서의 어려움과 전진의 느낌을 주는 단어를 사용하세요. (예: '기득권의 저항', '반드시 바로잡겠습니다', '한 걸음 더 나아가')" },
  SOLIDARITY_AND_PEOPLE: { id: 'solidarity_and_people', name: '연대와 서민', thematic_guidance: "'우리'라는 공동체 의식과 연대, 평범한 사람들의 삶을 지키겠다는 다짐, 그리고 함께할 때 더 나아질 수 있다는 희망을 담은 따뜻한 어휘를 사용하세요. (예: '함께 손잡고', '평범한 이웃들의', '더 나은 내일을 위해')" },
  RESPONSIBILITY_AND_PLEDGE: { id: 'responsibility_and_pledge', name: '책임과 의지', thematic_guidance: "리더로서의 책임감과 의지를 드러내되 공약성 표현은 피하고, 중립적으로 방향을 제시하는 어휘를 사용하세요. (예: '책임 있게 살펴보겠습니다', '끝까지 챙기겠습니다', '함께 방향을 잡아가겠습니다')" },
  SINCERITY_AND_APPEAL: { id: 'sincerity_and_appeal', name: '진정성과 호소', thematic_guidance: "자신을 낮추는 겸손함, 잘못에 대한 진솔한 성찰, 그리고 독자들에게 진심으로 도움을 구하는 절박함이 느껴지는 호소력 있는 어휘를 사용하세요. (예: '저의 부족함입니다', '깊이 성찰하겠습니다', '여러분의 힘이 필요합니다')" }
};

function buildDailyCommunicationPrompt(options) {
  const {
    topic,
    authorBio,
    instructions,
    keywords,
    targetWordCount,
    personalizedHints,
    newsContext,
    narrativeFrameId,
    emotionalArchetypeId,
    vocabularyModuleId,
  } = options;

  const narrativeFrame = Object.values(NARRATIVE_FRAMES).find(f => f.id === narrativeFrameId) || NARRATIVE_FRAMES.SERVANT_LEADER;
  const emotionalArchetype = Object.values(EMOTIONAL_ARCHETYPES).find(a => a.id === emotionalArchetypeId) || EMOTIONAL_ARCHETYPES.PERSONAL_NARRATIVE;
  const vocabularyModule = Object.values(VOCABULARY_MODULES).find(m => m.id === vocabularyModuleId) || VOCABULARY_MODULES.SOLIDARITY_AND_PEOPLE;

  const backgroundSection = instructions ? `
[배경 정보 및 필수 포함 내용]
${Array.isArray(instructions) ? instructions.join('\n') : instructions}
` : '';

  const keywordsSection = keywords && keywords.length > 0 ? `
[맥락 키워드 (참고용 - 삽입 강제 아님)]
${keywords.join(', ')}
→ 이 키워드들을 참고하여 글의 방향과 맥락을 잡으세요. 억지로 삽입할 필요 없습니다.
` : '';

  const hintsSection = personalizedHints ? `
[개인화 가이드]
${personalizedHints}
` : '';

  const newsSection = newsContext ? `
[참고 뉴스 (최신 정보 반영)]
${newsContext}
` : '';

  const prompt = `
# 전자두뇌비서관 - 일상 소통 원고 생성

╔═══════════════════════════════════════════════════════════════════════╗
║ 🎭 [CRITICAL] 화자 정체성 - 절대 혼동 금지!                              ║
╚═══════════════════════════════════════════════════════════════════════╝

**당신은 "${authorBio}"입니다. 이 글의 유일한 1인칭 화자입니다.**

[필수 규칙]
1. 이 글은 철저히 **1인칭 시점**으로 작성합니다. "저는", "제가"를 사용하세요.
2. 참고 자료(뉴스, 배경 정보)에 다른 인물의 발언이나 행동이 있더라도, **그 사람이 화자인 척 하지 마세요**.
   - ❌ 잘못된 예: "후원회장을 맡게 되었습니다" (당신이 후원회장이 아니라면 이렇게 쓰면 안 됨)
   - ✅ 올바른 예: "OOO 배우님께서 후원회장을 맡아주셨습니다"
3. 참고 자료에 등장하는 타인은 반드시 **3인칭**으로 언급하세요.
4. 글의 처음부터 끝까지 화자(${authorBio})의 관점을 일관되게 유지하세요.
5. 서명/인사도 반드시 화자 이름으로 마무리하세요.

[기본 정보]
- 작성자(화자): ${authorBio}
- 글의 주제: "${topic}"
- 목표 분량: ${targetWordCount || 1700}자 (공백 제외)
${backgroundSection}${keywordsSection}${hintsSection}${newsSection}
[글쓰기 설계도]
너는 아래 3가지 부품을 조립하여 하나의 완성된 글을 만들어야 한다.

1.  **뼈대 (서사 프레임): ${narrativeFrame.name}**
    - 지시사항: ${narrativeFrame.instruction}

2.  **감정 (감성 원형): ${emotionalArchetype.name}**
    - 지시사항: ${emotionalArchetype.instruction}

3.  **어휘 (주제어 가이드): ${vocabularyModule.name}**
    - 어휘 테마: ${vocabularyModule.thematic_guidance}
    - 지시사항: 위 '어휘 테마'에 맞는 단어와 표현을 창의적으로 사용하여 글 전체의 분위기를 형성하라.

4.  **구조 전략 (Standard 5-Step Structure)**
    - **핵심 규칙**: AEO 최적화와 안정감을 위해 **[서론 - 본론1 - 본론2 - 본론3 - 결론]**의 5단 구조를 반드시 준수하라.
    - 입력된 핵심 소재가 적더라도(1~2개), 이를 세분화하거나 관련 내용을 보강하여 반드시 **3개의 본론(Body Paragraphs)**을 채워라.
    - **구조 가이드**:
      1.  **[서론]**: 인사, 문제 제기, 공감 형성
      2.  **[본론 1]** (<h2>소제목 필수</h2>): 첫 번째 핵심 주장 / 현황 분석
      3.  **[본론 2]** (<h2>소제목 필수</h2>): 두 번째 핵심 주장 / 구체적 해결책
      4.  **[본론 3]** (<h2>소제목 필수</h2>): 세 번째 핵심 주장 / 미래 비전 및 기대효과
      5.  **[결론]**: 요약, 다짐, 마무리 인사

[📝 출력 형식 및 품질 기준]
- **출력 구조**: 반드시 JSON 형식으로 출력. title, content, wordCount 필드 포함
- **HTML 가이드라인**: <p> 태그로 문단 구성, <h2>/<h3> 태그로 소제목, <ul>/<ol> 태그로 목록, <strong> 태그로 강조. CSS 인라인 스타일 절대 금지. **마크다운 형식(**, *, #, - 등) 절대 금지 - 반드시 HTML 태그만 사용**
- **톤앤매너**: 반드시 존댓말 사용 ("~입니다", "~합니다"). "저는", "제가" 사용. 서민적이고 친근하며 진솔한 어조 유지
- **예시 JSON 구조**:
\`\`\`json
{
  "title": "제목",
  "content": "<p>존댓말로 작성된 진솔한 본문...</p><h2>소제목</h2><p>내용...</p>",
  "wordCount": 2050
}
\`\`\`

[🔍 품질 검증 필수사항]
다음 항목들을 반드시 확인하여 작성하라:
1. **문장 완결성**: 모든 문장이 완전한 구조를 갖추고 있는지 확인. 예시: "주민여하여" (X) → "주민 여러분께서" (O)
2. **조사/어미 검증**: "주민소리에" 같은 조사 누락 절대 금지. 예시: "주민소리에" (X) → "주민들의 소리에" (O)
3. **구체성 확보**: 괄호 안 예시가 아닌 실제 구체적 내용으로 작성. 예시: "(구체적 사례)" (X) → "지난 10월 12일 시흥시 체육관에서 열린" (O)
4. **날짜/시간 정보 보존**: 주제에 구체적인 날짜나 시간이 명시되어 있으면 반드시 그대로 사용할 것. "10월 12일 일요일" (O), "10월의 어느 날" (X)
5. **논리적 연결**: 도입-전개-결론의 자연스러운 흐름 구성
6. **문체 일관성**: 존댓말 통일 및 어색한 표현 제거
7. **실제 내용 작성**: 모든 괄호 표현 제거하고 실제 구체적인 문장으로 작성
8. **감정 진정성**: 형식적인 표현이 아닌, 진심이 느껴지는 구체적인 감정 표현 사용
9. **반복 금지**: 동일하거나 유사한 문장, 문단을 절대 반복하지 말 것. 각 문장과 문단은 새로운 정보나 관점을 제공해야 함
10. **구조 일관성**: 마무리 인사("감사합니다", "~드림" 등) 후에는 절대로 본문이 다시 시작되지 않아야 함. 마무리는 글의 완전한 종결을 의미함

[최종 임무]
위 '글쓰기 설계도'와 모든 규칙을 준수하여, 주어진 [기본 정보]와 [배경 정보]를 바탕으로 진솔하고 울림 있으며 완성도 높은 SNS 원고를 작성하라.
**반드시 JSON 형식으로만 출력하고, 코드 펜스(\`\`\`)는 사용하지 말 것.**
`;

  return prompt.trim();
}

module.exports = {
  buildDailyCommunicationPrompt,
  EMOTIONAL_ARCHETYPES,
  NARRATIVE_FRAMES,
  VOCABULARY_MODULES,
};
