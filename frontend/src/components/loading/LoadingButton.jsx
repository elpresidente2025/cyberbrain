// frontend/src/components/loading/LoadingButton.jsx
import React from 'react';
import { Button } from '@mui/material';
import BaseSpinner, { SPINNER_SIZES } from './BaseSpinner';

const LoadingButton = ({ 
  loading = false,
  children,
  disabled = false,
  loadingText = '',
  spinnerSize = SPINNER_SIZES.small,
  spinnerColor = 'inherit',
  variant = 'contained',
  color = 'primary',
  ...props 
}) => {
  return (
    <Button
      {...props}
      variant={variant}
      color={color}
      disabled={loading || disabled}
      startIcon={loading ? <BaseSpinner size={spinnerSize} color={spinnerColor} /> : props.startIcon}
    >
      {loading && loadingText ? loadingText : children}
    </Button>
  );
};

export default LoadingButton;