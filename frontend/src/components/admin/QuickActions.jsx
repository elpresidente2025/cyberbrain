// frontend/src/components/admin/QuickActions.jsx
import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  Typography,
  Grid,
  Button,
  Box,
  Alert,
  Chip,
  useTheme,
  Snackbar
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import {
  Download,
  People,
  Api,
  ToggleOn,
  Psychology,
  Style,
  MenuBook,
  AutoAwesome
} from '@mui/icons-material';
import UserListModal from './UserListModal';
import StatusUpdateModal from './StatusUpdateModal';
import HongKongNeonCard from '../HongKongNeonCard';
import { getAdminStats, callFunctionWithRetry } from '../../services/firebaseService';
import { buildFunctionsUrl } from '../../config/branding';

const DANGER = '#d22730';

function QuickActions() {
  const theme = useTheme();
  const P = theme.palette.primary.main;

  const primaryContained = {
    bgcolor: P,
    color: 'white',
    fontWeight: 600,
    '&:hover': {
      bgcolor: theme.palette.primary.dark,
      transform: 'translateY(-2px)',
      boxShadow: `0 6px 18px ${alpha(P, 0.32)}`,
    },
    '&:focus-visible': { outline: `2px solid ${P}`, outlineOffset: '2px' },
  };

  const primaryOutlined = {
    borderColor: alpha(P, 0.4),
    color: P,
    '&:hover': {
      borderColor: P,
      bgcolor: alpha(P, 0.05),
      transform: 'translateY(-2px)',
    },
    '&:focus-visible': { outline: `2px solid ${P}`, outlineOffset: '2px' },
  };

  const sysBtn = {
    borderColor: alpha(P, 0.3),
    color: P,
    '&:hover': { borderColor: P, bgcolor: alpha(P, 0.05) },
    '&.Mui-disabled': { opacity: 0.45 },
  };
  const [userListOpen, setUserListOpen] = useState(false);
  const [statusUpdateOpen, setStatusUpdateOpen] = useState(false);
  const [serviceMode, setServiceMode] = useState(null);
  const [loadingToggle, setLoadingToggle] = useState(false);
  const [notification, setNotification] = useState({ open: false, message: '', severity: 'info' });
  const [ragIndexing, setRagIndexing] = useState(false);
  const [ragProgress, setRagProgress] = useState('');
  const [affinityBatching, setAffinityBatching] = useState(false);
  const [styleBatching, setStyleBatching] = useState(false);
  const [styleBatchProgress, setStyleBatchProgress] = useState('');
  const [clicheDictRefreshing, setClicheDictRefreshing] = useState(false);
  const [clicheDictProgress, setClicheDictProgress] = useState('');

  const isMountedRef = useRef(true);

  const showNotification = useCallback((message, severity = 'info') => {
    setNotification({ open: true, message, severity });
  }, []);

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
        if (isMountedRef.current) setServiceMode(false);
      }
    };
    loadServiceMode();

    return () => { isMountedRef.current = false; };
  }, []);

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

  const exportAllData = useCallback(async () => {
    try {
      const [usersResult, statsResult] = await Promise.all([
        callFunctionWithRetry('getAllUsers'),
        getAdminStats()
      ]);
      let filesExported = 0;
      if (usersResult?.users && createCsv(usersResult.users, 'users')) filesExported++;
      if (statsResult?.stats || statsResult?.data) {
        const statsData = statsResult.stats || statsResult.data;
        if (createCsv([{ date: new Date().toISOString(), ...statsData }], 'stats')) filesExported++;
      }
      if (filesExported > 0) {
        showNotification(`${filesExported}개의 CSV 파일이 다운로드되었습니다.`, 'success');
      } else {
        showNotification('내보낼 데이터가 없습니다.', 'warning');
      }
    } catch (error) {
      showNotification('CSV 내보내기 실패: ' + error.message, 'error');
    }
  }, [createCsv, showNotification]);

  const clearCache = useCallback(async () => {
    if (!window.confirm('정말로 캐시를 비우시겠습니까?')) return;
    try {
      await callFunctionWithRetry('clearSystemCache');
      showNotification('캐시가 성공적으로 비워졌습니다.', 'success');
      setTimeout(() => window.location.reload(), 1500);
    } catch (error) {
      showNotification('캐시 비우기 실패: ' + error.message, 'error');
    }
  }, [showNotification]);

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
    let totalSuccess = 0, totalSkipped = 0, totalFailed = 0;
    let batchNumber = 0, startAfter = '', hasMore = true;

    try {
      while (hasMore) {
        batchNumber++;
        setRagProgress(`배치 ${batchNumber} 처리 중... (성공: ${totalSuccess}, 실패: ${totalFailed})`);
        const body = { limit: 10 };
        if (startAfter) body.startAfter = startAfter;
        const response = await fetch(functionUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(600000),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        const result = await response.json();
        if (result.error) throw new Error(result.error);
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
      setRagProgress('');
      showNotification(`RAG 일괄 색인 오류: ${error.message} (성공: ${totalSuccess}, 실패: ${totalFailed})`, 'error');
    } finally {
      setRagIndexing(false);
    }
  }, [showNotification]);

  const batchComputeAffinity = useCallback(async () => {
    if (!window.confirm(
      '전체 사용자의 Bio를 분석해 leadership.py 도메인 친화도를 재계산합니다.\n\n' +
      'RAG 재색인 없이 친화도만 갱신하므로 빠릅니다 (수십 초).\n\n' +
      '계속하시겠습니까?'
    )) return;
    setAffinityBatching(true);
    try {
      const functionUrl = buildFunctionsUrl('batch_compute_affinity');
      const response = await fetch(functionUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
        signal: AbortSignal.timeout(300000),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const result = await response.json();
      showNotification(
        `Affinity 재계산 완료: 성공 ${result.ok ?? 0}명, 스킵 ${result.skipped ?? 0}명, 실패 ${result.failed ?? 0}명`,
        (result.failed ?? 0) > 0 ? 'warning' : 'success'
      );
    } catch (error) {
      showNotification(`Affinity 재계산 오류: ${error.message}`, 'error');
    } finally {
      setAffinityBatching(false);
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
      '확인: 전체 재분석 / 취소: 고신뢰 사용자 건너뜀'
    );
    const modeLabel = forceReanalysis ? '강제 재분석' : '일반 분석';

    setStyleBatching(true);
    setStyleBatchProgress(`${modeLabel} 준비 중...`);
    let totalSuccess = 0, totalSkipped = 0, totalFailed = 0, totalNoContent = 0;
    let batchNumber = 0, startAfter = '', hasMore = true;

    try {
      while (hasMore) {
        batchNumber += 1;
        setStyleBatchProgress(`${modeLabel} 배치 ${batchNumber} 진행 중... (성공: ${totalSuccess}, 실패: ${totalFailed})`);
        const result = await callFunctionWithRetry(
          'py_batchAnalyzeBioStyles',
          { limit: 10, minConfidence: 0.7, force: forceReanalysis, ...(startAfter ? { startAfter } : {}) },
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
      setStyleBatchProgress('');
      showNotification(`문체 일괄 분석 오류: ${error.message} (성공: ${totalSuccess}, 실패: ${totalFailed})`, 'error');
    } finally {
      setStyleBatching(false);
    }
  }, [showNotification]);

  const refreshClicheDictionary = useCallback(async () => {
    if (!window.confirm(
      '상투어 대체어 사전을 갱신합니다.\n\n' +
      '• centroid 구축 → 후보 추출 → 승격 처리 3단계 실행\n' +
      '• 최대 9분 소요될 수 있습니다.\n\n' +
      '진행하시겠습니까?'
    )) return;
    setClicheDictRefreshing(true);
    setClicheDictProgress('사전 갱신 중...');
    try {
      const functionUrl = buildFunctionsUrl('refresh_cliche_dictionary');
      const response = await fetch(functionUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(600000),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      const result = await response.json();
      if (result.error) throw new Error(result.error);
      setClicheDictProgress('');
      showNotification(`상투어 사전 갱신 완료 (${result.elapsed || '?'}초)`, 'success');
    } catch (error) {
      setClicheDictProgress('');
      showNotification('상투어 사전 갱신 실패: ' + error.message, 'error');
    } finally {
      setClicheDictRefreshing(false);
    }
  }, [showNotification]);

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
      await callFunctionWithRetry('updateSystemConfig', { testMode: newMode });
      if (isMountedRef.current) {
        setServiceMode(newMode);
        showNotification(`${modeText}로 전환되었습니다.`, 'success');
        setTimeout(() => window.location.reload(), 1500);
      }
    } catch (error) {
      showNotification('서비스 모드 전환 실패: ' + error.message, 'error');
    } finally {
      if (isMountedRef.current) setLoadingToggle(false);
    }
  }, [serviceMode, showNotification]);

  return (
    <>
      <HongKongNeonCard
        sx={{
          p: { xs: 2, sm: 3 },
          mb: 3,
          // 콘텐츠 컨테이너 — 호버 리프트 비활성화
          '&:hover': { transform: 'none' },
        }}
      >
        {/* ── 헤더 ── */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            mb: 3,
          }}
        >
          <Typography
            variant="h6"
            component="h2"
            id="quick-actions-heading"
            sx={{ fontWeight: 700, color: theme.palette.text.primary }}
          >
            빠른 작업
          </Typography>
          {serviceMode !== null && (
            <Chip
              label={serviceMode ? '데모 모드' : '프로덕션 모드'}
              size="small"
              sx={{
                bgcolor: serviceMode
                  ? 'rgba(245, 158, 11, 0.12)'
                  : alpha(P, 0.1),
                color: serviceMode ? '#d97706' : P,
                border: '1px solid',
                borderColor: serviceMode
                  ? 'rgba(245, 158, 11, 0.35)'
                  : alpha(P, 0.3),
                fontWeight: 600,
                fontSize: '0.7rem',
              }}
            />
          )}
        </Box>

        {/* ── 주요 작업 — 7 : 5 비대칭 ── */}
        <Grid
          container
          spacing={2}
          role="group"
          aria-labelledby="quick-actions-heading"
          sx={{ mb: 2 }}
        >
          <Grid item xs={12} sm={7}>
            <Button
              fullWidth
              variant="contained"
              startIcon={<People aria-hidden="true" />}
              onClick={() => setUserListOpen(true)}
              aria-label="사용자 목록 모달 열기"
              sx={{ py: 1.75, ...primaryContained }}
            >
              사용자 목록
            </Button>
          </Grid>
          <Grid item xs={12} sm={5}>
            <Button
              fullWidth
              variant="outlined"
              startIcon={<Api aria-hidden="true" />}
              onClick={() => setStatusUpdateOpen(true)}
              aria-label="상태 수정 모달 열기"
              sx={{ py: 1.75, ...primaryOutlined }}
            >
              상태 수정
            </Button>
          </Grid>
        </Grid>

        {/* ── 데이터 + 서비스 모드 — 1 : 1 ── */}
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={12} sm={6}>
            <Button
              fullWidth
              variant="outlined"
              startIcon={<Download aria-hidden="true" />}
              onClick={exportAllData}
              aria-label="전체 데이터 CSV 다운로드"
              sx={{ py: 1.5, ...primaryOutlined }}
            >
              CSV 다운로드
            </Button>
          </Grid>
          <Grid item xs={12} sm={6}>
            <Button
              fullWidth
              variant={serviceMode ? 'contained' : 'outlined'}
              startIcon={<ToggleOn aria-hidden="true" />}
              onClick={toggleServiceMode}
              disabled={loadingToggle || serviceMode === null}
              aria-label={serviceMode ? '데모 모드 해제' : '데모 모드 활성화'}
              aria-pressed={!!serviceMode}
              sx={
                serviceMode
                  ? {
                      py: 1.5,
                      bgcolor: '#f59e0b',
                      color: 'white',
                      fontWeight: 600,
                      '&:hover': { bgcolor: '#d97706' },
                      '&.Mui-disabled': { opacity: 0.6 },
                    }
                  : {
                      py: 1.5,
                      ...primaryOutlined,
                      '&.Mui-disabled': { opacity: 0.6 },
                    }
              }
            >
              {serviceMode === null
                ? '로딩 중...'
                : serviceMode
                ? '데모 해제'
                : '데모 활성화'}
            </Button>
          </Grid>
        </Grid>

        {/* ── 서비스 모드 상태 배너 ── */}
        {serviceMode !== null && (
          <Alert
            severity={serviceMode ? 'warning' : 'info'}
            role="status"
            aria-live="polite"
            sx={{ py: 0.75, '& .MuiAlert-message': { py: 0 } }}
          >
            <Typography variant="body2" component="span">
              {serviceMode
                ? '데모 모드 — 당원 인증 시 월 8회 무료 제공'
                : '프로덕션 모드 — 유료 구독 + 당원 인증 필수'}
            </Typography>
          </Alert>
        )}

        {/* ── 시스템 관리 ── */}
        <Box
          sx={{
            mt: 3,
            pt: 2.5,
            borderTop: '1px solid',
            borderColor: 'divider',
          }}
        >
          <Typography
            variant="overline"
            sx={{
              display: 'block',
              mb: 1.5,
              fontSize: '0.65rem',
              letterSpacing: '0.12em',
              color: 'text.disabled',
            }}
          >
            시스템 관리
          </Typography>
          <Box
            sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}
            role="group"
            aria-label="시스템 관리 작업"
          >
            <Button
              size="small"
              variant="outlined"
              startIcon={<Psychology aria-hidden="true" sx={{ fontSize: 15 }} />}
              onClick={batchIndexRag}
              disabled={ragIndexing}
              aria-label="전체 사용자 RAG 일괄 색인"
              sx={sysBtn}
            >
              {ragIndexing ? ragProgress || 'RAG 색인 중...' : 'RAG 일괄 색인'}
            </Button>

            <Button
              size="small"
              variant="outlined"
              startIcon={<AutoAwesome aria-hidden="true" sx={{ fontSize: 15 }} />}
              onClick={batchComputeAffinity}
              disabled={affinityBatching}
              aria-label="전체 사용자 leadership affinity 재계산"
              sx={sysBtn}
            >
              {affinityBatching ? 'Affinity 계산 중...' : 'Affinity 재계산'}
            </Button>

            <Button
              size="small"
              variant="outlined"
              startIcon={<Style aria-hidden="true" sx={{ fontSize: 15 }} />}
              onClick={batchAnalyzeStyles}
              disabled={styleBatching}
              aria-label="전체 사용자 문체 일괄 분석"
              sx={sysBtn}
            >
              {styleBatching ? styleBatchProgress || '문체 분석 중...' : '문체 일괄 분석'}
            </Button>

            <Button
              size="small"
              variant="outlined"
              startIcon={<MenuBook aria-hidden="true" sx={{ fontSize: 15 }} />}
              onClick={refreshClicheDictionary}
              disabled={clicheDictRefreshing}
              aria-label="상투어 대체어 사전 갱신"
              sx={sysBtn}
            >
              {clicheDictRefreshing ? clicheDictProgress || '사전 갱신 중...' : '상투어 사전 갱신'}
            </Button>

            <Button
              size="small"
              variant="outlined"
              onClick={clearCache}
              aria-label="시스템 캐시 비우기"
              sx={{
                borderColor: `rgba(210, 39, 48, 0.35)`,
                color: DANGER,
                '&:hover': { borderColor: DANGER, bgcolor: 'rgba(210, 39, 48, 0.04)' },
                '&:focus-visible': { outline: `2px solid ${DANGER}`, outlineOffset: '2px' },
              }}
            >
              캐시 비우기
            </Button>
          </Box>
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
