import React from 'react';
import { useRouteError, Link as RouterLink } from 'react-router-dom';
import { Box, Button, Container, Typography, useTheme } from '@mui/material';
import { motion } from 'framer-motion';
import { Home, ErrorOutline, Block, Lock } from '@mui/icons-material';

const logError = (error) => {
  if (process.env.NODE_ENV === 'development') {
    console.error('ErrorPage caught an error:', error);
  }
};

const getErrorConfig = (status) => {
  switch (status) {
    case 404:
      return { message: '페이지를 찾을 수 없습니다.', icon: ErrorOutline, hint: '주소가 정확한지 확인해 주세요.' };
    case 500:
      return { message: '서버 오류가 발생했습니다.', icon: Block, hint: '잠시 후 다시 시도해 주세요.' };
    case 403:
      return { message: '접근 권한이 없습니다.', icon: Lock, hint: '로그인 상태를 확인해 주세요.' };
    default:
      return { message: '예상치 못한 오류가 발생했습니다.', icon: ErrorOutline, hint: '잠시 후 다시 시도해 주세요.' };
  }
};

const springTransition = 'all 0.35s cubic-bezier(0.16, 1, 0.3, 1)';

export default function ErrorPage() {
  const error = useRouteError();
  const theme = useTheme();
  logError(error);

  let status = 'ERROR';
  let statusText = '예상치 못한 오류가 발생했습니다.';
  let errorStatus = 0;

  if (error && typeof error === 'object' && error !== null) {
    errorStatus = error.status || 500;
    status = errorStatus;
    statusText = error.statusText || error.message || statusText;
  } else if (typeof error === 'string') {
    statusText = error;
  }

  const config = getErrorConfig(errorStatus);
  const IconComponent = config.icon;
  const isDark = theme.palette.mode === 'dark';

  return (
    <Box sx={{
      minHeight: '100dvh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      bgcolor: 'var(--color-background)',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {/* 배경 장식 - 은은한 radial gradient */}
      <Box sx={{
        position: 'absolute',
        top: '20%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: '60vw',
        height: '60vw',
        maxWidth: 600,
        maxHeight: 600,
        borderRadius: '50%',
        background: isDark
          ? 'radial-gradient(circle, rgba(21,36,132,0.12) 0%, transparent 70%)'
          : 'radial-gradient(circle, rgba(21,36,132,0.06) 0%, transparent 70%)',
        pointerEvents: 'none',
      }} />

      <Container component="main" maxWidth="sm">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        >
          <Box sx={{
            textAlign: 'center',
            p: { xs: 4, sm: 6 },
            borderRadius: 'var(--radius-xl)',
            bgcolor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            boxShadow: 'var(--shadow-lg)',
            position: 'relative',
            zIndex: 1,
          }}>
            {/* 아이콘 */}
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
            >
              <Box sx={{
                width: 80,
                height: 80,
                mx: 'auto',
                mb: 3,
                borderRadius: 'var(--radius-lg)',
                bgcolor: 'var(--color-primary-lighter)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                <IconComponent sx={{ fontSize: 40, color: 'var(--color-primary)' }} />
              </Box>
            </motion.div>

            {/* 상태 코드 */}
            <Typography
              variant="h1"
              component="h1"
              sx={{
                color: 'var(--color-primary)',
                fontWeight: 800,
                fontSize: { xs: '3.5rem', sm: '4.5rem' },
                lineHeight: 1,
                letterSpacing: '-0.03em',
                mb: 2,
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {status}
            </Typography>

            {/* 메시지 */}
            <Typography
              variant="h5"
              component="h2"
              sx={{
                color: 'var(--color-text-primary)',
                fontWeight: 700,
                mb: 1.5,
                fontSize: { xs: '1.25rem', sm: '1.5rem' },
                wordBreak: 'keep-all',
              }}
            >
              {config.message}
            </Typography>

            <Typography sx={{
              color: 'var(--color-text-secondary)',
              mb: 1,
              fontSize: '0.95rem',
              lineHeight: 1.6,
            }}>
              {config.hint}
            </Typography>

            {statusText !== config.message && (
              <Typography sx={{
                color: 'var(--color-text-tertiary)',
                fontSize: '0.85rem',
                mb: 4,
                wordBreak: 'break-word',
              }}>
                {statusText}
              </Typography>
            )}

            {!statusText || statusText === config.message ? <Box sx={{ mb: 4 }} /> : null}

            {/* CTA */}
            <Button
              component={RouterLink}
              to="/"
              variant="contained"
              size="large"
              startIcon={<Home />}
              aria-label="홈 페이지로 돌아가기"
              sx={{
                bgcolor: 'var(--color-primary)',
                color: 'var(--color-text-inverse)',
                fontWeight: 700,
                fontSize: '1.05rem',
                px: 5,
                py: 1.75,
                borderRadius: 'var(--radius-md)',
                boxShadow: 'var(--shadow-md)',
                textTransform: 'none',
                transition: springTransition,
                '&:hover': {
                  bgcolor: 'var(--color-primary-hover)',
                  boxShadow: 'var(--shadow-glow-primary)',
                  transform: 'scale(1.02)',
                },
                '&:active': { transform: 'scale(0.98)' },
                '&:focus-visible': {
                  outline: '2px solid var(--color-primary)',
                  outlineOffset: '2px',
                },
              }}
            >
              홈으로 돌아가기
            </Button>
          </Box>
        </motion.div>
      </Container>
    </Box>
  );
}

