import React from 'react';
import { Box, Typography, Stack, Chip, Alert } from '@mui/material';
import { CheckCircle } from '@mui/icons-material';

const CompleteStep = ({ data }) => {
  return (
    <Box sx={{ textAlign: 'center', py: 2 }}>
      <CheckCircle sx={{ fontSize: 72, color: 'success.main', mb: 2 }} />
      <Typography variant="h4" sx={{ fontWeight: 700, mb: 1 }}>
        설정이 완료되었습니다
      </Typography>
      <Typography variant="body1" color="text.secondary" sx={{ mb: 4 }}>
        입력하신 정보를 바탕으로 맞춤 원고를 생성할 수 있습니다.
      </Typography>

      <Box
        sx={{
          p: 3,
          bgcolor: 'action.hover',
          borderRadius: 2,
          textAlign: 'left',
          mb: 3,
        }}
      >
        <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 1.5 }}>
          입력하신 정보
        </Typography>
        <Stack direction="row" spacing={1} flexWrap="wrap" sx={{ gap: 1 }}>
          {data.position && <Chip label={`직책: ${data.position}`} color="primary" size="small" />}
          {data.regionMetro && <Chip label={`광역: ${data.regionMetro}`} color="info" size="small" />}
          {data.regionLocal && <Chip label={`기초: ${data.regionLocal}`} color="info" size="small" />}
          {data.electoralDistrict && (
            <Chip label={`선거구: ${data.electoralDistrict}`} color="info" size="small" />
          )}
          {data.bio && (
            <Chip label={`자기소개 ${data.bio.trim().length}자`} color="success" size="small" />
          )}
        </Stack>
      </Box>

      <Alert severity="info" sx={{ textAlign: 'left' }}>
        프로필 페이지에서 선택 정보(나이대, 경력, 공약 등)를 추가로 입력하면 원고 품질이 더욱 향상됩니다.
      </Alert>
    </Box>
  );
};

export default CompleteStep;
