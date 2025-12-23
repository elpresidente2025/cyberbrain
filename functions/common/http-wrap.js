'use strict';

const { onRequest, HttpsError } = require('firebase-functions/v2/https');
const { defineSecret } = require('firebase-functions/params');

// 시크릿 정의
const HF_API_TOKEN = defineSecret('HF_API_TOKEN');
const UPSTASH_REDIS_REST_URL = defineSecret('UPSTASH_REDIS_REST_URL');
const UPSTASH_REDIS_REST_TOKEN = defineSecret('UPSTASH_REDIS_REST_TOKEN');

// HTTP 함수용 옵션
const httpFunctionOptions = {
  cors: {
    origin: [
      'https://cyberbrain.kr',
      'https://ai-secretary-6e9c8.web.app',
      'https://ai-secretary-6e9c8.firebaseapp.com',
      'http://localhost:5173',
      'http://localhost:5174'
    ],
    methods: ['GET', 'POST', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Requested-With'],
    credentials: true
  },
  maxInstances: 5,
  timeoutSeconds: 60,
  memory: '512MiB',
  secrets: [HF_API_TOKEN, UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN]
};

/**
 * Firebase Functions v2 onRequest 래퍼 (CORS 지원)
 */
exports.httpWrap = (handler) => {
  return onRequest(httpFunctionOptions, async (req, res) => {
    // CORS 헤더 설정
    const allowedOrigins = [
      'https://cyberbrain.kr',
      'https://ai-secretary-6e9c8.web.app',
      'https://ai-secretary-6e9c8.firebaseapp.com',
      'http://localhost:5173',
      'http://localhost:5174'
    ];

    const origin = req.headers.origin;
    if (allowedOrigins.includes(origin)) {
      res.set('Access-Control-Allow-Origin', origin);
    }

    res.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.set('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With');
    res.set('Access-Control-Allow-Credentials', 'true');

    // Preflight 요청 처리
    if (req.method === 'OPTIONS') {
      res.status(204).send('');
      return;
    }

    const startTime = Date.now();
    
    try {
      console.log(`🔥 HTTP 함수 시작: ${handler.name || 'unknown'}`);
      
      // onCall 형태의 request 객체로 변환
      const callRequest = {
        data: req.method === 'POST' ? req.body : req.query,
        auth: null, // HTTP에서는 인증 정보를 별도 처리
        rawRequest: req
      };
      
      const result = await handler(callRequest);
      
      const duration = Date.now() - startTime;
      console.log(`✅ HTTP 함수 완료: ${handler.name || 'unknown'}, 소요시간: ${duration}ms`);
      
      // Firebase SDK 호환 응답 형식 (callable 함수 형태)
      res.status(200).json({
        data: result
      });
      
    } catch (error) {
      const duration = Date.now() - startTime;
      console.error(`❌ HTTP 함수 오류: ${handler.name || 'unknown'}, 소요시간: ${duration}ms`, error);
      
      // Firebase HttpsError 처리 - Firebase SDK 호환 형식
      if (error instanceof HttpsError) {
        const statusCode = getStatusCode(error.code);
        res.status(statusCode).json({
          error: {
            code: error.code,
            message: error.message
          }
        });
        return;
      }
      
      // 일반 에러 처리 - Firebase SDK 호환 형식
      res.status(500).json({
        error: {
          code: 'internal',
          message: '서버 내부 오류가 발생했습니다.'
        }
      });
    }
  });
};

// HttpsError 코드를 HTTP 상태 코드로 변환
function getStatusCode(errorCode) {
  const statusMap = {
    'cancelled': 499,
    'unknown': 500,
    'invalid-argument': 400,
    'deadline-exceeded': 504,
    'not-found': 404,
    'already-exists': 409,
    'permission-denied': 403,
    'resource-exhausted': 429,
    'failed-precondition': 400,
    'aborted': 409,
    'out-of-range': 400,
    'unimplemented': 501,
    'internal': 500,
    'unavailable': 503,
    'data-loss': 500,
    'unauthenticated': 401
  };
  
  return statusMap[errorCode] || 500;
}