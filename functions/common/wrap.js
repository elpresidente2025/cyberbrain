'use strict';

const { onCall, HttpsError } = require('firebase-functions/v2/https');
const { GEMINI_API_KEY } = require('./secrets');

// 공통 함수 옵션 - CORS 설정 강화
const functionOptions = {
  cors: true, // 모든 도메인 허용 (CORS 문제 방지)
  maxInstances: 10,
  timeoutSeconds: 300, // 5분으로 증가 (SNS 변환용)
  memory: '1GiB', // 메모리도 증가
  secrets: [GEMINI_API_KEY]
};

/**
 * Firebase Functions v2 onCall 래퍼
 * 에러 처리 및 로깅을 공통화
 */
exports.wrap = (handler) => {
  return onCall(functionOptions, async (request) => {
    const startTime = Date.now();
    const { uid } = request.auth || {};

    try {
      console.log(`🔥 함수 시작: ${handler.name || 'unknown'}, 사용자: ${uid || 'anonymous'}`);
      console.log(`🔍 요청 데이터:`, JSON.stringify({
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
      console.error(`❌ 오류 상세:`, {
        name: error.name,
        message: error.message,
        code: error.code,
        stack: error.stack?.substring(0, 500)
      });

      // Firebase HttpsError는 그대로 전달
      if (error instanceof HttpsError) {
        console.error(`❌ HttpsError 재전송: ${error.code} - ${error.message}`);
        throw error;
      }

      // 일반 에러는 internal 에러로 변환
      console.error(`❌ 일반 에러를 HttpsError로 변환: ${error.message}`);
      throw new HttpsError('internal', '서버 내부 오류가 발생했습니다.');
    }
  });
};
