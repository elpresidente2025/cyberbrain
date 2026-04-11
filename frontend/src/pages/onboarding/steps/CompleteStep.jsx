import React from 'react';
import { Box, Typography } from '@mui/material';
import { motion } from 'framer-motion';

const IOS_EASE = [0.32, 0.72, 0, 1];

const STATUS_LABEL = {
  현역: '현역',
  후보: '후보',
  예비: '예비후보',
  준비: '준비 중',
};

const CompleteStep = ({ data }) => {
  const items = [
    { label: '상태', value: STATUS_LABEL[data.status] || data.status },
    { label: '직책', value: data.position },
    { label: '광역', value: data.regionMetro },
    { label: '기초', value: data.regionLocal },
    { label: '선거구', value: data.electoralDistrict },
  ].filter((item) => item.value);

  if (items.length === 0) return null;

  return (
    <Box
      sx={{
        borderRadius: 3,
        overflow: 'hidden',
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: 'divider',
      }}
    >
      {items.map((item, idx) => (
        <React.Fragment key={item.label}>
          {idx > 0 && <Box sx={{ height: '1px', bgcolor: 'divider', ml: 2.5 }} />}
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.4,
              ease: IOS_EASE,
              delay: 0.25 + idx * 0.07,
            }}
          >
            <Box
              sx={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                px: 2.5,
                minHeight: 56,
                gap: 2,
              }}
            >
              <Typography sx={{ fontSize: '1.0625rem', color: 'text.primary' }}>
                {item.label}
              </Typography>
              <Typography sx={{ fontSize: '1.0625rem', color: 'text.secondary' }}>
                {item.value}
              </Typography>
            </Box>
          </motion.div>
        </React.Fragment>
      ))}
    </Box>
  );
};

export default CompleteStep;
