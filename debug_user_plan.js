// 사용자 플랜 디버깅용 스크립트
// 브라우저 콘솔에서 실행하세요

console.log('=== 사용자 플랜 디버깅 ===');

// useAuth에서 user 객체 확인
const checkUserData = () => {
  // React DevTools나 브라우저에서 접근 가능한 방법으로 확인
  console.log('1. localStorage에서 Firebase Auth 토큰 확인');
  const keys = Object.keys(localStorage).filter(key => key.includes('firebase'));
  keys.forEach(key => {
    console.log(`${key}:`, localStorage.getItem(key));
  });

  console.log('2. sessionStorage 확인');
  const sessionKeys = Object.keys(sessionStorage).filter(key => key.includes('firebase'));
  sessionKeys.forEach(key => {
    console.log(`${key}:`, sessionStorage.getItem(key));
  });
};

// Firebase 사용자 정보 확인
const checkFirebaseAuth = () => {
  if (typeof firebase !== 'undefined' && firebase.auth) {
    const user = firebase.auth().currentUser;
    console.log('3. Firebase currentUser:', user);
  } else {
    console.log('3. Firebase not available in global scope');
  }
};

console.log('다음 함수들을 실행해보세요:');
console.log('checkUserData() - 로컬스토리지 확인');
console.log('checkFirebaseAuth() - Firebase Auth 사용자 확인');

window.checkUserData = checkUserData;
window.checkFirebaseAuth = checkFirebaseAuth;