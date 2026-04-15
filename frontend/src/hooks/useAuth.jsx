import React, { useState, useEffect, createContext, useContext } from 'react';
import { onAuthStateChanged, signOut } from 'firebase/auth';
import { httpsCallable } from 'firebase/functions';
import { auth, functions } from '../services/firebase';
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
    const unsubscribeAuth = onAuthStateChanged(auth, async (firebaseUser) => {
      if (firebaseUser) {
        let naverUser = checkNaverUser();

        if (naverUser && naverUser.uid !== firebaseUser.uid) {
          console.warn('localStorage UID 불일치 감지:', {
            localStorageUid: naverUser.uid,
            firebaseUid: firebaseUser.uid,
          });
          localStorage.removeItem('currentUser');
          naverUser = null;
        }

        let initialUser;
        if (naverUser) {
          initialUser = normalizeAuthUser({
            ...naverUser,
            email: naverUser.email || firebaseUser.email || firebaseUser.providerData?.[0]?.email,
          });

          if (initialUser?.email && !naverUser.email) {
            localStorage.setItem('currentUser', JSON.stringify(initialUser));
          }
        } else {
          initialUser = normalizeAuthUser({
            uid: firebaseUser.uid,
            provider: 'naver',
            displayName: firebaseUser.displayName || '사용자',
            email: firebaseUser.email,
          });
        }

        setUser(initialUser);

        // 백엔드에서 최신 프로필을 가져와 병합한다.
        // 온보딩 완료 여부(status/position/regionMetro 등)는 OnboardingGuard가
        // user 객체의 필드로 판정하기 때문에, loading=false 로 내려가기 전에
        // 반드시 프로필이 채워져 있어야 재방문 시 온보딩 화면으로 잘못 보내지 않는다.
        try {
          const getUserProfile = httpsCallable(functions, 'getUserProfile');
          const result = await getUserProfile({
            __naverAuth: {
              uid: initialUser.uid,
              provider: 'naver',
            },
          });

          if (result.data?.profile) {
            const refreshedUser = normalizeAuthUser({
              ...initialUser,
              ...result.data.profile,
              uid: initialUser.uid,
            });
            localStorage.setItem('currentUser', JSON.stringify(refreshedUser));
            setUser(refreshedUser);
          }
        } catch (profileError) {
          console.warn('초기 프로필 조회 실패 (캐시 사용):', profileError?.message || profileError);
        }
      } else {
        setUser(null);
      }

      setLoading(false);
    }, (authError) => {
      console.error('useAuth 초기화 오류:', authError);
      setError(authError.message);
      setUser(null);
      setLoading(false);
    });

    const handleStorageChange = (e) => {
      if (e.key === 'currentUser') {
        const naverUser = checkNaverUser();
        if (naverUser) {
          setUser(naverUser);
        }
      }
    };

    const handleNaverAuthUpdate = (e) => {
      setUser(normalizeAuthUser(e.detail));
    };

    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('userProfileUpdated', handleNaverAuthUpdate);

    return () => {
      unsubscribeAuth();
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('userProfileUpdated', handleNaverAuthUpdate);
    };
  }, []);

  const logout = async () => {
    try {
      await signOut(auth);
      localStorage.removeItem('currentUser');
      setUser(null);
    } catch (e) {
      console.error('로그아웃 오류:', e);
    }
  };

  const refreshUserProfile = async () => {
    try {
      const currentUser = checkNaverUser();
      if (!currentUser?.uid) {
        console.warn('refreshUserProfile: 사용자 정보 없음');
        return;
      }

      const getUserProfile = httpsCallable(functions, 'getUserProfile');
      const result = await getUserProfile({
        __naverAuth: {
          uid: currentUser.uid,
          provider: 'naver',
        },
      });

      if (!result.data?.profile) {
        console.warn('refreshUserProfile: 프로필 데이터 없음');
        return;
      }

      const updatedUser = normalizeAuthUser({
        ...currentUser,
        ...result.data.profile,
        uid: currentUser.uid,
      });

      localStorage.setItem('currentUser', JSON.stringify(updatedUser));
      setUser(updatedUser);
    } catch (authError) {
      console.error('refreshUserProfile 오류:', authError);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, error, logout, refreshUserProfile }}>
      {children}
    </AuthContext.Provider>
  );
};
