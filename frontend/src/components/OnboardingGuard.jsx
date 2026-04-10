import React from 'react';
import { Navigate } from 'react-router-dom';
import { Box, LinearProgress } from '@mui/material';
import { useAuth } from '../hooks/useAuth';
import { hasAdminAccess } from '../utils/authz';

const MIN_BIO_LENGTH = 50;

// 광역자치단체장/기초자치단체장은 선거구(electoralDistrict) 불필요
export function getRequiredRegionFields(position) {
  if (!position) return ['regionMetro'];
  if (position === '광역자치단체장') return ['regionMetro'];
  if (position === '기초자치단체장') return ['regionMetro', 'regionLocal'];
  return ['regionMetro', 'regionLocal', 'electoralDistrict'];
}

export function isOnboardingComplete(user) {
  if (!user) return false;
  if (user.onboardingCompleted === true) return true;

  const { position, bio } = user;
  if (!position) return false;

  const required = getRequiredRegionFields(position);
  for (const key of required) {
    if (!user[key]) return false;
  }

  const bioText = typeof bio === 'string' ? bio.trim() : '';
  if (bioText.length < MIN_BIO_LENGTH) return false;

  return true;
}

const OnboardingGuard = ({ children }) => {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <Box sx={{ width: '100%', mt: 2 }}>
        <LinearProgress />
      </Box>
    );
  }

  if (!user) {
    return <Navigate to="/" replace />;
  }

  // 관리자는 온보딩 우회
  if (hasAdminAccess(user)) {
    return children;
  }

  if (!isOnboardingComplete(user)) {
    return <Navigate to="/onboarding" replace />;
  }

  return children;
};

export default OnboardingGuard;
