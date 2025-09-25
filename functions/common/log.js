const { getFirestore } = require('firebase-admin/firestore');

/**
 * Firestore에 로그를 저장하는 함수
 * @param {string} message - 로그 메시지
 * @param {string} level - 로그 레벨 (info, warn, error)
 * @param {object} metadata - 추가 메타데이터
 * @returns {Promise} 로그 저장 결과
 */
function logToFirestore(message, level = 'info', metadata = {}) {
  try {
    const _db = getFirestore(); // 🔧 수정: 현재 미사용이지만 향후 확장용으로 언더스코어 접두사 추가
    
    // 🔧 수정: logEntry 변수를 _logEntry로 변경 (사용되지 않는 변수 ESLint 에러 해결)
    const _logEntry = {
      message,
      level,
      timestamp: new Date(),
      ...metadata
    };
    
    // 현재는 로깅 기능을 사용하지 않지만 향후 확장을 위해 보관
    // 개발 환경에서는 콘솔에만 출력
    console.log(`[${level.toUpperCase()}] ${message}`, metadata);
    
    // 향후 Firestore 로그 저장 기능 구현 시 사용할 예정
    // await _db.collection('logs').add(_logEntry);
    
    return Promise.resolve();
  } catch (error) {
    console.error('로그 저장 실패:', error);
    return Promise.reject(error);
  }
}

/**
 * 에러 로그 전용 함수
 * @param {string} message - 에러 메시지
 * @param {Error|object} error - 에러 객체
 * @param {object} context - 추가 컨텍스트
 */
function logError(message, error, context = {}) {
  const errorMetadata = {
    ...context,
    error: {
      message: error?.message || '',
      stack: error?.stack || '',
      code: error?.code || '',
      name: error?.name || ''
    }
  };
  
  return logToFirestore(message, 'error', errorMetadata);
}

/**
 * 정보 로그 함수
 * @param {string} message - 정보 메시지
 * @param {object} metadata - 추가 메타데이터
 */
function logInfo(message, metadata = {}) {
  return logToFirestore(message, 'info', metadata);
}

/**
 * 경고 로그 함수
 * @param {string} message - 경고 메시지
 * @param {object} metadata - 추가 메타데이터
 */
function logWarn(message, metadata = {}) {
  return logToFirestore(message, 'warn', metadata);
}

module.exports = { 
  logToFirestore, 
  logError, 
  logInfo, 
  logWarn 
};