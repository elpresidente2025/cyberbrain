// design-system/tokens.js
// CSS Variables를 JS에서 참조할 수 있는 토큰 객체

export const tokens = {
    colors: {
        primary: 'var(--color-primary)',
        primaryHover: 'var(--color-primary-hover)',
        primaryLight: 'var(--color-primary-light)',
        secondary: 'var(--color-secondary)',
        secondaryHover: 'var(--color-secondary-hover)',
        accent: 'var(--color-accent)',
        accentGlow: 'var(--color-accent-glow)',
        gold: 'var(--color-gold)',

        success: 'var(--color-success)',
        successLight: 'var(--color-success-light)',
        warning: 'var(--color-warning)',
        warningLight: 'var(--color-warning-light)',
        error: 'var(--color-error)',
        errorLight: 'var(--color-error-light)',
        info: 'var(--color-info)',
        infoLight: 'var(--color-info-light)',

        background: 'var(--color-background)',
        surface: 'var(--color-surface)',
        surfaceElevated: 'var(--color-surface-elevated)',
        border: 'var(--color-border)',
        borderLight: 'var(--color-border-light)',
        divider: 'var(--color-divider)',

        textPrimary: 'var(--color-text-primary)',
        textSecondary: 'var(--color-text-secondary)',
        textTertiary: 'var(--color-text-tertiary)',
        textInverse: 'var(--color-text-inverse)',
    },

    spacing: {
        xxs: 'var(--spacing-xxs)',
        xs: 'var(--spacing-xs)',
        sm: 'var(--spacing-sm)',
        md: 'var(--spacing-md)',
        lg: 'var(--spacing-lg)',
        xl: 'var(--spacing-xl)',
        '2xl': 'var(--spacing-2xl)',
        '3xl': 'var(--spacing-3xl)',
        '4xl': 'var(--spacing-4xl)',
    },

    radius: {
        none: 'var(--radius-none)',
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
        '2xl': 'var(--radius-2xl)',
        full: 'var(--radius-full)',
    },

    shadows: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
        xl: 'var(--shadow-xl)',
        glowPrimary: 'var(--shadow-glow-primary)',
        glowAccent: 'var(--shadow-glow-accent)',
    },

    glass: {
        background: 'var(--glass-background)',
        border: 'var(--glass-border)',
        blur: 'var(--glass-blur)',
    },

    transitions: {
        fast: 'var(--transition-fast)',
        normal: 'var(--transition-normal)',
        slow: 'var(--transition-slow)',
        colors: 'var(--transition-colors)',
    },

    zIndex: {
        base: 'var(--z-base)',
        dropdown: 'var(--z-dropdown)',
        sticky: 'var(--z-sticky)',
        fixed: 'var(--z-fixed)',
        modalBackdrop: 'var(--z-modal-backdrop)',
        modal: 'var(--z-modal)',
        popover: 'var(--z-popover)',
        tooltip: 'var(--z-tooltip)',
    },
};

// 실제 값 (MUI 테마 등에서 필요할 때 사용)
export const rawTokens = {
    colors: {
        primary: '#152484',
        primaryHover: '#1e3a8a',
        secondary: '#0891b2',
        accent: '#00d4ff',
        gold: '#f8c023',
        success: '#10b981',
        warning: '#f59e0b',
        error: '#ef4444',
        info: '#3b82f6',
    },

    spacing: {
        xxs: 4,
        xs: 8,
        sm: 12,
        md: 16,
        lg: 24,
        xl: 32,
        '2xl': 48,
        '3xl': 64,
        '4xl': 96,
    },

    radius: {
        none: 0,
        sm: 4,
        md: 8,
        lg: 12,
        xl: 16,
        '2xl': 24,
        full: 9999,
    },
};
