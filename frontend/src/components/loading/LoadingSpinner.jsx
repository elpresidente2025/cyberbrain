// frontend/src/components/loading/LoadingSpinner.jsx
import React from 'react';
import { Box, Typography, useTheme } from '@mui/material';
import BaseSpinner, { SPINNER_SIZES } from './BaseSpinner';

const LoadingSpinner = ({ 
  size = SPINNER_SIZES.medium, 
  message = '', 
  color = 'primary',
  centered = true,
  fullHeight = false,
  sx = {} 
}) => {
  const theme = useTheme();
  const containerSx = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
    ...(centered && {
      width: '100%',
      textAlign: 'center'
    }),
    ...(fullHeight && {
      minHeight: '200px'
    }),
    ...sx
  };

  return (
    <Box sx={containerSx}>
      <BaseSpinner size={size} color={color} />
      {message && (
        <Typography
          variant="body2"
          sx={{
            mt: 1,
            color: theme.palette.primary.main,
            fontFamily: '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, system-ui, Roboto, "Helvetica Neue", "Segoe UI", "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", sans-serif',
            fontWeight: 500,
            fontSize: '1rem',
            // 카드 내부에서는 텍스트 색상으로 표시
            '.MuiCard-root &, .MuiPaper-root &': {
              color: theme.palette.text.secondary
            }
          }}
        >
          {message}
        </Typography>
      )}
    </Box>
  );
};

export default LoadingSpinner;