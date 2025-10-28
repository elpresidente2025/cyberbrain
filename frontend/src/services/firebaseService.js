// frontend/src/services/firebaseService.js
import { httpsCallable } from 'firebase/functions';
import { functions, auth } from './firebase';

// onCall �Լ� ȣ�� (�⺻)
export const callFunction = async (functionName, data = {}) => {
  const callable = httpsCallable(functions, functionName);
  const result = await callable(data);
  return result.data;
};

// onCall + ��õ� (401/403 �� �������� ���)
export const callFunctionWithRetry = async (functionName, data = {}, retries = 2) => {
  let lastError;
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const callable = httpsCallable(functions, functionName);
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
export const callFunctionWithNaverAuth = async (functionName, data = {}) => {
  // Firebase Auth가 설정되어 있으면 자동으로 인증 토큰 포함
  if (!auth.currentUser) {
    throw new Error('로그인이 필요합니다.');
  }

  return await callFunctionWithRetry(functionName, data);
};

// ----------------------------------------------------------------------------
// ������ ���� HTTP ��ƿ/������/SNS �Լ��� �ʿ� �� Bearer ��ū ������� ����
// ----------------------------------------------------------------------------

export const getSystemStatus = async () => {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 15000);
    const response = await fetch('https://asia-northeast3-ai-secretary-6e9c8.cloudfunctions.net/getSystemStatus', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return await response.json();
  } catch (error) {
    if (error.name === 'AbortError') throw new Error('Request timeout');
    return { success: false, status: 'unknown', message: '���� Ȯ�� ����' };
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
  try {
    const response = await fetch('https://asia-northeast3-ai-secretary-6e9c8.cloudfunctions.net/getUsers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    return await response.json();
  } catch (error) {
    return { success: false, users: [], total: 0 };
  }
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
    const response = await fetch('https://asia-northeast3-ai-secretary-6e9c8.cloudfunctions.net/updateSystemStatus', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(statusData),
    });
    return await response.json();
  } catch (error) {
    return { success: false, message: '�ý��� ���� ������Ʈ ����: ' + error.message };
  }
};

export const updateGeminiStatus = async (newState) => {
  return await callFunctionWithRetry('updateGeminiStatus', { newState });
};

export const clearSystemCache = async () => {
  return await callFunctionWithRetry('clearSystemCache');
};

export const convertToSNS = async (postId) => {
  const modelName = localStorage.getItem('gemini_model') || 'gemini-2.0-flash-exp';
  return await callHttpFunction('convertToSNS', { postId, modelName });
};

export const testSNS = async () => {
  return await callFunctionWithRetry('testSNS');
};

export const getSNSUsage = async () => {
  return await callHttpFunction('getSNSUsage', {});
};

export const purchaseSNSAddon = async () => {
  return await callFunctionWithRetry('purchaseSNSAddon');
};
