import React from 'react';
import { Box, CircularProgress, Typography, Skeleton } from '@mui/material';

/**
 * LoadingState - 다양한 로딩 상태를 표시하는 컴포넌트
 *
 * @param {boolean} loading - 로딩 상태
 * @param {ReactNode} children - 로딩이 끝난 후 보여줄 내용
 * @param {string} type - 로딩 타입 (fullPage, inline, button, skeleton)
 * @param {string} message - 로딩 메시지
 * @param {number} size - CircularProgress 크기
 * @param {number} skeletonCount - Skeleton 개수
 * @param {number} skeletonHeight - Skeleton 높이
 */
const LoadingState = ({
  loading,
  children,
  type = 'inline',
  message = '로딩 중...',
  size = 40,
  skeletonCount = 3,
  skeletonHeight = 60,
  ...props
}) => {
  if (!loading) {
    return <>{children}</>;
  }

  // Full Page Loading
  if (type === 'fullPage') {
    return (
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: '60vh',
          gap: 2
        }}
        {...props}
      >
        <CircularProgress size={size} />
        {message && (
          <Typography variant="body2" color="text.secondary">
            {message}
          </Typography>
        )}
      </Box>
    );
  }

  // Button Loading (small circular progress)
  if (type === 'button') {
    return <CircularProgress size={size || 20} {...props} />;
  }

  // Skeleton Loading
  if (type === 'skeleton') {
    return (
      <Box {...props}>
        {Array.from({ length: skeletonCount }).map((_, index) => (
          <Skeleton
            key={index}
            variant="rectangular"
            height={skeletonHeight}
            sx={{ mb: 2, borderRadius: 1 }}
          />
        ))}
      </Box>
    );
  }

  // Inline Loading (default)
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: 2
      }}
      {...props}
    >
      <CircularProgress size={size} />
    </Box>
  );
};

export default LoadingState;
