'use strict';

const { onCall, HttpsError } = require('firebase-functions/v2/https');
const { GEMINI_API_KEY } = require('./secrets');

const baseOptions = {
  cors: true,
  maxInstances: 10,
};

const liteFunctionOptions = {
  ...baseOptions,
  maxInstances: 20,
  timeoutSeconds: 60,
  memory: '256MiB',
};

const defaultFunctionOptions = {
  ...baseOptions,
  timeoutSeconds: 300,
  memory: '1GiB',
  secrets: [GEMINI_API_KEY],
};

const heavyFunctionOptions = {
  ...baseOptions,
  timeoutSeconds: 540,
  memory: '1GiB',
  secrets: [GEMINI_API_KEY],
};

function createWrap(functionOptions) {
  return (handler) => onCall(functionOptions, async (request) => {
    const startTime = Date.now();
    const { uid } = request.auth || {};

    try {
      console.log(`🚦 함수 시작: ${handler.name || 'unknown'}, 사용자: ${uid || 'anonymous'}`);
      console.log('📥 요청 데이터', JSON.stringify({
        auth: request.auth ? { uid: request.auth.uid } : null,
        data: request.data
      }, null, 2));

      const result = await handler(request);

      const duration = Date.now() - startTime;
      console.log(`✅ 함수 완료: ${handler.name || 'unknown'}, 소요시간: ${duration}ms`);

      return result;
    } catch (error) {
      const duration = Date.now() - startTime;
      console.error(`❌ 함수 오류: ${handler.name || 'unknown'}, 소요시간: ${duration}ms`);
      console.error('❌ 오류 상세:', {
        name: error.name,
        message: error.message,
        code: error.code,
        stack: error.stack?.substring(0, 500)
      });

      if (error instanceof HttpsError) {
        console.error(`📤 HttpsError 사전 처리: ${error.code} - ${error.message}`);
        throw error;
      }

      console.error(`❌ 일반 오류를 HttpsError로 변환: ${error.message}`);
      throw new HttpsError('internal', '서버 내부 오류가 발생했습니다.');
    }
  });
}

exports.wrapLite = createWrap(liteFunctionOptions);
exports.wrapDefault = createWrap(defaultFunctionOptions);
exports.wrapHeavy = createWrap(heavyFunctionOptions);
exports.wrap = exports.wrapDefault;