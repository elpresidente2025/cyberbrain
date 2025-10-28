// frontend/src/pages/RegisterPage.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate, Link as RouterLink, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { useNaverLogin } from '../hooks/useNaverLogin';
import { useThemeMode } from '../contexts/ThemeContext';
import { Container, Typography, Box, Paper, TextField, Alert, Link, Grid, FormControlLabel, Checkbox, Dialog, DialogTitle, DialogContent, DialogActions, Button, useTheme, Divider } from '@mui/material';
import UserInfoForm from '../components/UserInfoForm';
import { LoadingButton } from '../components/loading';

function RegisterPage() {
  const location = useLocation();
  const naverUserData = location.state?.naverUserData || null;
  const theme = useTheme();
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
    username: naverUserData?.id || '', // 네이버 연동 시 네이버 ID를 username으로 설정
    name: naverUserData?.name || '',
    status: '',
    position: '',
    regionMetro: '',
    regionLocal: '',
    electoralDistrict: '',
    // 선택 제공 동의 항목 자동 입력 (동의했다면 값이 존재)
    gender: normalizeGender(naverUserData?.gender || ''),
    ageDecade: naverUserData?.age || '', // 네이버는 '20-29' 형식 제공 → 그대로 저장
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

  useEffect(() => { document.title = '사이버브레인 - 회원가입'; }, []);

  // 네이버 동의 팝업 표시
  useEffect(() => {
    console.log('RegisterPage 상태 확인:', {
      showNaverConsent: location.state?.showNaverConsent,
      hasNaverUserData: !!naverUserData,
      naverUserData: naverUserData,
      locationState: location.state
    });
    
    if (location.state?.showNaverConsent && naverUserData) {
      console.log('네이버 동의 팝업 표시');
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

    // 네이버 사용자만 허용
    if (!isNaverUser) {
      setError('네이버 로그인을 통해서만 회원가입이 가능합니다.');
      return false;
    }

    // username
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
      // 네이버 사용자의 경우 원본 ID 사용, 일반 사용자는 소문자로 변환
      const uname = formData.isNaverUser 
        ? formData.username.trim() 
        : formData.username.trim().toLowerCase();

      if (formData.isNaverUser && naverUserData) {
        // 네이버 회원가입 처리
        const resp = await fetch('https://asia-northeast3-ai-secretary-6e9c8.cloudfunctions.net/naverCompleteRegistration', {
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
              // 추가 개인화 정보
              ageDecade: formData.ageDecade,
              ageDetail: formData.ageDetail,
              familyStatus: formData.familyStatus,
              backgroundCareer: formData.backgroundCareer,
              localConnection: formData.localConnection,
              politicalExperience: formData.politicalExperience,
              committees: formData.committees,
              customCommittees: formData.customCommittees,
              constituencyType: formData.constituencyType,
              twitterPremium: formData.twitterPremium
            }
          })
        });
        
        if (!resp.ok) {
          const errorData = await resp.json();
          throw new Error(errorData.error?.message || '회원가입 실패');
        }
        
        const result = await resp.json();
        console.log('네이버 회원가입 완료:', result);
        
        setSuccess(result.result.message || '회원가입이 완료되었습니다.');
        
        // 3초 후 로그인 페이지로 이동
        setTimeout(() => {
          navigate('/login', { 
            state: { 
              message: '회원가입이 완료되었습니다. 네이버로 로그인해주세요.' 
            } 
          });
        }, 3000);
      } else {
        // 네이버 사용자가 아닌 경우 에러
        throw new Error('네이버 로그인을 통해서만 회원가입이 가능합니다.');
      }
    } catch (err) {
      setError(err.message || '회원가입 처리 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  // 네이버 동의 처리 핸들러
  const handleNaverConsentAccept = () => {
    setNaverConsentOpen(false);
    // 동의 후 정보 제공 동의 완료, 폼 계속 진행
  };

  const handleNaverConsentDecline = () => {
    setNaverConsentOpen(false);
    // 동의 거부 시 로그인 페이지로 이동
    navigate('/login', {
      state: {
        message: '정보 제공에 동의하지 않으면 회원가입을 진행할 수 없습니다.'
      }
    });
  };

  // 네이버 회원가입 시작
  const handleNaverSignup = async () => {
    setError('');
    try {
      await loginWithNaver();
      // 성공 시 useNaverLogin 훅이 자동으로 회원가입 페이지로 이동시킴
    } catch (err) {
      console.error('네이버 회원가입 시작 오류:', err);
      setError(err.message || '네이버 로그인에 실패했습니다.');
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', py: { xs: 2, sm: 4 } }}>
      <Container component="main" maxWidth="md">
        <Box sx={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <Typography component="h1" variant="h5" sx={{ color: theme.palette.mode === 'dark' ? '#ffffff' : '#000000' }}>
            회원가입
          </Typography>

          <Paper elevation={2} sx={{ p: { xs: 2, sm: 4 }, mt: { xs: 2, sm: 3 }, width: '100%' }}>
            {/* 네이버 로그인이 안 되어 있으면 버튼 표시 */}
            {!naverUserData ? (
              <Box>
                <Alert severity="info" sx={{ mb: 3 }}>
                  전자두뇌비서관은 네이버 아이디로만 회원가입이 가능합니다.
                </Alert>

                <Box sx={{ textAlign: 'center', mb: 3 }}>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                    네이버 아이디로 간편하게 시작하세요
                  </Typography>

                  <Box sx={{ position: 'relative', display: 'inline-block', width: '75%' }}>
                    <Box
                      component="img"
                      src={isDarkMode ? "/buttons/login_dark.png" : "/buttons/login_light.png"}
                      alt="네이버로 회원가입"
                      onClick={handleNaverSignup}
                      sx={{
                        width: '100%',
                        maxWidth: '225px',
                        height: 'auto',
                        cursor: naverLoading ? 'not-allowed' : 'pointer',
                        opacity: naverLoading ? 0.6 : 1,
                        transition: 'opacity 0.2s, transform 0.1s',
                        '&:hover': {
                          transform: naverLoading ? 'none' : 'scale(1.02)',
                        },
                        '&:active': {
                          transform: naverLoading ? 'none' : 'scale(0.98)',
                        },
                        pointerEvents: naverLoading ? 'none' : 'auto'
                      }}
                    />
                    {naverLoading && (
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
                          연결 중...
                        </Typography>
                      </Box>
                    )}
                  </Box>
                </Box>

                {naverError && (
                  <Alert severity="error" sx={{ mt: 2 }}>
                    {naverError}
                  </Alert>
                )}

                <Divider sx={{ my: 3 }} />

                <Box sx={{ textAlign: 'center' }}>
                  <Typography variant="body2" color="text.secondary">
                    이미 계정이 있으신가요?{' '}
                    <Link component={RouterLink} to="/login">
                      로그인
                    </Link>
                  </Typography>
                </Box>
              </Box>
            ) : (
              /* 네이버 로그인 완료 후 회원가입 폼 */
              <Box component="form" onSubmit={handleSubmit}>
                <Grid container spacing={{ xs: 2, sm: 3 }}>
                  <Grid item xs={12}>
                    <Alert severity="success" sx={{ mb: 2 }}>
                      네이버 계정 연결 완료! 추가 정보를 입력해주세요.
                    </Alert>
                  </Grid>

                  <Grid item xs={12}>
                    <Typography variant="h6" gutterBottom>
                      계정 정보
                    </Typography>
                  </Grid>

                {/* Username: show for all users but disabled for Naver users */}
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
                    label={<Typography variant="body2"><strong>이용약관</strong> 및 <strong>개인정보 처리방침</strong>에 동의합니다 (필수)</Typography>}
                  />
                </Grid>

                {error && (
                  <Grid item xs={12}><Alert severity="error">{error}</Alert></Grid>
                )}

                <Grid item xs={12}>
                  <LoadingButton type="submit" fullWidth variant="contained" size="large" loading={loading} loadingText="처리 중..">
                    회원가입
                  </LoadingButton>
                </Grid>

                <Grid item xs={12}>
                  <Box textAlign="center">
                    <Link component={RouterLink} to="/login" variant="body2">이미 계정이 있으신가요? 로그인</Link>
                  </Box>
                </Grid>
              </Grid>
            </Box>
            )}
          </Paper>
        </Box>
      </Container>

      {/* 네이버 정보 제공 동의 다이얼로그 */}
      <Dialog open={naverConsentOpen} maxWidth="sm" fullWidth>
        <DialogTitle>네이버 정보 제공 동의</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            네이버 계정으로 회원가입을 진행하시겠습니까?
          </Alert>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            네이버에서 다음 정보를 제공받아 회원가입을 진행합니다:
          </Typography>
          <Box sx={{ pl: 2, mb: 2 }}>
            <Typography variant="body2" color="text.secondary">
              • 이름: {naverUserData?.name || '정보 없음'}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              • 성별: {naverUserData?.gender || '정보 없음'}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              • 연령대: {naverUserData?.age || '정보 없음'}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              • 프로필 이미지
            </Typography>
          </Box>
          <Typography variant="body2" color="text.secondary">
            위 정보 제공에 동의하시면 회원가입 페이지에서 추가 정보를 입력하실 수 있습니다.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleNaverConsentDecline} color="secondary">
            동의하지 않음
          </Button>
          <Button onClick={handleNaverConsentAccept} variant="contained" color="primary">
            동의하고 계속하기
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default RegisterPage;
