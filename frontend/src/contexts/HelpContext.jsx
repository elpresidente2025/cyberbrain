import React, { createContext, useContext, useState } from 'react';
import { useLocation } from 'react-router-dom';

// 도움말 가이드 컴포넌트들을 lazy import
const DashboardGuide = React.lazy(() => import('../components/guides/DashboardGuide'));
const GenerateGuide = React.lazy(() => import('../components/guides/GenerateGuide'));
const ManagementGuide = React.lazy(() => import('../components/guides/ManagementGuide'));
const ProfileGuide = React.lazy(() => import('../components/guides/ProfileGuide'));

// 페이지별 도움말 설정
const HELP_CONFIG = {
  '/dashboard': {
    title: '대시보드 사용 가이드',
    component: DashboardGuide
  },
  '/generate': {
    title: '원고 생성 가이드',
    component: GenerateGuide
  },
  '/posts': {
    title: '원고 관리 가이드',
    component: ManagementGuide
  },
  '/profile': {
    title: '프로필 설정 가이드',
    component: ProfileGuide
  },
  '/billing': {
    title: '인증 및 결제 가이드',
    component: null // 아직 가이드가 없는 페이지
  }
};

const HelpContext = createContext();

export const HelpProvider = ({ children }) => {
  const location = useLocation();
  const [isHelpOpen, setIsHelpOpen] = useState(false);

  // 현재 페이지의 도움말 설정 가져오기
  const getCurrentHelpConfig = () => {
    return HELP_CONFIG[location.pathname] || null;
  };

  // 현재 페이지에 도움말이 있는지 확인
  const hasHelp = () => {
    const config = getCurrentHelpConfig();
    return config && config.component;
  };

  const openHelp = () => setIsHelpOpen(true);
  const closeHelp = () => setIsHelpOpen(false);

  const value = {
    isHelpOpen,
    openHelp,
    closeHelp,
    getCurrentHelpConfig,
    hasHelp
  };

  return (
    <HelpContext.Provider value={value}>
      {children}
    </HelpContext.Provider>
  );
};

export const useHelp = () => {
  const context = useContext(HelpContext);
  if (!context) {
    throw new Error('useHelp must be used within a HelpProvider');
  }
  return context;
};