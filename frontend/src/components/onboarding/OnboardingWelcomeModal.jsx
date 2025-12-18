// frontend/src/components/onboarding/OnboardingWelcomeModal.jsx
import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
  Alert,
  Chip,
  useTheme
} from '@mui/material';
import {
  AutoFixHigh,
  Warning,
  AccountCircle
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { colors } from '../../theme/tokens';

const OnboardingWelcomeModal = ({ open, onClose, userName }) => {
  const theme = useTheme();
  const navigate = useNavigate();

  const handleStartNow = () => {
    onClose();
    navigate('/profile');
  };

  const handleLater = () => {
    // 세션 중에 다시 표시하지 않도록 표시
    sessionStorage.setItem('onboardingDismissed', 'true');
    onClose();
  };

  return (
    <Dialog
      open={open}
      maxWidth="sm"
      fullWidth
      disableEscapeKeyDown
      slotProps={{ backdrop: { 'aria-hidden': false } }}
      sx={{
        '& .MuiDialog-paper': {
          borderRadius: 1,
          bgcolor: 'background.paper'
        }
      }}
    >
      <DialogTitle sx={{
        textAlign: 'center',
        pb: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 1
      }}>
        <AutoFixHigh sx={{ fontSize: 48, color: colors.brand.primary, mb: 1 }} />
        <Typography variant="h5" component="div" sx={{ fontWeight: 'bold', color: colors.brand.primary }}>
          환영합니다!
        </Typography>
        <Chip
          label="계정 활성화 마지막 단계"
          color="primary"
          variant="outlined"
          size="small"
          sx={{ fontSize: '0.75rem' }}
        />
      </DialogTitle>

      <DialogContent sx={{ pt: 2 }}>
        <Box sx={{ textAlign: 'center', mb: 3 }}>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            {userName}님의 고유한 문체를 학습시켜<br />
            '전뇌비서관'을 활성화하는 단계입니다
          </Typography>

          <Typography variant="body1" color="text.secondary" sx={{ lineHeight: 1.8, mb: 2 }}>
            아래 자기소개서 작성을 완료하시면, 즉시 계정이 활성화되어<br />
            모든 기능을 사용하실 수 있습니다.
          </Typography>

          <Box sx={{
            bgcolor: 'rgba(21, 36, 132, 0.05)',
            borderRadius: 1,
            p: 2,
            mb: 2,
            border: '1px solid rgba(21, 36, 132, 0.1)'
          }}>
            <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
              완벽한 글을 쓰실 필요 없습니다.<br />
              {userName}님의 생각과 스타일이 자연스럽게 드러나도록<br />
              편하게 작성해주시는 것이 가장 좋은 학습 데이터가 됩니다.
            </Typography>
          </Box>
        </Box>

        <Alert
          severity="warning"
          icon={<Warning />}
          sx={{
            mb: 2,
            '& .MuiAlert-message': {
              width: '100%'
            }
          }}
        >
          <Typography variant="body2" sx={{ fontWeight: 500 }}>
            자기소개 미완성 시 원고 생성 등 핵심 기능을 사용할 수 없습니다
          </Typography>
        </Alert>

        <Box sx={{
          bgcolor: 'rgba(46, 125, 50, 0.05)',
          borderRadius: 1,
          p: 2,
          border: '1px solid rgba(46, 125, 50, 0.2)'
        }}>
          <Typography variant="caption" color="text.secondary">
            💡 <strong>포함하면 좋은 내용:</strong> 정치 철학, 핵심 공약, 주요 경력, 지역구 비전, 개인적 신념 등<br />
            📝 <strong>권장 분량:</strong> 최소 200자 이상 (제한 없음)
          </Typography>
        </Box>
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 3, gap: 1, justifyContent: 'center' }}>
        <Button
          onClick={handleLater}
          variant="outlined"
          sx={{
            minWidth: 120,
            color: 'text.secondary',
            borderColor: 'divider',
            '&:hover': {
              borderColor: 'text.secondary',
              bgcolor: 'rgba(0,0,0,0.04)'
            }
          }}
        >
          나중에 하기
        </Button>
        <Button
          onClick={handleStartNow}
          variant="contained"
          startIcon={<AccountCircle />}
          sx={{
            minWidth: 140,
            bgcolor: colors.brand.primary,
            color: 'white',
            fontWeight: 600,
            '&:hover': {
              bgcolor: colors.brand.primaryHover
            }
          }}
        >
          지금 설정하기
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default OnboardingWelcomeModal;