// frontend/src/services/firebaseService.js
import { httpsCallable } from 'firebase/functions';
import { functions, auth } from './firebase';

const buildCallable = (functionName, options = {}) => {
  const callableOptions = {};
  if (options.timeoutMs) {
    callableOptions.timeout = options.timeoutMs;
  }
  return Object.keys(callableOptions).length > 0
    ? httpsCallable(functions, functionName, callableOptions)
    : httpsCallable(functions, functionName);
};

// onCall 함수 호출 (기본)
export const callFunction = async (functionName, data = {}, options = {}) => {
  const callable = buildCallable(functionName, options);
  const result = await callable(data);
  return result.data;
};

// onCall + 재시도 (401/403 등 인증 관련 오류 처리)
export const callFunctionWithRetry = async (functionName, data = {}, options = {}) => {
  const isRetryNumber = typeof options === 'number';
  const retries = isRetryNumber ? options : (options.retries ?? 2);
  const timeoutMs = isRetryNumber ? undefined : options.timeoutMs;
  let lastError;
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const callable = buildCallable(functionName, { timeoutMs });
      const result = await callable(data);
      return result.data;
    } catch (error) {
      lastError = error;
      if (
        attempt < retries && (
          error?.code === 'functions/unauthenticated' ||
          error?.code === 'functions/permission-denied'
        )
      ) {
        await new Promise((r) => setTimeout(r, 800));
        continue;
      }
      throw error;
    }
  }
  throw lastError || new Error('Function call failed');
};

// HTTP(onRequest) 함수 호출: 더 이상 사용되지 않음 (deprecated)
// ✅ 보안 강화: Firebase Auth 사용으로 __naverAuth 패턴 제거
export const callHttpFunction = async (functionName, data = {}) => {
  console.warn('⚠️ callHttpFunction은 deprecated입니다. callFunction을 사용하세요.');
  return await callFunction(functionName, data);
};

// 네이버 인증 함수 호출: 이제 일반 Firebase Auth 사용
// ✅ 보안 강화: Firebase Auth 사용으로 __naverAuth 패턴 제거
export const callFunctionWithNaverAuth = async (functionName, data = {}, options = {}) => {
  // Firebase Auth가 설정되어 있으면 자동으로 인증 토큰 포함
  console.log('🔐 callFunctionWithNaverAuth:', {
    functionName,
    hasCurrentUser: !!auth.currentUser,
    currentUser: auth.currentUser ? {
      uid: auth.currentUser.uid,
      email: auth.currentUser.email,
      displayName: auth.currentUser.displayName
    } : null
  });

  if (!auth.currentUser) {
    console.error('❌ Firebase Auth currentUser가 없습니다!');
    throw new Error('로그인이 필요합니다.');
  }

  // 토큰 확인
  try {
    const token = await auth.currentUser.getIdToken();
    console.log('✅ Firebase Auth 토큰 확인:', token ? '토큰 존재' : '토큰 없음');
  } catch (e) {
    console.error('❌ 토큰 가져오기 실패:', e);
  }

  return await callFunctionWithRetry(functionName, data, options);
};

// ----------------------------------------------------------------------------
// 관리자 전용 HTTP 엔드포인트/백오피스/SNS 함수는 Bearer 토큰 사용
// ----------------------------------------------------------------------------

export const getSystemStatus = async () => {
  try {
    // onCall 함수로 변경 (CORS 문제 해결 및 일관성 유지)
    const result = await callFunction('getSystemStatus', {});
    return result;
  } catch (error) {
    console.error('시스템 상태 조회 실패:', error);
    return { status: 'active', message: '상태 확인 실패 - 정상 상태로 간주' };
  }
};

export const getAdminStats = async () => {
  return await callFunction('getAdminStats', {});
};

export const getErrorLogs = async () => {
  return await callFunction('getErrorLogs', {});
};

export const getNotices = async () => {
  return await callFunction('getNotices', {});
};

export const getUsers = async (params = {}) => {
  // getAllUsers는 onCall 함수이므로 callFunction 사용
  console.log('📋 getUsers 호출 시작...');
  const result = await callFunction('getAllUsers', params);
  console.log('📋 getUsers 결과:', result);
  return result;
};

export const searchUsers = async (query, limit = 20) => {
  return await callFunctionWithRetry('searchUsers', { query, limit });
};

export const searchPosts = async (params) => {
  return await callFunctionWithRetry('searchPosts', params);
};

export const getErrors = async (params = {}) => {
  try {
    const result = await callFunctionWithRetry('getErrorLogs', params);
    if (result.success && result.data) {
      return { errors: result.data.errors || [], hasMore: result.data.hasMore || false, nextPageToken: result.data.nextPageToken || null };
    }
    return { errors: [] };
  } catch (error) {
    return { errors: [] };
  }
};

export const getUserDetail = async (userEmail) => {
  return await callFunctionWithRetry('getUserDetail', { userEmail });
};

export const updateSystemStatus = async (statusData) => {
  try {
    // onCall 함수로 변경 (관리자 인증 자동 처리)
    const result = await callFunctionWithRetry('updateSystemStatus', statusData);
    return result;
  } catch (error) {
    console.error('시스템 상태 업데이트 실패:', error);
    return { success: false, message: '시스템 상태 업데이트 실패: ' + error.message };
  }
};

export const updateGeminiStatus = async (newState) => {
  return await callFunctionWithRetry('updateGeminiStatus', { newState });
};

export const clearSystemCache = async () => {
  return await callFunctionWithRetry('clearSystemCache');
};

export const convertToSNS = async (postId) => {
  const modelName = localStorage.getItem('gemini_model') || 'gemini-2.5-flash-lite';
  return await callFunctionWithNaverAuth('convertToSNS', { postId, modelName });
};

export const testSNS = async () => {
  return await callFunctionWithRetry('testSNS');
};

export const getSNSUsage = async () => {
  return await callFunctionWithNaverAuth('getSNSUsage', {});
};
