// design-system/components/Button.jsx
// 새 디자인 시스템 버튼 컴포넌트

import React from 'react';
import { Button as MuiButton, CircularProgress } from '@mui/material';

/**
 * 디자인 시스템 버튼 컴포넌트
 * 
 * @param {Object} props
 * @param {'primary' | 'secondary' | 'ghost' | 'danger'} props.variant - 버튼 스타일
 * @param {'sm' | 'md' | 'lg'} props.size - 버튼 크기
 * @param {boolean} props.loading - 로딩 상태
 * @param {boolean} props.fullWidth - 전체 너비
 * @param {React.ReactNode} props.startIcon - 시작 아이콘
 * @param {React.ReactNode} props.endIcon - 끝 아이콘
 */
export const Button = ({
    children,
    variant = 'primary',
    size = 'md',
    loading = false,
    disabled = false,
    fullWidth = false,
    startIcon,
    endIcon,
    onClick,
    type = 'button',
    ...props
}) => {
    // 크기별 스타일
    const sizeStyles = {
        sm: {
            fontSize: 'var(--font-size-sm)',
            padding: 'var(--spacing-xs) var(--spacing-md)',
            minHeight: '36px',
        },
        md: {
            fontSize: 'var(--font-size-base)',
            padding: 'var(--spacing-sm) var(--spacing-lg)',
            minHeight: '44px',
        },
        lg: {
            fontSize: 'var(--font-size-lg)',
            padding: 'var(--spacing-md) var(--spacing-xl)',
            minHeight: '52px',
        },
    };

    // 변형별 스타일
    const variantStyles = {
        primary: {
            backgroundColor: 'var(--color-primary)',
            color: 'var(--color-text-inverse)',
            border: 'none',
            '&:hover': {
                backgroundColor: 'var(--color-primary-hover)',
                boxShadow: 'var(--shadow-glow-primary)',
            },
            '&:active': {
                transform: 'scale(0.98)',
            },
            '&:disabled': {
                backgroundColor: 'var(--color-text-tertiary)',
                boxShadow: 'none',
            },
        },
        secondary: {
            backgroundColor: 'transparent',
            color: 'var(--color-primary)',
            border: '2px solid var(--color-primary)',
            '&:hover': {
                backgroundColor: 'var(--color-primary-lighter)',
                borderColor: 'var(--color-primary-hover)',
            },
            '&:active': {
                transform: 'scale(0.98)',
            },
            '&:disabled': {
                borderColor: 'var(--color-text-tertiary)',
                color: 'var(--color-text-tertiary)',
            },
        },
        ghost: {
            backgroundColor: 'transparent',
            color: 'var(--color-text-secondary)',
            border: 'none',
            '&:hover': {
                backgroundColor: 'var(--color-primary-lighter)',
                color: 'var(--color-primary)',
            },
            '&:disabled': {
                color: 'var(--color-text-tertiary)',
            },
        },
        danger: {
            backgroundColor: 'var(--color-error)',
            color: 'var(--color-text-inverse)',
            border: 'none',
            '&:hover': {
                backgroundColor: '#dc2626',
                boxShadow: '0 0 20px rgba(239, 68, 68, 0.3)',
            },
            '&:disabled': {
                backgroundColor: 'var(--color-text-tertiary)',
            },
        },
    };

    return (
        <MuiButton
            type={type}
            disabled={disabled || loading}
            fullWidth={fullWidth}
            startIcon={loading ? <CircularProgress size={16} color="inherit" /> : startIcon}
            endIcon={endIcon}
            onClick={onClick}
            sx={{
                fontFamily: 'var(--font-family-sans)',
                fontWeight: 'var(--font-weight-semibold)',
                borderRadius: 'var(--radius-md)',
                textTransform: 'none',
                letterSpacing: '-0.01em',
                transition: 'all var(--transition-normal)',
                ...sizeStyles[size],
                ...variantStyles[variant],
            }}
            {...props}
        >
            {children}
        </MuiButton>
    );
};

export default Button;
