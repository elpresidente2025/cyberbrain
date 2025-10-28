// frontend/src/components/admin/SystemSettings.jsx
import React, { useState, useEffect } from 'react';
import {
  Paper,
  Typography,
  Box,
  Switch,
  FormControlLabel,
  CircularProgress,
  Alert,
  Divider
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

  // 초기 설정 로드
  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      setLoading(true);
      setError(null);
      const result = await callFunction('getSystemConfig');
      if (result.config) {
        setConfig(result.config);
      }
    } catch (err) {
      console.error('시스템 설정 로드 실패:', err);
      setError('시스템 설정을 불러오는데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleChange = async (field) => async (event) => {
    const newValue = event.target.checked;

    try {
      setUpdating(true);
      setError(null);

      // 백엔드 업데이트
      await callFunction('updateSystemConfig', {
        [field]: newValue
      });

      // 로컬 상태 업데이트
      setConfig(prev => ({
        ...prev,
        [field]: newValue
      }));

      console.log('✅ 시스템 설정 업데이트 성공:', { [field]: newValue });
    } catch (err) {
      console.error('시스템 설정 업데이트 실패:', err);
      setError(err.message || '설정 업데이트에 실패했습니다.');

      // 롤백
      setConfig(prev => ({ ...prev }));
    } finally {
      setUpdating(false);
    }
  };

  if (loading) {
    return (
      <Paper sx={{ p: 3, borderRadius: 2 }}>
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 3, borderRadius: 2, boxShadow: '0 2px 8px rgba(0, 0, 0, 0.08)' }}>
      {/* 헤더 */}
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
        <Settings sx={{ fontSize: 28, color: '#006261', mr: 1.5 }} />
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600, color: '#000000' }}>
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
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* 설정 항목들 */}
      <Box>
        <Box sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          p: 2,
          borderRadius: 1,
          bgcolor: 'rgba(0, 98, 97, 0.04)',
          '&:hover': {
            bgcolor: 'rgba(0, 98, 97, 0.08)'
          }
        }}>
          <Box sx={{ display: 'flex', alignItems: 'center', flex: 1 }}>
            <Psychology sx={{ fontSize: 24, color: '#006261', mr: 2 }} />
            <Box>
              <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 0.5 }}>
                AI 검색어 추천 기능
              </Typography>
              <Typography variant="body2" sx={{ color: 'rgba(0, 0, 0, 0.6)' }}>
                사용자가 원고 작성 시 AI 기반 검색어 추천 기능을 사용할 수 있습니다.
                <br />
                (비활성화 시 모든 사용자에게 검색어 탐색 버튼이 표시되지 않습니다)
              </Typography>
            </Box>
          </Box>

          <FormControlLabel
            control={
              <Switch
                checked={config.aiKeywordRecommendationEnabled}
                onChange={handleToggleChange('aiKeywordRecommendationEnabled')}
                disabled={updating}
                sx={{
                  '& .MuiSwitch-switchBase.Mui-checked': {
                    color: '#006261',
                  },
                  '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': {
                    backgroundColor: '#006261',
                  },
                }}
              />
            }
            label={config.aiKeywordRecommendationEnabled ? '활성화' : '비활성화'}
            labelPlacement="start"
            sx={{ m: 0, ml: 2 }}
          />
        </Box>

        {/* 업데이트 로딩 오버레이 */}
        {updating && (
          <Box sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            mt: 2,
            p: 2,
            bgcolor: 'rgba(0, 98, 97, 0.04)',
            borderRadius: 1
          }}>
            <CircularProgress size={20} sx={{ mr: 1 }} />
            <Typography variant="body2" sx={{ color: 'rgba(0, 0, 0, 0.6)' }}>
              설정을 업데이트하는 중...
            </Typography>
          </Box>
        )}

        {/* 마지막 업데이트 정보 */}
        {config.lastUpdated && (
          <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid rgba(0, 0, 0, 0.08)' }}>
            <Typography variant="caption" sx={{ color: 'rgba(0, 0, 0, 0.5)' }}>
              마지막 업데이트: {new Date(config.lastUpdated.seconds * 1000).toLocaleString('ko-KR')}
            </Typography>
          </Box>
        )}
      </Box>
    </Paper>
  );
}
