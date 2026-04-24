// frontend/src/utils/electionExpressionCheck.js
// 선거법 형사 위반 표현 프론트엔드 사전 검사
// 공직선거법 제59조 3항: 온라인(SNS/블로그)은 선거운동 시기 제한 면제
// 형사처벌 대상(기부행위 제112조)만 매체·시기 불문 금지

const CRIMINAL_PATTERNS = [
  { pattern: /상품권.*?(지급|제공|드리)/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /선물.*?(지급|제공|드리)/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /금품/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /현금.*?(지급|제공|드리)/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /[0-9]+만\s*원\s*(지급|드리|제공)/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /경품/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /사은품/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /향응/, label: '기부행위 (형사)', suggestion: '삭제' },
  { pattern: /돈을?\s*드리/, label: '기부행위 (형사)', suggestion: '삭제' },
];

/**
 * 텍스트에서 형사 위반 표현을 검사한다.
 *
 * @param {string} text - 검사 대상 텍스트
 * @param {string} _status - 미사용 (하위 호환 유지)
 * @returns {Array<{matched: string, label: string, suggestion: string}>} 감지된 위반 목록
 */
export function checkElectionExpressions(text, _status) {
  if (!text || typeof text !== 'string') return [];

  const violations = [];
  const seen = new Set();

  for (const { pattern, label, suggestion } of CRIMINAL_PATTERNS) {
    const match = text.match(pattern);
    if (match) {
      const matched = match[0];
      if (!seen.has(matched)) {
        seen.add(matched);
        violations.push({ matched, label, suggestion });
      }
    }
  }

  return violations;
}

/**
 * 형사 위반 표현이 있는지 여부만 빠르게 확인
 */
export function hasElectionViolations(text, _status) {
  if (!text || typeof text !== 'string') return false;
  return CRIMINAL_PATTERNS.some(({ pattern }) => pattern.test(text));
}
