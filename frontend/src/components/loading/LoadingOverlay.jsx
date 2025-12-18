// frontend/src/components/loading/LoadingOverlay.jsx
import React from 'react';
import { Box, Typography, Backdrop, useTheme } from '@mui/material';
import BaseSpinner, { SPINNER_SIZES } from './BaseSpinner';

const LoadingOverlay = ({ 
  open = false,
  message = '로딩 중...',
  size = SPINNER_SIZES.medium,
  color = 'primary',
  backdrop = true,
  zIndex = 1300 
}) => {
  const theme = useTheme();
  if (backdrop) {
    return (
      <Backdrop
        open={open}
        // 포커스 관리 문제 방지 - aria-hidden 충돌 해결
        slotProps={{
          root: {
            'aria-hidden': false
          }
        }}
        sx={{
          zIndex,
          color: '#fff',
          backgroundColor: 'background.default',
          display: 'flex',
          flexDirection: 'column',
          gap: 2
        }}
      >
        <BaseSpinner size={size} color="inherit" />
        {message && (
          <Typography
            variant="h6"
            sx={{
              color: theme.palette.primary.main,
              fontFamily: '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, system-ui, Roboto, "Helvetica Neue", "Segoe UI", "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", sans-serif'
            }}
          >
            {message}
          </Typography>
        )}
      </Backdrop>
    );
  }

  return (
    <Box
      sx={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'background.default',
        zIndex,
        gap: 2
      }}
    >
      <BaseSpinner size={size} color={color} />
      {message && (
        <Typography
          variant="body1"
          sx={{
            color: theme.palette.primary.main,
            fontFamily: '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, system-ui, Roboto, "Helvetica Neue", "Segoe UI", "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", sans-serif'
          }}
        >
          {message}
        </Typography>
      )}
    </Box>
  );
};

export default LoadingOverlay;