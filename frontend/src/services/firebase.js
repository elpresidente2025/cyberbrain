import { initializeApp } from 'firebase/app';
import { getAuth, setPersistence, browserLocalPersistence } from 'firebase/auth';
import { getFirestore } from 'firebase/firestore';
import { getFunctions } from 'firebase/functions';
import { getStorage } from 'firebase/storage';

const defaultFirebaseConfig = {
  apiKey: 'AIzaSyDCMWyvRnyIesV9xATK-9RnObgDntmVadg',
  authDomain: 'ai-secretary-6e9c8.firebaseapp.com',
  projectId: 'ai-secretary-6e9c8',
  storageBucket: 'ai-secretary-6e9c8.firebasestorage.app',
  messagingSenderId: '527392419804',
  appId: '1:527392419804:web:9c9f355f250366cd716919',
  measurementId: 'G-LFJQF290TW',
};

const readFirebaseEnv = (key, fallbackValue) => {
  const value = import.meta.env[key];

  if (typeof value === 'string' && value.trim()) {
    return value.trim();
  }

  return fallbackValue;
};

// Firebase 설정
const firebaseConfig = {
  apiKey: readFirebaseEnv('VITE_FIREBASE_API_KEY', defaultFirebaseConfig.apiKey),
  authDomain: readFirebaseEnv('VITE_FIREBASE_AUTH_DOMAIN', defaultFirebaseConfig.authDomain),
  projectId: readFirebaseEnv('VITE_FIREBASE_PROJECT_ID', defaultFirebaseConfig.projectId),
  storageBucket: readFirebaseEnv('VITE_FIREBASE_STORAGE_BUCKET', defaultFirebaseConfig.storageBucket),
  messagingSenderId: readFirebaseEnv('VITE_FIREBASE_MESSAGING_SENDER_ID', defaultFirebaseConfig.messagingSenderId),
  appId: readFirebaseEnv('VITE_FIREBASE_APP_ID', defaultFirebaseConfig.appId),
  measurementId: readFirebaseEnv('VITE_FIREBASE_MEASUREMENT_ID', defaultFirebaseConfig.measurementId),
};

if (firebaseConfig.apiKey === defaultFirebaseConfig.apiKey) {
  console.warn('VITE_FIREBASE_API_KEY가 없어 기본 Firebase 웹 설정을 사용합니다.');
}

// Firebase 앱 초기화
const app = initializeApp(firebaseConfig);

// 다른 파일에서 사용하도록 export
export { app };
export const firebaseApiKey = firebaseConfig.apiKey;
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

// Analytics (비활성화 - API 키 제한으로 인한 에러 방지)
// 필요시 Google Cloud Console에서 API 키 제한 해제 후 활성화
export const analytics = null;
// export const analytics = typeof window !== 'undefined' ? getAnalytics(app) : null;
