// frontend/src/components/generate/PromptForm.jsx (카테고리 자동 분류 버전)

import React, { useEffect, useState } from 'react';
import {
  Paper,
  Typography,
  TextField,
  Grid,
  Box,
  IconButton,
  Tooltip,

  Button,
  Alert
} from '@mui/material';
import { Add, Remove, Search } from '@mui/icons-material';
import KeywordExplorerDialog from './KeywordExplorerDialog';
import { useSystemConfig } from '../../hooks/useSystemConfig';
import { checkElectionExpressions } from '../../utils/electionExpressionCheck';

export default function PromptForm({
  formData,
  // ✅ 2. 부모가 사용하는 `onChange` prop을 정상적으로 받습니다.
  onChange,
  disabled = false,
  isMobile = false,
  user = null,
  errors = {}
}) {

  // 시스템 설정 불러오기
  const { config } = useSystemConfig();

  // 키워드 탐색 다이얼로그 상태
  const [keywordDialogOpen, setKeywordDialogOpen] = useState(false);

  // 키워드 경고 메시지 상태
  const [keywordWarning, setKeywordWarning] = useState(null);

  // 선거법 금지 표현 위반 목록
  const [electionViolations, setElectionViolations] = useState([]);

  const normalizeInstructions = (instructions) => {
    if (Array.isArray(instructions)) {
      return instructions.length > 0 ? instructions : [''];
    }
    return instructions ? [instructions] : [''];
  };

  const areInstructionListsEqual = (a, b) => {
    if (a.length !== b.length) return false;
    return a.every((item, index) => item === b[index]);
  };

  const normalizeKeywordsInput = (rawValue, maxKeywords = 2) => {
    const tokens = String(rawValue || '')
      .split(',')
      .map((token) => token.trim())
      .filter((token) => token.length > 0);

    const exceeded = tokens.length > maxKeywords;
    const normalized = tokens.slice(0, maxKeywords).join(', ');
    return { normalized, exceeded };
  };

  const showKeywordWarning = (message = '검색어는 최대 2개까지만 입력 가능합니다.') => {
    setKeywordWarning(message);
    setTimeout(() => setKeywordWarning(null), 3000);
  };

  const iconButtonSizeSx = {
    width: { xs: 44, sm: 36 },
    height: { xs: 44, sm: 36 },
    minWidth: { xs: 44, sm: 36 },
    minHeight: { xs: 44, sm: 36 },
  };

  // 참고자료 목록 상태 관리
  const [instructionsList, setInstructionsList] = useState(() => normalizeInstructions(formData.instructions));

  useEffect(() => {
    const normalizedInstructions = normalizeInstructions(formData.instructions);
    setInstructionsList((prev) => (
      areInstructionListsEqual(prev, normalizedInstructions) ? prev : normalizedInstructions
    ));
  }, [formData.instructions]);
  // 참고자료 입력창 변경 핸들러
  const handleInstructionChange = (index) => (event) => {
    const { value } = event.target;
    const newList = [...instructionsList];
    newList[index] = value;
    setInstructionsList(newList);

    // 부모 컴포넌트에 배열로 전달
    onChange({ instructions: newList });

    // 입장문(index 0) 타이핑 중 선거법 금지 표현 실시간 검사
    if (index === 0) {
      const violations = checkElectionExpressions(value, user?.status);
      setElectionViolations(violations);
      onChange({ _electionViolations: violations.length > 0 ? violations : null });
    }
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
    // 입장문(index 0) blur 시 선거법 금지 표현 사전 검사
    if (index === 0 && value) {
      const violations = checkElectionExpressions(value, user?.status);
      setElectionViolations(violations);
      // 부모에게 위반 여부 전달 (생성 버튼 비활성화용)
      if (violations.length > 0) {
        onChange({ _electionViolations: violations });
      } else {
        onChange({ _electionViolations: null });
      }
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
    const combinedKeywords = currentKeywords ? `${currentKeywords}, ${keyword}` : keyword;
    const { normalized, exceeded } = normalizeKeywordsInput(combinedKeywords, 2);
    onChange({ keywords: normalized });
    if (exceeded) {
      showKeywordWarning();
    }
  };

  const handleKeywordsChange = (event) => {
    const rawValue = event.target.value;
    onChange({ keywords: rawValue });

    const { exceeded } = normalizeKeywordsInput(rawValue, 2);
    if (exceeded) {
      if (!keywordWarning) {
        showKeywordWarning();
      }
    } else if (keywordWarning) {
      setKeywordWarning(null);
    }
  };

  const handleKeywordsBlur = (event) => {
    const { normalized, exceeded } = normalizeKeywordsInput(event.target.value, 2);
    if ((formData.keywords || '') !== normalized) {
      onChange({ keywords: normalized });
    }
    if (exceeded) {
      showKeywordWarning('검색어는 최대 2개까지만 반영됩니다.');
    }
  };

  const formSize = isMobile ? "small" : "medium";

  return (
    <Paper elevation={0} sx={{ p: isMobile ? 2 : 3, mb: isMobile ? 2 : 3 }}>

      <Grid container spacing={isMobile ? 2 : 3}>
        {/* 카테고리 선택 UI 제거 - AI가 주제를 분석하여 자동 결정 */}

        {/* ✅ 5. 주제 입력칸을 `topic`에 연결하여 버튼 활성화 문제를 해결합니다. */}
        <Grid item xs={12}>
          {(() => {
            const topicError = Boolean(errors?.topic);
            return (
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
                error={topicError}
                inputProps={{ maxLength: 500, name: 'topic' }}
                helperText={topicError ? errors.topic : `${formData.topic?.length || 0}/500자`}
                FormHelperTextProps={{ sx: { color: topicError ? 'error.main' : 'text.secondary' } }}
              />
            );
          })()}
        </Grid>

        {/* ✅ 6. 참고자료 및 배경정보 입력창 - 다중 입력 지원 */}
        <Grid item xs={12}>
          <Box sx={{ mb: 1.25 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              참고자료 입력
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.25 }}>
              둘 중 하나 필수
            </Typography>

            {/* ✅ 역할 구분 안내 text + 합산 글자수 */}
            {(() => {
              const totalLength = instructionsList.reduce((sum, text) => sum + (text?.length || 0), 0);
              const isOverLimit = totalLength > 4000;
              return (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
                  <span style={{ color: isOverLimit ? 'var(--color-error)' : 'inherit', fontWeight: isOverLimit ? 700 : 400 }}>
                    합계: {totalLength.toLocaleString()}자
                    {isOverLimit && ' ⚠️ 4,000자 초과 시 앞부분만 분석됩니다'}
                  </span>
                </Typography>
              );
            })()}
          </Box>

          {instructionsList.map((instruction, index) => (
            <Box key={index} sx={{ mb: index < instructionsList.length - 1 ? 2 : 0 }}>
              <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                <TextField
                  fullWidth
                  size={formSize}
                  label={index === 0 ? '① 내 입장문 / 페이스북 글' : `② 뉴스/데이터 ${index}`}
                  placeholder={index === 0
                    ? "내가 이 주제에 대해 가진 입장, 의견, 페이스북에 올린 글 등을 입력하세요. 이 내용이 원고의 핵심 논조가 됩니다."
                    : "기사 본문을 복사하여 붙여넣으세요. (URL 붙여넣기 X, 크롤링 기능 없음)"
                  }
                  value={instruction}
                  onChange={handleInstructionChange(index)}
                  onBlur={handleInstructionBlur(index)}
                  disabled={disabled}
                  multiline
                  rows={index === 0 ? 4 : 3}
                  error={index === 0 && (Boolean(errors?.instructions0) || electionViolations.length > 0)}
                  inputProps={{ name: index === 0 ? 'instructions_0' : `instructions_${index}` }}
                  // 글자수 제한 해제 (백엔드에서 4000자로 잘림)
                  helperText={index === 0 && errors?.instructions0
                    ? errors.instructions0
                    : (index === 0
                      ? `원고의 논조와 주장을 결정합니다. 핵심 메시지를 입력하세요. | ${(instruction?.length || 0).toLocaleString()}자`
                      : `URL이 아닌 기사 본문 텍스트를 직접 복사-붙여넣기 하세요. | ${(instruction?.length || 0).toLocaleString()}자`)
                  }
                  FormHelperTextProps={{ sx: { color: index === 0 && errors?.instructions0 ? 'error.main' : 'text.secondary' } }}
                />
                {index !== 0 && (
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, mt: 1.25 }}>
                    {instructionsList.length > 2 && (
                      <IconButton
                        size="small"
                        onClick={() => removeInstructionField(index)}
                        disabled={disabled}
                        aria-label="참고자료 입력창 삭제"
                        sx={{
                          ...iconButtonSizeSx,
                          width: { xs: 22, sm: 18 },
                          height: { xs: 22, sm: 18 },
                          minWidth: { xs: 22, sm: 18 },
                          minHeight: { xs: 22, sm: 18 },
                          backgroundColor: 'var(--color-primary)',
                          color: 'var(--color-text-inverse)',
                          border: '1px solid',
                          borderColor: 'var(--color-primary)',
                          '&:hover': {
                            backgroundColor: 'var(--color-primary-hover)',
                            borderColor: 'var(--color-primary-hover)'
                          },
                          '&:disabled': {
                            backgroundColor: 'grey.50',
                            borderColor: 'grey.200',
                            color: 'grey.400'
                          }
                        }}
                      >
                        <Remove sx={{ fontSize: 14 }} />
                      </IconButton>
                    )}
                    {index === instructionsList.length - 1 && instructionsList.length < 10 && (
                      <Tooltip title="뉴스/데이터 입력창 추가">
                        <IconButton
                          size="small"
                          onClick={addInstructionField}
                          disabled={disabled}
                          aria-label="뉴스/데이터 입력창 추가"
                          sx={{
                            ...iconButtonSizeSx,
                            width: { xs: 22, sm: 18 },
                            height: { xs: 22, sm: 18 },
                            minWidth: { xs: 22, sm: 18 },
                            minHeight: { xs: 22, sm: 18 },
                            backgroundColor: 'var(--color-primary)',
                            color: 'var(--color-text-inverse)',
                            border: '1px solid',
                            borderColor: 'var(--color-primary)',
                            '&:hover': {
                              backgroundColor: 'var(--color-primary-hover)',
                              borderColor: 'var(--color-primary-hover)'
                            },
                            '&:disabled': {
                              backgroundColor: 'grey.50',
                              borderColor: 'grey.200',
                              color: 'grey.400'
                            }
                          }}
                        >
                          <Add sx={{ fontSize: 14 }} />
                        </IconButton>
                      </Tooltip>
                    )}
                  </Box>
                )}
              </Box>
              {/* 선거법 금��� 표현 경고 (입장문 전용) */}
              {index === 0 && electionViolations.length > 0 && (
                <Alert severity="error" sx={{ mt: 1 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, mb: 0.5 }}>
                    현재 선거 단계에서 사용할 수 없는 표현이 포함되어 있습니다.
                  </Typography>
                  {electionViolations.map((v, i) => (
                    <Typography key={i} variant="body2" sx={{ ml: 1 }}>
                      &bull; <strong>"{v.matched}"</strong> ({v.label}) &rarr; {v.suggestion}
                    </Typography>
                  ))}
                  <Typography variant="body2" sx={{ mt: 0.5, color: 'text.secondary' }}>
                    위 표현을 수정한 후 원고를 생성할 수 있습��다.
                  </Typography>
                </Alert>
              )}
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
          <Box sx={{ display: 'flex', alignItems: { xs: 'stretch', sm: 'flex-start' }, gap: 1, flexDirection: { xs: 'column', sm: 'row' } }}>
            <TextField
              fullWidth
              size={formSize}
              label="노출 희망 검색어 (선택사항)"
              placeholder="검색어는 최대 2개만 입력하세요"
              value={formData.keywords || ''}
              onChange={handleKeywordsChange}
              onBlur={handleKeywordsBlur}
              disabled={disabled}
              helperText={keywordWarning || "쉼표(,)로 구분하여 입력하세요. (예: 성수역 3번 출구, 울산대 대학로)"}
              error={!!keywordWarning}
              FormHelperTextProps={{ sx: { color: keywordWarning ? 'error.main' : 'text.secondary', fontWeight: keywordWarning ? 600 : 400 } }}
            />
            {/* AI 검색어 추천 버튼 - 관리자가 활성화한 경우에만 표시 */}
            {config.aiKeywordRecommendationEnabled && (
              <Tooltip title="AI 검색어 추천">
                <Button
                  variant="outlined"
                  onClick={() => setKeywordDialogOpen(true)}
                  disabled={disabled}
                  aria-label="AI 검색어 추천"
                  sx={{
                    minWidth: isMobile ? '100%' : '120px',
                    height: isMobile ? '44px' : '56px',
                    mt: { xs: 0, sm: 0.5 },
                    px: isMobile ? 1 : 2
                  }}
                >
                  <Search />
                  <Typography variant="button" sx={{ ml: 1 }}>검색어 추천</Typography>
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
