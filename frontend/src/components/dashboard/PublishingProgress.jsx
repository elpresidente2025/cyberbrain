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

  // 호버 시 랜덤 글로우 색상 생성 함수
  const getRandomGlowColor = () => {
    const colors = ['#00ffff', '#ff00ff', '#00ff88', '#ff4444', '#8844ff', '#ffff00'];
    return colors[Math.floor(Math.random() * colors.length)];
  };

  const [currentGlowColor, setCurrentGlowColor] = useState('#00ffff');

  // ColorContext에서 색상을 자동으로 동기화하므로 별도 로직 불필요

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
  }, [user?.uid, user?.plan, user?.subscription]); // 플랜 변경 시에도 데이터 새로고침

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
    // 사용자의 플랜 정보만 기반으로 목표 결정
    const plan = user?.plan || user?.subscription;
    
    console.log('📊 PublishingProgress - getMonthlyTarget:', {
      user: user,
      userPlan: user?.plan,
      userSubscription: user?.subscription,
      finalPlan: plan
    });
    
    if (plan) {
      switch (plan) {
        case '오피니언 리더':
          return 60;
        case '리전 인플루언서':
          return 20;
        case '로컬 블로거':
          return 8;
        default:
          return 8;
      }
    }
    
    // 플랜 정보가 없으면 결제되지 않은 상태
    return null;
  };

  const getBonusAmount = (user) => {
    // 사용자의 플랜 정보를 기반으로 보너스 결정
    const plan = user?.plan || user?.subscription;
    
    if (plan) {
      switch (plan) {
        case '오피니언 리더':
          return 30; // 60회 달성 시 익월 30회 추가 제공
        case '리전 인플루언서':
          return 10;
        case '로컬 블로거':
          return 4;
        default:
          return 4;
      }
    }
    
    // 플랜 정보가 없으면 결제되지 않은 상태
    return 0;
  };

  const getFullTarget = (user) => {
    const basicTarget = getMonthlyTarget(user);
    const bonusAmount = getBonusAmount(user);
    return basicTarget ? basicTarget + bonusAmount : null;
  };

  const getCurrentMonth = () => {
    const now = new Date();
    return `${now.getFullYear()}년 ${now.getMonth() + 1}월`;
  };

  if (loading || !publishingStats || !user) {
    return (
      <Card 
        onMouseEnter={() => setCurrentGlowColor(getRandomGlowColor())}
        elevation={0}
        sx={{ 
          height: '100%',
          bgcolor: 'transparent',
          cursor: 'pointer',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': {
            transform: 'scale(0.98)',
            boxShadow: `0 8px 32px ${currentGlowColor}40, 0 4px 16px ${currentGlowColor}20, inset 0 1px 0 ${currentGlowColor}10`,
            border: `1px solid ${currentGlowColor}30`
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
  
  // 플랜 검증을 먼저 수행 (관리자는 예외)
  const plan = user?.plan || user?.subscription;
  const isAdmin = user?.isAdmin || user?.role === 'admin';
  
  console.log('📊 PublishingProgress - 최종 렌더링 전 확인:', {
    userUid: user?.uid,
    userPlan: user?.plan,
    userSubscription: user?.subscription,
    finalPlan: plan,
    isAdmin
  });
  
  if (!plan && !isAdmin) {
    return (
      <Card
        onMouseEnter={() => setCurrentGlowColor(getRandomGlowColor())}
        elevation={0}
        sx={{ 
          height: '100%',
          bgcolor: 'transparent',
          cursor: 'pointer',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          '&:hover': {
            transform: 'scale(0.98)',
            boxShadow: `0 8px 32px ${currentGlowColor}40, 0 4px 16px ${currentGlowColor}20, inset 0 1px 0 ${currentGlowColor}10`,
            border: `1px solid ${currentGlowColor}30`
          }
        }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <Publish sx={{ color: '#152484' }} />
            <Typography variant="h6">발행 목표</Typography>
          </Box>
          
          <Alert severity="warning" sx={{ mb: 2 }}>
            <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
              요금제가 설정되지 않았습니다
            </Typography>
            <Typography variant="body2">
              발행 목표를 확인하려면 요금제를 선택해주세요.
            </Typography>
          </Alert>
          
          <Button 
            variant="contained" 
            fullWidth 
            sx={{ 
              bgcolor: '#f8c023',
              color: '#ffffff',
              border: 'none',
              '&:hover': { 
                bgcolor: '#e6a91c',
              },
              animation: 'planSelectBlink 2s ease-in-out infinite',
              '@keyframes planSelectBlink': {
                '0%, 50%, 100%': { opacity: 1 },
                '25%, 75%': { opacity: 0.6 }
              }
            }}
            onClick={() => window.location.href = '/billing'}
          >
            요금제 선택하기 ⚠️
          </Button>
        </CardContent>
      </Card>
    );
  }
  
  // 관리자이거나 플랜이 있는 경우 정상 처리 - 2단계 시스템
  const basicTarget = getMonthlyTarget(user);
  const fullTarget = getFullTarget(user);
  const bonusAmount = getBonusAmount(user);
  
  // 백엔드에서 받은 데이터 우선, 없으면 프론트엔드 계산값 사용
  const currentStage = actualData?.currentMonth?.currentStage || 'basic';
  const nextStageTarget = actualData?.currentMonth?.nextStageTarget || basicTarget;
  const achievements = actualData?.achievements || {};
  
  console.log('🎯 2단계 시스템 상태:', {
    published,
    basicTarget,
    fullTarget,
    currentStage,
    nextStageTarget,
    achievements,
    userPlan: user?.plan || user?.subscription
  });
  
  // 현재 진행 상황에 따른 UI 결정
  let displayTarget, progress, isCompleted, remaining, statusMessage;
  
  if (currentStage === 'completed') {
    // 2단계 완료 (SNS 무료 자격 획득)
    displayTarget = fullTarget;
    progress = 100;
    isCompleted = true;
    remaining = 0;
    statusMessage = {
      icon: 'trophy',
      text: `완전 달성! 다음 달 SNS 원고 무료 생성`,
      color: '#006261'
    };
  } else if (currentStage === 'bonus') {
    // 1단계 완료, 2단계 진행 중
    displayTarget = fullTarget;
    progress = Math.min((published / fullTarget) * 100, 100);
    isCompleted = false;
    remaining = Math.max(fullTarget - published, 0);
    statusMessage = {
      icon: 'star',
      text: `보너스 단계! ${remaining}회 더 발행하면 SNS 무료 획득`,
      color: '#55207D'
    };
  } else {
    // 기본 단계
    displayTarget = basicTarget;
    progress = Math.min((published / basicTarget) * 100, 100);
    isCompleted = published >= basicTarget;
    remaining = Math.max(basicTarget - published, 0);
    statusMessage = {
      icon: 'trending',
      text: isCompleted 
        ? `1단계 달성! 익월 보너스 ${bonusAmount}회 제공 예정`
        : `${remaining}회 더 발행하면 보너스 ${bonusAmount}회 획득!`,
      color: isCompleted ? '#006261' : '#152484'
    };
  }

  return (
    <Card
      onMouseEnter={() => setCurrentGlowColor(getRandomGlowColor())}
      elevation={0}
      sx={{ 
        height: '100%', 
        bgcolor: 'transparent',
        position: 'relative',
        cursor: 'pointer',
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        '&:hover': {
          transform: 'scale(0.98)',
          boxShadow: `0 8px 32px ${currentGlowColor}40, 0 4px 16px ${currentGlowColor}20, inset 0 1px 0 ${currentGlowColor}10`,
          border: `1px solid ${currentGlowColor}30`
        }
      }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="h6" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Publish sx={{ color: '#152484' }} />
            발행 목표
          </Typography>
          <Tooltip title="월간 목표 달성 시 익월 보너스 원고 제공">
            <IconButton size="small">
              <Info fontSize="small" sx={{ color: '#55207D' }} />
            </IconButton>
          </Tooltip>
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
            {/* 사이버펑크 스타일 게이지 */}
            <Box
              sx={{
                position: 'relative',
                height: 16,
                backgroundColor: '#0a0a0a',
                border: '1px solid #333',
                borderRadius: 2,
                overflow: 'hidden',
                boxShadow: 'inset 0 2px 4px rgba(0,0,0,0.3)'
              }}
            >
              {/* 배경 그리드 패턴 */}
              <Box
                sx={{
                  position: 'absolute',
                  width: '100%',
                  height: '100%',
                  background: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.05) 50%, transparent 100%)',
                  backgroundSize: '8px 100%',
                  animation: currentStage !== 'basic' ? 'cyberpunkScan 2s infinite linear' : 'none',
                  '@keyframes cyberpunkScan': {
                    '0%': { transform: 'translateX(-100%)' },
                    '100%': { transform: 'translateX(100%)' }
                  }
                }}
              />
              
              {/* 진행 바 - 사용자 플랜 색상 */}
              <Box
                sx={{
                  position: 'absolute',
                  left: 0,
                  top: 0,
                  height: '100%',
                  width: `${progress}%`,
                  background: currentStage === 'completed'
                    ? `linear-gradient(90deg, ${currentColor}, #39ff14)`
                    : currentStage === 'bonus'
                    ? 'linear-gradient(90deg, #f8c023, #ffff00)' // 보너스 단계는 노란색
                    : `linear-gradient(90deg, ${currentColor}, ${currentColor}AA)`,
                  boxShadow: currentStage === 'completed'
                    ? '0 0 12px #39ff14, inset 0 0 8px rgba(57,255,20,0.3)'
                    : currentStage === 'bonus'
                    ? '0 0 12px #f8c023, inset 0 0 8px rgba(248,192,35,0.3)'
                    : `0 0 12px ${currentColor}, inset 0 0 8px ${currentColor}50`,
                  transition: 'all 0.5s ease',
                  borderRadius: '1px'
                }}
              />
              
              {/* 구분선들 (33.33%, 66.67% 지점 - 30개씩 3등분) */}
              {[33.33, 66.67].map(percent => (
                <Box
                  key={percent}
                  sx={{
                    position: 'absolute',
                    left: `${percent}%`,
                    top: 0,
                    width: '1px',
                    height: '100%',
                    backgroundColor: 'rgba(255,255,255,0.3)',
                    zIndex: 1
                  }}
                />
              ))}

              {/* 다음 목표 지점 점멸 효과 */}
              {(() => {
                const nextGoalCount = published + 1;
                const nextGoalPercent = (nextGoalCount / displayTarget) * 100;
                
                if (nextGoalCount <= displayTarget) {
                  return (
                    <Box
                      sx={{
                        position: 'absolute',
                        left: `${nextGoalPercent}%`,
                        top: '-2px',
                        width: '4px',
                        height: '20px',
                        backgroundColor: '#f8c023',
                        zIndex: 2,
                        animation: 'nextGoalBlink 1.5s infinite ease-in-out',
                        boxShadow: '0 0 12px #f8c023',
                        borderRadius: '2px',
                        '@keyframes nextGoalBlink': {
                          '0%, 100%': { 
                            opacity: 0.4,
                            transform: 'translateX(-50%) scaleY(0.8)'
                          },
                          '50%': { 
                            opacity: 1,
                            transform: 'translateX(-50%) scaleY(1.2)'
                          }
                        }
                      }}
                    />
                  );
                }
                return null;
              })()}
              
              {/* 목표 달성 시 반짝임 효과 */}
              {isCompleted && (
                <Box
                  sx={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: '100%',
                    background: 'linear-gradient(45deg, transparent 30%, rgba(255,255,255,0.1) 50%, transparent 70%)',
                    animation: 'cyberpunkGlow 1.5s infinite ease-in-out',
                    '@keyframes cyberpunkGlow': {
                      '0%, 100%': { opacity: 0 },
                      '50%': { opacity: 1 }
                    }
                  }}
                />
              )}
            </Box>
          </Box>
        </Box>


        <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid #e0e0e0' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {statusMessage.icon === 'trophy' && <EmojiEvents sx={{ color: statusMessage.color }} />}
            {statusMessage.icon === 'star' && <AutoAwesome sx={{ color: statusMessage.color }} />}
            {statusMessage.icon === 'trending' && <TrendingUp sx={{ color: statusMessage.color }} />}
            
            <Typography variant="body2" sx={{ 
              color: statusMessage.color, 
              fontWeight: currentStage !== 'basic' ? 600 : 'normal' 
            }}>
              {statusMessage.text}
            </Typography>
          </Box>
          
          {/* 진행 상태 표시 */}
          {fullTarget && currentStage !== 'completed' && (
            <Box sx={{ mt: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography variant="caption" color="text.secondary">
                전체 진행률: {published}/{fullTarget} ({Math.round((published / fullTarget) * 100)}%)
              </Typography>
            </Box>
          )}
        </Box>

        {(actualData?.bonusEarned || 0) > 0 && (
          <Box sx={{ mt: 2 }}>
            <Chip
              icon={<AutoAwesome />}
              label={`이번 달 보너스: ${actualData.bonusEarned}회`}
              color="primary"
              variant="outlined"
              size="small"
              sx={{ backgroundColor: 'rgba(21, 36, 132, 0.1)' }}
            />
          </Box>
        )}
      </CardContent>
    </Card>
  );
};

export default PublishingProgress;
