import React from 'react';
import { Button, CircularProgress, Tooltip, useTheme } from '@mui/material';
import { transitions } from '../../../theme/tokens';

/**
 * ActionButton - 향상된 액션 버튼 컴포넌트
 *
 * @param {ReactNode} children - 버튼 텍스트
 * @param {string} variant - primary, secondary, danger, outlined, text
 * @param {boolean} loading - 로딩 상태
 * @param {ReactNode} icon - 아이콘 (startIcon으로 표시)
 * @param {string} tooltip - 툴팁 텍스트
 * @param {string} customColor - 커스텀 배경색
 * @param {function} onClick - 클릭 핸들러
 * @param {boolean} disabled - 비활성화 상태
 */
const ActionButton = ({
  children,
  variant = 'primary',
  loading = false,
  icon,
  tooltip,
  customColor,
  onClick,
  disabled,
  ...props
}) => {
  const theme = useTheme();

  // variant에 따른 스타일 결정
  const getVariantStyles = () => {
    const baseColor = customColor || theme.palette.ui?.header || '#152484';

    switch (variant) {
      case 'primary':
        return {
          variant: 'contained',
          sx: {
            bgcolor: baseColor,
            color: '#ffffff',
            transition: `all ${transitions.normal} ${transitions.easing.easeInOut}`,
            '&:hover': {
              bgcolor: baseColor,
              filter: 'brightness(0.9)',
              transform: 'scale(0.98)'
            }
          }
        };

      case 'secondary':
        return {
          variant: 'outlined',
          sx: {
            color: baseColor,
            borderColor: baseColor,
            transition: `all ${transitions.normal} ${transitions.easing.easeInOut}`,
            '&:hover': {
              borderColor: baseColor,
              bgcolor: `${baseColor}10`,
              transform: 'scale(0.98)'
            }
          }
        };

      case 'danger':
        return {
          variant: 'contained',
          color: 'error'
        };

      case 'outlined':
        return {
          variant: 'outlined'
        };

      case 'text':
        return {
          variant: 'text'
        };

      default:
        return {
          variant: 'contained'
        };
    }
  };

  const variantStyles = getVariantStyles();

  const button = (
    <Button
      onClick={onClick}
      disabled={disabled || loading}
      startIcon={loading ? <CircularProgress size={20} /> : icon}
      {...variantStyles}
      {...props}
      sx={{
        ...variantStyles.sx,
        ...props.sx
      }}
    >
      {loading ? '처리 중...' : children}
    </Button>
  );

  if (tooltip) {
    return (
      <Tooltip title={tooltip} arrow>
        <span>{button}</span>
      </Tooltip>
    );
  }

  return button;
};

export default ActionButton;
