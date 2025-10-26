import React from 'react';
import {
  Box,
  Typography,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Grid,
  Card,
  CardContent,
} from '@mui/material';
import { CheckCircleOutline, TrendingUp } from '@mui/icons-material';

const UsageGuide = () => {
  const plans = [
    { name: '스탠다드 플랜', limit: '월 90회 원고 생성 + SNS 원고 무료 생성' }
  ];

  const bonus = [
    '월 90회 원고 생성 가능',
    'SNS 원고 무료 생성 포함',
    '무제한 수정 및 재생성',
    '대시보드에서 현황 확인 가능'
  ];

  const monitoring = [
    '대시보드 인사말 카드에서 실시간 확인',
    '한도 초과 전 알림 제공',
    '플랜 업그레이드로 한도 확장 가능'
  ];

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <TrendingUp sx={{ color: '#2196f3', mr: 2 }} />
        <Typography variant="h5" sx={{ fontWeight: 600 }}>
          월간 사용량 관리
        </Typography>
      </Box>

      <Typography variant="h6" sx={{ fontWeight: 600, mb: 2, color: '#2196f3' }}>
        플랜별 한도
      </Typography>
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {plans.map((plan, index) => (
          <Grid item xs={12} sm={4} key={index}>
            <Card sx={{ textAlign: 'center', border: '1px solid #ddd' }}>
              <CardContent>
                <Typography variant="h6" sx={{ fontWeight: 600, color: '#2196f3' }}>
                  {plan.name}
                </Typography>
                <Typography variant="body1" sx={{ color: '#666' }}>
                  {plan.limit}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
      
      <Typography variant="h6" sx={{ fontWeight: 600, mb: 1, color: '#ff9800' }}>
        보너스 원고
      </Typography>
      <List dense>
        {bonus.map((item, index) => (
          <ListItem key={index} sx={{ py: 0.5 }}>
            <ListItemIcon sx={{ minWidth: 24 }}>
              <CheckCircleOutline sx={{ fontSize: 16, color: '#ff9800' }} />
            </ListItemIcon>
            <ListItemText primary={item} primaryTypographyProps={{ variant: 'body2' }} />
          </ListItem>
        ))}
      </List>
      
      <Typography variant="h6" sx={{ fontWeight: 600, mb: 1, mt: 2, color: '#9c27b0' }}>
        사용량 모니터링
      </Typography>
      <List dense>
        {monitoring.map((item, index) => (
          <ListItem key={index} sx={{ py: 0.5 }}>
            <ListItemIcon sx={{ minWidth: 24 }}>
              <CheckCircleOutline sx={{ fontSize: 16, color: '#9c27b0' }} />
            </ListItemIcon>
            <ListItemText primary={item} primaryTypographyProps={{ variant: 'body2' }} />
          </ListItem>
        ))}
      </List>
    </Box>
  );
};

export default UsageGuide;