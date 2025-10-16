'use strict';

/**
 * 공백 제외 글자수 계산 (Java 코드와 동일한 로직)
 * @param {string} str - 계산할 문자열
 * @returns {number} 공백을 제외한 글자수
 */
function countWithoutSpace(str) {
  if (!str) return 0;
  let count = 0;
  for (let i = 0; i < str.length; i++) {
    if (!/\s/.test(str.charAt(i))) {
      count++;
    }
  }
  return count;
}

/**
 * 성공 응답 헬퍼
 */
const ok = (data) => ({ success: true, ...data });

/**
 * 메시지 응답 헬퍼
 */
const okMessage = (message) => ({ success: true, message });

/**
 * 자연스러운 지역명 호칭 생성 (모두 붙여쓰기)
 */
function generateNaturalRegionTitle(regionLocal, regionMetro) {
  if (!regionLocal && !regionMetro) return '';

  const primaryRegion = regionLocal || regionMetro;

  // 🔧 수정: 순서 중요 - 더 구체적인 패턴부터 체크
  if (primaryRegion.includes('광역시')) {
    return primaryRegion + '민';
  }

  if (primaryRegion.includes('특별시')) {
    return primaryRegion + '민';
  }

  // 🔧 추가: '구' 체크 (예: 계양구 → 계양구민)
  if (primaryRegion.endsWith('구')) {
    return primaryRegion + '민';
  }

  if (primaryRegion.includes('시')) {
    return primaryRegion + '민';
  }

  if (primaryRegion.includes('군')) {
    return primaryRegion + '민';
  }

  // '도'는 마지막에 체크 (경기도, 강원도 등)
  if (primaryRegion.includes('도')) {
    return primaryRegion + '민';
  }

  // 그 외 default
  return primaryRegion + '민';
}

module.exports = {
  countWithoutSpace,
  ok,
  okMessage,
  generateNaturalRegionTitle
};
