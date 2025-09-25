import React, { createContext, useContext, useState, useEffect } from 'react';

const ThemeContext = createContext();

export const useThemeMode = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useThemeMode must be used within a ThemeProvider');
  }
  return context;
};

export const ThemeModeProvider = ({ children }) => {
  const [isDarkMode, setIsDarkMode] = useState(() => {
    // 로컬스토리지에서 저장된 테마 모드 불러오기
    const savedTheme = localStorage.getItem('themeMode');
    if (savedTheme) {
      return savedTheme === 'dark';
    }
    // 시스템 다크모드 설정 확인
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });
  
  // 컴포넌트 마운트 시 body 클래스 초기 동기화
  useEffect(() => {
    if (isDarkMode) {
      document.body.classList.add('dark-mode');
    } else {
      document.body.classList.remove('dark-mode');
    }
  }, []); // 빈 배열로 마운트 시에만 실행

  useEffect(() => {
    // 테마 변경 시 로컬스토리지에 저장 및 body 클래스 동기화
    localStorage.setItem('themeMode', isDarkMode ? 'dark' : 'light');
    
    // body 클래스 동기화 (HTML 로딩 화면과 일치)
    if (isDarkMode) {
      document.body.classList.add('dark-mode');
    } else {
      document.body.classList.remove('dark-mode');
    }
  }, [isDarkMode]);

  const toggleTheme = () => {
    setIsDarkMode(prev => !prev);
  };

  return (
    <ThemeContext.Provider value={{ isDarkMode, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};