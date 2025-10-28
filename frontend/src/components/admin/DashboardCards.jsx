// frontend/src/components/admin/DashboardCards.jsx
import React, { useState, useEffect } from 'react';
import {
  Box,
  Grid,
  CardContent,
  Typography,
  Alert,
  Button,
  IconButton,
  Tooltip,
  Chip
} from '@mui/material';
import { LoadingSkeleton } from '../loading';
import {
  Refresh,
  CheckCircle,
  Error,
  People,
  Api
} from '@mui/icons-material';
import { useAuth } from '../../hooks/useAuth';
import { getAdminStats, updateGeminiStatus } from '../../services/firebaseService';
import HongKongNeonCard from '../HongKongNeonCard';

// Gemini 상태 변경 함수
const handleGeminiStatusUpdate = async (newState) => {
  try {
    console.log('Update Gemini status:', newState);
    await updateGeminiStatus(newState);
    alert('상태가 업데이트되었습니다.');
    window.location.reload();
  } catch (error) {
    console.error('Gemini 상태 변경 실패:', error);
    alert('상태 변경 실패: ' + error.message);
  }
};

function DashboardCards() {
  const { user } = useAuth();
  const [stats, setStats] = useState({
    todaySuccess: 0,
    todayFail: 0,
    last30mErrors: 0,
    activeUsers: 0,
    geminiStatus: { state: 'unknown' }
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!user) {
      setLoading(true);
      return;
    }

    const fetchStats = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const result = await getAdminStats();
        
        console.log('신규 관리자 통계 조회 결과:', result);
        
        // 응답 구조에 따라 데이터 추출
        let statsData = {};
        
        if (result.success && result.data) {
          statsData = result.data;
        } else if (result.stats) {
          statsData = result.stats;
        } else {
          statsData = result;
        }
        
        setStats({
          todaySuccess: statsData.todaySuccess || 0,
          todayFail: statsData.todayFail || 0,
          last30mErrors: statsData.last30mErrors || 0,
          activeUsers: statsData.activeUsers || 0,
          geminiStatus: statsData.geminiStatus || { state: 'unknown' }
        });
      } catch (err) {
        console.error('통계 데이터 조회 실패:', err);
        setError(err.message);
        // 에러 시 기본값 사용
      } finally {
        setLoading(false);
      }
    };

    fetchStats();
    
    // 자동 새로고침 제거 - 1분마다 실행 최적화
    // const interval = setInterval(fetchStats, 30000);
    // return () => clearInterval(interval);
  }, [user]);

  const handleRefresh = async () => {
    console.log('수동 새로고침 시작');
    setLoading(true);
    setError(null);
    
    try {
      const result = await getAdminStats();
      
      console.log('수동 새로고침 결과:', result);
      
      // ?�답 구조???�라 ?�이??추출
      let statsData = {};
      
      if (result.success && result.data) {
        statsData = result.data;
      } else if (result.stats) {
        statsData = result.stats;
      } else {
        statsData = result;
      }
      
      setStats({
        todaySuccess: statsData.todaySuccess || 0,
        todayFail: statsData.todayFail || 0,
        last30mErrors: statsData.last30mErrors || 0,
        activeUsers: statsData.activeUsers || 0,
        geminiStatus: statsData.geminiStatus || { state: 'unknown' }
      });
    } catch (err) {
      console.error('새로고침 실패:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!user) {
    return (
      <Alert severity="warning">
        관리자 페이지는 로그인 후 사용 가능합니다.
      </Alert>
    );
  }

  if (user.role !== 'admin') {
    return (
      <Alert severity="error">
        관리자 권한이 필요합니다. 현재 권한: {user.role || 'user'}
      </Alert>
    );
  }

  if (loading) {
    return <LoadingSkeleton type="dashboard" count={4} />;
  }

  if (error) {
    return (
      <Alert 
        severity="error" 
        action={
          <Button color="inherit" size="small" onClick={handleRefresh}>
            다시 시도
          </Button>
        }
      >
        {error}
      </Alert>
    );
  }

  const totalToday = stats.todaySuccess + stats.todayFail;
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

  return (
    <Grid container spacing={3}>
      {/* 오늘 문서 생성 */}
      <Grid item xs={12} sm={6} md={3}>
        <HongKongNeonCard>
          <CardContent sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <Typography variant="h6" gutterBottom sx={{ color: 'black' }}>
                오늘 문서 생성
              </Typography>
              <Tooltip title="새로고침">
                <IconButton size="small" onClick={handleRefresh}>
                  <Refresh />
                </IconButton>
              </Tooltip>
            </Box>
            <Typography variant="h3" sx={{ mb: 1, color: 'black' }}>
              {totalToday}
            </Typography>
            <Box sx={{ display: 'flex', gap: 1 }}>
              <Chip 
                icon={<CheckCircle />} 
                label={`성공 ${stats.todaySuccess}`} 
                color="success" 
                size="small" 
              />
              <Chip 
                icon={<Error />} 
                label={`실패 ${stats.todayFail}`} 
                color="error" 
                size="small" 
              />
            </Box>
          </CardContent>
        </HongKongNeonCard>
      </Grid>

      {/* 활성 사용자 */}
      <Grid item xs={12} sm={6} md={3}>
        <HongKongNeonCard>
          <CardContent sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <People sx={{ color: 'black' }} />
              <Typography variant="h6" sx={{ color: 'black' }}>활성 사용자</Typography>
            </Box>
            <Typography variant="h3" sx={{ mb: 1, color: 'black' }}>
              {stats.activeUsers}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              최근 7일간 활동
            </Typography>
          </CardContent>
        </HongKongNeonCard>
      </Grid>

      {/* 최근 30분 에러 */}
      <Grid item xs={12} sm={6} md={3}>
        <HongKongNeonCard>
          <CardContent sx={{ p: 2 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <Error sx={{ color: stats.last30mErrors > 0 ? '#d22730' : 'black' }} />
              <Typography variant="h6" sx={{ color: 'black' }}>최근 30분 에러</Typography>
            </Box>
            <Typography variant="h3" sx={{ mb: 1, color: 'black' }}>
              {stats.last30mErrors}
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
              <Api sx={{ color: 'black' }} />
              <Typography variant="h6" sx={{ color: 'black' }}>Gemini API</Typography>
            </Box>
            <Box sx={{ mb: 2 }}>
              <Chip
                label={getGeminiStatusText(stats.geminiStatus.state)}
                color={getGeminiStatusColor(stats.geminiStatus.state)}
                sx={{ mb: 1 }}
              />
              {stats.geminiStatus.lastUpdated && (
                <Typography variant="caption" display="block" color="text.secondary">
                  업데이트: {new Date(stats.geminiStatus.lastUpdated).toLocaleString()}
                </Typography>
              )}
            </Box>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              <Button
                size="small"
                variant="contained"
                color="success"
                onClick={() => handleGeminiStatusUpdate('active')}
                disabled={stats.geminiStatus.state === 'active'}
                sx={{
                  '&:hover': {
                    transform: 'translateY(-1px)',
                    boxShadow: '0 3px 8px rgba(46, 125, 50, 0.3)'
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
                disabled={stats.geminiStatus.state === 'maintenance'}
                sx={{
                  '&:hover': {
                    transform: 'translateY(-1px)',
                    boxShadow: '0 3px 8px rgba(237, 108, 2, 0.3)'
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
                disabled={stats.geminiStatus.state === 'inactive'}
                sx={{
                  '&:hover': {
                    transform: 'translateY(-1px)',
                    boxShadow: '0 3px 8px rgba(211, 47, 47, 0.3)'
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
  );
}

export default DashboardCards;
