// frontend/src/pages/dashboard/components/UserStatusCard.jsx
// 사용자 상태 및 플랜 정보 카드 + 7-세그먼트 사용량 게이지 통합

import React from 'react';
import { motion } from 'framer-motion';
import {
    Box,
    Paper,
    Typography,
    Button,
    Avatar
} from '@mui/material';
import {
    Create,
    LocationOn,
    Star,
    TrendingUp,
    EmojiEvents
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { getUserFullTitle, getUserStatusIcon, getUserRegionInfo } from '../../../utils/userUtils';
import { useColor } from '../../../contexts/ColorContext';

// 7-세그먼트 숫자 컴포넌트
const SevenSegmentNumber = ({ number, color }) => {
    const digitPatterns = {
        '0': [1,1,1,1,1,1,0], '1': [0,1,1,0,0,0,0], '2': [1,1,0,1,1,0,1],
        '3': [1,1,1,1,0,0,1], '4': [0,1,1,0,0,1,1], '5': [1,0,1,1,0,1,1],
        '6': [1,0,1,1,1,1,1], '7': [1,1,1,0,0,0,0], '8': [1,1,1,1,1,1,1],
        '9': [1,1,1,1,0,1,1], ' ': [0,0,0,0,0,0,0]
    };
    const segments = {
        a: { top: '1px', left: '2px', width: '12px', height: '2px' },
        b: { top: '3px', right: '1px', width: '2px', height: '10px' },
        c: { bottom: '3px', right: '1px', width: '2px', height: '10px' },
        d: { bottom: '1px', left: '2px', width: '12px', height: '2px' },
        e: { bottom: '3px', left: '1px', width: '2px', height: '10px' },
        f: { top: '3px', left: '1px', width: '2px', height: '10px' },
        g: { top: '50%', left: '2px', width: '12px', height: '2px', transform: 'translateY(-50%)' }
    };
    const numberStr = number.toString().padStart(3, ' ');
    const segmentIds = ['a','b','c','d','e','f','g'];

    return (
        <Box sx={{ display: 'flex', gap: '2px' }}>
            {numberStr.split('').map((digit, di) => {
                const pattern = digitPatterns[digit] || digitPatterns['0'];
                return (
                    <Box key={di} sx={{ position: 'relative', width: '16px', height: '28px' }}>
                        {segmentIds.map((sid, i) => (
                            <Box key={sid} sx={{
                                position: 'absolute',
                                backgroundColor: pattern[i] === 1 ? color : '#333',
                                borderRadius: '1px',
                                opacity: pattern[i] === 1 ? 1 : 0.2,
                                boxShadow: pattern[i] === 1 ? `0 0 6px ${color}` : 'none',
                                transition: 'background-color 0.8s ease, box-shadow 0.8s ease',
                                ...segments[sid]
                            }} />
                        ))}
                    </Box>
                );
            })}
        </Box>
    );
};

// 칸 단위 게이지
const CellGauge = ({ published, target, color }) => (
    <Box sx={{
        display: 'flex', gap: '2px', height: 16,
        backgroundColor: '#0a0a0a', border: '1px solid #333',
        borderRadius: 2, padding: '2px',
        boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.3)'
    }}>
        {Array.from({ length: target }, (_, i) => {
            const isFilled = i < published;
            const isNext = i === published;
            return (
                <Box key={i} sx={{
                    flex: 1, height: '100%', borderRadius: '1px',
                    backgroundColor: isFilled ? color : isNext ? color : 'rgba(255,255,255,0.1)',
                    opacity: isFilled ? 1 : isNext ? 0.5 : 1,
                    boxShadow: isFilled ? `0 0 4px ${color}` : 'none',
                    transition: 'all 0.3s ease',
                    animation: isNext ? 'cellBlink 1.5s infinite ease-in-out' : 'none',
                    '@keyframes cellBlink': {
                        '0%, 100%': { opacity: 0.3 },
                        '50%': { opacity: 0.8 }
                    }
                }} />
            );
        })}
    </Box>
);

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
    const { currentColor } = useColor();

    const userTitle = getUserFullTitle(user);
    const userIcon = getUserStatusIcon(user);
    const regionInfo = getUserRegionInfo(user);

    const published = usage.postsGenerated || 0;
    // 테스터/유료=90, 무료=8, 관리자=무제한
    const target = isAdmin ? 0
        : (isTester || user?.plan || user?.subscription) ? 90
        : (user?.monthlyLimit || usage.monthlyLimit || 8);
    const progress = isAdmin ? 100 : target > 0 ? Math.min((published / target) * 100, 100) : 0;
    const isCompleted = published >= target;
    const remaining = Math.max(target - published, 0);

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
                    data-force-light
                    sx={{
                        p: 3,
                        background: 'var(--gradient-primary)',
                        color: '#ffffff',
                        position: 'relative',
                        overflow: 'hidden'
                    }}
                >
                    <Box sx={{ position: 'absolute', top: -30, right: -30, width: 120, height: 120, borderRadius: '50%', background: 'rgba(255,255,255,0.08)', zIndex: 0 }} />
                    <Box sx={{ position: 'absolute', bottom: -40, left: '30%', width: 80, height: 80, borderRadius: '50%', background: 'rgba(255,255,255,0.05)', zIndex: 0 }} />

                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, position: 'relative', zIndex: 1 }}>
                        <Avatar sx={{ width: 72, height: 72, bgcolor: '#ffffff', color: 'var(--color-primary)', fontSize: '2.2rem', fontWeight: 700, boxShadow: 'var(--shadow-lg)' }}>
                            {userIcon}
                        </Avatar>
                        <Box sx={{ flex: 1 }}>
                            <Typography variant="h5" sx={{ fontWeight: 700, color: '#ffffff', mb: 0.5 }}>
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
                        <Box sx={{ px: 2, py: 0.8, borderRadius: 'var(--radius-full)', bgcolor: 'rgba(255,255,255,0.2)', backdropFilter: 'blur(4px)', border: '1px solid rgba(255,255,255,0.3)', display: 'flex', alignItems: 'center', gap: 0.5 }}>
                            <Star sx={{ fontSize: 18, color: isAdmin ? 'var(--color-gold)' : '#ffffff' }} />
                            <Typography variant="body2" sx={{ fontWeight: 600, color: '#ffffff' }}>
                                {isAdmin ? '관리자' : isTester ? '테스터' : 'Pro 플랜'}
                            </Typography>
                        </Box>
                    </Box>
                </Box>

                {/* 하단 사용량 및 CTA 영역 */}
                <Box sx={{ p: 3, bgcolor: 'var(--color-surface-elevated)' }}>
                    {/* 7-세그먼트 사용량 게이지 */}
                    {!isAdmin && (
                        <Box sx={{ mb: 3 }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1.5 }}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                    {isCompleted
                                        ? <EmojiEvents sx={{ fontSize: 18, color: 'var(--color-success)' }} />
                                        : <TrendingUp sx={{ fontSize: 18, color: 'var(--color-primary)' }} />
                                    }
                                    <Typography variant="body2" sx={{ color: 'var(--color-text-secondary)' }}>
                                        이번 달 사용량
                                    </Typography>
                                </Box>
                                <Typography variant="body2" sx={{ fontWeight: 700, color: 'var(--color-primary)' }}>
                                    {isCompleted
                                        ? `목표 달성! ${published}/${target}회`
                                        : `${remaining}회 남음`
                                    }
                                </Typography>
                            </Box>

                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                                {/* 7-세그먼트 퍼센테이지 */}
                                <Box sx={{
                                    padding: 1,
                                    backgroundColor: '#0a0a0a',
                                    border: '2px solid #333',
                                    borderRadius: 2,
                                    display: 'flex',
                                    alignItems: 'flex-end',
                                    gap: 1,
                                    boxShadow: 'inset 4px 4px 10px rgba(0,0,0,0.8), inset -2px -2px 5px rgba(255,255,255,0.1)'
                                }}>
                                    <SevenSegmentNumber number={Math.round(progress)} color={currentColor} />
                                    <Typography variant="caption" sx={{
                                        color: `${currentColor} !important`,
                                        fontFamily: 'monospace',
                                        fontWeight: 700,
                                        fontSize: '0.75rem',
                                        lineHeight: 1,
                                        textShadow: `0 0 6px ${currentColor}`,
                                        transition: 'color 0.8s ease, text-shadow 0.8s ease'
                                    }}>
                                        %
                                    </Typography>
                                </Box>

                                {/* 칸 단위 게이지 */}
                                <Box sx={{ flexGrow: 1 }}>
                                    <CellGauge published={published} target={target} color={currentColor} />
                                </Box>
                            </Box>
                        </Box>
                    )}

                    {/* Bio 경고 알림 */}
                    {showBioAlert && (
                        <Box sx={{ p: 2, mb: 3, borderRadius: 'var(--radius-lg)', bgcolor: 'var(--color-warning-light)', border: '1px solid var(--color-warning)' }}>
                            <Typography variant="body2" sx={{ color: 'var(--color-text-primary)' }}>
                                자기소개를 작성해야 원고 생성이 가능합니다.
                                <Button size="small" onClick={() => navigate('/profile')} sx={{ ml: 1, color: 'var(--color-warning)', fontWeight: 600 }}>
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
                            py: 2, fontSize: '1.1rem', fontWeight: 700,
                            background: 'var(--gradient-primary-dark)',
                            color: '#ffffff',
                            borderRadius: 'var(--radius-lg)',
                            boxShadow: 'var(--shadow-glow-primary)',
                            transition: 'all var(--transition-normal)',
                            border: 'none',
                            '&:hover': { background: 'var(--gradient-primary)', transform: 'translateY(-2px)', boxShadow: 'var(--shadow-xl)' },
                            '&:disabled': { background: 'var(--color-border)', color: 'var(--color-text-tertiary)', boxShadow: 'none' }
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
