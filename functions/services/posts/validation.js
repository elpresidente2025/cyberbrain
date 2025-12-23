'use strict';

const { callGenerativeModel } = require('../gemini');
const { getElectionStage } = require('../../prompts/guidelines/legal');
const { runCriticReview, hasHardViolations, summarizeGuidelines } = require('./critic');
const { applyCorrections, summarizeViolations } = require('./corrector');
const { GENERATION_STAGES, createProgressState, createRetryMessage } = require('./generation-stages');

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
// 키워드 검증 함수
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

// ============================================================================
// Critic Agent 통합 검증 (v3)
// ============================================================================

/**
 * AI 응답 생성 + 휴리스틱 검증 + Critic Agent + Corrector
 *
 * 흐름:
 * 1. 초안 생성
 * 2. 휴리스틱 사전 검증 (빠른 필터)
 * 3. 실패 시 재생성 (최대 3회)
 * 4. 휴리스틱 통과 후 Critic Agent 검토
 * 5. HARD 위반 시 Corrector로 수정
 * 6. 최대 2회 Critic-Corrector 루프
 * 7. 최고 점수 버전 반환
 *
 * @param {Object} options
 * @param {string} options.prompt - AI 프롬프트
 * @param {string} options.modelName - 모델명
 * @param {string} options.status - 사용자 상태 (선거법 검증용)
 * @param {string} options.ragContext - RAG 컨텍스트 (Critic용)
 * @param {string} options.authorName - 작성자 이름
 * @param {string} options.topic - 원고 주제
 * @param {Function} options.onProgress - 진행 상황 콜백
 * @param {number} options.maxAttempts - 초안 생성 최대 시도 횟수 (기본: 3)
 * @param {number} options.maxCriticAttempts - Critic 루프 최대 횟수 (기본: 2)
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
  ragContext = null,
  authorName = null,
  topic = null,
  onProgress = null,
  maxAttempts = 3,
  maxCriticAttempts = 2
}) {
  // 진행 상황 알림 헬퍼
  const notifyProgress = (stageId, additionalInfo = {}) => {
    if (onProgress && typeof onProgress === 'function') {
      try {
        onProgress(createProgressState(stageId, additionalInfo));
      } catch (e) {
        console.warn('Progress 콜백 오류:', e.message);
      }
    }
  };

  // 최고 점수 버전 추적
  let bestVersion = null;
  let bestScore = 0;

  // ========================================
  // Phase 1: 초안 생성 + 휴리스틱 검증
  // ========================================
  notifyProgress('DRAFTING');

  let draft = null;
  let heuristicPassed = false;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    console.log(`🔥 AI 호출 (${attempt}/${maxAttempts})...`);

    // AI에게 글 쓰기 요청
    const apiResponse = await callGenerativeModel(prompt, 1, modelName);

    if (!apiResponse || apiResponse.length < 100) {
      console.warn(`⚠️ 응답이 너무 짧음 (${attempt}회차)`);
      continue;
    }

    draft = apiResponse;

    // 휴리스틱 검증
    notifyProgress('BASIC_CHECK');
    const heuristicResult = runHeuristicValidation(draft, status);

    if (heuristicResult.passed) {
      console.log(`✅ 휴리스틱 검증 통과 (${attempt}회차, ${draft.length}자)`);
      heuristicPassed = true;
      break;
    }

    // 검증 실패
    console.warn(`⚠️ 휴리스틱 검증 실패 (${attempt}회차):`, heuristicResult.issues);

    // 점수 추정 (휴리스틱 실패는 70점 기준)
    const estimatedScore = 70 - (heuristicResult.issues.length * 15);
    if (estimatedScore > bestScore) {
      bestScore = estimatedScore;
      bestVersion = draft;
    }

    if (attempt < maxAttempts) {
      console.log(`🔄 재생성 시도...`);
      notifyProgress('DRAFTING', { attempt: attempt + 1 });
    }
  }

  // 휴리스틱조차 통과 못하면 최선 버전 반환
  if (!heuristicPassed) {
    console.error(`❌ ${maxAttempts}회 시도 후에도 휴리스틱 검증 실패`);

    if (bestVersion && bestVersion.length >= 100) {
      console.warn(`⚠️ 최선 버전 반환 (점수: ${bestScore})`);
      notifyProgress('COMPLETED', { warning: '품질 검증 일부 실패' });
      return bestVersion;
    }

    throw new Error('AI 원고 생성 실패: 모든 시도에서 품질 기준 미달');
  }

  // ========================================
  // Phase 2: Critic Agent 검토 + Corrector 루프
  // ========================================

  // 핵심 지침 요약 (프롬프트 하단용)
  const guidelines = summarizeGuidelines(status, topic);

  let currentDraft = draft;
  let criticAttempt = 0;

  while (criticAttempt < maxCriticAttempts) {
    criticAttempt++;

    // Critic 검토
    const retryMsg = createRetryMessage(criticAttempt, maxCriticAttempts, bestScore);
    notifyProgress('EDITOR_REVIEW', {
      attempt: criticAttempt,
      message: retryMsg.message,
      detail: retryMsg.detail
    });

    console.log(`👔 Critic Agent 검토 (${criticAttempt}/${maxCriticAttempts})...`);

    const criticReport = await runCriticReview({
      draft: currentDraft,
      ragContext,
      guidelines,
      status,
      topic,
      authorName,
      modelName: 'gemini-1.5-flash'  // Critic은 빠른 모델 사용
    });

    // 점수 추적
    if (criticReport.score > bestScore) {
      bestScore = criticReport.score;
      bestVersion = currentDraft;
    }

    // 통과 시 반환
    if (criticReport.passed || !criticReport.needsRetry) {
      console.log(`✅ Critic 검토 통과 (점수: ${criticReport.score})`);
      notifyProgress('FINALIZING');

      // 최종 휴리스틱 재검증
      const finalCheck = runHeuristicValidation(currentDraft, status);
      if (!finalCheck.passed) {
        console.warn(`⚠️ 최종 휴리스틱 실패 (무시하고 반환):`, finalCheck.issues);
      }

      notifyProgress('COMPLETED', { score: criticReport.score });
      return currentDraft;
    }

    // HARD 위반이 있으면 수정 시도
    if (hasHardViolations(criticReport)) {
      notifyProgress('CORRECTING', {
        violations: summarizeViolations(criticReport.violations)
      });

      console.log(`✨ Corrector로 수정 시도 (위반: ${criticReport.violations.length}건)...`);

      const correctionResult = await applyCorrections({
        draft: currentDraft,
        violations: criticReport.violations,
        ragContext,
        authorName,
        status,
        modelName: 'gemini-1.5-flash'
      });

      if (correctionResult.success && !correctionResult.unchanged) {
        currentDraft = correctionResult.corrected;
        console.log(`✨ 수정 완료: ${correctionResult.originalLength}자 → ${correctionResult.correctedLength}자`);
      } else {
        console.warn(`⚠️ Corrector 수정 실패: ${correctionResult.error || '변경 없음'}`);
        // 수정 실패해도 루프 계속
      }
    } else {
      // SOFT 위반만 있으면 경고하고 통과
      console.log(`ℹ️ SOFT 위반만 발견 (${criticReport.violations.length}건) - 통과 처리`);
      notifyProgress('COMPLETED', {
        score: criticReport.score,
        warnings: criticReport.violations.length
      });
      return currentDraft;
    }
  }

  // ========================================
  // Phase 3: 루프 종료 - 최선 버전 반환
  // ========================================
  console.warn(`⚠️ Critic 루프 ${maxCriticAttempts}회 완료 - 최선 버전 반환 (점수: ${bestScore})`);

  notifyProgress('COMPLETED', {
    score: bestScore,
    warning: '일부 품질 기준 미달 - 수동 검토 권장'
  });

  // 최종 버전과 최고 점수 버전 비교
  const finalDraft = bestScore >= 70 ? bestVersion : currentDraft;

  return finalDraft || currentDraft || draft;
}

// ============================================================================
// Legacy 호환 함수
// ============================================================================

/**
 * LLM을 활용한 원고 품질 검증 (Legacy - Critic으로 대체)
 */
async function evaluateQualityWithLLM(content, modelName) {
  // Critic Agent로 대체됨 - 하위 호환성 유지
  return { passed: true, issues: [], suggestions: [] };
}

module.exports = {
  validateAndRetry,
  evaluateQualityWithLLM,
  // 개별 검증 함수도 export (테스트용)
  detectSentenceRepetition,
  detectElectionLawViolation,
  runHeuristicValidation,
  validateKeywordInsertion,
  countKeywordOccurrences,
  // Progress 관련
  GENERATION_STAGES
};
