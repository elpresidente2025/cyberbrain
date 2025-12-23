/**
 * functions/services/posts/corrector.js
 * Corrector Agent - Critic이 발견한 위반 사항을 수정하는 모듈
 *
 * 역할:
 * - 위반 리포트를 받아 해당 부분만 정확히 수정
 * - 원본의 흐름과 분량은 최대한 유지
 */

'use strict';

const { callGenerativeModel } = require('../gemini');
const { logError } = require('../../common/log');

/**
 * Corrector 프롬프트 생성
 */
function buildCorrectorPrompt({ draft, violations, ragContext, authorName, status }) {
  // 위반 사항 포맷팅
  const violationsList = violations.map((v, i) => `
${i + 1}. [${v.severity}] ${v.type}
   위치: ${v.location}
   문제: "${v.problematic}"
   수정안: ${v.suggestion}`).join('\n');

  // 상태별 추가 지침
  let statusGuideline = '';
  if (status === '준비' || status === '현역') {
    statusGuideline = `
⚠️ 중요: 현재 상태가 "${status}"이므로, "~하겠습니다" 형태의 공약 표현을 모두 제거해야 합니다.
대체 표현: "~을 검토하고 있습니다", "~이 필요합니다", "~을 위해 노력 중입니다"`;
  }

  return `당신은 원고 수정 전문가입니다.
아래 초안에서 지적된 문제점만 정확히 수정하세요.

═══════════════════════════════════════
[수정할 초안]
═══════════════════════════════════════
${draft}

═══════════════════════════════════════
[발견된 문제점 - 반드시 수정할 것]
═══════════════════════════════════════
${violationsList}
${statusGuideline}

═══════════════════════════════════════
[참조 데이터 (팩트 확인용)]
수치나 사업명 수정 시 반드시 이 데이터를 참조하세요.
═══════════════════════════════════════
${ragContext || '(참조 데이터 없음 - 구체적 수치/사업명 사용 자제)'}

═══════════════════════════════════════
[수정 원칙]
═══════════════════════════════════════
1. 위에서 지적된 문제점만 수정하고, 나머지는 원문 그대로 유지
2. 글의 전체 흐름과 분량은 유지
3. 작성자 "${authorName || '의원'}님"의 입장에서 자연스럽게 수정
4. 수정된 부분도 문맥에 맞게 자연스럽게 연결

═══════════════════════════════════════
[출력 형식]
═══════════════════════════════════════
수정된 HTML 원고만 출력하세요.
설명이나 주석 없이 오직 수정된 원고 본문만 출력합니다.
JSON 형식이 아닌, HTML 형식의 원고 본문을 출력하세요.`;
}

/**
 * Corrector 응답 정제
 * - 불필요한 wrapper 제거
 * - HTML 태그 정리
 */
function cleanCorrectorResponse(response) {
  if (!response) return null;

  let cleaned = response.trim();

  // 마크다운 코드 블록 제거
  cleaned = cleaned.replace(/^```html?\s*/i, '');
  cleaned = cleaned.replace(/\s*```$/i, '');

  // JSON wrapper 제거 (실수로 JSON으로 응답한 경우)
  if (cleaned.startsWith('{') && cleaned.includes('"content"')) {
    try {
      const parsed = JSON.parse(cleaned);
      if (parsed.content) {
        cleaned = parsed.content;
      }
    } catch (e) {
      // JSON 파싱 실패 시 원본 유지
    }
  }

  // 앞뒤 공백 및 빈 줄 정리
  cleaned = cleaned.trim();

  return cleaned;
}

/**
 * 수정 결과 검증
 * - 원본과 너무 다르지 않은지 확인
 * - 최소 길이 확인
 */
function validateCorrection(original, corrected) {
  if (!corrected || corrected.length < 100) {
    return {
      valid: false,
      reason: '수정된 원고가 너무 짧습니다'
    };
  }

  // 원본 대비 길이 변화 확인 (50% ~ 150% 범위)
  const originalLength = original.replace(/<[^>]*>/g, '').length;
  const correctedLength = corrected.replace(/<[^>]*>/g, '').length;
  const ratio = correctedLength / originalLength;

  if (ratio < 0.5) {
    return {
      valid: false,
      reason: `수정 후 분량이 너무 줄었습니다 (${Math.round(ratio * 100)}%)`
    };
  }

  if (ratio > 1.5) {
    return {
      valid: false,
      reason: `수정 후 분량이 너무 늘었습니다 (${Math.round(ratio * 100)}%)`
    };
  }

  return { valid: true };
}

/**
 * Corrector Agent 실행
 *
 * @param {Object} options
 * @param {string} options.draft - 수정할 초안
 * @param {Array} options.violations - 위반 사항 배열
 * @param {string} options.ragContext - RAG 컨텍스트
 * @param {string} options.authorName - 작성자 이름
 * @param {string} options.status - 사용자 상태
 * @param {string} options.modelName - 사용할 모델
 * @returns {Promise<Object>} { success, corrected, error }
 */
async function applyCorrections({
  draft,
  violations,
  ragContext,
  authorName,
  status,
  modelName = 'gemini-1.5-flash'
}) {
  console.log(`✨ Corrector Agent 시작: ${violations.length}건 수정 예정`);

  // 위반 사항이 없으면 원본 반환
  if (!violations || violations.length === 0) {
    console.log('✨ 수정할 위반 사항 없음 - 원본 반환');
    return {
      success: true,
      corrected: draft,
      unchanged: true
    };
  }

  try {
    // Corrector 프롬프트 생성
    const prompt = buildCorrectorPrompt({
      draft,
      violations,
      ragContext,
      authorName,
      status
    });

    // Gemini 호출
    const response = await callGenerativeModel(prompt, 1, modelName);

    if (!response) {
      throw new Error('Corrector Agent 응답 없음');
    }

    // 응답 정제
    const corrected = cleanCorrectorResponse(response);

    // 수정 결과 검증
    const validation = validateCorrection(draft, corrected);

    if (!validation.valid) {
      console.warn(`⚠️ Corrector 검증 실패: ${validation.reason}`);
      return {
        success: false,
        corrected: draft,  // 원본 반환
        error: validation.reason
      };
    }

    console.log(`✨ Corrector 완료: ${draft.length}자 → ${corrected.length}자`);

    return {
      success: true,
      corrected,
      originalLength: draft.length,
      correctedLength: corrected.length
    };

  } catch (error) {
    console.error('❌ Corrector Agent 오류:', error.message);
    logError('applyCorrections', 'Corrector Agent 실행 실패', { error: error.message });

    return {
      success: false,
      corrected: draft,  // 원본 반환
      error: error.message
    };
  }
}

/**
 * HARD 위반만 필터링
 */
function filterHardViolations(violations) {
  return violations.filter(v => v.severity === 'HARD');
}

/**
 * 위반 사항 요약 문자열 생성
 */
function summarizeViolations(violations) {
  if (!violations || violations.length === 0) {
    return '위반 사항 없음';
  }

  const hard = violations.filter(v => v.severity === 'HARD').length;
  const soft = violations.filter(v => v.severity === 'SOFT').length;
  const political = violations.filter(v => v.severity === 'POLITICAL').length;

  const parts = [];
  if (hard > 0) parts.push(`치명적 ${hard}건`);
  if (soft > 0) parts.push(`개선필요 ${soft}건`);
  if (political > 0) parts.push(`권고 ${political}건`);

  return parts.join(', ');
}

module.exports = {
  buildCorrectorPrompt,
  cleanCorrectorResponse,
  validateCorrection,
  applyCorrections,
  filterHardViolations,
  summarizeViolations
};
