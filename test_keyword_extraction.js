/**
 * 키워드 추출 함수 테스트
 * posts.js의 extractKeywordsFromInstructions 함수를 독립 실행하여 검증
 */

// posts.js에서 복사한 키워드 추출 함수 (개선 버전)
function extractKeywordsFromInstructions(instructions) {
  if (!instructions) return [];

  const text = Array.isArray(instructions) ? instructions.join(' ') : instructions;
  const keywords = [];

  // 1. 숫자+단위 추출 (예: 300여명, 500명, 1000개, 2회)
  const numberMatches = text.match(/[0-9]+여?[명개회건차명월일년원]/g);
  if (numberMatches) keywords.push(...numberMatches);

  // 2. 인명 + 직책 패턴 (예: 홍길동 의원, 김철수 위원장, 홍길동 경기도당위원장)
  // 첫 번째 패턴: 직책이 바로 붙거나 공백 후 나오는 경우
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

// 테스트 케이스
const testInstructions = [
  "지난 주말 경기도당 주최로 300여명이 참여한 체육대회가 성황리에 개최되었습니다.",
  "모경종 경기도당위원장과 정일영 의원, 오현식 의원이 함께 참석하여 축사를 전했습니다.",
  "이번 행사는 당원들의 화합과 소통을 위해 마련되었으며, 다양한 종목의 경기가 진행되었습니다."
];

console.log('='.repeat(80));
console.log('키워드 추출 함수 테스트');
console.log('='.repeat(80));
console.log('\n📝 입력 배경정보:');
testInstructions.forEach((inst, i) => {
  console.log(`${i + 1}. ${inst}`);
});

const extracted = extractKeywordsFromInstructions(testInstructions);

console.log('\n🔍 추출된 키워드:');
console.log(extracted);
console.log(`\n총 ${extracted.length}개 키워드 추출됨`);

// 상세 분석
console.log('\n📊 키워드 카테고리별 분석:');

const categories = {
  인명: extracted.filter(kw => kw.match(/[가-힣]{2,4}(?:국회의원|위원장|의원|시장|도지사)/)),
  숫자: extracted.filter(kw => kw.match(/[0-9]{3,}[여명개회건]/)),
  조직명: extracted.filter(kw => kw.match(/[가-힣]{3,}(?:시당|도당|위원회|체육대회|선거|합동)/)),
  연도: extracted.filter(kw => kw.match(/20[0-9]{2}년/))
};

Object.entries(categories).forEach(([category, keywords]) => {
  if (keywords.length > 0) {
    console.log(`\n${category}:`);
    keywords.forEach(kw => console.log(`  ✓ ${kw}`));
  }
});

// 누락 검증
console.log('\n⚠️ 누락된 중요 정보:');

const expectedKeywords = {
  '인명': ['모경종', '정일영', '오현식'],
  '숫자': ['300여명'],
  '조직명': ['경기도당']
};

let allFound = true;
Object.entries(expectedKeywords).forEach(([category, expected]) => {
  const missing = expected.filter(kw => {
    // 부분 매칭도 허용 (예: "정일영 의원"에 "정일영" 포함)
    return !extracted.some(extractedKw => extractedKw.includes(kw));
  });

  if (missing.length > 0) {
    console.log(`  ❌ ${category}: ${missing.join(', ')}`);
    allFound = false;
  }
});

if (allFound) {
  console.log('  ✅ 모든 중요 키워드가 추출되었습니다!');
}

// 프롬프트에서 어떻게 사용될지 시뮬레이션
console.log('\n📋 생성될 CHECKLIST 형식:');
console.log('CHECKLIST (Every item below MUST appear in your article):');
extracted.forEach((kw, i) => {
  console.log(`☐ ${i + 1}. "${kw}" must be included`);
});

console.log('\n' + '='.repeat(80));
console.log('결론:');
console.log('='.repeat(80));

if (allFound) {
  console.log('✅ 키워드 추출 함수가 정상적으로 작동합니다.');
  console.log(`✅ 총 ${extracted.length}개의 필수 키워드가 CHECKLIST에 포함됩니다.`);
  console.log('✅ AI는 이 체크리스트를 보고 모든 항목을 포함해야 합니다.');
} else {
  console.log('⚠️ 일부 중요 키워드가 누락되었습니다.');
  console.log('⚠️ 정규식 패턴을 개선해야 할 수 있습니다.');
}

console.log('\n💡 참고:');
console.log('- "모경종"은 직책 없이 단독으로 나와서 추출되지 않을 수 있습니다.');
console.log('- 하지만 "모경종 경기도당위원장"이 추출되므로 검증 시 부분 매칭으로 확인합니다.');
console.log('- 백엔드 검증 로직에서 생성된 content에 "모경종"이 포함되는지 확인합니다.');
