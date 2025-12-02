// frontend/src/App.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Box, useTheme } from '@mui/material';
import { motion, AnimatePresence } from 'framer-motion';
import { useAuth } from './hooks/useAuth';
import { getSystemStatus } from './services/firebaseService';
import MaintenancePage from './components/MaintenancePage';
import { LoadingOverlay } from './components/loading';
import { HelpProvider } from './contexts/HelpContext';
import { ColorProvider } from './contexts/ColorContext';

function App() {
  const { user, loading, logout } = useAuth();
  const theme = useTheme();
  const [systemStatus, setSystemStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const location = useLocation();
  const isDarkMode = theme.palette.mode === 'dark';

  // 시스템 상태 확인 (타임아웃 10초)
  const checkSystemStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      // 10초 타임아웃 설정 (Firebase Functions 응답 시간 고려)
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('timeout')), 10000)
      );

      const status = await Promise.race([
        getSystemStatus(),
        timeoutPromise
      ]);

      setSystemStatus(status);

      // ✅ 캐시에 상태와 타임스탬프 함께 저장 (점검 중 새로고침 시 우회 방지)
      sessionStorage.setItem('systemStatusCache', JSON.stringify({
        timestamp: Date.now(),
        status: status.status,
        maintenanceInfo: status.maintenanceInfo || null
      }));
    } catch (error) {
      console.error('시스템 상태 확인 실패:', error);
      setSystemStatus({ status: 'active' }); // 실패 시 정상 상태로 간주
    } finally {
      setStatusLoading(false);
    }
  }, []);

  // 관리자 계정 확인 (useEffect보다 먼저 선언)
  const isAdmin = user?.email === 'kjk6206@gmail.com' || user?.email === 'taesoo@secretart.ai';

  useEffect(() => {
    // 로그인 상태가 확정된 후에만 시스템 상태 확인 (최초 1회만)
    if (!loading && systemStatus === null) {
      // ✅ 페이지 새로고침 시 불필요한 재확인 방지 (캐시 활용)
      const cacheStr = sessionStorage.getItem('systemStatusCache');
      if (cacheStr) {
        try {
          const cache = JSON.parse(cacheStr);
          const now = Date.now();

          // 5분 이내 캐시된 상태가 있으면 사용 (단, 실제 status 값 사용)
          if (cache.timestamp && (now - cache.timestamp) < 300000) {
            console.log('✅ 캐시된 시스템 상태 사용:', cache.status);
            setSystemStatus({
              status: cache.status || 'active',
              maintenanceInfo: cache.maintenanceInfo || null,
              timestamp: new Date(cache.timestamp).toISOString()
            });
            setStatusLoading(false);
            return;
          }
        } catch (e) {
          console.warn('캐시 파싱 실패:', e);
        }
      }

      // 캐시가 없거나 만료되었으면 새로 확인
      checkSystemStatus();
    }
  }, [loading, checkSystemStatus, systemStatus]);

  // 점검 모드일 때만 주기적으로 상태 확인 (복구 감지)
  useEffect(() => {
    let interval = null;

    if (systemStatus?.status === 'maintenance' && !isAdmin) {
      // 점검 중일 때만 2분마다 복구 확인
      console.log('🔧 점검 모드: 2분마다 복구 상태 확인 시작');
      interval = setInterval(checkSystemStatus, 120000);
    }

    return () => {
      if (interval) {
        console.log('🔧 상태 확인 간격 정리');
        clearInterval(interval);
      }
    };
  }, [systemStatus?.status, isAdmin, checkSystemStatus]);

  // 점검 중이고 일반 사용자인 경우에 점검 페이지 표시
  const shouldShowMaintenance = () => {
    if (!systemStatus || systemStatus.status !== 'maintenance') {
      return false;
    }

    // 로그아웃 상태에서도 로그인 페이지 접근 허용
    const publicGuestPaths = ['/', '/login', '/about'];
    if (!user && publicGuestPaths.some((p) => location.pathname === p || location.pathname.startsWith(p + '/'))) {
      return false;
    }

    // 관리자는 모든 접근 허용 (점검 해제를 위해)
    if (isAdmin) {
      return false;
    }

    // 로그인된 일반 사용자는 모든 페이지에서 점검 페이지 표시
    if (user && !isAdmin) {
      return true;
    }

    return false;
  };

  // 로딩 화면 표시
  // 인증 로딩 중에만 로딩 화면 표시 (시스템 상태 확인은 백그라운드에서)
  if (loading) {
    return (
      <Box sx={{
        height: '100vh',
        bgcolor: 'transparent',
        background: 'none'
      }}>
        <LoadingOverlay
          open={true}
          message="인증 확인 중.."
          backdrop={false}
        />
      </Box>
    );
  }

  // 시스템 상태가 로드되었고 점검 중일 때만 점검 페이지 표시
  const showMaintenance = !statusLoading && shouldShowMaintenance();

  if (showMaintenance) {
    return (
      <MaintenancePage
        maintenanceInfo={systemStatus.maintenanceInfo}
        onRetry={checkSystemStatus}
        isAdmin={isAdmin}
        onLogout={user ? logout : null}
      />
    );
  }

  return (
    <HelpProvider>
      <ColorProvider>
      <Box sx={{ position: 'relative', minHeight: '100vh' }}>
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{
              duration: 0.3,
              ease: [0.4, 0, 0.2, 1]
            }}
            style={{ minHeight: '100vh' }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </Box>
      </ColorProvider>
    </HelpProvider>
  );
}

export default App;



