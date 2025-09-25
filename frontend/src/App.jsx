// frontend/src/App.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Box } from '@mui/material';
import { useAuth } from './hooks/useAuth';
import { getSystemStatus } from './services/firebaseService';
import MaintenancePage from './components/MaintenancePage';
import { LoadingOverlay } from './components/loading';
import { HelpProvider } from './contexts/HelpContext';
import { ColorProvider } from './contexts/ColorContext';
import BackgroundGrid from './components/BackgroundGrid';

function App() {
  const { user, loading, logout } = useAuth();
  const [systemStatus, setSystemStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const location = useLocation();

  // ?�스???�태 ?�인 (?�?�아??10초로 조정)
  const checkSystemStatus = useCallback(async () => {
    setStatusLoading(true);
    try {
      // cyberbrain.kr 도메인에서는 CORS 오류 방지를 위해 시스템 상태 체크 건너뛰기
      if (window.location.hostname === 'cyberbrain.kr') {
        console.log('🔧 CORS 방지: cyberbrain.kr에서 시스템 상태 체크 건너뛰기');
        setSystemStatus({ status: 'active' });
        return;
      }

      // 10초 타이마웃 설정 (Firebase Functions 응답 시간 고려)
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('timeout')), 10000)
      );

      const status = await Promise.race([
        getSystemStatus(),
        timeoutPromise
      ]);

      setSystemStatus(status);
    } catch (error) {
      console.error('시스템 상태 확인 실패:', error);
      setSystemStatus({ status: 'active' }); // 실패 시 정상 상태로 간주
    } finally {
      setStatusLoading(false);
    }
  }, []);

  // 관리자 계정 ?�인 (useEffect보다 먼�? ?�언)
  const isAdmin = user?.email === 'kjk6206@gmail.com' || user?.email === 'taesoo@secretart.ai';

  useEffect(() => {
    // 로그???�태가 ?�정???�에�??�스???�태 ?�인 (최초 1?�만)
    if (!loading && systemStatus === null) {
      // ???�환?�서 ?�아????불필?�한 ?�확??방�?
      const lastCheck = sessionStorage.getItem('systemStatusLastCheck');
      const now = Date.now();
      
      // 5�??�내???�인?�다�??�킵
      if (lastCheck && (now - parseInt(lastCheck)) < 300000) {
        setSystemStatus({ status: 'active' });
        setStatusLoading(false);
        return;
      }
      
      checkSystemStatus();
      sessionStorage.setItem('systemStatusLastCheck', now.toString());
    }
  }, [loading, checkSystemStatus, systemStatus]);

  // ?��? 모드???�만 주기?�으�??�태 ?�인 (복구 감�???
  useEffect(() => {
    let interval = null;
    
    if (systemStatus?.status === 'maintenance' && !isAdmin) {
      // ?��? 중일 ?�만 2분마??복구 ?�인
      console.log('?�� ?��? 모드: 2분마??복구 ?�태 ?�인 ?�작');
      interval = setInterval(checkSystemStatus, 120000);
    }
    
    return () => {
      if (interval) {
        console.log('?�� ?�태 ?�인 간격 ?�리');
        clearInterval(interval);
      }
    };
  }, [systemStatus?.status, isAdmin, checkSystemStatus]);

  // ?��? 중이�??�반 ?�용?�인 경우�??��? ?�이지 ?�시
  const shouldShowMaintenance = () => {
    if (!systemStatus || systemStatus.status !== 'maintenance') {
      return false;
    }

    // 로그?�웃 ?�태?�서??로그???�이지 ?�근 ?�용
    const publicGuestPaths = ['/', '/login', '/about'];
    if (!user && publicGuestPaths.some((p) => location.pathname === p || location.pathname.startsWith(p + '/'))) {
      return false;
    }

    // 관리자????�� ?�근 ?�용 (?��? ?�제�??�해)
    if (isAdmin) {
      return false;
    }

    // 로그?�된 ?�반 ?�용?�는 모든 ?�이지?�서 ?��? ?�이지 ?�시
    if (user && !isAdmin) {
      return true;
    }

    return false;
  };

  // 로딩 �??�시
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
        {/* Synthwave background image for top 50% */}
        <Box
          sx={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            height: '50vh',
            backgroundImage: 'url(/background/synthwave_city.png)',
            backgroundRepeat: 'no-repeat',
            backgroundPosition: 'top center',
            backgroundSize: 'cover',
            pointerEvents: 'none',
            zIndex: -1,
          }}
        />

        {/* Background Grid */}
        <BackgroundGrid />
        <Outlet />
      </Box>
      </ColorProvider>
    </HelpProvider>
  );
}

export default App;



