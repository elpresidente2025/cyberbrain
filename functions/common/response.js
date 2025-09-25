'use strict';

/**
 * 성공 응답 표준화
 */
exports.ok = (data = {}) => {
  return {
    success: true,
    ...data
  };
};

/**
 * 에러 응답 표준화
 */
exports.error = (message, code = 'internal', details = null) => {
  const response = {
    success: false,
    error: {
      code,
      message
    }
  };
  
  if (details) {
    response.error.details = details;
  }
  
  return response;
};