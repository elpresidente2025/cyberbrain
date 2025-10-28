import React from 'react';
import { useAuth } from '../hooks/useAuth';
import { Navigate, useLocation } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';

const AdminRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  // 화이트리스트: 긴급 접근 허용
  const adminEmails = ['kjk6206@gmail.com', 'taesoo@secretart.ai'];

  // 프로필 병합 전에는 잠시 대기하여 깜빡임 방지
  const isProfileMerging = !!user && user.role == null;

  if (loading || isProfileMerging) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  const hasAdminAccess = user.role === 'admin' || adminEmails.includes(user.email);

  if (!hasAdminAccess) {
    return <Navigate to="/dashboard" replace />;
  }

  return children;
};

export default AdminRoute;
