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

// HTTP(onRequest) 함수 호출: 네이버 인증 전용
export const callHttpFunction = async (functionName, data = {}) => {
  // localStorage에서 네이버 사용자 정보 확인
  const storedUser = localStorage.getItem('currentUser');
  if (!storedUser) {
    throw new Error('로그인이 필요합니다.');
  }

  let userData;
  try {
    userData = JSON.parse(storedUser);
  } catch (e) {
    throw new Error('사용자 정보를 읽을 수 없습니다.');
  }

  if (!userData.uid || userData.provider !== 'naver') {
    throw new Error('유효하지 않은 사용자 정보입니다.');
  }

  const projectId = functions.app.options.projectId;
  const region = 'asia-northeast3';
  const url = `https://${region}-${projectId}.cloudfunctions.net/${functionName}`;

  const requestOptions = {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...data,
      __naverAuth: { uid: userData.uid, provider: 'naver' }
    })
  };

  const response = await fetch(url, requestOptions);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`HTTP ${response.status}: ${text}`);
  }
  const raw = await response.json();
  return raw && typeof raw === 'object' && 'data' in raw ? raw.data : raw;
};

// ���� ȣȯ: ���� �̸��� �� ���۷� ����
export const callFunctionWithNaverAuth = async (functionName, data = {}) => {
  // localStorage에서 네이버 사용자 정보 확인
  const storedUser = localStorage.getItem('currentUser');
  if (!storedUser) {
    throw new Error('로그인이 필요합니다.');
  }

  let userData;
  try {
    userData = JSON.parse(storedUser);
  } catch (e) {
    throw new Error('사용자 정보를 읽을 수 없습니다.');
  }

  if (!userData.uid || userData.provider !== 'naver') {
    throw new Error('유효하지 않은 사용자 정보입니다.');
  }

  // __naverAuth 객체를 데이터에 추가
  const dataWithAuth = {
    ...data,
    __naverAuth: { uid: userData.uid, provider: 'naver' }
  };

  return await callFunctionWithRetry(functionName, dataWithAuth);
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
  try {
    const response = await fetch('https://asia-northeast3-ai-secretary-6e9c8.cloudfunctions.net/getAdminStats', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    return await response.json();
  } catch (error) {
    return { success: false, stats: { todaySuccess: 0, todayFail: 0, last30mErrors: 0, activeUsers: 0, geminiStatus: { state: 'unknown' } } };
  }
};

export const getErrorLogs = async () => {
  try {
    const response = await fetch('https://asia-northeast3-ai-secretary-6e9c8.cloudfunctions.net/getErrorLogs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    return await response.json();
  } catch (error) {
    return { success: false, message: '���� �α׸� �ҷ����� ���߽��ϴ�.' };
  }
};

export const getNotices = async () => {
  try {
    const response = await fetch('https://asia-northeast3-ai-secretary-6e9c8.cloudfunctions.net/getNotices', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    return await response.json();
  } catch (error) {
    return { success: false, notices: [] };
  }
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
  const modelName = localStorage.getItem('gemini_model') || 'gemini-1.5-flash';
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
