/**
 * 키워드 삽입 로직 테스트
 *
 * 목적: writer-agent.js와 seo-agent.js 수정 사항 검증
 * - 동적 계산이 올바르게 작동하는지
 * - 검증 로직이 부족/과다를 정확히 감지하는지
 */

'use strict';

const { calculateMinInsertions, calculateDistribution } = require('./prompts/guidelines/seo');

console.log('='.repeat(60));
console.log('키워드 삽입 로직 테스트');
console.log('='.repeat(60));

// 테스트 케이스 1: 다양한 글자수별 계산
const testCases = [
  { wordCount: 1500, expectedMin: 4 },
  { wordCount: 2000, expectedMin: 5 },
  { wordCount: 2050, expectedMin: 5 },
  { wordCount: 2500, expectedMin: 6 },
  { wordCount: 3000, expectedMin: 7 }
];

console.log('\n📊 테스트 1: 글자수별 키워드 삽입 횟수 계산');
console.log('-'.repeat(60));

testCases.forEach(({ wordCount, expectedMin }) => {
  const minCount = calculateMinInsertions(wordCount);
  const maxCount = Math.min(minCount + 2, Math.floor(minCount * 1.4));
  const distribution = calculateDistribution(minCount);

  const status = minCount === expectedMin ? '✅' : '❌';

  console.log(`${status} ${wordCount}자:`);
  console.log(`   최소: ${minCount}회 (기대: ${expectedMin}회)`);
  console.log(`   최대: ${maxCount}회`);
  console.log(`   배치: 도입 ${distribution.intro}회 + 본론 ${distribution.body}회 + 결론 ${distribution.conclusion}회`);
  console.log();
});

// 테스트 케이스 2: 검증 로직 시뮬레이션
console.log('🔍 테스트 2: 검증 로직 시뮬레이션');
console.log('-'.repeat(60));

const mockContent = `
조경태 의원이 윤석열 사형 구형에 대해 입장을 밝혔습니다.
조경태 의원은 "윤석열 전 대통령은 법정 최고형으로 다스려야 한다"고 말했습니다.
조경태 의원의 발언은 용기 있는 것이었습니다.
조경태 의원과 저는 경쟁 관계입니다.
조경태 의원의 소신을 존중합니다.
조경태 의원과 건강한 경쟁을 이어가겠습니다.

윤석열 사형 구형은 초유의 사태입니다.
윤석열 사형 구형에 대한 특검의 판단은 엄중합니다.
윤석열 사형 구형은 역사적 의미가 있습니다.
윤석열 사형 구형 소식을 듣고 깊은 성찰을 했습니다.
윤석열 사형 구형이라는 상황 앞에서 원칙이 중요합니다.
`.repeat(4); // 충분한 길이 확보

const userKeywords = ['조경태', '윤석열 사형 구형'];
const targetWordCount = 2000;

const minRequired = calculateMinInsertions(targetWordCount);
const maxAllowed = Math.min(minRequired + 2, Math.floor(minRequired * 1.4));

console.log(`목표 글자수: ${targetWordCount}자`);
console.log(`검색어: ${userKeywords.join(', ')}`);
console.log(`기준 범위: ${minRequired}~${maxAllowed}회`);
console.log();

userKeywords.forEach(keyword => {
  const regex = new RegExp(keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
  const matches = mockContent.match(regex);
  const count = matches ? matches.length : 0;

  let status, message;
  if (count < minRequired) {
    status = '❌ 부족';
    message = `SEO 효과 없음 (${count} < ${minRequired})`;
  } else if (count > maxAllowed) {
    status = '🚨 과다';
    message = `스팸 위험 (${count} > ${maxAllowed})`;
  } else {
    status = '✅ 적정';
    message = `최적 범위 (${minRequired}~${maxAllowed})`;
  }

  console.log(`${status} "${keyword}": ${count}회 - ${message}`);
});

// 테스트 케이스 3: 프롬프트 생성 시뮬레이션
console.log('\n📝 테스트 3: 프롬프트 생성 시뮬레이션');
console.log('-'.repeat(60));

const testWordCount = 2000;
const testMinCount = calculateMinInsertions(testWordCount);
const testMaxCount = Math.min(testMinCount + 2, Math.floor(testMinCount * 1.4));
const testDistribution = calculateDistribution(testMinCount);

console.log('생성될 프롬프트 내용:');
console.log(`  1. "조경태" → 필수 ${testMinCount}~${testMaxCount}회`);
console.log(`  2. "윤석열 사형 구형" → 필수 ${testMinCount}~${testMaxCount}회`);
console.log();
console.log('배치 계획:');
console.log(`  - 도입부: 각 키워드 ${testDistribution.intro}회`);
console.log(`  - 본론: 각 키워드 ${testDistribution.body}회`);
console.log(`  - 결론: 각 키워드 ${testDistribution.conclusion}회`);
console.log(`  - 합계: ${testDistribution.intro + testDistribution.body + testDistribution.conclusion}회`);

console.log('\n' + '='.repeat(60));
console.log('테스트 완료');
console.log('='.repeat(60));
console.log('\n📌 다음 단계:');
console.log('1. 이 테스트 결과를 확인');
console.log('2. 문제 없으면 실제 원고 생성 테스트');
console.log('3. 검증 통과 후 Firebase 배포');
