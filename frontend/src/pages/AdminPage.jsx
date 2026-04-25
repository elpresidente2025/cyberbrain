// frontend/src/pages/AdminPage.jsx
import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Container,
  Typography,
  Box,
  Button,
  Alert,
  Paper,
  useTheme,
  Grid
} from '@mui/material';
import { Speed, Visibility, AutoStories } from '@mui/icons-material';
import DashboardLayout from '../components/DashboardLayout';
import { colors, spacing } from '../theme/tokens';
import DashboardCards from '../components/admin/DashboardCards';
import QuickActions from '../components/admin/QuickActions';
import ErrorsMiniTable from '../components/admin/ErrorsMiniTable';
import NoticeManager from '../components/admin/NoticeManager';
import PerformanceMonitor from '../components/admin/PerformanceMonitor';
import UserManagement from '../components/admin/UserManagement';
import LeadershipManager from '../components/admin/LeadershipManager';
import SystemSettings from '../components/admin/SystemSettings';
import { useAuth } from '../hooks/useAuth';
import { hasAdminAccess } from '../utils/authz';
import { NotificationSnackbar, useNotification } from '../components/ui';

// 섹션 제목 컴포넌트 (접근성 개선)
const SectionHeading = ({ id, children }) => (
  <Typography
    id={id}
    variant="srOnly"
    component="h2"
    sx={{
      position: 'absolute',
      width: 1,
      height: 1,
      padding: 0,
      margin: -1,
      overflow: 'hidden',
      clip: 'rect(0, 0, 0, 0)',
      whiteSpace: 'nowrap',
      border: 0
    }}
  >
    {children}
  </Typography>
);

function AdminPage() {
  const { user } = useAuth();
  const isAdmin = hasAdminAccess(user);
  const theme = useTheme();
  const navigate = useNavigate();
  const { notification, showNotification, hideNotification } = useNotification();
  const [performanceMonitorOpen, setPerformanceMonitorOpen] = useState(false);
  const [leadershipOpen, setLeadershipOpen] = useState(false);

  // 성능 모니터 열기/닫기 핸들러 (메모이제이션)
  const handleOpenPerformanceMonitor = useCallback(() => {
    setPerformanceMonitorOpen(true);
  }, []);

  const handleClosePerformanceMonitor = useCallback(() => {
    setPerformanceMonitorOpen(false);
  }, []);

  const handlePreviewOnboarding = useCallback(() => {
    navigate('/onboarding?preview=1');
  }, [navigate]);

  // 권한 체크
  if (!user) {
    return (
      <DashboardLayout title="관리자 페이지">
        <Container maxWidth="xl" role="main" aria-labelledby="admin-page-title">
          <Alert
            severity="warning"
            role="alert"
            aria-live="polite"
          >
            관리자 페이지는 로그인 후 사용 가능합니다.
          </Alert>
        </Container>
      </DashboardLayout>
    );
  }

  if (!isAdmin) {
    return (
      <DashboardLayout title="관리자 페이지">
        <Container maxWidth="xl" role="main" aria-labelledby="admin-page-title">
          <Alert
            severity="error"
            role="alert"
            aria-live="assertive"
          >
            <Typography variant="h6" component="p" gutterBottom>접근 권한이 없습니다</Typography>
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
      <Container
        maxWidth="xl"
        component="main"
        role="main"
        aria-labelledby="admin-page-title"
      >
        {/* 헤더 영역 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <Box
            component="header"
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', md: 'row' },
              justifyContent: 'space-between',
              alignItems: { xs: 'flex-start', md: 'center' },
              gap: 2,
              mb: `${spacing.xl}px`,
              pb: `${spacing.md}px`,
              borderBottom: `2px solid ${theme.palette.ui?.header || colors.brand.primary}`
            }}
          >
            <Box>
              <Typography
                id="admin-page-title"
                variant="h4"
                component="h1"
                sx={{
                  color: theme.palette.mode === 'dark' ? '#ffffff' : '#000000',
                  fontWeight: 700,
                  mb: `${spacing.xs}px`
                }}
              >
                시스템 관리
              </Typography>
              <Typography
                variant="body1"
                sx={{ color: theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.6)' }}
              >
                전자두뇌비서관 서비스의 전반적인 상태를 모니터링하고 관리합니다.
              </Typography>
            </Box>

            <Box sx={{ display: 'flex', gap: `${spacing.md}px`, flexShrink: 0, flexWrap: 'wrap' }}>
              <Button
                variant="outlined"
                startIcon={<Visibility aria-hidden="true" />}
                onClick={handlePreviewOnboarding}
                aria-label="온보딩 미리보기 열기"
                sx={{
                  borderColor: colors.brand.primary,
                  color: colors.brand.primary,
                  '&:hover': {
                    borderColor: '#007a74',
                    bgcolor: 'rgba(0, 98, 97, 0.08)',
                    transform: 'translateY(-1px)'
                  },
                  '&:focus-visible': {
                    outline: '2px solid #006261',
                    outlineOffset: '2px'
                  }
                }}
              >
                온보딩 미리보기
              </Button>
              <Button
                variant="contained"
                startIcon={<Speed aria-hidden="true" />}
                onClick={handleOpenPerformanceMonitor}
                aria-label="성능 모니터 열기"
                sx={{
                  bgcolor: colors.brand.primary,
                  color: 'white',
                  '&:hover': {
                    bgcolor: '#007a74',
                    transform: 'translateY(-1px)',
                    boxShadow: '0 4px 12px rgba(0, 98, 97, 0.3)'
                  },
                  '&:focus-visible': {
                    outline: '2px solid #006261',
                    outlineOffset: '2px'
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
          <Box
            component="section"
            aria-labelledby="dashboard-cards-section"
            sx={{ mb: `${spacing.xl}px` }}
          >
            <SectionHeading id="dashboard-cards-section">대시보드 통계</SectionHeading>
            <DashboardCards />
          </Box>
        </motion.div>

        {/* 시스템 설정 영역 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
        >
          <Box
            component="section"
            aria-labelledby="system-settings-section"
            sx={{ mb: `${spacing.xl}px` }}
          >
            <SectionHeading id="system-settings-section">시스템 설정</SectionHeading>
            <SystemSettings />
          </Box>
        </motion.div>

        {/* 빠른 작업 & 에러 로그 영역 (2열 배치) */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          <Grid
            container
            spacing={3}
            sx={{ mb: `${spacing.xl}px` }}
          >
            <Grid item xs={12} md={6}>
              <Box component="section" aria-labelledby="quick-actions-section">
                <SectionHeading id="quick-actions-section">빠른 작업</SectionHeading>
                <QuickActions />
              </Box>
            </Grid>
            <Grid item xs={12} md={6}>
              <Box component="section" aria-labelledby="errors-section">
                <SectionHeading id="errors-section">에러 로그</SectionHeading>
                <ErrorsMiniTable />
              </Box>
            </Grid>
          </Grid>
        </motion.div>

        {/* 공지사항 관리 영역 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.5 }}
        >
          <Box
            component="section"
            aria-labelledby="notice-section"
            sx={{ mb: `${spacing.xl}px` }}
          >
            <SectionHeading id="notice-section">공지사항 관리</SectionHeading>
            <NoticeManager />
          </Box>
        </motion.div>

        {/* 리더십 철학 관리 영역 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.6 }}
        >
          <Box
            component="section"
            aria-labelledby="leadership-section"
            sx={{ mb: `${spacing.xl}px` }}
          >
            <SectionHeading id="leadership-section">리더십 철학 관리</SectionHeading>
            <Paper
              elevation={0}
              sx={{
                p: { xs: 2, sm: 3 },
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 2,
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <AutoStories sx={{ color: colors.brand.primary, fontSize: 26 }} />
                <Box>
                  <Typography
                    variant="subtitle1"
                    sx={{ fontWeight: 700, color: colors.brand.primary, lineHeight: 1.3 }}
                  >
                    리더십 철학 관리
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
                    leadership.py 섹션별 오버레이 편집 — 저장된 값이 Python 원본을 덮어씁니다.
                  </Typography>
                </Box>
              </Box>
              <Button
                variant="outlined"
                startIcon={<AutoStories />}
                onClick={() => setLeadershipOpen(true)}
                aria-label="리더십 철학 관리 편집 열기"
                sx={{
                  borderColor: 'rgba(21, 36, 132, 0.4)',
                  color: colors.brand.primary,
                  '&:hover': {
                    borderColor: colors.brand.primary,
                    bgcolor: 'rgba(21, 36, 132, 0.05)',
                  },
                }}
              >
                편집 열기
              </Button>
            </Paper>
            <LeadershipManager
              open={leadershipOpen}
              onClose={() => setLeadershipOpen(false)}
            />
          </Box>
        </motion.div>

        {/* 사용자 관리 영역 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.7 }}
        >
          <Box
            component="section"
            aria-labelledby="user-management-section"
            sx={{ mb: `${spacing.xl}px` }}
          >
            <SectionHeading id="user-management-section">사용자 관리</SectionHeading>
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
        onClose={handleClosePerformanceMonitor}
      />
    </DashboardLayout>
  );
}

export default AdminPage;
