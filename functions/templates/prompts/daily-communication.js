/**
 * functions/templates/prompts/daily-communication.js
 * '감성적 글쓰기' 작법 전용 프롬프트 생성 모듈입니다.
 */

'use strict';

const EMOTIONAL_ARCHETYPES = {
  PERSONAL_NARRATIVE: { id: 'personal_narrative', name: '개인 서사형', instruction: "당신의 개인적인 경험, 특히 어려움을 극복했거나 특별한 깨달음을 얻었던 순간의 서사를 진솔하게 풀어내세요. 독자가 당신의 삶의 한 조각을 직접 엿보는 것처럼 느끼게 하여 인간적인 공감대를 형성해야 합니다." },
  COMMUNITY_APPEAL: { id: 'community_appeal', name: '공동체 정서 호명형', instruction: "지지자들, 또는 특정 집단을 '우리'로 명확히 호명하고, 그들이 공유하는 집단적 기억이나 감정(예: 분노, 슬픔, 희망)을 직접적으로 자극하세요. 공동의 목표를 향한 연대와 결속을 강화하는 메시지를 전달해야 합니다." },
  POETIC_LYRICISM: { id: 'poetic_lyricism', name: '시적 서정형', instruction: "직설적인 표현 대신, 문학적 비유, 상징, 서정적인 묘사를 사용하여 당신의 감정을 은유적으로 표현하세요. 한 편의 시나 수필처럼, 독자에게 깊은 감성적 여운을 남겨야 합니다." },
  STORYTELLING_PERSUASION: { id: 'storytelling_persuasion', name: '사연 설득형', instruction: "당신이 직접 겪거나 들은 제3자의 구체적인 사연을 한 편의 이야기처럼 생생하게 전달하세요. 독자가 그 이야기의 주인공에게 감정적으로 이입하게 만들어, 당신이 전달하려는 메시지를 자연스럽게 설득시켜야 합니다." },
  EMOTIONAL_INTERPRETATION: { id: 'emotional_interpretation', name: '감정 해석형', instruction: "현재 상황이나 특정 사건을 '두려움', '억울함', '희망' 등 당신이 느끼는 감정의 틀로 직접 해석하여 제시하세요. 사실을 나열하는 대신, 당신의 감정을 통해 독자들이 상황의 본질을 감정적으로 이해하도록 이끌어야 합니다." },
  PLEA_AND_PETITION: { id: 'plea_and_petition', name: '호소와 탄원형', instruction: "당신의 진심과 절박함을 담아, 독자들에게 지지, 동참, 또는 용서를 겸손하고 간절하게 호소하세요. '도와주십시오', '죄송합니다' 와 같이 당신의 낮은 자세와 진솔한 마음을 직접적으로 드러내어 독자의 마음을 움직여야 합니다." },
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
  RESPONSIBILITY_AND_PLEDGE: { id: 'responsibility_and_pledge', name: '책임과 약속', thematic_guidance: "리더로서의 무거운 책임감, 국민과의 약속을 반드시 지키겠다는 결단, 그리고 미래를 향한 확고한 의지가 드러나는 신뢰감 있는 어휘를 사용하세요. (예: '제가 책임지겠습니다', '반드시 해내겠습니다', '미래를 열겠습니다')" },
  SINCERITY_AND_APPEAL: { id: 'sincerity_and_appeal', name: '진정성과 호소', thematic_guidance: "자신을 낮추는 겸손함, 잘못에 대한 진솔한 성찰, 그리고 지지자들에게 진심으로 도움을 구하는 절박함이 느껴지는 호소력 있는 어휘를 사용하세요. (예: '저의 부족함입니다', '깊이 성찰하겠습니다', '여러분의 힘이 필요합니다')" }
};

function buildDailyCommunicationPrompt(options) {
  const {
    topic,
    authorBio,
    narrativeFrameId,
    emotionalArchetypeId,
    vocabularyModuleId,
  } = options;

  const narrativeFrame = Object.values(NARRATIVE_FRAMES).find(f => f.id === narrativeFrameId) || NARRATIVE_FRAMES.SERVANT_LEADER;
  const emotionalArchetype = Object.values(EMOTIONAL_ARCHETYPES).find(a => a.id === emotionalArchetypeId) || EMOTIONAL_ARCHETYPES.PERSONAL_NARRATIVE;
  const vocabularyModule = Object.values(VOCABULARY_MODULES).find(m => m.id === vocabularyModuleId) || VOCABULARY_MODULES.SOLIDARITY_AND_PEOPLE;

  const prompt = `
# 전자두뇌비서관 - 일상 소통 원고 생성

[기본 정보]
- 작성자: ${authorBio}
- 글의 주제: "${topic}"

[글쓰기 설계도]
너는 아래 3가지 부품을 조립하여 하나의 완성된 글을 만들어야 한다.

1.  **뼈대 (서사 프레임): ${narrativeFrame.name}**
    - 지시사항: ${narrativeFrame.instruction}

2.  **감정 (감성 원형): ${emotionalArchetype.name}**
    - 지시사항: ${emotionalArchetype.instruction}

3.  **어휘 (주제어 가이드): ${vocabularyModule.name}**
    - 어휘 테마: ${vocabularyModule.thematic_guidance}
    - 지시사항: 위 '어휘 테마'에 맞는 단어와 표현을 창의적으로 사용하여 글 전체의 분위기를 형성하라.

[최종 임무]
위 '글쓰기 설계도'에 따라, 주어진 [기본 정보]를 바탕으로 진솔하고 울림 있는 SNS 원고 초안을 작성하라.
`;

  return prompt.trim();
}

module.exports = {
  buildDailyCommunicationPrompt,
  EMOTIONAL_ARCHETYPES,
  NARRATIVE_FRAMES,
  VOCABULARY_MODULES,
};
