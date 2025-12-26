// frontend/src/components/onboarding/ProfileIncompleteModal.jsx
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
  Alert
} from '@mui/material';
import {
  Warning,
  Person,
  LocationOn,
  Work,
  CheckCircle,
  Cancel
} from '@mui/icons-material';

/**
 * 프로필 미완성 시 표시되는 모달
 * 필수 정보(직책, 지역)가 입력되지 않은 경우 안내
 */
export default function ProfileIncompleteModal({
  open,
  onClose,
  onFillProfile,
  missingFields = []
}) {
  // 필드별 라벨 및 아이콘 매핑
  const fieldConfig = {
    position: { label: '직책', icon: <Work color="error" /> },
    regionMetro: { label: '광역시/도', icon: <LocationOn color="error" /> },
    regionLocal: { label: '시/군/구', icon: <LocationOn color="error" /> },
    electoralDistrict: { label: '선거구', icon: <LocationOn color="error" /> },
    name: { label: '이름', icon: <Person color="error" /> },
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      slotProps={{ backdrop: { 'aria-hidden': false } }}
    >
      <DialogTitle>
        <Box display="flex" alignItems="center" gap={1}>
          <Warning sx={{ color: '#f57c00', fontSize: 28 }} />
          <Typography variant="h6" component="span" sx={{ fontWeight: 600 }}>
            프로필 정보를 완성해 주세요
          </Typography>
        </Box>
      </DialogTitle>

      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>
          원고 생성을 위해 아래 필수 정보가 필요합니다.
        </Alert>

        <Typography variant="body1" sx={{ mb: 2 }}>
          다음 항목이 입력되지 않았습니다:
        </Typography>

        <List dense>
          {missingFields.map((field) => {
            const config = fieldConfig[field] || { label: field, icon: <Cancel color="error" /> };
            return (
              <ListItem key={field}>
                <ListItemIcon sx={{ minWidth: 36 }}>
                  {config.icon}
                </ListItemIcon>
                <ListItemText
                  primary={config.label}
                  primaryTypographyProps={{ fontWeight: 500 }}
                />
              </ListItem>
            );
          })}
        </List>

        <Box sx={{ mt: 2, p: 2, bgcolor: '#f5f5f5', borderRadius: 1 }}>
          <Typography variant="body2" color="text.secondary">
            프로필 정보는 맞춤형 원고 생성에 필수적입니다.
            정확한 정보를 입력하시면 지역과 직책에 맞는 원고를 생성할 수 있습니다.
          </Typography>
        </Box>
      </DialogContent>

      <DialogActions sx={{ p: 2, pt: 0 }}>
        <Button onClick={onClose} color="inherit">
          나중에 하기
        </Button>
        <Button
          onClick={onFillProfile}
          variant="contained"
          sx={{
            bgcolor: '#006261',
            '&:hover': { bgcolor: '#004d4c' }
          }}
        >
          지금 입력하기
        </Button>
      </DialogActions>
    </Dialog>
  );
}
