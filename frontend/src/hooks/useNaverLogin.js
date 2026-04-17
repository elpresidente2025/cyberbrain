import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { signInWithCustomToken } from 'firebase/auth';
import { auth } from '../services/firebase';
import { callFunctionWithNaverAuth } from '../services/firebaseService';
import { normalizeAuthUser } from '../utils/authz';
import { APP_ORIGIN, buildFunctionsUrl } from '../config/branding';

const DEFAULT_NAVER_CLIENT_ID = '_E0OZLvkgp61fV7MFtND';

export const useNaverLogin = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const hasHandledCallbackRef = useRef(false);
  const navigate = useNavigate();

  const initializeNaverLogin = () => {
    if (typeof window !== 'undefined' && window.naver) {
      const isLocalDevelopment = ['localhost', '127.0.0.1'].includes(window.location.hostname);
      const clientId = String(import.meta.env.VITE_NAVER_CLIENT_ID || DEFAULT_NAVER_CLIENT_ID).trim();
      const callbackBaseUrl = isLocalDevelopment ? window.location.origin : APP_ORIGIN;
      const callbackUrl = import.meta.env.VITE_NAVER_REDIRECT_URI || `${callbackBaseUrl}/auth/naver/callback`;
      if (!clientId) {
        console.error('VITE_NAVER_CLIENT_ID is missing. Please set it in frontend/.env');
        return null;
      }
      if (import.meta.env.DEV && !import.meta.env.VITE_NAVER_CLIENT_ID) {
        console.warn('VITE_NAVER_CLIENT_ID가 없어 기본 네이버 클라이언트 ID를 사용합니다.');
      }
      const naverLogin = new window.naver.LoginWithNaverId({
        clientId,
        callbackUrl,
        isPopup: false,
        callbackHandle: true,
        scope: 'name,email,gender,age,profile_image'
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
      throw e;
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

      const resp = await fetch(buildFunctionsUrl('naverLoginHTTP'), {
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

      // ✅ 보안 강화: customToken이 없으면 에러
      if (!customToken) {
        throw new Error('인증 토큰을 받지 못했습니다. 다시 시도해주세요.');
      }

      // ✅ Firebase Custom Token으로 인증
      console.log('🔐 Firebase Custom Token으로 인증 중...');
      const userCredential = await signInWithCustomToken(auth, customToken);
      console.log('✅ Firebase 인증 완료:', userCredential.user.uid);

      // customToken은 한 번만 사용 가능하므로 저장하지 않음
      // Firebase Auth가 자동으로 세션을 관리합니다

      if (registrationRequired) {
        // 미가입 회원 - 회원가입 페이지로 이동 (네이버 데이터와 함께)
        console.log('🟡 신규 사용자 - 회원가입 페이지로 이동');
        navigate('/register', {
          state: {
            naverUserData: naver,
            showNaverConsent: true
          }
        });
      } else {
        // 기존 회원 - Firebase Auth 완료 후 대시보드로 이동
        console.log('🟢 기존 사용자 - 대시보드로 이동. user 데이터:', user);
        console.log('🟢 네이버 API 데이터:', naver);

        const baseUserData = {
          uid: user.uid,
          naverUserId: user.naverUserId,
          displayName: user.displayName,
          email: user.email || naver?.email, // 이메일 포함
          photoURL: user.photoURL,
          provider: user.provider,
          profileComplete: user.profileComplete,
          role: user.role,
          bio: user.bio || '' // naverLoginHTTP에서 반환한 bio 포함
        };

        // 네비게이트 전에 프로필을 병합해 둔다 — 이게 없으면 Dashboard → OnboardingGuard 가
        // status/position/region 이 빠진 user 로 isOnboardingComplete 를 판정해 /onboarding 으로 튕기고,
        // OnboardingPage 의 stayOnOnboardingRef 가 잠기면서 로그인마다 온보딩에 갇힌다.
        let fullUserData = normalizeAuthUser(baseUserData);
        try {
          const profileResponse = await Promise.race([
            callFunctionWithNaverAuth('getUserProfile'),
            new Promise((_, reject) => setTimeout(() => reject(new Error('functions call timeout')), 10000))
          ]);
          const profile = profileResponse?.profile || profileResponse?.data?.profile;
          if (profile) {
            fullUserData = normalizeAuthUser({ ...baseUserData, ...profile });
            console.log('✅ 네이버 사용자 프로필 병합 완료:', fullUserData);
          }
        } catch (profileError) {
          console.warn('프로필 정보 조회 실패 — base 데이터로 계속:', profileError.message);
        }

        localStorage.setItem('currentUser', JSON.stringify(fullUserData));
        window.dispatchEvent(new CustomEvent('userProfileUpdated', {
          detail: fullUserData
        }));

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

