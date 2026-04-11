import React from 'react';
import { Box, Typography, Stack } from '@mui/material';
import { motion } from 'framer-motion';

const IOS_EASE = [0.32, 0.72, 0, 1];
const ITEMS = ['직책 선택', '활동 지역 선택', '프로필에서 자기소개 작성'];

const WelcomeStep = () => {
  return (
    <Stack spacing={2.5} alignItems="center">
      {ITEMS.map((item, idx) => (
        <motion.div
          key={item}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.45,
            ease: IOS_EASE,
            delay: 0.2 + idx * 0.08,
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <Box
            sx={{
              width: 26,
              height: 26,
              borderRadius: '50%',
              border: '1px solid',
              borderColor: 'divider',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '0.8125rem',
              fontWeight: 500,
              color: 'text.secondary',
            }}
          >
            {idx + 1}
          </Box>
          <Typography
            sx={{
              fontSize: '1.0625rem',
              color: 'text.primary',
            }}
          >
            {item}
          </Typography>
        </motion.div>
      ))}
    </Stack>
  );
};

export default WelcomeStep;
