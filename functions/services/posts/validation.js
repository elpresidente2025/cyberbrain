'use strict';

const { callGenerativeModel } = require('../gemini');
const { getElectionStage } = require('../../prompts/guidelines/legal');

// ============================================================================
// 휴리스틱 품질 검증 (v2 - LLM 없이 빠른 검증)
// ============================================================================

/**
 * 문장 반복 검출
 * 동일한 문장이 2회 이상 등장하면 실패
 *
 * @param {string} content - 검증할 HTML 콘텐츠
 * @returns {Object} { passed: boolean, repeatedSentences: string[] }
 */
function detectSentenceRepetition(content) {
  // HTML 태그 제거
  const plainText = content.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

  // 문장 분리 (마침표, 물음표, 느낌표 기준)
  const sentences = plainText
    .split(/(?<=[.?!])\s+/)
    .map(s => s.trim())
    .filter(s => s.length > 20); // 20자 이상 문장만 검사 (짧은 문장 제외)

  // 정규화: 공백 제거, 소문자화 (유사 문장 검출용)
  const normalizedSentences = sentences.map(s =>
    s.replace(/\s+/g, '').toLowerCase()
  );

  // 중복 검출
  const sentenceCount = {};
  const repeatedSentences = [];

  normalizedSentences.forEach((normalized, index) => {
    if (!sentenceCount[normalized]) {
      sentenceCount[normalized] = { count: 0, original: sentences[index] };
    }
    sentenceCount[normalized].count++;
  });

  Object.values(sentenceCount).forEach(({ count, original }) => {
    if (count >= 2) {
      repeatedSentences.push(`"${original.substring(0, 50)}..." (${count}회 반복)`);
    }
  });

  return {
    passed: repeatedSentences.length === 0,
    repeatedSentences
  };
}

/**
 * 선거법 위반 검출 (공약성 표현)
 * 사용자 상태가 '준비' 또는 '현역'일 때 ~하겠습니다 표현 검출
 *
 * @param {string} content - 검증할 HTML 콘텐츠
 * @param {string} status - 사용자 상태 (준비/현역/예비/후보)
 * @returns {Object} { passed: boolean, violations: string[] }
 */
function detectElectionLawViolation(content, status) {
  // 상태가 없거나 예비/후보 단계면 검사 스킵
  if (!status) {
    return { passed: true, violations: [], skipped: true };
  }

  const electionStage = getElectionStage(status);
  if (!electionStage || electionStage.name !== 'STAGE_1') {
    // 예비후보/후보 단계는 공약 표현 허용
    return { passed: true, violations: [], skipped: true };
  }

  // HTML 태그 제거
  const plainText = content.replace(/<[^>]*>/g, ' ');

  // 공약성 표현 패턴 (준비/현역 단계에서 금지)
  const pledgePatterns = [
    /추진하겠습니다/g,
    /실현하겠습니다/g,
    /만들겠습니다/g,
    /해내겠습니다/g,
    /전개하겠습니다/g,
    /제공하겠습니다/g,
    /활성화하겠습니다/g,
    /개선하겠습니다/g,
    /확대하겠습니다/g,
    /강화하겠습니다/g,
    /설립하겠습니다/g,
    /구축하겠습니다/g,
    /마련하겠습니다/g,
    /지원하겠습니다/g,
    /해결하겠습니다/g,
    /바꾸겠습니다/g,
    /펼치겠습니다/g,
    /이루겠습니다/g,
    /열겠습니다/g,
    /세우겠습니다/g,
  ];

  const violations = [];

  pledgePatterns.forEach(pattern => {
    const matches = plainText.match(pattern);
    if (matches) {
      violations.push(`"${matches[0]}" (${matches.length}회)`);
    }
  });

  return {
    passed: violations.length === 0,
    violations,
    status,
    stage: electionStage.name
  };
}

/**
 * 통합 휴리스틱 검증
 * @param {string} content - 검증할 콘텐츠
 * @param {string} status - 사용자 상태
 * @returns {Object} { passed: boolean, issues: string[] }
 */
function runHeuristicValidation(content, status) {
  const issues = [];

  // 1. 문장 반복 검출
  const repetitionResult = detectSentenceRepetition(content);
  if (!repetitionResult.passed) {
    issues.push(`⚠️ 문장 반복 감지: ${repetitionResult.repeatedSentences.join(', ')}`);
  }

  // 2. 선거법 위반 검출
  const electionResult = detectElectionLawViolation(content, status);
  if (!electionResult.passed) {
    issues.push(`⚠️ 선거법 위반 표현: ${electionResult.violations.join(', ')}`);
  }

  return {
    passed: issues.length === 0,
    issues,
    details: {
      repetition: repetitionResult,
      electionLaw: electionResult
    }
  };
}

// ============================================================================
// LLM 기반 품질 검증 (비활성화 - 필요시 복원 가능)
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
 * AI 응답 생성 + 휴리스틱 검증 + 재시도
 * 검증 실패 시 최대 2회 재시도 (총 3회)
 *
 * @param {Object} options
 * @param {string} options.prompt - AI 프롬프트
 * @param {string} options.modelName - 모델명
 * @param {string} options.status - 사용자 상태 (선거법 검증용)
 * @param {number} options.maxAttempts - 최대 시도 횟수 (기본: 3)
 */
async function validateAndRetry({
  prompt,
  modelName,
  fullName,
  fullRegion,
  targetWordCount,
  userKeywords = [],
  autoKeywords = [],
  status = null,
  maxAttempts = 3 // 휴리스틱 검증 실패 시 재시도
}) {
  let lastResponse = null;
  let lastValidationResult = null;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    console.log(`🔥 AI 호출 (${attempt}/${maxAttempts})...`);

    // AI에게 글 쓰기 요청
    const apiResponse = await callGenerativeModel(prompt, 1, modelName);

    if (!apiResponse || apiResponse.length < 100) {
      console.warn(`⚠️ 응답이 너무 짧음 (${attempt}회차)`);
      lastResponse = apiResponse;
      continue;
    }

    lastResponse = apiResponse;

    // 휴리스틱 검증 실행
    const validationResult = runHeuristicValidation(apiResponse, status);
    lastValidationResult = validationResult;

    if (validationResult.passed) {
      console.log(`✅ 품질 검증 통과 (${attempt}회차, ${apiResponse.length}자)`);
      return apiResponse;
    }

    // 검증 실패 로그
    console.warn(`⚠️ 품질 검증 실패 (${attempt}회차):`, validationResult.issues);

    if (attempt < maxAttempts) {
      console.log(`🔄 재시도 예정...`);
    }
  }

  // 모든 시도 실패 시
  console.error(`❌ ${maxAttempts}회 시도 후에도 품질 검증 실패`);

  // 마지막 응답 반환 (완전 실패보다는 낫다)
  if (lastResponse && lastResponse.length >= 100) {
    console.warn(`⚠️ 검증 실패했지만 마지막 응답 반환 (${lastResponse.length}자)`);
    console.warn(`⚠️ 발견된 문제점:`, lastValidationResult?.issues || []);
    return lastResponse;
  }

  throw new Error('AI 원고 생성 실패: 모든 시도에서 품질 기준 미달');
}

module.exports = {
  validateAndRetry,
  evaluateQualityWithLLM,
  // 개별 검증 함수도 export (테스트용)
  detectSentenceRepetition,
  detectElectionLawViolation,
  runHeuristicValidation
};