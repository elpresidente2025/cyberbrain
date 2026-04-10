import { useCallback, useEffect, useMemo, useState } from 'react';
import { getSystemStatus } from '../services/firebaseService';
import { hasAdminAccess } from '../utils/authz';

const SYSTEM_STATUS_CACHE_KEY = 'systemStatusCache';
const SYSTEM_STATUS_CACHE_TTL_MS = 5 * 60 * 1000;
const SYSTEM_STATUS_TIMEOUT_MS = 10 * 1000;
const MAINTENANCE_RECHECK_INTERVAL_MS = 2 * 60 * 1000;
const PUBLIC_GUEST_PATHS = ['/', '/login', '/about'];

const readCachedSystemStatus = () => {
  const cacheStr = sessionStorage.getItem(SYSTEM_STATUS_CACHE_KEY);
  if (!cacheStr) {
    return null;
  }

  try {
    const cache = JSON.parse(cacheStr);
    const now = Date.now();

    if (!cache.timestamp || (now - cache.timestamp) >= SYSTEM_STATUS_CACHE_TTL_MS) {
      return null;
    }

    return {
      status: cache.status || 'active',
      maintenanceInfo: cache.maintenanceInfo || null,
      timestamp: new Date(cache.timestamp).toISOString(),
    };
  } catch (error) {
    console.warn('시스템 상태 캐시 파싱 실패:', error);
    return null;
  }
};

const writeCachedSystemStatus = (status) => {
  sessionStorage.setItem(
    SYSTEM_STATUS_CACHE_KEY,
    JSON.stringify({
      timestamp: Date.now(),
      status: status.status,
      maintenanceInfo: status.maintenanceInfo || null,
    })
  );
};

const isPublicGuestPath = (pathname) => PUBLIC_GUEST_PATHS.some(
  (path) => pathname === path || pathname.startsWith(`${path}/`)
);

const shouldShowMaintenance = ({ systemStatus, pathname, user, isAdmin }) => {
  if (!systemStatus || systemStatus.status !== 'maintenance') {
    return false;
  }

  if (!user && isPublicGuestPath(pathname)) {
    return false;
  }

  if (isAdmin) {
    return false;
  }

  return Boolean(user);
};

export default function useMaintenanceMode({ user, authLoading, pathname }) {
  const [systemStatus, setSystemStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const isAdmin = hasAdminAccess(user);

  const refreshSystemStatus = useCallback(async () => {
    setStatusLoading(true);

    try {
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error('timeout')), SYSTEM_STATUS_TIMEOUT_MS);
      });

      const status = await Promise.race([
        getSystemStatus(),
        timeoutPromise,
      ]);

      setSystemStatus(status);
      writeCachedSystemStatus(status);
    } catch (error) {
      console.error('시스템 상태 확인 실패:', error);
      setSystemStatus({ status: 'active' });
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    if (authLoading || systemStatus !== null) {
      return;
    }

    const cachedStatus = readCachedSystemStatus();
    if (cachedStatus) {
      setSystemStatus(cachedStatus);
      setStatusLoading(false);
      return;
    }

    refreshSystemStatus();
  }, [authLoading, refreshSystemStatus, systemStatus]);

  useEffect(() => {
    if (systemStatus?.status !== 'maintenance' || isAdmin) {
      return undefined;
    }

    const interval = setInterval(refreshSystemStatus, MAINTENANCE_RECHECK_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isAdmin, refreshSystemStatus, systemStatus?.status]);

  const showMaintenance = useMemo(
    () => !statusLoading && shouldShowMaintenance({ systemStatus, pathname, user, isAdmin }),
    [isAdmin, pathname, statusLoading, systemStatus, user]
  );

  return {
    showMaintenance,
    isAdmin,
    maintenanceInfo: systemStatus?.maintenanceInfo || null,
    refreshSystemStatus,
  };
}
