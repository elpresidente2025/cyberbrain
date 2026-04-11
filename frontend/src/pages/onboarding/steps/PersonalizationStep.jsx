import React from 'react';
import { Box, Typography, Select, MenuItem } from '@mui/material';

const APPLE_BLUE = '#007AFF';

const FIELDS = [
  { name: 'ageDecade', label: '연령대', options: ['20대', '30대', '40대', '50대', '60대', '70대 이상'] },
  { name: 'ageDetail', label: '세부 연령', options: ['초반', '중반', '후반'], disabledWhen: (d) => !d.ageDecade },
  { name: 'gender', label: '성별', options: ['남성', '여성'] },
  { name: 'familyStatus', label: '가족', options: ['미혼', '기혼(자녀 있음)', '기혼(자녀 없음)', '한부모'] },
  { name: 'backgroundCareer', label: '주요 배경', options: ['교육자', '사업가', '공무원', '시민운동가', '법조인', '의료인', '기타'] },
  { name: 'localConnection', label: '지역 연고', options: ['토박이', '오래 거주 (10년 이상)', '이주민', '귀향'] },
  { name: 'politicalExperience', label: '정치 경험', options: ['초선', '재선', '3선 이상', '정치 신인'] },
];

const Row = ({ label, value, options, disabled, onChange, isFirst }) => (
  <>
    {!isFirst && <Box sx={{ height: '1px', bgcolor: 'divider', ml: 2.5 }} />}
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        px: 2.5,
        minHeight: 56,
        gap: 2,
        opacity: disabled ? 0.5 : 1,
      }}
    >
      <Typography
        sx={{
          fontSize: '1.0625rem',
          color: 'text.primary',
          minWidth: 104,
        }}
      >
        {label}
      </Typography>
      <Select
        variant="standard"
        disableUnderline
        fullWidth
        value={value || ''}
        disabled={disabled}
        onChange={onChange}
        displayEmpty
        renderValue={(selected) =>
          selected || (
            <Typography component="span" sx={{ color: 'text.disabled', fontSize: '1.0625rem' }}>
              선택 안함
            </Typography>
          )
        }
        sx={{
          '& .MuiSelect-select': {
            textAlign: 'right',
            color: value ? APPLE_BLUE : 'text.disabled',
            fontSize: '1.0625rem',
            pr: '24px !important',
            py: 1.5,
          },
          '& .MuiSvgIcon-root': { color: 'text.disabled' },
        }}
        MenuProps={{
          PaperProps: { sx: { borderRadius: 2, mt: 1 } },
        }}
      >
        <MenuItem value="">선택 안함</MenuItem>
        {options.map((o) => (
          <MenuItem key={o} value={o}>{o}</MenuItem>
        ))}
      </Select>
    </Box>
  </>
);

const PersonalizationStep = ({ data, onChange }) => (
  <Box
    sx={{
      borderRadius: 3,
      overflow: 'hidden',
      bgcolor: 'background.paper',
      border: '1px solid',
      borderColor: 'divider',
    }}
  >
    {FIELDS.map((f, idx) => {
      const disabled = f.disabledWhen ? f.disabledWhen(data) : false;
      return (
        <Row
          key={f.name}
          isFirst={idx === 0}
          label={f.label}
          value={data[f.name]}
          options={f.options}
          disabled={disabled}
          onChange={(e) => {
            const v = e.target.value;
            onChange(f.name, v);
            if (f.name === 'ageDecade' && !v) {
              onChange('ageDetail', '');
            }
          }}
        />
      );
    })}
  </Box>
);

export default PersonalizationStep;
