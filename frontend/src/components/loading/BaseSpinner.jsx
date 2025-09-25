// frontend/src/components/loading/BaseSpinner.jsx
import React from 'react';
import { CircularProgress, Box } from '@mui/material';

// 표준 스피너 크기
export const SPINNER_SIZES = {
  small: 20,    // 버튼 내부용
  medium: 50,   // 일반 로딩용 & 오버레이용 (통일)
};

/**
 * 공통 베이스 스피너 컴포넌트
 * 모든 로딩 스피너의 기본이 되는 컴포넌트
 */
const BaseSpinner = ({ 
  size = SPINNER_SIZES.medium,
  color = 'primary',
  sx = {},
  ...props
}) => {
  return (
    <CircularProgress 
      size={size} 
      color={color}
      sx={{
        // 테마에서 정의된 기본 스타일 (노란색 + 글로우)
        // 카드 내부에서는 파란색으로 표시
        '.MuiCard-root &, .MuiPaper-root &': {
          color: '#152484',
          filter: 'drop-shadow(0 0 6px #152484)',
        },
        ...sx
      }}
      {...props}
    />
  );
};

export default BaseSpinner;