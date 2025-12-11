// frontend/src/components/onboarding/CongratulationsModal.jsx
import React, { useState } from 'react';
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
  IconButton,
  useTheme
} from '@mui/material';
import {
  Celebration,
  CheckCircle,
  Launch,
  ContentCopy,
  Close
} from '@mui/icons-material';
import { colors } from '../../theme/tokens';

const CongratulationsModal = ({ open, onClose, userName, bioContent }) => {
  const theme = useTheme();
  const [copied, setCopied] = useState(false);

  const handleCopyBio = async () => {
    try {
      await navigator.clipboard.writeText(bioContent || '');
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('복사 실패:', err);
    }
  };

  const handleOpenNaverBlog = () => {
    // 네이버 블로그 새창으로 열기
    window.open('https://blog.naver.com/', '_blank', 'noopener,noreferrer');
  };

  return (
    <Dialog
      open={open}
      maxWidth="sm"
      fullWidth
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
        gap: 1,
        position: 'relative'
      }}>
        <IconButton
          onClick={onClose}
          sx={{
            position: 'absolute',
            right: 8,
            top: 8,
            color: 'grey.500'
          }}
        >
          <Close />
        </IconButton>

        <Celebration sx={{ fontSize: 64, color: colors.brand.primary, mb: 1 }} />
        <Typography variant="h4" component="div" sx={{ fontWeight: 'bold', color: colors.brand.primary }}>
          🎉 축하합니다!
        </Typography>
        <Chip
          label="전뇌비서관 활성화 완료"
          color="success"
          variant="outlined"
          size="small"
          sx={{ fontSize: '0.75rem' }}
        />
      </DialogTitle>

      <DialogContent sx={{ pt: 2 }}>
        <Box sx={{ textAlign: 'center', mb: 3 }}>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600 }}>
            {userName}님의 전뇌비서관이 활성화되었습니다!
          </Typography>

          <Typography variant="body1" color="text.secondary" sx={{ lineHeight: 1.8, mb: 2 }}>
            이제 모든 기능을 자유롭게 사용하실 수 있습니다.<br />
            작성해주신 자기소개가 AI 학습의 핵심 데이터가 되어<br />
            {userName}님만의 맞춤형 원고를 생성해드릴 것입니다.
          </Typography>
        </Box>

        <Alert
          severity="success"
          icon={<CheckCircle />}
          sx={{
            mb: 3,
            '& .MuiAlert-message': {
              width: '100%'
            }
          }}
        >
          <Typography variant="body2" sx={{ fontWeight: 500 }}>
            ✅ 계정 활성화 완료<br />
            ✅ 원고 생성 기능 사용 가능<br />
            ✅ SNS 변환 기능 사용 가능
          </Typography>
        </Alert>

        <Box sx={{
          bgcolor: 'rgba(21, 36, 132, 0.05)',
          borderRadius: 1,
          p: 3,
          border: '1px solid rgba(21, 36, 132, 0.1)',
          mb: 2
        }}>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600, textAlign: 'center' }}>
            🚀 첫 포스팅으로 시작해보세요!
          </Typography>

          <Typography variant="body2" color="text.secondary" sx={{ mb: 2, lineHeight: 1.6 }}>
            작성하신 자기소개를 네이버 블로그에 첫 포스팅으로 올려보세요.<br />
            유권자들과의 소통을 시작하는 좋은 출발점이 될 것입니다.
          </Typography>

          <Box sx={{ display: 'flex', gap: 1, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Button
              variant="outlined"
              size="small"
              startIcon={<ContentCopy />}
              onClick={handleCopyBio}
              sx={{
                minWidth: 120,
                bgcolor: copied ? 'success.light' : 'transparent',
                color: copied ? 'white' : 'text.primary',
                borderColor: copied ? 'success.main' : 'divider'
              }}
            >
              {copied ? '복사완료!' : '글 복사하기'}
            </Button>

            <Button
              variant="contained"
              size="small"
              startIcon={<Launch />}
              onClick={handleOpenNaverBlog}
              sx={{
                minWidth: 140,
                bgcolor: '#03C75A',
                '&:hover': {
                  bgcolor: '#02B351'
                }
              }}
            >
              네이버 블로그 열기
            </Button>
          </Box>
        </Box>

        <Box sx={{
          bgcolor: 'rgba(255, 193, 7, 0.1)',
          borderRadius: 1,
          p: 2,
          border: '1px solid rgba(255, 193, 7, 0.3)'
        }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.6 }}>
            💡 <strong>팁:</strong> 복사한 글을 네이버 블로그에 붙여넣고, 제목과 내용을 자유롭게 편집하여 포스팅하세요.<br />
            이후 생성되는 모든 원고도 같은 방식으로 블로그에 활용하실 수 있습니다.
          </Typography>
        </Box>
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 3, gap: 1, justifyContent: 'center' }}>
        <Button
          onClick={onClose}
          variant="contained"
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
          시작하기
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default CongratulationsModal;