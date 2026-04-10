import React from 'react';
import { Box, Typography, Stack, Chip } from '@mui/material';
import { Schedule, Verified, AutoAwesome } from '@mui/icons-material';

const WelcomeStep = ({ userName }) => {
  return (
    <Box sx={{ textAlign: 'center', py: 2 }}>
      <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
        {userName ? `${userName}님, 환영합니다` : '환영합니다'}
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 4 }}>
        전자두뇌비서관을 사용하려면 몇 가지 필수 정보를 입력해야 합니다.
      </Typography>

      <Stack direction="row" spacing={1} justifyContent="center" flexWrap="wrap" sx={{ mb: 4, gap: 1 }}>
        <Chip icon={<Schedule />} label="약 2~3분 소요" color="primary" variant="outlined" />
        <Chip icon={<Verified />} label="필수 정보만 입력" color="success" variant="outlined" />
        <Chip icon={<AutoAwesome />} label="맞춤 원고 생성" color="info" variant="outlined" />
      </Stack>

      <Box
        sx={{
          p: 3,
          bgcolor: 'action.hover',
          borderRadius: 2,
          textAlign: 'left',
        }}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1 }}>
          입력하실 항목
        </Typography>
        <Typography variant="body2" color="text.secondary" component="ol" sx={{ pl: 2, m: 0 }}>
          <li>현재 직책 또는 출마 예정 직책</li>
          <li>활동 지역 · 선거구</li>
          <li>자기소개 (최소 50자)</li>
        </Typography>
      </Box>
    </Box>
  );
};

export default WelcomeStep;
