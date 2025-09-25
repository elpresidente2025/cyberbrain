import React from 'react';
import { Fab } from '@mui/material';
import { LightbulbOutlined } from '@mui/icons-material';

const HelpButton = ({ onClick }) => {
  return (
    <Fab
      aria-label="도움말 열기"
      color="primary"
      size="small"
      onClick={onClick}
      sx={{
        position: 'fixed',
        bottom: 16,
        left: 16,
        zIndex: (theme) => theme.zIndex.appBar + 10,
        bgcolor: '#f8c023',
        color: '#000000',
        '&:hover': {
          bgcolor: '#e0a91f',
          transform: 'scale(1.05)',
          boxShadow:
            '0 8px 24px rgba(248, 192, 35, 0.8), 0 0 20px rgba(248, 192, 35, 0.6)',
        },
        boxShadow: '0 4px 12px rgba(248, 192, 35, 0.4)',
        transition: 'transform 0.3s ease, box-shadow 0.3s ease',
        '@supports (bottom: env(safe-area-inset-bottom))': {
          bottom: 'calc(16px + env(safe-area-inset-bottom))',
        },
        '@media (max-width: 1200px)': {
          bottom: 20,
          left: 20,
        },
      }}
    >
      <LightbulbOutlined />
    </Fab>
  );
};

export default HelpButton;

