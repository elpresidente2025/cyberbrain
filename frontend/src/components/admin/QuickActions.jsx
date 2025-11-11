// frontend/src/components/admin/QuickActions.jsx
import React, { useState } from 'react';
import {
  Typography,
  Grid,
  Button,
  Box,
  Switch,
  FormControlLabel,
  Alert,
  useTheme
} from '@mui/material';
import {
  Settings,
  Download,
  People,
  Api,
  ToggleOn
} from '@mui/icons-material';
import UserListModal from './UserListModal';
import StatusUpdateModal from './StatusUpdateModal';
import HongKongNeonCard from '../HongKongNeonCard';
import { getAdminStats, callFunctionWithRetry } from '../../services/firebaseService';

function QuickActions() {
  const theme = useTheme();
  const [userListOpen, setUserListOpen] = useState(false);
  const [statusUpdateOpen, setStatusUpdateOpen] = useState(false);
  const [serviceMode, setServiceMode] = useState(null); // null: loading, true: test, false: production
  const [loadingToggle, setLoadingToggle] = useState(false);

  // 시스템 설정 로드
  React.useEffect(() => {
    const loadServiceMode = async () => {
      try {
        const result = await callFunctionWithRetry('getSystemConfig');
        if (result?.config) {
          setServiceMode(result.config.testMode || false);
        }
      } catch (error) {
        console.error('시스템 설정 로드 실패:', error);
        setServiceMode(false); // 기본값: 프로덕션 모드
      }
    };
    loadServiceMode();
  }, []);

  const exportAllData = async () => {
    try {
      console.log('📊 전체 데이터 CSV 내보내기 시작...');
      
      // 모든 데이터를 가져와서 CSV로 변환
      const [usersResult, errorsResult, statsResult] = await Promise.all([
        callFunctionWithRetry('getUsers'),
        callFunctionWithRetry('getErrors', { limit: 1000 }),
        getAdminStats()
      ]);

      // CSV 생성 함수
      const createCsv = (data, filename) => {
        if (!data || data.length === 0) return;
        
        const headers = Object.keys(data[0]);
        const csvContent = [
          headers.join(','),
          ...data.map(row => 
            headers.map(header => {
              const value = row[header];
              if (value === null || value === undefined) return '';
              if (typeof value === 'object') return JSON.stringify(value).replace(/"/g, '""');
              return String(value).replace(/"/g, '""');
            }).map(v => `"${v}"`).join(',')
          )
        ].join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${filename}_${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      };

      // 각각 CSV로 내보내기
      if (usersResult?.users) {
        createCsv(usersResult.users, 'users');
      }
      
      if (errorsResult?.errors) {
        createCsv(errorsResult.errors, 'errors');
      }

      // 통계 데이터도 CSV로
      if (statsResult?.stats) {
        createCsv([{
          date: new Date().toISOString(),
          ...statsResult.stats
        }], 'stats');
      }

      alert('✅ CSV 파일들이 다운로드되었습니다.');
      
    } catch (error) {
      console.error('❌ CSV 내보내기 실패:', error);
      alert('❌ CSV 내보내기 실패: ' + error.message);
    }
  };

  const clearCache = async () => {
    if (!confirm('정말로 캐시를 비우시겠습니까?')) return;
    
    try {
      await callFunctionWithRetry('clearSystemCache');
      alert('✅ 캐시가 성공적으로 비워졌습니다.');
      window.location.reload();
    } catch (error) {
      console.error('❌ 캐시 비우기 실패:', error);
      alert('❌ 캐시 비우기 실패: ' + error.message);
    }
  };

  const toggleServiceMode = async () => {
    const newMode = !serviceMode;
    const modeText = newMode ? '데모 모드' : '프로덕션 모드';

    const confirmed = confirm(
      `정말로 ${modeText}로 전환하시겠습니까?\n\n` +
      (newMode
        ? '• 모든 사용자에게 월 8회 무료 제공\n• 구독 및 당원 인증 불필요\n• 대시보드에 "데모 모드" 배지 표시'
        : '• 즉시 유료 결제 + 당원 인증 필수\n• 사용자는 8회 무료 체험 후 결제 필요')
    );

    if (!confirmed) return;

    setLoadingToggle(true);
    try {
      await callFunctionWithRetry('updateSystemConfig', {
        testMode: newMode
      });

      setServiceMode(newMode);
      alert(`✅ ${modeText}로 전환되었습니다.`);

      // 페이지 새로고침하여 모든 컴포넌트에 반영
      setTimeout(() => window.location.reload(), 1000);
    } catch (error) {
      console.error('서비스 모드 전환 실패:', error);
      alert('❌ 서비스 모드 전환 실패: ' + error.message);
    } finally {
      setLoadingToggle(false);
    }
  };

  return (
    <>
      <HongKongNeonCard sx={{ p: 3, mb: 3 }}>
        <Typography variant="h6" gutterBottom sx={{ color: theme.palette.ui?.header || '#152484', fontWeight: 600 }}>
          빠른 작업 (Quick Actions)
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          자주 사용하는 관리 기능들을 빠르게 실행할 수 있습니다.
        </Typography>
        
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6} md={4}>
            <Button
              fullWidth
              variant="contained"
              startIcon={<People />}
              onClick={() => setUserListOpen(true)}
              sx={{ 
                py: 2,
                bgcolor: theme.palette.ui?.header || '#152484',
                color: 'white',
                '&:hover': {
                  bgcolor: '#1e2d9f',
                  transform: 'translateY(-2px)',
                  boxShadow: '0 6px 16px rgba(21, 36, 132, 0.3)'
                }
              }}
            >
              사용자 목록
            </Button>
          </Grid>
          
          <Grid item xs={12} sm={6} md={4}>
            <Button
              fullWidth
              variant="contained"
              startIcon={<Api />}
              onClick={() => setStatusUpdateOpen(true)}
              sx={{ 
                py: 2,
                bgcolor: '#006261',
                color: 'white',
                '&:hover': {
                  bgcolor: '#007a74',
                  transform: 'translateY(-2px)',
                  boxShadow: '0 6px 16px rgba(0, 98, 97, 0.3)'
                }
              }}
            >
              상태 수정
            </Button>
          </Grid>
          
          <Grid item xs={12} sm={6} md={4}>
            <Button
              fullWidth
              variant="contained"
              startIcon={<Download />}
              onClick={exportAllData}
              sx={{ 
                py: 2,
                bgcolor: '#55207D',
                color: 'white',
                '&:hover': {
                  bgcolor: '#6d2b93',
                  transform: 'translateY(-2px)',
                  boxShadow: '0 6px 16px rgba(85, 32, 125, 0.3)'
                }
              }}
            >
              CSV 다운로드
            </Button>
          </Grid>

          <Grid item xs={12} sm={6} md={4}>
            <Button
              fullWidth
              variant={serviceMode ? "contained" : "outlined"}
              startIcon={<ToggleOn />}
              onClick={toggleServiceMode}
              disabled={loadingToggle || serviceMode === null}
              sx={{
                py: 2,
                borderColor: serviceMode ? '#006261' : '#d22730',
                color: serviceMode ? 'white' : '#d22730',
                backgroundColor: serviceMode ? '#006261' : 'transparent',
                '&:hover': {
                  borderColor: serviceMode ? '#006261' : '#d22730',
                  backgroundColor: serviceMode ? '#007a74' : 'rgba(210, 39, 48, 0.04)'
                },
                '&.Mui-disabled': {
                  opacity: 0.6
                }
              }}
            >
              {serviceMode === null ? '로딩 중...' : (serviceMode ? '🧪 데모 모드' : '💼 프로덕션 모드')}
            </Button>
          </Grid>
        </Grid>

        {/* 서비스 모드 상태 표시 */}
        {serviceMode !== null && (
          <Alert severity={serviceMode ? "info" : "success"} sx={{ mt: 2 }}>
            <Typography variant="body2">
              {serviceMode ? (
                <>
                  🧪 <strong>데모 모드</strong>
                  <br />
                  • 모든 사용자에게 월 8회 무료 제공
                  <br />
                  • 구독 및 당원 인증 불필요
                </>
              ) : (
                <>
                  💼 <strong>프로덕션 모드</strong>
                  <br />
                  • 유료 구독 + 당원 인증 필수
                  <br />
                  • 무료 체험 8회 제공 후 결제 필요
                </>
              )}
            </Typography>
          </Alert>
        )}

        {/* 추가 관리 도구 */}
        <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid #e0e0e0' }}>
          <Typography variant="subtitle2" color="text.secondary" gutterBottom>
            시스템 관리
          </Typography>
          <Grid container spacing={1}>
            <Grid item>
              <Button
                size="small"
                variant="text"
                onClick={clearCache}
                sx={{ color: '#55207D' }}
              >
                캐시 비우기
              </Button>
            </Grid>
          </Grid>
        </Box>
      </HongKongNeonCard>

      {/* 모달들 */}
      <UserListModal 
        open={userListOpen} 
        onClose={() => setUserListOpen(false)} 
      />
      <StatusUpdateModal 
        open={statusUpdateOpen} 
        onClose={() => setStatusUpdateOpen(false)} 
      />
    </>
  );
}

export default QuickActions;