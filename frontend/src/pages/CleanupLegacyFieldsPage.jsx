import React, { useState } from 'react';
import { Container, Paper, Typography, Button, Alert, Box, LinearProgress } from '@mui/material';
import { functions } from '../services/firebase';
import { httpsCallable } from 'firebase/functions';
import DashboardLayout from '../components/DashboardLayout';
import { useAuth } from '../hooks/useAuth';

const CleanupLegacyFieldsPage = () => {
  const { user } = useAuth();
  const [loading, setLoading] = useState({ district: false, profileImage: false, isAdmin: false });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const executeCleanup = async (type) => {
    if (!user || user.role !== 'admin') {
      setError('관리자 권한이 필요합니다.');
      return;
    }

    const confirmMessages = {
      district: '정말로 모든 사용자에서 레거시 district 필드를 제거하시겠습니까?',
      profileImage: '정말로 모든 사용자에서 레거시 profileImage 필드를 제거하시겠습니까?',
      isAdmin: '정말로 모든 사용자에서 레거시 isAdmin 필드를 제거하시겠습니까?'
    };

    if (!confirm(confirmMessages[type] + '\n\n이 작업은 되돌릴 수 없습니다!')) {
      return;
    }

    const functionNames = {
      district: 'removeLegacyDistrictField',
      profileImage: 'removeLegacyProfileImage',
      isAdmin: 'removeLegacyIsAdmin'
    };

    setLoading({ ...loading, [type]: true });
    setError(null);
    setResult(null);

    try {
      const cleanupFunction = httpsCallable(functions, functionNames[type]);
      const response = await cleanupFunction({});

      if (response.data.success) {
        setResult(response.data);
      } else {
        setError(response.data.message || '작업 실패');
      }
    } catch (err) {
      console.error('Cleanup error:', err);
      setError(err.message);
    } finally {
      setLoading({ ...loading, [type]: false });
    }
  };

  if (!user) {
    return (
      <DashboardLayout title="레거시 필드 정리">
        <Container maxWidth="lg">
          <Alert severity="warning">로그인이 필요합니다.</Alert>
        </Container>
      </DashboardLayout>
    );
  }

  if (user.role !== 'admin') {
    return (
      <DashboardLayout title="레거시 필드 정리">
        <Container maxWidth="lg">
          <Alert severity="error">관리자 권한이 필요합니다.</Alert>
        </Container>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="레거시 필드 정리">
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h5" gutterBottom sx={{ color: 'error.main' }}>
            ⚠️ 레거시 필드 정리 (관리자 전용)
          </Typography>

          <Alert severity="warning" sx={{ my: 2 }}>
            <Typography variant="h6" gutterBottom>⚠️ 경고</Typography>
            <Typography variant="body2">
              이 페이지는 <strong>관리자 전용</strong>입니다.<br />
              레거시 필드를 모든 사용자에서 제거합니다.<br />
              이 작업은 되돌릴 수 없습니다!
            </Typography>
          </Alert>

          <Alert severity="info" sx={{ my: 2 }}>
            <Typography variant="h6" gutterBottom>ℹ️ 작업 내용</Typography>
            <Typography variant="subtitle2" gutterBottom><strong>1. district 필드 제거</strong></Typography>
            <ul>
              <li>모든 사용자 문서에서 <code>district</code> 필드를 제거합니다</li>
              <li><code>regionMetro</code>, <code>regionLocal</code>, <code>electoralDistrict</code> 필드는 유지됩니다</li>
            </ul>
            <Typography variant="subtitle2" gutterBottom><strong>2. profileImage 필드 제거</strong></Typography>
            <ul>
              <li>모든 사용자 문서에서 <code>profileImage</code> 필드를 제거합니다</li>
              <li>Firebase Auth의 <code>photoURL</code>을 사용하므로 중복 저장 불필요</li>
            </ul>
            <Typography variant="subtitle2" gutterBottom><strong>3. isAdmin 필드 제거</strong></Typography>
            <ul>
              <li>모든 사용자 문서에서 <code>isAdmin</code> 필드를 제거합니다</li>
              <li><code>role</code> 필드로 통일하므로 중복 제거</li>
            </ul>
            <Typography variant="body2" sx={{ mt: 1, fontStyle: 'italic' }}>
              제거된 필드 정보는 로그에 기록됩니다. 최대 실행 시간: 9분 (타임아웃)
            </Typography>
          </Alert>

          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', my: 3 }}>
            <Button
              variant="contained"
              color="error"
              onClick={() => executeCleanup('district')}
              disabled={loading.district}
            >
              {loading.district ? '제거 중...' : '레거시 district 필드 제거 실행'}
            </Button>
            <Button
              variant="contained"
              color="error"
              onClick={() => executeCleanup('profileImage')}
              disabled={loading.profileImage}
            >
              {loading.profileImage ? '제거 중...' : '레거시 profileImage 필드 제거 실행'}
            </Button>
            <Button
              variant="contained"
              color="error"
              onClick={() => executeCleanup('isAdmin')}
              disabled={loading.isAdmin}
            >
              {loading.isAdmin ? '제거 중...' : '레거시 isAdmin 필드 제거 실행'}
            </Button>
          </Box>

          {(loading.district || loading.profileImage || loading.isAdmin) && (
            <Box sx={{ mt: 2 }}>
              <LinearProgress />
              <Typography variant="body2" sx={{ mt: 1 }}>
                레거시 필드 제거 중... (최대 9분 소요)
              </Typography>
            </Box>
          )}

          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              <Typography variant="h6">오류 발생</Typography>
              <Typography variant="body2">{error}</Typography>
            </Alert>
          )}

          {result && (
            <Alert severity="success" sx={{ mt: 2 }}>
              <Typography variant="h6">✅ {result.message}</Typography>
              <Box component="pre" sx={{ mt: 1, p: 2, bgcolor: 'grey.100', borderRadius: 1, overflow: 'auto' }}>
                {JSON.stringify(result.stats, null, 2)}
              </Box>
              {result.details && result.details.length > 0 && (
                <Box sx={{ mt: 2, maxHeight: 400, overflow: 'auto' }}>
                  <Typography variant="subtitle2" gutterBottom><strong>상세 내역:</strong></Typography>
                  {result.details.map((detail, index) => (
                    <Box key={index} sx={{ p: 1, mb: 1, bgcolor: 'white', borderLeft: 3, borderColor: 'info.main', borderRadius: 1 }}>
                      <Typography variant="body2">
                        <strong>{index + 1}. {detail.userId}</strong>
                      </Typography>
                      {detail.oldDistrict && (
                        <Typography variant="body2">이전 district: "{detail.oldDistrict}"</Typography>
                      )}
                      {detail.oldProfileImage !== undefined && (
                        <Typography variant="body2">이전 profileImage: "{detail.oldProfileImage || 'null'}"</Typography>
                      )}
                      {detail.oldIsAdmin !== undefined && (
                        <>
                          <Typography variant="body2">이전 isAdmin: "{detail.oldIsAdmin}"</Typography>
                          <Typography variant="body2">role: {detail.role || 'null'}</Typography>
                        </>
                      )}
                      {detail.regionMetro && (
                        <>
                          <Typography variant="body2">regionMetro: {detail.regionMetro}</Typography>
                          <Typography variant="body2">regionLocal: {detail.regionLocal || '없음'}</Typography>
                          <Typography variant="body2">electoralDistrict: {detail.electoralDistrict || '없음'}</Typography>
                        </>
                      )}
                    </Box>
                  ))}
                </Box>
              )}
            </Alert>
          )}
        </Paper>
      </Container>
    </DashboardLayout>
  );
};

export default CleanupLegacyFieldsPage;
