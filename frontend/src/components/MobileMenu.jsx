import React, { useState } from 'react';
import {
  IconButton,
  Box,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  ListItemIcon,
  Avatar,
  Typography,
  Slide
} from '@mui/material';
import {
  Menu as MenuIcon,
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
import { useTheme } from '@mui/material';

const MobileMenu = () => {
  const { user, logout } = useAuth();
  const { isDarkMode, toggleTheme } = useThemeMode();
  const [isOpen, setIsOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const theme = useTheme();

  const handleToggle = () => setIsOpen(!isOpen);
  const handleClose = () => setIsOpen(false);
  const handleLogout = async () => { await logout(); handleClose(); };

  // 스크롤 잠금 처리
  React.useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }

    // 컴포넌트 언마운트 시 정리
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  const userIcon = getUserStatusIcon(user);
  const regionInfo = getUserRegionInfo(user);
  const isAdmin = user?.role === 'admin' || user?.isAdmin;
  const hasBio = user?.bio && user.bio.trim().length > 0;

  const menuItems = [];

  if (hasBio || isAdmin) {
    menuItems.push(
      { text: '새 원고 생성', icon: <Create />, path: '/generate' },
      { text: '내 원고 목록', icon: <History />, path: '/posts' },
      { text: '가이드라인', icon: <MenuBook />, path: '/guidelines' }
    );
  }

  // 소개 페이지는 항상 표시
  menuItems.push({ text: '소개', icon: <Info />, path: '/about' });

  menuItems.push(
    { text: '프로필 수정', icon: <Settings />, path: '/profile' },
    { text: '인증 및 결제', icon: <CreditCard />, path: '/billing' }
  );

  if (isAdmin) {
    menuItems.push({ text: '관리', icon: <AdminPanelSettings />, path: '/admin' });
  }

  const isCurrentPath = (path) => location.pathname === path;
  const handleNavigate = (path) => { navigate(path); handleClose(); };

  return (
    <>
      {/* 햄버거 메뉴 버튼 - 고정 위치 */}
      <IconButton
        onClick={handleToggle}
        disableRipple
        sx={{
          position: 'fixed',
          top: 0,
          right: 16,
          height: 64, // 헤더 높이와 동일
          display: 'flex',
          alignItems: 'center',
          zIndex: 1102,
          color: 'white',
          width: 48
        }}
      >
        <MenuIcon />
      </IconButton>

      {/* 메뉴 패널 */}
      <Slide direction="left" in={isOpen} mountOnEnter unmountOnExit>
        <Box
          sx={{
            position: 'fixed',
            top: 0,
            right: 0,
            width: 300,
            height: '100vh',
            bgcolor: isDarkMode
              ? 'rgba(18, 18, 18, 0.8)'
              : 'rgba(255, 255, 255, 0.8)',
            backdropFilter: 'blur(10px)',
            zIndex: 1101,
            boxShadow: isDarkMode
              ? '-2px 0 10px rgba(0,0,0,0.5)'
              : '-2px 0 10px rgba(0,0,0,0.1)',
            overflow: 'auto',
            color: theme.palette.text.primary
          }}
        >
          {/* 사용자 정보 */}
          <Box sx={{ p: 3, borderBottom: '1px solid', borderColor: 'divider', mt: 6 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <Avatar sx={{ mr: 2, bgcolor: 'primary.main' }}>{userIcon}</Avatar>
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  {user?.name || '사용자'}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {getUserDisplayTitle(user)}
                </Typography>
              </Box>
            </Box>
            {regionInfo && (
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                {regionInfo}
              </Typography>
            )}
          </Box>

          {/* 메뉴 리스트 */}
          <List>
            {menuItems.map((item) => (
              <ListItem key={item.text} disablePadding>
                <ListItemButton
                  onClick={() => handleNavigate(item.path)}
                  selected={isCurrentPath(item.path)}
                >
                  <ListItemIcon>{item.icon}</ListItemIcon>
                  <ListItemText primary={item.text} />
                </ListItemButton>
              </ListItem>
            ))}
            <ListItem disablePadding>
              <ListItemButton onClick={toggleTheme}>
                <ListItemIcon>
                  {isDarkMode ? <LightMode /> : <DarkMode />}
                </ListItemIcon>
                <ListItemText primary={isDarkMode ? "라이트 모드" : "다크 모드"} />
              </ListItemButton>
            </ListItem>
            <ListItem disablePadding>
              <ListItemButton onClick={handleLogout}>
                <ListItemIcon><Logout /></ListItemIcon>
                <ListItemText primary="로그아웃" />
              </ListItemButton>
            </ListItem>
          </List>
        </Box>
      </Slide>

      {/* 백드롭 */}
      {isOpen && (
        <Box
          onClick={handleClose}
          sx={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100vw',
            height: '100vh',
            bgcolor: 'rgba(0, 0, 0, 0.3)',
            zIndex: 1100,
            overflow: 'hidden'
          }}
        />
      )}
    </>
  );
};

export default MobileMenu;