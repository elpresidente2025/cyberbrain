// frontend/src/pages/billing/components/RefundPolicyCard.jsx
// 환불 정책 카드

import React from 'react';
import { Paper, Typography, List, ListItem, ListItemText } from '@mui/material';
import { Warning } from '@mui/icons-material';

const REFUND_ITEMS = [
    '구매일로부터 7일 이내: 전액 환불 가능',
    '원고 생성 이용 후: 미사용 횟수만큼 일할 계산하여 환불',
    '환불 요청 시 7영업일 이내 처리 완료',
];

const RefundPolicyCard = () => {
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
            <Typography variant="h6" sx={{ mb: 1.5, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Warning sx={{ color: 'var(--color-warning)' }} />
                환불 정책
            </Typography>
            <List dense disablePadding>
                {REFUND_ITEMS.map((text) => (
                    <ListItem key={text} sx={{ px: 0 }}>
                        <ListItemText
                            primary={text}
                            primaryTypographyProps={{ variant: 'body2' }}
                        />
                    </ListItem>
                ))}
            </List>
        </Paper>
    );
};

export default RefundPolicyCard;
