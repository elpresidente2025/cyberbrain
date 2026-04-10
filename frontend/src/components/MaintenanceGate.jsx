import React from 'react';
import { Box } from '@mui/material';
import MaintenancePage from './MaintenancePage';
import { LoadingOverlay } from './loading';

export default function MaintenanceGate({
  authLoading,
  showMaintenance,
  maintenanceInfo,
  isAdmin,
  onRetry,
  onLogout,
  children,
}) {
  if (authLoading) {
    return (
      <Box
        sx={{
          height: '100vh',
          bgcolor: 'transparent',
          background: 'none',
        }}
      >
        <LoadingOverlay
          open
          message="인증 확인 중.."
          backdrop={false}
        />
      </Box>
    );
  }

  if (showMaintenance) {
    return (
      <MaintenancePage
        maintenanceInfo={maintenanceInfo}
        onRetry={onRetry}
        isAdmin={isAdmin}
        onLogout={onLogout}
      />
    );
  }

  return children;
}
