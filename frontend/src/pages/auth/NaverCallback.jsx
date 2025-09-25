// frontend/src/pages/auth/NaverCallback.jsx
import React, { useEffect } from 'react';
import { Box, Typography, CircularProgress } from '@mui/material';
import { useNaverLogin } from '../../hooks/useNaverLogin';
import { LoadingOverlay } from '../../components/loading';

const NaverCallback = () => {
  const { handleNaverCallback, isLoading, error } = useNaverLogin();

  useEffect(() => {
    // 페이지 로드 시 네이버 콜백 처리
    handleNaverCallback();
  }, [handleNaverCallback]);

  if (error) {
    return (
      <Box
        sx={{
          height: '100vh',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          alignItems: 'center',
          padding: 3,
          textAlign: 'center'
        }}
      >
        <Typography variant="h5" color="error" gutterBottom>
          네이버 로그인 오류
        </Typography>
        <Typography variant="body1" color="text.secondary" sx={{ mb: 3 }}>
          {error}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          잠시 후 로그인 페이지로 이동합니다...
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ 
      height: '100vh',
      bgcolor: 'transparent',
      background: 'none'
    }}>
      <LoadingOverlay 
        open={true} 
        message={isLoading ? "네이버 로그인 처리 중..." : "로그인 완료!"} 
        backdrop={false}
      />
    </Box>
  );
};

export default NaverCallback;