'use strict';

/**
 * getWritingExamples 테스트
 * 실행: node functions/tests/editorial.test.js
 */

const assert = require('assert');
const { getWritingExamples } = require('../prompts/guidelines/editorial');

console.log('🧪 getWritingExamples 테스트 시작\n');

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`  ✅ ${name}`);
    passed++;
  } catch (error) {
    console.log(`  ❌ ${name}`);
    console.log(`     ${error.message}`);
    failed++;
  }
}

// 1. 정상 카테고리 테스트
test('local-issues 카테고리 → 문자열 반환', () => {
  const result = getWritingExamples('local-issues');
  assert.strictEqual(typeof result, 'string');
  assert.ok(result.length > 0, '빈 문자열이면 안 됨');
  assert.ok(result.includes('모범 문장'), '모범 문장 헤더 포함');
});

test('policy-proposal 카테고리 → 문자열 반환', () => {
  const result = getWritingExamples('policy-proposal');
  assert.strictEqual(typeof result, 'string');
  assert.ok(result.length > 0);
});

test('daily-communication 카테고리 → 문자열 반환', () => {
  const result = getWritingExamples('daily-communication');
  assert.strictEqual(typeof result, 'string');
  assert.ok(result.length > 0);
});

// 2. unknown 카테고리 테스트
test('unknown 카테고리 → fallback으로 문자열 반환', () => {
  const result = getWritingExamples('unknown-category');
  assert.strictEqual(typeof result, 'string');
  assert.ok(result.length > 0, 'unknown이어도 빈 문자열이면 안 됨');
});

// 3. null/undefined 테스트
test('null 입력 → 문자열 반환 (에러 없음)', () => {
  const result = getWritingExamples(null);
  assert.strictEqual(typeof result, 'string');
});

test('undefined 입력 → 문자열 반환 (에러 없음)', () => {
  const result = getWritingExamples(undefined);
  assert.strictEqual(typeof result, 'string');
});

test('빈 문자열 입력 → 문자열 반환', () => {
  const result = getWritingExamples('');
  assert.strictEqual(typeof result, 'string');
});

// 4. 공감묘사 fallback 테스트
test('필터 결과 없는 카테고리도 공감묘사 섹션 포함', () => {
  const result = getWritingExamples('unknown-category');
  assert.ok(result.includes('공감 묘사 예시'), '공감 묘사 섹션 있어야 함');
});

// 5. 모든 섹션 포함 테스트
test('모든 필수 섹션 포함', () => {
  const result = getWritingExamples('local-issues');
  assert.ok(result.includes('도입부 예시'), '도입부 섹션');
  assert.ok(result.includes('공감 묘사 예시'), '공감묘사 섹션');
  assert.ok(result.includes('전환 예시'), '전환 섹션');
  assert.ok(result.includes('약속/다짐 예시'), '약속다짐 섹션');
  assert.ok(result.includes('마무리 예시'), '마무리 섹션');
});

// 결과 출력
console.log(`\n📊 테스트 결과: ${passed} 통과, ${failed} 실패`);

if (failed > 0) {
  process.exit(1);
}
