// 선거일 계산 테스트 스크립트
// 브라우저 콘솔에서 실행하여 검증

console.log('🗳️ 선거일 계산 테스트');

// 다음 선거일 계산 함수
const getNextElectionDate = (baseElection, today = new Date()) => {
  const { year: baseYear, month: baseMonth, day: baseDay, cycle } = baseElection;
  
  let candidateYear = baseYear;
  let candidateDate = new Date(candidateYear, baseMonth, baseDay);
  
  while (candidateDate <= today) {
    candidateYear += cycle;
    candidateDate = new Date(candidateYear, baseMonth, baseDay);
  }
  
  return {
    year: candidateYear,
    date: candidateDate
  };
};

// 윤년 판별 함수
const isLeapYear = (year) => {
  return new Date(year, 1, 29).getDate() === 29;
};

// 정확한 일수 계산 (윤년 고려)
const calculateDays = (startDate, endDate) => {
  const diffTime = endDate - startDate;
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
};

// 테스트 케이스
const testCases = [
  {
    name: '총선 (2028-04-12 기준)',
    base: { year: 2028, month: 3, day: 12, cycle: 4 },
    type: 'general'
  },
  {
    name: '지선 (2026-06-03 기준)', 
    base: { year: 2026, month: 5, day: 3, cycle: 4 },
    type: 'local'
  }
];

testCases.forEach(({ name, base, type }) => {
  console.log(`\n=== ${name} ===`);
  
  // 다음 5회 선거일 계산
  for (let i = 0; i < 5; i++) {
    const testYear = base.year + (i * base.cycle);
    const electionDate = new Date(testYear, base.month, base.day);
    const today = new Date();
    const daysUntil = calculateDays(today, electionDate);
    const isLeap = isLeapYear(testYear);
    
    console.log(`${i + 1}. ${electionDate.toLocaleDateString('ko-KR', {
      year: 'numeric',
      month: 'long', 
      day: 'numeric',
      weekday: 'short'
    })} (${testYear}${isLeap ? ' 윤년' : ''}) - D${daysUntil > 0 ? '-' + daysUntil : '+' + Math.abs(daysUntil)}`);
  }
});

// 임기 계산 테스트
console.log('\n=== 임기 계산 테스트 ===');
const termTest = [
  { start: '2024-05-30', end: '2028-05-29', name: '22대 국회의원' },
  { start: '2026-07-01', end: '2030-06-30', name: '9회 지방의원' }
];

termTest.forEach(({ start, end, name }) => {
  const startDate = new Date(start);
  const endDate = new Date(end);
  const termDays = calculateDays(startDate, endDate);
  const years = Math.floor(termDays / 365);
  const hasLeapYear = [2024, 2026, 2028, 2030].some(isLeapYear);
  
  console.log(`${name}: ${termDays}일 (약 ${years}년) ${hasLeapYear ? '- 윤년 포함' : ''}`);
});

console.log('\n✅ 모든 계산은 JavaScript Date 객체가 윤년을 자동 처리합니다.');
console.log('📅 다음 선거까지 정확한 일수가 실시간으로 계산됩니다.');

// 전역 함수로 등록
window.testElectionCalculation = () => {
  const today = new Date();
  console.log(`현재 시각: ${today.toLocaleString('ko-KR')}`);
  
  // 총선
  const nextGeneral = getNextElectionDate({ year: 2028, month: 3, day: 12, cycle: 4 });
  const generalDays = calculateDays(today, nextGeneral.date);
  console.log(`다음 총선: ${nextGeneral.date.toLocaleDateString('ko-KR')} (D-${generalDays})`);
  
  // 지선  
  const nextLocal = getNextElectionDate({ year: 2026, month: 5, day: 3, cycle: 4 });
  const localDays = calculateDays(today, nextLocal.date);
  console.log(`다음 지선: ${nextLocal.date.toLocaleDateString('ko-KR')} (D-${localDays})`);
};

console.log('\n🚀 testElectionCalculation() 함수를 실행해보세요!');