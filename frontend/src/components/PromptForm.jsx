import React from 'react';
import { 
  Box, 
  TextField, 
  Button, 
  Stack, 
  FormControl, 
  InputLabel, 
  Select, 
  MenuItem,
  Typography,
  Chip,
  Alert,
  Paper,
  Divider
} from '@mui/material';
import { useAuth } from '../hooks/useAuth';
import { CATEGORIES, CATEGORY_DESCRIPTIONS } from '../constants/formConstants';
import { LoadingButton } from './loading';

/**
 * @description AI 포스트 생성을 위한 프롬프트 입력 폼 컴포넌트
 */
const PromptForm = ({ 
  category = '일반', 
  setCategory, 
  subCategory = '', 
  setSubCategory,
  prompt = '', 
  setPrompt, 
  keywords = '', 
  setKeywords, 
  onGenerate, 
  isLoading = false, 
  isGenerated = false,
  validation = {}
}) => {
  
  // 🔧 수정: 올바른 구조로 변경
  const { user } = useAuth();
  
  // 카테고리 변경 시 세부 카테고리 초기화
  const handleCategoryChange = (event) => {
    const newCategory = event.target.value;
    setCategory(newCategory);
    if (setSubCategory) {
      setSubCategory(''); // 세부 카테고리 초기화
    }
  };

  // 폼 제출 핸들러
  const handleFormSubmit = (event) => {
    event.preventDefault();
    if (!validation.hasErrors && prompt.trim() && !isLoading) {
      onGenerate();
    }
  };

  // 입력값 실시간 검증
  const getPromptError = () => {
    if (!prompt.trim()) return '주제를 입력해주세요.';
    if (prompt.length < 5) return '주제는 최소 5자 이상 입력해주세요.';
    if (prompt.length > 500) return '주제는 500자를 초과할 수 없습니다.';
    return '';
  };

  const getKeywordsError = () => {
    if (keywords.length > 200) return '키워드는 200자를 초과할 수 없습니다.';
    return '';
  };

  const promptError = getPromptError();
  const keywordsError = getKeywordsError();
  const hasErrors = !!promptError || !!keywordsError;

  const buttonText = isGenerated ? '초안 다시 생성하기' : 'AI 초안 생성하기';

  // 🔧 수정: user 사용으로 변경
  const regionInfo = user ? [
    user.regionMetro,
    user.regionLocal,
    user.electoralDistrict
  ].filter(Boolean).join(' > ') : '';

  return (
    <Paper elevation={2} sx={{ p: 3, mb: 3 }}>
      <Typography variant="h6" gutterBottom sx={{ color: 'black' }}>
        📝 AI 원고 생성
      </Typography>
      
      {/* 사용자 정보 표시 */}
      {user && (
        <Alert severity="info" sx={{ mb: 2 }}>
          <Typography variant="body2" sx={{ color: 'black' }}>
            <strong>{user.name || '이름 없음'}</strong> 
            {user.position && ` (${user.position})`}
            {regionInfo && ` | ${regionInfo}`}
          </Typography>
        </Alert>
      )}

      <Box component="form" onSubmit={handleFormSubmit}>
        <Stack spacing={3}>
          {/* 카테고리 선택 */}
          <FormControl fullWidth>
            <InputLabel>카테고리</InputLabel>
            <Select
              value={category}
              label="카테고리"
              onChange={handleCategoryChange}
              disabled={isLoading}
            >
              {Object.keys(CATEGORIES).map((cat) => (
                <MenuItem key={cat} value={cat}>
                  {cat}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {/* 세부 카테고리 선택 */}
          {CATEGORIES[category] && CATEGORIES[category].length > 0 && (
            <FormControl fullWidth>
              <InputLabel>세부 카테고리</InputLabel>
              <Select
                value={subCategory}
                label="세부 카테고리"
                onChange={(e) => setSubCategory(e.target.value)}
                disabled={isLoading}
              >
                <MenuItem value="">
                  <em>선택 안함</em>
                </MenuItem>
                {CATEGORIES[category].map((subCat) => (
                  <MenuItem key={subCat} value={subCat}>
                    {subCat}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}

          {/* 카테고리 설명 */}
          {CATEGORY_DESCRIPTIONS[category] && (
            <Alert severity="info">
              <Typography variant="body2" sx={{ color: 'black' }}>
                {CATEGORY_DESCRIPTIONS[category]}
              </Typography>
            </Alert>
          )}

          {/* 주제 입력 */}
          <TextField
            label="주제 및 내용"
            multiline
            rows={4}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            error={!!promptError}
            helperText={promptError || `${prompt.length}/500자`}
            FormHelperTextProps={{ sx: { color: 'black' } }}
            placeholder="어떤 내용의 원고를 작성하시겠습니까? 구체적으로 설명해주세요."
            disabled={isLoading}
            fullWidth
            required
          />

          {/* 키워드 입력 */}
          <TextField
            label="핵심 키워드 (선택사항)"
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            error={!!keywordsError}
            helperText={keywordsError || `${keywords.length}/200자 | 쉼표로 구분하여 입력하세요`}
            FormHelperTextProps={{ sx: { color: 'black' } }}
            placeholder="예: 경제정책, 일자리 창출, 청년 지원"
            disabled={isLoading}
            fullWidth
          />

          {/* 키워드 미리보기 */}
          {keywords.trim() && (
            <Box>
              <Typography variant="body2" gutterBottom sx={{ color: 'black' }}>
                키워드 미리보기:
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {keywords.split(',').map((keyword, index) => (
                  <Chip 
                    key={index} 
                    label={keyword.trim()} 
                    size="small" 
                    variant="outlined"
                  />
                ))}
              </Box>
            </Box>
          )}

          <Divider />

          {/* 생성 버튼 */}
          <LoadingButton
            type="submit"
            variant="contained"
            size="large"
            disabled={hasErrors || !prompt.trim()}
            loading={isLoading}
            loadingText="생성 중..."
            fullWidth
          >
            {buttonText}
          </LoadingButton>
        </Stack>
      </Box>
    </Paper>
  );
};

export default PromptForm;