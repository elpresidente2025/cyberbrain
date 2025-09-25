// 브라우저 콘솔에서 실행할 플랜 동기화 디버깅 스크립트

console.log('🔧 플랜 동기화 디버깅 도구 로드됨');

// 1. 현재 사용자 정보 확인
const checkCurrentUser = () => {
  console.log('=== 현재 사용자 정보 ===');
  
  // React DevTools가 있다면 useAuth 훅 결과 확인 가능
  const elements = document.querySelectorAll('[data-testid], [data-cy]');
  console.log('페이지 요소들:', elements.length);
  
  // Firebase Auth 사용자 확인
  if (window.firebase && window.firebase.auth) {
    const currentUser = window.firebase.auth().currentUser;
    console.log('Firebase Auth User:', currentUser);
  }
  
  // 글로벌 상태에서 user 찾기 (개발 모드에서만 가능할 수도 있음)
  console.log('window 객체에서 user 관련 찾기...');
  Object.keys(window).forEach(key => {
    if (key.includes('user') || key.includes('auth')) {
      console.log(`${key}:`, window[key]);
    }
  });
};

// 2. 플랜 강제 설정 (테스트용)
const forceSetPlan = async (planName) => {
  console.log(`🎯 플랜을 '${planName}'으로 강제 설정 시도...`);
  
  try {
    // Firebase 함수 직접 호출
    const functions = window.firebase?.functions?.();
    if (functions) {
      const updatePlan = functions.httpsCallable('updateUserPlan');
      const result = await updatePlan({ plan: planName });
      console.log('✅ 플랜 설정 성공:', result);
      
      // 페이지 새로고침으로 강제 동기화
      console.log('페이지를 새로고침합니다...');
      window.location.reload();
    } else {
      console.error('❌ Firebase functions를 찾을 수 없습니다');
    }
  } catch (error) {
    console.error('❌ 플랜 설정 실패:', error);
  }
};

// 3. 로컬스토리지/세션스토리지 초기화
const clearAuthCache = () => {
  console.log('🗑️ 인증 캐시 초기화...');
  
  // Firebase 관련 저장소 항목들 찾기
  const keysToRemove = [];
  
  // localStorage 확인
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && (key.includes('firebase') || key.includes('auth') || key.includes('user'))) {
      keysToRemove.push({ storage: 'local', key });
    }
  }
  
  // sessionStorage 확인
  for (let i = 0; i < sessionStorage.length; i++) {
    const key = sessionStorage.key(i);
    if (key && (key.includes('firebase') || key.includes('auth') || key.includes('user'))) {
      keysToRemove.push({ storage: 'session', key });
    }
  }
  
  console.log('찾은 캐시 키들:', keysToRemove);
  
  // 삭제 확인
  const shouldClear = confirm(`${keysToRemove.length}개의 캐시 항목을 삭제하시겠습니까?`);
  if (shouldClear) {
    keysToRemove.forEach(({ storage, key }) => {
      if (storage === 'local') {
        localStorage.removeItem(key);
      } else {
        sessionStorage.removeItem(key);
      }
    });
    console.log('✅ 캐시 삭제 완료. 페이지를 새로고침하세요.');
  }
};

// 전역 함수로 등록
window.checkCurrentUser = checkCurrentUser;
window.forceSetPlan = forceSetPlan;
window.clearAuthCache = clearAuthCache;

console.log('사용 가능한 함수들:');
console.log('- checkCurrentUser() : 현재 사용자 정보 확인');
console.log('- forceSetPlan("오피니언 리더") : 플랜 강제 설정');
console.log('- clearAuthCache() : 인증 캐시 초기화');

// 자동으로 현재 사용자 정보 확인
checkCurrentUser();