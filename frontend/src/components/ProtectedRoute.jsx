import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';
import { useAuth } from '../hooks/useAuth';
import { firebaseApiKey } from '../services/firebase';

const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
        }}
      >
        <CircularProgress />
      </Box>
    );
  }

  if (!user || !user.uid) {
    try {
      localStorage.removeItem(`firebase:authUser:${firebaseApiKey}:[DEFAULT]`);
      sessionStorage.clear();
    } catch (error) {
      console.warn('스토리지 정리 실패:', error);
    }

    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return children;
};

export default ProtectedRoute;
