import React, { useState, useEffect } from 'react';
import { useNavigate, Link as RouterLink } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import {
  Container,
  Box,
  TextField,
  Typography,
  Alert,
  Grid,
  Link as MuiLink,
} from '@mui/material';
import { LoadingButton, LoadingSpinner } from '../components/loading';

const HomePage = () => {
  // ✅ 젠스파크 수정: 올바른 구조로 수정
  const { user, loading: authLoading, login } = useAuth();

  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    // 인증 로딩이 끝나고 사용자 정보가 있으면 대시보드로 이동
    if (!authLoading && user) {
      navigate('/dashboard', { replace: true });
    }
  }, [user, authLoading, navigate]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!email || !password) {
      setError('이메일과 비밀번호를 모두 입력해주세요.');
      return;
    }
    
    setError('');
    setIsSubmitting(true);

    try {
      // ✅ 젠스파크 수정: try-catch 블록으로 에러 처리 개선
      await login(email, password);
      // 성공 시에는 useEffect가 알아서 대시보드로 이동시킵니다.
    } catch (err) {
      // ✅ 젠스파크 수정: Firebase 에러 코드에 따른 사용자 친화적인 메시지 표시
      const getErrorMessage = (errorCode) => {
        switch (errorCode) {
          case 'auth/user-not-found':
            return '등록되지 않은 이메일입니다.';
          case 'auth/wrong-password':
            return '비밀번호가 잘못되었습니다.';
          case 'auth/invalid-email':
            return '올바른 이메일 형식이 아닙니다.';
          case 'auth/user-disabled':
            return '비활성화된 계정입니다.';
          case 'auth/too-many-requests':
            return '너무 많은 로그인 시도가 있었습니다. 잠시 후 다시 시도해주세요.';
          case 'auth/invalid-credential':
            return '이메일 또는 비밀번호가 잘못되었습니다.';
          default:
            return '로그인 중 오류가 발생했습니다.';
        }
      };
      
      setError(getErrorMessage(err.code));
    } finally {
      setIsSubmitting(false);
    }
  };

  // 초기 인증 확인 중일 때 로딩 화면 표시
  if (authLoading) {
    return (
      <Box sx={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}>
        <LoadingSpinner message="시스템 초기화 중..." fullHeight />
      </Box>
    );
  }

  return (
    <Box sx={{ 
      minHeight: '100vh', 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center' 
    }}>
      <Container component="main" maxWidth="xs">
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <Box
            component="img"
            src="/logo.png"
            alt="전자두뇌비서관 로고"
            sx={{ 
              width: '80%', 
              mb: 3,
              objectFit: 'contain'
            }}
          />
          <Typography component="h1" variant="h5" sx={{ mb: 3 }}>
            전자두뇌비서관 로그인
          </Typography>
        <Box component="form" onSubmit={handleSubmit} noValidate sx={{ mt: 1 }}>
          <TextField
            margin="normal"
            required
            fullWidth
            id="email"
            label="이메일 주소"
            name="email"
            autoComplete="email"
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={isSubmitting}
          />
          <TextField
            margin="normal"
            required
            fullWidth
            name="password"
            label="비밀번호"
            type="password"
            id="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={isSubmitting}
          />
          {error && (
            <Alert severity="error" sx={{ width: '100%', mt: 2 }}>
              {error}
            </Alert>
          )}
          <LoadingButton
            type="submit"
            fullWidth
            variant="contained"
            loading={isSubmitting}
            loadingText="로그인 중..."
            sx={{ 
              mt: 3, 
              mb: 2,
              bgcolor: '#152484',
              '&:hover': {
                bgcolor: '#003A87'
              }
            }}
          >
            로그인
          </LoadingButton>
          <Grid container justifyContent="flex-end">
            <Grid item>
              <MuiLink component={RouterLink} to="/register" variant="body2">
                계정이 없으신가요? 회원가입
              </MuiLink>
            </Grid>
          </Grid>
        </Box>
        </Box>
      </Container>
    </Box>
  );
};

export default HomePage;