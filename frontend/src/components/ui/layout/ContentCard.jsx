import React from 'react';
import { Paper, Typography, Box } from '@mui/material';
import { spacing, borders, visualWeight, verticalRhythm, transitions, shadows } from '../../../theme/tokens';

/**
 * ContentCard - 콘텐츠 카드 컴포넌트
 * - 게슈탈트 리듬 적용: 일관된 spacing, typography, borders
 *
 * @param {string} title - 카드 제목
 * @param {ReactNode} titleIcon - 제목 옆 아이콘
 * @param {ReactNode} children - 카드 내용
 * @param {number} padding - 패딩 (기본: spacing.lg)
 * @param {boolean} transparent - 투명 배경 사용 여부
 * @param {ReactNode} headerAction - 헤더 오른쪽 액션
 * @param {number} elevation - Paper elevation (기본값: 0)
 */
const ContentCard = ({
  title,
  titleIcon,
  children,
  padding = spacing.lg,
  transparent = false,
  headerAction,
  elevation = 0,
  ...props
}) => {
  return (
    <Paper
      elevation={elevation}
      sx={{
        p: `${padding}px`,
        bgcolor: transparent ? 'transparent' : 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.1)',
        borderRadius: `${borders.radius.md}px`,
        transition: `all ${transitions.normal} ${transitions.easing.easeInOut}`,
        '&:hover': {
          boxShadow: shadows.cardHover,
          borderColor: 'rgba(255,255,255,0.15)'
        },
        ...props.sx
      }}
      {...props}
    >
      {title && (
        <Box sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          mb: `${verticalRhythm.common.sm}px`, // 16px baseline
          pb: `${spacing.xs}px` // 8px padding-bottom
        }}>
          <Box sx={{
            display: 'flex',
            alignItems: 'center',
            gap: `${spacing.xs}px` // 8px gap
          }}>
            {titleIcon}
            <Typography
              variant="h6"
              sx={{
                fontSize: visualWeight.tertiary.fontSize,
                fontWeight: visualWeight.tertiary.fontWeight,
                lineHeight: visualWeight.tertiary.lineHeight
              }}
            >
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
