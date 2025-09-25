// frontend/src/components/DashboardLayout.jsx
import React from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  IconButton,
  Box,
  useTheme,
  useMediaQuery,
  Button,
  Portal
} from '@mui/material';
import {
  Create,
  History,
  Settings,
  Logout,
  CreditCard,
  AdminPanelSettings,
  MenuBook,
  DarkMode,
  LightMode,
  Info
} from '@mui/icons-material';
import { useAuth } from '../hooks/useAuth';
import { useNavigate, useLocation } from 'react-router-dom';
import { getUserDisplayTitle, getUserRegionInfo, getUserStatusIcon } from '../utils/userUtils';
import { useThemeMode } from '../contexts/ThemeContext';
import { useHelp } from '../contexts/HelpContext';
import HelpButton from './HelpButton';
import HelpModal from './HelpModal';
import MobileMenu from './MobileMenu';

const DashboardLayout = ({ children }) => {
  const { user, logout } = useAuth();
  const { isDarkMode, toggleTheme } = useThemeMode();
  const { isHelpOpen, openHelp, closeHelp, getCurrentHelpConfig, hasHelp } = useHelp();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('lg'));
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => await logout();
  const handleLogoClick = () => navigate('/dashboard');

  const userIcon = getUserStatusIcon(user);
  const regionInfo = getUserRegionInfo(user);
  const isAdmin = user?.role === 'admin' || user?.isAdmin;
  const hasBio = user?.bio && user.bio.trim().length > 0;

  // 자기소개가 없는 사용자는 제한된 메뉴만 표시
  const menuItems = [];
  
  if (hasBio || isAdmin) {
    // 자기소개가 있거나 관리자인 경우 전체 메뉴 표시
    menuItems.push(
      { text: '새 원고 생성', icon: <Create />, path: '/generate' },
      { text: '내 원고 목록', icon: <History />, path: '/posts' },
      { text: '가이드라인', icon: <MenuBook />, path: '/guidelines' }
    );
  }

  // 소개 페이지는 항상 표시
  menuItems.push({ text: '소개', icon: <Info />, path: '/about' });
  
  // 프로필과 결제는 항상 표시
  menuItems.push(
    { text: '프로필 수정', icon: <Settings />, path: '/profile' },
    { text: '인증 및 결제', icon: <CreditCard />, path: '/billing' }
  );
  
  if (isAdmin) {
    menuItems.push({ text: '관리', icon: <AdminPanelSettings />, path: '/admin' });
  }

  const isCurrentPath = (path) => location.pathname === path;
  const handleNavigate = (path) => navigate(path);


  return (
    // 자연스러운 문서 플로우: 스크롤은 실제 콘텐츠 길이만큼만
    <Box sx={{
      display: 'flex',
      flexDirection: 'column',
      minHeight: '100dvh'
    }}>
      {/* 상단 헤더: 완전 고정 */}
      <AppBar
        position="fixed"
        elevation={0}
        sx={{
          bgcolor: '#152484',
          top: 0,
          zIndex: (t) => t.zIndex.appBar + 1,
          borderRadius: 0,
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.02) 2px, rgba(255,255,255,0.02) 4px)',
            pointerEvents: 'none',
            zIndex: 1
          }
        }}
      >
        <Toolbar sx={{ position: 'relative', zIndex: 2 }}>
          {/* 로고 (왼쪽 정렬) */}
          <Box
            sx={{ display: 'flex', alignItems: 'center', flexGrow: 1, cursor: 'pointer' }}
            onClick={handleLogoClick}
          >
            <Box
              component="img"
              src="/logo-landscape.png"
              alt="전자두뇌비서관 로고"
              sx={{ height: 32, objectFit: 'contain' }}
            />
          </Box>

          {/* 데스크톱: 중앙 메뉴 + 우측 로그아웃 */}
          {!isMobile && (
            <>
              <Box sx={{
                position: 'absolute',
                left: '50%',
                transform: 'translateX(-50%)',
                display: 'flex',
                alignItems: 'center',
                gap: 1
              }}>
                {menuItems.map((item) => (
                  <Button
                    key={item.text}
                    color="inherit"
                    startIcon={item.icon}
                    onClick={() => handleNavigate(item.path)}
                    sx={{
                      color: 'white',
                      '&:hover': { bgcolor: 'rgba(255,255,255,0.1)' },
                      ...(isCurrentPath(item.path) && { bgcolor: 'rgba(255,255,255,0.2)', fontWeight: 'bold' })
                    }}
                  >
                    {item.text}
                  </Button>
                ))}
              </Box>

              {/* 다크모드 토글 버튼 */}
              <IconButton 
                color="inherit" 
                onClick={toggleTheme}
                sx={{ color: 'white', '&:hover': { bgcolor: 'rgba(255,255,255,0.1)' }, mr: 1 }}
              >
                {isDarkMode ? <LightMode /> : <DarkMode />}
              </IconButton>

              <Button
                color="inherit"
                startIcon={<Logout />}
                onClick={handleLogout}
                sx={{ color: 'white', '&:hover': { bgcolor: 'rgba(255,255,255,0.1)' } }}
              >
                로그아웃
              </Button>
            </>
          )}

          {/* 모바일: 헤더에는 아무것도 표시하지 않음 (햄버거 메뉴 내부에서 처리) */}
        </Toolbar>
      </AppBar>


      {/* 본문 - 콘텐츠에 맞는 자연스러운 높이 */}
      <Box
        component="main"
        sx={{
          bgcolor: 'transparent', // 카본 질감이 보이도록 투명하게 설정
          display: 'flex',
          justifyContent: 'center',
          width: '100%',
          flex: '1 0 auto',
          position: 'relative',
          pt: '64px', // 고정 헤더 높이만큼 상단 여백
          pb: 4, // 푸터와의 간격
        }}
      >
        <Box sx={{ width: '100%' }}>
          {children}
        </Box>
        {hasHelp() && (
          <Portal container={document.body}>
            <HelpButton onClick={openHelp} />
          </Portal>
        )}
      </Box>

      {/* 푸터 - 콘텐츠 바로 아래에 자연스럽게 배치 */}
      <Box
        component="footer"
        sx={{
          py: 2,
          px: 2,
          bgcolor: '#152484',
          borderTop: '1px solid',
          borderColor: 'divider',
          textAlign: 'center',
          position: 'relative',
          mt: 'auto',
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(255,255,255,0.02) 2px, rgba(255,255,255,0.02) 4px)',
            pointerEvents: 'none',
            zIndex: 1
          }
        }}
      >
        <Typography variant="caption" sx={{ lineHeight: 1.6, color: 'white', position: 'relative', zIndex: 2 }}>
          사이버브레인 | 사업자등록번호: 870-55-00786 | 통신판매업신고번호: (비움)<br />
          대표: 차서영 | 인천광역시 계양구 용종로 124, 학마을한진아파트 139동 1504호 | 대표번호: 010-4885-6206<br />
          Copyright 2025. CyberBrain. All Rights Reserved.
        </Typography>
      </Box>

      {/* 모바일 햄버거 메뉴 */}
      {isMobile && <MobileMenu />}

      {/* 전역 도움말 버튼 - 해당 페이지에 도움말이 있을 때만 표시 */}
      {hasHelp() && (
        <>
          <HelpModal
            open={isHelpOpen}
            onClose={closeHelp}
            title={getCurrentHelpConfig()?.title || '사용 가이드'}
          >
            <React.Suspense fallback={<Box sx={{ p: 2, textAlign: 'center', fontFamily: '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, system-ui, Roboto, "Helvetica Neue", "Segoe UI", "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", sans-serif' }}>로딩 중...</Box>}>
              {getCurrentHelpConfig()?.component && React.createElement(getCurrentHelpConfig().component)}
            </React.Suspense>
          </HelpModal>
        </>
      )}
    </Box>
  );
};

export default DashboardLayout;
