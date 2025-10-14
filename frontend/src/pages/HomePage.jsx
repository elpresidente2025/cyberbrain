// frontend/src/pages/HomePage.jsx
import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import AboutPage from './AboutPage';

const HomePage = () => {
  const { user, loading } = useAuth();

  // 로딩 중에는 아무것도 표시하지 않음 (App.jsx에서 로딩 처리)
  if (loading) {
    return null;
  }

  // 로그인된 사용자는 대시보드로 리다이렉트
  if (user) {
    return <Navigate to="/dashboard" replace />;
  }

  // 비로그인 사용자는 About 페이지 표시
  return <AboutPage />;
};

export default HomePage;