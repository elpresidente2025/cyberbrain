// design-system/components/Input.jsx
// 디자인 시스템 입력 필드 컴포넌트

import React from 'react';
import { TextField, InputAdornment, Box, Typography } from '@mui/material';

/**
 * 디자인 시스템 입력 필드 컴포넌트
 * 
 * @param {Object} props
 * @param {string} props.label - 레이블
 * @param {string} props.helperText - 도움말 텍스트
 * @param {string} props.error - 에러 메시지 (있으면 에러 상태)
 * @param {'sm' | 'md' | 'lg'} props.size - 크기
 * @param {React.ReactNode} props.startIcon - 시작 아이콘
 * @param {React.ReactNode} props.endIcon - 끝 아이콘
 */
export const Input = ({
    label,
    placeholder,
    helperText,
    error,
    size = 'md',
    fullWidth = true,
    startIcon,
    endIcon,
    multiline = false,
    rows,
    maxRows,
    type = 'text',
    value,
    onChange,
    onBlur,
    disabled = false,
    required = false,
    name,
    id,
    sx,
    ...props
}) => {
    // 크기별 스타일
    const sizeStyles = {
        sm: {
            '& .MuiInputBase-input': {
                padding: 'var(--spacing-xs) var(--spacing-sm)',
                fontSize: 'var(--font-size-sm)',
            },
        },
        md: {
            '& .MuiInputBase-input': {
                padding: 'var(--spacing-sm) var(--spacing-md)',
                fontSize: 'var(--font-size-base)',
            },
        },
        lg: {
            '& .MuiInputBase-input': {
                padding: 'var(--spacing-md) var(--spacing-lg)',
                fontSize: 'var(--font-size-lg)',
            },
        },
    };

    const hasError = Boolean(error);

    return (
        <TextField
            label={label}
            placeholder={placeholder}
            helperText={error || helperText}
            error={hasError}
            fullWidth={fullWidth}
            multiline={multiline}
            rows={rows}
            maxRows={maxRows}
            type={type}
            value={value}
            onChange={onChange}
            onBlur={onBlur}
            disabled={disabled}
            required={required}
            name={name}
            id={id}
            InputProps={{
                startAdornment: startIcon ? (
                    <InputAdornment position="start">{startIcon}</InputAdornment>
                ) : undefined,
                endAdornment: endIcon ? (
                    <InputAdornment position="end">{endIcon}</InputAdornment>
                ) : undefined,
            }}
            sx={{
                '& .MuiOutlinedInput-root': {
                    fontFamily: 'var(--font-family-sans)',
                    borderRadius: 'var(--radius-md)',
                    backgroundColor: 'var(--color-surface)',
                    transition: 'all var(--transition-fast)',

                    '& fieldset': {
                        borderColor: 'var(--color-border)',
                        transition: 'border-color var(--transition-fast)',
                    },

                    '&:hover fieldset': {
                        borderColor: 'var(--color-primary)',
                    },

                    '&.Mui-focused fieldset': {
                        borderColor: 'var(--color-primary)',
                        borderWidth: '2px',
                    },

                    '&.Mui-error fieldset': {
                        borderColor: 'var(--color-error)',
                    },

                    '&.Mui-disabled': {
                        backgroundColor: 'var(--color-border-light)',
                    },
                },

                '& .MuiInputLabel-root': {
                    fontFamily: 'var(--font-family-sans)',
                    color: 'var(--color-text-secondary)',

                    '&.Mui-focused': {
                        color: 'var(--color-primary)',
                    },

                    '&.Mui-error': {
                        color: 'var(--color-error)',
                    },
                },

                '& .MuiFormHelperText-root': {
                    fontFamily: 'var(--font-family-sans)',
                    marginTop: 'var(--spacing-xxs)',
                    marginLeft: 0,
                },

                ...sizeStyles[size],
                ...sx,
            }}
            {...props}
        />
    );
};

/**
 * 텍스트 영역 컴포넌트 (Input의 multiline 래퍼)
 */
export const TextArea = (props) => (
    <Input multiline rows={4} {...props} />
);

/**
 * 폼 필드 그룹 컴포넌트
 */
export const FormField = ({ label, required, error, helperText, children, sx }) => (
    <Box sx={{ marginBottom: 'var(--spacing-lg)', ...sx }}>
        {label && (
            <Typography
                component="label"
                sx={{
                    display: 'block',
                    marginBottom: 'var(--spacing-xs)',
                    fontSize: 'var(--font-size-sm)',
                    fontWeight: 'var(--font-weight-medium)',
                    color: error ? 'var(--color-error)' : 'var(--color-text-primary)',
                }}
            >
                {label}
                {required && <span style={{ color: 'var(--color-error)', marginLeft: '4px' }}>*</span>}
            </Typography>
        )}
        {children}
        {(helperText || error) && (
            <Typography
                sx={{
                    marginTop: 'var(--spacing-xxs)',
                    fontSize: 'var(--font-size-xs)',
                    color: error ? 'var(--color-error)' : 'var(--color-text-tertiary)',
                }}
            >
                {error || helperText}
            </Typography>
        )}
    </Box>
);

export default Input;
