// frontend/src/pages/billing/components/BillingHeroCard.jsx
// 결제 페이지 상단 히어로 카드

import React from 'react';
import { motion } from 'framer-motion';
import { Box, Paper, Typography, Avatar, Switch, FormControlLabel } from '@mui/material';
import { CreditCard, CheckCircle, WarningAmber } from '@mui/icons-material';

const BillingHeroCard = ({ isSubscribed, isAdmin, adminOverrideSubscription, user, onAdminToggle }) => {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
        >
            <Paper
                elevation={0}
                sx={{
                    overflow: 'hidden',
                    borderRadius: 'var(--radius-xl)',
                    mb: 3,
                    border: '1px solid var(--color-primary-light)',
                    boxShadow: 'var(--shadow-md)',
                }}
            >
                {/* 그래디언트 헤더 */}
                <Box
                    data-force-light
                    sx={{
                        p: 3,
                        background: 'var(--gradient-primary)',
                        color: '#ffffff',
                        position: 'relative',
                        overflow: 'hidden',
                    }}
                >
                    <Box sx={{ position: 'absolute', top: -30, right: -30, width: 120, height: 120, borderRadius: '50%', background: 'rgba(255,255,255,0.08)' }} />
                    <Box sx={{ position: 'absolute', bottom: -40, left: '30%', width: 80, height: 80, borderRadius: '50%', background: 'rgba(255,255,255,0.05)' }} />

                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, position: 'relative', zIndex: 1 }}>
                        <Avatar sx={{
                            width: 64, height: 64,
                            bgcolor: '#ffffff',
                            color: 'var(--color-primary)',
                            fontSize: '1.8rem', fontWeight: 700,
                            boxShadow: 'var(--shadow-lg)',
                        }}>
                            <CreditCard sx={{ fontSize: 32 }} />
                        </Avatar>

                        <Box sx={{ flex: 1 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                                <Typography variant="h5" sx={{ fontWeight: 700, color: '#ffffff' }}>
                                    결제 및 인증
                                </Typography>
                            </Box>
                            <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.9)' }}>
                                {isSubscribed ? '구독 정보와 당원 인증을 관리하세요' : '구독과 당원 인증으로 서비스를 이용하세요'}
                            </Typography>
                        </Box>

                        {/* 구독 상태 배지 */}
                        <Box sx={{
                            display: 'flex', alignItems: 'center', gap: 0.5,
                            bgcolor: isSubscribed ? 'rgba(255,255,255,0.2)' : 'rgba(255,255,255,0.1)',
                            px: 2, py: 0.75, borderRadius: 'var(--radius-full)',
                            border: '1px solid rgba(255,255,255,0.3)',
                        }}>
                            {isSubscribed
                                ? <CheckCircle sx={{ fontSize: 18, color: '#4ade80' }} />
                                : <WarningAmber sx={{ fontSize: 18, color: '#fbbf24' }} />
                            }
                            <Typography variant="body2" sx={{ color: '#ffffff', fontWeight: 600 }}>
                                {isSubscribed ? '구독 중' : '미구독'}
                            </Typography>
                        </Box>
                    </Box>
                </Box>

                {/* 관리자 토글 */}
                {isAdmin && (
                    <Box sx={{ px: 2.5, py: 1, bgcolor: 'var(--color-surface-elevated)', borderTop: '1px solid var(--color-border-light)' }}>
                        <FormControlLabel
                            control={
                                <Switch
                                    checked={adminOverrideSubscription !== null ? adminOverrideSubscription : (user?.subscriptionStatus === 'active')}
                                    onChange={(e) => onAdminToggle(e.target.checked)}
                                    size="small"
                                />
                            }
                            label={
                                <Typography variant="caption" sx={{ color: 'var(--color-text-tertiary)' }}>
                                    관리자: {isSubscribed ? '구독 모드' : '미구독 모드'}
                                </Typography>
                            }
                        />
                    </Box>
                )}
            </Paper>
        </motion.div>
    );
};

export default BillingHeroCard;
