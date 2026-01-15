// functions/prompts/guidelines/seo.js
// SEO 최적화 및 품질 검증 지침 생성기
// - 글자수 규칙
// - 키워드 삽입 규칙
// - 반복 금지 규칙 (v2 강화)

'use strict';

const { SEO_RULES } = require('./editorial');

/**
 * 키워드별 필수 삽입 횟수 계산
 * @param {number} targetWordCount - 목표 글자수
 * @returns {number} 키워드당 최소 삽입 횟수
 */
function calculateMinInsertions(targetWordCount) {
  // [수정] 네이버 SEO 로직 변경: 글자수 무관하게 최소 4회, 최대 6회 유지
  return 4;  // 항상 4 리턴
}

/**
 * 키워드 배치 구간 계산
 * @param {number} minInsertions - 최소 삽입 횟수
 * @returns {Object} 구간별 삽입 횟수 { intro, body, conclusion }
 */
function calculateDistribution(minInsertions) {
  if (minInsertions <= 2) {
    return { intro: 1, body: 1, conclusion: 0 };
  } else if (minInsertions <= 4) {
    return { intro: 1, body: 2, conclusion: 1 };
  } else {
    const intro = Math.ceil(minInsertions * 0.25);
    const conclusion = Math.ceil(minInsertions * 0.25);
    const body = minInsertions - intro - conclusion;
    return { intro, body, conclusion };
  }
}

/**
 * SEO 최적화 지침 생성
 * 프롬프트 최상단에 주입되어 AI가 반드시 따르도록 강제
 *
 * @param {Object} params
 * @param {Array<string>} params.keywords - 필수 삽입 키워드 목록
 * @param {number} params.targetWordCount - 목표 글자수
 * @returns {string} 프롬프트에 주입할 SEO 지침
 */
function buildSEOInstruction({ keywords, targetWordCount }) {
  const { min, max } = SEO_RULES.wordCount;  // 1500, 2300 고정
  const target = targetWordCount || SEO_RULES.wordCount.target;
  const minInsertions = calculateMinInsertions(target);
  const distribution = calculateDistribution(minInsertions);

  // 키워드 섹션 (키워드가 있을 때만)
  let keywordSection = '';
  if (keywords && keywords.length > 0) {
    const keywordTable = keywords.map((keyword, index) => {
      return `   ${index + 1}. "${keyword}" → ${minInsertions}회 이상`;
    }).join('\n');

    keywordSection = `
┌─────────────────────────────────────────────────────────────┐
│  2. 키워드 삽입 규칙                                         │
└─────────────────────────────────────────────────────────────┘

[필수 삽입 키워드]
${keywordTable}

[배치 방법] (총 ${minInsertions}회를 본문 전체에 분산)
• 도입부 (첫 2문단): 각 키워드 ${distribution.intro}회
• 본론 (중간 문단들): 각 키워드 ${distribution.body}회
• 결론 (마지막 2문단): 각 키워드 ${distribution.conclusion}회

[삽입 방법]
✅ 자연스러운 문장 내 삽입:
   - 주어 위치: "${keywords[0]}은(는) 이번 행사에서..."
   - 목적어 위치: "...에서 ${keywords[0]}을(를) 논의했습니다."
   - 수식어 위치: "${keywords[0]}의 성과로..."
   - 인용 위치: "...라고 ${keywords[0]}에서 밝혔습니다."

❌ 금지 사항:
   - 동일 문단에 같은 키워드 2회 이상 반복
   - 키워드만 나열하는 스터핑: "${keywords[0]} ${keywords[0]} ${keywords[0]}"
   - 띄어쓰기 임의 변경 (검색 노출 실패 원인)
`;
  }

  return `
████████████████████████████████████████████████████████████████
█                    [SEO 최적화 규칙]                         █
█          이 규칙은 다른 모든 규칙보다 우선합니다              █
████████████████████████████████████████████████████████████████

⚠️ 아래 규칙을 위반하면 원고가 폐기됩니다.

┌─────────────────────────────────────────────────────────────┐
│  1. 글자수 규칙 (공백 제외)                                  │
└─────────────────────────────────────────────────────────────┘

   최소: ${min}자
   최대: ${max}자

   ⚠️ ${min}자 미만 또는 ${max}자 초과 시 원고 폐기
${keywordSection}
┌─────────────────────────────────────────────────────────────┐
│  작성 전 체크리스트                                          │
└─────────────────────────────────────────────────────────────┘

□ 글자수 ${min}~${max}자 범위를 준수하며 작성할 것
${keywords && keywords.length > 0 ? `□ 각 키워드를 ${minInsertions}회씩 자연스럽게 배치할 것
□ 키워드가 도입부/본론/결론에 고르게 분산되었는지 확인할 것` : ''}
□ 도입-본론-결론 구조로 내용을 구성할 것

████████████████████████████████████████████████████████████████

`;
}

/**
 * 반복 금지 및 품질 규칙 지침 생성
 * SEO 지침과 함께 프롬프트 최상단에 배치
 *
 * @returns {string} 반복 금지 지침
 */
function buildAntiRepetitionInstruction() {
  return `
██████████████████████████████████████████████████████████████████
█  🚫 [반복 금지 규칙] - 위반 시 원고 폐기 🚫                      █
██████████████████████████████████████████████████████████████████

⚠️ 다음 규칙을 위반하면 생성된 원고가 자동 폐기됩니다.

┌─────────────────────────────────────────────────────────────────┐
│  1. 동일 문장 반복 절대 금지                                      │
└─────────────────────────────────────────────────────────────────┘

❌ 금지 예시:
   "박 시장은 설명해야 할 책임이 있습니다."
   "박 시장은 설명해야 할 책임이 있습니다." ← 같은 문장 2회 = 폐기

✅ 올바른 예시:
   각 문장은 반드시 새로운 정보나 관점을 담아야 합니다.
   표현만 살짝 바꾼 유사 문장도 반복으로 간주됩니다.

┌─────────────────────────────────────────────────────────────────┐
│  2. 유사 문단 반복 금지                                          │
└─────────────────────────────────────────────────────────────────┘

❌ 금지:
   - 같은 주장을 표현만 바꿔서 여러 번 반복
   - 결론에서 본문 내용을 다시 요약하며 분량 채우기
   - 비슷한 구조의 문장을 연속으로 나열

✅ 1문단 1메시지 원칙:
   - 각 문단은 하나의 핵심 메시지만 전달
   - 새 문단은 반드시 새로운 정보 포함
   - 할 말이 없으면 짧게 마무리 (억지로 늘리지 말 것)

┌─────────────────────────────────────────────────────────────────┐
│  3. 구조 일관성                                                  │
└─────────────────────────────────────────────────────────────────┘

마무리 인사("감사합니다", "~드림" 등) 이후에는 본문이 절대 다시 시작되면 안 됩니다.
마무리가 나오면 거기서 글이 완전히 종료됩니다.

┌─────────────────────────────────────────────────────────────────┐
│  📋 작성 전 자가 점검 체크리스트                                  │
└─────────────────────────────────────────────────────────────────┘

□ 같은 문장이 2번 이상 등장하지 않는가?
□ 비슷한 내용을 표현만 바꿔 반복하지 않았는가?
□ 각 문단이 새로운 정보를 담고 있는가?
□ 마무리 인사 이후에 본문이 다시 시작되지 않는가?

██████████████████████████████████████████████████████████████████

`;
}

module.exports = {
  buildSEOInstruction,
  buildAntiRepetitionInstruction,
  calculateMinInsertions,
  calculateDistribution
};
