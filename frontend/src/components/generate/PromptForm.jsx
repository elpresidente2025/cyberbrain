// frontend/src/components/generate/PromptForm.jsx (최종 수정본)

import React, { useMemo, useState } from 'react';
import {
  Paper,
  Typography,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Grid,
  Box,
  IconButton,
  Tooltip,
  useTheme
} from '@mui/material';
import { AutoAwesome, Add, Remove } from '@mui/icons-material';
// ✅ 1. formConstants에서 카테고리 데이터를 직접 불러와서 자급자족합니다.
import { CATEGORIES } from '../../constants/formConstants';

export default function PromptForm({
  formData,
  // ✅ 2. 부모가 사용하는 `onChange` prop을 정상적으로 받습니다.
  onChange,
  disabled = false,
  isMobile = false
}) {
  const theme = useTheme();
  // 참고자료 목록 상태 관리
  const [instructionsList, setInstructionsList] = useState(() => {
    // formData.instructions가 배열이면 그대로 사용, 아니면 문자열을 배열로 변환
    if (Array.isArray(formData.instructions)) {
      return formData.instructions.length > 0 ? formData.instructions : [''];
    }
    return formData.instructions ? [formData.instructions] : [''];
  });
  // 참고자료 입력창 변경 핸들러
  const handleInstructionChange = (index) => (event) => {
    const { value } = event.target;
    const newList = [...instructionsList];
    newList[index] = value;
    setInstructionsList(newList);
    
    // 부모 컴포넌트에 배열로 전달
    onChange({ instructions: newList });
  };

  // 참고자료 입력창 추가
  const addInstructionField = () => {
    const newList = [...instructionsList, ''];
    setInstructionsList(newList);
    onChange({ instructions: newList });
  };

  // 참고자료 입력창 삭제
  const removeInstructionField = (index) => {
    if (instructionsList.length > 1) {
      const newList = instructionsList.filter((_, i) => i !== index);
      setInstructionsList(newList);
      onChange({ instructions: newList });
    }
  };

  const handleInputChange = (field) => (event) => {
    const { value } = event.target;
    
    // ✅ 3. 부모로부터 받은 `onChange` 함수를 올바른 방식으로 호출합니다.
    if (field === 'category') {
      // 카테고리가 바뀌면, 세부 카테고리 값을 초기화하라는 신호를 함께 보냅니다.
      onChange({ category: value, subCategory: '' });
    } else {
      // 그 외의 경우는 해당 필드만 업데이트하라는 신호를 보냅니다.
      onChange({ [field]: value });
    }
  };

  // 선택된 카테고리에 맞는 세부 카테고리 목록을 안전하게 찾습니다.
  const subCategories = useMemo(() => {
    const selectedCategory = CATEGORIES.find(cat => cat.value === formData.category);
    // subCategories가 배열이 아니거나 없으면, 안전하게 빈 배열을 반환하여 오류를 방지합니다.
    return Array.isArray(selectedCategory?.subCategories) ? selectedCategory.subCategories : [];
  }, [formData.category]);

  const formSize = isMobile ? "small" : "medium";

  return (
    <Paper elevation={0} sx={{ p: isMobile ? 2 : 3, mb: isMobile ? 2 : 3 }}>

      <Grid container spacing={isMobile ? 2 : 3}>
        {/* 카테고리 */}
        <Grid item xs={isMobile ? 6 : 12} md={6}>
          <FormControl fullWidth size={formSize}>
            <InputLabel>카테고리</InputLabel>
            <Select
              value={formData.category || ''}
              label="카테고리"
              onChange={handleInputChange('category')}
              disabled={disabled}
            >
              {/* ✅ 4. 직접 불러온 CATEGORIES 배열을 사용해 정상적인 메뉴를 보여줍니다. */}
              {CATEGORIES.map((cat) => (
                <MenuItem key={cat.value} value={cat.value}>
                  {cat.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>

        {/* 세부 카테고리 */}
        <Grid item xs={isMobile ? 6 : 12} md={6}>
          <FormControl fullWidth size={formSize} disabled={disabled || subCategories.length === 0}>
            <InputLabel>세부 카테고리</InputLabel>
            <Select
              value={formData.subCategory || ''}
              label="세부 카테고리"
              onChange={handleInputChange('subCategory')}
            >
              {subCategories.length === 0 ? (
                <MenuItem value="" disabled>
                  선택사항 없음
                </MenuItem>
              ) : (
                subCategories.map((sub) => (
                  <MenuItem key={sub.value} value={sub.value}>
                    {sub.label}
                  </MenuItem>
                ))
              )}
            </Select>
          </FormControl>
        </Grid>

        {/* ✅ 5. 주제 입력칸을 `topic`에 연결하여 버튼 활성화 문제를 해결합니다. */}
        <Grid item xs={12}>
          <TextField
            fullWidth
            size={formSize}
            label="주제"
            placeholder="어떤 내용의 원고를 작성하고 싶으신가요?"
            value={formData.topic || ''}
            onChange={handleInputChange('topic')}
            disabled={disabled}
            multiline
            rows={2}
            inputProps={{ maxLength: 500 }}
            helperText={`${formData.topic?.length || 0}/500자`}
            FormHelperTextProps={{ sx: { color: 'black' } }}
          />
        </Grid>
        
        {/* ✅ 6. 참고자료 및 배경정보 입력창 - 다중 입력 지원 */}
        <Grid item xs={12}>
          <Box sx={{ mb: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              참고자료 및 배경정보 (선택사항)
            </Typography>
            <Tooltip title="참고자료 입력창 추가">
              <IconButton 
                size="small" 
                onClick={addInstructionField}
                disabled={disabled || instructionsList.length >= 10}
                sx={{ 
                  width: 24,
                  height: 24,
                  backgroundColor: '#006261',
                  color: 'white',
                  border: '1px solid',
                  borderColor: '#006261',
                  '&:hover': { 
                    backgroundColor: '#003A87',
                    borderColor: '#003A87'
                  },
                  '&:disabled': {
                    backgroundColor: 'grey.50',
                    borderColor: 'grey.200',
                    color: 'grey.400'
                  }
                }}
              >
                <Add fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
          
          {instructionsList.map((instruction, index) => (
            <Box key={index} sx={{ mb: index < instructionsList.length - 1 ? 2 : 0 }}>
              <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                <TextField
                  fullWidth
                  size={formSize}
                  label={`참고자료 ${index + 1}`}
                  placeholder={index === 0 
                    ? "실제 뉴스, 정책 내용, 통계 데이터 등 원고 작성에 참고할 배경정보를 입력하세요."
                    : "추가 참고자료나 배경정보를 입력하세요."
                  }
                  value={instruction}
                  onChange={handleInstructionChange(index)}
                  disabled={disabled}
                  multiline
                  rows={index === 0 ? 4 : 3}
                  inputProps={{ maxLength: 1500 }}
                  helperText={index === 0 
                    ? `예시: • 한미정상회담 주요 성과: 반도체 협력, 사이버보안 공동대응 체제 구축 • 지역 현황: 청년 실업률 8.2% (${instruction?.length || 0}/1500자)`
                    : `${instruction?.length || 0}/1500자`
                  }
                  FormHelperTextProps={{ sx: { color: 'black' } }}
                />
                {instructionsList.length > 1 && (
                  <Tooltip title="이 참고자료 삭제">
                    <IconButton
                      size="small"
                      onClick={() => removeInstructionField(index)}
                      disabled={disabled}
                      sx={{ 
                        mt: 1,
                        width: 24,
                        height: 24,
                        backgroundColor: '#55207d',
                        color: 'white',
                        border: '1px solid',
                        borderColor: '#55207d',
                        '&:hover': {
                          backgroundColor: theme.palette.ui?.header || '#152484',
                          borderColor: theme.palette.ui?.header || '#152484'
                        },
                        '&:disabled': {
                          backgroundColor: 'grey.50',
                          borderColor: 'grey.200',
                          color: 'grey.400'
                        }
                      }}
                    >
                      <Remove fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
              </Box>
            </Box>
          ))}
          
          {instructionsList.length >= 10 && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              최대 10개까지 참고자료를 입력할 수 있습니다.
            </Typography>
          )}
        </Grid>

        {/* 키워드 */}
        <Grid item xs={12}>
          <TextField
            fullWidth
            size={formSize}
            label="키워드 (선택사항)"
            placeholder="쉼표(,)로 구분하여 입력하세요"
            value={formData.keywords || ''}
            onChange={handleInputChange('keywords')}
            disabled={disabled}
            helperText="예: 민생안정, 경제활성화, 부동산문제"
            FormHelperTextProps={{ sx: { color: 'black' } }}
          />
        </Grid>
      </Grid>
    </Paper>
  );
}