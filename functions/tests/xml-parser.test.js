/**
 * functions/tests/xml-parser.test.js
 * xml-parser 유틸리티 단위 테스트
 * 
 * 실행 방법:
 *   cd e:\ai-secretary\functions
 *   node tests/xml-parser.test.js
 */

'use strict';

const {
    extractTag,
    extractMultipleTags,
    parseStandardOutput,
    extractNestedTags,
    extractTagAttribute,
    parseTextProtocol,
    parseAIResponse,
    debugParse
} = require('../utils/xml-parser');

// 테스트 유틸리티
let passCount = 0;
let failCount = 0;

function test(name, fn) {
    try {
        fn();
        console.log(`✅ PASS: ${name}`);
        passCount++;
    } catch (error) {
        console.log(`❌ FAIL: ${name}`);
        console.log(`   Error: ${error.message}`);
        failCount++;
    }
}

function assertEqual(actual, expected, message = '') {
    const actualStr = JSON.stringify(actual);
    const expectedStr = JSON.stringify(expected);
    if (actualStr !== expectedStr) {
        throw new Error(`${message}\n   Expected: ${expectedStr}\n   Actual: ${actualStr}`);
    }
}

function assertNotNull(value, message = '') {
    if (value === null || value === undefined) {
        throw new Error(`Expected non-null value. ${message}`);
    }
}

// ============================================================================
// 테스트 케이스
// ============================================================================

console.log('\n🧪 XML Parser 단위 테스트 시작...\n');
console.log('═'.repeat(60));

// === extractTag 테스트 ===
console.log('\n📌 extractTag 테스트\n');

test('정상적인 열림/닫힘 태그 추출', () => {
    const text = '<title>테스트 제목입니다</title>';
    const result = extractTag(text, 'title');
    assertEqual(result, '테스트 제목입니다');
});

test('속성이 있는 태그 추출', () => {
    const text = '<rule type="must" priority="critical">중요한 규칙</rule>';
    const result = extractTag(text, 'rule');
    assertEqual(result, '중요한 규칙');
});

test('여러 줄 내용 추출', () => {
    const text = `<content>
    <p>첫 번째 문단입니다.</p>
    <p>두 번째 문단입니다.</p>
  </content>`;
    const result = extractTag(text, 'content');
    assertNotNull(result);
    assertEqual(result.includes('첫 번째 문단'), true);
    assertEqual(result.includes('두 번째 문단'), true);
});

test('닫는 태그 누락 시 Fallback', () => {
    const text = '<title>제목인데 닫는 태그가 없음 <content>본문 시작';
    const result = extractTag(text, 'title');
    assertEqual(result, '제목인데 닫는 태그가 없음');
});

test('존재하지 않는 태그 → null 반환', () => {
    const text = '<title>제목</title>';
    const result = extractTag(text, 'nonexistent');
    assertEqual(result, null);
});

test('빈 문자열 입력 → null 반환', () => {
    const result = extractTag('', 'title');
    assertEqual(result, null);
});

test('null 입력 → null 반환', () => {
    const result = extractTag(null, 'title');
    assertEqual(result, null);
});

// === extractMultipleTags 테스트 ===
console.log('\n📌 extractMultipleTags 테스트\n');

test('여러 태그 동시 추출', () => {
    const text = `
    <title>제목입니다</title>
    <content>본문입니다</content>
    <hashtags>#정치 #경제</hashtags>
  `;
    const result = extractMultipleTags(text, ['title', 'content', 'hashtags']);
    assertEqual(result.title, '제목입니다');
    assertEqual(result.content, '본문입니다');
    assertEqual(result.hashtags, '#정치 #경제');
});

test('일부 태그만 존재할 때', () => {
    const text = '<title>제목만 있음</title>';
    const result = extractMultipleTags(text, ['title', 'content', 'hashtags']);
    assertEqual(result.title, '제목만 있음');
    assertEqual(result.content, null);
    assertEqual(result.hashtags, null);
});

// === parseStandardOutput 테스트 ===
console.log('\n📌 parseStandardOutput 테스트\n');

test('표준 출력 형식 파싱', () => {
    const text = `
    <title>정치 분석 리포트</title>
    <content><p>본문 내용입니다.</p></content>
    <hashtags>정치, 경제, 사회</hashtags>
  `;
    const result = parseStandardOutput(text);
    assertEqual(result.title, '정치 분석 리포트');
    assertNotNull(result.content);
    assertEqual(result.hashtags.length, 3);
    assertEqual(result.hashtags[0], '#정치');
});

test('해시태그 중복 제거', () => {
    const text = `
    <title>테스트</title>
    <hashtags>#정치 #경제 #정치 정치</hashtags>
  `;
    const result = parseStandardOutput(text);
    assertEqual(result.hashtags.length, 2); // 중복 제거됨
});

test('해시태그 다양한 구분자 처리', () => {
    const text = `
    <hashtags>
      #태그1
      #태그2, #태그3
      태그4 태그5
    </hashtags>
  `;
    const result = parseStandardOutput(text);
    assertEqual(result.hashtags.length, 5);
});

// === extractNestedTags 테스트 ===
console.log('\n📌 extractNestedTags 테스트\n');

test('중첩 태그 추출', () => {
    const text = `
    <rules>
      <rule>첫 번째 규칙</rule>
      <rule>두 번째 규칙</rule>
      <rule>세 번째 규칙</rule>
    </rules>
  `;
    const result = extractNestedTags(text, 'rules', 'rule');
    assertEqual(result.length, 3);
    assertEqual(result[0], '첫 번째 규칙');
    assertEqual(result[2], '세 번째 규칙');
});

test('컨테이너 태그 없음 → 빈 배열', () => {
    const text = '<other>다른 내용</other>';
    const result = extractNestedTags(text, 'rules', 'rule');
    assertEqual(result.length, 0);
});

// === extractTagAttribute 테스트 ===
console.log('\n📌 extractTagAttribute 테스트\n');

test('태그 속성 값 추출', () => {
    const text = '<rule type="must" priority="critical">내용</rule>';
    const typeVal = extractTagAttribute(text, 'rule', 'type');
    const priorityVal = extractTagAttribute(text, 'rule', 'priority');
    assertEqual(typeVal, 'must');
    assertEqual(priorityVal, 'critical');
});

test('존재하지 않는 속성 → null', () => {
    const text = '<rule type="must">내용</rule>';
    const result = extractTagAttribute(text, 'rule', 'nonexistent');
    assertEqual(result, null);
});

// === parseTextProtocol 테스트 ===
console.log('\n📌 parseTextProtocol 테스트\n');

test('텍스트 프로토콜 파싱', () => {
    const text = `===TITLE===
정책 제안서
===CONTENT===
<p>본문 내용입니다.</p>`;
    const result = parseTextProtocol(text, '기본 제목');
    assertEqual(result.title, '정책 제안서');
    assertEqual(result.content.includes('본문 내용'), true);
});

test('구분자 없는 텍스트 → 전체를 본문으로', () => {
    const text = '<p>그냥 HTML 본문입니다.</p>';
    const result = parseTextProtocol(text, '기본 제목');
    assertEqual(result.title, '기본 제목');
    assertEqual(result.content.includes('그냥 HTML'), true);
});

test('마크다운 코드블록 제거', () => {
    const text = '```html\n===TITLE===\n제목\n===CONTENT===\n본문\n```';
    const result = parseTextProtocol(text, '');
    assertEqual(result.title, '제목');
    assertEqual(result.content, '본문');
});

// === parseAIResponse 테스트 (통합 파서) ===
console.log('\n📌 parseAIResponse 통합 파서 테스트\n');

test('XML 형식 응답 파싱', () => {
    const text = `
    <title>XML 기반 제목</title>
    <content><p>XML 기반 본문</p></content>
    <hashtags>#XML #테스트</hashtags>
  `;
    const result = parseAIResponse(text, '폴백 제목');
    assertEqual(result.parseMethod, 'xml');
    assertEqual(result.title, 'XML 기반 제목');
    assertEqual(result.hashtags.length, 2);
});

test('텍스트 프로토콜 폴백', () => {
    const text = `===TITLE===
텍스트 프로토콜 제목
===CONTENT===
<p>텍스트 프로토콜 본문</p>`;
    const result = parseAIResponse(text, '폴백 제목');
    assertEqual(result.parseMethod, 'text-protocol');
    assertEqual(result.title, '텍스트 프로토콜 제목');
});

test('형식 없는 텍스트 → text-protocol 폴백', () => {
    const text = '그냥 일반 텍스트입니다.';
    const result = parseAIResponse(text, '폴백 제목');
    // 일반 텍스트는 text-protocol의 fallback으로 처리됨 (전체를 본문으로)
    assertEqual(result.parseMethod, 'text-protocol');
    assertEqual(result.title, '폴백 제목');
    assertEqual(result.content, '그냥 일반 텍스트입니다.');
});

// === 실제 AI 응답 시뮬레이션 테스트 ===
console.log('\n📌 실제 AI 응답 시뮬레이션 테스트\n');

test('복잡한 실제 응답 파싱', () => {
    const simulatedResponse = `
물론입니다. 아래는 요청하신 원고입니다.

<title>2차 특검법 국회 통과, 정의 실현의 첫걸음</title>

<content>
<p>존경하는 부산시민 여러분, 더불어민주당 이재성입니다.</p>

<h2>헌정 질서 수호를 위한 국회의 결단</h2>
<p>지난 12월 3일 있었던 비상계엄 사태의 진상을 규명하기 위한 2차 특검법이 국회 본회의를 통과했습니다.</p>

<h2>왜 특검이 필요한가</h2>
<p>헌정 질서를 흔든 중대한 사안에 대해, 철저하고 공정한 수사가 필요합니다.</p>

<h2>앞으로의 과제</h2>
<p>저 이재성은 부산시민의 대표로서 정의로운 사회를 만들기 위해 최선을 다하겠습니다.</p>
</content>

<hashtags>
#2차특검법
#헌정질서수호
#이재성
#부산
</hashtags>
`;

    const result = parseAIResponse(simulatedResponse, '기본 제목');
    assertEqual(result.parseMethod, 'xml');
    assertEqual(result.title, '2차 특검법 국회 통과, 정의 실현의 첫걸음');
    assertNotNull(result.content);
    assertEqual(result.content.includes('존경하는 부산시민'), true);
    assertEqual(result.hashtags.length, 4);
    assertEqual(result.hashtags[0], '#2차특검법');
});

test('태그 외 불필요한 텍스트 무시', () => {
    const text = `
AI: 네, 제목과 본문을 작성했습니다.

<title>실제 제목</title>
<content>실제 본문 내용입니다.</content>

위 내용을 확인해주세요.
`;
    const result = parseAIResponse(text, '폴백');
    assertEqual(result.title, '실제 제목');
    assertEqual(result.content, '실제 본문 내용입니다.');
    // 불필요한 텍스트가 포함되지 않음
    assertEqual(result.content.includes('AI:'), false);
    assertEqual(result.content.includes('확인해주세요'), false);
});

// === 테스트 결과 요약 ===
console.log('\n' + '═'.repeat(60));
console.log(`\n📊 테스트 결과: ${passCount} passed, ${failCount} failed`);

if (failCount === 0) {
    console.log('🎉 모든 테스트 통과!\n');
    process.exit(0);
} else {
    console.log('⚠️ 일부 테스트 실패\n');
    process.exit(1);
}
