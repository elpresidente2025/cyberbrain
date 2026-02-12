// frontend/src/pages/profile/components/SectionCard.jsx
// 접이식 섹션 카드 (Accordion 스타일)

import React, { useState } from 'react';
import {
    Box,
    Paper,
    Typography,
    IconButton,
    Collapse
} from '@mui/material';
import { ExpandMore, ExpandLess } from '@mui/icons-material';

const SectionCard = ({
    icon,
    title,
    subtitle,
    titleColor = 'var(--color-text-primary)',
    children,
    defaultOpen = true,
    action,
    noPadding = false,
}) => {
    const [open, setOpen] = useState(defaultOpen);

    return (
        <Paper
            elevation={0}
            sx={{
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--color-border)',
                overflow: 'hidden',
                transition: 'box-shadow var(--transition-normal)',
                '&:hover': { boxShadow: 'var(--shadow-md)' },
            }}
        >
            {/* 헤더 */}
            <Box
                onClick={() => setOpen(prev => !prev)}
                sx={{
                    px: 2.5,
                    py: 2,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    cursor: 'pointer',
                    bgcolor: open ? 'var(--color-surface)' : 'transparent',
                    borderBottom: open ? '1px solid var(--color-border-light)' : 'none',
                    transition: 'background-color var(--transition-fast)',
                    '&:hover': { bgcolor: 'var(--color-primary-lighter)' },
                }}
            >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flex: 1 }}>
                    {icon && (
                        <Box sx={{ color: titleColor, display: 'flex', alignItems: 'center' }}>
                            {icon}
                        </Box>
                    )}
                    <Box>
                        <Typography variant="subtitle1" sx={{ fontWeight: 600, color: titleColor, lineHeight: 1.3 }}>
                            {title}
                        </Typography>
                        {subtitle && (
                            <Typography variant="caption" sx={{ color: 'var(--color-text-tertiary)' }}>
                                {subtitle}
                            </Typography>
                        )}
                    </Box>
                </Box>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    {action && <Box onClick={(e) => e.stopPropagation()}>{action}</Box>}
                    <IconButton size="small" sx={{ color: 'var(--color-text-tertiary)' }}>
                        {open ? <ExpandLess /> : <ExpandMore />}
                    </IconButton>
                </Box>
            </Box>

            {/* 콘텐츠 */}
            <Collapse in={open}>
                <Box sx={{ p: noPadding ? 0 : 2.5 }}>
                    {children}
                </Box>
            </Collapse>
        </Paper>
    );
};

export default SectionCard;
