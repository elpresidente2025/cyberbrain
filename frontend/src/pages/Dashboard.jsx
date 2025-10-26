// frontend/src/pages/Dashboard.jsx
import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Container,
  Typography,
  Button,
  Paper,
  List,
  ListItem,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Grid,
  Alert,
  CircularProgress,
  useTheme,
  useMediaQuery,
  Divider,
  Chip,
  LinearProgress,
  Card,
  CardContent
} from '@mui/material';
import {
  LoadingState,
  EmptyState,
  ContentCard,
  ActionButton,
  NotificationSnackbar,
  useNotification
} from '../components/ui';
import { colors, spacing, typography, visualWeight, verticalRhythm } from '../theme/tokens';
import {
  Create,
  KeyboardArrowRight,
  MoreVert,
  Settings,
  TrendingUp,
  CalendarToday,
  Notifications,
  CheckCircle,
  Warning,
  CreditCard,
  Schedule,
  ContentCopy
} from '@mui/icons-material';
import { LoadingSpinner } from '../components/loading';
import { useNavigate } from 'react-router-dom';
import DashboardLayout from '../components/DashboardLayout';
import NoticeBanner from '../components/dashboard/NoticeBanner';
import ElectionDDay from '../components/dashboard/ElectionDDay';
import PublishingProgress from '../components/dashboard/PublishingProgress';
import PostViewerModal from '../components/PostViewerModal';
import OnboardingWelcomeModal from '../components/onboarding/OnboardingWelcomeModal';
import { useAuth } from '../hooks/useAuth';
import { getUserFullTitle, getUserDisplayTitle, getUserRegionInfo, getUserStatusIcon } from '../utils/userUtils';
import { functions } from '../services/firebase';
import { httpsCallable } from 'firebase/functions';
import { callFunctionWithNaverAuth } from '../services/firebaseService';

const Dashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  // 상태 관리
  const [usage, setUsage] = useState({ postsGenerated: 0, monthlyLimit: 50 });
  const [recentPosts, setRecentPosts] = useState([]);
  const [notices, setNotices] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // useNotification 훅 사용
  const { notification, showNotification, hideNotification } = useNotification();
  
  // 모달 관리
  const [viewerOpen, setViewerOpen] = useState(false);
  const [viewerPost, setViewerPost] = useState(null);
  const [onboardingOpen, setOnboardingOpen] = useState(false);

  // Bio 체크 실행 여부 추적
  const hasCheckedBio = useRef(false);

  // 사용자 정보
  const userTitle = getUserFullTitle(user);
  const userIcon = getUserStatusIcon(user);
  const regionInfo = getUserRegionInfo(user);
  
  // 플랜 정보 (실제 사용자 데이터 기반)
  const isAdmin = user?.role === 'admin';
  const planName = isAdmin ? '관리자' : getPlanName(usage.monthlyLimit);

  // 플랜명 결정 함수
  function getPlanName(limit) {
    return '스탠다드 플랜';
  }

  // 플랜별 색상 가져오기
  function getPlanColor(planName) {
    return colors.brand.primary; // 스탠다드 플랜 색상
  }

  const planColor = getPlanColor(planName);

  // 데이터 로딩 함수 (재사용 가능하도록 분리)
  const fetchDashboardData = async () => {
    if (!user?.uid) return;
    
    setIsLoading(true);
    setError(null);

    try {
      // 사용량 정보와 포스트 목록을 별도로 호출 (네이버 인증 지원)
      // 병렬로 두 함수 호출
      const [dashboardData, postsData] = await Promise.all([
        callFunctionWithNaverAuth('getDashboardData'),
        callFunctionWithNaverAuth('getUserPosts')
      ]);
      
      const postsArray = postsData?.posts || [];
      
      // 사용량 정보 설정
      setUsage(dashboardData.usage || { postsGenerated: 0, monthlyLimit: 50 });
      
      // 히스토리 페이지와 동일한 포스트 목록 사용 (최신순으로 정렬)
      const sortedPosts = postsArray.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
      setRecentPosts(sortedPosts);
      
    } catch (err) {
      console.error('❌ Dashboard: 데이터 요청 실패:', err);
      
      // 에러 처리
      let errorMessage = '데이터를 불러오는 데 실패했습니다.';
      if (err.code === 'functions/unauthenticated') {
        errorMessage = '로그인이 필요합니다.';
      } else if (err.code === 'functions/internal') {
        errorMessage = '서버에서 오류가 발생했습니다.';
      } else if (err.message) {
        errorMessage = err.message;
      }
      
      setError(errorMessage);
    } finally {
      setIsLoading(false);
    }
  };

  // bio 체크 및 온보딩 로직
  const checkBioAndShowOnboarding = () => {
    if (!user) return;

    // 세션 중에 한 번 닫으면 다시 표시하지 않음
    const onboardingDismissed = sessionStorage.getItem('onboardingDismissed');
    if (onboardingDismissed) return;

    // user 객체를 먼저 체크, localStorage는 폴백
    let hasSufficientBio = false;
    try {
      // 1. user 객체에서 직접 체크 (최신 데이터)
      if (user.bio && user.bio.trim().length >= 200) {
        hasSufficientBio = true;
      } else {
        // 2. localStorage 폴백 (네이버 로그인 시)
        const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
        hasSufficientBio = currentUser.bio && currentUser.bio.trim().length >= 200;
      }

      console.log('🔍 Bio 체크:', {
        userBio: user.bio?.length || 0,
        localStorageBio: JSON.parse(localStorage.getItem('currentUser') || '{}').bio?.length || 0,
        hasSufficientBio
      });
    } catch (e) {
      // fallback to user object
      hasSufficientBio = user.bio && user.bio.trim().length >= 200;
    }

    const shouldShowOnboarding = !hasSufficientBio;

    if (shouldShowOnboarding) {
      console.log('🎯 Bio 부족 - 온보딩 모달 표시');
      setOnboardingOpen(true);
    }
  };

  // 실제 데이터 로딩 (페이지 마운트 시에만 실행)
  useEffect(() => {
    fetchDashboardData();
  }, [user]);

  // bio 체크 (사용자 로그인 후) - isLoading이 false가 되면 프로필 로드 완료된 상태
  // ref를 사용하여 한 번만 실행되도록 보장
  useEffect(() => {
    console.log('🔄 Bio check useEffect:', {
      hasUser: !!user,
      isLoading,
      hasCheckedBio: hasCheckedBio.current
    });

    if (user && !isLoading && !hasCheckedBio.current) {
      console.log('✅ Bio check 조건 충족 - 즉시 실행');
      hasCheckedBio.current = true;
      // isLoading이 false이면 이미 프로필 로드 완료된 상태이므로 즉시 실행
      checkBioAndShowOnboarding();
    }
  }, [user, isLoading]);

  // 공지사항 별도 로딩 (대시보드 데이터와 독립적으로)
  useEffect(() => {
    const fetchNotices = async () => {
      if (!user?.uid) return;

      try {
        const noticesResponse = await callFunctionWithNaverAuth('getActiveNotices');
        
        // 올바른 경로로 공지사항 데이터 추출
        const noticesData = noticesResponse?.notices || [];
        setNotices(noticesData);
        
      } catch (noticeError) {
        console.error('❌ 공지사항 로딩 실패:', noticeError);
        setNotices([]);
      }
    };

    fetchNotices();
  }, [user]);


  // 이벤트 핸들러들
  const handleGeneratePost = () => {
    // 비활성화 조건 체크는 버튼 레벨에서 처리
    navigate('/generate');
  };

  const handleChangePlan = () => {
    navigate('/profile');
  };

  const handleViewAllPosts = () => {
    navigate('/posts');
  };

  const handleViewBilling = () => {
    navigate('/billing');
  };

  // 당원 인증 상태 판단 함수
  const getAuthStatus = () => {
    // 실제 사용자 인증 상태를 기반으로 체크
    if (user?.verificationStatus === 'verified' && user?.lastVerification) {
      return {
        status: 'active',
        image: '/buttons/AuthPass.png',
        title: '인증 완료',
        message: `${user.lastVerification.quarter} 인증 완료`
      };
    } else {
      return {
        status: 'warning',
        image: '/buttons/AuthFail.png',
        title: '인증 필요',
        message: '당원 인증이 필요합니다'
      };
    }
  };

  const authStatus = getAuthStatus();

  // 유틸리티 함수들 (PostsListPage에서 가져옴)
  const formatDate = (iso) => {
    try {
      if (!iso) return '-';
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return '-';
      const y = d.getFullYear();
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      const hh = String(d.getHours()).padStart(2, '0');
      const mm = String(d.getMinutes()).padStart(2, '0');
      return `${y}-${m}-${day} ${hh}:${mm}`;
    } catch {
      return '-';
    }
  };

  const stripHtml = (html = '') => {
    try {
      return html.replace(/<[^>]*>/g, '');
    } catch {
      return html || '';
    }
  };

  const handlePostClick = (postId) => {
    const post = recentPosts.find(p => p.id === postId);
    if (post) {
      setViewerPost(post);
      setViewerOpen(true);
    }
  };

  const closeViewer = () => {
    setViewerOpen(false);
    setViewerPost(null);
  };

  const handleDelete = async (postId, e) => {
    if (e) e.stopPropagation();
    if (!postId) return;
    const ok = window.confirm('정말 이 원고를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.');
    if (!ok) return;
    try {
      // 네이버 인증으로 삭제 요청
      const response = await fetch('https://asia-northeast3-ai-secretary-6e9c8.cloudfunctions.net/deletePost', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          postId,
          __naverAuth: { uid: user.uid, provider: 'naver' }
        })
      });
      
      const result = await response.json();
      
      if (!response.ok) {
        throw new Error(result.message || '삭제에 실패했습니다.');
      }
      
      // 대시보드의 최근 포스트 목록에서 제거
      setRecentPosts((prev) => prev.filter((p) => p.id !== postId));

      showNotification('삭제되었습니다.', 'info');
      if (viewerPost?.id === postId) {
        setViewerOpen(false);
        setViewerPost(null);
      }
    } catch (err) {
      console.error(err);
      showNotification(err.message || '삭제에 실패했습니다.', 'error');
    }
  };

  const handleCopy = (content, e) => {
    if (e) e.stopPropagation();
    try {
      const text = stripHtml(content);
      navigator.clipboard.writeText(text);
      showNotification('클립보드에 복사되었습니다!', 'success');
    } catch (err) {
      console.error(err);
      showNotification('복사에 실패했습니다.', 'error');
    }
  };


  // 사용량 퍼센트 계산
  const usagePercentage = isAdmin ? 100 : 
    usage.monthlyLimit > 0 ? (usage.postsGenerated / usage.monthlyLimit) * 100 : 0;

  // 로딩 중
  if (isLoading) {
    return (
      <DashboardLayout>
        <LoadingState loading={true} type="fullPage" message="대시보드 로딩 중..." />
      </DashboardLayout>
    );
  }

  // 에러 발생
  if (error) {
    return (
      <DashboardLayout>
        <Box sx={{ py: `${spacing.xl}px`, px: { xs: 2, md: 4 }, maxWidth: '1200px', mx: 'auto' }}>
          <Alert severity="error" sx={{ mb: `${spacing.lg}px` }}>
            {error}
          </Alert>
          <Button variant="contained" onClick={() => window.location.reload()}>
            다시 시도
          </Button>
        </Box>
      </DashboardLayout>
    );
  }

  // 자기소개 완성 여부 확인
  const hasBio = user?.bio && user.bio.trim().length > 0;
  const showBioAlert = !hasBio && !isAdmin;
  
  // 버튼 비활성화 조건 계산
  const canGeneratePost = isAdmin || (hasBio && usage.postsGenerated < usage.monthlyLimit);

  return (
    <DashboardLayout>
      <Box
        sx={{
          py: `${spacing.xl}px`,
          px: { xs: 2, md: 4 },
          maxWidth: '1200px',
          mx: 'auto'
        }}
      >
        {/* 공지사항 배너 - 최상단에 위치 */}
        <NoticeBanner />
        
        
        {/* 사용자 정보 + CTA 버튼 */}
        <Box sx={{ mb: `${spacing.lg}px` }}>
          {/* 상단: 사용자 정보와 프로필 수정 버튼 */}
          <Box sx={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            mb: `${spacing.md}px`,
            flexWrap: 'wrap',
            gap: `${spacing.xs}px`
          }}>
            {/* 사용자 정보 */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: `${spacing.md}px`, flexWrap: 'wrap' }}>
              <Typography variant="h5" sx={{
                fontWeight: 600,
                color: theme.palette.mode === 'dark' ? '#ffffff' : '#000000'
              }}>
                {user?.name || '사용자'} {getUserDisplayTitle(user)} {userIcon}
              </Typography>
              {regionInfo && (
                <Chip
                  label={regionInfo}
                  size="medium"
                  sx={{
                    bgcolor: theme.palette.mode === 'dark' ? colors.brand.primaryLight10 : 'rgba(21, 36, 132, 0.15)',
                    color: theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.9)' : colors.brand.primary,
                    fontWeight: 500
                  }}
                />
              )}
              <Chip
                label={`D-${(() => {
                  const electionDate = new Date('2026-06-03');
                  const today = new Date();
                  const diffTime = electionDate - today;
                  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                  return diffDays;
                })()}`}
                size="medium"
                sx={{ bgcolor: colors.brand.primary, color: 'white', fontWeight: 600 }}
              />
            </Box>

            {/* 프로필 수정 버튼 */}
            <Button
              variant="outlined"
              size="small"
              startIcon={<Settings />}
              onClick={handleChangePlan}
              sx={{
                bgcolor: showBioAlert ? colors.brand.gold : 'transparent',
                color: showBioAlert ? '#ffffff' : (theme.palette.mode === 'dark' ? '#ffffff' : '#000000'),
                borderColor: showBioAlert ? colors.brand.gold : (theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.23)' : 'rgba(0, 0, 0, 0.23)'),
                fontSize: '0.75rem',
                py: 0.5,
                px: 1.5,
                '&:hover': {
                  bgcolor: showBioAlert ? '#e6a91c' : 'rgba(0, 0, 0, 0.04)',
                  borderColor: showBioAlert ? '#e6a91c' : 'rgba(0, 0, 0, 0.23)',
                },
                ...(showBioAlert && {
                  animation: 'profileEditBlink 2s ease-in-out infinite',
                  '@keyframes profileEditBlink': {
                    '0%, 50%, 100%': { opacity: 1 },
                    '25%, 75%': { opacity: 0.6 }
                  }
                })
              }}
            >
              프로필 수정{showBioAlert && ' ⚠️'}
            </Button>
          </Box>

          {/* 플랜 정보 및 사용량 */}
          <Paper
            elevation={0}
            sx={{
              p: `${spacing.md}px`,
              bgcolor: theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.03)' : 'rgba(0, 0, 0, 0.02)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: `${spacing.md}px`
            }}
          >
            {/* 플랜 정보 */}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: `${spacing.md}px`, flexWrap: 'wrap' }}>
              <Typography variant="h6" sx={{ color: theme.palette.text.primary }}>
                플랜: <strong style={{ color: planColor }}>{planName}</strong>
              </Typography>
              {!isAdmin && (
                <Typography variant="body1" color="text.secondary">
                  · 발행 목표: {usage.postsGenerated}/{usage.monthlyLimit}회
                </Typography>
              )}
              {isAdmin && (
                <Chip label="무제한" sx={{ bgcolor: planColor, color: 'white' }} />
              )}
            </Box>

            {/* 인증 상태 */}
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: `${spacing.xs}px`,
                cursor: 'pointer',
                transition: 'transform 0.2s ease',
                '&:hover': {
                  transform: 'scale(1.02)'
                }
              }}
              onClick={handleViewBilling}
            >
              <Box
                component="img"
                src={authStatus.image}
                alt={authStatus.title}
                sx={{
                  width: '50px',
                  height: 'auto',
                  filter: 'drop-shadow(0 1px 4px rgba(0,0,0,0.1))'
                }}
              />
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.75rem', fontWeight: 500 }}>
                {authStatus.message}
              </Typography>
            </Box>
          </Paper>

          {/* 새 원고 생성 버튼 - 크고 눈에 띄게 */}
          <Button
            variant="contained"
            size="large"
            startIcon={<Create />}
            onClick={handleGeneratePost}
            disabled={!canGeneratePost}
            fullWidth
            sx={{
              mt: `${spacing.md}px`,
              bgcolor: canGeneratePost ? planColor : '#757575',
              color: '#ffffff',
              fontSize: '1.125rem',
              py: 2.5,
              minHeight: '70px',
              fontWeight: 700,
              boxShadow: '0 4px 12px rgba(0, 0, 0, 0.3)',
              '&:hover': canGeneratePost ? {
                bgcolor: planColor,
                filter: 'brightness(0.9)',
              } : {},
              '&.Mui-disabled': {
                bgcolor: '#757575 !important',
                color: 'rgba(255, 255, 255, 0.6) !important'
              }
            }}
          >
            📝 새 원고 생성
          </Button>

          {/* 프로필 미완료 경고 메시지 */}
          {showBioAlert && (
            <Alert severity="warning" sx={{ mt: `${spacing.md}px` }}>
              <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5, color: theme.palette.text.primary }}>
                프로필 설정이 완료되지 않았습니다
              </Typography>
              <Typography variant="body2" sx={{ color: theme.palette.text.primary }}>
                AI 원고 생성을 위해 자기소개 작성이 필요합니다.
              </Typography>
            </Alert>
          )}
        </Box>

        {/* 콘텐츠 섹션 - 기존 구조 유지하되 공지사항은 데이터가 있을 때만 표시 */}
        {isMobile ? (
          /* 모바일 - 수직 스택 */
          <Box>
            {/* 공지사항 카드 - 공지가 있을 때만 표시 */}
            {notices.length > 0 && (
              <Paper elevation={0} sx={{
                mb: `${spacing.lg}px`,
                bgcolor: theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.03)' : 'rgba(0, 0, 0, 0.03)',
                border: `1px solid ${theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.1)'}`,
                borderRadius: 2
              }}>
                <Box sx={{ p: `${spacing.md}px`, borderBottom: '1px solid', borderColor: 'divider' }}>
                  <Typography variant="h6" sx={{ fontWeight: 600, display: 'flex', alignItems: 'center', color: theme.palette.text.primary }}>
                    <Notifications sx={{ mr: `${spacing.xs}px`, color: 'colors.brand.primary' }} />
                    공지사항
                  </Typography>
                </Box>

                <List>
                  {notices.slice(0, 5).map((notice, index) => (
                    <React.Fragment key={notice.id || index}>
                      <ListItem sx={{ alignItems: 'flex-start' }}>
                        <ListItemText
                          primary={
                            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: `${spacing.xs}px` }}>
                                <Typography variant="subtitle2" sx={{ fontWeight: 600, color: theme.palette.text.primary }}>
                                  {notice.title || '제목 없음'}
                                </Typography>
                                {notice.priority === 'high' && (
                                  <Chip label="중요" color="error" size="small" />
                                )}
                              </Box>
                              <Typography variant="caption" color="text.secondary">
                                {notice.createdAt ? new Date(notice.createdAt).toLocaleDateString('ko-KR', {
                                  month: 'short',
                                  day: 'numeric'
                                }) : ''}
                              </Typography>
                            </Box>
                          }
                          secondary={
                            <Typography
                              variant="body2"
                              color="text.secondary"
                              sx={{
                                mt: 0.5,
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                display: '-webkit-box',
                                WebkitLineClamp: 2,
                                WebkitBoxOrient: 'vertical'
                              }}
                            >
                              {notice.content || '내용 없음'}
                            </Typography>
                          }
                        />
                      </ListItem>
                      {index < Math.min(notices.length, 5) - 1 && <Divider />}
                    </React.Fragment>
                  ))}
                </List>

                {notices.length > 5 && (
                  <Box sx={{ p: `${spacing.md}px`, textAlign: 'center' }}>
                    <Button variant="text" size="small" sx={{ color: planColor }}>
                      더 보기 ({notices.length - 5}개 더)
                    </Button>
                  </Box>
                )}
              </Paper>
            )}

            {/* 발행 진행률 카드 */}
            <Box sx={{ mb: `${spacing.lg}px` }}>
              <PublishingProgress />
            </Box>

            {/* 최근 생성한 글 */}
            <Paper elevation={0} sx={{
              mb: `${spacing.lg}px`,
              bgcolor: 'rgba(255, 255, 255, 0.03)',
              border: '1px solid rgba(255, 255, 255, 0.05)',
              borderRadius: 2
            }}>
              <Box sx={{ p: `${spacing.md}px`, borderBottom: '1px solid', borderColor: 'divider' }}>
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  최근 생성한 글
                </Typography>
              </Box>
              
              {recentPosts.length > 0 ? (
                <>
                  <List>
                    {recentPosts.slice(0, 5).map((post, index) => (
                      <React.Fragment key={post.id}>
                        <ListItem 
                          button 
                          onClick={() => handlePostClick(post.id)}
                        >
                          <ListItemText
                            primary={`${index + 1}) ${new Date(post.createdAt).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' })} ${post.title || '제목 없음'}`}
                            secondary={post.category || '일반'}
                          />
                          <ListItemSecondaryAction>
                            <IconButton edge="end" onClick={() => handlePostClick(post.id)}>
                              <KeyboardArrowRight />
                            </IconButton>
                          </ListItemSecondaryAction>
                        </ListItem>
                        {index < Math.min(recentPosts.length, 5) - 1 && <Divider />}
                      </React.Fragment>
                    ))}
                  </List>
                  <Box sx={{ p: `${spacing.md}px`, textAlign: 'center' }}>
                    <Button variant="text" onClick={handleViewAllPosts} sx={{ color: planColor }}>
                      전체 보기
                    </Button>
                  </Box>
                </>
              ) : (
                <EmptyState
                  message="아직 생성한 원고가 없습니다"
                  action={
                    <ActionButton variant="primary" icon={<Create />} onClick={handleGeneratePost}>
                      첫 원고 만들기
                    </ActionButton>
                  }
                  py={3}
                />
              )}
            </Paper>
          </Box>
        ) : (
          /* PC - 반응형 레이아웃: 2K 이상에서 3컬럼, 이하에서 2컬럼 */
          <Grid container spacing={3}>
            {/* 좌측: 최근 생성한 글 */}
            <Grid item xs={12} md={6} xl={4}>
              <Paper elevation={0} sx={{ 
                height: 'fit-content', 
                bgcolor: 'transparent',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: 2,
                boxShadow: 'none'
              }}>
                <Box sx={{ p: `${spacing.lg}px`, borderBottom: '1px solid', borderColor: 'divider' }}>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    최근 생성한 글
                  </Typography>
                </Box>
                
                {recentPosts.length > 0 ? (
                  <List>
                    {recentPosts.slice(0, 5).map((post, index) => (
                      <React.Fragment key={post.id}>
                        <ListItem 
                          button 
                          onClick={() => handlePostClick(post.id)}
                        >
                          <ListItemText
                            primary={`${new Date(post.createdAt).toLocaleDateString('ko-KR', { month: 'long', day: 'numeric' })} ${post.title || '제목 없음'}`}
                            secondary={post.category || '일반'}
                          />
                          <ListItemSecondaryAction>
                            <IconButton edge="end" onClick={(e) => {
                              e.stopPropagation();
                            }}>
                              <MoreVert />
                            </IconButton>
                          </ListItemSecondaryAction>
                        </ListItem>
                        {index < Math.min(recentPosts.length, 5) - 1 && <Divider />}
                      </React.Fragment>
                    ))}
                  </List>
                ) : (
                  <EmptyState
                    message="아직 생성한 원고가 없습니다"
                    action={
                      <ActionButton variant="primary" icon={<Create />} onClick={handleGeneratePost}>
                        첫 원고 만들기
                      </ActionButton>
                    }
                    py={3}
                  />
                )}
              </Paper>
            </Grid>

            {/* 가운데: 공지사항 (2K 이상에서만 표시) */}
            <Grid 
              item 
              xl={4}
              sx={{ 
                display: { xs: 'none', xl: 'block' } // 2K 미만에서는 숨김
              }}
            >
              <Paper elevation={0} sx={{ 
                height: 'fit-content', 
                bgcolor: 'transparent',
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: 2,
                boxShadow: 'none'
              }}>
                <Box sx={{ p: `${spacing.md}px`, borderBottom: '1px solid', borderColor: 'divider' }}>
                  <Typography variant="h6" sx={{ fontWeight: 600, display: 'flex', alignItems: 'center' }}>
                    <Notifications sx={{ mr: `${spacing.xs}px`, color: 'colors.brand.primary' }} />
                    공지사항
                  </Typography>
                </Box>
                
                {notices.length === 0 ? (
                  <EmptyState
                    icon={Notifications}
                    message="현재 공지사항이 없습니다"
                    py={3}
                  />
                ) : (
                  <>
                    <List>
                      {notices.slice(0, 8).map((notice, index) => ( // 더 많은 공지사항 표시
                        <React.Fragment key={notice.id || index}>
                          <ListItem sx={{ alignItems: 'flex-start' }}>
                            <ListItemText
                              primary={
                                <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: `${spacing.xs}px` }}>
                                    <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                                      {notice.title || '제목 없음'}
                                    </Typography>
                                    {notice.priority === 'high' && (
                                      <Chip label="중요" color="error" size="small" />
                                    )}
                                  </Box>
                                  <Typography variant="caption" color="text.secondary">
                                    {notice.createdAt ? new Date(notice.createdAt).toLocaleDateString('ko-KR', { 
                                      month: 'short', 
                                      day: 'numeric' 
                                    }) : ''}
                                  </Typography>
                                </Box>
                              }
                              secondary={
                                <Typography 
                                  variant="body2" 
                                  color="text.secondary"
                                  sx={{
                                    mt: 0.5,
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    display: '-webkit-box',
                                    WebkitLineClamp: 2,
                                    WebkitBoxOrient: 'vertical'
                                  }}
                                >
                                  {notice.content || '내용 없음'}
                                </Typography>
                              }
                            />
                          </ListItem>
                          {index < Math.min(notices.length, 8) - 1 && <Divider />}
                        </React.Fragment>
                      ))}
                    </List>

                    {notices.length > 8 && (
                      <Box sx={{ p: `${spacing.md}px`, textAlign: 'center' }}>
                        <Button variant="text" size="small" sx={{ color: planColor }}>
                          더 보기 ({notices.length - 8}개 더)
                        </Button>
                      </Box>
                    )}
                  </>
                )}
              </Paper>
            </Grid>

            {/* 우측: 발행 진행률(상단) + 선거일정(하단), 2K 미만에서는 공지사항도 포함 */}
            <Grid item xs={12} md={6} xl={4}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: `${spacing.lg}px` }}>
                {/* 발행 진행률 카드 - 항상 상단에 */}
                <PublishingProgress />


                {/* 2K 미만에서만 표시되는 공지사항 */}
                <Box sx={{ display: { xs: 'block', xl: 'none' } }}>
                  <Paper elevation={0} sx={{ 
                    bgcolor: 'rgba(255, 255, 255, 0.03)',
                          border: '1px solid rgba(255, 255, 255, 0.05)',
                    borderRadius: 2
                  }}>
                    <Box sx={{ p: `${spacing.md}px`, borderBottom: '1px solid', borderColor: 'divider' }}>
                      <Typography variant="h6" sx={{ fontWeight: 600, display: 'flex', alignItems: 'center' }}>
                        <Notifications sx={{ mr: `${spacing.xs}px`, color: 'colors.brand.primary' }} />
                        공지사항
                      </Typography>
                    </Box>
                    
                    {notices.length === 0 ? (
                      <EmptyState
                        icon={Notifications}
                        message="현재 공지사항이 없습니다"
                        py={3}
                      />
                    ) : (
                      <>
                        <List>
                          {notices.slice(0, 5).map((notice, index) => (
                            <React.Fragment key={notice.id || index}>
                              <ListItem sx={{ alignItems: 'flex-start' }}>
                                <ListItemText
                                  primary={
                                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 0.5 }}>
                                      <Box sx={{ display: 'flex', alignItems: 'center', gap: `${spacing.xs}px` }}>
                                        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                                          {notice.title || '제목 없음'}
                                        </Typography>
                                        {notice.priority === 'high' && (
                                          <Chip label="중요" color="error" size="small" />
                                        )}
                                      </Box>
                                      <Typography variant="caption" color="text.secondary">
                                        {notice.createdAt ? new Date(notice.createdAt).toLocaleDateString('ko-KR', { 
                                          month: 'short', 
                                          day: 'numeric' 
                                        }) : ''}
                                      </Typography>
                                    </Box>
                                  }
                                  secondary={
                                    <Typography 
                                      variant="body2" 
                                      color="text.secondary"
                                      sx={{
                                        mt: 0.5,
                                        overflow: 'hidden',
                                        textOverflow: 'ellipsis',
                                        display: '-webkit-box',
                                        WebkitLineClamp: 2,
                                        WebkitBoxOrient: 'vertical'
                                      }}
                                    >
                                      {notice.content || '내용 없음'}
                                    </Typography>
                                  }
                                />
                              </ListItem>
                              {index < Math.min(notices.length, 5) - 1 && <Divider />}
                            </React.Fragment>
                          ))}
                        </List>

                        {notices.length > 5 && (
                          <Box sx={{ p: `${spacing.md}px`, textAlign: 'center' }}>
                            <Button variant="text" size="small" sx={{ color: planColor }}>
                              더 보기 ({notices.length - 5}개 더)
                            </Button>
                          </Box>
                        )}
                      </>
                    )}
                  </Paper>
                </Box>


              </Box>
            </Grid>
          </Grid>
        )}
      </Box>

      {/* 원고 보기 모달 */}
      <PostViewerModal
        open={viewerOpen}
        onClose={closeViewer}
        post={viewerPost}
        onDelete={handleDelete}
      />

      {/* 알림 스낵바 */}
      <NotificationSnackbar
        open={notification.open}
        onClose={hideNotification}
        message={notification.message}
        severity={notification.severity}
      />

      {/* 온보딩 환영 모달 */}
      <OnboardingWelcomeModal
        open={onboardingOpen}
        onClose={() => setOnboardingOpen(false)}
        userName={user?.name}
      />

    </DashboardLayout>
  );
};

export default Dashboard;
