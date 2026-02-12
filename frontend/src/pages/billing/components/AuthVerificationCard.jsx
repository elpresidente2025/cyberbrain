// frontend/src/pages/billing/components/AuthVerificationCard.jsx
// 당원 인증 카드 (구독/미구독 모두 사용)

import React from 'react';
import { Box, Paper, Typography, Button, Alert } from '@mui/material';
import { VerifiedUser, CheckCircle, Schedule, Upload } from '@mui/icons-material';

const AuthVerificationCard = ({ authStatus, onAuthClick, compact = false }) => {
    const statusColor = {
        active: 'var(--color-success)',
        pending: 'var(--color-warning)',
        warning: 'var(--color-primary)',
    };

    return (
        <Paper
            elevation={0}
            sx={{
                p: 2.5,
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: 2,
                borderRadius: 'var(--radius-lg)',
                border: '1px solid var(--color-border)',
                transition: 'box-shadow var(--transition-normal)',
                '&:hover': { boxShadow: 'var(--shadow-md)' },
            }}
        >
            <Box sx={{ flex: 1 }}>
                <Typography variant="h6" sx={{ mb: 1.5, display: 'flex', alignItems: 'center', gap: 1, fontWeight: 600 }}>
                    <VerifiedUser sx={{ color: statusColor[authStatus.status] }} />
                    당원 인증
                </Typography>

                {compact && authStatus.status !== 'warning' && (
                    <Alert
                        severity={authStatus.status === 'active' ? 'success' : 'info'}
                        sx={{ mb: 1.5, '& .MuiAlert-message': { fontSize: '0.8rem' } }}
                    >
                        <Typography variant="body2" sx={{ fontWeight: 600 }}>
                            {authStatus.title}
                        </Typography>
                        {authStatus.message && (
                            <Typography variant="caption">{authStatus.message}</Typography>
                        )}
                    </Alert>
                )}

                {!compact && (
                    <Typography variant="body2" sx={{ mb: 1.5, color: 'var(--color-text-secondary)' }}>
                        더불어민주당 당원 인증을 완료하시면 서비스를 이용하실 수 있습니다.
                    </Typography>
                )}

                <Button
                    variant="contained"
                    onClick={onAuthClick}
                    startIcon={
                        authStatus.status === 'active' ? <CheckCircle /> :
                        authStatus.status === 'pending' ? <Schedule /> : <Upload />
                    }
                    fullWidth
                    disabled={authStatus.status === 'active' || authStatus.status === 'pending'}
                    sx={{
                        bgcolor: statusColor[authStatus.status],
                        color: '#ffffff',
                        fontWeight: 600,
                        '&:hover': {
                            bgcolor: statusColor[authStatus.status],
                            filter: (authStatus.status === 'active' || authStatus.status === 'pending') ? 'none' : 'brightness(0.9)',
                        },
                        '&.Mui-disabled': {
                            bgcolor: `${statusColor[authStatus.status]} !important`,
                            color: 'rgba(255,255,255,0.9) !important',
                        },
                    }}
                >
                    {authStatus.status === 'active' ? '인증 완료' : authStatus.status === 'pending' ? '검토 대기 중' : '당원 인증하기'}
                </Button>
            </Box>

            <Box
                component="img"
                src={authStatus.image}
                alt={authStatus.title}
                sx={{
                    width: compact ? 100 : 140,
                    height: 'auto',
                    filter: 'drop-shadow(0 2px 8px rgba(0,0,0,0.15))',
                    flexShrink: 0,
                }}
            />
        </Paper>
    );
};

export default AuthVerificationCard;
