// frontend/src/components/admin/QuickActions.jsx
import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  Typography,
  Grid,
  Button,
  Box,
  Alert,
  useTheme,
  Snackbar
} from '@mui/material';
import {
  Download,
  People,
  Api,
  ToggleOn,
  Psychology,
  Style
} from '@mui/icons-material';
import UserListModal from './UserListModal';
import StatusUpdateModal from './StatusUpdateModal';
import HongKongNeonCard from '../HongKongNeonCard';
import { getAdminStats, callFunctionWithRetry } from '../../services/firebaseService';
import { buildFunctionsUrl } from '../../config/branding';

function QuickActions() {
  const theme = useTheme();
  const [userListOpen, setUserListOpen] = useState(false);
  const [statusUpdateOpen, setStatusUpdateOpen] = useState(false);
  const [serviceMode, setServiceMode] = useState(null);
  const [loadingToggle, setLoadingToggle] = useState(false);
  const [notification, setNotification] = useState({ open: false, message: '', severity: 'info' });
  const [ragIndexing, setRagIndexing] = useState(false);
  const [ragProgress, setRagProgress] = useState('');
  const [styleBatching, setStyleBatching] = useState(false);
  const [styleBatchProgress, setStyleBatchProgress] = useState('');

  // cleanup ref
  const isMountedRef = useRef(true);

  // 알림 표시
  const showNotification = useCallback((message, severity = 'info') => {
    setNotification({ open: true, message, severity });
  }, []);

  // 시스템 설정 로드
  useEffect(() => {
    isMountedRef.current = true;

    const loadServiceMode = async () => {
      try {
        const result = await callFunctionWithRetry('getSystemConfig');
        if (isMountedRef.current && result?.config) {
          setServiceMode(result.config.testMode || false);
        }
      } catch (error) {
        console.error('시스템 설정 로드 실패:', error);
        if (isMountedRef.current) {
          setServiceMode(false);
        }
      }
    };
    loadServiceMode();

    return () => {
      isMountedRef.current = false;
    };
  }, []);

  // CSV 생성 헬퍼 함수
  const createCsv = useCallback((data, filename) => {
    if (!data || data.length === 0) return false;

    const headers = Object.keys(data[0]);
    const csvContent = [
      headers.join(','),
      ...data.map(row =>
        headers.map(header => {
          const value = row[header];
          if (value === null || value === undefined) return '';
          if (typeof value === 'object') return JSON.stringify(value).replace(/"/g, '""');
          return String(value).replace(/"/g, '""');
        }).map(v => `"${v}"`).join(',')
      )
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${filename}_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    return true;
  }, []);

  // 전체 데이터 CSV 내보내기
  const exportAllData = useCallback(async () => {
    try {
      const [usersResult, statsResult] = await Promise.all([
        callFunctionWithRetry('getAllUsers'),
        getAdminStats()
      ]);

      let filesExported = 0;

      if (usersResult?.users && createCsv(usersResult.users, 'users')) {
        filesExported++;
      }

      if (statsResult?.stats || statsResult?.data) {
        const statsData = statsResult.stats || statsResult.data;
        if (createCsv([{ date: new Date().toISOString(), ...statsData }], 'stats')) {
          filesExported++;
        }
      }

      if (filesExported > 0) {
        showNotification(`${filesExported}개의 CSV 파일이 다운로드되었습니다.`, 'success');
      } else {
        showNotification('내보낼 데이터가 없습니다.', 'warning');
      }
    } catch (error) {
      console.error('CSV 내보내기 실패:', error);
      showNotification('CSV 내보내기 실패: ' + error.message, 'error');
    }
  }, [createCsv, showNotification]);

  // 캐시 비우기
  const clearCache = useCallback(async () => {
    if (!window.confirm('정말로 캐시를 비우시겠습니까?')) return;

    try {
      await callFunctionWithRetry('clearSystemCache');
      showNotification('캐시가 성공적으로 비워졌습니다.', 'success');
      setTimeout(() => window.location.reload(), 1500);
    } catch (error) {
      console.error('캐시 비우기 실패:', error);
      showNotification('캐시 비우기 실패: ' + error.message, 'error');
    }
  }, [showNotification]);

  // RAG 일괄 색인
  const batchIndexRag = useCallback(async () => {
    if (!window.confirm(
      '전체 사용자의 프로필 데이터를 LightRAG 지식 그래프에 일괄 색인합니다.\n\n' +
      '• Gemini API를 사용하므로 사용자당 30~60초 소요\n' +
      '• 사용자가 많으면 자동으로 여러 배치로 나눠 실행\n\n' +
      '진행하시겠습니까?'
    )) return;

    setRagIndexing(true);
    setRagProgress('색인 준비 중...');

    const functionUrl = buildFunctionsUrl('batch_index_bios');

    let totalSuccess = 0;
    let totalSkipped = 0;
    let totalFailed = 0;
    let batchNumber = 0;
    let startAfter = '';
    let hasMore = true;

    try {
      while (hasMore) {
        batchNumber++;
        setRagProgress(`배치 ${batchNumber} 처리 중... (성공: ${totalSuccess}, 스킵: ${totalSkipped}, 실패: ${totalFailed})`);

        const body = { limit: 10 };
        if (startAfter) body.startAfter = startAfter;

        const response = await fetch(functionUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(600000),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const result = await response.json();

        if (result.error) {
          throw new Error(result.error);
        }

        totalSuccess += result.successCount || 0;
        totalSkipped += result.skippedCount || 0;
        totalFailed += result.failedCount || 0;
        startAfter = result.lastUid || '';
        hasMore = result.hasMore === true && startAfter;
      }

      setRagProgress('');
      showNotification(
        `RAG 일괄 색인 완료: 성공 ${totalSuccess}명, 스킵 ${totalSkipped}명, 실패 ${totalFailed}명`,
        totalFailed > 0 ? 'warning' : 'success'
      );
    } catch (error) {
      console.error('RAG 일괄 색인 실패:', error);
      setRagProgress('');
      showNotification(
        `RAG 일괄 색인 오류: ${error.message} (성공: ${totalSuccess}, 실패: ${totalFailed})`,
        'error'
      );
    } finally {
      setRagIndexing(false);
    }
  }, [showNotification]);

  const batchAnalyzeStyles = useCallback(async () => {
    if (!window.confirm(
      '전체 사용자 bio를 순차적으로 읽어 문체 분석(styleFingerprint)을 다시 계산합니다.\n\n' +
      '• 이미 신뢰도 0.7 이상인 사용자는 자동으로 건너뜁니다.\n' +
      '• 사용자 수에 따라 여러 배치로 나누어 수 분 이상 걸릴 수 있습니다.\n\n' +
      '계속하시겠습니까?'
    )) return;

    const forceReanalysis = window.confirm(
      '기존에 신뢰도 0.7 이상 문체 분석이 있는 사용자까지 포함해 강제 재분석할까요?\n\n' +
      '확인을 누르면 전체 bio를 다시 분석하고, 취소를 누르면 기존 고신뢰 사용자는 건너뜁니다.'
    );
    const modeLabel = forceReanalysis ? '강제 재분석' : '일반 분석';

    setStyleBatching(true);
    setStyleBatchProgress(`${modeLabel} 준비 중...`);

    let totalSuccess = 0;
    let totalSkipped = 0;
    let totalFailed = 0;
    let totalNoContent = 0;
    let batchNumber = 0;
    let startAfter = '';
    let hasMore = true;

    try {
      while (hasMore) {
        batchNumber += 1;
        setStyleBatchProgress(
          `${modeLabel} 배치 ${batchNumber} 진행 중... (성공: ${totalSuccess}, 스킵: ${totalSkipped}, 실패: ${totalFailed})`
        );

        const result = await callFunctionWithRetry(
          'py_batchAnalyzeBioStyles',
          {
            limit: 10,
            minConfidence: 0.7,
            force: forceReanalysis,
            ...(startAfter ? { startAfter } : {})
          },
          { timeoutMs: 300000, retries: 1 }
        );

        totalSuccess += result?.successCount || 0;
        totalSkipped += result?.skippedCount || 0;
        totalFailed += result?.failedCount || 0;
        totalNoContent += result?.noContentCount || 0;
        startAfter = result?.lastUid || '';
        hasMore = result?.hasMore === true && Boolean(startAfter);
      }

      setStyleBatchProgress('');
      showNotification(
        `문체 분석 완료: 성공 ${totalSuccess}명, 스킵 ${totalSkipped}명, 콘텐츠 부족 ${totalNoContent}명, 실패 ${totalFailed}명`,
        totalFailed > 0 ? 'warning' : 'success'
      );
    } catch (error) {
      console.error('문체 일괄 분석 실패:', error);
      setStyleBatchProgress('');
      showNotification(
        `문체 일괄 분석 오류: ${error.message} (성공: ${totalSuccess}, 실패: ${totalFailed})`,
        'error'
      );
    } finally {
      setStyleBatching(false);
    }
  }, [showNotification]);

  // 서비스 모드 토글
  const toggleServiceMode = useCallback(async () => {
    const newMode = !serviceMode;
    const modeText = newMode ? '데모 모드' : '프로덕션 모드';

    const confirmed = window.confirm(
      `정말로 ${modeText}로 전환하시겠습니까?\n\n` +
      (newMode
        ? '• 당원 인증 시 월 8회 무료 제공\n• 당원 인증 필수, 구독 불필요\n• 대시보드에 "데모 모드" 배지 표시'
        : '• 즉시 유료 결제 + 당원 인증 필수\n• 사용자는 8회 무료 체험 후 결제 필요')
    );

    if (!confirmed) return;

    setLoadingToggle(true);
    try {
      await callFunctionWithRetry('updateSystemConfig', {
        testMode: newMode
      });

      if (isMountedRef.current) {
        setServiceMode(newMode);
        showNotification(`${modeText}로 전환되었습니다.`, 'success');
        setTimeout(() => window.location.reload(), 1500);
      }
    } catch (error) {
      console.error('서비스 모드 전환 실패:', error);
      showNotification('서비스 모드 전환 실패: ' + error.message, 'error');
    } finally {
      if (isMountedRef.current) {
        setLoadingToggle(false);
      }
    }
  }, [serviceMode, showNotification]);

  return (
    <>
      <HongKongNeonCard sx={{ p: { xs: 2, sm: 3 }, mb: 3 }}>
        <Typography
          variant="h6"
          component="h2"
          id="quick-actions-heading"
          gutterBottom
          sx={{ color: theme.palette.ui?.header || '#152484', fontWeight: 600 }}
        >
          빠른 작업 (Quick Actions)
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
          자주 사용하는 관리 기능들을 빠르게 실행할 수 있습니다.
        </Typography>

        <Grid
          container
          spacing={2}
          role="group"
          aria-labelledby="quick-actions-heading"
        >
          <Grid item xs={12} sm={6} md={4}>
            <Button
              fullWidth
              variant="contained"
              startIcon={<People aria-hidden="true" />}
              onClick={() => setUserListOpen(true)}
              aria-label="사용자 목록 모달 열기"
              sx={{
                py: 2,
                bgcolor: theme.palette.ui?.header || '#152484',
                color: 'white',
                '&:hover': {
                  bgcolor: '#1e2d9f',
                  transform: 'translateY(-2px)',
                  boxShadow: '0 6px 16px rgba(21, 36, 132, 0.3)'
                },
                '&:focus-visible': {
                  outline: '2px solid #152484',
                  outlineOffset: '2px'
                }
              }}
            >
              사용자 목록
            </Button>
          </Grid>

          <Grid item xs={12} sm={6} md={4}>
            <Button
              fullWidth
              variant="contained"
              startIcon={<Api aria-hidden="true" />}
              onClick={() => setStatusUpdateOpen(true)}
              aria-label="상태 수정 모달 열기"
              sx={{
                py: 2,
                bgcolor: '#006261',
                color: 'white',
                '&:hover': {
                  bgcolor: '#007a74',
                  transform: 'translateY(-2px)',
                  boxShadow: '0 6px 16px rgba(0, 98, 97, 0.3)'
                },
                '&:focus-visible': {
                  outline: '2px solid #006261',
                  outlineOffset: '2px'
                }
              }}
            >
              상태 수정
            </Button>
          </Grid>

          <Grid item xs={12} sm={6} md={4}>
            <Button
              fullWidth
              variant="contained"
              startIcon={<Download aria-hidden="true" />}
              onClick={exportAllData}
              aria-label="전체 데이터 CSV 다운로드"
              sx={{
                py: 2,
                bgcolor: '#55207D',
                color: 'white',
                '&:hover': {
                  bgcolor: '#6d2b93',
                  transform: 'translateY(-2px)',
                  boxShadow: '0 6px 16px rgba(85, 32, 125, 0.3)'
                },
                '&:focus-visible': {
                  outline: '2px solid #55207D',
                  outlineOffset: '2px'
                }
              }}
            >
              CSV 다운로드
            </Button>
          </Grid>

          <Grid item xs={12} sm={6} md={4}>
            <Button
              fullWidth
              variant={serviceMode ? "contained" : "outlined"}
              startIcon={<ToggleOn aria-hidden="true" />}
              onClick={toggleServiceMode}
              disabled={loadingToggle || serviceMode === null}
              aria-label={serviceMode ? '데모 모드에서 프로덕션 모드로 전환' : '프로덕션 모드에서 데모 모드로 전환'}
              aria-pressed={serviceMode}
              sx={{
                py: 2,
                borderColor: serviceMode ? '#006261' : '#d22730',
                color: serviceMode ? 'white' : '#d22730',
                backgroundColor: serviceMode ? '#006261' : 'transparent',
                '&:hover': {
                  borderColor: serviceMode ? '#006261' : '#d22730',
                  backgroundColor: serviceMode ? '#007a74' : 'rgba(210, 39, 48, 0.04)'
                },
                '&.Mui-disabled': {
                  opacity: 0.6
                },
                '&:focus-visible': {
                  outline: `2px solid ${serviceMode ? '#006261' : '#d22730'}`,
                  outlineOffset: '2px'
                }
              }}
            >
              {serviceMode === null ? '로딩 중...' : (serviceMode ? '데모 모드' : '프로덕션 모드')}
            </Button>
          </Grid>
        </Grid>

        {/* 서비스 모드 상태 표시 */}
        {serviceMode !== null && (
          <Alert
            severity={serviceMode ? "info" : "success"}
            sx={{ mt: 2 }}
            role="status"
            aria-live="polite"
          >
            <Typography variant="body2" component="div">
              {serviceMode ? (
                <>
                  <strong>데모 모드 활성화됨</strong>
                  <br />
                  <span>• 당원 인증 시 월 8회 무료 제공</span>
                  <br />
                  <span>• 당원 인증 필수, 구독 불필요</span>
                </>
              ) : (
                <>
                  <strong>프로덕션 모드 활성화됨</strong>
                  <br />
                  <span>• 유료 구독 + 당원 인증 필수</span>
                  <br />
                  <span>• 무료 체험 8회 제공 후 결제 필요</span>
                </>
              )}
            </Typography>
          </Alert>
        )}

        {/* 추가 관리 도구 */}
        <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid #e0e0e0' }}>
          <Typography variant="subtitle2" color="text.secondary" gutterBottom>
            시스템 관리
          </Typography>
          <Grid container spacing={1} alignItems="center">
            <Grid item>
              <Button
                size="small"
                variant="text"
                onClick={clearCache}
                aria-label="시스템 캐시 비우기"
                sx={{
                  color: '#55207D',
                  '&:focus-visible': {
                    outline: '2px solid #55207D',
                    outlineOffset: '2px'
                  }
                }}
              >
                캐시 비우기
              </Button>
            </Grid>
            <Grid item>
              <Button
                size="small"
                variant="text"
                startIcon={<Psychology aria-hidden="true" sx={{ fontSize: 18 }} />}
                onClick={batchIndexRag}
                disabled={ragIndexing}
                aria-label="전체 사용자 RAG 일괄 색인"
                sx={{
                  color: '#003A87',
                  '&:focus-visible': {
                    outline: '2px solid #003A87',
                    outlineOffset: '2px'
                  },
                  '&.Mui-disabled': {
                    color: '#003A87',
                    opacity: 0.7
                  }
                }}
              >
                {ragIndexing ? ragProgress || 'RAG 색인 중...' : 'RAG 일괄 색인'}
              </Button>
            </Grid>
            <Grid item>
              <Button
                size="small"
                variant="text"
                startIcon={<Style aria-hidden="true" sx={{ fontSize: 18 }} />}
                onClick={batchAnalyzeStyles}
                disabled={styleBatching}
                aria-label="전체 사용자 문체 일괄 분석"
                sx={{
                  color: '#8C2F39',
                  '&:focus-visible': {
                    outline: '2px solid #8C2F39',
                    outlineOffset: '2px'
                  },
                  '&.Mui-disabled': {
                    color: '#8C2F39',
                    opacity: 0.7
                  }
                }}
              >
                {styleBatching ? styleBatchProgress || '문체 분석 중...' : '문체 일괄 분석'}
              </Button>
            </Grid>
          </Grid>
        </Box>
      </HongKongNeonCard>

      {/* 모달들 */}
      <UserListModal
        open={userListOpen}
        onClose={() => setUserListOpen(false)}
      />
      <StatusUpdateModal
        open={statusUpdateOpen}
        onClose={() => setStatusUpdateOpen(false)}
      />

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

export default QuickActions;
