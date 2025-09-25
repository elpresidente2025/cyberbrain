import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth'; // useAuth 훅의 실제 경로로 수정하세요
import { Box, CircularProgress } from '@mui/material';

const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth(); // 'user'와 'loading'을 직접 사용
  const location = useLocation();

  console.log('🔒 ProtectedRoute 상태:', { user: !!user, loading, path: location.pathname });

  // 인증 상태를 확인하는 동안 로딩 화면을 보여줌
  if (loading) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  // 로딩이 끝난 후, 사용자 정보가 없으면 로그인 페이지로 리디렉션
  if (!user || !user.uid) {
    console.log('🚫 인증되지 않은 접근, 로그인 페이지로 리다이렉트');
    // 혹시 남은 스토리지도 정리
    try {
      localStorage.removeItem('firebase:authUser:' + process.env.VITE_FIREBASE_API_KEY);
      sessionStorage.clear();
    } catch (e) {
      console.warn('스토리지 정리 실패:', e);
    }
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // 사용자 정보가 있으면 요청된 페이지(children)를 보여줌
  return children;
};

export default ProtectedRoute;