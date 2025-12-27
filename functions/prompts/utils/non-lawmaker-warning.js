/**
 * functions/prompts/utils/non-lawmaker-warning.js
 * 원외 인사 경고 및 가족 상황 경고 섹션 생성 유틸리티
 */

'use strict';

/**
 * 원외 인사 경고 섹션 생성
 * @param {Object} params
 * @param {boolean} params.isCurrentLawmaker - 현역 의원 여부
 * @param {string} params.politicalExperience - 정치 경험
 * @param {string} params.authorBio - 작성자 정보
 * @returns {string} 경고 섹션 (원외 인사가 아니면 빈 문자열)
 */
function generateNonLawmakerWarning({ isCurrentLawmaker, politicalExperience, authorBio }) {
  // 현역 의원이면 경고 불필요
  if (isCurrentLawmaker !== false || politicalExperience !== '정치 신인') {
    return '';
  }

  return `

╔═══════════════════════════════════════════════════════════════╗
║  🚫 작성자 신분 설정 (원고에 명시 금지)                          ║
╚═══════════════════════════════════════════════════════════════╝

작성자: ${authorBio}
(이 정보는 글쓰기 톤 설정용입니다. 원고 본문에 절대 노출하지 마세요.)

[사용 금지 표현]
❌ "의원", "국회의원", "의정활동", "의원으로서" - 본인이 의원이 아니므로
❌ "지역구" - 국회의원 전용 용어 ("우리 지역", "이 지역" 등으로 대체)

[원고에 절대 포함하지 말 것]
❌ "저는 정치 신인입니다만", "저는 국회의원이 아닙니다만" 등 신분 고백
❌ "시민의 입장에서", "지역 주민의 한 사람으로서" 같은 화자 위치 명시
❌ "광역자치단체장 준비 중", "시장 준비 중" 등 준비 상태 언급
❌ 위 작성자 정보를 원고 본문에 그대로 복사하는 행위

→ 작성자 신분은 글의 톤과 시점을 결정하는 태그입니다.
→ 원고는 자연스럽게 해당 위치에서 말하듯 작성하되, 신분 자체를 언급하지 마세요.

`;
}

/**
 * 가족 상황 경고 섹션 생성
 * @param {Object} params
 * @param {string} params.familyStatus - 가족 상황 ('미혼', '기혼(자녀 있음)', '기혼(자녀 없음)', '한부모')
 * @returns {string} 경고 섹션 (경고가 필요하면 경고 문자열, 아니면 빈 문자열)
 */
function generateFamilyStatusWarning({ familyStatus }) {
  if (!familyStatus) {
    return '';
  }

  // 자녀가 없는 경우 명확한 경고
  if (familyStatus === '기혼(자녀 없음)' || familyStatus === '미혼') {
    return `

╔═══════════════════════════════════════════════════════════════╗
║  ⚠️  가족 상황 확인 - 절대 준수 필수! ⚠️                        ║
╚═══════════════════════════════════════════════════════════════╝

** 작성자는 자녀가 없습니다 **

가족 상황: ${familyStatus}

[절대 금지 사항]
❌ "자녀", "아이", "아들", "딸" 등 자녀 관련 표현 절대 금지
❌ "자녀 양육", "육아", "자녀 교육", "부모로서" 등의 표현 절대 금지
❌ "아버지로서", "어머니로서" 등 부모 정체성 표현 절대 금지
❌ 자녀가 있다고 가정하거나 암시하는 어떠한 내용도 금지

[작성 가이드]
✅ 작성자의 실제 가족 상황에 맞는 내용만 작성
✅ 개인적 경험을 언급할 때도 자녀 관련 내용은 절대 포함하지 말 것

`;
  }

  return '';
}

module.exports = {
  generateNonLawmakerWarning,
  generateFamilyStatusWarning
};
