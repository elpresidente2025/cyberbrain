import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { callFunctionWithNaverAuth } from '../services/firebaseService';

export const useNaverLogin = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const hasHandledCallbackRef = useRef(false);
  const navigate = useNavigate();

  const initializeNaverLogin = () => {
    if (typeof window !== 'undefined' && window.naver) {
      const clientId = import.meta.env.VITE_NAVER_CLIENT_ID;
      const callbackUrl = import.meta.env.VITE_NAVER_REDIRECT_URI || (window.location.origin + "/auth/naver/callback");
      if (!clientId) {
        console.error('VITE_NAVER_CLIENT_ID is missing. Please set it in frontend/.env');
        return null;
      }
      const naverLogin = new window.naver.LoginWithNaverId({
        clientId,
        callbackUrl,
        isPopup: false,
        callbackHandle: true,
        scope: 'name,gender,age,profile_image'
      });
      return naverLogin;
    }
    return null;
  };

  const loginWithNaver = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const naverLogin = initializeNaverLogin();
      if (!naverLogin) throw new Error('네이버 SDK를 불러오지 못했습니다');
      naverLogin.authorize();
    } catch (e) {
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleNaverCallback = async () => {
    if (hasHandledCallbackRef.current) return;
    hasHandledCallbackRef.current = true;
    setIsLoading(true);
    setError(null);
    try {
      // Try implicit flow token from hash
      const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''));
      let accessToken = hash.get('access_token');
      let state = hash.get('state');
      let code = null;

      // Or authorization code from query
      if (!accessToken) {
        const qs = new URLSearchParams(window.location.search);
        accessToken = qs.get('access_token');
        code = qs.get('code');
        state = qs.get('state') || state;
      }

      // Call Cloud Function with either accessToken or code
      const payload = accessToken ? { accessToken } : code ? { code, state } : null;
      if (!payload) throw new Error('네이버 콜백 파라미터가 없습니다. 다시 시도해주세요.');

      console.log('🔵 네이버 콜백 디버그 - payload:', payload);

      const resp = await fetch('https://asia-northeast3-ai-secretary-6e9c8.cloudfunctions.net/naverLoginHTTP', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      console.log('🔵 네이버 로그인 HTTP 응답 상태:', resp.status);

      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();

      console.log('🔵 네이버 로그인 응답 데이터:', json);

      const result = json.result;
      if (!result?.success) throw new Error('네이버 로그인 처리 실패');

      const { registrationRequired, user, naver, customToken } = result;
      
      if (registrationRequired) {
        // 미가입 회원 - 회원가입 페이지로 이동 (네이버 데이터와 함께)
        // localStorage를 설정하지 않아서 useAuth에서 프로필 조회를 시도하지 않음
        console.log('미가입 회원 - 회원가입 페이지로 이동:', naver);
        console.log('🟡 신규 사용자 - 회원가입 페이지로 이동');
        navigate('/register', {
          state: {
            naverUserData: naver,
            showNaverConsent: true
          }
        });
      } else {
        // 기존 회원 - localStorage 설정하고 대시보드로 이동
        console.log('🟢 기존 사용자 - 대시보드로 이동. user 데이터:', user);
        const currentUserData = {
          uid: user.uid,
          naverUserId: user.naverUserId,
          displayName: user.displayName,
          photoURL: user.photoURL,
          provider: user.provider,
          profileComplete: user.profileComplete,
          isAdmin: user.isAdmin
        };
        
        localStorage.setItem('currentUser', JSON.stringify(currentUserData));

        // useAuth에 즉시 알림
        window.dispatchEvent(new CustomEvent('userProfileUpdated', {
          detail: currentUserData
        }));
        
        // 백그라운드에서 프로필 정보 조회 (메인 흐름과 차단 방지)
        setTimeout(async () => {
          try {
            // const { callFunctionWithNaverAuth } = await import('../services/firebaseService'); // 정적 import로 변경
            const profileResponse = await Promise.race([
              callFunctionWithNaverAuth('getUserProfile'),
              new Promise((_, reject) => setTimeout(() => reject(new Error('functions call timeout')), 3000))
            ]);
            if (profileResponse?.profile) {
              const updatedUserData = {
                ...currentUserData,
                ...profileResponse.profile
              };
              localStorage.setItem('currentUser', JSON.stringify(updatedUserData));
              console.log('✅ 네이버 사용자 프로필 정보 업데이트 완료:', updatedUserData);
              
              // CustomEvent로 프로필 업데이트 알림
              window.dispatchEvent(new CustomEvent('userProfileUpdated', {
                detail: updatedUserData
              }));
            }
          } catch (profileError) {
            console.warn('프로필 정보 조회 실패 (무시):', profileError.message);
          }
        }, 100);
        
        navigate('/dashboard', { replace: true });
      }
    } catch (e) {
      console.error('❌ 네이버 콜백 처리 에러:', e);
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  };

  return { loginWithNaver, handleNaverCallback, isLoading, error, initializeNaverLogin };
};

