import React from 'react';
import { Paper, Typography, Box } from '@mui/material';

/**
 * ContentCard - 콘텐츠 카드 컴포넌트
 *
 * @param {string} title - 카드 제목
 * @param {ReactNode} titleIcon - 제목 옆 아이콘
 * @param {ReactNode} children - 카드 내용
 * @param {number} padding - 패딩 (2 또는 3)
 * @param {boolean} transparent - 투명 배경 사용 여부
 * @param {ReactNode} headerAction - 헤더 오른쪽 액션
 * @param {number} elevation - Paper elevation (기본값: 0)
 */
const ContentCard = ({
  title,
  titleIcon,
  children,
  padding = 3,
  transparent = false,
  headerAction,
  elevation = 0,
  ...props
}) => {
  return (
    <Paper
      elevation={elevation}
      sx={{
        p: padding,
        bgcolor: transparent ? 'transparent' : 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: 2,
        ...props.sx
      }}
      {...props}
    >
      {title && (
        <Box sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          mb: 2
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {titleIcon}
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              {title}
            </Typography>
          </Box>
          {headerAction && (
            <Box>
              {headerAction}
            </Box>
          )}
        </Box>
      )}

      {children}
    </Paper>
  );
};

export default ContentCard;
