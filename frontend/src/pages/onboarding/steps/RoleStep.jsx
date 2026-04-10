import React from 'react';
import {
  Box,
  Typography,
  Card,
  CardActionArea,
  Stack,
} from '@mui/material';
import {
  AccountBalance,
  LocationCity,
  Apartment,
  HowToVote,
  Gavel,
} from '@mui/icons-material';

const POSITION_OPTIONS = [
  {
    value: '국회의원',
    label: '국회의원',
    description: '총선 지역구 또는 비례대표',
    icon: AccountBalance,
  },
  {
    value: '광역자치단체장',
    label: '광역자치단체장',
    description: '특별시장 · 광역시장 · 도지사',
    icon: LocationCity,
  },
  {
    value: '기초자치단체장',
    label: '기초자치단체장',
    description: '시장 · 군수 · 구청장',
    icon: Apartment,
  },
  {
    value: '광역의원',
    label: '광역의원',
    description: '특별시 · 광역시 · 도 의회 의원',
    icon: HowToVote,
  },
  {
    value: '기초의원',
    label: '기초의원',
    description: '시 · 군 · 구 의회 의원',
    icon: Gavel,
  },
];

const RoleStep = ({ value, onChange }) => {
  return (
    <Box>
      <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
        현재 직책 또는 출마 예정 직책을 선택해주세요
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        선택한 직책에 맞춰 다음 단계에서 지역·선거구를 입력합니다.
      </Typography>

      <Stack spacing={1.5}>
        {POSITION_OPTIONS.map((opt) => {
          const Icon = opt.icon;
          const selected = value === opt.value;
          return (
            <Card
              key={opt.value}
              elevation={selected ? 4 : 1}
              sx={{
                borderRadius: 2,
                borderWidth: 2,
                borderStyle: 'solid',
                borderColor: selected ? 'primary.main' : 'divider',
                transition: 'all 0.2s ease',
              }}
            >
              <CardActionArea onClick={() => onChange(opt.value)} sx={{ p: 2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                  <Box
                    sx={{
                      width: 48,
                      height: 48,
                      borderRadius: '50%',
                      bgcolor: selected ? 'primary.main' : 'action.hover',
                      color: selected ? 'primary.contrastText' : 'text.secondary',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                    }}
                  >
                    <Icon />
                  </Box>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                      {opt.label}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {opt.description}
                    </Typography>
                  </Box>
                </Box>
              </CardActionArea>
            </Card>
          );
        })}
      </Stack>
    </Box>
  );
};

export default RoleStep;
