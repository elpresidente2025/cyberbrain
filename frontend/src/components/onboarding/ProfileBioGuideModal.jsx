// frontend/src/components/onboarding/ProfileBioGuideModal.jsx
import React from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider,
  Chip
} from '@mui/material';
import {
  Edit,
  CheckCircle,
  Psychology,
  Campaign,
  Work,
  LocationCity,
  Favorite,
  TrendingUp
} from '@mui/icons-material';

const ProfileBioGuideModal = ({ open, onClose, onStartWriting, userName }) => {

  const handleStartWriting = () => {
    onClose();
    if (onStartWriting) {
      onStartWriting();
    }
  };

  const guideItems = [
    {
      icon: <Psychology color="primary" />,
      title: "정치 철학",
      description: "대표님의 정치적 신념과 가치관"
    },
    {
      icon: <Campaign color="primary" />,
      title: "핵심 공약",
      description: "유권자들에게 전달하고 싶은 주요 약속"
    },
    {
      icon: <Work color="primary" />,
      title: "주요 경력",
      description: "정치적 배경과 전문성을 보여주는 이력"
    },
    {
      icon: <LocationCity color="primary" />,
      title: "지역구 비전",
      description: "지역 발전을 위한 구체적인 계획과 목표"
    },
    {
      icon: <Favorite color="primary" />,
      title: "개인적 신념",
      description: "사명감과 봉사정신, 개인적 동기"
    },
    {
      icon: <TrendingUp color="primary" />,
      title: "미래 비전",
      description: "장기적인 정치적 목표와 꿈"
    }
  ];

  return (
    <Dialog
      open={open}
      maxWidth="md"
      fullWidth
      disableEscapeKeyDown
      sx={{
        '& .MuiDialog-paper': {
          borderRadius: 2,
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
        <Edit sx={{ fontSize: 48, color: '#152484', mb: 1 }} />
        <Typography variant="h5" component="div" sx={{ fontWeight: 'bold', color: '#152484' }}>
          문체 DNA 입력하기
        </Typography>
        <Chip
          label="전뇌비서관 개인화 핵심 단계"
          color="primary"
          variant="outlined"
          size="small"
          sx={{ fontSize: '0.75rem' }}
        />
      </DialogTitle>

      <DialogContent sx={{ pt: 2 }}>
        <Box sx={{ mb: 3 }}>
          <Typography variant="h6" sx={{ mb: 2, fontWeight: 600, textAlign: 'center' }}>
            {userName}님만의 고유한 문체와 가치관을<br />
            자기소개서에 자유롭게 담아주세요
          </Typography>

          <Box sx={{
            bgcolor: 'rgba(21, 36, 132, 0.05)',
            borderRadius: 2,
            p: 2,
            mb: 3,
            border: '1px solid rgba(21, 36, 132, 0.1)',
            textAlign: 'center'
          }}>
            <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic', mb: 1 }}>
              💡 <strong>핵심 포인트:</strong> 완벽한 글보다는 <strong>진정성</strong>이 중요합니다
            </Typography>
            <Typography variant="caption" color="text.secondary">
              AI가 학습할 수 있는 충분한 분량(최소 200자)만 작성해주시면 됩니다
            </Typography>
          </Box>
        </Box>

        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
            <CheckCircle sx={{ color: 'success.main' }} />
            포함하면 좋은 내용들
          </Typography>

          <List dense sx={{ bgcolor: 'rgba(0,0,0,0.02)', borderRadius: 1 }}>
            {guideItems.map((item, index) => (
              <React.Fragment key={index}>
                <ListItem>
                  <ListItemIcon sx={{ minWidth: 40 }}>
                    {item.icon}
                  </ListItemIcon>
                  <ListItemText
                    primary={item.title}
                    secondary={item.description}
                    primaryTypographyProps={{ fontWeight: 500, fontSize: '0.9rem' }}
                    secondaryTypographyProps={{ fontSize: '0.8rem' }}
                  />
                </ListItem>
                {index < guideItems.length - 1 && <Divider variant="inset" />}
              </React.Fragment>
            ))}
          </List>
        </Box>

        <Box sx={{
          bgcolor: 'rgba(255, 193, 7, 0.1)',
          borderRadius: 1,
          p: 2,
          border: '1px solid rgba(255, 193, 7, 0.3)'
        }}>
          <Typography variant="body2" sx={{ fontWeight: 500, mb: 1 }}>
            ✍️ 작성 팁
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.6 }}>
            • 평소 말하는 톤으로 편하게 작성하세요<br />
            • 구체적인 경험과 사례를 포함하면 더욱 좋습니다<br />
            • 유권자들과 소통하고 싶은 메시지를 담아보세요<br />
            • 분량 제한은 없으니 충분히 자세히 작성해주세요
          </Typography>
        </Box>
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 3, gap: 1, justifyContent: 'center' }}>
        <Button
          onClick={onClose}
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
          onClick={handleStartWriting}
          variant="contained"
          startIcon={<Edit />}
          sx={{
            minWidth: 140,
            bgcolor: '#152484',
            '&:hover': {
              bgcolor: '#003A87'
            }
          }}
        >
          작성 시작하기
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ProfileBioGuideModal;