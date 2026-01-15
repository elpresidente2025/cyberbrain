// frontend/src/components/admin/DashboardCards.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box,
  Grid,
  CardContent,
  Typography,
  Alert,
  Button,
  IconButton,
  Tooltip,
  Chip,
  Snackbar
} from '@mui/material';
import { LoadingSkeleton } from '../loading';
import {
  Refresh,
  CheckCircle,
  Error as ErrorIcon,
  People,
  Api,
  TrendingUp
} from '@mui/icons-material';
import { useAuth } from '../../hooks/useAuth';
import { getAdminStats, updateGeminiStatus } from '../../services/firebaseService';
import HongKongNeonCard from '../HongKongNeonCard';
import ActiveUsersChartModal from './ActiveUsersChartModal';

function DashboardCards() {
  const { user } = useAuth();
  const [stats, setStats] = useState({
    todaySuccess: 0,
    todayFail: 0,
    last30mErrors: 0,
    activeUsers: 0,
    geminiStatus: { state: 'unknown', lastUpdated: null }
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notification, setNotification] = useState({ open: false, message: '', severity: 'info' });
  const [updatingGemini, setUpdatingGemini] = useState(false);
  const [chartModalOpen, setChartModalOpen] = useState(false);

  // cleanup을 위한 ref
  const isMountedRef = useRef(true);

  // 알림 표시 함수
  const showNotification = useCallback((message, severity = 'info') => {
    setNotification({ open: true, message, severity });
  }, []);

  // Gemini 상태 변경 함수 (컴포넌트 내부로 이동)
  const handleGeminiStatusUpdate = useCallback(async (newState) => {
    setUpdatingGemini(true);
    try {
      await updateGeminiStatus(newState);
      showNotification('API 상태가 업데이트되었습니다.', 'success');

      // 상태 새로고침
      if (isMountedRef.current) {
        setStats(prev => ({
          ...prev,
          geminiStatus: { state: newState, lastUpdated: new Date().toISOString() }
        }));
      }
    } catch (err) {
      console.error('Gemini 상태 변경 실패:', err);
      showNotification('상태 변경 실패: ' + err.message, 'error');
    } finally {
      if (isMountedRef.current) {
        setUpdatingGemini(false);
      }
    }
  }, [showNotification]);

  // 통계 데이터 가져오기 함수
  const fetchStats = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const result = await getAdminStats();

      // 응답 구조에 따라 데이터 추출
      let statsData = {};

      if (result.success && result.data) {
        statsData = result.data;
      } else if (result.stats) {
        statsData = result.stats;
      } else {
        statsData = result;
      }

      if (isMountedRef.current) {
        setStats({
          todaySuccess: statsData.todaySuccess || 0,
          todayFail: statsData.todayFail || 0,
          last30mErrors: statsData.last30mErrors || 0,
          activeUsers: statsData.activeUsers || 0,
          geminiStatus: {
            state: statsData.geminiStatus?.state || 'unknown',
            lastUpdated: statsData.geminiStatus?.lastUpdated || null
          }
        });
      }
    } catch (err) {
      console.error('통계 데이터 조회 실패:', err);
      if (isMountedRef.current) {
        setError(err.message);
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;

    if (!user) {
      setLoading(true);
      return;
    }

    fetchStats();

    // cleanup 함수
    return () => {
      isMountedRef.current = false;
    };
  }, [user, fetchStats]);

  // 수동 새로고침 핸들러
  const handleRefresh = useCallback(async () => {
    await fetchStats();
    showNotification('통계가 새로고침되었습니다.', 'success');
  }, [fetchStats, showNotification]);

  // 상태 색상 및 텍스트 헬퍼 함수
  const getGeminiStatusColor = (state) => {
    switch (state) {
      case 'active': return 'success';
      case 'inactive': return 'error';
      case 'maintenance': return 'warning';
      default: return 'default';
    }
  };

  const getGeminiStatusText = (state) => {
    switch (state) {
      case 'active': return '정상';
      case 'inactive': return '중단';
      case 'maintenance': return '점검';
      default: return '알 수 없음';
    }
  };

  const totalToday = stats.todaySuccess + stats.todayFail;

  // 로그인 필요
  if (!user) {
    return (
      <Alert severity="warning" role="alert" aria-live="polite">
        관리자 페이지는 로그인 후 사용 가능합니다.
      </Alert>
    );
  }

  // 권한 부족
  if (user.role !== 'admin') {
    return (
      <Alert severity="error" role="alert" aria-live="assertive">
        관리자 권한이 필요합니다. 현재 권한: {user.role || 'user'}
      </Alert>
    );
  }

  // 로딩 중
  if (loading) {
    return (
      <Box aria-busy="true" aria-label="대시보드 통계 로딩 중">
        <LoadingSkeleton type="dashboard" count={4} />
      </Box>
    );
  }

  // 에러 상태
  if (error) {
    return (
      <Alert
        severity="error"
        role="alert"
        aria-live="assertive"
        action={
          <Button
            color="inherit"
            size="small"
            onClick={handleRefresh}
            aria-label="통계 다시 불러오기"
          >
            다시 시도
          </Button>
        }
      >
        {error}
      </Alert>
    );
  }

  return (
    <>
      <Grid container spacing={3} role="region" aria-label="대시보드 통계">
        {/* 오늘 문서 생성 */}
        <Grid item xs={12} sm={6} md={3}>
          <HongKongNeonCard>
            <CardContent sx={{ p: 2 }}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <Typography
                  variant="h6"
                  component="h3"
                  id="doc-generation-title"
                  gutterBottom
                  sx={{ color: 'black' }}
                >
                  오늘 문서 생성
                </Typography>
                <Tooltip title="통계 새로고침">
                  <IconButton
                    size="small"
                    onClick={handleRefresh}
                    aria-label="통계 새로고침"
                    sx={{
                      '&:focus-visible': {
                        outline: '2px solid #006261',
                        outlineOffset: '2px'
                      }
                    }}
                  >
                    <Refresh aria-hidden="true" />
                  </IconButton>
                </Tooltip>
              </Box>
              <Typography
                variant="h3"
                sx={{ mb: 1, color: 'black' }}
                aria-describedby="doc-generation-title"
              >
                {totalToday}
              </Typography>
              <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }} role="group" aria-label="성공/실패 현황">
                <Chip
                  icon={<CheckCircle aria-hidden="true" />}
                  label={`성공 ${stats.todaySuccess}`}
                  color="success"
                  size="small"
                  aria-label={`성공 ${stats.todaySuccess}건`}
                />
                <Chip
                  icon={<ErrorIcon aria-hidden="true" />}
                  label={`실패 ${stats.todayFail}`}
                  color="error"
                  size="small"
                  aria-label={`실패 ${stats.todayFail}건`}
                />
              </Box>
            </CardContent>
          </HongKongNeonCard>
        </Grid>

        {/* 활성 사용자 */}
        <Grid item xs={12} sm={6} md={3}>
          <HongKongNeonCard
            sx={{
              cursor: 'pointer',
              transition: 'transform 0.2s, box-shadow 0.2s',
              '&:hover': {
                transform: 'translateY(-2px)',
                boxShadow: '0 4px 12px rgba(0, 98, 97, 0.2)'
              },
              '&:focus-visible': {
                outline: '2px solid #006261',
                outlineOffset: '2px'
              }
            }}
            onClick={() => setChartModalOpen(true)}
            tabIndex={0}
            role="button"
            aria-label="활성 사용자 추이 그래프 보기"
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setChartModalOpen(true);
              }
            }}
          >
            <CardContent sx={{ p: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <People sx={{ color: 'black' }} aria-hidden="true" />
                  <Typography variant="h6" component="h3" sx={{ color: 'black' }}>
                    활성 사용자
                  </Typography>
                </Box>
                <Tooltip title="추이 보기">
                  <span>
                    <TrendingUp sx={{ color: '#006261', fontSize: 20 }} aria-hidden="true" />
                  </span>
                </Tooltip>
              </Box>
              <Typography variant="h3" sx={{ mb: 1, color: 'black' }}>
                {stats.activeUsers}
                <Typography component="span" sx={{ fontSize: '0.5em', ml: 0.5 }}>명</Typography>
              </Typography>
              <Typography variant="body2" color="text.secondary">
                최근 7일간 활동 (클릭하여 상세 보기)
              </Typography>
            </CardContent>
          </HongKongNeonCard>
        </Grid>

        {/* 최근 30분 에러 */}
        <Grid item xs={12} sm={6} md={3}>
          <HongKongNeonCard>
            <CardContent sx={{ p: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <ErrorIcon
                  sx={{ color: stats.last30mErrors > 0 ? '#d22730' : 'black' }}
                  aria-hidden="true"
                />
                <Typography variant="h6" component="h3" sx={{ color: 'black' }}>
                  최근 30분 에러
                </Typography>
              </Box>
              <Typography
                variant="h3"
                sx={{ mb: 1, color: stats.last30mErrors > 0 ? '#d22730' : 'black' }}
                role={stats.last30mErrors > 0 ? 'alert' : undefined}
              >
                {stats.last30mErrors}
                <Typography component="span" sx={{ fontSize: '0.5em', ml: 0.5 }}>건</Typography>
              </Typography>
              <Typography variant="body2" color="text.secondary">
                시스템 상태 모니터링
              </Typography>
            </CardContent>
          </HongKongNeonCard>
        </Grid>

        {/* Gemini API 상태 */}
        <Grid item xs={12} sm={6} md={3}>
          <HongKongNeonCard>
            <CardContent sx={{ p: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <Api sx={{ color: 'black' }} aria-hidden="true" />
                <Typography variant="h6" component="h3" sx={{ color: 'black' }}>
                  Gemini API
                </Typography>
              </Box>
              <Box sx={{ mb: 2 }}>
                <Chip
                  label={getGeminiStatusText(stats.geminiStatus.state)}
                  color={getGeminiStatusColor(stats.geminiStatus.state)}
                  sx={{ mb: 1 }}
                  aria-label={`Gemini API 상태: ${getGeminiStatusText(stats.geminiStatus.state)}`}
                />
                {stats.geminiStatus.lastUpdated && (
                  <Typography variant="caption" display="block" color="text.secondary">
                    업데이트: {new Date(stats.geminiStatus.lastUpdated).toLocaleString('ko-KR')}
                  </Typography>
                )}
              </Box>
              <Box
                sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}
                role="group"
                aria-label="API 상태 변경"
              >
                <Button
                  size="small"
                  variant="contained"
                  color="success"
                  onClick={() => handleGeminiStatusUpdate('active')}
                  disabled={stats.geminiStatus.state === 'active' || updatingGemini}
                  aria-label="API 상태를 정상으로 변경"
                  sx={{
                    '&:hover': {
                      transform: 'translateY(-1px)',
                      boxShadow: '0 3px 8px rgba(46, 125, 50, 0.3)'
                    },
                    '&:focus-visible': {
                      outline: '2px solid #2e7d32',
                      outlineOffset: '2px'
                    }
                  }}
                >
                  정상
                </Button>
                <Button
                  size="small"
                  variant="contained"
                  color="warning"
                  onClick={() => handleGeminiStatusUpdate('maintenance')}
                  disabled={stats.geminiStatus.state === 'maintenance' || updatingGemini}
                  aria-label="API 상태를 점검으로 변경"
                  sx={{
                    '&:hover': {
                      transform: 'translateY(-1px)',
                      boxShadow: '0 3px 8px rgba(237, 108, 2, 0.3)'
                    },
                    '&:focus-visible': {
                      outline: '2px solid #ed6c02',
                      outlineOffset: '2px'
                    }
                  }}
                >
                  점검
                </Button>
                <Button
                  size="small"
                  variant="contained"
                  color="error"
                  onClick={() => handleGeminiStatusUpdate('inactive')}
                  disabled={stats.geminiStatus.state === 'inactive' || updatingGemini}
                  aria-label="API 상태를 중단으로 변경"
                  sx={{
                    '&:hover': {
                      transform: 'translateY(-1px)',
                      boxShadow: '0 3px 8px rgba(211, 47, 47, 0.3)'
                    },
                    '&:focus-visible': {
                      outline: '2px solid #d32f2f',
                      outlineOffset: '2px'
                    }
                  }}
                >
                  중단
                </Button>
              </Box>
            </CardContent>
          </HongKongNeonCard>
        </Grid>
      </Grid>

      {/* 알림 스낵바 */}
      <Snackbar
        open={notification.open}
        autoHideDuration={4000}
        onClose={() => setNotification(prev => ({ ...prev, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert
          onClose={() => setNotification(prev => ({ ...prev, open: false }))}
          severity={notification.severity}
          variant="filled"
          sx={{ width: '100%' }}
        >
          {notification.message}
        </Alert>
      </Snackbar>

      {/* 활성 사용자 차트 모달 */}
      <ActiveUsersChartModal
        open={chartModalOpen}
        onClose={() => setChartModalOpen(false)}
      />
    </>
  );
}

export default DashboardCards;
