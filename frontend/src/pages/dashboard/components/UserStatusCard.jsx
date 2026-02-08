// frontend/src/pages/dashboard/components/UserStatusCard.jsx
// 사용자 상태 및 플랜 정보 카드

import React from 'react';
import { motion } from 'framer-motion';
import {
    Box,
    Paper,
    Typography,
    Button,
    Avatar,
    LinearProgress
} from '@mui/material';
import {
    Create,
    LocationOn,
    Star,
    TrendingUp
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { getUserFullTitle, getUserStatusIcon, getUserRegionInfo } from '../../../utils/userUtils';

const UserStatusCard = ({
    user,
    usage,
    isAdmin,
    isTester,
    canGeneratePost,
    showBioAlert,
    onGeneratePost
}) => {
    const navigate = useNavigate();

    const userTitle = getUserFullTitle(user);
    const userIcon = getUserStatusIcon(user);
    const regionInfo = getUserRegionInfo(user);

    const usagePercentage = isAdmin ? 100 :
        usage.monthlyLimit > 0 ? (usage.postsGenerated / usage.monthlyLimit) * 100 : 0;

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
                    border: '1px solid',
                    borderColor: 'var(--color-primary-light)',
                    boxShadow: 'var(--shadow-md)'
                }}
            >
                {/* 상단 프로필 영역 */}
                <Box
                    sx={{
                        p: 3,
                        background: 'var(--gradient-primary)',
                        color: '#ffffff',
                        position: 'relative',
                        overflow: 'hidden'
                    }}
                >
                    {/* 장식용 원형 패턴 */}
                    <Box sx={{
                        position: 'absolute',
                        top: -30,
                        right: -30,
                        width: 120,
                        height: 120,
                        borderRadius: '50%',
                        background: 'rgba(255,255,255,0.08)',
                        zIndex: 0
                    }} />
                    <Box sx={{
                        position: 'absolute',
                        bottom: -40,
                        left: '30%',
                        width: 80,
                        height: 80,
                        borderRadius: '50%',
                        background: 'rgba(255,255,255,0.05)',
                        zIndex: 0
                    }} />

                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, position: 'relative', zIndex: 1 }}>
                        <Avatar
                            sx={{
                                width: 72,
                                height: 72,
                                bgcolor: '#ffffff',
                                color: 'var(--color-primary)',
                                fontSize: '2.2rem',
                                fontWeight: 700,
                                boxShadow: 'var(--shadow-lg)'
                            }}
                        >
                            {userIcon}
                        </Avatar>
                        <Box sx={{ flex: 1 }}>
                            <Typography
                                variant="h5"
                                sx={{
                                    fontWeight: 700,
                                    color: '#ffffff',
                                    mb: 0.5
                                }}
                            >
                                {userTitle}
                            </Typography>
                            {regionInfo && (
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                    <LocationOn sx={{ fontSize: 16, color: 'rgba(255,255,255,0.8)' }} />
                                    <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.9)' }}>
                                        {regionInfo}
                                    </Typography>
                                </Box>
                            )}
                        </Box>

                        {/* 플랜 배지 */}
                        <Box
                            sx={{
                                px: 2,
                                py: 0.8,
                                borderRadius: 'var(--radius-full)',
                                bgcolor: 'rgba(255,255,255,0.2)',
                                backdropFilter: 'blur(4px)',
                                border: '1px solid rgba(255,255,255,0.3)',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 0.5
                            }}
                        >
                            <Star sx={{ fontSize: 18, color: isAdmin ? 'var(--color-gold)' : '#ffffff' }} />
                            <Typography variant="body2" sx={{ fontWeight: 600, color: '#ffffff' }}>
                                {isAdmin ? '관리자' : isTester ? '테스터' : 'Pro 플랜'}
                            </Typography>
                        </Box>
                    </Box>
                </Box>

                {/* 하단 사용량 및 CTA 영역 */}
                <Box sx={{ p: 3, bgcolor: 'var(--color-surface-elevated)' }}>
                    {/* 사용량 진행률 */}
                    {!isAdmin && (
                        <Box sx={{ mb: 3 }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1.5 }}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                    <TrendingUp sx={{ fontSize: 18, color: 'var(--color-primary)' }} />
                                    <Typography variant="body2" sx={{ color: 'var(--color-text-secondary)' }}>
                                        이번 달 사용량
                                    </Typography>
                                </Box>
                                <Typography variant="body2" sx={{ fontWeight: 700, color: 'var(--color-primary)' }}>
                                    {usage.postsGenerated} / {usage.monthlyLimit}건
                                </Typography>
                            </Box>
                            <LinearProgress
                                variant="determinate"
                                value={Math.min(usagePercentage, 100)}
                                sx={{
                                    height: 10,
                                    borderRadius: 'var(--radius-full)',
                                    bgcolor: 'var(--color-primary-lighter)',
                                    '& .MuiLinearProgress-bar': {
                                        borderRadius: 'var(--radius-full)',
                                        background: 'var(--gradient-primary)'
                                    }
                                }}
                            />
                        </Box>
                    )}

                    {/* Bio 경고 알림 */}
                    {showBioAlert && (
                        <Box
                            sx={{
                                p: 2,
                                mb: 3,
                                borderRadius: 'var(--radius-lg)',
                                bgcolor: 'var(--color-warning-light)',
                                border: '1px solid var(--color-warning)'
                            }}
                        >
                            <Typography variant="body2" sx={{ color: 'var(--color-text-primary)' }}>
                                자기소개를 작성해야 원고 생성이 가능합니다.
                                <Button
                                    size="small"
                                    onClick={() => navigate('/profile')}
                                    sx={{ ml: 1, color: 'var(--color-warning)', fontWeight: 600 }}
                                >
                                    프로필 작성하기
                                </Button>
                            </Typography>
                        </Box>
                    )}

                    {/* CTA 버튼 */}
                    <Button
                        variant="contained"
                        size="large"
                        fullWidth
                        startIcon={<Create />}
                        disabled={!canGeneratePost}
                        onClick={onGeneratePost}
                        sx={{
                            py: 2,
                            fontSize: '1.1rem',
                            fontWeight: 700,
                            background: 'var(--gradient-primary-dark)',
                            color: '#ffffff',
                            borderRadius: 'var(--radius-lg)',
                            boxShadow: 'var(--shadow-glow-primary)',
                            transition: 'all var(--transition-normal)',
                            border: 'none',
                            '&:hover': {
                                background: 'var(--gradient-primary)',
                                transform: 'translateY(-2px)',
                                boxShadow: 'var(--shadow-xl)'
                            },
                            '&:disabled': {
                                background: 'var(--color-border)',
                                color: 'var(--color-text-tertiary)',
                                boxShadow: 'none'
                            }
                        }}
                    >
                        새 원고 생성하기
                    </Button>
                </Box>
            </Paper>
        </motion.div>
    );
};

export default UserStatusCard;
