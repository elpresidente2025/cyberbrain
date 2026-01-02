// frontend/src/components/generate/GenerateActions.jsx
import React, { useEffect, useMemo, useState } from 'react';
import {
  Box,
  Button,
  Typography,
  Chip,
  Alert
} from '@mui/material';
import { AutoAwesome, Refresh } from '@mui/icons-material';
import { LoadingButton } from '../loading';
import { colors, shadows } from '../../theme/tokens';

export default function GenerateActions({
  onGenerate,
  onReset,
  loading = false,
  canGenerate = true,
  attempts = 0,
  maxAttempts = 3,
  drafts = [],
  progress = null,
  isMobile = false,
  // 🆕 세션 정보
  sessionAttempts = 0,
  maxSessionAttempts = 3,
  canRegenerate = false
}) {
  const attemptsRemaining = maxAttempts - attempts;
  const [rotatingIndex, setRotatingIndex] = useState(0);

  const generatingVariants = useMemo(() => ([
    '원고 초안 정리 중...',
    '핵심 메시지 다듬는 중...',
    '문장 흐름 정리 중...',
    '근거와 구조를 정돈 중...',
    '표현을 자연스럽게 다듬는 중...',
    '읽기 쉬운 문장으로 변환 중...',
    '주요 포인트 정리 중...',
    '문단 구성 조율 중...',
    '맥락을 반영해 문장을 다듬는 중...',
    '완성도를 높이는 중...'
  ]), []);

  useEffect(() => {
    if (!loading || !progress || progress.step !== 3) {
      setRotatingIndex(0);
      return undefined;
    }

    const intervalId = setInterval(() => {
      setRotatingIndex((prev) => (prev + 1) % generatingVariants.length);
    }, 2000);

    return () => clearInterval(intervalId);
  }, [loading, progress?.step, generatingVariants.length]);

  // 진행 상황 메시지 결정
  const getProgressMessage = () => {
    if (!progress || !loading) return '생성 중...';
    if (progress.step === 3) {
      return generatingVariants[rotatingIndex] || '원고 초안 정리 중...';
    }
    return progress.message || '처리 중...';
  };

  return (
    <Box sx={{ mb: 3 }}>
      {/* 액션 버튼들 */}
      <Box sx={{ 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: isMobile ? 'stretch' : 'space-between', 
        flexDirection: isMobile ? 'column' : 'row',
        gap: 2 
      }}>
        {/* 왼쪽: 생성 버튼 */}
        <Box sx={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: 2,
          width: isMobile ? '100%' : 'auto'
        }}>
          <LoadingButton
            variant="contained"
            size={isMobile ? "medium" : "large"}
            startIcon={<AutoAwesome />}
            onClick={onGenerate}
            disabled={!canGenerate}
            loading={loading}
            loadingText={getProgressMessage()}
            sx={{
              minWidth: isMobile ? 'auto' : 160,
              flex: isMobile ? 1 : 'none',
              bgcolor: canGenerate ? `${colors.brand.primary} !important` : '#757575 !important',
              color: 'white !important',
              fontWeight: 600,
              transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              '&.Mui-disabled': {
                bgcolor: '#757575 !important',
                color: 'rgba(255, 255, 255, 0.6) !important'
              },
              ...(canGenerate && !loading && {
                boxShadow: shadows.glow.brand,
                '&:hover': {
                  bgcolor: `${colors.brand.primaryHover} !important`,
                  boxShadow: shadows.glow.brandHover,
                  transform: 'scale(0.98)',
                }
              })
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <span>{sessionAttempts === 0 ? '원고 생성 시도' : '재생성'}</span>
              {sessionAttempts > 0 && (
                <Chip
                  label={`${sessionAttempts}/${maxSessionAttempts}`}
                  size="small"
                  sx={{
                    bgcolor: canRegenerate ? 'rgba(255, 255, 255, 0.2)' : 'rgba(255, 0, 0, 0.3)',
                    color: 'white',
                    fontSize: '0.75rem',
                    height: '20px',
                    fontWeight: 600
                  }}
                />
              )}
            </Box>
          </LoadingButton>


          {drafts.length > 0 && (
            <Button
              variant="outlined"
              size={isMobile ? "medium" : "large"}
              startIcon={<Refresh />}
              onClick={onReset}
              disabled={loading}
              color="secondary"
              sx={{ flexShrink: 0 }}
            >
              {isMobile ? '초기화' : '새로 시작'}
            </Button>
          )}

          {/* 🆕 세션 막혔을 때 '새 생성 시작' 버튼 */}
          {!canRegenerate && sessionAttempts >= maxSessionAttempts && sessionAttempts > 0 && (
            <Button
              variant="contained"
              size={isMobile ? "medium" : "large"}
              startIcon={<Refresh />}
              onClick={onReset}
              disabled={loading}
              color="warning"
              sx={{
                flexShrink: 0,
                bgcolor: '#ff9800 !important',
                '&:hover': {
                  bgcolor: '#f57c00 !important'
                }
              }}
            >
              새 생성 시작
            </Button>
          )}
        </Box>

      </Box>

      {/* 🆕 세션 한도 도달 안내 */}
      {!canRegenerate && sessionAttempts >= maxSessionAttempts && sessionAttempts > 0 && (
        <Alert severity="info" sx={{ mt: 2 }}>
          <Typography variant="body2" fontWeight="bold" sx={{ color: 'black' }}>ℹ️ 재생성 한도 도달</Typography>
          <Typography variant="body2" sx={{ color: 'black' }}>
            현재 생성 세션에서 {maxSessionAttempts}회 시도를 모두 사용했습니다.
            위의 원고 중 하나를 선택하여 저장하거나, "새 생성 시작" 버튼을 눌러 새로운 원고를 생성해주세요.
          </Typography>
        </Alert>
      )}

      {/* 주의사항 */}
      <Alert severity="warning" sx={{ mt: 2 }}>
        <Typography variant="body2" fontWeight="bold" sx={{ color: 'black' }}>⚠️ 주의사항</Typography>
        <Typography variant="body2" sx={{ color: 'black' }}>
          전자두뇌비서관은 원고 초안을 제공하며, 반드시 사용자가 최종 검수 및 수정해야 합니다.
        </Typography>
      </Alert>
    </Box>
  );
}
