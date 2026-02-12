// frontend/src/pages/billing/components/PaymentHistoryCard.jsx
// 결제 내역 카드

import React from 'react';
import { Paper, Typography } from '@mui/material';
import { Payment } from '@mui/icons-material';

const PaymentHistoryCard = () => {
    return (
        <Paper
            elevation={0}
            sx={{
                p: 2.5,
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--color-border)',
                transition: 'box-shadow var(--transition-normal)',
                '&:hover': { boxShadow: 'var(--shadow-md)' },
            }}
        >
            <Typography variant="h6" sx={{ mb: 1, display: 'flex', alignItems: 'center', gap: 1, fontWeight: 600 }}>
                <Payment />
                결제 내역
            </Typography>
            <Typography variant="body2" sx={{ color: 'var(--color-text-secondary)', mb: 1.5 }}>
                최근 결제 내역을 확인할 수 있습니다.
            </Typography>
            <Typography variant="body2" sx={{ color: 'var(--color-text-tertiary)', textAlign: 'center', py: 4 }}>
                결제 내역이 없습니다
            </Typography>
        </Paper>
    );
};

export default PaymentHistoryCard;
