// frontend/src/pages/RegisterPage.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate, Link as RouterLink, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useNaverLogin } from '../hooks/useNaverLogin';
import { useThemeMode } from '../contexts/ThemeContext';
import {
  Container,
  Typography,
  Box,
  TextField,
  Alert,
  Link,
  Grid,
  FormControlLabel,
  Checkbox,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Divider,
  LinearProgress,
} from '@mui/material';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowBackIosNew, CheckCircleOutline } from '@mui/icons-material';
import UserInfoForm from '../components/UserInfoForm';
import { LoadingButton } from '../components/loading';
import { BRANDING, buildFunctionsUrl } from '../config/branding';

const springTransition = 'all 0.35s cubic-bezier(0.16, 1, 0.3, 1)';
const IOS_EASE = [0.32, 0.72, 0, 1];

function RegisterPage() {
  const location = useLocation();
  const naverUserData = location.state?.naverUserData || null;
  const navigate = useNavigate();
  const { loginWithNaver, isLoading: naverLoading, error: naverError } = useNaverLogin();
  const { isDarkMode } = useThemeMode();

  const normalizeGender = (g) => {
    if (!g) return '';
    const s = String(g).trim().toUpperCase();
    if (s === 'M' || s === 'MALE' || s === '남' || s === '남자') return '남성';
    if (s === 'F' || s === 'FEMALE' || s === '여' || s === '여자') return '여성';
    return String(g).trim();
  };

  const [formData, setFormData] = useState({
    username: naverUserData?.id || '',
    name: naverUserData?.name || '',
    status: '',
    position: '',
    regionMetro: '',
    regionLocal: '',
    electoralDistrict: '',
    gender: normalizeGender(naverUserData?.gender || ''),
    ageDecade: naverUserData?.age || '',
    ageDetail: naverUserData?.age || '',
    agreedToTerms: false,
    isNaverUser: !!naverUserData,
    naverData: naverUserData,
  });

  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const [naverConsentOpen, setNaverConsentOpen] = useState(false);
  const { register } = useAuth();

  useEffect(() => { document.title = `${BRANDING.serviceName} - 회원가입`; }, []);

  useEffect(() => {
    if (location.state?.showNaverConsent && naverUserData) {
      setNaverConsentOpen(true);
    }
  }, [location.state, naverUserData]);

  const handleChange = (e) => {
    const { name, value, checked, type } = e.target;
    setFormData((prev) => ({ ...prev, [name]: type === 'checkbox' ? checked : value }));
    setError('');
  };

  const handleUserInfoChange = (name, value) => {
    setFormData((prev) => ({ ...prev, [name]: value }));
    setError('');
  };

  const validateForm = () => {
    const {
      username, name,
      position, regionMetro, regionLocal, electoralDistrict,
      agreedToTerms, isNaverUser,
    } = formData;

    if (!isNaverUser) {
      setError('네이버 로그인을 통해서만 회원가입이 가능합니다.');
      return false;
    }

    const uname = String(username || '').trim();
    if (!uname) {
      setError('네이버 ID가 설정되지 않았습니다. 다시 로그인해 주세요.');
      return false;
    }

    if (!String(name || '').trim()) { setError('이름을 입력해 주세요.'); return false; }
    if (!position || !regionMetro || !regionLocal || !electoralDistrict) {
      setError('직책/지역 정보를 모두 선택해 주세요.');
      return false;
    }
    if (!agreedToTerms) { setError('이용약관과 개인정보 처리방침에 동의해 주세요.'); return false; }

    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (!validateForm()) return;
    try {
      setLoading(true);
      const uname = formData.isNaverUser
        ? formData.username.trim()
        : formData.username.trim().toLowerCase();

      if (formData.isNaverUser && naverUserData) {
        const resp = await fetch(buildFunctionsUrl('naverCompleteRegistration'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            naverUserData: naverUserData,
            profileData: {
              name: formData.name,
              position: formData.position,
              regionMetro: formData.regionMetro,
              regionLocal: formData.regionLocal,
              electoralDistrict: formData.electoralDistrict,
              status: formData.status || '현역',
              bio: formData.bio || '',
              gender: formData.gender || naverUserData.gender,
              age: naverUserData.age,
              ageDecade: formData.ageDecade,
              ageDetail: formData.ageDetail,
              familyStatus: formData.familyStatus,
              backgroundCareer: formData.backgroundCareer,
              localConnection: formData.localConnection,
              politicalExperience: formData.politicalExperience,
              committees: formData.committees,
              customCommittees: formData.customCommittees,
              constituencyType: formData.constituencyType
            }
          })
        });

        if (!resp.ok) {
          const errorData = await resp.json();
          throw new Error(errorData.error?.message || '회원가입 실패');
        }

        const result = await resp.json();
        setSuccess(result.result.message || '회원가입이 완료되었습니다.');

        setTimeout(() => {
          navigate('/login', {
            state: {
              message: '회원가입이 완료되었습니다. 네이버로 로그인해주세요.'
            }
          });
        }, 3000);
      } else {
        throw new Error('네이버 로그인을 통해서만 회원가입이 가능합니다.');
      }
    } catch (err) {
      setError(err.message || '회원가입 처리 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleNaverConsentAccept = () => {
    setNaverConsentOpen(false);
  };

  const handleNaverConsentDecline = () => {
    setNaverConsentOpen(false);
    navigate('/login', {
      state: {
        message: '정보 제공에 동의하지 않으면 회원가입을 진행할 수 없습니다.'
      }
    });
  };

  const handleNaverSignup = async () => {
    setError('');
    try {
      await loginWithNaver();
    } catch (err) {
      console.error('네이버 회원가입 시작 오류:', err);
      setError(err.message || '네이버 로그인에 실패했습니다.');
    }
  };

  // 가입 완료 화면
  if (success) {
    return (
      <Box sx={{
        minHeight: '100dvh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        bgcolor: 'var(--color-background)',
      }}>
        <Container maxWidth="sm">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.5, ease: IOS_EASE }}
          >
            <Box sx={{ textAlign: 'center', p: { xs: 4, sm: 6 } }}>
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ duration: 0.5, delay: 0.2, type: 'spring', stiffness: 200 }}
              >
                <CheckCircleOutline sx={{
                  fontSize: 80,
                  color: 'var(--color-success)',
                  mb: 3,
                }} />
              </motion.div>
              <Typography sx={{
                fontWeight: 700,
                fontSize: { xs: '1.75rem', sm: '2.25rem' },
                color: 'var(--color-text-primary)',
                mb: 2,
                letterSpacing: '-0.02em',
                wordBreak: 'keep-all',
              }}>
                가입이 완료되었습니다
              </Typography>
              <Typography sx={{
                color: 'var(--color-text-secondary)',
                fontSize: '1rem',
                lineHeight: 1.6,
                mb: 4,
              }}>
                {success}
              </Typography>
              <LinearProgress sx={{
                height: 3,
                borderRadius: 2,
                bgcolor: 'var(--color-border)',
                '& .MuiLinearProgress-bar': {
                  bgcolor: 'var(--color-primary)',
                },
              }} />
              <Typography sx={{
                color: 'var(--color-text-tertiary)',
                fontSize: '0.85rem',
                mt: 2,
              }}>
                잠시 후 로그인 페이지로 이동합니다...
              </Typography>
            </Box>
          </motion.div>
        </Container>
      </Box>
    );
  }

  return (
    <Box sx={{
      minHeight: '100dvh',
      bgcolor: 'var(--color-background)',
      display: 'flex',
      flexDirection: 'column',
    }}>
      {/* 상단 바 - 뒤로가기 */}
      <Box sx={{
        height: 56,
        display: 'flex',
        alignItems: 'center',
        px: { xs: 1, md: 2 },
        flexShrink: 0,
      }}>
        <Button
          component={RouterLink}
          to="/login"
          disableRipple
          startIcon={<ArrowBackIosNew sx={{ fontSize: '17px !important' }} />}
          sx={{
            color: 'var(--color-primary)',
            fontWeight: 400,
            fontSize: '1.0625rem',
            textTransform: 'none',
            '&:hover': { bgcolor: 'transparent', opacity: 0.6 },
          }}
        >
          로그인
        </Button>
      </Box>

      {/* 본문 */}
      <Box
        component="main"
        sx={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          px: { xs: 2, sm: 3, md: 4 },
          pb: { xs: 4, sm: 6 },
        }}
      >
        <Container maxWidth="md" disableGutters sx={{ flex: 1 }}>
          {/* 네이버 연결 전 */}
          {!naverUserData ? (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: IOS_EASE }}
            >
              <Box sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                minHeight: '70vh',
                textAlign: 'center',
              }}>
                <Typography sx={{
                  fontWeight: 700,
                  fontSize: { xs: '2rem', sm: '2.5rem' },
                  color: 'var(--color-text-primary)',
                  letterSpacing: '-0.03em',
                  lineHeight: 1.15,
                  mb: 2,
                  wordBreak: 'keep-all',
                }}>
                  회원가입
                </Typography>
                <Typography sx={{
                  color: 'var(--color-text-secondary)',
                  fontSize: { xs: '1rem', sm: '1.0625rem' },
                  lineHeight: 1.5,
                  mb: { xs: 5, sm: 7 },
                  maxWidth: 400,
                  wordBreak: 'keep-all',
                }}>
                  {BRANDING.serviceName}은 네이버 아이디로만
                  회원가입이 가능합니다.
                </Typography>

                {/* 네이버 로그인 버튼 */}
                <Box sx={{
                  p: { xs: 4, sm: 5 },
                  borderRadius: 'var(--radius-xl)',
                  bgcolor: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  boxShadow: 'var(--shadow-md)',
                  width: '100%',
                  maxWidth: 400,
                  textAlign: 'center',
                }}>
                  <Box sx={{ position: 'relative', display: 'inline-block', width: '80%', mb: 3 }}>
                    <Box
                      component="img"
                      src={isDarkMode ? "/buttons/login_dark.png" : "/buttons/login_light.png"}
                      alt="네이버로 회원가입"
                      onClick={handleNaverSignup}
                      sx={{
                        width: '100%',
                        maxWidth: '240px',
                        height: 'auto',
                        cursor: naverLoading ? 'not-allowed' : 'pointer',
                        opacity: naverLoading ? 0.6 : 1,
                        transition: springTransition,
                        borderRadius: 'var(--radius-md)',
                        '&:hover': {
                          transform: naverLoading ? 'none' : 'scale(1.03)',
                          boxShadow: naverLoading ? 'none' : '0 4px 16px rgba(3, 199, 90, 0.15)',
                        },
                        '&:active': {
                          transform: naverLoading ? 'none' : 'scale(0.97)',
                        },
                        pointerEvents: naverLoading ? 'none' : 'auto',
                      }}
                    />
                    {naverLoading && (
                      <Box sx={{
                        position: 'absolute',
                        top: '50%',
                        left: '50%',
                        transform: 'translate(-50%, -50%)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 1,
                      }}>
                        <Box sx={{
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
                        }} />
                        <Typography variant="body2" sx={{ color: '#03C75A', fontWeight: 600 }}>
                          연결 중...
                        </Typography>
                      </Box>
                    )}
                  </Box>

                  {naverError && (
                    <Alert severity="error" sx={{ mt: 1, borderRadius: 'var(--radius-md)' }}>
                      {naverError}
                    </Alert>
                  )}
                </Box>

                <Typography sx={{
                  color: 'var(--color-text-tertiary)',
                  fontSize: '0.85rem',
                  mt: 4,
                }}>
                  이미 계정이 있으신가요?{' '}
                  <Link component={RouterLink} to="/login" sx={{
                    color: 'var(--color-primary)',
                    fontWeight: 600,
                    textDecoration: 'none',
                    '&:hover': { textDecoration: 'underline' },
                  }}>
                    로그인
                  </Link>
                </Typography>
              </Box>
            </motion.div>
          ) : (
            /* 네이버 연결 완료 → 추가 정보 입력 폼 */
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, ease: IOS_EASE }}
            >
              <Box sx={{ maxWidth: 700, mx: 'auto', pt: { xs: 2, sm: 4 } }}>
                {/* 타이틀 */}
                <Typography sx={{
                  fontWeight: 700,
                  fontSize: { xs: '1.75rem', sm: '2.25rem' },
                  color: 'var(--color-text-primary)',
                  letterSpacing: '-0.03em',
                  lineHeight: 1.15,
                  mb: 1.5,
                  wordBreak: 'keep-all',
                }}>
                  추가 정보를{'\n'}
                  입력해 주세요
                </Typography>
                <Typography sx={{
                  color: 'var(--color-text-secondary)',
                  fontSize: { xs: '1rem', sm: '1.0625rem' },
                  lineHeight: 1.5,
                  mb: 4,
                }}>
                  네이버 계정 연결이 완료되었습니다.
                </Typography>

                {/* 폼 카드 */}
                <Box
                  component="form"
                  onSubmit={handleSubmit}
                  sx={{
                    p: { xs: 3, sm: 4 },
                    borderRadius: 'var(--radius-xl)',
                    bgcolor: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    boxShadow: 'var(--shadow-md)',
                  }}
                >
                  <Grid container spacing={{ xs: 2, sm: 3 }}>
                    {/* 계정 정보 */}
                    <Grid item xs={12}>
                      <Typography sx={{
                        fontWeight: 700,
                        fontSize: '1.1rem',
                        color: 'var(--color-text-primary)',
                        mb: 0.5,
                      }}>
                        계정 정보
                      </Typography>
                    </Grid>

                    <Grid item xs={12}>
                      <TextField
                        required
                        fullWidth
                        id="username"
                        label="아이디"
                        name="username"
                        autoComplete="username"
                        value={formData.username}
                        onChange={handleChange}
                        disabled={loading || formData.isNaverUser}
                        helperText={formData.isNaverUser ? "네이버 ID가 자동으로 설정되었습니다." : "소문자/숫자/._- 3~20자"}
                        FormHelperTextProps={{
                          sx: { color: formData.isNaverUser ? 'success.main' : 'text.secondary' }
                        }}
                      />
                    </Grid>

                    {/* 사용자 기본 정보 */}
                    <UserInfoForm
                      name={formData.name}
                      status={formData.status}
                      position={formData.position}
                      regionMetro={formData.regionMetro}
                      regionLocal={formData.regionLocal}
                      electoralDistrict={formData.electoralDistrict}
                      onChange={handleUserInfoChange}
                      disabled={loading}
                      nameDisabled={formData.isNaverUser}
                      enableDuplicateCheck={false}
                      excludeUserId={null}
                      showTitle={true}
                    />

                    {/* 구분선 */}
                    <Grid item xs={12}>
                      <Divider sx={{ my: 1 }} />
                    </Grid>

                    {/* 동의 */}
                    <Grid item xs={12}>
                      <FormControlLabel
                        control={
                          <Checkbox
                            name="agreedToTerms"
                            checked={formData.agreedToTerms}
                            onChange={handleChange}
                            disabled={loading}
                            color="primary"
                          />
                        }
                        label={
                          <Typography variant="body2" sx={{ wordBreak: 'keep-all' }}>
                            <strong>이용약관</strong> 및 <strong>개인정보 처리방침</strong>에 동의합니다 (필수)
                          </Typography>
                        }
                      />
                    </Grid>

                    {error && (
                      <Grid item xs={12}>
                        <Alert severity="error" sx={{ borderRadius: 'var(--radius-md)' }}>
                          {error}
                        </Alert>
                      </Grid>
                    )}

                    {/* 제출 버튼 */}
                    <Grid item xs={12}>
                      <motion.div
                        whileTap={loading ? {} : { scale: 0.97 }}
                        transition={{ duration: 0.15, ease: IOS_EASE }}
                      >
                        <LoadingButton
                          type="submit"
                          fullWidth
                          variant="contained"
                          size="large"
                          loading={loading}
                          loadingText="처리 중.."
                          sx={{
                            bgcolor: 'var(--color-primary)',
                            color: '#fff',
                            fontWeight: 600,
                            fontSize: '1.0625rem',
                            textTransform: 'none',
                            borderRadius: 'var(--radius-lg)',
                            py: 1.75,
                            boxShadow: 'none',
                            transition: springTransition,
                            '&:hover': {
                              bgcolor: 'var(--color-primary-hover)',
                              boxShadow: 'var(--shadow-glow-primary)',
                            },
                            '&.Mui-disabled': {
                              bgcolor: 'var(--color-border)',
                              color: 'var(--color-text-tertiary)',
                            },
                          }}
                        >
                          회원가입
                        </LoadingButton>
                      </motion.div>
                    </Grid>

                    <Grid item xs={12}>
                      <Box textAlign="center">
                        <Typography sx={{
                          color: 'var(--color-text-tertiary)',
                          fontSize: '0.85rem',
                        }}>
                          이미 계정이 있으신가요?{' '}
                          <Link component={RouterLink} to="/login" sx={{
                            color: 'var(--color-primary)',
                            fontWeight: 600,
                            textDecoration: 'none',
                            '&:hover': { textDecoration: 'underline' },
                          }}>
                            로그인
                          </Link>
                        </Typography>
                      </Box>
                    </Grid>
                  </Grid>
                </Box>

                {/* 하단 안내 */}
                <Typography sx={{
                  textAlign: 'center',
                  fontSize: '0.8125rem',
                  color: 'var(--color-text-tertiary)',
                  mt: 3,
                  mb: 4,
                  letterSpacing: '-0.005em',
                  wordBreak: 'keep-all',
                }}>
                  입력하신 정보는 나중에 프로필에서 언제든 수정할 수 있습니다.
                </Typography>
              </Box>
            </motion.div>
          )}
        </Container>
      </Box>

      {/* 네이버 정보 제공 동의 다이얼로그 */}
      <Dialog
        open={naverConsentOpen}
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
        <DialogTitle sx={{ fontWeight: 700, pt: 3 }}>네이버 정보 제공 동의</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2, borderRadius: 'var(--radius-md)' }}>
            네이버 계정으로 회원가입을 진행하시겠습니까?
          </Alert>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            네이버에서 다음 정보를 제공받아 회원가입을 진행합니다:
          </Typography>
          <Box sx={{
            pl: 2,
            mb: 2,
            p: 2,
            borderRadius: 'var(--radius-md)',
            bgcolor: 'var(--color-background)',
            border: '1px solid var(--color-border)',
          }}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
              이름: {naverUserData?.name || '정보 없음'}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
              성별: {naverUserData?.gender || '정보 없음'}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
              연령대: {naverUserData?.age || '정보 없음'}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              프로필 이미지
            </Typography>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ wordBreak: 'keep-all' }}>
            위 정보 제공에 동의하시면 회원가입 페이지에서 추가 정보를 입력하실 수 있습니다.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ p: 2.5, gap: 1 }}>
          <Button
            onClick={handleNaverConsentDecline}
            sx={{
              color: 'var(--color-text-secondary)',
              textTransform: 'none',
            }}
          >
            동의하지 않음
          </Button>
          <Button
            onClick={handleNaverConsentAccept}
            variant="contained"
            sx={{
              bgcolor: 'var(--color-primary)',
              color: '#fff',
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
            동의하고 계속하기
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default RegisterPage;
