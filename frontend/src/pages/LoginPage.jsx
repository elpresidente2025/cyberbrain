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
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Link,
} from '@mui/material';
import { motion } from 'framer-motion';

const springTransition = 'all 0.35s cubic-bezier(0.16, 1, 0.3, 1)';

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

  useEffect(() => {
    if (user) {
      const redirectTo = location.state?.from?.pathname || '/dashboard';
      navigate(redirectTo, { replace: true });
    }
  }, [user, navigate, location.state]);

  useEffect(() => {
    document.title = '전자두뇌비서관 - 로그인';
  }, []);

  useEffect(() => {
    if (location.state?.message) {
      setError('');
    }
  }, [location.state]);

  const handleNaverLogin = async () => {
    setError('');
    setLoading(true);

    try {
      await loginWithNaver();
    } catch (error) {
      console.error('네이버 로그인 오류:', error);

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
    navigate('/register');
  };

  return (
    <Box sx={{
      minHeight: '100dvh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      bgcolor: 'var(--color-background)',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* 배경 장식 */}
      <Box sx={{
        position: 'absolute',
        top: '-10%',
        right: '-15%',
        width: '50vw',
        height: '50vw',
        maxWidth: 600,
        maxHeight: 600,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(21,36,132,0.06) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />
      <Box sx={{
        position: 'absolute',
        bottom: '-10%',
        left: '-10%',
        width: '40vw',
        height: '40vw',
        maxWidth: 450,
        maxHeight: 450,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(21,36,132,0.04) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      <Container component="main" maxWidth="xs" sx={{ position: 'relative', zIndex: 1 }}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        >
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            {/* 로고 */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.4, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
            >
              <Box
                component="img"
                src="/logo-portrait.png"
                alt="전자두뇌비서관 로고"
                sx={{
                  width: '70%',
                  maxWidth: 280,
                  mb: 4,
                  mx: 'auto',
                  display: 'block',
                  objectFit: 'contain',
                }}
              />
            </motion.div>

            {/* 제목 */}
            <Typography
              component="h1"
              sx={{
                color: 'var(--color-text-primary)',
                fontWeight: 700,
                fontSize: { xs: '1.5rem', sm: '1.75rem' },
                letterSpacing: '-0.02em',
                mb: 1,
                wordBreak: 'keep-all',
              }}
            >
              로그인
            </Typography>
            <Typography sx={{
              color: 'var(--color-text-secondary)',
              fontSize: '0.95rem',
              mb: 4,
            }}>
              네이버 계정으로 시작하세요
            </Typography>

            {/* 카드 */}
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
              style={{ width: '100%' }}
            >
              <Box sx={{
                p: { xs: 3, sm: 4 },
                width: '100%',
                borderRadius: 'var(--radius-xl)',
                bgcolor: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                boxShadow: 'var(--shadow-lg)',
              }}>
                {error && (
                  <Alert severity="error" sx={{ mb: 3, borderRadius: 'var(--radius-md)' }}>
                    {error}
                  </Alert>
                )}

                {location.state?.message && (
                  <Alert severity="success" sx={{ mb: 3, borderRadius: 'var(--radius-md)' }}>
                    {location.state.message}
                  </Alert>
                )}

                <Box sx={{ textAlign: 'center' }}>
                  {/* 네이버 로그인 버튼 */}
                  <Box sx={{ position: 'relative', display: 'inline-block', width: '80%', mb: 3 }}>
                    <Box
                      component="img"
                      src={isDarkMode ? "/buttons/login_dark.png" : "/buttons/login_light.png"}
                      alt="네이버로 로그인"
                      onClick={handleNaverLogin}
                      sx={{
                        width: '100%',
                        maxWidth: '240px',
                        height: 'auto',
                        cursor: loading ? 'not-allowed' : 'pointer',
                        opacity: loading ? 0.6 : 1,
                        transition: springTransition,
                        borderRadius: 'var(--radius-md)',
                        '&:hover': {
                          transform: loading ? 'none' : 'scale(1.03)',
                          boxShadow: loading ? 'none' : '0 4px 16px rgba(3, 199, 90, 0.15)',
                        },
                        '&:active': {
                          transform: loading ? 'none' : 'scale(0.97)',
                        },
                        pointerEvents: loading ? 'none' : 'auto',
                      }}
                    />
                    {loading && (
                      <Box
                        sx={{
                          position: 'absolute',
                          top: '50%',
                          left: '50%',
                          transform: 'translate(-50%, -50%)',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 1,
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
                              '100%': { transform: 'rotate(360deg)' },
                            },
                          }}
                        />
                        <Typography variant="body2" sx={{ color: '#03C75A', fontWeight: 600 }}>
                          로그인 중...
                        </Typography>
                      </Box>
                    )}
                  </Box>

                  {/* 구분선 */}
                  <Box sx={{
                    display: 'flex',
                    alignItems: 'center',
                    mb: 3,
                    gap: 2,
                  }}>
                    <Box sx={{ flex: 1, height: '1px', bgcolor: 'var(--color-border)' }} />
                    <Typography sx={{ color: 'var(--color-text-tertiary)', fontSize: '0.8rem' }}>
                      또는
                    </Typography>
                    <Box sx={{ flex: 1, height: '1px', bgcolor: 'var(--color-border)' }} />
                  </Box>

                  {/* 회원가입 링크 */}
                  <Button
                    component={RouterLink}
                    to="/register"
                    fullWidth
                    variant="outlined"
                    sx={{
                      color: 'var(--color-primary)',
                      borderColor: 'var(--color-border)',
                      borderWidth: 1,
                      fontWeight: 600,
                      fontSize: '0.95rem',
                      py: 1.5,
                      borderRadius: 'var(--radius-md)',
                      textTransform: 'none',
                      transition: springTransition,
                      '&:hover': {
                        borderColor: 'var(--color-primary)',
                        bgcolor: 'var(--color-primary-lighter)',
                        borderWidth: 1,
                      },
                    }}
                  >
                    회원가입하기
                  </Button>
                </Box>
              </Box>
            </motion.div>
          </Box>
        </motion.div>
      </Container>

      {/* 네이버 로그인 실패 다이얼로그 */}
      <Dialog
        open={naverDialogOpen}
        onClose={handleNaverDialogClose}
        maxWidth="sm"
        fullWidth
        slotProps={{ backdrop: { 'aria-hidden': false } }}
        PaperProps={{
          sx: {
            borderRadius: 'var(--radius-xl)',
            bgcolor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
          },
        }}
      >
        <DialogTitle sx={{ fontWeight: 700, pt: 3 }}>가입 정보 없음</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2, borderRadius: 'var(--radius-md)' }}>
            가입 정보가 없습니다. 회원가입 페이지로 이동합니다.
          </Alert>
          <Typography variant="body2" color="text.secondary">
            네이버 계정으로 로그인하려면 먼저 회원가입을 완료해야 합니다.
            회원가입 페이지에서 네이버 계정을 연결하여 가입할 수 있습니다.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ p: 2.5 }}>
          <Button onClick={handleNaverDialogClose} color="secondary" sx={{ textTransform: 'none' }}>
            취소
          </Button>
          <Button
            onClick={handleGoToRegister}
            variant="contained"
            sx={{
              bgcolor: 'var(--color-primary)',
              color: 'var(--color-text-inverse)',
              fontWeight: 600,
              textTransform: 'none',
              borderRadius: 'var(--radius-md)',
              px: 3,
              transition: springTransition,
              '&:hover': {
                bgcolor: 'var(--color-primary-hover)',
                transform: 'scale(1.02)',
              },
              '&:active': { transform: 'scale(0.98)' },
            }}
          >
            회원가입 페이지로 이동
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default LoginPage;
