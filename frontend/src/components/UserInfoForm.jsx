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
  Button,
  Stack,
  FormControlLabel,
  Checkbox,
} from '@mui/material';
import { Add } from '@mui/icons-material';
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
  } else if (position === '광역자치단체장' || position === '기초자치단체장') {
    // 지자체장은 국회의원 선거구를 따라감 (지역위원회 소속 기준)
    return districtData['국회의원'] || [];
  }

  return [];
}

/**
 * 자치단체장 호칭 자동 생성
 * @param {string} position - 직책
 * @param {string} regionMetro - 광역자치단체
 * @param {string} regionLocal - 기초자치단체
 * @returns {string} 호칭 (예: 서울특별시장, 부산광역시장, 경기도지사, 성남시장, 강남구청장, 양평군수)
 */
function getAutomaticTitle(position, regionMetro, regionLocal) {
  if (position === '광역자치단체장' && regionMetro) {
    const lastChar = regionMetro.slice(-1);
    if (lastChar === '시') {
      return `${regionMetro}장`;
    } else if (lastChar === '도') {
      return `${regionMetro}지사`;
    }
    return regionMetro; // 기타 경우
  } else if (position === '기초자치단체장' && regionLocal) {
    const lastChar = regionLocal.slice(-1);
    if (lastChar === '시') {
      return `${regionLocal}장`;
    } else if (lastChar === '구') {
      return `${regionLocal}청장`;
    } else if (lastChar === '군') {
      return `${regionLocal}수`;
    }
    return regionLocal; // 기타 경우
  }
  return '';
}

/**
 * 사용자 기본 정보 + 지역구 정보 통합 컴포넌트
 * @param {Object} props
 * @param {string} props.name - 이름
 * @param {string} props.status - 상태 (현역/예비/준비)
 * @param {string} props.customTitle - 사용자 지정 직위 (입력 중인 값)
 * @param {string} props.savedCustomTitle - DB에 저장된 직위 (배지 표시용, 쉼표로 구분)
 * @param {string} props.position - 직책
 * @param {string} props.regionMetro - 광역자치단체
 * @param {string} props.regionLocal - 기초자치단체
 * @param {string} props.electoralDistrict - 선거구
 * @param {Object} props.targetElection - 목표 선거 정보
 * @param {function} props.onChange - 값 변경 콜백 (name, value)
 * @param {function} props.onCustomTitleSave - 직위 즉시 저장 콜백 (newCustomTitle)
 * @param {boolean} props.disabled - 비활성화 여부
 * @param {boolean} props.nameDisabled - 이름 필드만 비활성화 여부
 * @param {boolean} props.enableDuplicateCheck - 중복 체크 활성화 (기본: true)
 * @param {string} props.excludeUserId - 중복 체크에서 제외할 사용자 ID
 * @param {boolean} props.showTitle - 제목 표시 여부 (기본: true)
 */
export default function UserInfoForm({
  name = '',
  status = '현역',
  customTitle = '',
  savedCustomTitle = '',
  position = '',
  regionMetro = '',
  regionLocal = '',
  electoralDistrict = '',
  targetElection = null,
  onChange,
  onCustomTitleSave,
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

  // 셀렉트 목록 (현재 직책)
  const localList = useMemo(() => getLocalList(regionMetro), [regionMetro]);
  const electoralList = useMemo(
    () => getElectoralList(regionMetro, regionLocal, position),
    [regionMetro, regionLocal, position]
  );

  // 목표 선거 셀렉트 목록
  const targetLocalList = useMemo(
    () => getLocalList(targetElection?.regionMetro),
    [targetElection?.regionMetro]
  );
  const targetElectoralList = useMemo(
    () => getElectoralList(
      targetElection?.regionMetro,
      targetElection?.regionLocal,
      targetElection?.position
    ),
    [targetElection?.regionMetro, targetElection?.regionLocal, targetElection?.position]
  );

  // 자치단체장 호칭 자동 생성
  const automaticTitle = useMemo(
    () => getAutomaticTitle(position, regionMetro, regionLocal),
    [position, regionMetro, regionLocal]
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

  // 목표 선거 필드 변경 핸들러
  const handleTargetElectionChange = (field, value) => {
    const currentTarget = targetElection || { position: '', regionMetro: '', regionLocal: '', electoralDistrict: '' };
    let newTarget = { ...currentTarget, [field]: value };

    // 상위 필드 변경 시 하위 필드 초기화
    if (field === 'position') {
      newTarget = { position: value, regionMetro: '', regionLocal: '', electoralDistrict: '' };
    } else if (field === 'regionMetro') {
      newTarget = { ...currentTarget, regionMetro: value, regionLocal: '', electoralDistrict: '' };
    } else if (field === 'regionLocal') {
      newTarget = { ...currentTarget, regionLocal: value, electoralDistrict: '' };
    }

    onChange('targetElection', newTarget);
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

  // 저장된 직위를 배열로 변환 (쉼표로 구분)
  const savedTitles = useMemo(() => {
    if (!savedCustomTitle || savedCustomTitle.trim() === '') return [];
    return savedCustomTitle.split(',').map(t => t.trim()).filter(t => t);
  }, [savedCustomTitle]);

  // 직위 추가 핸들러
  const handleAddTitle = () => {
    const trimmedTitle = customTitle.trim();
    if (!trimmedTitle) return;

    // 이미 존재하는 직위인지 확인
    if (savedTitles.includes(trimmedTitle)) {
      alert('이미 추가된 직위입니다.');
      return;
    }

    // 새로운 직위 목록 생성 (쉼표로 조인)
    const newTitles = [...savedTitles, trimmedTitle];
    const newCustomTitle = newTitles.join(', ');

    // 입력 필드 초기화
    onChange('customTitle', '');

    // 부모 컴포넌트에 즉시 저장 요청 (추가 액션)
    if (onCustomTitleSave) {
      onCustomTitleSave(newCustomTitle, 'add');
    }
  };

  // 직위 삭제 핸들러
  const handleDeleteTitle = (titleToDelete) => {
    // 해당 직위 제거
    const newTitles = savedTitles.filter(t => t !== titleToDelete);
    const newCustomTitle = newTitles.join(', ');

    // 부모 컴포넌트에 즉시 저장 요청 (삭제 액션)
    if (onCustomTitleSave) {
      onCustomTitleSave(newCustomTitle, 'delete');
    }
  };

  // Enter 키로 직위 추가
  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleAddTitle();
    }
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
            <MenuItem value="준비">준비</MenuItem>
          </Select>
        </FormControl>
      </Grid>

      {/* 직위 (준비 상태일 때만 표시) */}
      {status === '준비' && (
        <Grid item xs={12}>
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
            <TextField
              fullWidth
              label="직위 (선택사항)"
              name="customTitle"
              value={customTitle}
              onChange={handleTextFieldChange}
              onKeyPress={handleKeyPress}
              disabled={disabled}
              placeholder="예: 청년위원장, 정책위원장, 여성위원장 등"
              helperText="직위를 입력하고 추가 버튼을 클릭하세요. (Enter 키로도 추가 가능)"
            />
            <Button
              variant="contained"
              onClick={handleAddTitle}
              disabled={disabled || !customTitle.trim()}
              startIcon={<Add />}
              sx={{
                mt: 0,
                minWidth: 100,
                height: 56,
                bgcolor: 'primary.main',
                '&:hover': { bgcolor: 'primary.dark' }
              }}
            >
              추가
            </Button>
          </Box>

          {/* 저장된 직위 배지 표시 (항상 표시) */}
          <Box sx={{ mt: 2 }}>
            <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
              현재 저장된 직위:
            </Typography>
            {savedTitles.length > 0 ? (
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {savedTitles.map((title, index) => (
                  <Chip
                    key={index}
                    label={title}
                    onDelete={() => handleDeleteTitle(title)}
                    disabled={disabled}
                    color="primary"
                    size="medium"
                    sx={{
                      fontWeight: 500,
                      color: 'white',
                      mb: 1
                    }}
                  />
                ))}
              </Stack>
            ) : (
              <Chip
                label="저장된 직위 없음"
                disabled
                color="default"
                size="small"
                sx={{ fontWeight: 400 }}
              />
            )}
          </Box>
        </Grid>
      )}

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
            <MenuItem value="광역자치단체장">광역자치단체장(특별/광역시장, 도지사)</MenuItem>
            <MenuItem value="기초자치단체장">기초자치단체장(시장, 구청장, 군수 등)</MenuItem>
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
        <FormControl fullWidth required={position !== '광역자치단체장'}>
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
          {position === '광역자치단체장' && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
              지역위원회 소속 기준으로 선택하세요
            </Typography>
          )}
        </FormControl>
      </Grid>

      {/* 선거구 */}
      <Grid item xs={12} sm={6}>
        <FormControl fullWidth required={['국회의원', '광역의원', '기초의원'].includes(position)}>
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
          {(position === '광역자치단체장' || position === '기초자치단체장') && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
              지역위원회 소속 기준으로 선택하세요
            </Typography>
          )}
        </FormControl>
      </Grid>

      {/* ========== 목표 선거 섹션 ========== */}
      <Grid item xs={12}>
        <Typography variant="h6" gutterBottom sx={{ mt: 3 }}>
          목표 선거
        </Typography>
        <FormControlLabel
          control={
            <Checkbox
              checked={targetElection?.sameAsCurrentDistrict || false}
              onChange={(e) => {
                const checked = e.target.checked;
                if (checked) {
                  // 체크 시: 현재 지역구 정보와 동일하게 설정
                  onChange('targetElection', {
                    sameAsCurrentDistrict: true,
                    position: position,
                    regionMetro: regionMetro,
                    regionLocal: regionLocal,
                    electoralDistrict: electoralDistrict,
                  });
                } else {
                  // 체크 해제 시: 플래그만 해제하고 값은 유지
                  onChange('targetElection', {
                    ...targetElection,
                    sameAsCurrentDistrict: false,
                  });
                }
              }}
              disabled={disabled || !position}
            />
          }
          label="지역구 정보와 같음"
          sx={{ mb: 1 }}
        />
      </Grid>

      {/* 목표 선거 드롭다운 - "지역구 정보와 같음" 체크 시 숨김 */}
      {!targetElection?.sameAsCurrentDistrict && (
        <>
          {/* 목표 직책 */}
          <Grid item xs={12} sm={6}>
            <FormControl fullWidth required>
              <InputLabel>목표 직책</InputLabel>
              <Select
                value={targetElection?.position || ''}
                label="목표 직책"
                onChange={(e) => handleTargetElectionChange('position', e.target.value)}
                disabled={disabled}
                MenuProps={{
                  keepMounted: false,
                  PaperProps: { style: { zIndex: 1400 } },
                }}
              >
                <MenuItem value="국회의원">국회의원</MenuItem>
                <MenuItem value="광역의원">광역의원(시/도의원)</MenuItem>
                <MenuItem value="기초의원">기초의원(시/군/구의원)</MenuItem>
                <MenuItem value="광역자치단체장">광역자치단체장(특별/광역시장, 도지사)</MenuItem>
                <MenuItem value="기초자치단체장">기초자치단체장(시장, 구청장, 군수 등)</MenuItem>
              </Select>
            </FormControl>
          </Grid>

          {/* 목표 광역자치단체 */}
          <Grid item xs={12} sm={6}>
            <FormControl fullWidth required>
              <InputLabel>목표 광역자치단체</InputLabel>
              <Select
                value={targetElection?.regionMetro || ''}
                label="목표 광역자치단체"
                onChange={(e) => handleTargetElectionChange('regionMetro', e.target.value)}
                disabled={disabled || !targetElection?.position}
                MenuProps={{
                  keepMounted: false,
                  PaperProps: { style: { zIndex: 1400 } },
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

          {/* 목표 기초자치단체 */}
          <Grid item xs={12} sm={6}>
            <FormControl fullWidth required={targetElection?.position !== '광역자치단체장'}>
              <InputLabel>목표 기초자치단체</InputLabel>
              <Select
                value={targetElection?.regionLocal || ''}
                label="목표 기초자치단체"
                onChange={(e) => handleTargetElectionChange('regionLocal', e.target.value)}
                disabled={disabled || !targetElection?.regionMetro}
                MenuProps={{
                  keepMounted: false,
                  PaperProps: { style: { zIndex: 1400 } },
                }}
              >
                {targetLocalList.map((local) => (
                  <MenuItem key={local} value={local}>
                    {local}
                  </MenuItem>
                ))}
              </Select>
              {targetElection?.position === '광역자치단체장' && (
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                  지역위원회 소속 기준으로 선택하세요
                </Typography>
              )}
            </FormControl>
          </Grid>

          {/* 목표 선거구 */}
          <Grid item xs={12} sm={6}>
            <FormControl fullWidth required={['국회의원', '광역의원', '기초의원'].includes(targetElection?.position)}>
              <InputLabel>목표 선거구</InputLabel>
              <Select
                value={targetElection?.electoralDistrict || ''}
                label="목표 선거구"
                onChange={(e) => handleTargetElectionChange('electoralDistrict', e.target.value)}
                disabled={disabled || !targetElection?.regionLocal || !targetElection?.position}
                MenuProps={{
                  keepMounted: false,
                  PaperProps: { style: { zIndex: 1400 } },
                }}
              >
                {targetElectoralList.map((district) => (
                  <MenuItem key={district} value={district}>
                    {district}
                  </MenuItem>
                ))}
              </Select>
              {(targetElection?.position === '광역자치단체장' || targetElection?.position === '기초자치단체장') && (
                <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                  지역위원회 소속 기준으로 선택하세요
                </Typography>
              )}
            </FormControl>
          </Grid>
        </>
      )}

    </>
  );
}

// 🔧 보안상 중복 체크 헬퍼 함수 제거
// export const useDistrictValidation = (duplicateCheck) => { ... }