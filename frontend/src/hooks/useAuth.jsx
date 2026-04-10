import React, { useState, useEffect, createContext, useContext } from 'react';
import { normalizeAuthUser } from '../utils/authz';

const AuthContext = createContext();

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const checkNaverUser = () => {
    try {
      const storedUser = localStorage.getItem('currentUser');
      if (storedUser) {
        const userData = normalizeAuthUser(JSON.parse(storedUser));
        if (userData?.uid && userData?.provider === 'naver') {
          return userData;
        }
      }
    } catch (e) {
      console.warn('localStorage 사용자 정보 읽기 실패:', e);
    }
    return null;
  };

  useEffect(() => {
    let unsubscribeAuth = null;

    const initAuth = async () => {
      try {
        const { auth } = await import('../services/firebase');
        const { onAuthStateChanged } = await import('firebase/auth');

        unsubscribeAuth = onAuthStateChanged(auth, (firebaseUser) => {
          if (firebaseUser) {
            console.log('🔵 useAuth: Firebase Auth 사용자 인증됨', firebaseUser.uid);

            let naverUser = checkNaverUser();

            if (naverUser && naverUser.uid !== firebaseUser.uid) {
              console.warn('⚠️ useAuth: localStorage UID 불일치 감지', {
                localStorageUid: naverUser.uid,
                firebaseUid: firebaseUser.uid
              });
              localStorage.removeItem('currentUser');
              naverUser = null;
            }

            if (naverUser) {
              const updatedUser = normalizeAuthUser({
                ...naverUser,
                email: naverUser.email || firebaseUser.email || firebaseUser.providerData?.[0]?.email
              });

              if (updatedUser?.email && !naverUser.email) {
                localStorage.setItem('currentUser', JSON.stringify(updatedUser));
                console.log('🔵 useAuth: email 추가 후 localStorage 업데이트:', updatedUser.email);
              }

              setUser(updatedUser);
            } else {
              const basicUser = normalizeAuthUser({
                uid: firebaseUser.uid,
                provider: 'naver',
                displayName: firebaseUser.displayName || '사용자',
                email: firebaseUser.email
              });
              setUser(basicUser);
            }
          } else {
            console.log('🔵 useAuth: 로그아웃 상태');
            setUser(null);
          }
          setLoading(false);
        });
      } catch (e) {
        console.error('🔵 useAuth 초기화 에러:', e);
        setError(e.message);
        setUser(null);
        setLoading(false);
      }
    };

    initAuth();

    const handleStorageChange = (e) => {
      if (e.key === 'currentUser') {
        console.log('🔵 useAuth: localStorage 변경 감지');
        const naverUser = checkNaverUser();
        if (naverUser) {
          setUser(naverUser);
        }
      }
    };

    const handleNaverAuthUpdate = (e) => {
      console.log('🔵 useAuth: 프로필 업데이트 이벤트', e.detail);
      setUser(normalizeAuthUser(e.detail));
    };

    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('userProfileUpdated', handleNaverAuthUpdate);

    return () => {
      if (unsubscribeAuth) unsubscribeAuth();
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('userProfileUpdated', handleNaverAuthUpdate);
    };
  }, []);

  const logout = async () => {
    try {
      const { auth } = await import('../services/firebase');
      const { signOut } = await import('firebase/auth');
      await signOut(auth);

      localStorage.removeItem('currentUser');
      setUser(null);
      console.log('🔵 useAuth: 로그아웃 완료');
    } catch (e) {
      console.error('🔵 useAuth: 로그아웃 에러:', e);
    }
  };

  const refreshUserProfile = async () => {
    try {
      const currentUser = checkNaverUser();
      if (!currentUser || !currentUser.uid) {
        console.warn('🔵 refreshUserProfile: 사용자 정보 없음');
        return;
      }

      console.log('🔵 refreshUserProfile: Cloud Function으로 최신 프로필 가져오기 시작');

      const { functions } = await import('../services/firebase');
      const { httpsCallable } = await import('firebase/functions');

      const getUserProfile = httpsCallable(functions, 'getUserProfile');
      const result = await getUserProfile({
        __naverAuth: {
          uid: currentUser.uid,
          provider: 'naver'
        }
      });

      if (result.data?.profile) {
        const firestoreData = result.data.profile;
        console.log('🔵 refreshUserProfile: Cloud Function 데이터', {
          verificationStatus: firestoreData.verificationStatus,
          lastVerification: firestoreData.lastVerification
        });

        const updatedUser = normalizeAuthUser({
          ...currentUser,
          ...firestoreData,
          uid: currentUser.uid
        });

        localStorage.setItem('currentUser', JSON.stringify(updatedUser));
        setUser(updatedUser);

        console.log('🔵 refreshUserProfile: 프로필 업데이트 완료');
      } else {
        console.warn('🔵 refreshUserProfile: 프로필 데이터 없음');
      }
    } catch (error) {
      console.error('🔵 refreshUserProfile 에러:', error);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, error, logout, refreshUserProfile }}>
      {children}
    </AuthContext.Provider>
  );
};
