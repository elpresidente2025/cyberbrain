/**
 * functions/templates/prompts/current-affairs.js
 * '비판적 글쓰기' 작법 전용 프롬프트 생성 모듈입니다.
 */

'use strict';

const CRITICAL_STRUCTURES = {
  MEDIA_FRAME_CRITICISM: { id: 'media_frame_criticism', name: '언론 프레이밍 비판 구조', instruction: "글을 '문제 보도 인용 → 숨은 의도 및 프레임 지적 → 대중에게 질문'의 3단계로 구성하세요. 언론의 보도가 단순한 실수가 아닌, 의도적인 프레임을 갖고 있음을 암시하며 여론전을 유도해야 합니다." },
  FACT_CHECK_REBUTTAL: { id: 'fact_check_rebuttal', name: '가짜뉴스 반박 구조', instruction: "글을 '허위 주장 요약 → 명백한 사실/데이터 제시 → 법적/정치적 책임 경고'의 순서로 구성하세요. 감정적 대응을 자제하고, 명확한 증거를 통해 상대 주장의 신뢰도를 완전히 무너뜨려야 합니다." },
  POLICY_FAILURE_CRITICISM: { id: 'policy_failure_criticism', name: '정책 실패 비판 구조', instruction: "글을 '문제 현상 제시 → 데이터/통계를 통한 원인 분석 → 구체적인 정책 대안 촉구'의 흐름으로 구성하세요. 단순한 비난이 아닌, 대안을 가진 책임 있는 비판의 모습을 보여주어야 합니다." },
  OFFICIAL_MISCONDUCT_CRITICISM: { id: 'official_misconduct_criticism', name: '공직자 비위 비판 구조', instruction: "글을 '의혹 사실 요약 → 법적/윤리적 문제점 지적 → 사퇴/징계 등 구체적인 책임 요구' 순으로 구성하세요. 개인적인 비난이 아닌, 공직자로서의 책임을 묻는다는 점을 명확히 해야 합니다." },
};

const OFFENSIVE_TACTICS = {
  METAPHORICAL_STRIKE: { id: 'metaphorical_strike', name: '은유와 상징을 통한 공격', instruction: "비판 대상을 부정적인 의미를 가진 단어나 상황(예: '커밍아웃', '소설쓰기')에 빗대어 표현하세요. 직접적인 비난보다 더 큰 모욕감과 압박감을 주는 효과를 노립니다." },
  INDIRECT_CRITICISM_BY_SHARING: { id: 'indirect_criticism_by_sharing', name: '기사/타인 글 공유를 통한 간접 비판', instruction: "당신의 입장과 유사한 제3자(언론, 전문가 등)의 글을 공유한 뒤, '이 정도일 줄은 몰랐다'와 같이 짧은 코멘트를 덧붙여 비판의 책임을 분산시키고 객관성을 확보하는 전략을 사용하세요." },
  SATIRE_AND_PARODY: { id: 'satire_and_parody', name: '풍자와 패러디를 통한 조롱', instruction: "상대방의 행동이나 발언을 익살스럽게 따라하거나(패러디), 과장하여 웃음거리로 만드세요. 이를 통해 상대의 권위를 실추시키고, 지지층에게는 카타르시스를 제공합니다." },
  EXPOSING_CONTRADICTION: { id: 'exposing_contradiction', name: '내로남불/모순 지적', instruction: "상대방이 과거에 했던 발언이나 행동을 현재의 입장과 비교하여, 그들의 모순과 이중성을 명확하게 드러내세요. '그들 자신의 논리'로 그들을 공격하여 반박의 여지를 차단합니다." },
};

const VOCABULARY_MODULES = {
  AGGRESSIVE_ATTACK: { id: 'aggressive_attack', name: '공격적/도발적 어휘', thematic_guidance: "강하고 때로는 자극적인 단어를 사용하여 이슈를 선점하고 주목도를 높이세요. '망언', '내란', '참사', '심판' 등 선명하고 단호한 표현으로 비판의 강도를 극대화합니다." },
  LEGAL_FACTUAL: { id: 'legal_factual', name: '법률적/사실적 어휘', thematic_guidance: "감정적 표현을 배제하고, 법률 용어, 통계, 데이터 등 객관적인 사실에만 기반하여 비판하세요. '직권남용', '허위사실공표', '통계에 따르면' 등 차분하고 논리적인 표현으로 신뢰도를 높입니다." },
  SARCASTIC_IRONIC: { id: 'sarcastic_ironic', name: '풍자적/반어적 어휘', thematic_guidance: "상대방을 비꼬거나 반어적인 표현을 사용하여 비판의 날을 세우세요. '대단한 업적', '그냥 웃습니다', '잘하는 짓이다' 등 우회적인 표현으로 상대의 권위를 조롱합니다." },
  FORMAL_OFFICIAL: { id: 'formal_official', name: '공식적/점잖은 어휘', thematic_guidance: "공식적인 입장문이나 논평의 격식을 갖추어 비판하세요. '깊은 유감을 표합니다', '~할 것을 촉구합니다', '매우 우려스럽습니다' 등 절제되고 품위 있는 표현을 사용합니다." }
};

function buildCriticalWritingPrompt(options) {
  const {
    topic,
    authorBio,
    criticalStructureId,
    offensiveTacticId,
    vocabularyModuleId,
  } = options;

  const criticalStructure = Object.values(CRITICAL_STRUCTURES).find(s => s.id === criticalStructureId) || CRITICAL_STRUCTURES.POLICY_FAILURE_CRITICISM;
  const offensiveTactic = Object.values(OFFENSIVE_TACTICS).find(t => t.id === offensiveTacticId) || OFFENSIVE_TACTICS.EXPOSING_CONTRADICTION;
  const vocabularyModule = Object.values(VOCABULARY_MODULES).find(m => m.id === vocabularyModuleId) || VOCABULARY_MODULES.LEGAL_FACTUAL;

  const prompt = `
# 전자두뇌비서관 - 비판적 글쓰기 원고 생성

[기본 정보]
- 작성자: ${authorBio}
- 글의 주제 (사용자 제공 사실): "${topic}"

[🚫 절대 원칙: 사실 기반 글쓰기 (Hallucination Guardrail)]
- 너는 절대로 사실을 지어내거나 추측해서는 안 된다.
- 모든 비판과 주장은 오직 사용자가 [기본 정보]의 '글의 주제'에 제공한 내용에만 100% 근거해야 한다.
- 만약 사용자가 구체적인 사실, 통계, 인용문을 제공했다면 그것을 반드시 활용하라.
- 만약 사용자가 구체적인 사실을 제공하지 않았다면, 사실을 날조하지 말고 원칙적인 수준의 비판만 수행하라.
- 법적 문제가 발생할 수 있는 민감한 작법이므로, 이 원칙은 반드시 지켜져야 한다.

[글쓰기 설계도]
너는 아래 3가지 부품을 조립하여, 매우 날카롭고 설득력 있는 비판의 글을 만들어야 한다.

1.  **전체 뼈대 (비판 구조): ${criticalStructure.name}**
    - 지시사항: ${criticalStructure.instruction}

2.  **핵심 기술 (공격 전술): ${offensiveTactic.name}**
    - 지시사항: ${offensiveTactic.instruction}

3.  **표현 방식 (어휘 모듈): ${vocabularyModule.name}**
    - 어휘 테마: ${vocabularyModule.thematic_guidance}
    - 지시사항: 위 '어휘 테마'에 맞는 단어와 표현을 사용하여 글 전체의 톤앤매너를 형성하라.

[최종 임무]
위 '절대 원칙'과 '글쓰기 설계도'에 따라, 주어진 [기본 정보]를 바탕으로 논리정연하고 강력한 비판 원고 초안을 작성하라.
`;

  return prompt.trim();
}

module.exports = {
  buildCriticalWritingPrompt,
  CRITICAL_STRUCTURES,
  OFFENSIVE_TACTICS,
  VOCABULARY_MODULES,
};
