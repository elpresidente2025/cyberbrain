import React from 'react';
import { Box, Typography } from '@mui/material';
import { Inbox } from '@mui/icons-material';

/**
 * EmptyState - 빈 상태 표시 컴포넌트
 *
 * @param {ReactNode} icon - 아이콘 컴포넌트 (기본값: Inbox)
 * @param {string} message - 빈 상태 메시지
 * @param {ReactNode} action - 액션 버튼
 * @param {number} iconSize - 아이콘 크기 (기본값: 64)
 * @param {number} py - 상하 패딩 (기본값: 4)
 */
const EmptyState = ({
  icon,
  message = '데이터가 없습니다',
  action,
  iconSize = 64,
  py = 4,
  ...props
}) => {
  const IconComponent = icon || <Inbox sx={{ fontSize: iconSize, color: 'grey.400' }} />;

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        py,
        textAlign: 'center'
      }}
      {...props}
    >
      <Box sx={{ mb: 2 }}>
        {React.isValidElement(IconComponent)
          ? IconComponent
          : React.createElement(IconComponent, { sx: { fontSize: iconSize, color: 'grey.400' } })
        }
      </Box>

      <Typography variant="body1" color="text.secondary" sx={{ mb: action ? 2 : 0 }}>
        {message}
      </Typography>

      {action && (
        <Box sx={{ mt: 1 }}>
          {action}
        </Box>
      )}
    </Box>
  );
};

export default EmptyState;
