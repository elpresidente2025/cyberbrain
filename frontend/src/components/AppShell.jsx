import React from 'react';
import { Outlet } from 'react-router-dom';
import { Box } from '@mui/material';
import { motion, AnimatePresence } from 'framer-motion';
import { HelpProvider } from '../contexts/HelpContext';
import { ColorProvider } from '../contexts/ColorContext';

export default function AppShell({ pathname }) {
  return (
    <HelpProvider>
      <ColorProvider>
        <Box sx={{ position: 'relative', minHeight: '100vh' }}>
          <AnimatePresence mode="wait">
            <motion.div
              key={pathname}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{
                duration: 0.3,
                ease: [0.4, 0, 0.2, 1],
              }}
              style={{ minHeight: '100vh' }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </Box>
      </ColorProvider>
    </HelpProvider>
  );
}
