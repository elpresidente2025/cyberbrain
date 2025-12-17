// functions/prompts/guidelines/seo.js
// SEO 최적화 지침 생성기
// - 글자수 규칙
// - 키워드 삽입 규칙

'use strict';

const { SEO_RULES } = require('./editorial');

/**
 * 키워드별 필수 삽입 횟수 계산
 * @param {number} targetWordCount - 목표 글자수
 * @returns {number} 키워드당 최소 삽입 횟수
 */
function calculateMinInsertions(targetWordCount) {
  const interval = SEO_RULES.keywordPlacement.body.interval; // 400
  return Math.max(2, Math.floor(targetWordCount / interval));
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

module.exports = {
  buildSEOInstruction,
  calculateMinInsertions,
  calculateDistribution
};
