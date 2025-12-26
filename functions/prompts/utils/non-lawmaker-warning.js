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
║  ⚠️  작성자 신분 확인 - 절대 준수 필수! ⚠️                      ║
╚═══════════════════════════════════════════════════════════════╝

** 작성자는 국회의원이 아닙니다 **

작성자: ${authorBio}
정치 경험: 정치 신인 (국회의원 경험 없음)

[절대 금지 사항]
❌ "의원", "국회의원", "지역구 의원", "지역구 국회의원" 등의 표현 사용 금지
❌ "의정활동", "국회 활동", "의원 경력", "의원으로서" 등 언급 금지
❌ "256명의 국회의원 중..." 같은 맥락에서 본인을 의원으로 암시하거나 동일시하는 표현 금지
❌ **"지역구" 표현 절대 금지** - "지역구 발전", "지역구 주민", "지역구 현안" 등 모두 불가
   (이유: "지역구"는 국회의원 전용 용어. 광역/기초지자체장은 사용 불가)

[작성 가이드]
✅ 작성자의 실제 직위(지역위원장 등)를 사용하세요
✅ 지역 활동, 준비 과정, 정책 연구, 주민과의 소통 등을 중심으로 작성
✅ 타 의원을 비판할 때도 "같은 의원으로서"가 아닌 "시민의 입장에서", "지역 주민의 한 사람으로서" 관점 유지
✅ "부산시민", "사하구 주민" 등 지역명 + 시민/주민 표현 사용

[원고에 절대 포함하지 말 것]
❌ "준비 중", "OO 준비 중" - 이런 표현을 원고 본문에 절대 사용 금지
❌ "광역자치단체장 준비 중", "기초자치단체장 준비 중" 등 직접적인 신분 표현 금지
❌ 작성자의 현재 상태(준비/예비)를 원고에 직접 노출하지 말 것

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
