// frontend/src/pages/billing/components/SubscriptionCTA.jsx
// 미구독자용 CTA 카드

import React from 'react';
import { Box, Paper, Typography, Button } from '@mui/material';

const SubscriptionCTA = ({ planInfo, testMode, onSubscribe }) => {
    return (
        <Paper
            elevation={0}
            data-force-light
            sx={{
                p: 3,
                background: 'var(--gradient-primary)',
                color: '#ffffff',
                textAlign: 'center',
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--color-border)',
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
            }}
        >
            <Typography variant="h4" sx={{ fontWeight: 700, mb: 2, color: '#ffffff' }}>
                더 많은 주민과 소통하세요
            </Typography>
            <Typography variant="h5" sx={{ mb: 0.5, fontWeight: 700, color: '#ffffff' }}>
                {planInfo.price.toLocaleString()}원/월
            </Typography>
            <Typography variant="body1" sx={{ mb: 3, color: 'rgba(255,255,255,0.9)' }}>
                {testMode ? '정식 출시 예정' : `VAT 포함 · 월 ${planInfo.monthlyLimit}회 원고 생성`}
            </Typography>
            <Button
                variant="contained"
                size="large"
                onClick={onSubscribe}
                disabled={testMode}
                sx={{
                    bgcolor: testMode ? 'rgba(255,255,255,0.3)' : '#ffffff',
                    color: testMode ? 'rgba(255,255,255,0.7)' : 'var(--color-primary)',
                    fontSize: '1.1rem',
                    fontWeight: 700,
                    py: 1.5, px: 4,
                    '&:hover': { bgcolor: testMode ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.9)' },
                    '&.Mui-disabled': { bgcolor: 'rgba(255,255,255,0.2)', color: 'rgba(255,255,255,0.5)' },
                }}
            >
                {testMode ? '준비 중' : '구독'}
            </Button>
        </Paper>
    );
};

export default SubscriptionCTA;
