import React, { useState, useEffect, createContext, useContext } from 'react';
import {
  getAuth,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  updateProfile,
  signOut,
  GoogleAuthProvider,
  signInWithPopup,
  signInWithRedirect,
  getRedirectResult,
  linkWithPopup,
  linkWithCredential,
  EmailAuthProvider,
  unlink,
} from 'firebase/auth';
import { 
  getFirestore, 
  doc, 
  getDoc 
} from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { app, functions } from '../services/firebase';

// AuthContext 생성
const AuthContext = createContext();

// 다른 컴포넌트에서 쉽게 사용할 수 있도록 export
export const useAuth = () => {
  const context = useContext(AuthContext);
  
  // ✅ 젠스파크 수정: useAuth 훅에 컨텍스트 검증 추가
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  
  return context;
};

// AuthProvider 컴포넌트
export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true); // 초기값 true로 시작
  const [error, setError] = useState(null);
  const auth = getAuth(app);
  const db = getFirestore(app);
  
  // 강제 타임아웃으로 무한 로딩 방지
  React.useEffect(() => {
    const timeout = setTimeout(() => {
      if (loading) {
        console.warn('⚠️ Auth 로딩 타임아웃 - 강제 완료');
        setLoading(false);
      }
    }, 5000); // 5초 타임아웃
    
    return () => clearTimeout(timeout);
  }, [loading]);

  // 🔥 Firestore에서 사용자 프로필 정보 가져오기
  const fetchUserProfile = async (uid) => {
    try {
      console.log('🔍 Firestore에서 사용자 프로필 조회 중...', uid);
      const userDocRef = doc(db, 'users', uid);
      const userDocSnap = await getDoc(userDocRef);
      
      if (userDocSnap.exists()) {
        const userData = userDocSnap.data();
        console.log('✅ Firestore 사용자 데이터:', userData);
        return userData;
      } else {
        console.log('⚠️ Firestore에서 사용자 문서를 찾을 수 없음:', uid);
        return null;
      }
    } catch (error) {
      console.error('❌ Firestore 사용자 조회 실패:', error);
      return null;
    }
  };

  useEffect(() => {
    // onAuthStateChanged는 구독을 해제하는 함수를 반환합니다.
    const unsubscribe = onAuthStateChanged(auth, async (currentUser) => {
      console.log('🔥 Auth 상태 변경:', currentUser?.uid);
      
      try {
        if (currentUser) {
          // 임시로 Firestore 연결 없이 Firebase Auth만 사용
          console.log('⚡ 빠른 로딩을 위해 Firestore 스킵');
          
          const combinedUser = {
            // Firebase Auth 기본 정보만
            uid: currentUser.uid,
            email: currentUser.email,
            displayName: currentUser.displayName,
            emailVerified: currentUser.emailVerified,
            
            // 기본값들
            isActive: true,
            role: null,
            isAdmin: false,
            
            // 원본 Firebase User 객체도 보관 (필요시)
            _firebaseUser: currentUser
          };
          
          console.log('👤 기본 사용자 정보:', combinedUser);
          setUser(combinedUser);
          
          // Firestore 프로필 정보를 비동기로 나중에 로드
          setTimeout(async () => {
            try {
              console.log('🔍 Firestore 프로필 백그라운드 로드 중...');
              const userProfile = await fetchUserProfile(currentUser.uid);
              if (userProfile) {
                setUser(prev => ({
                  ...prev,
                  ...userProfile
                }));
                console.log('✅ Firestore 프로필 로드 완료');
              }
            } catch (error) {
              console.warn('⚠️ Firestore 프로필 로드 실패:', error);
            }
          }, 100);
          
        } else {
          console.log('🚫 로그아웃됨');
          setUser(null);
        }
      } catch (error) {
        console.error('❌ Auth 상태 처리 중 오류:', error);
        setUser(null);
      } finally {
        // 성공하든 실패하든 로딩은 완료
        setLoading(false);
      }
    });

    // 컴포넌트가 언마운트될 때 구독을 해제하여 메모리 누수를 방지합니다.
    return unsubscribe;
  }, [auth, db]);

  const login = async (email, password) => {
    setError(null); // 이전 오류 초기화
    try {
      console.log('🔐 로그인 시도:', email);
      
      // 네트워크 오류 재시도 로직 (최대 3회)
      let lastError = null;
      let userCredential = null;
      
      for (let attempt = 1; attempt <= 3; attempt++) {
        try {
          console.log(`🔄 로그인 시도 ${attempt}/3`);
          userCredential = await signInWithEmailAndPassword(auth, email, password);
          console.log(`✅ 로그인 성공 (${attempt}번째 시도)`);
          break; // 성공하면 루프 종료
        } catch (err) {
          lastError = err;
          console.warn(`❌ 로그인 시도 ${attempt} 실패:`, err.code);
          
          // 네트워크 오류가 아니면 즉시 중단
          if (err.code !== 'auth/network-request-failed') {
            throw err;
          }
          
          // 마지막 시도가 아니면 1초 대기 후 재시도
          if (attempt < 3) {
            console.log('⏳ 1초 후 재시도...');
            await new Promise(resolve => setTimeout(resolve, 1000));
          }
        }
      }
      
      // 모든 시도가 실패한 경우
      if (!userCredential) {
        throw lastError || new Error('로그인 재시도 실패');
      }
      
      // 로그인 성공 후 Firestore에서 프로필 정보 가져오기
      const userProfile = await fetchUserProfile(userCredential.user.uid);
      
      const combinedUser = {
        // Firebase Auth 기본 정보
        uid: userCredential.user.uid,
        email: userCredential.user.email,
        displayName: userCredential.user.displayName,
        emailVerified: userCredential.user.emailVerified,
        
        // Firestore 프로필 정보 (있다면)
        ...userProfile,
        
        // 원본 Firebase User 객체도 보관 (필요시)
        _firebaseUser: userCredential.user
      };
      
      setUser(combinedUser);
      console.log('✅ 로그인 성공:', combinedUser);
      return combinedUser;
    } catch (err) {
      // Firebase에서 발생한 오류를 잡아냅니다.
      console.error('❌ 로그인 실패:', err);
      // 오류 메시지를 상태에 저장하고,
      setError(err.message);
      // 🔥 가장 중요한 부분: 잡은 오류를 다시 던져서 HomePage가 알 수 있도록 합니다.
      throw err;
    }
  };

  // Google 로그인 함수 추가
  const signInWithGoogle = async () => {
    setError(null);
    try {
      console.log('🔐 Google 로그인 시도');
      const provider = new GoogleAuthProvider();
      
      // 추가 스코프 요청 (이메일, 프로필)
      provider.addScope('email');
      provider.addScope('profile');
      
      // CORS 정책 문제로 인해 모든 환경에서 리다이렉트 방식 사용
      console.log('🔄 리다이렉트 방식으로 Google 로그인 진행');
      await signInWithRedirect(auth, provider);
      return; // 리다이렉트 후 결과는 페이지 로드 시 처리됨
      
      if (result) {
        const user = result.user;
        console.log('✅ Google 로그인 성공:', user.email);
        
        // Firestore에서 기존 프로필 정보 가져오기
        const userProfile = await fetchUserProfile(user.uid);
        
        const combinedUser = {
          uid: user.uid,
          email: user.email,
          displayName: user.displayName,
          photoURL: user.photoURL,
          emailVerified: user.emailVerified,
          
          // Google 로그인 특별 정보
          isGoogleUser: true,
          
          // Firestore 프로필 정보
          ...userProfile,
          
          // 원본 Firebase User 객체
          _firebaseUser: user
        };
        
        setUser(combinedUser);
        
        // 신규 Google 사용자면 프로필 설정 페이지로 안내
        if (!userProfile || !userProfile.isActive) {
          console.log('🆕 신규 Google 사용자 - 프로필 설정 필요');
        }
        
        return combinedUser;
      }
    } catch (err) {
      console.error('❌ Google 로그인 실패:', err);
      
      let errorMessage = 'Google 로그인에 실패했습니다.';
      
      switch (err.code) {
        case 'auth/popup-closed-by-user':
          errorMessage = 'Google 로그인 창이 닫혔습니다.';
          break;
        case 'auth/popup-blocked':
          errorMessage = '팝업이 차단되었습니다. 팝업 차단을 해제해주세요.';
          break;
        case 'auth/cancelled-popup-request':
          errorMessage = 'Google 로그인이 취소되었습니다.';
          break;
        case 'auth/network-request-failed':
          errorMessage = '네트워크 오류입니다. 다시 시도해주세요.';
          break;
        default:
          errorMessage = `Google 로그인 실패: ${err.message}`;
      }
      
      setError(errorMessage);
      throw err;
    }
  };

  // 리다이렉트 결과 처리 (모든 Google 로그인용)
  useEffect(() => {
    const handleRedirectResult = async () => {
      try {
        const result = await getRedirectResult(auth);
        if (result) {
          const user = result.user;
          console.log('✅ Google 리다이렉트 로그인 성공:', user.email);
          
          // Firestore에서 기존 프로필 정보 가져오기
          const userProfile = await fetchUserProfile(user.uid);
          
          const combinedUser = {
            uid: user.uid,
            email: user.email,
            displayName: user.displayName,
            photoURL: user.photoURL,
            emailVerified: user.emailVerified,
            
            // Google 로그인 특별 정보
            isGoogleUser: true,
            
            // Firestore 프로필 정보
            ...userProfile,
            
            // 원본 Firebase User 객체
            _firebaseUser: user
          };
          
          setUser(combinedUser);
          
          // 신규 Google 사용자면 프로필 설정 페이지로 안내
          if (!userProfile || !userProfile.isActive) {
            console.log('🆕 신규 Google 사용자 - 프로필 설정 필요');
            // 프로필 설정 페이지로 리다이렉트할 수도 있음
          }
        }
      } catch (error) {
        console.error('❌ Google 리다이렉트 처리 실패:', error);
        setError(error.message || 'Google 로그인 처리 중 오류가 발생했습니다.');
      }
    };
    
    handleRedirectResult();
  }, []);

  const logout = async () => {
    setError(null);
    try {
      console.log('🚪 로그아웃 시도');
      
      // Firebase Auth 로그아웃
      await signOut(auth);
      
      // 상태 초기화
      setUser(null);
      setLoading(false);
      
      // 브라우저 스토리지 완전 정리
      try {
        localStorage.clear();
        sessionStorage.clear();
        
        // IndexedDB 정리 (Firebase용)
        if ('indexedDB' in window) {
          const deleteDB = (dbName) => {
            const deleteReq = indexedDB.deleteDatabase(dbName);
            deleteReq.onerror = () => console.log('IndexedDB 삭제 실패:', dbName);
            deleteReq.onsuccess = () => console.log('IndexedDB 삭제 성공:', dbName);
          };
          deleteDB('firebaseLocalStorageDb');
          deleteDB('firebase-heartbeat-database');
          deleteDB('firebase-installations-database');
        }
        
        console.log('🧹 브라우저 스토리지 정리 완료');
      } catch (storageError) {
        console.warn('⚠️ 스토리지 정리 중 일부 오류:', storageError);
      }
      
      console.log('✅ 완전한 로그아웃 성공');
      
      // 강제 페이지 새로고침으로 모든 상태 초기화
      setTimeout(() => {
        window.location.href = '/login';
      }, 100);
      
    } catch (err) {
      console.error('❌ 로그아웃 실패:', err);
      setError(err.message);
      throw err;
    }
  };

  const register = async ({ email, password, displayName, profileData }) => {
    setError(null);
    try {
      console.log('📝 회원가입 시도:', email, displayName);
      
      // 1. Firebase Auth에 사용자 생성
      const userCredential = await createUserWithEmailAndPassword(auth, email, password);
      const user = userCredential.user;
      
      // 2. 사용자 프로필 업데이트 (displayName 설정)
      await updateProfile(user, {
        displayName: displayName
      });
      
      // 3. Firebase Functions를 통해 프로필 데이터 저장 및 선거구 체크
      const registerWithDistrictCheck = httpsCallable(functions, 'registerWithDistrictCheck');
      await registerWithDistrictCheck({ profileData });
      
      console.log('✅ 회원가입 성공:', user.uid);
      
      // 4. 새로운 사용자 정보로 상태 업데이트
      const combinedUser = {
        uid: user.uid,
        email: user.email,
        displayName: displayName,
        emailVerified: user.emailVerified,
        ...profileData,
        _firebaseUser: user
      };
      
      setUser(combinedUser);
      return combinedUser;
      
    } catch (err) {
      console.error('❌ 회원가입 실패:', err);
      setError(err.message);
      throw err;
    }
  };

  // 🔥 사용자 프로필 새로고침 함수 (필요시 호출)
  const refreshUserProfile = async () => {
    if (user?.uid) {
      console.log('🔄 사용자 프로필 새로고침');
      const userProfile = await fetchUserProfile(user.uid);
      if (userProfile) {
        setUser(prev => ({ ...prev, ...userProfile }));
      }
    }
  };

  // 🔗 Google 계정 연결 함수
  const linkGoogleAccount = async () => {
    setError(null);
    try {
      console.log('🔗 Google 계정 연결 시도');
      
      if (!user) {
        throw new Error('로그인이 필요합니다.');
      }

      const provider = new GoogleAuthProvider();
      provider.addScope('email');
      provider.addScope('profile');

      const result = await linkWithPopup(auth.currentUser, provider);
      console.log('✅ Google 계정 연결 성공:', result.user.email);
      
      // 사용자 정보 업데이트
      const updatedUser = {
        ...user,
        photoURL: result.user.photoURL,
        linkedAccounts: [...(user.linkedAccounts || []), 'google.com'],
        _firebaseUser: result.user
      };
      
      setUser(updatedUser);
      return updatedUser;
      
    } catch (err) {
      console.error('❌ Google 계정 연결 실패:', err);
      
      let errorMessage = 'Google 계정 연결에 실패했습니다.';
      
      switch (err.code) {
        case 'auth/provider-already-linked':
          errorMessage = '이미 Google 계정이 연결되어 있습니다.';
          break;
        case 'auth/credential-already-in-use':
          errorMessage = '이 Google 계정은 다른 사용자가 사용중입니다.';
          break;
        case 'auth/popup-blocked':
          errorMessage = '팝업이 차단되었습니다. 팝업 차단을 해제해주세요.';
          break;
        case 'auth/popup-closed-by-user':
          errorMessage = '연결이 취소되었습니다.';
          break;
        default:
          errorMessage = `Google 계정 연결 실패: ${err.message}`;
      }
      
      setError(errorMessage);
      throw err;
    }
  };

  // 🔗 이메일/비밀번호 계정 연결 함수
  const linkEmailAccount = async (email, password) => {
    setError(null);
    try {
      console.log('🔗 이메일 계정 연결 시도:', email);
      
      if (!user) {
        throw new Error('로그인이 필요합니다.');
      }

      const credential = EmailAuthProvider.credential(email, password);
      const result = await linkWithCredential(auth.currentUser, credential);
      console.log('✅ 이메일 계정 연결 성공:', result.user.email);
      
      // 사용자 정보 업데이트
      const updatedUser = {
        ...user,
        email: result.user.email,
        linkedAccounts: [...(user.linkedAccounts || []), 'password'],
        _firebaseUser: result.user
      };
      
      setUser(updatedUser);
      return updatedUser;
      
    } catch (err) {
      console.error('❌ 이메일 계정 연결 실패:', err);
      
      let errorMessage = '이메일 계정 연결에 실패했습니다.';
      
      switch (err.code) {
        case 'auth/provider-already-linked':
          errorMessage = '이미 이메일 계정이 연결되어 있습니다.';
          break;
        case 'auth/credential-already-in-use':
          errorMessage = '이 이메일은 다른 사용자가 사용중입니다.';
          break;
        case 'auth/invalid-email':
          errorMessage = '유효하지 않은 이메일 주소입니다.';
          break;
        case 'auth/weak-password':
          errorMessage = '비밀번호가 너무 약합니다.';
          break;
        default:
          errorMessage = `이메일 계정 연결 실패: ${err.message}`;
      }
      
      setError(errorMessage);
      throw err;
    }
  };

  // 🔓 계정 연결 해제 함수
  const unlinkAccount = async (providerId) => {
    setError(null);
    try {
      console.log('🔓 계정 연결 해제 시도:', providerId);
      
      if (!user) {
        throw new Error('로그인이 필요합니다.');
      }

      const result = await unlink(auth.currentUser, providerId);
      console.log('✅ 계정 연결 해제 성공:', providerId);
      
      // 사용자 정보 업데이트
      const updatedUser = {
        ...user,
        linkedAccounts: (user.linkedAccounts || []).filter(id => id !== providerId),
        _firebaseUser: result
      };
      
      setUser(updatedUser);
      return updatedUser;
      
    } catch (err) {
      console.error('❌ 계정 연결 해제 실패:', err);
      
      let errorMessage = '계정 연결 해제에 실패했습니다.';
      
      switch (err.code) {
        case 'auth/no-such-provider':
          errorMessage = '연결된 계정이 없습니다.';
          break;
        default:
          errorMessage = `계정 연결 해제 실패: ${err.message}`;
      }
      
      setError(errorMessage);
      throw err;
    }
  };

  // 컨텍스트로 제공할 값들
  const value = {
    user,
    loading,
    error,
    login,
    signInWithGoogle, // 🔥 Google 로그인 함수 추가
    register,
    logout,
    refreshUserProfile, // 🔥 프로필 새로고침 함수 추가
    // 🔗 계정 연결 함수들 추가
    linkGoogleAccount,
    linkEmailAccount,
    unlinkAccount,
    // 편의를 위한 바로 접근 가능한 값들
    auth: {
      user: user,
      isAuthenticated: !!user,
      isAdmin: user?.isAdmin || false,
      role: user?.role || null
    }
  };

  return (
    <AuthContext.Provider value={value}>
      {/* ✅ 젠스파크 수정: 항상 children을 렌더링하도록 수정 */}
      {children}
    </AuthContext.Provider>
  );
};