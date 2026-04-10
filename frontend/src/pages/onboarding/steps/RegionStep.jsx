import React, { useMemo } from 'react';
import {
  Box,
  Typography,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Stack,
  Alert,
} from '@mui/material';
import {
  getElectionMetroList,
  getElectionLocalList,
  getElectionDistrictList,
} from '../../../utils/election-data-provider';
import { getRequiredRegionFields } from '../../../components/OnboardingGuard';

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
      <Alert severity="warning">이전 단계에서 직책을 먼저 선택해주세요.</Alert>
    );
  }

  return (
    <Box>
      <Typography variant="h5" sx={{ fontWeight: 700, mb: 1 }}>
        활동 지역을 선택해주세요
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        선택하신 직책: <strong>{position}</strong>
      </Typography>

      <Stack spacing={2.5}>
        <FormControl fullWidth>
          <InputLabel>광역자치단체 *</InputLabel>
          <Select
            label="광역자치단체 *"
            value={regionMetro}
            onChange={(e) => {
              onChange('regionMetro', e.target.value);
              onChange('regionLocal', '');
              onChange('electoralDistrict', '');
            }}
          >
            {metros.map((m) => (
              <MenuItem key={m} value={m}>{m}</MenuItem>
            ))}
          </Select>
        </FormControl>

        {needLocal && (
          <FormControl fullWidth disabled={!regionMetro}>
            <InputLabel>기초자치단체 *</InputLabel>
            <Select
              label="기초자치단체 *"
              value={regionLocal}
              onChange={(e) => {
                onChange('regionLocal', e.target.value);
                onChange('electoralDistrict', '');
              }}
            >
              {locals.map((l) => (
                <MenuItem key={l} value={l}>{l}</MenuItem>
              ))}
            </Select>
          </FormControl>
        )}

        {needDistrict && (
          <FormControl fullWidth disabled={!regionLocal}>
            <InputLabel>선거구 *</InputLabel>
            <Select
              label="선거구 *"
              value={electoralDistrict}
              onChange={(e) => onChange('electoralDistrict', e.target.value)}
            >
              {districts.length === 0 && regionLocal && (
                <MenuItem value="" disabled>
                  해당 지역의 선거구 데이터를 찾지 못했습니다
                </MenuItem>
              )}
              {districts.map((d) => (
                <MenuItem key={d} value={d}>{d}</MenuItem>
              ))}
            </Select>
          </FormControl>
        )}

        {!needDistrict && (
          <Alert severity="info" sx={{ mt: 1 }}>
            선택하신 직책({position})은 별도의 선거구 입력이 필요하지 않습니다.
          </Alert>
        )}
      </Stack>
    </Box>
  );
};

export default RegionStep;
