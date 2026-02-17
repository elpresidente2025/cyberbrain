// frontend/src/pages/GeneratePage.jsx

// React 및 UI 라이브러리에서 필요한 기능들을 가져옵니다.
import React, { Suspense, useEffect, useCallback, useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  Container,
  Alert,
  useTheme,
  useMediaQuery,
  Skeleton,
  Box,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Button,
  Typography,
  FormControlLabel, // 🆕 추가
  Switch,           // 🆕 추가
  Tooltip,          // 🆕 추가
  Chip,             // 🆕 추가
  Backdrop,         // 🆕 추가
  CircularProgress  // 🆕 추가
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import ShareIcon from '@mui/icons-material/Share';
import { Create } from '@mui/icons-material';
import DashboardLayout from '../components/DashboardLayout';
import PromptForm from '../components/generate/PromptForm';
import GenerateActions from '../components/generate/GenerateActions';
import SNSConversionModal from '../components/SNSConversionModal';
// 기능별로 분리된 커스텀 훅(Hook)들을 가져옵니다.
import { useAuth } from '../hooks/useAuth';
import { useGenerateForm } from '../hooks/useGenerateForm';
import { NotificationSnackbar, useNotification, PageHeader } from '../components/ui';
import { useGenerateAPI } from '../hooks/useGenerateAPI';
import { useBonus } from '../hooks/useBonus';
import { getSNSUsage } from '../services/firebaseService';
// 폼에서 사용할 카테고리/세부 카테고리 목록 데이터를 가져옵니다.
import { CATEGORIES } from '../constants/formConstants';
import { spacing, typography, visualWeight, verticalRhythm } from '../theme/tokens';

// 🚀 성능 최적화를 위해 초안 그리드와 미리보기 패널은 필요할 때만 불러옵니다 (Lazy Loading).
const DraftGrid = React.lazy(() => import('../components/generate/DraftGrid'));
const PreviewPane = React.lazy(() => import('../components/generate/PreviewPane'));

// 🔄 로딩 오버레이 컴포넌트 (텍스트 순환 애니메이션)
// 🔄 로딩 오버레이 컴포넌트 (텍스트 순환 애니메이션)
// 단계별 순환 메시지 정의
const STEP_MESSAGES = {
  // 1. 구조 설계 (가장 오래 걸림)
  '구조 설계 및 초안 작성 중': [
    '근거와 구조를 정돈 중...',
    '주요 포인트 정리 중...',
    '문단 구성 조율 중...',
    '전체 개요를 잡는 중...'
  ],
  // 2. 본문 작성 (가장 텍스트 많음)
  '본문 작성 중': [
    '상세 내용을 글로 풀어내는 중...',
    '원고 초안 정리 중...',
    '핵심 메시지 다듬는 중...',
    '맥락을 반영해 문장을 다듬는 중...'
  ],
  '초안 작성 중': [
    '상세 내용을 글로 풀어내는 중...',
    '원고 초안 정리 중...',
    '핵심 메시지 다듬는 중...',
    '맥락을 반영해 문장을 다듬는 중...'
  ],
  // 3. SEO 최적화 (후반 작업)
  '검색 노출 최적화(SEO) 중': [
    '표현을 자연스럽게 다듬는 중...',
    '읽기 쉬운 문장으로 변환 중...',
    '문장 흐름 정리 중...',
    '완성도를 높이는 중...',
    '읽기 편한 문장으로 고치는 중...'
  ]
};

// 기본 메시지 (초기 로딩 등)
const DEFAULT_MESSAGES = [
  'AI가 원고를 생성하고 있습니다...',
  '잠시만 기다려 주세요...'
];

const LoadingOverlayWithRotatingText = React.memo(({ loading, progress }) => {
  const [messageIndex, setMessageIndex] = React.useState(0);

  // 현재 단계에 맞는 메시지 목록 찾기
  // progress.message가 STEP_MESSAGES의 키와 일치하면 해당 목록 사용
  // 일치하지 않으면 (예: '준비 중...', '완료') 해당 메시지를 단독으로 보여줌 (순환 X)
  const currentStepMessage = progress?.message;
  const targetMessages = STEP_MESSAGES[currentStepMessage] || DEFAULT_MESSAGES;
  const isRotatingStep = !!STEP_MESSAGES[currentStepMessage];

  React.useEffect(() => {
    if (!loading) {
      setMessageIndex(0);
      return;
    }

    // 단계가 변경되면 인덱스 초기화
    setMessageIndex(0);
  }, [loading, currentStepMessage]); // currentStepMessage 변경 시 초기화

  React.useEffect(() => {
    if (!loading || !isRotatingStep) return;

    const intervalId = setInterval(() => {
      setMessageIndex(prev => (prev + 1) % targetMessages.length);
    }, 2500); // 2.5초마다 변경

    return () => clearInterval(intervalId);
  }, [loading, isRotatingStep, targetMessages.length]);

  // 표시할 메시지 결정 로직:
  // 1. 순환 단계인 경우: targetMessages[index]
  // 2. 순환 단계가 아닌 경우 (예: 준비 중): progress.message 그대로 표시
  // 3. progress 자체가 없는 경우: DEFAULT_MESSAGES[index]
  let displayMessage;

  if (currentStepMessage && !isRotatingStep) {
    displayMessage = currentStepMessage;
  } else if (isRotatingStep) {
    displayMessage = targetMessages[messageIndex];
  } else {
    displayMessage = DEFAULT_MESSAGES[messageIndex % DEFAULT_MESSAGES.length];
  }

  return (
    <Backdrop
      sx={{
        color: '#fff',
        zIndex: (theme) => theme.zIndex.drawer + 1,
        flexDirection: 'column',
        gap: 2,
        backgroundColor: 'rgba(0, 0, 0, 0.6)',
        backdropFilter: 'blur(8px)',
        WebkitBackdropFilter: 'blur(8px)'
      }}
      open={loading}
    >
      <CircularProgress color="inherit" size={60} thickness={4} />
      <Typography
        variant="h6"
        align="center"
        sx={{
          fontWeight: 500,
          whiteSpace: 'pre-line',
          minHeight: '3em',  // 레이아웃 안정화
          display: 'flex',
          alignItems: 'center'
        }}
      >
        {displayMessage}
      </Typography>
      <Typography variant="body2" color="rgba(255, 255, 255, 0.7)">
        (보통 2~5분 소요, 상황에 따라 더 걸릴 수 있습니다)
      </Typography>
    </Backdrop>
  );
});


const GeneratePage = () => {
  // --- 🎨 UI 및 사용자 상태 관리 ---
  const theme = useTheme();
  const navigate = useNavigate();
  const isMobile = useMediaQuery(theme.breakpoints.down('md')); // 화면 크기에 따라 모바일 여부 판단
  const { user, refreshUserProfile } = useAuth(); // useAuth 훅을 통해 현재 로그인된 사용자 정보를 가져옴

  // 프로필 새로고침 상태
  const [profileRefreshed, setProfileRefreshed] = React.useState(false);
  const hasRefreshedProfile = React.useRef(false);

  // --- 🧠 커스텀 훅을 통한 핵심 로직 분리 ---
  // 폼의 상태와 관련된 모든 로직을 useGenerateForm 훅이 전담합니다.
  const { formData, updateForm, resetForm, validateForm, canGenerate } = useGenerateForm(user);
  // API 통신과 관련된 모든 상태와 함수를 useGenerateAPI 훅이 전담합니다.
  const {
    loading,      // 로딩 중인지 여부 (true/false)
    error,        // API 에러 메시지
    drafts,       // 생성된 원고 초안 목록
    setDrafts,    // 원고 목록 직접 설정 함수
    attempts,     // 현재 생성 시도 횟수
    maxAttempts,  // 최대 생성 시도 횟수
    progress,     // 진행 상황 { step, progress, message }
    generate,     // 원고 생성 API 호출 함수
    reset,        // API 상태 초기화 함수
    save,         // 원고 저장 API 호출 함수
    // 🆕 세션 정보
    sessionId,
    sessionAttempts,
    maxSessionAttempts,
    canRegenerate,
  } = useGenerateAPI();

  // --- 🎁 보너스 기능 관련 (자동 fetch 비활성화) ---
  const { bonusStats, fetchBonusStats } = useBonus({ autoFetch: false });

  // SNS 사용 조건 확인
  const fetchSNSUsage = useCallback(async () => {
    try {
      const result = await getSNSUsage();
      setSnsUsage(result);
    } catch (error) {
      console.error('SNS 사용량 조회 실패:', error);
    }
  }, []);

  // 사용자 프로필 새로고침 (최신 plan/subscription 정보 가져오기)
  useEffect(() => {
    const doRefresh = async () => {
      if (user?.uid && refreshUserProfile && !hasRefreshedProfile.current) {
        console.log('🔄 GeneratePage: 사용자 프로필 새로고침 시작');
        hasRefreshedProfile.current = true;
        try {
          await refreshUserProfile();
          console.log('✅ GeneratePage: 프로필 새로고침 완료');
          setProfileRefreshed(true);
        } catch (error) {
          console.error('❌ GeneratePage: 프로필 새로고침 실패:', error);
          // 실패해도 데이터 로딩은 진행
          setProfileRefreshed(true);
        }
      } else if (!user?.uid) {
        // 사용자가 없으면 바로 진행
        setProfileRefreshed(true);
      }
    };

    doRefresh();
  }, [user?.uid, refreshUserProfile]);

  // 프로필 새로고침 완료 후 데이터 로딩
  useEffect(() => {
    if (profileRefreshed && user?.uid) {
      console.log('📊 GeneratePage: 프로필 새로고침 완료 - 데이터 로딩 시작');
      fetchSNSUsage();
      fetchBonusStats();
    }
  }, [profileRefreshed, user?.uid, fetchSNSUsage, fetchBonusStats]);

  // --- 📢 사용자 피드백(알림창) 상태 관리 ---
  const { notification, showNotification, hideNotification } = useNotification();

  // --- 👁️ 미리보기 상태 관리 ---
  const [selectedDraft, setSelectedDraft] = React.useState(null); // 사용자가 선택한 초안

  // --- 📱 SNS 변환 상태 관리 ---
  const [snsModalOpen, setSnsModalOpen] = React.useState(false);
  const [snsPost, setSnsPost] = React.useState(null);
  const [snsUsage, setSnsUsage] = React.useState(null);

  // 💧 UX 개선: 메인 카테고리가 변경되면 세부 카테고리 선택값을 자동으로 초기화합니다.
  useEffect(() => {
    if (formData.category) {
      updateForm({ subCategory: '' });
    }
  }, [formData.category, updateForm]);

  // --- 🔒 사용자 인증 확인 ---
  // 사용자 정보가 없으면 페이지 내용을 보여주지 않고 에러 메시지를 표시합니다.
  if (!user?.uid) {
    return (
      <DashboardLayout>
        <Container maxWidth="xl" sx={{ py: `${spacing.xl}px` }}>
          <Alert severity="error">
            사용자 정보를 불러올 수 없습니다. 다시 로그인해주세요.
          </Alert>
        </Container>
      </DashboardLayout>
    );
  }

  // --- 헨들러 함수 (사용자 이벤트 처리) ---

  // 🌟 고품질 모드 상태 (A/B 테스트)
  const [useHighQuality, setUseHighQuality] = React.useState(false);
  // 권한 체크: 관리자 또는 테스터만 허용
  const canUseBetaFeatures = React.useMemo(() => {
    return user?.role === 'admin' || user?.isAdmin === true || user?.isTester === true;
  }, [user]);

  /** 원고 생성 버튼 클릭 시 실행되는 함수 */
  const handleGenerate = async () => {
    // 🔴 [FIX] 한글 IME 조합 완료를 위해 현재 포커스된 요소에서 blur 트리거
    // 모든 입력 필드(주제, 검색어 등)에서 조합 중인 한글이 있으면 완료시킴
    const activeElement = document.activeElement;
    if (activeElement && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA')) {
      activeElement.blur();
    }

    // blur 후 React state 업데이트 대기
    await new Promise(resolve => {
      requestAnimationFrame(() => {
        setTimeout(resolve, 100);
      });
    });

    // 1. 폼 데이터 유효성 검사
    const validation = validateForm();
    if (!validation.isValid) {
      showNotification(validation.error, 'error');
      return;
    }

    // 2. 유효하면 API 호출
    // 🆕 고품질 모드 선택 시 pipeline 파라미터 추가
    // 기본값은 백엔드에서 'modular'로 설정됨 (프롬프트 분산으로 품질 향상)
    const payload = {
      ...formData,
      ...(useHighQuality && { pipeline: 'highQuality' })  // highQuality만 명시, 나머지는 백엔드 기본값 사용
    };

    const result = await generate(payload);

    // 3. API 결과 처리
    if (result.success) {
      const modeMsg = useHighQuality ? ' [고품질 모드 적용됨]' : '';
      const successMessage = result.message + modeMsg + '\n\n💡 생성된 원고를 꼭 검수하시고, 필요에 따라 직위나 내용을 직접 편집해주세요.';
      showNotification(successMessage, 'success');
    } else {
      showNotification(result.error, 'error');
    }
  };

  /** 초기화 버튼 클릭 시 실행되는 함수 */
  const handleReset = () => {
    // resetForm();     // 💡 사용자 요청: '새 생성' 시 주제와 검색어 등 입력값은 유지되어야 함.
    reset();            // API 관련 상태(초안, 에러 등) 초기화
    setSelectedDraft(null); // 선택된 초안 초기화
    setSnsPost(null);   // SNS 포스트 상태 초기화
  };

  /** 초안 선택 시 실행되는 함수 - 선택만 하고 다른 초안은 유지 */
  const handleSelectDraft = (draft) => {
    // 선택된 초안을 별도로 저장하되, 다른 초안들은 그대로 유지
    setSelectedDraft(draft);
    showNotification('원고를 선택했습니다. 저장하시겠습니까?', 'info');
  };

  /** 선택된 원고를 최종 저장하는 함수 */
  const handleConfirmSelection = async (draft) => {
    try {
      // 실제 저장 로직
      const result = await save(draft);

      if (result.success) {
        showNotification('원고가 저장되었습니다. 내 원고 목록으로 이동합니다.', 'success');
        // 저장 성공 후 내 원고 목록으로 이동
        setTimeout(() => {
          navigate('/posts');
        }, 1000);
      } else {
        showNotification(result.error || '저장에 실패했습니다.', 'error');
      }
    } catch (error) {
      console.error('원고 저장 오류:', error);
      showNotification('저장 처리 중 오류가 발생했습니다.', 'error');
    }
  };

  /** SNS 변환 버튼 클릭 시 실행되는 함수 */
  const handleSNSConvert = (draft) => {
    setSnsPost(draft);
    setSnsModalOpen(true);
  };

  /** 초안 저장 버튼 클릭 시 실행되는 함수 */
  const handleSave = async (draft) => {
    try {
      console.log('💾 저장 시작:', draft.title);
      const result = await save(draft);
      console.log('💾 저장 결과:', result);

      // 저장 API 결과에 따라 스낵바를 띄움
      if (result.success) {
        showNotification(result.message || '원고가 저장되었습니다.', 'success');
      } else {
        showNotification(result.error || '저장에 실패했습니다.', 'error');
      }
    } catch (error) {
      console.error('💾 저장 핸들러 오류:', error);
      showNotification('저장 처리 중 오류가 발생했습니다.', 'error');
    }
  };


  // '생성하기' 버튼을 활성화할지 최종적으로 결정하는 변수
  // 세션 기반 로직: 첫 생성이거나 재생성 가능한 경우만 활성화
  const finalCanGenerate = canGenerate && (sessionAttempts === 0 || canRegenerate) && !loading;

  // --- 🖥️ 화면 렌더링 ---
  return (
    <DashboardLayout>
      <Container maxWidth="xl" sx={{ py: `${spacing.xl}px` }}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
        >
          <Box sx={{ mb: `${spacing.xl}px` }}>
            <Typography variant="h4" sx={{
              fontWeight: 'bold',
              mb: `${spacing.xs}px`,
              color: theme.palette.mode === 'dark' ? 'white' : 'black',
              display: 'flex',
              alignItems: 'center',
              gap: `${spacing.xs}px`
            }}>
              <Create sx={{ color: theme.palette.mode === 'dark' ? 'white' : 'black' }} />
              새 원고 생성
            </Typography>
          </Box>
        </motion.div>

        {/* API 에러가 있을 경우, 화면 상단에 에러 메시지를 보여줌 */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
          >
            <Alert severity="error" sx={{ mb: `${spacing.md}px` }}>
              {error}
            </Alert>
          </motion.div>
        )}

        {/* 입력 폼 컴포넌트 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.3 }}
        >
          {/* 🆕 고품질 모드 토글 (PromptForm 위에 배치) */}
          {canUseBetaFeatures && (
            <Box sx={{
              mb: 2,
              p: 2,
              bgcolor: theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.05)' : 'rgba(0, 0, 0, 0.02)',
              borderRadius: 2,
              border: `1px solid ${theme.palette.divider}`
            }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={useHighQuality}
                      onChange={(e) => setUseHighQuality(e.target.checked)}
                      color="secondary"
                    />
                  }
                  label={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography fontWeight="bold">💎 고품질 모드 (Chain Writer)</Typography>
                      <Chip label="BETA" size="small" color="secondary" sx={{ height: 20, fontSize: '0.7rem' }} />
                    </Box>
                  }
                />
                {useHighQuality && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: { xs: 'none', sm: 'block' } }}>
                    ⚠️ 생성 시간이 2~3배 더 소요됩니다
                  </Typography>
                )}
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1, ml: 4 }}>
                단계별 생성(CoT) 기술을 적용하여 글의 구조와 핵심 내용 반영도를 극대화합니다. (관리자/테스터 전용)
              </Typography>
            </Box>
          )}

          <PromptForm
            formData={formData}
            onChange={updateForm} // 폼 데이터가 변경될 때 호출될 함수
            disabled={loading}     // 로딩 중일 때는 입력 비활성화
            categories={CATEGORIES}
            isMobile={isMobile}
            user={user}            // 사용자 정보 전달 (검색어 추천에 필요)
          />
        </motion.div>

        {/* 생성/초기화 버튼 컴포넌트 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.4 }}
        >
          <GenerateActions
            onGenerate={handleGenerate}
            onReset={handleReset}
            loading={loading}
            canGenerate={finalCanGenerate}
            attempts={attempts}
            maxAttempts={maxAttempts}
            drafts={drafts}
            progress={progress}
            isMobile={isMobile}
            sessionAttempts={sessionAttempts}
            maxSessionAttempts={maxSessionAttempts}
            canRegenerate={canRegenerate}
          />
        </motion.div>

        {/* 초안 그리드 (Lazy Loading 적용) */}
        <Suspense fallback={
          // 로딩 중일 때 보여줄 UI (스켈레톤)
          <Box sx={{ py: `${spacing.md}px` }}>
            <Skeleton variant="text" width={200} height={32} sx={{ mb: `${spacing.md}px` }} />
            <Box sx={{ display: 'grid', gap: `${spacing.md}px`, gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: '1fr 1fr 1fr' } }}>
              <Skeleton variant="rectangular" height={300} />
              <Skeleton variant="rectangular" height={300} />
              <Skeleton variant="rectangular" height={300} />
            </Box>
          </Box>
        }>
          <DraftGrid
            items={drafts}
            onSelect={setSelectedDraft} // 항상 자세히 보기 모달 활성화
            onSave={handleSave}         // 초안 저장 시 호출될 함수
            maxAttempts={maxAttempts}
            isMobile={isMobile}
            user={user}                 // 🆕 관리자/테스터 메타데이터 표시용
          />
        </Suspense>

        {/* 미리보기 다이얼로그 (팝업) */}
        <Dialog
          open={!!selectedDraft}
          onClose={() => setSelectedDraft(null)}
          fullWidth
          maxWidth="md"
          aria-labelledby="preview-dialog-title"
        >
          <DialogTitle
            id="preview-dialog-title"
            sx={{
              backgroundColor: theme.palette.mode === 'dark' ? '#1e1e1e' : '#2c3e50',
              color: '#ffffff !important',
              '& .MuiTypography-root': {
                color: '#ffffff !important'
              }
            }}
          >
            원고 미리보기
            <IconButton
              aria-label="close"
              onClick={() => setSelectedDraft(null)}
              sx={{
                position: 'absolute',
                right: 8,
                top: 8,
                color: '#ffffff',
              }}
            >
              <CloseIcon />
            </IconButton>
          </DialogTitle>
          <DialogContent dividers>
            {selectedDraft && (
              <Suspense fallback={
                <Box>
                  <Skeleton variant="text" width={150} height={32} sx={{ mb: `${spacing.md}px` }} />
                  <Skeleton variant="rectangular" height={400} />
                </Box>
              }>
                <PreviewPane draft={selectedDraft} />
              </Suspense>
            )}
          </DialogContent>
          <DialogActions sx={{ p: `${spacing.md}px`, gap: `${spacing.xs}px`, justifyContent: 'space-between' }}>
            <Box>
              {/* SNS 변환은 저장된 원고에만 표시 */}
              {snsUsage?.isActive && selectedDraft?.saved && (
                <Button
                  variant="outlined"
                  startIcon={<ShareIcon />}
                  onClick={() => handleSNSConvert(selectedDraft)}
                  sx={{ mr: `${spacing.xs}px` }}
                >
                  SNS 변환
                </Button>
              )}
            </Box>
            <Box sx={{ display: 'flex', gap: `${spacing.xs}px` }}>
              <Button onClick={() => setSelectedDraft(null)}>
                취소
              </Button>
              <Button
                variant="contained"
                onClick={() => handleConfirmSelection(selectedDraft)}
                color="primary"
              >
                이 원고 저장
              </Button>
            </Box>
          </DialogActions>
        </Dialog>
      </Container>

      {/* 알림 메시지를 보여주는 스낵바 컴포넌트 */}
      <NotificationSnackbar
        open={notification.open}
        onClose={hideNotification}
        message={notification.message}
        severity={notification.severity}
        autoHideDuration={6000}
      />

      {/* SNS 변환 모달 */}
      <SNSConversionModal
        open={snsModalOpen}
        onClose={() => setSnsModalOpen(false)}
        post={snsPost}
      />

      {/* 🔄 전체 로딩 오버레이 (텍스트 순환 적용) */}
      <LoadingOverlayWithRotatingText loading={loading} progress={progress} />

    </DashboardLayout>
  );
};

export default GeneratePage;