// frontend/src/components/generate/GenerateActions.jsx
import React from 'react';
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

  // 진행 상황 메시지 결정
  const getProgressMessage = () => {
    if (!progress || !loading) return '생성 중...';
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
              <span>{sessionAttempts === 0 ? '새 원고 생성' : '재생성'}</span>
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
        </Box>

      </Box>

      {/* 모바일에서 추가 안내 */}
      {isMobile && (
        <Typography variant="caption" sx={{ display: 'block', mt: 1, textAlign: 'center', color: 'black' }}>
          한 번에 1개만 생성
        </Typography>
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