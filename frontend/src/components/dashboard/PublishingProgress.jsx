import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  LinearProgress,
  Box,
  Chip,
  Grid,
  Tooltip,
  IconButton,
  Alert,
  Button
} from '@mui/material';
import { 
  TrendingUp, 
  EmojiEvents, 
  Publish,
  Info,
  AutoAwesome
} from '@mui/icons-material';
import { useAuth } from '../../hooks/useAuth';
import { callFunctionWithNaverAuth } from '../../services/firebaseService';
import { useColor } from '../../contexts/ColorContext';
import { getMonthlyLimit, hasAdminAccess, isPaidSubscriber, isTesterUser } from '../../utils/authz';

// 7-세그먼트 숫자 컴포넌트 (3자리 고정)
const SevenSegmentNumber = ({ number, color, size = 'small' }) => {
  const digitPatterns = {
    '0': [1, 1, 1, 1, 1, 1, 0],
    '1': [0, 1, 1, 0, 0, 0, 0],
    '2': [1, 1, 0, 1, 1, 0, 1],
    '3': [1, 1, 1, 1, 0, 0, 1],
    '4': [0, 1, 1, 0, 0, 1, 1],
    '5': [1, 0, 1, 1, 0, 1, 1],
    '6': [1, 0, 1, 1, 1, 1, 1],
    '7': [1, 1, 1, 0, 0, 0, 0],
    '8': [1, 1, 1, 1, 1, 1, 1],
    '9': [1, 1, 1, 1, 0, 1, 1],
    ' ': [0, 0, 0, 0, 0, 0, 0] // 공백
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

  // 숫자를 3자리로 패딩 (100% 표시를 위해)
  const numberStr = number.toString().padStart(3, ' ');
  const segmentIds = ['a', 'b', 'c', 'd', 'e', 'f', 'g'];

  return (
    <Box sx={{ display: 'flex', gap: '2px' }}>
      {numberStr.split('').map((digit, digitIndex) => {
        const pattern = digitPatterns[digit] || digitPatterns['0'];
        return (
          <Box
            key={digitIndex}
            sx={{
              position: 'relative',
              width: '16px',
              height: '28px'
            }}
          >
            {segmentIds.map((segmentId, index) => (
              <Box
                key={segmentId}
                sx={{
                  position: 'absolute',
                  backgroundColor: pattern[index] === 1 ? color : '#333',
                  borderRadius: '1px',
                  opacity: pattern[index] === 1 ? 1 : 0.2,
                  boxShadow: pattern[index] === 1 ? `0 0 6px ${color}` : 'none',
                  transition: 'background-color 0.8s ease, box-shadow 0.8s ease',
                  ...segments[segmentId]
                }}
              />
            ))}
          </Box>
        );
      })}
    </Box>
  );
};

const PublishingProgress = () => {
  const { user } = useAuth();
  const { currentColor } = useColor();
  const [publishingStats, setPublishingStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [testMode, setTestMode] = useState(false);

  // ColorContext에서 색상을 자동으로 동기화하므로 별도 로직 불필요

  // 시스템 설정 로드 (데모 모드 확인)
  useEffect(() => {
    const loadSystemConfig = async () => {
      try {
        const configResponse = await callFunctionWithNaverAuth('getSystemConfig');
        if (configResponse?.config) {
          setTestMode(configResponse.config.testMode || false);
        }
      } catch (error) {
        console.error('시스템 설정 로드 실패:', error);
      }
    };

    loadSystemConfig();
  }, []);

  useEffect(() => {
    let mounted = true;

    const loadStats = async () => {
      if (user?.uid && mounted) {
        try {
          await fetchPublishingStats();
        } catch (error) {
          console.error('PublishingProgress mount error:', error);
        }
      }
    };

    loadStats();

    return () => {
      mounted = false;
    };
  }, [user?.uid, user?.monthlyLimit, user?.subscriptionStatus, user?.role, user?.isTester]); // 플랜 변경 시에도 데이터 새로고침

  const fetchPublishingStats = async () => {
    if (!user?.uid) return;
    
    try {
      setLoading(true);
      const response = await callFunctionWithNaverAuth('getPublishingStats');
      
      // callFunctionWithNaverAuth는 이미 response.data를 반환하므로 직접 사용
      let statsData = response.data || response;
      
      // currentMonth가 없거나 올바르지 않은 경우 기본값 설정
      if (!statsData.currentMonth || typeof statsData.currentMonth !== 'object') {
        statsData = {
          ...statsData,
          currentMonth: {
            published: statsData.totalPublished || 0,
            target: getMonthlyTarget(user)
          },
          bonusEarned: statsData.bonusEarned || 0,
          nextBonusEligible: statsData.nextBonusEligible !== false
        };
      } else {
        // currentMonth는 있지만 필수 필드가 없는 경우
        const userBasedTarget = getMonthlyTarget(user);
        console.log('🎯 Target 결정:', {
          backendTarget: statsData.currentMonth.target,
          userBasedTarget: userBasedTarget,
          willUse: userBasedTarget || statsData.currentMonth.target
        });
        
        statsData.currentMonth = {
          published: statsData.currentMonth.published || 0,
          target: userBasedTarget || statsData.currentMonth.target // 사용자 기반 target을 우선 사용
        };
      }
      
      setPublishingStats(statsData);
    } catch (error) {
      console.error('Failed to fetch publishing stats:', error);
      console.error('Error details:', error.message, error.code);
      // 실패 시 기본값 설정
      setPublishingStats({
        currentMonth: {
          published: 0,
          target: getMonthlyTarget(user)
        },
        bonusEarned: 0,
        nextBonusEligible: true
      });
    } finally {
      setLoading(false);
    }
  };

  const getMonthlyTarget = (user) => {
    const isAdmin = hasAdminAccess(user);
    const isTester = isTesterUser(user);
    const isSubscribed = isPaidSubscriber(user);
    const resolvedMonthlyLimit = getMonthlyLimit(user, 8);

    console.log('?뱤 PublishingProgress - getMonthlyTarget:', {
      isAdmin,
      isTester,
      isSubscribed,
      monthlyLimit: user?.monthlyLimit,
      resolvedMonthlyLimit
    });

    return resolvedMonthlyLimit;
  };


  const getCurrentMonth = () => {
    const now = new Date();
    return `${now.getFullYear()}년 ${now.getMonth() + 1}월`;
  };

  if (loading || !publishingStats || !user) {
    return (
      <Card
        elevation={0}
        sx={{
          height: '100%',
          bgcolor: 'transparent',
          borderRadius: '4px',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          transition: 'all 0.2s ease',
          '&:hover': {
            borderColor: 'rgba(255, 255, 255, 0.2)',
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
          }
        }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <Publish sx={{ color: '#152484' }} />
            <Typography variant="h6">발행 목표</Typography>
          </Box>
          <LinearProgress sx={{ color: '#152484' }} />
          <Typography variant="caption" sx={{ mt: 2, display: 'block', color: '#152484', fontFamily: '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, system-ui, Roboto, "Helvetica Neue", "Segoe UI", "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic", "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", sans-serif' }}>
            로딩 중...
          </Typography>
        </CardContent>
      </Card>
    );
  }

  // publishingStats가 {success: true, data: {...}} 구조인 경우 data 추출
  const actualData = publishingStats?.data || publishingStats || {};
  const { currentMonth } = actualData;
  
  const published = currentMonth?.published || 0;
  
  // 플랜 검증을 먼저 수행 (관리자/테스터는 예외)
  const isAdmin = hasAdminAccess(user);
  const isTester = isTesterUser(user);
  const isSubscribed = isPaidSubscriber(user);

  console.log('📊 PublishingProgress - 최종 렌더링 전 확인:', {
    userUid: user?.uid,
    isAdmin,
    isTester,
    isSubscribed
  });

  // 모든 사용자에게 정상 게이지 표시 (무료: 8회, 유료: 90회)
  const target = getMonthlyTarget(user);

  console.log('🎯 게이지 데이터 확인:', {
    publishingStats,
    actualData,
    currentMonth,
    published,
    target,
    subscriptionStatus: user?.subscriptionStatus,
    monthlyLimit: user?.monthlyLimit
  });

  // 진행 상황 계산
  const progress = Math.min((published / target) * 100, 100);
  const isCompleted = published >= target;
  const remaining = Math.max(target - published, 0);

  return (
    <Card
      elevation={0}
      sx={{
        height: '100%',
        bgcolor: 'transparent',
        position: 'relative',
        borderRadius: '4px',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        transition: 'all 0.2s ease',
        '&:hover': {
          borderColor: 'rgba(255, 255, 255, 0.2)',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
        }
      }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
          <Publish sx={{ color: '#152484', mr: 1 }} />
          <Typography variant="h6">발행 목표</Typography>
        </Box>

        <Typography variant="body2" color="text.secondary" gutterBottom>
          {getCurrentMonth()} 진행률
        </Typography>

        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
          {/* 7-세그먼트 퍼센테이지 디스플레이 (좌측) */}
          <Box
            sx={{
              padding: 1,
              backgroundColor: '#0a0a0a',
              border: '2px solid #333',
              borderRadius: 2,
              display: 'flex',
              alignItems: 'flex-end',
              gap: 1,
              boxShadow: 'inset 4px 4px 10px rgba(0,0,0,0.8), inset -2px -2px 5px rgba(255,255,255,0.1)'
            }}
          >
            <SevenSegmentNumber
              number={Math.round(progress)}
              color={currentColor}
            />
            <Typography
              variant="caption"
              sx={{
                color: `${currentColor} !important`,
                fontFamily: 'monospace',
                fontWeight: 700,
                fontSize: '0.75rem',
                lineHeight: 1,
                textShadow: `0 0 6px ${currentColor}`,
                transition: 'color 0.8s ease, text-shadow 0.8s ease'
              }}
            >
              %
            </Typography>
          </Box>

          <Box sx={{ flexGrow: 1, position: 'relative' }}>
            {/* 칸 단위 게이지 */}
            <Box
              sx={{
                display: 'flex',
                gap: '2px',
                height: 16,
                backgroundColor: '#0a0a0a',
                border: '1px solid #333',
                borderRadius: 2,
                padding: '2px',
                boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.3)'
              }}
            >
              {(() => {
                const totalCells = target; // 8칸 또는 90칸
                const cells = [];

                for (let i = 0; i < totalCells; i++) {
                  const isFilled = i < published; // 발행된 횟수만큼 채워짐
                  const isNext = i === published; // 다음 칸은 점멸

                  cells.push(
                    <Box
                      key={i}
                      sx={{
                        flex: 1,
                        height: '100%',
                        backgroundColor: isFilled
                          ? currentColor
                          : isNext
                          ? currentColor
                          : 'rgba(255,255,255,0.1)',
                        opacity: isFilled ? 1 : isNext ? 0.5 : 1,
                        boxShadow: isFilled
                          ? `0 0 4px ${currentColor}`
                          : 'none',
                        borderRadius: '1px',
                        transition: 'all 0.3s ease',
                        animation: isNext ? 'cellBlink 1.5s infinite ease-in-out' : 'none',
                        '@keyframes cellBlink': {
                          '0%, 100%': { opacity: 0.3 },
                          '50%': { opacity: 0.8 }
                        }
                      }}
                    />
                  );
                }

                return cells;
              })()}
            </Box>
          </Box>
        </Box>


        <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid #e0e0e0' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {isCompleted ? (
              <EmojiEvents sx={{ color: '#006261' }} />
            ) : (
              <TrendingUp sx={{ color: '#152484' }} />
            )}

            <Typography variant="body2" sx={{ color: isCompleted ? '#006261' : '#152484' }}>
              {isCompleted
                ? `목표 달성! ${published}/${target}회 완료`
                : `${remaining}회 더 작성하면 목표 달성!`}
            </Typography>
          </Box>
        </Box>

        {/* 무료 티어 업그레이드 안내 (관리자/테스터 제외) */}
        {!isSubscribed && !isAdmin && !isTester && (
          <Box sx={{ mt: 2 }}>
            <Alert severity="info" sx={{ mb: 0 }}>
              <Typography variant="body2" sx={{ mb: 1 }}>
                <strong>더 많은 원고가 필요하신가요?</strong> {testMode ? '정식 출시를 기다려 주세요!' : '월 90회까지 사용 가능합니다'}
              </Typography>
              {!testMode && (
                <Button
                  variant="contained"
                  size="small"
                  sx={{
                    bgcolor: '#152484',
                    color: '#ffffff',
                    '&:hover': {
                      bgcolor: '#0d1850',
                    }
                  }}
                  onClick={() => window.location.href = '/billing'}
                >
                  공식 파트너십 체결
                </Button>
              )}
            </Alert>
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default PublishingProgress;







