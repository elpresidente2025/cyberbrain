import React from 'react';
import { Box, Typography, ButtonBase } from '@mui/material';
import { Check } from '@mui/icons-material';
import { motion, AnimatePresence } from 'framer-motion';

const APPLE_BLUE = '#007AFF';
const IOS_EASE = [0.32, 0.72, 0, 1];

const STATUS_OPTIONS = [
  {
    value: '현역',
    label: '현역',
    description: '현재 해당 자리에 재임 중입니다',
  },
  {
    value: '후보',
    label: '후보',
    description: '공식 후보로 등록되어 선거를 치르고 있습니다',
  },
  {
    value: '예비',
    label: '예비후보',
    description: '예비후보로 등록하여 활동 중입니다',
  },
  {
    value: '준비',
    label: '준비 중',
    description: '다음 선거 출마를 준비하고 있습니다',
  },
];

const StatusStep = ({ value, onChange }) => {
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
      {STATUS_OPTIONS.map((opt, idx) => {
        const selected = value === opt.value;
        return (
          <React.Fragment key={opt.value}>
            {idx > 0 && <Box sx={{ height: '1px', bgcolor: 'divider', ml: 2.5 }} />}
            <motion.div
              whileTap={{ backgroundColor: 'rgba(0, 0, 0, 0.04)' }}
              transition={{ duration: 0.12, ease: IOS_EASE }}
            >
              <ButtonBase
                onClick={() => onChange(opt.value)}
                sx={{
                  width: '100%',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  px: 2.5,
                  py: 2,
                  textAlign: 'left',
                  transition: 'background-color 160ms ease',
                  '&:hover': { bgcolor: 'action.hover' },
                }}
              >
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontSize: '1.0625rem', color: 'text.primary' }}>
                    {opt.label}
                  </Typography>
                  <Typography sx={{ fontSize: '0.8125rem', color: 'text.secondary', mt: 0.25 }}>
                    {opt.description}
                  </Typography>
                </Box>
                <Box sx={{ width: 22, height: 22, ml: 2, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <AnimatePresence>
                    {selected && (
                      <motion.div
                        key="check"
                        initial={{ scale: 0.4, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        exit={{ scale: 0.4, opacity: 0 }}
                        transition={{ duration: 0.25, ease: IOS_EASE }}
                        style={{ display: 'flex' }}
                      >
                        <Check sx={{ fontSize: 22, color: APPLE_BLUE }} />
                      </motion.div>
                    )}
                  </AnimatePresence>
                </Box>
              </ButtonBase>
            </motion.div>
          </React.Fragment>
        );
      })}
    </Box>
  );
};

export default StatusStep;
