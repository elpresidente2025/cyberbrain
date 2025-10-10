import React from 'react';
import { Box, Typography, useTheme } from '@mui/material';

/**
 * PageHeader - 페이지 헤더 컴포넌트
 *
 * @param {string} title - 페이지 제목
 * @param {string} subtitle - 페이지 부제목
 * @param {ReactNode} icon - 제목 옆 아이콘
 * @param {ReactNode} actions - 오른쪽 액션 버튼들
 * @param {number} mb - 하단 마진 (기본값: 4)
 */
const PageHeader = ({
  title,
  subtitle,
  icon,
  actions,
  mb = 4,
  ...props
}) => {
  const theme = useTheme();

  return (
    <Box sx={{ mb }} {...props}>
      <Box sx={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        mb: subtitle ? 1 : 0
      }}>
        <Typography
          variant="h4"
          sx={{
            fontWeight: 'bold',
            color: theme.palette.mode === 'dark' ? 'white' : 'black',
            display: 'flex',
            alignItems: 'center',
            gap: 1
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
          <Box sx={{ display: 'flex', gap: 1 }}>
            {actions}
          </Box>
        )}
      </Box>

      {subtitle && (
        <Typography variant="body1" color="text.secondary">
          {subtitle}
        </Typography>
      )}
    </Box>
  );
};

export default PageHeader;
