import React, { useState } from 'react';
import { Container, Button, Typography, Alert, Box, Paper } from '@mui/material';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../services/firebase';

export default function RestoreAdminPage() {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleRestore = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const restoreAdmin = httpsCallable(functions, 'emergencyRestoreAdmin');
      const response = await restoreAdmin({});

      setResult(response.data);

      setTimeout(() => {
        window.location.href = '/';
      }, 3000);

    } catch (err) {
      console.error('복구 실패:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="sm" sx={{ mt: 10 }}>
      <Paper elevation={3} sx={{ p: 4, textAlign: 'center' }}>
        <Typography variant="h4" gutterBottom>
          🔧 관리자 권한 긴급 복구
        </Typography>

        <Typography variant="body1" sx={{ mb: 4 }}>
          아래 버튼을 클릭하여 관리자 권한을 복구하세요.
        </Typography>

        <Button
          variant="contained"
          size="large"
          onClick={handleRestore}
          disabled={loading}
          sx={{
            bgcolor: '#152484',
            '&:hover': {
              bgcolor: '#1e30a0'
            }
          }}
        >
          {loading ? '처리 중...' : '관리자 권한 복구'}
        </Button>

        {result && (
          <Alert severity="success" sx={{ mt: 3 }}>
            <Typography variant="h6">✅ 복구 완료!</Typography>
            <Typography variant="body2">
              {JSON.stringify(result, null, 2)}
            </Typography>
            <Typography variant="body2" sx={{ mt: 1 }}>
              3초 후 메인 페이지로 이동합니다...
            </Typography>
          </Alert>
        )}

        {error && (
          <Alert severity="error" sx={{ mt: 3 }}>
            <Typography variant="h6">❌ 복구 실패</Typography>
            <Typography variant="body2">{error}</Typography>
          </Alert>
        )}
      </Paper>
    </Container>
  );
}
