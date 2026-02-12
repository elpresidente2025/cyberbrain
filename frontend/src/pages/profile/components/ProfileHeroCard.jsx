// frontend/src/pages/profile/components/ProfileHeroCard.jsx
// 프로필 페이지 상단 히어로 카드 (대시보드 UserStatusCard 스타일)

import React from 'react';
import { motion } from 'framer-motion';
import {
    Box,
    Paper,
    Typography,
    Avatar,
    Button,
    LinearProgress
} from '@mui/material';
import {
    Settings,
    LocationOn,
    AutoAwesome,
    CheckCircle,
    WarningAmber
} from '@mui/icons-material';
import { getUserFullTitle, getUserStatusIcon, getUserRegionInfo } from '../../../utils/userUtils';

/**
 * 프로필 완성도 계산
 */
const calcCompletion = (profile, bioEntries) => {
    const checks = [
        { label: '이름', done: !!profile.name },
        { label: '직책', done: !!profile.position },
        { label: '광역시도', done: !!profile.regionMetro },
        { label: '자기소개', done: (profile.bio || '').trim().length >= 10 },
    ];

    // 직책에 따라 추가 필수 항목
    if (profile.position === '기초자치단체장') {
        checks.push({ label: '기초자치단체', done: !!profile.regionLocal });
    } else if (profile.position && profile.position !== '광역자치단체장') {
        checks.push({ label: '기초자치단체', done: !!profile.regionLocal });
        checks.push({ label: '선거구', done: !!profile.electoralDistrict });
    }

    // 선택 항목 (가중치 낮게)
    const optionalChecks = [
        { label: '연령대', done: !!profile.ageDecade },
        { label: '성별', done: !!profile.gender },
        { label: '주요 배경', done: !!profile.backgroundCareer },
        { label: '자기소개 200자+', done: (profile.bio || '').trim().length >= 200 },
        { label: '추가 정보', done: bioEntries.filter(e => e.content?.trim()).length >= 2 },
    ];

    const requiredDone = checks.filter(c => c.done).length;
    const requiredTotal = checks.length;
    const optionalDone = optionalChecks.filter(c => c.done).length;
    const optionalTotal = optionalChecks.length;

    // 필수 70% + 선택 30%
    const percent = Math.round(
        (requiredDone / requiredTotal) * 70 +
        (optionalDone / optionalTotal) * 30
    );

    return { percent, requiredDone, requiredTotal, optionalDone, optionalTotal, checks, optionalChecks };
};

const ProfileHeroCard = ({ user, profile, bioEntries, saving, onPastPostsIndexing }) => {
    const userTitle = getUserFullTitle(user);
    const userIcon = getUserStatusIcon(user);
    const regionInfo = getUserRegionInfo(user);
    const { percent, requiredDone, requiredTotal } = calcCompletion(profile, bioEntries);

    const isComplete = percent >= 90;

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
                    {/* 배경 원형 장식 */}
                    <Box sx={{ position: 'absolute', top: -30, right: -30, width: 120, height: 120, borderRadius: '50%', background: 'rgba(255,255,255,0.08)' }} />
                    <Box sx={{ position: 'absolute', bottom: -40, left: '30%', width: 80, height: 80, borderRadius: '50%', background: 'rgba(255,255,255,0.05)' }} />

                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, position: 'relative', zIndex: 1 }}>
                        <Avatar sx={{
                            width: 64, height: 64,
                            bgcolor: '#ffffff',
                            color: 'var(--color-primary)',
                            fontSize: '1.8rem', fontWeight: 700,
                            boxShadow: 'var(--shadow-lg)'
                        }}>
                            {userIcon}
                        </Avatar>

                        <Box sx={{ flex: 1 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                                <Settings sx={{ fontSize: 20, color: 'rgba(255,255,255,0.8)' }} />
                                <Typography variant="h5" sx={{ fontWeight: 700, color: '#ffffff' }}>
                                    프로필 설정
                                </Typography>
                            </Box>
                            <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.9)' }}>
                                {userTitle || '프로필 정보를 입력해 주세요'}
                            </Typography>
                            {regionInfo && (
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                                    <LocationOn sx={{ fontSize: 14, color: 'rgba(255,255,255,0.7)' }} />
                                    <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.8)' }}>
                                        {regionInfo}
                                    </Typography>
                                </Box>
                            )}
                        </Box>

                        <Button
                            variant="contained"
                            size="small"
                            startIcon={<AutoAwesome />}
                            onClick={onPastPostsIndexing}
                            disabled={saving}
                            sx={{
                                bgcolor: 'rgba(255,255,255,0.2)',
                                color: '#ffffff',
                                backdropFilter: 'blur(4px)',
                                border: '1px solid rgba(255,255,255,0.3)',
                                whiteSpace: 'nowrap',
                                '&:hover': { bgcolor: 'rgba(255,255,255,0.3)' },
                                '&:disabled': { bgcolor: 'rgba(255,255,255,0.1)', color: 'rgba(255,255,255,0.5)' },
                            }}
                        >
                            과거 원고 학습
                        </Button>
                    </Box>
                </Box>

                {/* 프로필 완성도 */}
                <Box sx={{ p: 2.5, bgcolor: 'var(--color-surface-elevated)' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                            {isComplete
                                ? <CheckCircle sx={{ fontSize: 18, color: 'var(--color-success)' }} />
                                : <WarningAmber sx={{ fontSize: 18, color: 'var(--color-warning)' }} />
                            }
                            <Typography variant="body2" sx={{ color: 'var(--color-text-secondary)', fontWeight: 500 }}>
                                프로필 완성도
                            </Typography>
                        </Box>
                        <Typography variant="body2" sx={{
                            fontWeight: 700,
                            color: isComplete ? 'var(--color-success)' : 'var(--color-primary)'
                        }}>
                            {percent}%
                            {requiredDone < requiredTotal && (
                                <Typography component="span" variant="caption" sx={{ ml: 0.5, color: 'var(--color-warning)' }}>
                                    (필수 {requiredDone}/{requiredTotal})
                                </Typography>
                            )}
                        </Typography>
                    </Box>
                    <LinearProgress
                        variant="determinate"
                        value={percent}
                        sx={{
                            height: 8,
                            borderRadius: 4,
                            bgcolor: 'var(--color-border-light)',
                            '& .MuiLinearProgress-bar': {
                                borderRadius: 4,
                                background: isComplete
                                    ? 'linear-gradient(90deg, var(--color-success), #34d399)'
                                    : 'var(--gradient-primary)',
                            }
                        }}
                    />
                    {!isComplete && (
                        <Typography variant="caption" sx={{ color: 'var(--color-text-tertiary)', mt: 0.5, display: 'block' }}>
                            프로필을 더 채우면 원고 품질이 향상됩니다
                        </Typography>
                    )}
                </Box>
            </Paper>
        </motion.div>
    );
};

export default ProfileHeroCard;
