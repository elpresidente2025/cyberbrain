// frontend/src/pages/billing/components/SubscriptionInfoCard.jsx
// 구독 정보 카드 (구독 중인 사용자 전용)

import React from 'react';
import { Box, Paper, Typography, Divider } from '@mui/material';
import { CreditCard } from '@mui/icons-material';

const SubscriptionInfoCard = ({ user, planInfo }) => {
    const nextBilling = user?.nextBillingDate?.toDate?.() ||
        new Date(new Date().getFullYear(), new Date().getMonth() + 1, 1);
    const dateStr = nextBilling.toLocaleDateString('ko-KR', {
        year: 'numeric', month: 'long', day: 'numeric',
    });

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
            <Typography variant="h6" sx={{ mb: 1.5, display: 'flex', alignItems: 'center', gap: 1, fontWeight: 600 }}>
                <CreditCard sx={{ color: 'var(--color-primary)' }} />
                구독 정보
            </Typography>
            <Box sx={{ mb: 1.5 }}>
                <Typography variant="h5" sx={{ fontWeight: 700, color: 'var(--color-primary)', mb: 0.5 }}>
                    {planInfo.name}
                </Typography>
                <Typography variant="h6">
                    {planInfo.price.toLocaleString()}원/월
                </Typography>
                <Typography variant="body2" sx={{ color: 'var(--color-text-secondary)' }}>
                    VAT 포함
                </Typography>
            </Box>
            <Divider sx={{ my: 1.5 }} />
            <Typography variant="subtitle2" sx={{ color: 'var(--color-text-secondary)', mb: 0.5 }}>
                다음 결제일
            </Typography>
            <Typography variant="body1" sx={{ fontWeight: 700 }}>
                {dateStr}
            </Typography>
        </Paper>
    );
};

export default SubscriptionInfoCard;
