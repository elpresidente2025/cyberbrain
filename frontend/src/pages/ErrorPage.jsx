import React from 'react';
import { useRouteError, Link as RouterLink } from 'react-router-dom';
import { Box, Button, Container, Typography, Paper } from '@mui/material';

// 프로덕션 환경에서는 Sentry 등으로 대체 예정
const logError = (error) => {
  if (process.env.NODE_ENV === 'development') {
    console.error('ErrorPage caught an error:', error);
  }
  // TODO: 프로덕션에서는 Sentry.captureException(error) 등으로 대체
};

// 상태코드별 맞춤 메시지
const getErrorMessage = (status) => {
  switch (status) {
    case 404:
      return '페이지를 찾을 수 없습니다.';
    case 500:
      return '서버 오류가 발생했습니다.';
    case 403:
      return '접근 권한이 없습니다.';
    default:
      return '페이지를 찾을 수 없거나 오류가 발생했습니다.';
  }
};

export default function ErrorPage() {
  const error = useRouteError();
  logError(error);

  let status = 'ERROR';
  let statusText = '예상치 못한 오류가 발생했습니다.';
  let displayMessage = '페이지를 찾을 수 없거나 오류가 발생했습니다.';

  if (error && typeof error === 'object' && error !== null) {
    const errorStatus = error.status || 500;
    status = errorStatus;
    statusText = error.statusText || error.message || statusText;
    displayMessage = getErrorMessage(errorStatus);
  } else if (typeof error === 'string') {
    statusText = error;
  }

  return (
    <Container component="main" maxWidth="sm" sx={{ display: 'flex', alignItems: 'center', minHeight: '100vh' }}>
      <Paper
        elevation={1}
        sx={{
          p: 4,
          width: '100%',
          textAlign: 'center',
          borderRadius: 2,
          backgroundColor: 'rgba(255,255,255,0.04)',
          backdropFilter: 'blur(6px)',
          border: '1px solid rgba(255,255,255,0.08)'
        }}
      >
        <Typography variant="h1" component="h1" sx={{ color: '#00d4ff', mb: 2 }}>
          {status}
        </Typography>
        <Typography variant="h5" component="h2" sx={{ color: 'rgba(255,255,255,0.9)', mb: 3 }}>
          {displayMessage}
        </Typography>
        <Typography sx={{ color: 'rgba(255,255,255,0.7)', mb: 4 }}>
          {statusText}
        </Typography>
        <Box sx={{ mt: 4 }}>
          <Button
            component={RouterLink}
            to="/"
            variant="contained"
            size="large"
            aria-label="홈 페이지로 돌아가기"
            sx={{
              backgroundColor: '#00d4ff',
              color: '#041120',
              '&:hover': {
                backgroundColor: '#00bde6'
              }
            }}
          >
            홈으로 돌아가기
          </Button>
        </Box>
      </Paper>
    </Container>
  );
}

