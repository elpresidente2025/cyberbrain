// design-system/components/Typography.jsx
// 디자인 시스템 타이포그래피 컴포넌트

import React from 'react';
import { Typography as MuiTypography, Box } from '@mui/material';

/**
 * 타이포그래피 변형별 스타일 정의
 */
const textStyles = {
    // 제목들
    h1: {
        fontSize: 'var(--font-size-5xl)',
        fontWeight: 'var(--font-weight-bold)',
        lineHeight: 'var(--line-height-tight)',
        letterSpacing: '-0.025em',
    },
    h2: {
        fontSize: 'var(--font-size-4xl)',
        fontWeight: 'var(--font-weight-bold)',
        lineHeight: 'var(--line-height-tight)',
        letterSpacing: '-0.02em',
    },
    h3: {
        fontSize: 'var(--font-size-3xl)',
        fontWeight: 'var(--font-weight-semibold)',
        lineHeight: 'var(--line-height-snug)',
        letterSpacing: '-0.015em',
    },
    h4: {
        fontSize: 'var(--font-size-2xl)',
        fontWeight: 'var(--font-weight-semibold)',
        lineHeight: 'var(--line-height-snug)',
    },
    h5: {
        fontSize: 'var(--font-size-xl)',
        fontWeight: 'var(--font-weight-semibold)',
        lineHeight: 'var(--line-height-normal)',
    },
    h6: {
        fontSize: 'var(--font-size-lg)',
        fontWeight: 'var(--font-weight-semibold)',
        lineHeight: 'var(--line-height-normal)',
    },

    // 본문
    body1: {
        fontSize: 'var(--font-size-base)',
        fontWeight: 'var(--font-weight-normal)',
        lineHeight: 'var(--line-height-relaxed)',
    },
    body2: {
        fontSize: 'var(--font-size-sm)',
        fontWeight: 'var(--font-weight-normal)',
        lineHeight: 'var(--line-height-relaxed)',
    },

    // 기타
    caption: {
        fontSize: 'var(--font-size-xs)',
        fontWeight: 'var(--font-weight-normal)',
        lineHeight: 'var(--line-height-normal)',
        color: 'var(--color-text-tertiary)',
    },
    overline: {
        fontSize: 'var(--font-size-xs)',
        fontWeight: 'var(--font-weight-semibold)',
        lineHeight: 'var(--line-height-normal)',
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
        color: 'var(--color-text-secondary)',
    },
    label: {
        fontSize: 'var(--font-size-sm)',
        fontWeight: 'var(--font-weight-medium)',
        lineHeight: 'var(--line-height-normal)',
    },
};

/**
 * 디자인 시스템 타이포그래피 컴포넌트
 * 
 * @param {Object} props
 * @param {'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6' | 'body1' | 'body2' | 'caption' | 'overline' | 'label'} props.variant
 * @param {'primary' | 'secondary' | 'tertiary' | 'inverse' | 'success' | 'warning' | 'error'} props.color
 * @param {boolean} props.gradient - 그라데이션 텍스트
 * @param {boolean} props.truncate - 텍스트 말줄임
 * @param {number} props.lines - 최대 줄 수 (말줄임)
 */
export const Typography = ({
    children,
    variant = 'body1',
    color = 'primary',
    gradient = false,
    truncate = false,
    lines,
    component,
    align,
    sx,
    ...props
}) => {
    // 색상 매핑
    const colorMap = {
        primary: 'var(--color-text-primary)',
        secondary: 'var(--color-text-secondary)',
        tertiary: 'var(--color-text-tertiary)',
        inverse: 'var(--color-text-inverse)',
        success: 'var(--color-success)',
        warning: 'var(--color-warning)',
        error: 'var(--color-error)',
        inherit: 'inherit',
    };

    // 컴포넌트 태그 매핑
    const componentMap = {
        h1: 'h1',
        h2: 'h2',
        h3: 'h3',
        h4: 'h4',
        h5: 'h5',
        h6: 'h6',
        body1: 'p',
        body2: 'p',
        caption: 'span',
        overline: 'span',
        label: 'label',
    };

    // 줄 수 제한 스타일
    const truncateStyles = truncate ? {
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        ...(lines ? {
            display: '-webkit-box',
            WebkitLineClamp: lines,
            WebkitBoxOrient: 'vertical',
        } : {
            whiteSpace: 'nowrap',
        }),
    } : {};

    // 그라데이션 스타일
    const gradientStyles = gradient ? {
        background: 'linear-gradient(135deg, var(--color-primary), var(--color-accent))',
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        backgroundClip: 'text',
    } : {};

    return (
        <MuiTypography
            component={component || componentMap[variant]}
            align={align}
            sx={{
                fontFamily: 'var(--font-family-sans)',
                color: gradient ? undefined : colorMap[color],
                ...textStyles[variant],
                ...truncateStyles,
                ...gradientStyles,
                ...sx,
            }}
            {...props}
        >
            {children}
        </MuiTypography>
    );
};

/**
 * 섹션 제목 컴포넌트
 */
export const SectionTitle = ({
    title,
    subtitle,
    align = 'center',
    gradient = false,
    sx,
    ...props
}) => (
    <Box
        sx={{
            textAlign: align,
            marginBottom: 'var(--spacing-2xl)',
            ...sx
        }}
        {...props}
    >
        <Typography
            variant="h2"
            gradient={gradient}
            sx={{ marginBottom: subtitle ? 'var(--spacing-md)' : 0 }}
        >
            {title}
        </Typography>
        {subtitle && (
            <Typography variant="body1" color="secondary">
                {subtitle}
            </Typography>
        )}
    </Box>
);

/**
 * 그라데이션 텍스트 컴포넌트
 */
export const GradientText = ({ children, variant = 'h2', ...props }) => (
    <Typography variant={variant} gradient {...props}>
        {children}
    </Typography>
);

export default Typography;
