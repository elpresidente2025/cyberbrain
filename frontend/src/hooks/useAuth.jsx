import React, { useState, useEffect, createContext, useContext } from 'react';

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

  // 네이버 사용자 정보 확인
  const checkNaverUser = () => {
    try {
      const storedUser = localStorage.getItem('currentUser');
      if (storedUser) {
        const userData = JSON.parse(storedUser);
        if (userData.uid && userData.provider === 'naver') {
          return userData;
        }
      }
    } catch (e) {
      console.warn('localStorage 사용자 정보 읽기 실패:', e);
    }
    return null;
  };

  useEffect(() => {
    // 네이버 로그인 전용 - localStorage 기반 인증 확인
    const checkAuth = () => {
      try {
        const naverUser = checkNaverUser();
        if (naverUser) {
          console.log('🔍 useAuth: 네이버 사용자 인증됨:', naverUser);
          setUser(naverUser);
        } else {
          console.log('🔍 useAuth: 네이버 사용자 없음');
          setUser(null);
        }
      } catch (e) {
        console.error('🔍 useAuth 에러:', e);
        setError(e.message);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };

    // 초기 인증 확인
    checkAuth();

    // localStorage 변경 감지
    const handleStorageChange = (e) => {
      if (e.key === 'currentUser') {
        console.log('🔍 useAuth: localStorage 변경 감지');
        checkAuth();
      }
    };

    // 커스텀 이벤트 리스너 (네이버 로그인 콜백에서 발생)
    const handleNaverAuthUpdate = (e) => {
      console.log('🔍 useAuth: 네이버 인증 업데이트 이벤트:', e.detail);
      checkAuth();
    };

    window.addEventListener('storage', handleStorageChange);
    window.addEventListener('userProfileUpdated', handleNaverAuthUpdate);

    return () => {
      window.removeEventListener('storage', handleStorageChange);
      window.removeEventListener('userProfileUpdated', handleNaverAuthUpdate);
    };
  }, []);

  const logout = async () => {
    // 네이버 로그인은 localStorage만 정리
    localStorage.removeItem('currentUser');
    setUser(null);
    console.log('🔍 useAuth: 네이버 로그아웃 완료');
  };

  return (
    <AuthContext.Provider value={{ user, loading, error, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

