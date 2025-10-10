import React from 'react';
import { Box, IconButton, Tooltip } from '@mui/material';

/**
 * ActionButtonGroup - 아이콘 버튼 그룹 컴포넌트
 *
 * @param {Array} actions - 액션 배열 [{ icon, onClick, tooltip, color, disabled, size }]
 * @param {string} size - 버튼 크기 (small, medium, large)
 * @param {number} gap - 버튼 간 간격
 * @param {string} direction - 버튼 방향 (row, column)
 */
const ActionButtonGroup = ({
  actions = [],
  size = 'small',
  gap = 1,
  direction = 'row',
  ...props
}) => {
  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: direction,
        gap
      }}
      {...props}
    >
      {actions.map((action, index) => {
        const button = (
          <IconButton
            key={index}
            size={action.size || size}
            onClick={action.onClick}
            color={action.color || 'default'}
            disabled={action.disabled}
            sx={action.sx}
          >
            {action.icon}
          </IconButton>
        );

        // Tooltip이 있으면 감싸기
        if (action.tooltip) {
          return (
            <Tooltip key={index} title={action.tooltip} arrow>
              {button}
            </Tooltip>
          );
        }

        return button;
      })}
    </Box>
  );
};

export default ActionButtonGroup;
