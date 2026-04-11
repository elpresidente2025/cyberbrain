// frontend/src/components/MaintenancePage.jsx
import React from 'react';
import {
  Box,
  Container,
  Typography,
  Paper,
  Alert,
  Button,
  Divider,
  Chip,
  CircularProgress,
  useTheme
} from '@mui/material';
import {
  Warning,
  Schedule,
  ContactSupport,
  Refresh,
  AdminPanelSettings,
  Logout
} from '@mui/icons-material';
import { BRANDING } from '../config/branding';

function MaintenancePage({ maintenanceInfo, onRetry, isAdmin, onLogout }) {
  const theme = useTheme();
  console.log('🔧 MaintenancePage props:', { 
    hasOnLogout: !!onLogout, 
    isAdmin, 
    maintenanceInfo 
  });
  
  const {
    title = '시스템 점검 안내',
    message = '',
    estimatedEndTime = '',
    contactInfo = '문의사항이 있으시면 고객센터로 연락해 주세요.',
    allowAdminAccess = false
  } = maintenanceInfo || {};

  const formatDateTime = (dateTimeString) => {
    if (!dateTimeString) return null;
    try {
      return new Date(dateTimeString).toLocaleString('ko-KR');
    } catch {
      return dateTimeString;
    }
  };

  return (
    <Box
      sx={{
        minHeight: '100vh',
        backgroundColor: '#f5f5f5',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 2
      }}
    >
      <Container maxWidth="md">
        <Paper
          elevation={8}
          sx={{
            padding: { xs: 3, md: 5 },
            borderRadius: 1,
            textAlign: 'center',
            position: 'relative'
          }}
        >
          {/* 상태 표시 */}
          <Box sx={{ mb: 3 }}>
            <Chip
              icon={<Warning />}
              label="점검 중"
              color="warning"
              size="large"
              sx={{ fontSize: '1rem', px: 2, py: 1 }}
            />
          </Box>

          {/* 제목 */}
          <Typography 
            variant="h3" 
            component="h1" 
            gutterBottom
            sx={{ 
              fontWeight: 700,
              color: theme.palette.ui?.header || '#152484',
              mb: 3,
              fontSize: { xs: '2rem', md: '3rem' }
            }}
          >
            {title}
          </Typography>

          {/* 메시지 */}
          {message && (
            <Box sx={{ mb: 4 }}>
              <Typography 
                variant="h6" 
                color="text.secondary"
                sx={{ 
                  lineHeight: 1.8,
                  whiteSpace: 'pre-line',
                  maxWidth: '600px',
                  margin: '0 auto'
                }}
              >
                {message}
              </Typography>
            </Box>
          )}

          <Divider sx={{ my: 4 }} />

          {/* 예상 복구 시간 */}
          {estimatedEndTime && (
            <Alert 
              severity="info" 
              icon={<Schedule />}
              sx={{ mb: 3, textAlign: 'left' }}
            >
              <Typography variant="body1" sx={{ fontWeight: 600 }}>
                예상 복구 시간: {formatDateTime(estimatedEndTime)}
              </Typography>
            </Alert>
          )}

          {/* 문의 안내 */}
          {contactInfo && (
            <Alert 
              severity="info" 
              icon={<ContactSupport />}
              sx={{ mb: 4, textAlign: 'left' }}
            >
              <Typography variant="body1">
                {contactInfo}
              </Typography>
            </Alert>
          )}

          {/* 관리자 접근 버튼 */}
          {isAdmin && allowAdminAccess && (
            <Box sx={{ mb: 3 }}>
              <Button
                variant="contained"
                startIcon={<AdminPanelSettings />}
                onClick={() => window.location.href = '/admin'}
                sx={{
                  backgroundColor: theme.palette.ui?.header || '#152484',
                  '&:hover': { backgroundColor: '#003A87' },
                  mr: 2
                }}
              >
                관리자 페이지로 이동
              </Button>
            </Box>
          )}

          {/* 액션 버튼들 */}
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', justifyContent: 'center' }}>
            <Button
              variant="outlined"
              startIcon={<Refresh />}
              onClick={onRetry}
              size="large"
              sx={{
                borderColor: theme.palette.ui?.header || '#152484',
                color: theme.palette.ui?.header || '#152484',
                '&:hover': {
                  borderColor: '#003A87',
                  backgroundColor: 'rgba(21, 36, 132, 0.1)'
                }
              }}
            >
              상태 다시 확인
            </Button>

            {/* 로그아웃 버튼 */}
            {onLogout && (
              <Button
                variant="outlined"
                startIcon={<Logout />}
                onClick={onLogout}
                size="large"
                color="secondary"
                sx={{
                  borderColor: '#55207D',
                  color: '#55207D',
                  '&:hover': {
                    borderColor: theme.palette.ui?.header || '#152484',
                    backgroundColor: 'rgba(85, 32, 125, 0.1)'
                  }
                }}
              >
                로그아웃
              </Button>
            )}
          </Box>

          {/* 로딩 애니메이션 */}
          <Box sx={{ mt: 4, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 2 }}>
            <CircularProgress size={20} sx={{ color: theme.palette.ui?.header || '#152484' }} />
            <Typography variant="body2" color="text.secondary">
              시스템 복구 작업을 진행하고 있습니다...
            </Typography>
          </Box>

          {/* 푸터 */}
          <Box sx={{ mt: 5, pt: 3, borderTop: '1px solid', borderColor: 'divider' }}>
            <Typography variant="body2" color="text.secondary">
              {BRANDING.serviceName} • 서비스 일시 중단
            </Typography>
          </Box>
        </Paper>
      </Container>
    </Box>
  );
}

export default MaintenancePage;
