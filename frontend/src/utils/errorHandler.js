/**
 * HTTP 에러 처리 유틸리티
 * 공통 에러 처리 로직을 중앙화
 */

export const handleHttpError = (error) => {
  console.error('HTTP Error:', error);

  const errorMessage = error.message || '';

  // 인증 관련 에러
  if (errorMessage.includes('401') || errorMessage.includes('Unauthorized')) {
    return '로그인이 필요합니다. 다시 로그인해주세요.';
  }

  // 사용량 제한 에러
  if (errorMessage.includes('429')) {
    return 'AI 사용량을 초과했습니다. 잠시 후 다시 시도해주세요.';
  }

  // 서버 에러
  if (errorMessage.includes('503') || errorMessage.includes('502')) {
    return 'AI 서비스가 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해주세요.';
  }

  // 타임아웃 에러
  if (errorMessage.includes('408') || errorMessage.includes('timeout')) {
    return 'AI 응답 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.';
  }

  // 요청 데이터 에러
  if (errorMessage.includes('400')) {
    return errorMessage || '입력된 정보를 확인해주세요.';
  }

  // Firebase Functions 에러
  if (error.code === 'functions/permission-denied') {
    return '권한이 없습니다. 로그인을 확인해주세요.';
  }

  if (error.code === 'functions/invalid-argument') {
    return '요청 데이터가 올바르지 않습니다. 내용을 확인해주세요.';
  }

  // 기본 에러 메시지
  return errorMessage || '요청 처리 중 오류가 발생했습니다.';
};