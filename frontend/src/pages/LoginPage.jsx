import React, { useState, useEffect } from 'react';
import { useNavigate, Link as RouterLink, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useNaverLogin } from '../hooks/useNaverLogin';
import { useThemeMode } from '../contexts/ThemeContext';
import {
  Container,
  Typography,
  Button,
  Box,
  Paper,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Link,
  useTheme,
} from '@mui/material';
import { LoadingButton } from '../components/loading';

function LoginPage() {
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [naverDialogOpen, setNaverDialogOpen] = useState(false);
  const [naverUserData, setNaverUserData] = useState(null);

  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const { loginWithNaver } = useNaverLogin();
  const { isDarkMode } = useThemeMode();
  const theme = useTheme();

  useEffect(() => {
    if (user) {
      const redirectTo = location.state?.from?.pathname || '/dashboard';
      navigate(redirectTo, { replace: true });
    }
  }, [user, navigate, location.state]);

  useEffect(() => {
    document.title = '전자두뇌비서관 - 로그인';
  }, []);

  // 회원가입 완료 메시지 표시
  useEffect(() => {
    if (location.state?.message) {
      setError(''); // 기존 에러 클리어
      // 성공 메시지라면 성공 스타일로 표시 (간단한 방법)
      console.log('회원가입 완료 메시지:', location.state.message);
    }
  }, [location.state]);


  const handleNaverLogin = async () => {
    setError('');
    setLoading(true);

    try {
      await loginWithNaver();
    } catch (error) {
      console.error('네이버 로그인 오류:', error);
      
      // 가입 정보가 없는 경우 팝업 띄우기
      if (error.code === 'auth/user-not-found' && error.isNaverUser) {
        setNaverUserData(error.naverUserData);
        setNaverDialogOpen(true);
      } else {
        let errorMessage = '네이버 로그인에 실패했습니다.';
        
        switch (error.code) {
          case 'auth/network-request-failed':
            errorMessage = '네트워크 오류입니다. 다시 시도해주세요.';
            break;
          case 'auth/cancelled-popup-request':
            errorMessage = '네이버 로그인이 취소되었습니다.';
            break;
          case 'auth/popup-blocked':
            errorMessage = '팝업이 차단되었습니다. 팝업 차단을 해제해주세요.';
            break;
          default:
            errorMessage = error.message || '네이버 로그인에 실패했습니다.';
        }
        
        setError(errorMessage);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleNaverDialogClose = () => {
    setNaverDialogOpen(false);
  };

  const handleGoToRegister = () => {
    setNaverDialogOpen(false);
    // 회원가입 페이지로 이동
    navigate('/register');
  };


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
          src="/logo-portrait.png"
          alt="전자두뇌비서관 로고"
          sx={{ 
            width: '80%', 
            mb: 3,
            objectFit: 'contain'
          }}
        />
        <Typography component="h1" variant="h5" sx={{ color: theme.palette.mode === 'dark' ? '#ffffff' : '#000000' }}>
          전자두뇌비서관 로그인
        </Typography>

        <Paper elevation={2} sx={{ p: 4, mt: 3, width: '100%' }}>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          <Box sx={{ textAlign: 'center' }}>
            <Box sx={{ position: 'relative', display: 'inline-block', width: '75%', mb: 3 }}>
              <Box
                component="img"
                src={isDarkMode ? "/buttons/login_dark.png" : "/buttons/login_light.png"}
                alt="네이버로 로그인"
                onClick={handleNaverLogin}
                sx={{
                  width: '100%',
                  maxWidth: '225px',
                  height: 'auto',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  opacity: loading ? 0.6 : 1,
                  transition: 'opacity 0.2s, transform 0.1s',
                  '&:hover': {
                    transform: loading ? 'none' : 'scale(1.02)',
                  },
                  '&:active': {
                    transform: loading ? 'none' : 'scale(0.98)',
                  },
                  pointerEvents: loading ? 'none' : 'auto'
                }}
              />
              {loading && (
                <Box
                  sx={{
                    position: 'absolute',
                    top: '50%',
                    left: '50%',
                    transform: 'translate(-50%, -50%)',
                    color: '#03C75A',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1
                  }}
                >
                  <Box
                    sx={{
                      width: 20,
                      height: 20,
                      border: '2px solid rgba(3, 199, 90, 0.3)',
                      borderTop: '2px solid #03C75A',
                      borderRadius: '50%',
                      animation: 'spin 1s linear infinite',
                      '@keyframes spin': {
                        '0%': { transform: 'rotate(0deg)' },
                        '100%': { transform: 'rotate(360deg)' }
                      }
                    }}
                  />
                  <Typography variant="body2" sx={{ color: '#03C75A', fontWeight: 600 }}>
                    로그인 중...
                  </Typography>
                </Box>
              )}
            </Box>
            
            <Box sx={{ textAlign: 'center' }}>
              <Link component={RouterLink} to="/register" variant="body2">
                회원가입하기
              </Link>
            </Box>
          </Box>
        </Paper>


        {/* 네이버 로그인 실패 다이얼로그 */}
        <Dialog open={naverDialogOpen} onClose={handleNaverDialogClose} maxWidth="sm" fullWidth slotProps={{ backdrop: { 'aria-hidden': false } }}>
          <DialogTitle>가입 정보 없음</DialogTitle>
          <DialogContent>
            <Alert severity="info" sx={{ mb: 2 }}>
              가입 정보가 없습니다. 회원가입 페이지로 이동합니다.
            </Alert>
            <Typography variant="body2" color="text.secondary">
              네이버 계정으로 로그인하려면 먼저 회원가입을 완료해야 합니다. 
              회원가입 페이지에서 네이버 계정을 연결하여 가입할 수 있습니다.
            </Typography>
          </DialogContent>
          <DialogActions>
            <Button onClick={handleNaverDialogClose} color="secondary">
              취소
            </Button>
            <Button
              onClick={handleGoToRegister}
              variant="contained"
              sx={{
                bgcolor: '#00d4ff',
                color: '#000',
                fontWeight: 600,
                '&:hover': {
                  bgcolor: '#00a8cc'
                }
              }}
            >
              회원가입 페이지로 이동
            </Button>
          </DialogActions>
        </Dialog>
        </Box>
      </Container>
    </Box>
  );
}

export default LoginPage;
