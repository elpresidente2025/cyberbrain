// functions/utils/errorLogger.js
// 에러 로깅 유틸리티

const { admin, db } = require('./firebaseAdmin');

/**
 * 에러를 Firestore에 로그로 저장
 * @param {Error} error - 에러 객체
 * @param {Object} context - 추가 컨텍스트 정보
 */
async function logError(error, context = {}) {
  try {
    const errorData = {
      message: error.message || 'Unknown error',
      stack: error.stack || '',
      code: error.code || 'UNKNOWN',
      severity: determineSeverity(error),
      functionName: context.functionName || 'unknown',
      userId: context.userId || null,
      requestData: context.requestData || null,
      timestamp: admin.firestore.FieldValue.serverTimestamp(),
      environment: process.env.NODE_ENV || 'production',
      // 추가 메타데이터
      userAgent: context.userAgent || null,
      ipAddress: context.ipAddress || null,
      buildVersion: process.env.BUILD_VERSION || null
    };

    // 민감한 정보 제거
    if (errorData.requestData) {
      errorData.requestData = sanitizeRequestData(errorData.requestData);
    }

    await db.collection('error_logs').add(errorData);
    
    console.log(`📝 에러 로그 저장됨: ${error.message} (${errorData.severity})`);
  } catch (logError) {
    // 로깅 실패 시에도 원래 에러는 유지
    console.error('❌ 에러 로그 저장 실패:', logError);
  }
}

/**
 * 에러 심각도 결정
 * @param {Error} error
 * @returns {string} 'critical' | 'error' | 'warning'
 */
function determineSeverity(error) {
  // HTTP 에러 코드 기반 분류
  if (error.code) {
    if (error.code === 'permission-denied' || error.code === 'unauthenticated') {
      return 'warning';
    }
    if (error.code === 'internal' || error.code === 'unavailable') {
      return 'critical';
    }
  }

  // 메시지 기반 분류
  const message = error.message.toLowerCase();
  if (message.includes('timeout') || message.includes('connection')) {
    return 'critical';
  }
  if (message.includes('not found') || message.includes('invalid')) {
    return 'warning';
  }

  return 'error';
}

/**
 * 요청 데이터에서 민감한 정보 제거
 * @param {Object} requestData
 * @returns {Object}
 */
function sanitizeRequestData(requestData) {
  const sanitized = { ...requestData };
  
  // 민감한 필드들 제거 또는 마스킹
  const sensitiveFields = ['password', 'token', 'secret', 'key', 'auth'];
  
  function sanitizeObject(obj) {
    if (typeof obj !== 'object' || obj === null) {
      return obj;
    }
    
    const result = {};
    for (const [key, value] of Object.entries(obj)) {
      const lowerKey = key.toLowerCase();
      
      if (sensitiveFields.some(field => lowerKey.includes(field))) {
        result[key] = '[REDACTED]';
      } else if (typeof value === 'object') {
        result[key] = sanitizeObject(value);
      } else {
        result[key] = value;
      }
    }
    return result;
  }
  
  return sanitizeObject(sanitized);
}

/**
 * 성능 로그 저장 (응답 시간 등)
 * @param {string} functionName
 * @param {number} responseTime
 * @param {Object} metadata
 */
async function logPerformance(functionName, responseTime, metadata = {}) {
  try {
    await db.collection('performance_logs').add({
      functionName,
      responseTime,
      timestamp: admin.firestore.FieldValue.serverTimestamp(),
      metadata: metadata
    });
  } catch (error) {
    console.error('성능 로그 저장 실패:', error);
  }
}

/**
 * wrap 함수에서 사용할 에러 로거
 * @param {Error} error
 * @param {Object} context
 */
async function logWrapError(error, context) {
  await logError(error, {
    functionName: context.functionName,
    userId: context.auth?.uid,
    requestData: context.data,
    userAgent: context.headers?.['user-agent'],
    ipAddress: context.headers?.['x-forwarded-for'] || context.headers?.['x-real-ip']
  });
}

module.exports = {
  logError,
  logPerformance,
  logWrapError,
  determineSeverity,
  sanitizeRequestData
};