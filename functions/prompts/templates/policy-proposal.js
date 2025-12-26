/**
 * functions/prompts/templates/policy-proposal.js
 * '논리적 글쓰기' 작법 전용 프롬프트 생성 모듈입니다.
 * 정책 제안 및 비전 발표에 최적화되어 있습니다.
 */

'use strict';

const { getElectionStage } = require('../guidelines/legal');

const LOGICAL_STRUCTURES = {
  STEP_BY_STEP: { id: 'step_by_step', name: '단계적 논증 구조', instruction: "글을 '문제 제시 → 근거/원인 분석 → 명료한 결론'의 3단계로 명확하게 구성하세요. 각 단계가 논리적으로 연결되어 독자가 자연스럽게 결론에 도달하도록 이끌어야 합니다." },
  ENUMERATIVE: { id: 'enumerative', name: '열거식 병렬 구조', instruction: "하나의 핵심 주장을 뒷받침하는 여러 근거나 문제점을 '첫째, 둘째, 셋째...' 또는 글머리 기호 방식으로 조목조목 나열하세요. 다양한 각도에서 주장을 증명하여 논리의 깊이를 더해야 합니다." },
  PROBLEM_SOLUTION: { id: 'problem_solution', name: '문제 해결형 구조', instruction: "먼저 시급히 해결해야 할 문제를 명확히 제시하고, 이에 대한 구체적인 해결책을 제안한 뒤, 마지막으로 독자나 특정 대상의 행동(예: 동참, 시정)을 강력하게 촉구하는 흐름으로 글을 구성하세요." },
  CLIMACTIC_SANDWICH: { id: 'climactic_sandwich', name: '두괄식/양괄식 구조', instruction: "글의 가장 중요한 핵심 주장이나 결론을 첫 문단(두괄식) 또는 첫 문단과 마지막 문단(양괄식)에 배치하여 메시지를 강력하게 각인시키세요. 본문은 그 주장에 대한 부연 설명으로 채워야 합니다." },
  COMPREHENSIVE: { id: 'comprehensive', name: '포괄적 구성', instruction: "하나의 중심 주제를 설정하고, 관련된 다양한 각도의 논거, 통계, 국내외 사례, 현장 목소리 등을 풍부하게 제시하여 전체 그림을 보여주세요. 서론에서 제기한 문제를 결론에서 다시 한번 환기하며 깊이 있는 설득을 이끌어냅니다." },
  PRINCIPLE_BASED: { id: 'principle_based', name: '원칙 기반 논증', instruction: "법률적, 철학적, 혹은 헌법적 '원칙'을 먼저 제시하고, 현재의 사안이 그 원칙에 어떻게 부합하는지 혹은 위배되는지를 논증하세요. 과거의 유사 사례를 유추(analogy)하여 주장의 정당성을 강화하는 방식을 사용합니다." },
};

const ARGUMENTATION_TACTICS = {
  EVIDENCE_CITATION: { id: 'evidence_citation', name: '사례 및 데이터 인용', instruction: "당신의 주장을 뒷받침할 수 있는 구체적인 통계, 연구 결과, 실제 사례, 전문가 의견 등을 풍부하게 인용하여 글의 객관성과 신뢰도를 높여야 합니다." },
  ANALOGY: { id: 'analogy', name: '유추 기반 논증', instruction: "과거의 유사한 역사적 사례나 다른 영역의 원칙을 끌어와 현재의 문제에 적용(유추)하여 주장의 정당성을 확보하세요. 독자가 익숙한 사례를 통해 새로운 문제를 쉽게 이해하도록 돕습니다." },
  BENEFIT_EMPHASIS: { id: 'benefit_emphasis', name: '기대효과 강조', instruction: "정책이 시행되었을 때 국민들의 삶이 어떻게 긍정적으로 변화하는지를 구체적인 예시와 함께 생생하게 묘사하세요. '만약 ~된다면, 우리 아이들은...'과 같이 미래의 긍정적 모습을 그려주어 설득력을 높입니다." },
};

const VOCABULARY_MODULES = {
  POLICY_ANALYSIS: { id: 'policy_analysis', name: '정책 분석 어휘', thematic_guidance: "객관적이고 신뢰감 있는 정책 전문가의 톤을 유지하세요. '통계에 따르면', '장기적인 관점에서', '체계적인 접근', '합리적인 대안' 등 분석적이고 전문적인 어휘를 사용해야 합니다." },
  RATIONAL_PERSUASION: { id: 'rational_persuasion', name: '합리적 설득 어휘', thematic_guidance: "독자를 가르치려 하지 말고, 차분하고 논리적인 어조로 설득하세요. '함께 고민해볼 문제입니다', '우리가 주목해야 할 부분은', '더 나은 방향은' 등 합리적이고 균형 잡힌 어휘를 사용하세요." },
  VISION_AND_HOPE: { id: 'vision_and_hope', name: '비전과 희망 어휘', thematic_guidance: "미래에 대한 긍정적인 비전과 희망을 담은 어휘를 사용하세요. '새로운 미래를 열겠습니다', '희망의 씨앗을 심겠습니다', '함께 꿈꾸는 대한민국' 등 진취적이고 포용적인 표현을 사용합니다." },
  ACTION_URGING: { id: 'action_urging', name: '행동 촉구 어휘', thematic_guidance: "강력하고 호소력 있는 어조로 독자들의 행동과 참여를 유도하세요. '지금 바로 행동해야 합니다', '여러분의 힘이 필요합니다', '함께 바꿔나갑시다' 등 동기를 부여하는 어휘를 사용하세요." }
};

function buildLogicalWritingPrompt(options) {
  const {
    topic,
    authorBio,
    instructions,
    keywords,
    targetWordCount,
    personalizedHints,
    newsContext,
    logicalStructureId,
    argumentationTacticId,
    vocabularyModuleId,
    currentStatus,  // 사용자 상태 (준비/현역/예비/후보)
  } = options;

  // 선거법 준수 지시문 생성
  const electionStage = getElectionStage(currentStatus);
  const electionComplianceSection = electionStage && electionStage.promptInstruction
    ? `
╔═══════════════════════════════════════════════════════════════╗
║  🚨 선거법 준수 필수 - 위반 시 법적 책임 발생 🚨                  ║
╚═══════════════════════════════════════════════════════════════╝
${electionStage.promptInstruction}
---
`
    : '';

  const logicalStructure = Object.values(LOGICAL_STRUCTURES).find(s => s.id === logicalStructureId) || LOGICAL_STRUCTURES.STEP_BY_STEP;
  const argumentationTactic = Object.values(ARGUMENTATION_TACTICS).find(t => t.id === argumentationTacticId) || ARGUMENTATION_TACTICS.EVIDENCE_CITATION;
  const vocabularyModule = Object.values(VOCABULARY_MODULES).find(m => m.id === vocabularyModuleId) || VOCABULARY_MODULES.RATIONAL_PERSUASION;

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
# 전자두뇌비서관 - 논리적 글쓰기 원고 생성 (정책/비전)

${electionComplianceSection}
[기본 정보]
- 작성자: ${authorBio}
- 글의 주제: "${topic}"
- 목표 분량: ${targetWordCount || 1700}자 (공백 제외)
${backgroundSection}${keywordsSection}${hintsSection}${newsSection}
[글쓰기 설계도]
너는 아래 3가지 부품을 조립하여, 매우 체계적이고 설득력 있는 글을 만들어야 한다.

1.  **전체 뼈대 (논리 구조): ${logicalStructure.name}**
    - 지시사항: ${logicalStructure.instruction}

2.  **핵심 기술 (논증 전술): ${argumentationTactic.name}**
    - 지시사항: ${argumentationTactic.instruction}

3.  **표현 방식 (어휘 모듈): ${vocabularyModule.name}**
    - 어휘 테마: ${vocabularyModule.thematic_guidance}
    - 지시사항: 위 '어휘 테마'에 맞는 단어와 표현을 사용하여 글 전체의 톤앤매너를 형성하라.

[📝 출력 형식 및 품질 기준]
- **출력 구조**: 반드시 JSON 형식으로 출력. title, content, wordCount 필드 포함
- **HTML 가이드라인**: <p> 태그로 문단 구성, <h2>/<h3> 태그로 소제목, <ul>/<ol> 태그로 목록, <strong> 태그로 강조. CSS 인라인 스타일 절대 금지
- **톤앤매너**: 반드시 존댓말 사용 ("~입니다", "~합니다"). "저는", "제가" 사용. 합리적이고 설득력 있는 어조 유지
- **예시 JSON 구조**:
\`\`\`json
{
  "title": "제목",
  "content": "<p>존댓말로 작성된 논리적인 본문...</p><h2>소제목</h2><p>내용...</p>",
  "wordCount": 2050
}
\`\`\`

[🔍 품질 검증 필수사항]
다음 항목들을 반드시 확인하여 작성하라:
1. **문장 완결성**: 모든 문장이 완전한 구조를 갖추고 있는지 확인
2. **조사/어미 검증**: 조사 누락 절대 금지
3. **구체성 확보**: 괄호 안 예시가 아닌 실제 구체적 내용으로 작성
4. **논리적 연결**: 도입-전개-결론의 자연스러운 흐름 구성
5. **문체 일관성**: 존댓말 통일 및 어색한 표현 제거
6. **실제 내용 작성**: 모든 괄호 표현 제거하고 실제 구체적인 문장으로 작성
7. **반복 금지**: 동일하거나 유사한 문장, 문단을 절대 반복하지 말 것. 각 문장과 문단은 새로운 정보나 관점을 제공해야 함
8. **구조 일관성**: 마무리 인사("감사합니다", "~드림" 등) 후에는 절대로 본문이 다시 시작되지 않아야 함. 마무리는 글의 완전한 종결을 의미함

[최종 임무]
위 '글쓰기 설계도'와 모든 규칙을 준수하여, 주어진 [기본 정보]와 [배경 정보]를 바탕으로 논리정연하고 설득력 있으며 완성도 높은 원고를 작성하라.
**[필수 키워드]에 명시된 모든 키워드를 원고에 자연스럽게 포함시켜야 한다.**
**반드시 JSON 형식으로만 출력하고, 코드 펜스(\`\`\`)는 사용하지 말 것.**
`;

  return prompt.trim();
}

module.exports = {
  buildLogicalWritingPrompt,
  LOGICAL_STRUCTURES,
  ARGUMENTATION_TACTICS,
  VOCABULARY_MODULES,
};
