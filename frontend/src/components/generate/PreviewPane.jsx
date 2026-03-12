// frontend/src/components/generate/PreviewPane.jsx
import React from 'react';
import {
  Box,
  Typography,
  Paper,
  useTheme
} from '@mui/material';
import { CATEGORIES } from '../../constants/formConstants';

export default function PreviewPane({ draft }) {
  const theme = useTheme();
  if (!draft) {
    return null;
  }

  // HTML 태그를 제거하고 순수 텍스트만 추출하여 글자수 계산
  const getTextContent = (html) => {
    if (!html) return '';
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;
    return tempDiv.textContent || tempDiv.innerText || '';
  };

  // 공백 제외 글자수 계산
  const countWithoutSpace = (str) => {
    if (!str) return 0;
    let count = 0;
    for (let i = 0; i < str.length; i++) {
      if (!/\s/.test(str.charAt(i))) {
        count++;
      }
    }
    return count;
  };

  const textContent = getTextContent(draft.htmlContent);
  const characterCount = countWithoutSpace(textContent);

  // 검색어별 출현 횟수 계산
  const countKeywordOccurrences = (content, keyword) => {
    if (!content || !keyword) return 0;
    const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(escapedKeyword, 'g');
    const matches = content.match(regex);
    return matches ? matches.length : 0;
  };

  const getKeywordTokens = (keyword) => {
    if (!keyword) return [];
    return keyword.split(/\s+/).map(token => token.trim()).filter(Boolean);
  };

  const splitKeywordSentenceUnits = (content) => {
    if (!content) return [];
    const normalized = content.replace(/\s+/g, ' ').trim();
    if (!normalized) return [];
    return normalized
      .split(/(?<=[.!?。])\s+|\n+/)
      .map(unit => unit.trim())
      .filter(Boolean);
  };

  const countKeywordSentenceReflections = (content, keyword) => {
    const tokens = getKeywordTokens(keyword).map(token => token.replace(/\s+/g, ''));
    if (tokens.length < 2) return 0;
    return splitKeywordSentenceUnits(content).reduce((total, unit) => {
      const compactUnit = unit.replace(/\s+/g, '');
      if (compactUnit && tokens.every(token => compactUnit.includes(token))) {
        return total + 1;
      }
      return total;
    }, 0);
  };

  const getKeywordStats = () => {
    if (!draft.keywords) return null;
    const keywords = draft.keywords.split(',').map(k => k.trim()).filter(k => k);
    if (keywords.length === 0) return null;

    return keywords.map(keyword => ({
      keyword,
      exactCount: countKeywordOccurrences(textContent, keyword),
      sentenceCoverageCount: countKeywordSentenceReflections(textContent, keyword),
    }));
  };

  const keywordStats = getKeywordStats();

  // 카테고리를 한글로 변환
  const getCategoryLabel = () => {
    if (!draft.category) return null;

    const category = CATEGORIES.find(cat => cat.value === draft.category);
    if (!category) return draft.category;

    let label = category.label;

    // 세부 카테고리가 있으면 추가
    if (draft.subCategory) {
      const subCategory = category.subCategories?.find(sub => sub.value === draft.subCategory);
      if (subCategory) {
        label += ` / ${subCategory.label}`;
      }
    }

    return label;
  };

  const categoryLabel = getCategoryLabel();

  return (
    <>
      <Paper
        elevation={0}
        sx={{
          p: { xs: 1, sm: 2 },
          backgroundColor: 'background.paper',
          '.article-content h1': {
            fontSize: '1.75rem',
            fontWeight: 700,
            color: 'primary.main',
            marginBottom: '1rem',
            paddingBottom: '0.5rem',
            borderBottom: '2px solid',
            borderColor: 'primary.main'
          },
          '.article-content h2': {
            fontSize: '1.3rem',
            fontWeight: 600,
            marginTop: '2rem',
            marginBottom: '1rem',
          },
          '.article-content p': {
            fontSize: '1rem',
            lineHeight: 1.8,
            marginBottom: '1rem',
            color: 'text.primary',
          },
          '.article-content strong': {
            fontWeight: 700,
            color: theme.palette.mode === 'dark'
              ? theme.palette.primary.light
              : (theme.palette.ui?.header || theme.palette.primary.dark),
            backgroundColor: theme.palette.mode === 'dark'
              ? 'rgba(144, 202, 249, 0.2)'
              : 'rgba(33, 150, 243, 0.1)',
            padding: '2px 5px',
            borderRadius: '2px',
            boxDecorationBreak: 'clone',
            WebkitBoxDecorationBreak: 'clone',
          }
        }}
      >
        <Box sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          mb: 2
        }}>
          <Typography
            variant="h6"
            sx={{ fontWeight: 600, color: 'text.primary' }}
          >
            {draft.title || '제목 없음'}
          </Typography>
          <Typography
            variant="body2"
            sx={{
              backgroundColor: 'action.hover',
              px: 1.5,
              py: 0.5,
              borderRadius: 1,
              fontWeight: 500,
              color: 'text.secondary'
            }}
          >
            {characterCount.toLocaleString()}자
          </Typography>
        </Box>

        <Box
          className="article-content"
          dangerouslySetInnerHTML={{ __html: draft.htmlContent || '내용이 없습니다.' }}
          sx={{
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1,
            p: 2,
            backgroundColor: 'background.default',
            minHeight: 200,
            maxHeight: '60vh',
            overflow: 'auto',
            '& p:last-child': {
              mb: 0,
            },
            '& *': {
              color: 'text.primary',
            },
          }}
        />

        {/* 메타 정보 */}
        {(categoryLabel || draft.keywords || draft.generatedAt) && (
          <Box sx={{
            mt: 2,
            pt: 2,
            borderTop: '1px solid',
            borderColor: 'divider',
            backgroundColor: theme.palette.mode === 'dark' ? 'rgba(255,255,255,0.05)' : 'rgba(21, 36, 132, 0.08)',
            p: 2,
            borderRadius: 1
          }}>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
              {categoryLabel && (
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  카테고리: {categoryLabel}
                </Typography>
              )}
              {keywordStats && keywordStats.length > 0 && (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                  <Typography variant="caption" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                    검색어 반영 횟수:
                  </Typography>
                  {keywordStats.map((stat, index) => {
                    // 🔑 백엔드 검증 결과 우선 사용
                    const backendValidation = draft.keywordValidation?.[stat.keyword];
                    const backendExactCount = Number(
                      backendValidation?.exclusiveCount ?? backendValidation?.exactCount
                    );
                    const backendSentenceCoverageCount = Number(backendValidation?.sentenceCoverageCount);
                    const backendGateCount = Number(backendValidation?.gateCount ?? backendValidation?.count);
                    const fallbackExactCount = Number(stat.exactCount);
                    const fallbackSentenceCoverageCount = Number(stat.sentenceCoverageCount);
                    const fallbackGateCount = Math.max(
                      Number.isFinite(fallbackExactCount) ? fallbackExactCount : 0,
                      Number.isFinite(fallbackSentenceCoverageCount) ? fallbackSentenceCoverageCount : 0
                    );
                    const displayCount = Number.isFinite(backendGateCount)
                      ? backendGateCount
                      : fallbackGateCount;
                    const exactCount = Number.isFinite(backendExactCount)
                      ? backendExactCount
                      : fallbackExactCount;
                    const sentenceCoverageCount = Number.isFinite(backendSentenceCoverageCount)
                      ? backendSentenceCoverageCount
                      : fallbackSentenceCoverageCount;
                    const fallbackMinCount = keywordStats.length >= 2 ? 3 : 5;
                    const fallbackMaxCount = fallbackMinCount + 1;

                    const parsedMin = Number(backendValidation?.expected);
                    const parsedMax = Number(backendValidation?.max);
                    const minCount = Number.isFinite(parsedMin) && parsedMin > 0
                      ? parsedMin
                      : fallbackMinCount;
                    const maxCount = Number.isFinite(parsedMax) && parsedMax >= minCount
                      ? parsedMax
                      : fallbackMaxCount;

                    let validationStatus = backendValidation?.status;
                    if (!['valid', 'insufficient', 'spam_risk'].includes(validationStatus)) {
                      if (displayCount < minCount) {
                        validationStatus = 'insufficient';
                      } else if (displayCount > maxCount) {
                        validationStatus = 'spam_risk';
                      } else {
                        validationStatus = 'valid';
                      }
                    }

                    const isValid = validationStatus === 'valid';
                    const statusLabel = validationStatus === 'insufficient'
                      ? ' (\uBD80\uC871)'
                      : (validationStatus === 'spam_risk' ? ' (\uACFC\uB2E4)' : '');
                    const hasMultipleTokens = getKeywordTokens(stat.keyword).length >= 2;
                    const detailLabel = hasMultipleTokens
                      ? ` (정확 ${Number.isFinite(exactCount) ? exactCount : 0}회 / 문장 반영 ${Number.isFinite(sentenceCoverageCount) ? sentenceCoverageCount : 0}회)`
                      : '';

                    return (
                      <Typography
                        key={index}
                        variant="caption"
                        sx={{
                          color: isValid ? 'success.main' : 'error.main',
                          fontWeight: 500,
                          pl: 1
                        }}
                      >
                        "{stat.keyword}": {displayCount}회{statusLabel}{detailLabel}
                      </Typography>
                    );
                  })}
                </Box>
              )}
              {draft.generatedAt && (
                <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                  생성 시간: {new Date(draft.generatedAt).toLocaleString()}
                </Typography>
              )}
            </Box>
          </Box>
        )}
      </Paper>
    </>
  );
}
