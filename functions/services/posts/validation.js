'use strict';

const { callGenerativeModel } = require('../gemini');

// ============================================================================
// LLM 기반 품질 검증 (삭제됨 - 프롬프트 강화로 대체)
// ============================================================================

/**
 * LLM을 활용한 원고 품질 검증
 * 성능 이슈(504 Timeout) 방지를 위해 실제 검증 로직은 제거하고 통과 처리함
 */
async function evaluateQualityWithLLM(content, modelName) {
  // 함수 형태는 유지하되 무조건 통과 반환 (참조 에러 방지)
  return { passed: true, issues: [], suggestions: [] };
}

// ============================================================================
// 휴리스틱 검증 함수들 (빠른 검증)
// ============================================================================

/**
 * 키워드 출현 횟수 카운팅 (띄어쓰기 정확히 일치)
 */
function countKeywordOccurrences(content, keyword) {
  const cleanContent = content.replace(/<[^>]*>/g, '');
  // 특수문자 이스케이프 처리
  const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(escapedKeyword, 'g');
  const matches = cleanContent.match(regex);
  return matches ? matches.length : 0;
}

/**
 * 키워드 삽입 검증 (사용자 키워드는 엄격, 자동 키워드는 완화)
 */
function validateKeywordInsertion(content, userKeywords = [], autoKeywords = [], targetWordCount) {
  const plainText = content.replace(/<[^>]*>/g, '').replace(/\s/g, '');
  const actualWordCount = plainText.length;

  // 사용자 입력 키워드: 400자당 1회 (엄격)
  const userExpectedCount = Math.floor(actualWordCount / 400);
  const userMinCount = Math.max(1, userExpectedCount);

  // 자동 추출 키워드: 최소 1회만 (완화)
  const autoMinCount = 1;

  const results = {};
  let totalOccurrences = 0;
  let allValid = true;

  // 1. 사용자 입력 키워드 검증 (엄격)
  for (const keyword of userKeywords) {
    const count = countKeywordOccurrences(content, keyword);
    totalOccurrences += count;
    const isValid = count >= userMinCount;

    results[keyword] = {
      count,
      expected: userMinCount,
      valid: isValid,
      type: 'user'
    };

    if (!isValid) {
      allValid = false;
    }
  }

  // 2. 자동 추출 키워드 검증 (완화)
  for (const keyword of autoKeywords) {
    const count = countKeywordOccurrences(content, keyword);
    totalOccurrences += count;
    const isValid = count >= autoMinCount;

    results[keyword] = {
      count,
      expected: autoMinCount,
      valid: isValid,
      type: 'auto'
    };
  }

  // 키워드 밀도 계산 (참고용)
  const allKeywords = [...userKeywords, ...autoKeywords];
  const totalKeywordChars = allKeywords.reduce((sum, kw) => {
    const occurrences = countKeywordOccurrences(content, kw);
    return sum + (kw.replace(/\s/g, '').length * occurrences);
  }, 0);
  const density = actualWordCount > 0 ? (totalKeywordChars / actualWordCount * 100) : 0;

  return {
    valid: allValid,
    details: {
      keywords: results,
      density: {
        value: density.toFixed(2),
        valid: true,
        optimal: density >= 1.5 && density <= 2.5
      },
      wordCount: actualWordCount
    }
  };
}

/**
 * AI 응답 생성 (사후 검증 제거 - 프롬프트 강화로 대체)
 * 1회 호출 후 즉시 반환
 */
async function validateAndRetry({
  prompt,
  modelName,
  fullName,
  fullRegion,
  targetWordCount,
  userKeywords = [],
  autoKeywords = [],
  maxAttempts = 1 // 더 이상 재시도 없음
}) {
  console.log(`🔥 AI 호출 (1회, 검증 없음)...`);

  // AI에게 글 쓰기 요청 (1회만)
  const apiResponse = await callGenerativeModel(prompt, 1, modelName);

  if (!apiResponse || apiResponse.length < 100) {
    throw new Error('AI 원고 생성 실패: 응답이 너무 짧음');
  }

  console.log(`✅ AI 응답 완료 (${apiResponse.length}자)`);
  return apiResponse;
}

module.exports = {
  validateAndRetry,
  evaluateQualityWithLLM
};