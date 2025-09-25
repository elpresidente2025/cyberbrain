import React, { createContext, useContext, useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';

// 사이버펑크 색상 옵션
const COLOR_OPTIONS = [
  '#d22730', // 클래식 레드
  '#00ffff', // 시안 (사이버펑크)
  '#00ff41', // 네온 그린 (사이버펑크)
  '#f8c023', // 사이버펑크 옐로우
  '#ff0080', // 마젠타 (사이버펑크)
  '#ffffff'  // 화이트
];

const ColorContext = createContext();

export const useColor = () => {
  const context = useContext(ColorContext);
  if (!context) {
    throw new Error('useColor must be used within a ColorProvider');
  }
  return context;
};

export const ColorProvider = ({ children }) => {
  const { user } = useAuth();
  const [currentColorIndex, setCurrentColorIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(true);

  const currentColor = COLOR_OPTIONS[currentColorIndex];

  // 색상 설정 로드 (네이버 전용 - localStorage만 사용)
  const loadColorPreference = async () => {
    try {
      const savedIndex = localStorage.getItem('electionDDayColorIndex');
      if (savedIndex !== null) {
        const index = parseInt(savedIndex, 10);
        if (index >= 0 && index < COLOR_OPTIONS.length) {
          setCurrentColorIndex(index);
        }
      }
    } catch (error) {
      console.warn('localStorage 색상 설정 로드 실패:', error);
    }
    setIsLoading(false);
  };

  // 색상 설정 저장 (네이버 전용 - localStorage만 사용)
  const saveColorPreference = async (newIndex) => {
    try {
      localStorage.setItem('electionDDayColorIndex', newIndex.toString());
    } catch (error) {
      console.warn('localStorage 색상 설정 저장 실패:', error);
    }
  };

  // 색상 변경 함수
  const changeColor = async (direction) => {
    let newIndex;
    if (direction === 'prev') {
      newIndex = currentColorIndex === 0 ? COLOR_OPTIONS.length - 1 : currentColorIndex - 1;
    } else {
      newIndex = currentColorIndex === COLOR_OPTIONS.length - 1 ? 0 : currentColorIndex + 1;
    }

    setCurrentColorIndex(newIndex);
    await saveColorPreference(newIndex);
  };

  // 사용자 변경 시 색상 로드
  useEffect(() => {
    loadColorPreference();
  }, [user?.uid]);

  const value = {
    currentColor,
    currentColorIndex,
    colorOptions: COLOR_OPTIONS,
    changeColor,
    isLoading
  };

  return (
    <ColorContext.Provider value={value}>
      {children}
    </ColorContext.Provider>
  );
};