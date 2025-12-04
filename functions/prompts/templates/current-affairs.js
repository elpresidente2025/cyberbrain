/**
 * functions/prompts/templates/current-affairs.js
 * '비판적 글쓰기' 작법 전용 프롬프트 생성 모듈입니다.
 */

'use strict';

// ============================================================================
// 작성 예시 (사용자가 실제 내용을 채워넣을 템플릿)
// ============================================================================

const WRITING_EXAMPLES = {
  // TODO: 실제 좋은 원고로 교체 필요
  SOLUTION_FIRST: `
**참고 예시 - 대안 우선 구조**

배경정보: [정책/인물/사건에 대한 구체적 정보]

생성 결과:
\`\`\`json
{
  "title": "[제목]",
  "content": "<p>존경하는 [지역] 여러분, [이름]입니다.</p><h2>[대안 제목 - 이렇게 해야 합니다]</h2><p>[구체적 대안: 수치, 연도, 계획 포함]</p><h2>[비판 제목 - 그런데 현재는]</h2><p>[문제 지적 및 대비]</p><h2>[다짐 제목]</h2><p>[대안 재강조]</p>",
  "wordCount": 1800
}
\`\`\`

위 예시처럼:
- 대안을 먼저 제시 (구체적 수치 포함)
- 그 다음 문제를 대비시킴
- 마지막에 다짐으로 대안 재강조
`,

  PROBLEM_FIRST: `
**참고 예시 - 문제 우선 구조 (전통적)**

배경정보: [문제 상황에 대한 구체적 정보]

생성 결과:
\`\`\`json
{
  "title": "[제목]",
  "content": "<p>존경하는 [지역] 여러분, [이름]입니다.</p><h2>[문제 제목]</h2><p>[문제 현상 및 데이터]</p><h2>[원인 분석]</h2><p>[왜 이런 일이 발생했는가]</p><h2>[대안 제시]</h2><p>[구체적 해결 방안]</p>",
  "wordCount": 1800
}
\`\`\`
`
};

// 비판 구조에 따라 관련 예시 선택
function getRelevantExample(criticalStructureId) {
  if (criticalStructureId === 'solution_first_criticism') {
    return WRITING_EXAMPLES.SOLUTION_FIRST;
  } else if (criticalStructureId === 'problem_first_criticism' || criticalStructureId === 'policy_failure_criticism') {
    return WRITING_EXAMPLES.PROBLEM_FIRST;
  }
  // 기본값: 대안 우선 예시
  return WRITING_EXAMPLES.SOLUTION_FIRST;
}

const CRITICAL_STRUCTURES = {
  // 🆕 대안 우선 비판 구조 (두괄식) - 기본값으로 사용
  SOLUTION_FIRST_CRITICISM: {
    id: 'solution_first_criticism',
    name: '대안 우선 비판 구조 (두괄식)',
    instruction: `글을 다음 3단계로 구성하세요:

1. **대안 제시 (앞 40%, 구체적으로)**
   - 먼저 "이렇게 해야 합니다"를 명확히 제시
   - 구체적 수치, 연도, 계획 포함 (예: "2025년까지", "3만개 일자리", "5천억 투자")
   - 독자에게 "이 사람은 준비된 리더"라는 인상을 각인

2. **문제 지적 (중간 40%, 대비 강화)**
   - "그런데 현재는/상대방은 이렇게 하고 있습니다"로 전환
   - 앞서 제시한 올바른 방법과 대비시켜 상대의 무능/무책임 부각
   - 팩트 기반으로 냉정하게 비판

3. **다짐 강화 (뒤 20%, 재확인)**
   - 대안을 다시 한 번 강조하며 마무리
   - "저는 준비되어 있습니다", "성과로 보여드리겠습니다"

**핵심:** 독자가 기억하는 것은 "비판받는 사람"이 아니라 "대안을 가진 당신"이어야 합니다.`
  },

  MEDIA_FRAME_CRITICISM: { id: 'media_frame_criticism', name: '언론 프레이밍 비판 구조', instruction: "글을 '문제 보도 인용 → 숨은 의도 및 프레임 지적 → 대중에게 질문'의 3단계로 구성하세요. 언론의 보도가 단순한 실수가 아닌, 의도적인 프레임을 갖고 있음을 암시하며 여론전을 유도해야 합니다." },

  FACT_CHECK_REBUTTAL: { id: 'fact_check_rebuttal', name: '가짜뉴스 반박 구조', instruction: "글을 '허위 주장 요약 → 명백한 사실/데이터 제시 → 법적/정치적 책임 경고'의 순서로 구성하세요. 감정적 대응을 자제하고, 명확한 증거를 통해 상대 주장의 신뢰도를 완전히 무너뜨려야 합니다." },

  PROBLEM_FIRST_CRITICISM: { id: 'problem_first_criticism', name: '문제 우선 비판 구조 (전통식)', instruction: "글을 '문제 현상 제시 → 데이터/통계를 통한 원인 분석 → 구체적인 정책 대안 촉구'의 흐름으로 구성하세요. 단순한 비난이 아닌, 대안을 가진 책임 있는 비판의 모습을 보여주어야 합니다." },

  // 하위 호환성을 위해 유지 (PROBLEM_FIRST_CRITICISM과 동일)
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
    instructions,
    keywords,
    targetWordCount,
    personalizedHints,
    newsContext,
    criticalStructureId,
    offensiveTacticId,
    vocabularyModuleId,
  } = options;

  const criticalStructure = Object.values(CRITICAL_STRUCTURES).find(s => s.id === criticalStructureId) || CRITICAL_STRUCTURES.SOLUTION_FIRST_CRITICISM;
  const offensiveTactic = Object.values(OFFENSIVE_TACTICS).find(t => t.id === offensiveTacticId) || OFFENSIVE_TACTICS.EXPOSING_CONTRADICTION;
  const vocabularyModule = Object.values(VOCABULARY_MODULES).find(m => m.id === vocabularyModuleId) || VOCABULARY_MODULES.LEGAL_FACTUAL;

  // 🆕 관련 예시 가져오기
  const relevantExample = getRelevantExample(criticalStructure.id);

  const backgroundSection = instructions ? `
[배경 정보 및 필수 포함 내용]
${Array.isArray(instructions) ? instructions.join('\n') : instructions}
` : '';

  const keywordsSection = keywords && keywords.length > 0 ? `
[필수 키워드 (반드시 원고에 포함할 것)]
${keywords.join(', ')}
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
# 전자두뇌비서관 - 비판적 글쓰기 원고 생성

[기본 정보]
- 작성자: ${authorBio}
- 글의 주제: "${topic}"
- 목표 분량: ${targetWordCount || 1700}자 (공백 제외)
${backgroundSection}${keywordsSection}${hintsSection}${newsSection}

[📖 참고: 올바른 작성 예시]
${relevantExample}

---
⚠️ **중요:** 위 예시의 구조와 스타일을 참고하되, 제공된 [배경 정보]를 바탕으로 완전히 새로운 원고를 작성하라.
배경정보를 그대로 복사하지 말고, 자연스럽게 재구성하여 본론에 녹여내라.
---

[🚫 절대 원칙: 사실 기반 글쓰기 (Hallucination Guardrail)]
- 너는 절대로 사실을 지어내거나 추측해서는 안 된다.
- 모든 비판과 주장은 오직 사용자가 [기본 정보] 및 [배경 정보]에 제공한 내용에만 100% 근거해야 한다.
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

[📊 SEO 최적화 규칙]
- **필수 분량**: 1800~2300자 (공백 제외, 목표: 2050자)
- **키워드 배치**: 본문 400자당 1회, 맥락에 맞게 자연스럽게 포함 (키워드 스터핑 금지)
- **구조화**: h2 태그 2-3개, h3 태그 3-5개로 소제목 구성, 문단 6-8개 (각 150-250자)

[📝 출력 형식 및 품질 기준]
- **출력 구조**: 반드시 JSON 형식으로 출력. title, content, wordCount 필드 포함
- **HTML 가이드라인**: <p> 태그로 문단 구성, <h2>/<h3> 태그로 소제목, <ul>/<ol> 태그로 목록, <strong> 태그로 강조. CSS 인라인 스타일 절대 금지
- **톤앤매너**: 반드시 존댓말 사용 ("~입니다", "~합니다"). "저는", "제가" 사용. 비판적이되 논리적인 어조 유지
- **예시 JSON 구조**:
\`\`\`json
{
  "title": "제목",
  "content": "<p>존댓말로 작성된 비판적 본문...</p><h2>소제목</h2><p>내용...</p>",
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
7. **사실 기반 비판**: 제공된 정보에만 근거한 비판, 추측이나 날조 금지
8. **반복 금지**: 동일하거나 유사한 문장, 문단을 절대 반복하지 말 것. 각 문장과 문단은 새로운 정보나 관점을 제공해야 함
9. **구조 일관성**: 마무리 인사("감사합니다", "~드림" 등) 후에는 절대로 본문이 다시 시작되지 않아야 함. 마무리는 글의 완전한 종결을 의미함

[최종 임무]
위 '절대 원칙'과 '글쓰기 설계도', 그리고 모든 규칙을 준수하여, 주어진 [기본 정보]와 [배경 정보]를 바탕으로 논리정연하고 강력하며 완성도 높은 비판 원고를 작성하라.
**[필수 키워드]에 명시된 모든 키워드를 원고에 자연스럽게 포함시켜야 한다.**
**반드시 JSON 형식으로만 출력하고, 코드 펜스(\`\`\`)는 사용하지 말 것.**
`;

  return prompt.trim();
}

module.exports = {
  buildCriticalWritingPrompt,
  CRITICAL_STRUCTURES,
  OFFENSIVE_TACTICS,
  VOCABULARY_MODULES,
};
