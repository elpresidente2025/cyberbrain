/**
 * 프롬프트 재구조화 테스트 스크립트
 *
 * 목적: 새로운 PRIORITY 기반 프롬프트가 배경정보를 제대로 반영하는지 검증
 *
 * 테스트 케이스: 체육대회 관련 실제 사실이 포함된 배경정보
 * - 300여명 참여
 * - 모경종, 정일영, 오현식 등 실명
 * - 경기도당 조직명
 * - 구체적인 이벤트 사실
 */

const testRequest = {
  // 사용자 입력 (프론트엔드에서 전송되는 형태)
  topic: "경기도당 체육대회 성황리 개최",
  category: "activity-report",
  wordCount: 1500,

  // 배경정보 (핵심 테스트 대상)
  instructions: [
    "지난 주말 경기도당 주최로 300여명이 참여한 체육대회가 성황리에 개최되었습니다.",
    "모경종 경기도당위원장과 정일영 의원, 오현식 의원이 함께 참석하여 축사를 전했습니다.",
    "이번 행사는 당원들의 화합과 소통을 위해 마련되었으며, 다양한 종목의 경기가 진행되었습니다."
  ]
};

// 예상되는 키워드 추출 결과
const expectedKeywords = [
  "300여명",           // 숫자 추출 (100 이상 + 명)
  "모경종",            // 인명 후보 (한글 2-4자, 하지만 직책 없음)
  "경기도당위원장",     // 인명 + 직책 패턴
  "정일영 의원",        // 인명 + 직책 패턴
  "오현식 의원",        // 인명 + 직책 패턴
  "경기도당",          // 고유명사 (조직명)
  "체육대회"           // 고유명사 (이벤트명)
];

// 성공 기준
const successCriteria = {
  // 1. 모든 배경정보 키워드가 생성된 content에 포함되어야 함
  allKeywordsPresent: true,

  // 2. 최소 글자수 충족 (목표의 90% = 1350자 이상)
  minWordCount: 1350,

  // 3. 필수 인명이 정확히 포함되어야 함
  requiredNames: ["모경종", "정일영", "오현식"],

  // 4. 필수 조직명 포함
  requiredOrgs: ["경기도당"],

  // 5. 구체적인 숫자 정보 포함
  requiredNumbers: ["300여명"],

  // 6. 배경정보에 없는 내용 환각 금지
  noHallucination: true
};

// 실패 기준 (이전 문제들)
const failureCriteria = {
  // 1. 배경정보 무시 (가장 심각한 문제)
  examples: [
    "배경정보의 실명(모경종, 정일영, 오현식)이 하나라도 누락됨",
    "구체적인 숫자(300여명)가 누락되거나 다른 숫자로 대체됨",
    "조직명(경기도당)이 일반명사(당원, 도당)로 대체됨"
  ],

  // 2. 환각 (배경정보에 없는 내용 추가)
  hallucinationExamples: [
    "배경정보에 없는 '심도 깊은 논의' 같은 추상적 표현 추가",
    "배경정보에 없는 인명이나 조직명 추가",
    "배경정보에 없는 구체적인 정책이나 사건 언급"
  ],

  // 3. 분량 미달
  insufficientLength: {
    target: 1500,
    minimum: 1350, // 90%
    previousFailure: "이전 테스트에서 목표 대비 50% 이하로 생성됨"
  },

  // 4. 일반적/추상적 내용으로 대체
  genericContentExamples: [
    "구체적인 사실 대신 '지역구 주민들과 소통' 같은 일반론",
    "실제 참석자 대신 '많은 분들이 참석' 같은 모호한 표현",
    "구체적인 행사 내용 대신 '뜻깊은 시간' 같은 추상적 표현"
  ]
};

// 검증 함수
function validateOutput(generatedContent) {
  const results = {
    passed: [],
    failed: [],
    warnings: []
  };

  // HTML 태그 제거하고 순수 텍스트만 추출
  const plainText = generatedContent.replace(/<[^>]*>/g, '');
  const wordCount = plainText.replace(/\s/g, '').length;

  // 1. 글자수 검증
  if (wordCount >= successCriteria.minWordCount) {
    results.passed.push(`✅ 글자수 충족: ${wordCount}자 (최소 ${successCriteria.minWordCount}자)`);
  } else {
    results.failed.push(`❌ 글자수 부족: ${wordCount}자 (최소 ${successCriteria.minWordCount}자 필요)`);
  }

  // 2. 필수 인명 검증
  const missingNames = successCriteria.requiredNames.filter(name => !plainText.includes(name));
  if (missingNames.length === 0) {
    results.passed.push(`✅ 모든 필수 인명 포함: ${successCriteria.requiredNames.join(', ')}`);
  } else {
    results.failed.push(`❌ 누락된 인명: ${missingNames.join(', ')}`);
  }

  // 3. 필수 조직명 검증
  const missingOrgs = successCriteria.requiredOrgs.filter(org => !plainText.includes(org));
  if (missingOrgs.length === 0) {
    results.passed.push(`✅ 모든 필수 조직명 포함: ${successCriteria.requiredOrgs.join(', ')}`);
  } else {
    results.failed.push(`❌ 누락된 조직명: ${missingOrgs.join(', ')}`);
  }

  // 4. 필수 숫자 정보 검증
  const missingNumbers = successCriteria.requiredNumbers.filter(num => !plainText.includes(num));
  if (missingNumbers.length === 0) {
    results.passed.push(`✅ 모든 필수 숫자 정보 포함: ${successCriteria.requiredNumbers.join(', ')}`);
  } else {
    results.failed.push(`❌ 누락된 숫자 정보: ${missingNumbers.join(', ')}`);
  }

  // 5. 환각 경고 (수동 확인 필요)
  const hallucinationKeywords = [
    '심도 깊은 논의', '다양한 의견', '활발한 토론',
    '열띤 토의', '건설적인 대화', '폭넓은 공감'
  ];

  const foundHallucinations = hallucinationKeywords.filter(keyword => plainText.includes(keyword));
  if (foundHallucinations.length > 0) {
    results.warnings.push(`⚠️ 환각 의심 표현 발견: ${foundHallucinations.join(', ')}`);
  }

  // 6. 종합 판정
  const allPassed = results.failed.length === 0;

  return {
    success: allPassed,
    summary: allPassed ?
      '🎉 모든 검증 통과! 프롬프트 재구조화 성공!' :
      '❌ 검증 실패 - 추가 수정 필요',
    details: results,
    stats: {
      passed: results.passed.length,
      failed: results.failed.length,
      warnings: results.warnings.length,
      wordCount
    }
  };
}

// 테스트 실행 가이드
const testGuide = `
=== 테스트 실행 방법 ===

1. Firebase 프로젝트에 로그인
   firebase login

2. 로컬 Functions 에뮬레이터 실행 (선택사항)
   firebase emulators:start --only functions

3. 프론트엔드에서 테스트 요청 전송
   - 주제: "${testRequest.topic}"
   - 카테고리: "${testRequest.category}"
   - 배경정보: (위 instructions 배열 내용)

4. 생성된 content를 validateOutput() 함수에 전달하여 검증

5. 예상 결과:
   - 모든 필수 키워드(${expectedKeywords.length}개) 포함
   - 최소 ${successCriteria.minWordCount}자 이상
   - 환각 없음 (배경정보 사실만 사용)

=== 이전 실패 사례 (수정 전) ===

문제 1: 배경정보 완전 무시
- 입력: "300여명, 모경종, 정일영, 오현식 참석"
- 출력: "많은 분들이 참석하여 뜻깊은 시간을 가졌습니다" (일반론)
- 원인: 프롬프트에서 "참고자료"로 표현하여 선택사항으로 인식됨

문제 2: 분량 미달
- 목표: 1500자
- 실제: 700자 (47%)
- 원인: temperature가 너무 높아 지시사항보다 창의성 우선

문제 3: 환각
- 배경정보에 없는 "심도 깊은 논의", "다양한 의견 수렴" 등 추가
- 원인: 검증 로직 없음

=== 재구조화된 프롬프트의 해결책 ===

1. PRIORITY 2: SOURCE MATERIAL - MANDATORY USE
   - "참고자료" → "MANDATORY USE" (필수 사용 명시)
   - CHECKLIST 형식으로 각 키워드를 체크리스트화
   - "You MUST use ALL items below" 강조

2. PRIORITY 4: PROHIBITIONS
   - 일반적 표현 금지 명시
   - 배경정보 외 내용 추가 금지

3. SELF-VERIFICATION BEFORE OUTPUT
   - AI가 출력 전 스스로 체크리스트 확인
   - 분량, 키워드, 사실관계 자가 검증

4. 백엔드 검증 로직 (extractKeywordsFromInstructions)
   - 정규식으로 필수 키워드 자동 추출
   - 누락 키워드 발견 시 재생성 (최대 3회)

=== 다음 단계 ===

이 테스트가 성공하면:
✅ 프롬프트 재구조화 완료
✅ 배경정보 반영 문제 해결
✅ 분량 준수 문제 해결
✅ 환각 방지 메커니즘 작동

만약 여전히 실패한다면:
- temperature를 0.3 → 0.1로 더 낮춤 (지시 준수율 극대화)
- CHECKLIST 형식을 더 구체화 (각 항목에 예시 추가)
- 백엔드 검증을 더 엄격하게 (키워드 포함률 100% 강제)
`;

module.exports = {
  testRequest,
  expectedKeywords,
  successCriteria,
  failureCriteria,
  validateOutput,
  testGuide
};

// 콘솔 출력
if (require.main === module) {
  console.log('='.repeat(80));
  console.log('프롬프트 재구조화 테스트 케이스');
  console.log('='.repeat(80));
  console.log('\n📋 테스트 요청:');
  console.log(JSON.stringify(testRequest, null, 2));
  console.log('\n🔍 예상 키워드 추출 결과:');
  console.log(expectedKeywords);
  console.log('\n✅ 성공 기준:');
  console.log(JSON.stringify(successCriteria, null, 2));
  console.log('\n❌ 실패 기준:');
  console.log(JSON.stringify(failureCriteria, null, 2));
  console.log('\n' + testGuide);
}
