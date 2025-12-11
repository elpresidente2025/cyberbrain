import React from 'react';
import { Paper } from '@mui/material';

const HongKongNeonCard = ({ 
  children, 
  elevation = 0, 
  sx = {},
  ...props 
}) => {

  const neonCardStyle = {
    // 네온 홍콩 스타일 배경
    background: 'linear-gradient(135deg, rgba(0, 200, 200, 0.05) 0%, rgba(255, 20, 147, 0.05) 100%)',
    backdropFilter: 'blur(10px)',
    
    // 네온 테두리와 그림자
    border: '1px solid rgba(0, 200, 200, 0.6)',
    boxShadow: `
      0 0 20px rgba(0, 200, 200, 0.3),
      0 4px 15px rgba(0, 0, 0, 0.1),
      inset 0 1px 0 rgba(255, 255, 255, 0.1)
    `,

    borderRadius: '2px',
    position: 'relative',
    overflow: 'hidden',
    
    // 부드러운 전환 효과
    transition: 'all 0.4s ease',
    
    // 호버 시 네온 리프트 효과
    '&:hover': {
      transform: 'translateY(-4px)',
      boxShadow: `
        0 0 30px rgba(0, 200, 200, 0.5),
        0 0 60px rgba(255, 20, 147, 0.2),
        0 8px 25px rgba(0, 0, 0, 0.2),
        inset 0 1px 0 rgba(255, 255, 255, 0.2)
      `,
      borderColor: 'rgba(0, 200, 200, 0.8)',
    },
    
    // 네온 액센트 라인 (상단)
    '&::before': {
      content: '""',
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      height: '2px',
      background: 'linear-gradient(90deg, rgba(0, 200, 200, 0.8), rgba(255, 20, 147, 0.8))',
      zIndex: 1,
    },
    
    // 자식 요소들이 효과 위에 표시되도록
    '& > *': {
      position: 'relative',
      zIndex: 2,
    },
    
    // 네온 텍스트 스타일링
    '& .MuiTypography-h6, & .MuiTypography-h5, & .MuiTypography-h4': {
      textShadow: '0 0 10px rgba(0, 200, 200, 0.3), 0 1px 2px rgba(0, 0, 0, 0.2)',
      fontWeight: 700,
    },
    
    // 추가 스타일 병합
    ...sx
  };

  return (
    <Paper 
      elevation={elevation}
      sx={neonCardStyle}
      {...props}
    >
      {children}
    </Paper>
  );
};

export default HongKongNeonCard;
