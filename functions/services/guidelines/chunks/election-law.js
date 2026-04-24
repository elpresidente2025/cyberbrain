/**
 * functions/services/guidelines/chunks/election-law.js
 * 선거법 준수 지침 청크
 *
 * 공직선거법 제59조 3항: 온라인(SNS/블로그)은 선거운동 시기 제한 면제.
 * 형사처벌 대상(기부행위·허위사실·후보자비방)만 매체·시기 불문 금지.
 */

'use strict';

const ELECTION_LAW_CHUNKS = [
  // ============================================================================
  // MEDIUM: 기부행위 금지 (제112조) — 모든 단계 적용
  // ============================================================================
  {
    id: 'EL-020',
    type: 'election_law',
    priority: 'MEDIUM',
    applies_to: {},
    keywords: ['금품', '향응', '매수', '상품권', '경품'],
    instruction: '기부행위 금지: 금품/향응/상품권 제공 암시 표현 사용 불가 (공직선거법 제112조)',
    forbidden: ['금품', '향응', '돈을 드리', '상품권 지급', '경품 제공', '사은품'],
    examples: [
      { bad: '당선되면 금품을 드리겠습니다', good: '(불법 — 사용 불가)' }
    ],
    replacements: {}
  }
];

/**
 * 상태별 적용 가능한 청크 필터링
 */
function getChunksForStatus(status) {
  return ELECTION_LAW_CHUNKS.filter(chunk => {
    const s = chunk.applies_to.status;
    return !s || s.length === 0 || s.includes(status);
  });
}

module.exports = {
  ELECTION_LAW_CHUNKS,
  getChunksForStatus
};
