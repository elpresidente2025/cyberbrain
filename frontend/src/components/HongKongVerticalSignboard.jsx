import React from 'react';
import { Box, Typography } from '@mui/material';

const HongKongVerticalSignboard = ({ 
  children, 
  title = "ADMIN STATS",
  sx = {},
  ...props 
}) => {
  return (
    <Box
      sx={{
        position: 'relative',
        background: 'transparent',
        border: '2px solid rgba(0, 200, 200, 0.5)',
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.7)',
        borderRadius: '12px',
        padding: '20px 16px',
        minHeight: '600px',
        width: '100%',
        maxWidth: '320px',
        
        // 깔끔한 카드 스타일
        transition: 'all 0.3s ease',
        
        // 깔끔한 좌우 액센트 라인
        '&::before': { content: 'none' },
        
        '&::after': { content: 'none' },
        
        // 호버 효과
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: '0 8px 30px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.8)',
          borderColor: 'rgba(0, 200, 200, 0.7)'
        },
        
        // 자식 요소들 배치
        '& > *:not(:last-child)': {
          marginBottom: '8px',
        },
        
        ...sx
      }}
      {...props}
    >
      {/* 제목 */}
      <Typography
        variant="h6"
        sx={{
          color: '#1a1a2e',
          textAlign: 'center',
          fontFamily: '"Noto Sans KR", monospace',
          fontWeight: 700,
          fontSize: '1.1rem',
          letterSpacing: '3px',
          textShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
          mb: 3,
          textTransform: 'uppercase',
          writingMode: 'horizontal-tb',
          
          // 깜빡거리는 효과
          animation: 'titleFlicker 3s ease-in-out infinite alternate'
        }}
      >
        {title}
      </Typography>
      
      {/* 카드들 */}
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          gap: 1,
          position: 'relative',
          zIndex: 2,
          
          // 각 카드에 네온 효과 적용
          '& > *': {
            transition: 'all 0.3s ease',
            '&:hover': {
              transform: 'translateX(4px)',
              filter: 'brightness(1.1)'
            }
          }
        }}
      >
        {children}
      </Box>
      
      {/* 추가 키프레임 */}
      <style jsx>{`
        @keyframes titleFlicker {
          0%, 100% { opacity: 0.9; }
          50% { opacity: 1; }
        }
      `}</style>
    </Box>
  );
};

export default HongKongVerticalSignboard;
