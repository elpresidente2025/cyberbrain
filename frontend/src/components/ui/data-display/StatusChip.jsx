import React from 'react';
import { Chip } from '@mui/material';

/**
 * StatusChip - 상태 표시 칩 컴포넌트
 *
 * @param {string} status - 상태 값 (published, draft, pending, active, inactive 등)
 * @param {string} label - 표시할 텍스트 (기본값: status)
 * @param {string} size - 크기 (small, medium)
 * @param {object} customColors - 커스텀 색상 매핑 { status: color }
 * @param {string} variant - outlined 또는 filled
 */
const StatusChip = ({
  status,
  label,
  size = 'small',
  customColors = {},
  variant = 'outlined',
  ...props
}) => {
  // 기본 색상 매핑
  const defaultColorMap = {
    published: 'success',
    draft: 'default',
    pending: 'warning',
    active: 'success',
    inactive: 'default',
    error: 'error',
    processing: 'info',
    completed: 'success',
    cancelled: 'error',
    approved: 'success',
    rejected: 'error',
    ...customColors
  };

  // 기본 라벨 매핑 (한글)
  const defaultLabelMap = {
    published: '발행됨',
    draft: '초안',
    pending: '대기 중',
    active: '활성',
    inactive: '비활성',
    error: '오류',
    processing: '처리 중',
    completed: '완료',
    cancelled: '취소됨',
    approved: '승인됨',
    rejected: '거부됨'
  };

  const chipColor = defaultColorMap[status] || 'default';
  const chipLabel = label || defaultLabelMap[status] || status;

  return (
    <Chip
      label={chipLabel}
      size={size}
      color={chipColor}
      variant={variant}
      sx={{
        fontSize: '0.7rem',
        fontWeight: 500,
        ...props.sx
      }}
      {...props}
    />
  );
};

export default StatusChip;
