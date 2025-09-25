// src/services/api.js
const API_BASE = 'https://asia-northeast3-ai-secretary-6e9c8.cloudfunctions.net';

// 기본 fetch 래퍼
const apiCall = async (endpoint, options = {}) => {
  const url = `${API_BASE}/${endpoint}`;
  
  const config = {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers
    },
    ...options
  };

  console.log(`🌐 API 호출: ${endpoint}`, config.body ? JSON.parse(config.body) : {});

  try {
    const response = await fetch(url, config);
    
    if (!response.ok) {
      throw new Error(`API 오류: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();
    console.log(`✅ API 응답: ${endpoint}`, data);
    return data;

  } catch (error) {
    console.error(`❌ API 호출 실패: ${endpoint}`, error);
    throw error;
  }
};

// 전자두뇌비서관 API 서비스
export const api = {
  // 원고 생성 (현재 문제 해결용 - generatePosts 호출)
  generatePost: async (data) => {
    return await apiCall('generatePosts', {
      body: JSON.stringify({
        prompt: data.prompt,
        category: data.category,
        subCategory: data.subCategory || '',
        keywords: data.keywords || '',
        userName: data.userName || '의원',
        userId: data.userId || 'test-user'
      })
    });
  },


  // 사용자 프로필 조회
  getUserProfile: async (userId) => {
    return await apiCall('getUserProfile', {
      body: JSON.stringify({ userId })
    });
  },

  // 사용자 포스트 목록 조회
  getUserPosts: async (userId) => {
    return await apiCall('getUserPosts', {
      body: JSON.stringify({ userId })
    });
  },

  // 포스트 저장
  savePost: async (postData, userId) => {
    return await apiCall('savePost', {
      body: JSON.stringify({
        post: postData,
        userId: userId,
        metadata: {
          savedAt: new Date().toISOString()
        }
      })
    });
  },

  // 대시보드 데이터 조회
  getDashboardData: async (userId) => {
    return await apiCall('getDashboardData', {
      body: JSON.stringify({ userId })
    });
  }
};

// 개발용 설정
if (import.meta.env.DEV) {
  window.api = api; // 개발자 도구에서 테스트 가능
}