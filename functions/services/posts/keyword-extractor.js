'use strict';

/**
 * 배경정보에서 필수 키워드 추출
 * @param {string|Array} instructions - 배경정보
 * @returns {Array<string>} 추출된 키워드 목록
 */
function extractKeywordsFromInstructions(instructions) {
  if (!instructions) return [];

  const text = Array.isArray(instructions) ? instructions.join(' ') : instructions;
  const keywords = [];

  // 1. 숫자+단위 추출 (예: 300여명, 500명, 1000개, 2회)
  const numberMatches = text.match(/[0-9]+여?[명개회건차명월일년원]/g);
  if (numberMatches) keywords.push(...numberMatches);

  // 2. 인명 + 직책 패턴 (예: 홍길동 의원, 김철수 위원장, 홍길동 경기도당위원장)
  const nameWithTitleMatches = text.match(/[가-힣]{2,4}\s+(?:경기도당위원장|국회의원|위원장|의원|시장|도지사|장관|총리|대통령)/g);
  if (nameWithTitleMatches) {
    keywords.push(...nameWithTitleMatches);
    // 이름만 별도 추출 (검증 시 부분 매칭용)
    nameWithTitleMatches.forEach(match => {
      const nameOnly = match.match(/([가-힣]{2,4})\s+/);
      if (nameOnly && nameOnly[1]) keywords.push(nameOnly[1]);
    });
  }

  // 3. 조직명 패턴 (예: 경기도당, 서울시당, 교육위원회)
  const orgMatches = text.match(/[가-힣]{2,}(?:도당|시당|구당|위원회|재단|협회|연합|위원회)/g);
  if (orgMatches) keywords.push(...orgMatches);

  // 4. 이벤트명 패턴 (예: 체육대회, 토론회, 간담회)
  const eventMatches = text.match(/[가-힣]{2,}(?:대회|행사|토론회|간담회|설명회|세미나|워크숍|회의|집회|축제)/g);
  if (eventMatches) keywords.push(...eventMatches);

  // 5. 지명 패턴 (예: 서울특별시, 경기도, 수원시)
  const placeMatches = text.match(/[가-힣]{2,}(?:특별시|광역시|도|시|군|구|읍|면|동)/g);
  if (placeMatches) keywords.push(...placeMatches);

  // 6. 연도/날짜 (예: 2024년, 2025년)
  const yearMatches = text.match(/20[0-9]{2}년/g);
  if (yearMatches) keywords.push(...yearMatches);

  // 7. 정책/법안명 (예: OO법, OO정책, OO사업)
  const policyMatches = text.match(/[가-힣]{2,}(?:법|조례|정책|사업|계획|방안)/g);
  if (policyMatches) keywords.push(...policyMatches);

  // 중복 제거 및 반환
  return [...new Set(keywords)];
}

module.exports = {
  extractKeywordsFromInstructions
};
