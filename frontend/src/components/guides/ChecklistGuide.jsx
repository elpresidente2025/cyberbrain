import React from 'react';
import {
  Box,
  Typography,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Alert,
  useTheme
} from '@mui/material';
import { CheckCircleOutline } from '@mui/icons-material';

const ChecklistGuide = () => {
  const theme = useTheme();
  const required = [
    '날짜, 장소, 인명 등 사실관계',
    '내 정치 성향 및 공약과의 일치성',
    '선거법 위반 요소 점검',
    '오타나 어색한 문장 수정'
  ];

  const warnings = [
    { situation: '통계나 수치가 포함된 경우', action: '출처 재확인' },
    { situation: '다른 정치인 언급 시', action: '사실관계 점검' },
    { situation: '정책 내용 포함 시', action: '최신 정보인지 확인' },
    { situation: '생성된 원고 사용 시', action: '반드시 선거법에 맞게 검토 후 사용. 과도한 자기홍보, 허위사실, 비방 표현 금지' }
  ];

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <CheckCircleOutline sx={{ color: '#4caf50', mr: 2 }} />
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          사용 전 체크포인트
        </Typography>
      </Box>

      <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, color: '#4caf50' }}>
        필수 확인 사항
      </Typography>
      <List dense>
        {required.map((item, index) => (
          <ListItem key={index} sx={{ py: 0.5 }}>
            <ListItemIcon sx={{ minWidth: 24 }}>
              <CheckCircleOutline sx={{ fontSize: 16, color: '#4caf50' }} />
            </ListItemIcon>
            <ListItemText primary={item} primaryTypographyProps={{ variant: 'body2' }} />
          </ListItem>
        ))}
      </List>
      
      <Box sx={{ mt: 3 }}>
        <Typography variant="h6" sx={{ 
          fontWeight: 600, 
          mb: 2, 
          color: theme.palette.mode === 'dark' ? '#f48fb1' : '#d22730' 
        }}>
          특별 주의사항
        </Typography>
        {warnings.map((warning, index) => (
          <Alert key={index} severity="warning" sx={{ mb: 1 }}>
            <Typography variant="body2">
              <strong>{warning.situation}:</strong> {warning.action}
            </Typography>
          </Alert>
        ))}
      </Box>
    </Box>
  );
};

export default ChecklistGuide;