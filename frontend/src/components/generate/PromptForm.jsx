// frontend/src/components/generate/PromptForm.jsx (카테고리 자동 분류 버전)

import React, { useState } from 'react';
import {
  Paper,
  Typography,
  TextField,
  Grid,
  Box,
  IconButton,
  Tooltip,
  useTheme,
  Button,
  Alert
} from '@mui/material';
import { Add, Remove, Search } from '@mui/icons-material';
import KeywordExplorerDialog from './KeywordExplorerDialog';
import { useSystemConfig } from '../../hooks/useSystemConfig';

export default function PromptForm({
  formData,
  // ✅ 2. 부모가 사용하는 `onChange` prop을 정상적으로 받습니다.
  onChange,
  disabled = false,
  isMobile = false,
  user = null
}) {
  const theme = useTheme();

  // 시스템 설정 불러오기
  const { config } = useSystemConfig();

  // 키워드 탐색 다이얼로그 상태
  const [keywordDialogOpen, setKeywordDialogOpen] = useState(false);

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

  // 🔧 수정: 참고자료 onBlur 핸들러 - 포커스를 잃을 때 확실히 업데이트
  const handleInstructionBlur = (index) => (event) => {
    const { value } = event.target;
    if (instructionsList[index] !== value) {
      const newList = [...instructionsList];
      newList[index] = value;
      setInstructionsList(newList);
      onChange({ instructions: newList });
    }
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
    onChange({ [field]: value });
  };

  // 🔧 수정: onBlur 핸들러 추가 - 포커스를 잃을 때 확실히 업데이트
  const handleInputBlur = (field) => (event) => {
    const { value } = event.target;
    // 현재 formData와 다른 경우에만 업데이트 (불필요한 리렌더링 방지)
    if (formData[field] !== value) {
      onChange({ [field]: value });
    }
  };

  // 키워드 선택 핸들러 - 노출 희망 검색어 필드에 추가
  const handleKeywordSelect = (keyword) => {
    const currentKeywords = formData.keywords || '';
    const newKeywords = currentKeywords ? `${currentKeywords}, ${keyword}` : keyword;
    onChange({ keywords: newKeywords });
  };

  const formSize = isMobile ? "small" : "medium";

  return (
    <Paper elevation={0} sx={{ p: isMobile ? 2 : 3, mb: isMobile ? 2 : 3 }}>

      <Grid container spacing={isMobile ? 2 : 3}>
        {/* 카테고리 선택 UI 제거 - AI가 주제를 분석하여 자동 결정 */}

        {/* ✅ 5. 주제 입력칸을 `topic`에 연결하여 버튼 활성화 문제를 해결합니다. */}
        <Grid item xs={12}>
          <TextField
            fullWidth
            size={formSize}
            label="주제"
            placeholder="어떤 내용의 원고를 작성하고 싶으신가요?"
            value={formData.topic || ''}
            onChange={handleInputChange('topic')}
            onBlur={handleInputBlur('topic')}
            disabled={disabled}
            multiline
            rows={2}
            inputProps={{ maxLength: 500 }}
            helperText={`${formData.topic?.length || 0}/500자`}
            FormHelperTextProps={{ sx: { color: 'text.secondary' } }}
          />
        </Grid>

        {/* ✅ 6. 참고자료 및 배경정보 입력창 - 다중 입력 지원 */}
        <Grid item xs={12}>
          <Box sx={{ mb: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              참고자료 입력
            </Typography>
            {/* ✅ 역할 구분 안내 text + 합산 글자수 */}
            {(() => {
              const totalLength = instructionsList.reduce((sum, text) => sum + (text?.length || 0), 0);
              const isOverLimit = totalLength > 4000;
              return (
                <>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                    <span style={{ color: isOverLimit ? '#d32f2f' : 'inherit', fontWeight: isOverLimit ? 700 : 400 }}>
                      합계: {totalLength.toLocaleString()}자
                      {isOverLimit && ' ⚠️ 4,000자 초과 시 앞부분만 분석됩니다'}
                    </span>
                  </Typography>
                </>
              );
            })()}
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
                  label={index === 0 ? '① 내 입장문 / 페이스북 글 (필수)' : `② 뉴스/데이터 ${index}`}
                  placeholder={index === 0
                    ? "내가 이 주제에 대해 가진 입장, 의견, 페이스북에 올린 글 등을 입력하세요. 이 내용이 원고의 핵심 논조가 됩니다."
                    : "기사 본문을 복사하여 붙여넣으세요. (URL 붙여넣기 X, 크롤링 기능 없음)"
                  }
                  value={instruction}
                  onChange={handleInstructionChange(index)}
                  onBlur={handleInstructionBlur(index)}
                  disabled={disabled}
                  required={index === 0}
                  multiline
                  rows={index === 0 ? 4 : 3}
                  // 글자수 제한 해제 (백엔드에서 4000자로 잘림)
                  helperText={index === 0
                    ? `원고의 논조와 주장을 결정합니다. 핵심 메시지를 입력하세요. | ${(instruction?.length || 0).toLocaleString()}자`
                    : `URL이 아닌 기사 본문 텍스트를 직접 복사-붙여넣기 하세요. | ${(instruction?.length || 0).toLocaleString()}자`
                  }
                  FormHelperTextProps={{ sx: { color: 'text.secondary' } }}
                />
                {instructionsList.length > 1 && index !== 0 && (
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
              {/* URL 감지 경고 */}
              {index !== 0 && instruction?.match(/https?:\/\//) && (
                <Alert severity="warning" sx={{ mt: 1 }}>
                  URL이 감지되었습니다. 링크는 분석되지 않습니다.<br />
                  기사 본문을 직접 복사하여 붙여넣어 주세요.
                </Alert>
              )}
            </Box>
          ))}

          {instructionsList.length >= 10 && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              최대 10개까지 참고자료를 입력할 수 있습니다.
            </Typography>
          )}
        </Grid>

        {/* 노출 희망 검색어 */}
        <Grid item xs={12}>
          <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
            <TextField
              fullWidth
              size={formSize}
              label="노출 희망 검색어 (선택사항)"
              placeholder="쉼표(,)로 구분하여 입력하세요"
              value={formData.keywords || ''}
              onChange={handleInputChange('keywords')}
              onBlur={handleInputBlur('keywords')}
              disabled={disabled}
              helperText="예: 성수역 3번 출구, 울산대 대학로, 계양IC 정체 등"
              FormHelperTextProps={{ sx: { color: 'text.secondary' } }}
            />
            {/* AI 검색어 추천 버튼 - 관리자가 활성화한 경우에만 표시 */}
            {config.aiKeywordRecommendationEnabled && (
              <Tooltip title="AI 검색어 추천">
                <Button
                  variant="outlined"
                  onClick={() => setKeywordDialogOpen(true)}
                  disabled={disabled}
                  sx={{
                    minWidth: isMobile ? '40px' : '120px',
                    height: isMobile ? '40px' : '56px',
                    mt: 0.5,
                    px: isMobile ? 1 : 2
                  }}
                >
                  <Search />
                  {!isMobile && <Typography variant="button" sx={{ ml: 1 }}>검색어 추천</Typography>}
                </Button>
              </Tooltip>
            )}
          </Box>
        </Grid>
      </Grid>

      {/* 검색어 추천 다이얼로그 - 관리자가 활성화한 경우에만 렌더링 */}
      {
        config.aiKeywordRecommendationEnabled && (
          <KeywordExplorerDialog
            open={keywordDialogOpen}
            onClose={() => setKeywordDialogOpen(false)}
            onSelectKeyword={handleKeywordSelect}
            topic={formData.topic}
            instructions={instructionsList}
            user={user}
          />
        )
      }
    </Paper >
  );
}