// design-system/components/Card.jsx
// 글래스모피즘 스타일 카드 컴포넌트

import React from 'react';
import { Paper, Box } from '@mui/material';
import { motion } from 'framer-motion';

/**
 * 디자인 시스템 카드 컴포넌트
 * 
 * @param {Object} props
 * @param {'default' | 'elevated' | 'glass' | 'outlined'} props.variant - 카드 스타일
 * @param {'sm' | 'md' | 'lg'} props.padding - 내부 여백
 * @param {boolean} props.hoverable - 호버 효과
 * @param {boolean} props.clickable - 클릭 가능 여부 (cursor: pointer)
 * @param {boolean} props.animate - 애니메이션 활성화
 */
export const Card = ({
    children,
    variant = 'default',
    padding = 'md',
    hoverable = false,
    clickable = false,
    animate = false,
    onClick,
    className,
    sx,
    ...props
}) => {
    // 패딩 크기
    const paddingSizes = {
        sm: 'var(--spacing-sm)',
        md: 'var(--spacing-lg)',
        lg: 'var(--spacing-xl)',
        none: 0,
    };

    // 변형별 스타일
    const variantStyles = {
        default: {
            backgroundColor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            boxShadow: 'var(--shadow-sm)',
        },
        elevated: {
            backgroundColor: 'var(--color-surface-elevated)',
            border: '1px solid var(--color-border-light)',
            boxShadow: 'var(--shadow-lg)',
        },
        glass: {
            background: 'var(--glass-background)',
            backdropFilter: 'var(--glass-blur)',
            WebkitBackdropFilter: 'var(--glass-blur)',
            border: '1px solid var(--glass-border)',
            boxShadow: 'var(--shadow-md)',
        },
        outlined: {
            backgroundColor: 'transparent',
            border: '1px solid var(--color-border)',
            boxShadow: 'none',
        },
    };

    // 호버 효과
    const hoverStyles = hoverable ? {
        transition: 'all var(--transition-normal)',
        '&:hover': {
            transform: 'translateY(-4px)',
            boxShadow: 'var(--shadow-xl)',
            borderColor: 'var(--color-primary)',
        },
    } : {};

    // 클릭 가능 스타일
    const clickableStyles = clickable ? {
        cursor: 'pointer',
        '&:active': {
            transform: 'scale(0.99)',
        },
    } : {};

    const cardContent = (
        <Paper
            elevation={0}
            onClick={onClick}
            className={className}
            sx={{
                borderRadius: 'var(--radius-lg)',
                padding: paddingSizes[padding],
                ...variantStyles[variant],
                ...hoverStyles,
                ...clickableStyles,
                ...sx,
            }}
            {...props}
        >
            {children}
        </Paper>
    );

    // 애니메이션 래퍼
    if (animate) {
        return (
            <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease: 'easeOut' }}
            >
                {cardContent}
            </motion.div>
        );
    }

    return cardContent;
};

/**
 * 카드 헤더 컴포넌트
 */
export const CardHeader = ({ children, action, sx, ...props }) => (
    <Box
        sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 'var(--spacing-md)',
            paddingBottom: 'var(--spacing-md)',
            borderBottom: '1px solid var(--color-divider)',
            ...sx,
        }}
        {...props}
    >
        <Box sx={{ flex: 1 }}>{children}</Box>
        {action && <Box>{action}</Box>}
    </Box>
);

/**
 * 카드 콘텐츠 컴포넌트
 */
export const CardContent = ({ children, sx, ...props }) => (
    <Box sx={sx} {...props}>
        {children}
    </Box>
);

/**
 * 카드 푸터 컴포넌트
 */
export const CardFooter = ({ children, sx, ...props }) => (
    <Box
        sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: 'var(--spacing-sm)',
            marginTop: 'var(--spacing-md)',
            paddingTop: 'var(--spacing-md)',
            borderTop: '1px solid var(--color-divider)',
            ...sx,
        }}
        {...props}
    >
        {children}
    </Box>
);

export default Card;
