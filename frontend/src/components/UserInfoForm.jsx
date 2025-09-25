// frontend/src/components/UserInfoForm.jsx
import React, { useMemo, useState, useEffect } from 'react';
import {
  Grid,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert,
  CircularProgress,
  Chip,
  Typography,
  Box,
} from '@mui/material';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../services/firebase';
import allLocations from '../data/location/locations.index';

const DIST_DATA = allLocations;
const metroList = Object.keys(DIST_DATA);

function getLocalList(metro) {
  return metro && DIST_DATA[metro] ? Object.keys(DIST_DATA[metro]) : [];
}

function getElectoralList(metro, local, position) {
  if (!metro || !local || !DIST_DATA[metro]?.[local] || !position) return [];
  
  const districtData = DIST_DATA[metro][local];
  
  if (position === '국회의원') {
    return districtData['국회의원'] || [];
  } else if (position === '광역의원') {
    return districtData['광역의원'] || [];
  } else if (position === '기초의원') {
    return districtData['기초의원'] || [];
  }
  
  return [];
}

/**
 * 사용자 기본 정보 + 지역구 정보 통합 컴포넌트
 * @param {Object} props
 * @param {string} props.name - 이름
 * @param {string} props.status - 상태 (현역/예비)
 * @param {string} props.position - 직책
 * @param {string} props.regionMetro - 광역자치단체
 * @param {string} props.regionLocal - 기초자치단체
 * @param {string} props.electoralDistrict - 선거구
 * @param {function} props.onChange - 값 변경 콜백 (name, value)
 * @param {boolean} props.disabled - 비활성화 여부
 * @param {boolean} props.nameDisabled - 이름 필드만 비활성화 여부
 * @param {boolean} props.enableDuplicateCheck - 중복 체크 활성화 (기본: true)
 * @param {string} props.excludeUserId - 중복 체크에서 제외할 사용자 ID
 * @param {boolean} props.showTitle - 제목 표시 여부 (기본: true)
 */
export default function UserInfoForm({
  name = '',
  status = '현역',
  position = '',
  regionMetro = '',
  regionLocal = '',
  electoralDistrict = '',
  onChange,
  disabled = false,
  nameDisabled = false,
  enableDuplicateCheck = false, // 🔧 기본값을 false로 변경
  excludeUserId = null,
  showTitle = true,
}) {
  const [duplicateCheck, setDuplicateCheck] = useState({
    status: null, // null, 'checking', 'available', 'occupied', 'error'
    message: '',
    loading: false,
  });

  // 🔧 보안상 이유로 클라이언트 중복 체크 완전 제거
  // 모든 중복 확인은 서버에서만 처리됩니다.

  const callCheckAvailability = useMemo(() => 
    httpsCallable(functions, 'checkDistrictAvailability'), []
  );

  // 셀렉트 목록
  const localList = useMemo(() => getLocalList(regionMetro), [regionMetro]);
  const electoralList = useMemo(
    () => getElectoralList(regionMetro, regionLocal, position),
    [regionMetro, regionLocal, position]
  );

  const handleChange = (name, value) => {
    // 상위 필드 변경 시 하위 필드들 초기화
    let updates = { [name]: value };
    
    if (name === 'position') {
      updates = { position: value, regionMetro: '', regionLocal: '', electoralDistrict: '' };
    } else if (name === 'regionMetro') {
      updates = { regionMetro: value, regionLocal: '', electoralDistrict: '' };
    } else if (name === 'regionLocal') {
      updates = { regionLocal: value, electoralDistrict: '' };
    }

    // 각 변경사항을 개별적으로 호출
    Object.entries(updates).forEach(([key, val]) => {
      onChange(key, val);
    });
  };

  const handleTextFieldChange = (e) => {
    const { name, value } = e.target;
    onChange(name, value);
  };

  const handleSelectChange = (e) => {
    const { name, value } = e.target;
    handleChange(name, value);
  };

  // 현재 선택된 정보 요약
  const getSelectionSummary = () => {
    const parts = [position, regionMetro, regionLocal, electoralDistrict].filter(Boolean);
    return parts.length > 0 ? parts.join(' > ') : '선택해주세요';
  };

  return (
    <>
      {/* 제목 */}
      {showTitle && (
        <Grid item xs={12}>
          <Typography variant="h6" gutterBottom>
            기본 정보
          </Typography>
        </Grid>
      )}

      {/* 이름 */}
      <Grid item xs={12} sm={6}>
        <TextField
          required
          fullWidth
          label="이름"
          name="name"
          value={name}
          onChange={handleTextFieldChange}
          disabled={disabled || nameDisabled}
          helperText={nameDisabled ? "네이버 계정의 이름이 자동으로 설정되었습니다." : ""}
          FormHelperTextProps={{ sx: { color: nameDisabled ? 'success.main' : 'text.secondary' } }}
        />
      </Grid>

      {/* 상태 */}
      <Grid item xs={12} sm={6}>
        <FormControl fullWidth required>
          <InputLabel>상태</InputLabel>
          <Select
            name="status"
            value={status}
            label="상태"
            onChange={handleSelectChange}
            disabled={disabled}
            MenuProps={{
              keepMounted: false,
              PaperProps: {
                style: {
                  zIndex: 1400,
                },
              },
            }}
          >
            <MenuItem value="현역">현역</MenuItem>
            <MenuItem value="후보">후보</MenuItem>
            <MenuItem value="예비">예비</MenuItem>
          </Select>
        </FormControl>
      </Grid>

      {/* 지역구 정보 제목 */}
      <Grid item xs={12}>
        <Typography variant="h6" gutterBottom sx={{ mt: 2 }}>
          지역구 정보
        </Typography>
      </Grid>

      {/* 선택 요약 정보 */}
      <Grid item xs={12}>
      </Grid>

      {/* 직책 */}
      <Grid item xs={12} sm={6}>
        <FormControl fullWidth required>
          <InputLabel>직책</InputLabel>
          <Select
            name="position"
            value={position}
            label="직책"
            onChange={handleSelectChange}
            disabled={disabled}
            MenuProps={{
              keepMounted: false,
              PaperProps: {
                style: {
                  zIndex: 1400,
                },
              },
            }}
          >
            <MenuItem value="국회의원">국회의원</MenuItem>
            <MenuItem value="광역의원">광역의원(시/도의원)</MenuItem>
            <MenuItem value="기초의원">기초의원(시/군/구의원)</MenuItem>
          </Select>
        </FormControl>
      </Grid>

      {/* 광역자치단체 */}
      <Grid item xs={12} sm={6}>
        <FormControl fullWidth required>
          <InputLabel>광역자치단체</InputLabel>
          <Select
            name="regionMetro"
            value={regionMetro}
            label="광역자치단체"
            onChange={handleSelectChange}
            disabled={disabled || !position}
            MenuProps={{
              keepMounted: false,
              PaperProps: {
                style: {
                  zIndex: 1400,
                },
              },
            }}
          >
            {metroList.map((metro) => (
              <MenuItem key={metro} value={metro}>
                {metro}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Grid>

      {/* 기초자치단체 */}
      <Grid item xs={12} sm={6}>
        <FormControl fullWidth required>
          <InputLabel>기초자치단체</InputLabel>
          <Select
            name="regionLocal"
            value={regionLocal}
            label="기초자치단체"
            onChange={handleSelectChange}
            disabled={disabled || !regionMetro}
            MenuProps={{
              keepMounted: false,
              PaperProps: {
                style: {
                  zIndex: 1400,
                },
              },
            }}
          >
            {localList.map((local) => (
              <MenuItem key={local} value={local}>
                {local}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Grid>

      {/* 선거구 */}
      <Grid item xs={12} sm={6}>
        <FormControl fullWidth required>
          <InputLabel>선거구</InputLabel>
          <Select
            name="electoralDistrict"
            value={electoralDistrict}
            label="선거구"
            onChange={handleSelectChange}
            disabled={disabled || !regionLocal || !position}
            MenuProps={{
              keepMounted: false,
              PaperProps: {
                style: {
                  zIndex: 1400,
                },
              },
            }}
          >
            {electoralList.map((district) => (
              <MenuItem key={district} value={district}>
                {district}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Grid>

    </>
  );
}

// 🔧 보안상 중복 체크 헬퍼 함수 제거
// export const useDistrictValidation = (duplicateCheck) => { ... }