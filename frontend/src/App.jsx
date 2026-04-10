import React from 'react';
import { useLocation } from 'react-router-dom';
import { useAuth } from './hooks/useAuth';
import AppShell from './components/AppShell';
import MaintenanceGate from './components/MaintenanceGate';
import useMaintenanceMode from './hooks/useMaintenanceMode';

function App() {
  const { user, loading, logout } = useAuth();
  const location = useLocation();
  const {
    showMaintenance,
    maintenanceInfo,
    isAdmin,
    refreshSystemStatus,
  } = useMaintenanceMode({
    user,
    authLoading: loading,
    pathname: location.pathname,
  });

  return (
    <MaintenanceGate
      authLoading={loading}
      showMaintenance={showMaintenance}
      maintenanceInfo={maintenanceInfo}
      isAdmin={isAdmin}
      onRetry={refreshSystemStatus}
      onLogout={user ? logout : null}
    >
      <AppShell pathname={location.pathname} />
    </MaintenanceGate>
  );
}

export default App;
