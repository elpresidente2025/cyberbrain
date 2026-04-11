import React, { useMemo } from 'react';
import {
  Box,
  Typography,
  Select,
  MenuItem,
  Alert,
} from '@mui/material';
import {
  getElectionMetroList,
  getElectionLocalList,
  getElectionDistrictList,
} from '../../../utils/election-data-provider';
import { getRequiredRegionFields } from '../../../components/OnboardingGuard';

const APPLE_BLUE = '#007AFF';

const Row = ({ label, value, placeholder, options, disabled, onChange, isFirst }) => (
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
          minWidth: 96,
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
              {placeholder}
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
          '& .MuiSvgIcon-root': {
            color: 'text.disabled',
          },
        }}
        MenuProps={{
          PaperProps: {
            sx: { borderRadius: 2, mt: 1 },
          },
        }}
      >
        {options.length === 0 && (
          <MenuItem value="" disabled>
            선택할 수 있는 항목이 없습니다
          </MenuItem>
        )}
        {options.map((o) => (
          <MenuItem key={o} value={o}>{o}</MenuItem>
        ))}
      </Select>
    </Box>
  </>
);

const RegionStep = ({ data, onChange }) => {
  const { position, regionMetro, regionLocal, electoralDistrict } = data;

  const metros = useMemo(() => getElectionMetroList(position), [position]);
  const locals = useMemo(
    () => (regionMetro ? getElectionLocalList(position, regionMetro) : []),
    [position, regionMetro]
  );
  const districts = useMemo(
    () => (regionMetro && regionLocal ? getElectionDistrictList(position, regionMetro, regionLocal) : []),
    [position, regionMetro, regionLocal]
  );

  const required = getRequiredRegionFields(position);
  const needLocal = required.includes('regionLocal');
  const needDistrict = required.includes('electoralDistrict');

  if (!position) {
    return (
      <Alert
        severity="warning"
        sx={{ border: 'none', bgcolor: 'action.hover', borderRadius: 2 }}
      >
        이전 단계에서 직책을 먼저 선택해주세요.
      </Alert>
    );
  }

  return (
    <Box
      sx={{
        borderRadius: 3,
        overflow: 'hidden',
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: 'divider',
      }}
    >
      <Row
        isFirst
        label="광역"
        placeholder="선택"
        value={regionMetro}
        options={metros}
        onChange={(e) => {
          onChange('regionMetro', e.target.value);
          onChange('regionLocal', '');
          onChange('electoralDistrict', '');
        }}
      />

      {needLocal && (
        <Row
          label="기초"
          placeholder="선택"
          value={regionLocal}
          options={locals}
          disabled={!regionMetro}
          onChange={(e) => {
            onChange('regionLocal', e.target.value);
            onChange('electoralDistrict', '');
          }}
        />
      )}

      {needDistrict && (
        <Row
          label="선거구"
          placeholder="선택"
          value={electoralDistrict}
          options={districts}
          disabled={!regionLocal}
          onChange={(e) => onChange('electoralDistrict', e.target.value)}
        />
      )}
    </Box>
  );
};

export default RegionStep;
