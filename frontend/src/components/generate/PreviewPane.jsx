// frontend/src/components/generate/PreviewPane.jsx
import React from 'react';
import {
  Box,
  Typography,
  Paper,
  useTheme
} from '@mui/material';

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

  return (
    <>
      <Paper
        elevation={0}
        sx={{
          p: { xs: 1, sm: 2 },
          backgroundColor: '#f5f5f5',
          // 제목과 글자수를 강제로 검은색으로
          '& .MuiTypography-h6': {
            color: '#000000 !important'
          },
          '& .MuiTypography-body2': {
            color: '#000000 !important'
          },
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
            color: '#000000 !important', // Force black text
          },
          // 🔥 'strong' 태그 스타일 개선 (가이드 역할 강화)
          '.article-content strong': {
            fontWeight: 700,
            color: theme.palette.ui?.header || '#152484', // 남색 계열로 텍스트 색상 강조
            backgroundColor: 'rgba(33, 150, 243, 0.1)', // 아주 연한 하늘색 배경 추가
            padding: '2px 5px',
            borderRadius: '4px',
            boxDecorationBreak: 'clone', // 줄바꿈 시에도 스타일 유지
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
            sx={{ fontWeight: 600, color: '#000000 !important' }}
            style={{ color: '#000000 !important' }}
          >
            {draft.title || '제목 없음'}
          </Typography>
          <Typography
            variant="body2"
            sx={{
              backgroundColor: 'grey.100',
              px: 1.5,
              py: 0.5,
              borderRadius: 1,
              fontWeight: 500,
              color: '#000000 !important'
            }}
            style={{ color: '#000000 !important' }}
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
            backgroundColor: '#f5f5f5',
            minHeight: 200,
            maxHeight: '60vh',
            overflow: 'auto',
            '& p:last-child': {
              mb: 0,
            },
            // Force all text to be black
            '& *': {
              color: '#000000 !important',
            },
          }}
        />

        {/* 메타 정보 */}
        {(draft.category || draft.keywords || draft.generatedAt) && (
          <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
              {draft.category && (
                <Typography variant="caption" color="text.secondary">
                  카테고리: {draft.category}
                </Typography>
              )}
              {draft.keywords && (
                <Typography variant="caption" color="text.secondary">
                  키워드: {draft.keywords}
                </Typography>
              )}
              {draft.generatedAt && (
                <Typography variant="caption" color="text.secondary">
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