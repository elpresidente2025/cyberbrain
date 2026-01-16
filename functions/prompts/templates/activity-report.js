/**
 * functions/prompts/templates/activity-report.js
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
  PLEDGE_EMPHASIS: { id: 'pledge_emphasis', name: '주민 신뢰 강조', instruction: "'정책 방향을 분명히 제시합니다', '필요성을 강조합니다'처럼 공약성 표현 없이 책임감을 드러내어 진정성을 전달하세요." },
};

const VOCABULARY_MODULES = {
  FORMAL_AND_REPORTING: { id: 'formal_and_reporting', name: '공식/보고 어휘', thematic_guidance: "의정활동을 주민들께 보고하는 공식적인 톤을 유지하세요. '보고드립니다', '~를 확보했습니다', '성과를 거두었습니다', '노력해 보겠습니다' 등 신뢰감 있고 격식 있는 표현을 사용해야 합니다." },
  RELIABLE_AND_COMPETENT: { id: 'reliable_and_competent', name: '신뢰/유능함 어휘', thematic_guidance: "성과, 해결, 추진, 확보, 성공, 개선, 결실, 마침내, 드디어, 이뤄냈습니다 등 유능함과 신뢰를 보여주는 긍정적이고 힘있는 어휘를 사용하여 '일 잘하는 정치인' 이미지를 부각하세요." },
  LOCAL_AND_COMMUNITY: { id: 'local_and_community', name: '지역/공동체 어휘', thematic_guidance: "우리 동네, 주민 여러분, 골목상권, 아이들의 미래 등 지역 공동체에 대한 애정과 소속감이 드러나는 따뜻하고 구체적인 단어를 사용하세요." },
  RESOLUTE_AND_FIRM: { id: 'resolute_and_firm', name: '단호하고 확고한 어휘', thematic_guidance: "반드시, 원칙, 책임, 결단, 의지 등 흔들림 없는 신념을 보여주는 단호한 어휘를 사용하여 메시지에 대한 강한 신뢰감을 주어야 합니다." },
};

function buildActivityReportPrompt(options) {
  const {
    topic,
    authorBio,
    instructions,
    keywords,
    targetWordCount,
    personalizedHints,
    newsContext,
    declarativeStructureId,
    rhetoricalTacticId,
    vocabularyModuleId,
  } = options;

  const declarativeStructure = Object.values(DECLARATIVE_STRUCTURES).find(s => s.id === declarativeStructureId) || DECLARATIVE_STRUCTURES.GENERAL_ACTIVITY_REPORT;
  const rhetoricalTactic = Object.values(RHETORICAL_TACTICS).find(t => t.id === rhetoricalTacticId) || RHETORICAL_TACTICS.FACTS_AND_EVIDENCE;
  const vocabularyModule = Object.values(VOCABULARY_MODULES).find(m => m.id === vocabularyModuleId) || VOCABULARY_MODULES.FORMAL_AND_REPORTING;

  // 배경정보 포맷팅
  const backgroundSection = instructions ? `
[배경 정보 및 필수 포함 내용]
${Array.isArray(instructions) ? instructions.join('\n') : instructions}
` : '';

  // 맥락 키워드 포맷팅 (참고용)
  const keywordsSection = keywords && keywords.length > 0 ? `
[맥락 키워드 (참고용 - 삽입 강제 아님)]
${keywords.join(', ')}
→ 이 키워드들을 참고하여 글의 방향과 맥락을 잡으세요. 억지로 삽입할 필요 없습니다.
` : '';

  // 개인화 힌트 포맷팅
  const hintsSection = personalizedHints ? `
[개인화 가이드]
${personalizedHints}
` : '';

  // 뉴스 컨텍스트 포맷팅
  const newsSection = newsContext ? `
[참고 뉴스 (최신 정보 반영)]
${newsContext}
` : '';

  const prompt = `
# 전자두뇌비서관 - 의정활동 보고 원고 생성

[기본 정보]
- 작성자: ${authorBio}
- 글의 주제: "${topic}"
- 목표 분량: ${targetWordCount || 2000}자 (공백 제외)
${backgroundSection}${keywordsSection}${hintsSection}${newsSection}
[글쓰기 설계도]
너는 아래 3가지 부품을 조립하여, 매우 명확하고 신뢰감 있는 글을 만들어야 한다.

1.  **전체 뼈대 (보고 구조): ${declarativeStructure.name}**
    - 지시사항: ${declarativeStructure.instruction}

2.  **핵심 기술 (표현 전술): ${rhetoricalTactic.name}**
    - 지시사항: ${rhetoricalTactic.instruction}

3.  **표현 방식 (어휘 모듈): ${vocabularyModule.name}**
    - 어휘 테마: ${vocabularyModule.thematic_guidance}
    - 지시사항: 위 '어휘 테마'에 맞는 단어와 표현을 사용하여 글 전체의 톤앤매너를 형성하라.

[📝 출력 형식 및 품질 기준]
- **출력 구조**: 반드시 JSON 형식으로 출력. title, content, wordCount 필드 포함
- **HTML 가이드라인**: <p> 태그로 문단 구성, <h2>/<h3> 태그로 소제목, <ul>/<ol> 태그로 목록, <strong> 태그로 강조. CSS 인라인 스타일 절대 금지. **마크다운 형식(**, *, #, - 등) 절대 금지 - 반드시 HTML 태그만 사용**
- **톤앤매너**: 반드시 존댓말 사용 ("~입니다", "~합니다"). "저는", "제가" 사용. 서민적이고 친근한 어조 유지
- **예시 JSON 구조**:
\`\`\`json
{
  "title": "제목",
  "content": "<p>존댓말로 작성된 본문...</p><h2>소제목</h2><p>내용...</p>",
  "wordCount": 2000
}
\`\`\`

[🔍 품질 검증 필수사항]
다음 항목들을 반드시 확인하여 작성하라:
1. **문장 완결성**: 모든 문장이 완전한 구조를 갖추고 있는지 확인. 예시: "주민여하여" (X) → "주민 여러분께서" (O)
2. **조사/어미 검증**: "주민소리에" 같은 조사 누락 절대 금지. 예시: "주민소리에" (X) → "주민들의 소리에" (O)
3. **구체성 확보**: 괄호 안 예시가 아닌 실제 구체적 내용으로 작성. 예시: "(구체적 사례)" (X) → "지난 10월 12일 시흥시 체육관에서 열린" (O)
4. **논리적 연결**: 도입-전개-결론의 자연스러운 흐름 구성
5. **문체 일관성**: 존댓말 통일 및 어색한 표현 제거
6. **실제 내용 작성**: 모든 괄호 표현 제거하고 실제 구체적인 문장으로 작성
7. **반복 금지**: 동일하거나 유사한 문장, 문단을 절대 반복하지 말 것. 각 문장과 문단은 새로운 정보나 관점을 제공해야 함
8. **구조 일관성**: 마무리 인사("감사합니다", "~드림" 등) 후에는 절대로 본문이 다시 시작되지 않아야 함. 마무리는 글의 완전한 종결을 의미함
9. **[CRITICAL] 본론 섹션별 미니결론 금지**: 각 본론(H2) 섹션 끝에 "이러한 노력을 통해...", "이를 통해..." 식의 결론성 문장을 넣지 마라. 글 전체에서 결론은 **마지막 결론 섹션 하나**만 존재해야 한다.


[최종 임무]
위 '글쓰기 설계도'와 모든 규칙을 준수하여, 주어진 [기본 정보]와 [배경 정보]를 바탕으로 신뢰도 높고 완성도 있는 의정활동 보고 원고를 작성하라.
**[필수 키워드]에 명시된 모든 키워드를 원고에 자연스럽게 포함시켜야 한다.**
**반드시 JSON 형식으로만 출력하고, 코드 펜스(\`\`\`)는 사용하지 말 것.**
`;

  return prompt.trim();
}

module.exports = {
  buildActivityReportPrompt,
  DECLARATIVE_STRUCTURES,
  RHETORICAL_TACTICS,
  VOCABULARY_MODULES,
};
