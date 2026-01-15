// frontend/src/components/admin/SystemSettings.jsx
import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Paper,
  Typography,
  Box,
  Switch,
  FormControlLabel,
  CircularProgress,
  Alert,
  Divider,
  Snackbar
} from '@mui/material';
import { Settings, Psychology } from '@mui/icons-material';
import { callFunction } from '../../services/firebaseService';

export default function SystemSettings() {
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState(null);
  const [config, setConfig] = useState({
    aiKeywordRecommendationEnabled: true
  });
  const [notification, setNotification] = useState({ open: false, message: '', severity: 'info' });

  // cleanup ref
  const isMountedRef = useRef(true);

  // 알림 표시
  const showNotification = useCallback((message, severity = 'info') => {
    setNotification({ open: true, message, severity });
  }, []);

  // 초기 설정 로드
  const loadConfig = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await callFunction('getSystemConfig');

      if (isMountedRef.current && result.config) {
        setConfig(result.config);
      }
    } catch (err) {
      console.error('시스템 설정 로드 실패:', err);
      if (isMountedRef.current) {
        setError('시스템 설정을 불러오는데 실패했습니다.');
      }
    } finally {
      if (isMountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    loadConfig();

    return () => {
      isMountedRef.current = false;
    };
  }, [loadConfig]);

  // 토글 변경 핸들러
  const handleToggleChange = useCallback((field) => async (event) => {
    const newValue = event.target.checked;
    const previousValue = config[field];

    // 낙관적 업데이트
    setConfig(prev => ({ ...prev, [field]: newValue }));

    try {
      setUpdating(true);
      setError(null);

      await callFunction('updateSystemConfig', {
        [field]: newValue
      });

      if (isMountedRef.current) {
        showNotification('설정이 업데이트되었습니다.', 'success');
      }
    } catch (err) {
      console.error('시스템 설정 업데이트 실패:', err);

      // 롤백
      if (isMountedRef.current) {
        setConfig(prev => ({ ...prev, [field]: previousValue }));
        setError(err.message || '설정 업데이트에 실패했습니다.');
        showNotification('설정 업데이트에 실패했습니다.', 'error');
      }
    } finally {
      if (isMountedRef.current) {
        setUpdating(false);
      }
    }
  }, [config, showNotification]);

  // 로딩 상태
  if (loading) {
    return (
      <Paper
        sx={{ p: 3, borderRadius: 1 }}
        aria-busy="true"
        aria-label="시스템 설정 로딩 중"
      >
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 4 }}>
          <CircularProgress aria-label="로딩 중" />
        </Box>
      </Paper>
    );
  }

  return (
    <>
      <Paper
        sx={{ p: { xs: 2, sm: 3 }, borderRadius: 1, boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)' }}
        component="section"
        aria-labelledby="system-settings-title"
      >
        {/* 헤더 */}
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
          <Settings sx={{ fontSize: 28, color: '#006261', mr: 1.5 }} aria-hidden="true" />
          <Box>
            <Typography
              id="system-settings-title"
              variant="h6"
              component="h2"
              sx={{ fontWeight: 600, color: '#000000' }}
            >
              시스템 설정
            </Typography>
            <Typography variant="body2" sx={{ color: 'rgba(0, 0, 0, 0.6)' }}>
              전체 사용자에게 적용되는 시스템 기능을 관리합니다
            </Typography>
          </Box>
        </Box>

        <Divider sx={{ mb: 3 }} />

        {/* 에러 메시지 */}
        {error && (
          <Alert
            severity="error"
            sx={{ mb: 3 }}
            onClose={() => setError(null)}
            role="alert"
            aria-live="assertive"
          >
            {error}
          </Alert>
        )}

        {/* 설정 항목들 */}
        <Box role="group" aria-label="시스템 설정 옵션">
          <Box
            sx={{
              display: 'flex',
              flexDirection: { xs: 'column', sm: 'row' },
              alignItems: { xs: 'flex-start', sm: 'center' },
              justifyContent: 'space-between',
              gap: 2,
              p: 2,
              borderRadius: 1,
              bgcolor: 'rgba(0, 98, 97, 0.04)',
              '&:hover': {
                bgcolor: 'rgba(0, 98, 97, 0.08)'
              }
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'flex-start', flex: 1 }}>
              <Psychology sx={{ fontSize: 24, color: '#006261', mr: 2, mt: 0.5 }} aria-hidden="true" />
              <Box>
                <Typography
                  variant="subtitle1"
                  component="label"
                  id="ai-keyword-label"
                  htmlFor="ai-keyword-switch"
                  sx={{ fontWeight: 600, mb: 0.5, display: 'block', cursor: 'pointer' }}
                >
                  AI 검색어 추천 기능
                </Typography>
                <Typography
                  variant="body2"
                  id="ai-keyword-description"
                  sx={{ color: 'rgba(0, 0, 0, 0.6)' }}
                >
                  사용자가 원고 작성 시 AI 기반 검색어 추천 기능을 사용할 수 있습니다.
                  <br />
                  (비활성화 시 모든 사용자에게 검색어 탐색 버튼이 표시되지 않습니다)
                </Typography>
              </Box>
            </Box>

            <FormControlLabel
              control={
                <Switch
                  id="ai-keyword-switch"
                  checked={config.aiKeywordRecommendationEnabled}
                  onChange={handleToggleChange('aiKeywordRecommendationEnabled')}
                  disabled={updating}
                  inputProps={{
                    'aria-labelledby': 'ai-keyword-label',
                    'aria-describedby': 'ai-keyword-description'
                  }}
                  sx={{
                    '& .MuiSwitch-switchBase.Mui-checked': {
                      color: '#006261',
                    },
                    '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                      backgroundColor: '#006261',
                    },
                    '& .MuiSwitch-switchBase:focus-visible': {
                      outline: '2px solid #006261',
                      outlineOffset: '2px'
                    }
                  }}
                />
              }
              label={
                <Typography
                  variant="body2"
                  sx={{
                    fontWeight: 500,
                    color: config.aiKeywordRecommendationEnabled ? '#006261' : 'rgba(0, 0, 0, 0.6)'
                  }}
                >
                  {config.aiKeywordRecommendationEnabled ? '활성화' : '비활성화'}
                </Typography>
              }
              labelPlacement="start"
              sx={{ m: 0, ml: { xs: 0, sm: 2 } }}
            />
          </Box>

          {/* 업데이트 로딩 오버레이 */}
          {updating && (
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                mt: 2,
                p: 2,
                bgcolor: 'rgba(0, 98, 97, 0.04)',
                borderRadius: 1
              }}
              role="status"
              aria-live="polite"
            >
              <CircularProgress size={20} sx={{ mr: 1 }} aria-hidden="true" />
              <Typography variant="body2" sx={{ color: 'rgba(0, 0, 0, 0.6)' }}>
                설정을 업데이트하는 중...
              </Typography>
            </Box>
          )}

          {/* 마지막 업데이트 정보 */}
          {config.lastUpdated && (
            <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid rgba(0, 0, 0, 0.08)' }}>
              <Typography variant="caption" sx={{ color: 'rgba(0, 0, 0, 0.5)' }}>
                마지막 업데이트: {new Date(config.lastUpdated).toLocaleString('ko-KR')}
              </Typography>
            </Box>
          )}
        </Box>
      </Paper>

      {/* 알림 스낵바 */}
      <Snackbar
        open={notification.open}
        autoHideDuration={4000}
        onClose={() => setNotification(prev => ({ ...prev, open: false }))}
        message={notification.message}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      />
    </>
  );
}
