import React from 'react';
import { Box, Typography, useTheme } from '@mui/material';
import { spacing, typography, visualWeight, verticalRhythm } from '../../../theme/tokens';

/**
 * PageHeader - 페이지 헤더 컴포넌트
 * - 게슈탈트 리듬 적용: 일관된 spacing, typography, visual weight
 *
 * @param {string} title - 페이지 제목
 * @param {string} subtitle - 페이지 부제목
 * @param {ReactNode} icon - 제목 옆 아이콘
 * @param {ReactNode} actions - 오른쪽 액션 버튼들
 * @param {number} mb - 하단 마진 (기본값: spacing.lg)
 */
const PageHeader = ({
  title,
  subtitle,
  icon,
  actions,
  mb = spacing.lg,
  ...props
}) => {
  const theme = useTheme();

  return (
    <Box
      sx={{
        mb: `${mb}px`,
        pb: `${verticalRhythm.common.sm}px`, // 16px baseline
      }}
      {...props}
    >
      <Box sx={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        mb: subtitle ? `${spacing.xs}px` : 0 // 8px if subtitle exists
      }}>
        <Typography
          variant="h4"
          sx={{
            fontSize: visualWeight.primary.fontSize,
            fontWeight: visualWeight.primary.fontWeight,
            lineHeight: visualWeight.primary.lineHeight,
            letterSpacing: visualWeight.primary.letterSpacing,
            color: theme.palette.mode === 'dark' ? 'white' : 'black',
            display: 'flex',
            alignItems: 'center',
            gap: `${spacing.xs}px` // 8px gap
          }}
        >
          {icon && (
            <Box
              component="span"
              sx={{
                display: 'flex',
                color: theme.palette.mode === 'dark' ? 'white' : 'black'
              }}
            >
              {icon}
            </Box>
          )}
          {title}
        </Typography>

        {actions && (
          <Box sx={{ display: 'flex', gap: `${spacing.xs}px` }}>
            {actions}
          </Box>
        )}
      </Box>

      {subtitle && (
        <Typography
          variant="body1"
          color="text.secondary"
          sx={{
            fontSize: visualWeight.body.fontSize,
            fontWeight: visualWeight.body.fontWeight,
            lineHeight: visualWeight.body.lineHeight,
            mt: `${spacing.xs}px` // 8px margin-top
          }}
        >
          {subtitle}
        </Typography>
      )}
    </Box>
  );
};

export default PageHeader;
