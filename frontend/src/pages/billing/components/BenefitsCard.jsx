// frontend/src/pages/billing/components/BenefitsCard.jsx
// 포함된 혜택 카드

import React from 'react';
import { Paper, Typography, List, ListItem, ListItemIcon, ListItemText } from '@mui/material';
import { CheckCircle } from '@mui/icons-material';

const BENEFITS = [
    {
        primary: '월 90회 원고 생성',
        secondary: '지역구 주민과 소통할 양질의 콘텐츠를 충분히 생성하세요',
    },
    {
        primary: 'SNS 원고 무료 생성',
        secondary: '블로그 원고를 Instagram, Facebook 등 SNS용으로 자동 변환',
    },
    {
        primary: '최대 3회 재생성',
        secondary: '동일 주제에 대해 최대 3번까지 다른 버전을 생성할 수 있습니다',
    },
];

const BenefitsCard = () => {
    return (
        <Paper
            elevation={0}
            sx={{
                p: 2.5,
                height: '100%',
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--color-border)',
                transition: 'box-shadow var(--transition-normal)',
                '&:hover': { boxShadow: 'var(--shadow-md)' },
            }}
        >
            <Typography variant="h6" sx={{ mb: 1.5, fontWeight: 700 }}>
                포함된 혜택
            </Typography>
            <List disablePadding>
                {BENEFITS.map((item) => (
                    <ListItem key={item.primary} sx={{ px: 0 }}>
                        <ListItemIcon sx={{ minWidth: 36 }}>
                            <CheckCircle sx={{ color: 'var(--color-primary)' }} />
                        </ListItemIcon>
                        <ListItemText
                            primary={item.primary}
                            secondary={item.secondary}
                            primaryTypographyProps={{ fontWeight: 600 }}
                        />
                    </ListItem>
                ))}
            </List>
        </Paper>
    );
};

export default BenefitsCard;
