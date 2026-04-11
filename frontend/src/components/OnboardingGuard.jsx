import React from 'react';
import { Navigate } from 'react-router-dom';
import { Box, LinearProgress } from '@mui/material';
import { useAuth } from '../hooks/useAuth';
import { hasAdminAccess } from '../utils/authz';

// 광역자치단체장/기초자치단체장은 선거구(electoralDistrict) 불필요
export function getRequiredRegionFields(position) {
  if (!position) return ['regionMetro'];
  if (position === '광역자치단체장') return ['regionMetro'];
  if (position === '기초자치단체장') return ['regionMetro', 'regionLocal'];
  return ['regionMetro', 'regionLocal', 'electoralDistrict'];
}

// 자기소개(bio)는 온보딩 완료 조건에서 제외하고 프로필 페이지에서 별도로 작성하도록 유도한다.
// status는 선거법 기준 판별의 핵심 지표이므로 예외 없이 필수이며,
// onboardingCompleted 플래그보다 실제 필드 상태를 우선 판정한다.
export function isOnboardingComplete(user) {
  if (!user) return false;

  if (!user.status) return false;

  const { position } = user;
  if (!position) return false;

  const required = getRequiredRegionFields(position);
  for (const key of required) {
    if (!user[key]) return false;
  }

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
