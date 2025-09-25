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
      if (!naverLogin) throw new Error('?ㅼ씠踰?SDK瑜?遺덈윭?ㅼ? 紐삵뻽?듬땲??');
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
      if (!payload) throw new Error('?ㅼ씠踰?肄쒕갚 ?뚮씪誘명꽣媛 ?놁뒿?덈떎. ?ㅼ떆 ?쒕룄??二쇱꽭??');

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
        // 誘멸????뚯썝 - ?뚯썝媛???섏씠吏濡??대룞 (?ㅼ씠踰??곗씠?곗? ?④퍡)
        // localStorage瑜??ㅼ젙?섏? ?딆븘??useAuth?먯꽌 ?꾨줈??議고쉶瑜??쒕룄?섏? ?딆쓬
        console.log('誘멸????뚯썝 - ?뚯썝媛???섏씠吏濡??대룞:', naver);
        console.log('🟡 신규 사용자 - 회원가입 페이지로 이동');
        navigate('/register', {
          state: {
            naverUserData: naver,
            showNaverConsent: true
          }
        });
      } else {
        // 湲곗〈 ?뚯썝 - localStorage????ν븯怨???쒕낫?쒕줈 ?대룞
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
        
        // 諛깃렇?쇱슫?쒖뿉???꾨줈???뺣낫 議고쉶 (硫붿씤 ?ㅻ젅??李⑤떒 諛⑹?)
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
              console.log('???ㅼ씠踰??ъ슜???꾨줈???뺣낫 ?낅뜲?댄듃 ?꾨즺:', updatedUserData);
              
              // CustomEvent로 프로필 업데이트 알림
              window.dispatchEvent(new CustomEvent('userProfileUpdated', {
                detail: updatedUserData
              }));
            }
          } catch (profileError) {
            console.warn('?꾨줈???뺣낫 議고쉶 ?ㅽ뙣 (臾댁떆):', profileError.message);
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

