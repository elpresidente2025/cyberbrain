/**
 * HTTP 에러 처리 유틸리티
 * 공통 에러 처리 로직을 중앙화
 */

export const handleHttpError = (error) => {
  console.error('HTTP Error:', error);

  const errorMessage = error.message || '';
  const errorCode = error.code || '';

  // ============================================================================
  // Firebase Functions 에러 (우선 처리)
  // ============================================================================

  // 사용량 제한 에러 (무료 체험 소진, 월간 한도 초과, 세션 시도 횟수 초과)
  if (errorCode === 'functions/resource-exhausted') {
    // 서버에서 보낸 실제 메시지 사용
    return errorMessage || '사용 횟수를 모두 소진했습니다.';
  }

  // 사전 조건 실패 (구독 만료, 당원 인증 필요, 체험 기간 종료 등)
  if (errorCode === 'functions/failed-precondition') {
    return errorMessage || '서비스 이용 조건을 확인해주세요.';
  }

  // 권한 거부 (결제 기반 우선권 없음 등)
  if (errorCode === 'functions/permission-denied') {
    return errorMessage || '서비스 이용 권한이 없습니다.';
  }

  // 인증 실패
  if (errorCode === 'functions/unauthenticated') {
    return '로그인이 필요합니다. 다시 로그인해주세요.';
  }

  // 잘못된 요청 데이터
  if (errorCode === 'functions/invalid-argument') {
    return errorMessage || '입력된 정보를 확인해주세요.';
  }

  // 내부 서버 에러
  if (errorCode === 'functions/internal') {
    return errorMessage || '서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.';
  }

  // ============================================================================
  // HTTP 상태 코드 기반 에러
  // ============================================================================

  // 인증 관련 에러
  if (errorMessage.includes('401') || errorMessage.includes('Unauthorized')) {
    return '로그인이 필요합니다. 다시 로그인해주세요.';
  }

  // 사용량 제한 에러 (429)
  if (errorMessage.includes('429')) {
    return 'API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요.';
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

  // ============================================================================
  // 기본 에러 메시지
  // ============================================================================
  return errorMessage || '요청 처리 중 오류가 발생했습니다.';
};