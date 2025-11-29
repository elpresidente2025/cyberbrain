// frontend/src/pages/AdminPage.jsx (단순화 버전)
import React, { useState } from 'react';
import { motion } from 'framer-motion';
import {
  Container,
  Typography,
  Box,
  Button,
  Alert,
  useTheme,
  Grid
} from '@mui/material';
import { Speed } from '@mui/icons-material';
import DashboardLayout from '../components/DashboardLayout';
import { colors, spacing, typography, visualWeight, verticalRhythm } from '../theme/tokens';
import DashboardCards from '../components/admin/DashboardCards';
import QuickActions from '../components/admin/QuickActions';
import ErrorsMiniTable from '../components/admin/ErrorsMiniTable';
import NoticeManager from '../components/admin/NoticeManager';
import PerformanceMonitor from '../components/admin/PerformanceMonitor';
import UserManagement from '../components/admin/UserManagement';
import SystemSettings from '../components/admin/SystemSettings';
import { useAuth } from '../hooks/useAuth';
import { PageHeader, NotificationSnackbar, useNotification } from '../components/ui';

function AdminPage() {
  const { user } = useAuth();
  const theme = useTheme();
  const { notification, showNotification, hideNotification } = useNotification();
  const [performanceMonitorOpen, setPerformanceMonitorOpen] = useState(false);

  // 권한 체크
  if (!user) {
    return (
      <DashboardLayout title="관리자 페이지">
        <Container maxWidth="xl">
          <Alert severity="warning">
            관리자 페이지는 로그인 후 사용 가능합니다.
          </Alert>
        </Container>
      </DashboardLayout>
    );
  }

  if (user.role !== 'admin') {
    return (
      <DashboardLayout title="관리자 페이지">
        <Container maxWidth="xl">
          <Alert severity="error">
            <Typography variant="h6" gutterBottom>접근 권한이 없습니다</Typography>
            <Typography variant="body2">
              이 페이지는 관리자만 접근할 수 있습니다.
              현재 권한: {user.role || '일반 사용자'}
            </Typography>
          </Alert>
        </Container>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="시스템 관리">
      <Container maxWidth="xl">
        {/* 헤더 영역 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <Box sx={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            mb: `${spacing.xl}px`,
            pb: `${spacing.md}px`,
            borderBottom: `2px solid ${theme.palette.ui?.header || colors.brand.primary}`
          }}>
          <Box>
            <Typography
              variant="h4"
              sx={{
                color: theme.palette.mode === 'dark' ? '#ffffff' : '#000000',
                fontWeight: 700,
                mb: `${spacing.xs}px`
              }}
            >
              시스템 관리
            </Typography>
            <Typography variant="body1" sx={{ color: theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.6)' }}>
              전자두뇌비서관 서비스의 전반적인 상태를 모니터링하고 관리합니다.
            </Typography>
          </Box>
          
          <Box sx={{ display: 'flex', gap: `${spacing.md}px` }}>
            <Button
              variant="contained"
              startIcon={<Speed />}
              onClick={() => setPerformanceMonitorOpen(true)}
              sx={{ 
                bgcolor: colors.brand.primary,
                color: 'white',
                '&:hover': { 
                  bgcolor: '#007a74',
                  transform: 'translateY(-1px)',
                  boxShadow: '0 4px 12px rgba(0, 98, 97, 0.3)'
                }
              }}
            >
              성능 모니터
            </Button>
          </Box>
        </Box>
        </motion.div>

        {/* 대시보드 카드 영역 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.2 }}
        >
          <Box sx={{ mb: `${spacing.xl}px` }}>
          <DashboardCards />
        </Box>
        </motion.div>

        {/* 시스템 설정 영역 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
        >
          <Box sx={{ mb: `${spacing.xl}px` }}>
          <SystemSettings />
        </Box>
        </motion.div>

        {/* 빠른 작업 & 에러 로그 영역 (2열 배치) */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          <Grid container spacing={3} sx={{ mb: `${spacing.xl}px` }}>
          <Grid item xs={12} md={6}>
            <QuickActions />
          </Grid>
          <Grid item xs={12} md={6}>
            <ErrorsMiniTable />
          </Grid>
        </Grid>
        </motion.div>

        {/* 공지사항 관리 영역 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.5 }}
        >
          <Box sx={{ mb: `${spacing.xl}px` }}>
          <NoticeManager />
        </Box>
        </motion.div>

        {/* 사용자 관리 영역 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.6 }}
        >
          <Box sx={{ mb: `${spacing.xl}px` }}>
          <UserManagement />
        </Box>
        </motion.div>

      </Container>

      {/* 알림 스낵바 */}
      <NotificationSnackbar
        open={notification.open}
        onClose={hideNotification}
        message={notification.message}
        severity={notification.severity}
        autoHideDuration={6000}
      />

      {/* 성능 모니터 다이얼로그 */}
      <PerformanceMonitor
        open={performanceMonitorOpen}
        onClose={() => setPerformanceMonitorOpen(false)}
      />
    </DashboardLayout>
  );
}

export default AdminPage;