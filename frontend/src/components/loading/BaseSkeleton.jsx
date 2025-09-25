// frontend/src/components/loading/BaseSkeleton.jsx
import React from 'react';
import { Skeleton } from '@mui/material';

/**
 * 공통 베이스 스켈레톤 컴포넌트
 * 모든 스켈레톤 로딩의 기본이 되는 컴포넌트
 */
const BaseSkeleton = ({ 
  variant = 'text', 
  width = '100%', 
  height = undefined,
  animation = 'pulse',
  sx = {},
  ...props
}) => (
  <Skeleton 
    variant={variant} 
    width={width} 
    height={height} 
    animation={animation}
    sx={{
      // 공통 스켈레톤 스타일
      backgroundColor: 'rgba(255, 255, 255, 0.08)',
      '&::after': {
        background: 'linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent)',
      },
      ...sx
    }}
    {...props}
  />
);

export default BaseSkeleton;