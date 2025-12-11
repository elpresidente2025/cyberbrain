// frontend/src/components/dashboard/ElectionDDay.jsx
import React, { useState, useEffect, useRef } from 'react';
import {
  Paper,
  Box,
  Typography,
  Chip,
  Alert,
  useTheme
} from '@mui/material';
import {
  CalendarToday,
  People,
  HowToVote
} from '@mui/icons-material';
import { useColor } from '../../contexts/ColorContext';

// 7세그먼트 패턴
const DIGIT_PATTERNS = {
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
  'D': [0, 1, 1, 1, 1, 0, 1],
  '-': [0, 0, 0, 0, 0, 0, 1],
  ' ': [0, 0, 0, 0, 0, 0, 0],
  'C': [1, 0, 0, 1, 1, 1, 0],
  'O': [1, 1, 1, 1, 1, 1, 0],
  'L': [0, 0, 0, 1, 1, 1, 0],
  'R': [0, 0, 0, 0, 1, 0, 1],
  'c': [0, 0, 0, 1, 1, 0, 1],
  'o': [0, 0, 1, 1, 1, 0, 1],
  'l': [0, 1, 1, 0, 0, 0, 0],
  'r': [0, 0, 0, 0, 1, 0, 1]
};

// 세그먼트 위치 정의
const SEGMENT_POSITIONS = {
  // 큰 디스플레이용 (18px x 36px) - 1.5배로 키움
  large: {
    a: { top: '1.5px', left: '3px', width: '12px', height: '3px' },
    b: { top: '4.5px', right: '1.5px', width: '3px', height: '12px' },
    c: { bottom: '4.5px', right: '1.5px', width: '3px', height: '12px' },
    d: { bottom: '1.5px', left: '3px', width: '12px', height: '3px' },
    e: { bottom: '4.5px', left: '1.5px', width: '3px', height: '12px' },
    f: { top: '4.5px', left: '1.5px', width: '3px', height: '12px' },
    g: { top: '50%', left: '3px', width: '12px', height: '3px', transform: 'translateY(-50%)' }
  },
  // 반응형 큰 디스플레이용
  responsive: {
    a: { 
      top: { xs: '1.5px', sm: '2px', md: '2px' }, 
      left: { xs: '4px', sm: '5.5px', md: '7px' }, 
      width: { xs: '20px', sm: '25px', md: '31px' }, 
      height: { xs: '4px', sm: '5px', md: '6.5px' } 
    },
    b: { 
      top: { xs: '5.5px', sm: '7px', md: '8.5px' }, 
      right: { xs: '1.5px', sm: '2px', md: '2px' }, 
      width: { xs: '4px', sm: '5px', md: '6.5px' }, 
      height: { xs: '21px', sm: '26px', md: '32.5px' } 
    },
    c: { 
      bottom: { xs: '5.5px', sm: '7px', md: '8.5px' }, 
      right: { xs: '1.5px', sm: '2px', md: '2px' }, 
      width: { xs: '4px', sm: '5px', md: '6.5px' }, 
      height: { xs: '21px', sm: '26px', md: '32.5px' } 
    },
    d: { 
      bottom: { xs: '1.5px', sm: '2px', md: '2px' }, 
      left: { xs: '4px', sm: '5.5px', md: '7px' }, 
      width: { xs: '20px', sm: '25px', md: '31px' }, 
      height: { xs: '4px', sm: '5px', md: '6.5px' } 
    },
    e: { 
      bottom: { xs: '5.5px', sm: '7px', md: '8.5px' }, 
      left: { xs: '1.5px', sm: '2px', md: '2px' }, 
      width: { xs: '4px', sm: '5px', md: '6.5px' }, 
      height: { xs: '21px', sm: '26px', md: '32.5px' } 
    },
    f: { 
      top: { xs: '5.5px', sm: '7px', md: '8.5px' }, 
      left: { xs: '1.5px', sm: '2px', md: '2px' }, 
      width: { xs: '4px', sm: '5px', md: '6.5px' }, 
      height: { xs: '21px', sm: '26px', md: '32.5px' } 
    },
    g: { 
      top: '50%', 
      left: { xs: '4px', sm: '5.5px', md: '7px' }, 
      width: { xs: '20px', sm: '25px', md: '31px' }, 
      height: { xs: '4px', sm: '5px', md: '6.5px' }, 
      transform: 'translateY(-50%)' 
    }
  },
  // 작은 디스플레이용 (5px x 11px) - 0.5배로 축소
  small: {
    a: { top: '0.5px', left: '1px', width: '3px', height: '0.75px' },
    b: { top: '1.25px', right: '0.25px', width: '0.75px', height: '4px' },
    c: { bottom: '1.25px', right: '0.25px', width: '0.75px', height: '4px' },
    d: { bottom: '0.5px', left: '1px', width: '3px', height: '0.75px' },
    e: { bottom: '1.25px', left: '0.25px', width: '0.75px', height: '4px' },
    f: { top: '1.25px', left: '0.25px', width: '0.75px', height: '4px' },
    g: { top: '50%', left: '1px', width: '3px', height: '0.75px', transform: 'translateY(-50%)' }
  }
};

// 단일 세그먼트 컴포넌트
const Segment = ({ isActive, segmentId, color, size = 'large', scaleFactor = 1 }) => {
  const positions = SEGMENT_POSITIONS[size];
  
  // 반응형 border radius 설정
  const getBorderRadius = () => {
    if (size === 'responsive') {
      return { xs: '1.5px', sm: '2.5px', md: '3px' };
    }
    return size === 'large' ? '3px' : '0.5px';
  };

  // 반응형 box shadow 설정
  const getBoxShadow = () => {
    if (size === 'responsive') {
      return isActive 
        ? {
            xs: `0 0 4px ${color}80, 0 0 8px ${color}40, inset 0 0 2px ${color}60`,
            sm: `0 0 6px ${color}80, 0 0 12px ${color}40, inset 0 0 3px ${color}60`,
            md: `0 0 8px ${color}80, 0 0 16px ${color}40, inset 0 0 4px ${color}60`
          }
        : 'none';
    }
    return isActive 
      ? `0 0 ${size === 'large' ? '8px' : '4px'} ${color}80, 0 0 ${size === 'large' ? '16px' : '8px'} ${color}40, inset 0 0 ${size === 'large' ? '4px' : '2px'} ${color}60`
      : 'none';
  };
  
  // scaleFactor가 있으면 위치도 스케일링
  const scaledPositions = scaleFactor !== 1 && size === 'large' ?
    Object.entries(positions[segmentId]).reduce((acc, [key, value]) => {
      if (typeof value === 'string' && value.includes('px')) {
        const numValue = parseFloat(value);
        acc[key] = `${numValue * scaleFactor}px`;
      } else {
        acc[key] = value;
      }
      return acc;
    }, {}) : positions[segmentId];

  return (
    <Box
      sx={{
        position: 'absolute',
        backgroundColor: isActive ? color : '#222',
        borderRadius: getBorderRadius(),
        boxShadow: getBoxShadow(),
        opacity: isActive ? 1 : (size === 'large' || size === 'responsive' ? 0.15 : 0.2),
        transition: 'all 0.6s ease-out',
        ...scaledPositions
      }}
    />
  );
};

// 단일 문자/숫자 디스플레이
const DigitDisplay = ({ character, color, size = 'large', responsive = false, containerHeight }) => {
  const pattern = DIGIT_PATTERNS[character] || DIGIT_PATTERNS[' '];
  const segmentIds = ['a', 'b', 'c', 'd', 'e', 'f', 'g'];

  let dimensions;
  if (responsive && size === 'large') {
    dimensions = {
      width: { xs: '28px', sm: '36px', md: '45px' },
      height: { xs: '55px', sm: '70px', md: '85px' }
    };
  } else if (containerHeight && size === 'large') {
    // 컨테이너 높이에 따라 동적으로 크기 조정
    const scaleFactor = Math.max(0.5, Math.min(2, containerHeight / 60));
    const baseWidth = 18 * scaleFactor;
    const baseHeight = 36 * scaleFactor;
    dimensions = {
      width: `${baseWidth}px`,
      height: `${baseHeight}px`
    };
  } else {
    dimensions = size === 'large'
      ? { width: '18px', height: '36px' } // 1.5배로 키움 (12px->18px, 24px->36px)
      : { width: '5px', height: '11px' }; // 0.5배로 줄임 (10px->5px, 22px->11px)
  }

  return (
    <Box
      sx={{
        position: 'relative',
        ...dimensions,
        margin: size === 'large' ? '0 0.5px' : '0 0.5px'
      }}
    >
      {segmentIds.map((segmentId, index) => (
        <Segment
          key={segmentId}
          isActive={pattern[index] === 1}
          segmentId={segmentId}
          color={color}
          size={responsive && size === 'large' ? 'responsive' : size}
          scaleFactor={containerHeight ? Math.max(0.5, Math.min(2, containerHeight / 60)) : 1}
        />
      ))}
    </Box>
  );
};

// 메인 7세그먼트 디스플레이 컴포넌트
const SevenSegmentDisplay = ({ dDay, cardHeight = '140px', onColorChange }) => {
  const theme = useTheme();
  const { currentColor, changeColor } = useColor();
  const containerRef = useRef(null);
  const [containerHeight, setContainerHeight] = useState(60);

  // 컨테이너 높이 측정
  useEffect(() => {
    const measureHeight = () => {
      if (containerRef.current) {
        const height = containerRef.current.offsetHeight;
        setContainerHeight(height);
      }
    };

    measureHeight();

    const resizeObserver = new ResizeObserver(measureHeight);
    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
    }

    return () => resizeObserver.disconnect();
  }, []);

  // 색상 변경 시 부모 컴포넌트에 알림
  useEffect(() => {
    onColorChange && onColorChange(currentColor);
  }, [currentColor, onColorChange]);

  const handleColorChange = async (direction) => {
    await changeColor(direction);
  };

  // D-Day 텍스트 생성
  const getDDayText = (days) => {
    if (days > 0) {
      return `D-${days.toString().padStart(3, ' ')}`;
    } else if (days === 0) {
      return 'D- 0';
    } else {
      return `D+${Math.abs(days)}`;
    }
  };

  const displayText = getDDayText(dDay);

  return (
    <Box
      ref={containerRef}
      sx={{
        backgroundColor: '#0a0a0a',
        border: '2px solid #333',
        borderRadius: 1,
        padding: { xs: '8px', sm: '12px' },
        width: '100%',
        maxWidth: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        boxShadow: 'inset 4px 4px 12px rgba(0,0,0,0.8), inset -2px -2px 6px rgba(255,255,255,0.1), 0 2px 8px rgba(0,0,0,0.2)',
        gap: '4px', // 박스 높이의 5% 간격
        overflow: 'hidden'
      }}
    >
      {/* 메인 디스플레이 */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '0',
          width: '100%',
          maxWidth: '100%',
          flex: 1,
          minHeight: 0
        }}
      >
        {displayText.split('').map((char, index) => (
          <DigitDisplay key={index} character={char} color={currentColor} size="large" responsive={false} containerHeight={containerHeight} />
        ))}
      </Box>

      {/* 색상 변경 컨트롤 */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 1,
          flex: 1,
          minHeight: 0
        }}
      >
        {/* 왼쪽 화살표 */}
        <Box
          onClick={() => handleColorChange('prev')}
          sx={{
            color: '#666',
            cursor: 'pointer',
            fontSize: '14px',
            userSelect: 'none',
            '&:hover': { color: '#999' },
            transition: 'color 0.3s ease'
          }}
        >
          ◀
        </Box>

        {/* color 텍스트 (작은 7세그먼트) */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0 }}>
          {'color'.split('').map((char, index) => (
            <DigitDisplay key={index} character={char} color={currentColor} size="small" responsive={false} containerHeight={containerHeight * 0.3} />
          ))}
        </Box>

        {/* 오른쪽 화살표 */}
        <Box
          onClick={() => handleColorChange('next')}
          sx={{
            color: '#666',
            cursor: 'pointer',
            fontSize: '14px',
            userSelect: 'none',
            '&:hover': { color: '#999' },
            transition: 'color 0.3s ease'
          }}
        >
          ▶
        </Box>
      </Box>
    </Box>
  );
};

/**
 * ?�거???�데??컴포?�트
 * @param {Object} props
 * @param {string} props.position - 직책 ('�?��?�원', '광역?�원', '기초?�원')
 * @param {string} props.status - ?�태 ('?�역', '?�비')
 */
function ElectionDDay({ position, status }) {

  const theme = useTheme(); // Hook을 함수 최상단으로 이동
  const { currentColor } = useColor();
  const [electionInfo, setElectionInfo] = useState(null);
  const [dDay, setDDay] = useState(null);
  const [displayColor, setDisplayColor] = useState(currentColor);

  // 호버 시 랜덤 글로우 색상 생성 함수
  const getRandomGlowColor = () => {
    const colors = ['#00ffff', '#ff00ff', '#00ff88', '#ff4444', '#8844ff', '#ffff00'];
    return colors[Math.floor(Math.random() * colors.length)];
  };

  const [currentGlowColor, setCurrentGlowColor] = useState('#00ffff');

  // ?�거 ?�보 ?�정
  useEffect(() => {
    const getElectionInfo = () => {
      const today = new Date();
      const currentYear = today.getFullYear();
      
      if (position === '국회의원') {
        // 총선: 4년주기, 기준일: 2028-04-12
        const baseElection = {
          year: 2028,
          month: 3, // 0-based (4월)
          day: 12,
          cycle: 4
        };
        
        const nextElection = getNextElectionDate(baseElection, today);
        const termNumber = Math.floor((nextElection.year - 2024) / 4) + 22; // 22대부터 시작
        
        return {
          type: `제${termNumber}대 국회의원 선거`,
          date: nextElection.date,
          description: '총선',
          icon: HowToVote,
          color: '#003A87',
          cycle: '4년'
        };
      } else if (position === '광역의원' || position === '기초의원') {
        // 지방 4년주기, 기준일: 2026-06-03
        const baseElection = {
          year: 2026,
          month: 5, // 0-based (6월)
          day: 3,
          cycle: 4
        };
        
        const nextElection = getNextElectionDate(baseElection, today);
        const termNumber = Math.floor((nextElection.year - 2026) / 4) + 9; // 9기부터 시작
        
        return {
          type: `제${termNumber}회 전국동시지방선거`,
          date: nextElection.date,
          description: '지방',
          icon: People,
          color: '#006261',
          cycle: '4년'
        };
      }
      
      return null;
    };

    // ?�음 ?�거??계산 ?�수
    const getNextElectionDate = (baseElection, today) => {
      const { year: baseYear, month: baseMonth, day: baseDay, cycle } = baseElection;
      
      // 기�? ?�거??
      let candidateYear = baseYear;
      let candidateDate = new Date(candidateYear, baseMonth, baseDay);
      
      // ?�늘 ?�후??가??가까운 ?�거??찾기
      while (candidateDate <= today) {
        candidateYear += cycle;
        candidateDate = new Date(candidateYear, baseMonth, baseDay);
      }
      
      return {
        year: candidateYear,
        date: candidateDate
      };
    };

    const info = getElectionInfo();
    setElectionInfo(info);
  }, [position]);

  // ?�데??계산
  useEffect(() => {
    if (!electionInfo) return;

    const calculateDDay = () => {
      const today = new Date();
      const electionDate = electionInfo.date;
      
      // ?�간 ?�규??(?�짜�?비교)
      today.setHours(0, 0, 0, 0);
      electionDate.setHours(0, 0, 0, 0);
      
      const diffTime = electionDate - today;
      const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
      
      return diffDays;
    };

    const days = calculateDDay();
    setDDay(days);

    // 매일 ?�정???�데?�트
    const now = new Date();
    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    tomorrow.setHours(0, 0, 0, 0);
    
    const msUntilMidnight = tomorrow - now;
    
    const timeout = setTimeout(() => {
      setDDay(calculateDDay());
      
      // ?�후 24?�간마다 ?�데?�트
      const interval = setInterval(() => {
        setDDay(calculateDDay());
      }, 24 * 60 * 60 * 1000);
      
      return () => clearInterval(interval);
    }, msUntilMidnight);

    return () => clearTimeout(timeout);
  }, [electionInfo]);

  // 선거 정보가 없으면 렌더링하지 않음
  if (!electionInfo || dDay === null) {
    return null;
  }

  // D-Day 텍스트 포맷팅
  const formatDDay = (days) => {
    if (days > 0) {
      return `D-${days}`;
    } else if (days === 0) {
      return '투표일';
    } else {
      return `D+${Math.abs(days)}`;
    }
  };


  // 기존 Chip 색상 함수 (아래에서 계속 사용)
  const getDDayChipProps = (days) => {
    if (days <= 0) {
      return { color: 'error', variant: 'filled' };
    } else if (days <= 30) {
      return { color: 'warning', variant: 'filled' };
    } else if (days <= 365) {
      return { color: 'primary', variant: 'filled' };
    } else {
      return { color: 'default', variant: 'outlined' };
    }
  };

  const Icon = electionInfo.icon;

  return (
    <Paper
      elevation={1}
      data-card-container="true"
      onMouseEnter={() => setCurrentGlowColor(getRandomGlowColor())}
      sx={{
        p: 2.5,
        height: '100%',
        cursor: 'pointer',
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        '&:hover': {
          transform: 'scale(0.98)',
          boxShadow: `0 8px 32px ${currentGlowColor}40, 0 4px 16px ${currentGlowColor}20, inset 0 1px 0 ${currentGlowColor}10`,
          border: `1px solid ${currentGlowColor}30`
        }
      }}
    >
      {/* 1열 2행 배치 */}
      <Box sx={{
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
        mb: 2,
        flex: 1,
        minHeight: 0
      }}>
        {/* 1행: 텍스트 정보 */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, minWidth: 0 }}>
          <Box
            sx={{
              p: { xs: 1, sm: 1.5 },
              borderRadius: 1,
              bgcolor: electionInfo.color,
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0
            }}
          >
            <Icon sx={{ fontSize: { xs: '1rem', sm: '1.25rem' } }} />
          </Box>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="h6" sx={{
              fontWeight: 600,
              mb: 0.5,
              fontSize: { xs: '1rem', sm: '1.25rem' }
            }}>
              {electionInfo.description} 예정
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{
              fontSize: { xs: '0.75rem', sm: '0.875rem' }
            }}>
              {electionInfo.type}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{
              display: 'block',
              mt: 0.5,
              fontSize: { xs: '0.75rem', sm: '0.875rem' }
            }}>
              {electionInfo.date.toLocaleDateString('ko-KR', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                weekday: 'short'
              })}
            </Typography>
          </Box>
        </Box>

        {/* 2행: 7-세그먼트 D-Day 카운터 */}
        <Box sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          flex: 1,
          minHeight: 0
        }}>
          <SevenSegmentDisplay
            dDay={dDay}
            cardHeight="100px"
            color={displayColor}
            onColorChange={setDisplayColor}
          />
        </Box>
      </Box>

        {/* 선거법 준수 알림 */}
        {(() => {
          // 선거 단계 판단
          let phase = 'NORMAL_PERIOD';
          let alertProps = { severity: 'info' };
          let title = '';
          let message = '';

          if (dDay === 0) {
            phase = 'ELECTION_DAY';
            alertProps = { severity: 'error' };
            title = '투표일 - 선거활동 금지';
            message = '모든 형태의 선거활동이 금지됩니다';
          } else if (dDay > 0 && dDay <= 14) {
            phase = 'CAMPAIGN_PERIOD';
            alertProps = { severity: 'success' };
            title = '공식 선거활동 기간';
            message = '선거법에 따른 제한 사항을 준수하여 선거활동이 가능합니다.';
          } else if (dDay > 14 && dDay <= 30) {
            phase = 'PRE_CAMPAIGN_WARNING';
            alertProps = { severity: 'warning' };
            title = '사전 선거활동 주의 기간';
            message = '과도한 조기 홍보와 지지 호청 표현을 피해주세요';
          } else if (dDay > 30 && dDay <= 180) {
            phase = 'NORMAL_PERIOD';
            alertProps = { severity: 'info' };
            title = status === '예비' ? '예비홍보 활동 기간' : '정치활동 홍보 기간';
            message = status === '예비' 
              ? 'SNS 활동과 지역 의안 발굴에 집중하세요'
              : '정치활동 성과를 중심으로 지지기반을 강화하세요';
          }

          // 180일 이상 또는 경우에는 알림 표시하지 않음
          if (dDay > 180 || dDay < 0) return null;

          return (
            <Alert {...alertProps} sx={{ mt: 2 }}>
              <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                {title}
              </Typography>
              <Typography variant="body2">
                {message}
              </Typography>
              {phase === 'PRE_CAMPAIGN_WARNING' && (
                <Typography variant="caption" sx={{ display: 'block', mt: 1, fontStyle: 'italic' }}>
                  AI 원고 작성 및 활동으로 선거법 준수 검토를 진행합니다
                </Typography>
              )}
            </Alert>
          );
        })()}
    </Paper>
  );
}

export default ElectionDDay;


