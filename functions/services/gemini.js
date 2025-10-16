/**
 * functions/services/gemini.js
 * Google Gemini AI 모델과의 통신을 전담하는 서비스 모듈입니다.
 * API 호출, 재시도 로직, 에러 처리 등을 담당합니다.
 */

'use strict';

const { GoogleGenerativeAI } = require('@google/generative-ai');
const { logError } = require('../common/log');
const { HttpsError } = require('firebase-functions/v2/https');

// Gemini API 키는 환경변수를 통해 관리됩니다.
const API_KEY = process.env.GEMINI_API_KEY;

/**
 * API 오류를 사용자 친화적인 메시지로 변환
 */
function getUserFriendlyErrorMessage(error) {
  const errorMessage = error.message || '';
  const errorString = String(error);
  
  // 429 Too Many Requests - 할당량 초과
  if (errorMessage.includes('429') || errorMessage.includes('Too Many Requests') || 
      errorMessage.includes('quota') || errorMessage.includes('exceeded')) {
    return '⚠️ AI 모델의 일일 사용량을 초과했습니다.\n\n• 내일 00시(한국시간) 이후 다시 시도해주세요.\n• 또는 관리자에게 문의하여 유료 플랜 업그레이드를 요청하세요.\n\n현재 무료 플랜: 하루 50회 제한';
  }
  
  // 401 Unauthorized - API 키 문제
  if (errorMessage.includes('401') || errorMessage.includes('Unauthorized') || 
      errorMessage.includes('API key')) {
    return '🔑 API 인증에 실패했습니다. 관리자에게 문의해주세요.';
  }
  
  // 403 Forbidden - 권한 문제
  if (errorMessage.includes('403') || errorMessage.includes('Forbidden')) {
    return '🚫 API 접근 권한이 없습니다. 관리자에게 문의해주세요.';
  }
  
  // 500 Internal Server Error - 서버 오류
  if (errorMessage.includes('500') || errorMessage.includes('Internal Server Error')) {
    return '🔧 AI 서비스에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요.';
  }
  
  // 네트워크 오류
  if (errorMessage.includes('ECONNRESET') || errorMessage.includes('ETIMEDOUT') || 
      errorMessage.includes('network') || errorMessage.includes('timeout')) {
    return '🌐 네트워크 연결에 문제가 발생했습니다. 잠시 후 다시 시도해주세요.';
  }
  
  // 빈 응답
  if (errorMessage.includes('빈 응답')) {
    return '📝 AI가 응답을 생성하지 못했습니다. 다른 주제로 다시 시도해주세요.';
  }
  
  // 기본 오류 메시지
  return `❌ AI 원고 생성 중 오류가 발생했습니다.\n\n오류 내용: ${errorMessage}\n\n관리자에게 문의하거나 잠시 후 다시 시도해주세요.`;
}

/**
 * @function callGenerativeModel
 * @description 주어진 프롬프트로 Gemini 모델을 호출하고, 텍스트 응답을 반환합니다.
 * @param {string} prompt - AI 모델에게 전달할 프롬프트
 * @param {number} retries - 실패 시 재시도 횟수
 * @param {string} modelName - 사용할 모델명 (기본값: gemini-2.0-flash-exp)
 * @param {boolean} useJsonMode - JSON 형식 응답 강제 (기본값: true)
 * @returns {Promise<string>} - AI가 생성한 텍스트
 */
async function callGenerativeModel(prompt, retries = 3, modelName = 'gemini-2.0-flash-exp', useJsonMode = true) {
  if (!API_KEY) {
    logError('callGenerativeModel', 'Gemini API 키가 설정되지 않았습니다.');
    throw new HttpsError('internal', 'AI 서비스 설정에 오류가 발생했습니다.');
  }

  const genAI = new GoogleGenerativeAI(API_KEY);
  
  // 모델별 설정
  const isGemini2 = modelName.includes('gemini-2.0');

  const generationConfig = {
    temperature: 0.3, // 정치인 원고: 창의성보다 지시 준수율 우선
    topK: 25,
    topP: 0.85,
    maxOutputTokens: isGemini2 ? 20000 : 20000, // 한국어 장문 콘텐츠 생성을 위한 토큰 증가
    stopSequences: [], // stopSequences는 출력을 제한하지만, 프롬프트 템플릿의 구분자(---)도 차단하므로 제거
  };

  // Gemini 2.0만 JSON mode 지원 (useJsonMode가 true일 때만)
  if (isGemini2 && useJsonMode) {
    generationConfig.responseMimeType = 'application/json';
  }

  const model = genAI.getGenerativeModel({
    model: modelName,
    generationConfig,
    safetySettings: [
      { category: 'HARM_CATEGORY_HARASSMENT', threshold: 'BLOCK_MEDIUM_AND_ABOVE' },
      { category: 'HARM_CATEGORY_HATE_SPEECH', threshold: 'BLOCK_MEDIUM_AND_ABOVE' },
      { category: 'HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold: 'BLOCK_MEDIUM_AND_ABOVE' },
      { category: 'HARM_CATEGORY_DANGEROUS_CONTENT', threshold: 'BLOCK_MEDIUM_AND_ABOVE' },
    ],
  });

  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      console.log(`🤖 Gemini API 호출 시도 (${attempt}/${retries}) - 모델: ${modelName}${isGemini2 ? ' [실험적]' : ''}`);
      const result = await model.generateContent(prompt);
      const response = await result.response;
      const text = response.text();

      if (!text || text.trim().length === 0) {
        throw new Error('Gemini API가 빈 응답을 반환했습니다.');
      }

      console.log(`✅ Gemini API 응답 성공 (${text.length}자) - 모델: ${modelName}`);
      return text;

    } catch (error) {
      console.error(`❌ Gemini API 오류 상세:`, {
        message: error.message,
        stack: error.stack,
        code: error.code,
        name: error.name,
        cause: error.cause,
        response: error.response,
        status: error.status,
        statusText: error.statusText
      });
      logError('callGenerativeModel', `Gemini API 시도 ${attempt} 실패`, { 
        error: error.message,
        code: error.code,
        name: error.name,
        fullError: String(error)
      });
      if (attempt === retries) {
        // 마지막 시도에서도 실패하면 에러를 던짐
        const userFriendlyMessage = getUserFriendlyErrorMessage(error);
        throw new HttpsError('unavailable', userFriendlyMessage);
      }
      // 재시도 전 잠시 대기 (Exponential backoff)
      await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
    }
  }
}

module.exports = {
  callGenerativeModel,
};
