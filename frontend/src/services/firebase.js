import { initializeApp } from 'firebase/app';
import { getAuth, setPersistence, browserLocalPersistence } from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';
import { getFunctions } from 'firebase/functions';
import { getStorage } from 'firebase/storage';
import { getAnalytics } from 'firebase/analytics';

// Firebase 설정
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: 'ai-secretary-6e9c8.firebaseapp.com',
  projectId: 'ai-secretary-6e9c8',
  storageBucket: 'ai-secretary-6e9c8.firebasestorage.app',
  messagingSenderId: '527392419804',
  appId: '1:527392419804:web:9c9f355f250366cd716919',
  measurementId: 'G-LFJQF290TW'
};

// Firebase 앱 초기화
const app = initializeApp(firebaseConfig);

// 다른 파일에서 사용하도록 export
export { app };
export const auth = getAuth(app);
export const db = getFirestore(app);
export const storage = getStorage(app);

// Firebase Auth persistence 설정 (LocalStorage 사용)
setPersistence(auth, browserLocalPersistence).catch((error) => {
  console.error('Firebase Auth persistence 설정 실패:', error);
});

// Functions 인스턴스: 정확한 리전 지정 필수
// cyberbrain.kr은 Firebase Hosting이 아니므로 직접 리전 지정 필요
// asia-northeast3에 배포된 Functions와 정확히 매칭
export const functions = getFunctions(app, 'asia-northeast3');

// Analytics
export const analytics = getAnalytics(app);
