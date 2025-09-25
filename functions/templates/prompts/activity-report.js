/**
 * functions/templates/prompts/activity-report.js
 * '직설적 글쓰기' 작법에 기반한 의정활동 보고 전용 프롬프트 생성 모듈입니다.
 * (성과 보고, 입법 활동, 예산 확보 등)
 */

'use strict';

const DECLARATIVE_STRUCTURES = {
  GENERAL_ACTIVITY_REPORT: { id: 'general_activity_report', name: '일반 의정활동 보고 구조', instruction: "특정 의정활동에 대해 '활동 목표 → 구체적인 과정 및 성과 → 주민에게 미치는 긍정적 영향 및 향후 계획'의 순서로 체계적으로 보고하세요. 객관적인 사실을 기반으로 신뢰도를 높여야 합니다." },
  LEGISLATIVE_REPORT: { id: 'legislative_report', name: '입법 활동(조례/법안) 보고 구조', instruction: "발의한 조례나 법안에 대해 '입법 배경 및 현행 문제점 → 개정안의 핵심 내용 및 조문 설명 → 통과 시 기대효과 및 사회적 의미'의 3단계로 구성하여 전문성과 당위성을 강조하세요." },
  BUDGET_REPORT: { id: 'budget_report', name: '예산 확보 보고 구조', instruction: "확보한 예산에 대해 '지역 숙원 사업의 필요성 설명 → 예산 확보 과정의 어려움과 최종 규모 → 구체적인 사업 추진 계획 및 주민들이 체감할 변화' 순서로 구성하여 성과를 극대화하여 보여주세요." },
  PERFORMANCE_SHOWCASE_REPORT: { id: 'performance_showcase_report', name: '성과 중심 보고 구조', instruction: "글을 '지역의 오랜 문제/숙원 사업 제시 → 문제 해결을 위한 노력과 과정 설명 → 구체적인 성과와 결과 보고 → 이를 통해 주민들이 누리게 될 실질적인 혜택 설명'의 구조로 구성하여, 성과를 중심으로 체계적으로 전달하세요." },
  PRINCIPLE_DECLARATION: { id: 'principle_declaration', name: '의정활동 원칙 선언 구조', instruction: "글의 서두에서 당신이 의정활동에서 가장 중요하게 생각하는 '원칙'이나 '철학'(예: 현장 중심, 주민 소통)을 명확히 선언하고, 현재의 활동이 그 원칙에 어떻게 부합하는지를 설명하며 행동의 정당성을 부여해야 합니다." },
};

const RHETORICAL_TACTICS = {
  FACTS_AND_EVIDENCE: { id: 'facts_and_evidence', name: '사실과 근거 제시', instruction: "당신의 활동 성과를 뒷받침하기 위해 구체적인 데이터, 확보된 예산 액수, 조례 통과 현황 등 객관적인 사실과 수치를 명확하게 제시하여 주장의 신뢰도를 높이세요." },
  RELATING_TO_RESIDENTS: { id: 'relating_to_residents', name: '주민 생활 연결', instruction: "보고하는 성과가 '우리 아이들의 등하굣길이 안전해집니다', '어르신들이 더 편안하게 병원을 이용하실 수 있습니다'와 같이 주민들의 실생활에 어떤 긍정적인 변화를 가져오는지 구체적인 예시를 들어 설명하여 공감대를 형성하세요." },
  CREDIT_TAKING: { id: 'credit_taking', name: '성과 귀속 및 강조', instruction: "'제가 해냈습니다', '마침내 결실을 맺었습니다'와 같이 성과가 자신의 노력과 능력 덕분임을 명확히 하여 리더십을 부각시키세요. 경쟁 상대나 과거의 실패와 대비하여 성과의 의미를 극대화합니다." },
  PLEDGE_EMPHASIS: { id: 'pledge_emphasis', name: '주민 약속 강조', instruction: "'주민 여러분께 약속드립니다', '반드시 실천하겠습니다'와 같은 표현을 사용하여, 당신의 다짐이 단순한 계획이 아닌, 주민과의 굳은 약속임을 강조하여 진정성을 전달하세요." },
};

const VOCABULARY_MODULES = {
  FORMAL_AND_REPORTING: { id: 'formal_and_reporting', name: '공식/보고 어휘', thematic_guidance: "의정활동을 주민들께 보고하는 공식적인 톤을 유지하세요. '보고드립니다', '~를 확보했습니다', '성과를 거두었습니다', '노력하겠습니다' 등 신뢰감 있고 격식 있는 표현을 사용해야 합니다." },
  RELIABLE_AND_COMPETENT: { id: 'reliable_and_competent', name: '신뢰/유능함 어휘', thematic_guidance: "성과, 해결, 추진, 확보, 성공, 개선, 결실, 마침내, 드디어, 이뤄냈습니다 등 유능함과 신뢰를 보여주는 긍정적이고 힘있는 어휘를 사용하여 '일 잘하는 정치인' 이미지를 부각하세요." },
  LOCAL_AND_COMMUNITY: { id: 'local_and_community', name: '지역/공동체 어휘', thematic_guidance: "우리 동네, 주민 여러분, 골목상권, 아이들의 미래 등 지역 공동체에 대한 애정과 소속감이 드러나는 따뜻하고 구체적인 단어를 사용하세요." },
  RESOLUTE_AND_FIRM: { id: 'resolute_and_firm', name: '단호하고 확고한 어휘', thematic_guidance: "반드시, 원칙, 책임, 결단, 약속 등 흔들림 없는 의지와 신념을 보여주는 단호한 어휘를 사용하여 메시지에 대한 강한 신뢰감을 주어야 합니다." },
};

function buildActivityReportPrompt(options) {
  const {
    topic,
    authorBio,
    declarativeStructureId,
    rhetoricalTacticId,
    vocabularyModuleId,
  } = options;

  const declarativeStructure = Object.values(DECLARATIVE_STRUCTURES).find(s => s.id === declarativeStructureId) || DECLARATIVE_STRUCTURES.GENERAL_ACTIVITY_REPORT;
  const rhetoricalTactic = Object.values(RHETORICAL_TACTICS).find(t => t.id === rhetoricalTacticId) || RHETORICAL_TACTICS.FACTS_AND_EVIDENCE;
  const vocabularyModule = Object.values(VOCABULARY_MODULES).find(m => m.id === vocabularyModuleId) || VOCABULARY_MODULES.FORMAL_AND_REPORTING;

  const prompt = `
# 전자두뇌비서관 - 의정활동 보고 원고 생성

[기본 정보]
- 작성자: ${authorBio}
- 글의 주제: "${topic}"

[글쓰기 설계도]
너는 아래 3가지 부품을 조립하여, 매우 명확하고 신뢰감 있는 글을 만들어야 한다.

1.  **전체 뼈대 (보고 구조): ${declarativeStructure.name}**
    - 지시사항: ${declarativeStructure.instruction}

2.  **핵심 기술 (표현 전술): ${rhetoricalTactic.name}**
    - 지시사항: ${rhetoricalTactic.instruction}

3.  **표현 방식 (어휘 모듈): ${vocabularyModule.name}**
    - 어휘 테마: ${vocabularyModule.thematic_guidance}
    - 지시사항: 위 '어휘 테마'에 맞는 단어와 표현을 사용하여 글 전체의 톤앤매너를 형성하라.

[최종 임무]
위 '글쓰기 설계도'에 따라, 주어진 [기본 정보]를 바탕으로 신뢰도 높은 의정활동 보고 원고 초안을 작성하라.
`;

  return prompt.trim();
}

module.exports = {
  buildActivityReportPrompt,
  DECLARATIVE_STRUCTURES,
  RHETORICAL_TACTICS,
  VOCABULARY_MODULES,
};
