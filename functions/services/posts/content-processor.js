'use strict';

/**
 * AI가 생성한 원고에 대한 후처리 및 보정
 * @param {Object} params
 * @param {string} params.content - 생성된 원고 내용
 * @param {string} params.fullName - 작성자 이름
 * @param {string} params.fullRegion - 지역명
 * @param {string} params.currentStatus - 현재 상태 (현역/예비/준비)
 * @param {Object} params.userProfile - 사용자 프로필
 * @param {Object} params.config - 상태별 설정
 * @param {string} params.customTitle - 사용자 지정 직위 (선택)
 * @param {string} params.displayTitle - 표시할 직위 (customTitle 또는 config.title)
 * @param {boolean} params.isCurrentLawmaker - 현역 의원 여부
 * @returns {string} 수정된 원고 내용
 */
function processGeneratedContent({ content, fullName, fullRegion, currentStatus, userProfile, config, customTitle, displayTitle, isCurrentLawmaker }) {
  console.log('🔩 후처리 시작 - 필수 정보 강제 삽입');

  if (!content) return content;

  let fixedContent = content;

  // 🔥 원외 인사의 경우 강력한 "의원" 표현 제거
  if (isCurrentLawmaker === false) {
    console.log('⚠️ 원외 인사 감지 - "의원" 및 "지역구" 표현 강력 제거 시작');

    // "국회의원", "지역구 국회의원" 등 제거
    fixedContent = fixedContent.replace(/국회\s*의원/g, fullName);
    fixedContent = fixedContent.replace(/지역구\s*국회\s*의원/g, fullName);
    fixedContent = fixedContent.replace(/지역구\s*의원/g, fullName);

    // "의원으로서" → "저로서" 또는 customTitle
    const asPhrase = customTitle ? `${customTitle}으로서` : '저로서';
    fixedContent = fixedContent.replace(/의원으로서/g, asPhrase);

    // "의원입니다" → 이름
    fixedContent = fixedContent.replace(/의원입니다/g, `${fullName}입니다`);

    // "의원의 한 사람으로서" → "시민의 한 사람으로서"
    fixedContent = fixedContent.replace(/의원의 한 사람으로서/g, '시민의 한 사람으로서');

    // "의정활동" → "활동"
    fixedContent = fixedContent.replace(/의정활동/g, '활동');

    // 🔥 "지역구" 표현 제거 (국회의원 전용 용어)
    // "지역구 발전" → "부산 발전" 또는 "지역 발전"
    const regionName = fullRegion || '지역';
    fixedContent = fixedContent.replace(/지역구\s*발전/g, `${regionName} 발전`);
    fixedContent = fixedContent.replace(/지역구\s*주민/g, `${regionName} 주민`);
    fixedContent = fixedContent.replace(/지역구\s*현안/g, `${regionName} 현안`);
    fixedContent = fixedContent.replace(/지역구를/g, `${regionName}을`);
    fixedContent = fixedContent.replace(/지역구의/g, `${regionName}의`);
    fixedContent = fixedContent.replace(/지역구에/g, `${regionName}에`);

    console.log('✅ 원외 인사 "의원" 및 "지역구" 표현 제거 완료');
  }

  // 1. 기본적인 호칭 수정
  // '준비' 상태는 이름만 사용하므로 직위 표현을 제거
  if (currentStatus === '준비') {
    fixedContent = fixedContent.replace(/의원입니다/g, `${fullName}입니다`);
    fixedContent = fixedContent.replace(/의원으로서/g, customTitle ? `${customTitle}으로서` : '저로서');
    fixedContent = fixedContent.replace(/후보입니다/g, `${fullName}입니다`);
    fixedContent = fixedContent.replace(/후보으로서/g, customTitle ? `${customTitle}으로서` : '저로서');
    fixedContent = fixedContent.replace(/예비후보입니다/g, `${fullName}입니다`);
    fixedContent = fixedContent.replace(/예비후보으로서/g, customTitle ? `${customTitle}으로서` : '저로서');
  } else {
    fixedContent = fixedContent.replace(/의원입니다/g, `${fullName}입니다`);
    fixedContent = fixedContent.replace(/의원으로서/g, `${displayTitle}으로서`);
    fixedContent = fixedContent.replace(/국회 의원/g, displayTitle);
    fixedContent = fixedContent.replace(/\s의원\s/g, ` ${displayTitle} `);
  }

  // 은퇴 상태 특별 수정
  if (currentStatus === '은퇴') {
    fixedContent = applyRetirementCorrections(fixedContent, fullName, userProfile);
  }

  // 2. 인사말에 이름 삽입
  if (!fixedContent.includes(`저 ${fullName}`)) {
    fixedContent = fixedContent.replace(/(<p>)안녕하세요/g, `$1안녕하세요 ${fullName}입니다`);
  }
  fixedContent = fixedContent.replace(/(<p>)안녕 ([^가-힣])/g, `$1안녕 ${fullName} $2`);

  // 3. 인사말 지역정보 수정
  if (fullRegion) {
    fixedContent = fixedContent.replace(/우리 지역의/g, `${fullRegion}의`);
    fixedContent = fixedContent.replace(/우리 지역에/g, `${fullRegion}에`);
    fixedContent = fixedContent.replace(/지역의/g, `${fullRegion} `);
    fixedContent = fixedContent.replace(/\s를\s/g, ` ${fullRegion}를`);
    fixedContent = fixedContent.replace(/\s의 발전을/g, ` ${fullRegion}의 발전을`);
    fixedContent = fixedContent.replace(/에서의/g, `${fullRegion}에서의`);
    fixedContent = fixedContent.replace(/,\s*의\s/g, `, ${fullRegion}의`);
    fixedContent = fixedContent.replace(/\s*에서\s*인/g, ` ${fullRegion}에서 인구`);
  }

  // 4. 시작 문장에 호칭 포함 체크
  if (!fixedContent.includes(`${fullName}입니다`)) {
    // fullRegion은 이미 "민"이 붙어있으므로 "도민" 하드코딩 제거
    const greeting = fullRegion ? `존경하는 ${fullRegion} 여러분` : '존경하는 여러분';
    fixedContent = fixedContent.replace(/^<p>[^<]*?<\/p>/,
      `<p>${greeting}, ${fullName}입니다.</p>`);
  }

  // 5. 마지막에 서명 수정
  if (currentStatus !== '은퇴') {
    fixedContent = fixedContent.replace(/의원 올림/g, `${fullName} 드림`);
    fixedContent = fixedContent.replace(/의원 드림/g, `${fullName} 드림`);

    if (!fixedContent.includes(`${fullName} 드림`) && !fixedContent.includes(`${fullName} 올림`)) {
      fixedContent = fixedContent.replace(/<\/p>$/, `</p><p>${fullName} 드림</p>`);
    }
  }

  // 6. 기타 패턴 수정
  fixedContent = fixedContent.replace(/도민 여러분 의원입니다/g, `도민 여러분 ${fullName}입니다`);
  fixedContent = fixedContent.replace(/여러분께, 의원입니다/g, `여러분께, ${fullName}입니다`);

  // 불완전한 문장 수정
  fixedContent = fixedContent.replace(/행복하겠습니다/g, '행복을 높이겠습니다');
  fixedContent = fixedContent.replace(/도민들의 목소리재현/g, '도민들의 목소리를 듣고 있재현');
  fixedContent = fixedContent.replace(/모두의 소통 미래를/g, '모두의 소통을 채워가며 미래를');

  // 이상한 텍스트 조각 수정
  fixedContent = fixedContent.replace(/양양군시민들이 행복이/g, '양양군시민 여러분을 위해 행복이');
  fixedContent = fixedContent.replace(/불여해서/g, '제 여러분께');

  // 최종 중복 이름 패턴 제거
  fixedContent = removeDuplicateNames(fixedContent, fullName);

  console.log('✅ 후처리 완료 - 필수 정보 삽입됨');
  return fixedContent;
}

/**
 * 은퇴 상태 특별 수정
 */
function applyRetirementCorrections(content, fullName, userProfile) {
  let fixed = content;

  // 모든 호칭 제거
  fixed = fixed.replace(/은퇴예비후보/g, '저');
  fixed = fixed.replace(/예비후보/g, '저');
  fixed = fixed.replace(/의원으로서/g, '저로서');
  fixed = fixed.replace(/은퇴.*예비후보.*로서/g, '저로서');

  // 공약/정치 활동 표현 제거
  fixed = fixed.replace(/의정활동을 통해/g, '제 경험과의 소통을 통해');
  fixed = fixed.replace(/현역 의원으로서/g, '저로서');
  fixed = fixed.replace(/성과를/g, '경험을');
  fixed = fixed.replace(/실적을/g, '활동을');
  fixed = fixed.replace(/추진하겠습니다/g, '생각합니다');
  fixed = fixed.replace(/기여하겠습니다/g, '관심을 갖고 있습니다');

  // 3인칭을 1인칭 변경
  const sentences = fixed.split('</p>');
  for (let i = 1; i < sentences.length; i++) {
    sentences[i] = sentences[i].replace(new RegExp(`${fullName}는`, 'g'), '저는');
    sentences[i] = sentences[i].replace(new RegExp(`${fullName}가`, 'g'), '제가');
    sentences[i] = sentences[i].replace(new RegExp(`${fullName}를`, 'g'), '저를');
    sentences[i] = sentences[i].replace(new RegExp(`${fullName}의`, 'g'), '저의');
  }
  fixed = sentences.join('</p>');

  // 마지막 형식 마무리/인사 완전 제거
  fixed = fixed.replace(new RegExp(`${fullName} 드림`, 'g'), '');
  fixed = fixed.replace(/드림<\/p>/g, '</p>');
  fixed = fixed.replace(/<p>드림<\/p>/g, '');
  fixed = fixed.replace(/\n\n드림$/g, '');
  fixed = fixed.replace(/드림$/g, '');
  fixed = fixed.replace(/올림<\/p>/g, '</p>');
  fixed = fixed.replace(/<p>올림<\/p>/g, '');

  // 이상한 지역 표현 수정
  const regionName = userProfile.regionLocal || userProfile.regionMetro || '양양군시';
  const baseRegion = regionName.replace('도민', '').replace('민', '');
  fixed = fixed.replace(new RegExp(`${baseRegion}도민 경제`, 'g'), `${baseRegion} 경제`);
  fixed = fixed.replace(new RegExp(`${baseRegion}도민 관광`, 'g'), `${baseRegion} 관광`);
  fixed = fixed.replace(new RegExp(`${baseRegion}도민 발전`, 'g'), `${baseRegion} 발전`);

  // 중복/이상한 표현 정리
  fixed = fixed.replace(/양양군시민을 포함한 많은 군민들/g, '많은 주민들');
  fixed = fixed.replace(/양양군시민 여러분을 포함한/g, '제 여러분을 포함한');

  // 불완전한 문장 감지 및 제거
  fixed = fixed.replace(/([가-힣]+)\s*<\/p>/g, (match, word) => {
    if (!word.match(/[다요까니다요면네요습것음임음]$/)) {
      return '</p>';
    }
    return match;
  });

  // 빈 문단 제거
  fixed = fixed.replace(/<p><\/p>/g, '');
  fixed = fixed.replace(/<p>\s*<\/p>/g, '');

  // 이상한 조사 수정
  fixed = fixed.replace(/양양군을 통해/g, '양양군내를 통해');
  fixed = fixed.replace(/양양군을/g, '양양군내를');

  return fixed;
}

/**
 * 중복 이름 패턴 제거
 */
function removeDuplicateNames(content, fullName) {
  let fixed = content;

  console.log('🔩 최종 중복 이름 제거 시작');

  fixed = fixed.replace(new RegExp(`안녕 ${fullName} ${fullName}입`, 'g'), `안녕 ${fullName}입`);
  fixed = fixed.replace(new RegExp(`안녕 ${fullName} ${fullName}가`, 'g'), `안녕 ${fullName}가`);
  fixed = fixed.replace(new RegExp(`안녕 ${fullName} ${fullName}를`, 'g'), `안녕 ${fullName}를`);
  fixed = fixed.replace(new RegExp(`안녕 ${fullName} ${fullName}`, 'g'), `안녕 ${fullName}`);
  fixed = fixed.replace(new RegExp(`${fullName} ${fullName}입`, 'g'), `${fullName}입`);
  fixed = fixed.replace(new RegExp(`${fullName} ${fullName}가`, 'g'), `${fullName}가`);
  fixed = fixed.replace(new RegExp(`${fullName} ${fullName}를`, 'g'), `${fullName}를`);
  fixed = fixed.replace(new RegExp(`${fullName} ${fullName}`, 'g'), fullName);

  // 3연속 이상 중복도 처리
  fixed = fixed.replace(new RegExp(`${fullName} ${fullName} ${fullName}`, 'g'), fullName);
  fixed = fixed.replace(new RegExp(`안녕 ${fullName} ${fullName} ${fullName}`, 'g'), `안녕 ${fullName}`);

  return fixed;
}

module.exports = {
  processGeneratedContent
};
