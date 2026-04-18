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
  Backdrop,         // 🆕 추가
  CircularProgress, // 🆕 추가
  LinearProgress,   // 결정형 진행 표시
  Stepper,
  Step,
  StepLabel
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
// TODO: 단계 전환 시 읽을거리(검색어 노하우, 원고 작성 팁 등) 정보 카드 추가 — 200자 내외, 단계마다 교체
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

  const activeStep = progress?.step ?? 0;
  const progressValue = progress?.progress ?? 0;
  const STEP_LABELS = ['구조설계', '본문', 'SEO'];

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
      {/* 단계형 Stepper */}
      <Stepper
        activeStep={activeStep}
        alternativeLabel
        sx={{
          width: '80%',
          maxWidth: 400,
          '& .MuiStepLabel-label': {
            color: 'rgba(255, 255, 255, 0.5)',
            fontSize: '0.75rem',
            '&.Mui-active': { color: '#fff' },
            '&.Mui-completed': { color: 'rgba(255, 255, 255, 0.8)' }
          },
          '& .MuiStepIcon-root': {
            color: 'rgba(255, 255, 255, 0.3)',
            '&.Mui-active': { color: '#fff' },
            '&.Mui-completed': { color: 'rgba(255, 255, 255, 0.8)' }
          },
          '& .MuiStepConnector-line': {
            borderColor: 'rgba(255, 255, 255, 0.3)'
          },
          '& .MuiStepConnector-root.Mui-completed .MuiStepConnector-line': {
            borderColor: 'rgba(255, 255, 255, 0.8)'
          },
          '& .MuiStepConnector-root.Mui-active .MuiStepConnector-line': {
            borderColor: 'rgba(255, 255, 255, 0.8)'
          }
        }}
      >
        {STEP_LABELS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {/* 결정형 프로그레스 바 + 퍼센트 */}
      <Box sx={{ width: '80%', maxWidth: 400, mt: 1 }}>
        <LinearProgress
          variant="determinate"
          value={progressValue}
          role="progressbar"
          aria-valuenow={Math.round(progressValue)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`원고 생성 진행률 ${Math.round(progressValue)}%`}
          sx={{
            height: 6,
            borderRadius: 3,
            backgroundColor: 'rgba(255, 255, 255, 0.15)',
            '& .MuiLinearProgress-bar': {
              borderRadius: 3,
              backgroundColor: '#fff',
              transition: 'transform 0.6s ease'
            }
          }}
        />
        <Typography variant="body2" align="right" color="rgba(255, 255, 255, 0.7)" sx={{ mt: 0.5 }}>
          {Math.round(progressValue)}%
        </Typography>
      </Box>

      {/* 순환 서브 메시지 */}
      <Typography
        variant="body2"
        align="center"
        sx={{
          color: 'rgba(255, 255, 255, 0.7)',
          minHeight: '1.5em'
        }}
      >
        {displayMessage}
      </Typography>

      <Typography variant="caption" color="rgba(255, 255, 255, 0.5)" sx={{ mt: 1 }}>
        보통 2~5분 소요, 상황에 따라 더 걸릴 수 있습니다
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
  const { formData, updateForm, resetForm, validateForm, canGenerate, clearPersistedForm } = useGenerateForm(user);
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

  // 사용자 프로필 새로고침 (최신 구독/한도 정보 가져오기)
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
  const [formErrors, setFormErrors] = React.useState({ topic: '', instructions0: '' });

  // --- 추모/애도 확인 다이얼로그 ---
  const [memorialConfirmOpen, setMemorialConfirmOpen] = React.useState(false);
  const [pendingPayload, setPendingPayload] = React.useState(null);

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


  const [electionViolations, setElectionViolations] = React.useState(null);

  const handleFormChange = useCallback((updates) => {
    // 선거법 위반 상태는 폼 데이터가 아니므로 분리 저장
    if (Object.prototype.hasOwnProperty.call(updates, '_electionViolations')) {
      setElectionViolations(updates._electionViolations);
      const { _electionViolations, ...rest } = updates;
      if (Object.keys(rest).length > 0) updateForm(rest);
    } else {
      updateForm(updates);
    }
    setFormErrors((prev) => {
      let next = prev;
      if (Object.prototype.hasOwnProperty.call(updates, 'topic') && prev.topic) {
        if (next === prev) next = { ...prev };
        next.topic = '';
      }
      if (Object.prototype.hasOwnProperty.call(updates, 'instructions') && prev.instructions0) {
        if (next === prev) next = { ...prev };
        next.instructions0 = '';
      }
      return next;
    });
  }, [updateForm]);

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

    // 0. 선거법 금지 표현 사전 차단
    if (electionViolations && electionViolations.length > 0) {
      const matched = electionViolations.map((v) => `"${v.matched}"`).join(', ');
      showNotification(`선거법상 사용할 수 없는 표현이 포함되어 있습니다: ${matched}`, 'error');
      return;
    }

    // 0.5. 추모/애도 메시지 감지 — 확인 다이얼로그로 분기
    const memorialPattern = /추모|애도|추도|조문|영결|분향|희생자|유가족|명복|안식|세월호|이태원|참사/;
    const textToCheck = `${formData.topic || ''} ${formData.stanceText || ''} ${(formData.instructions || []).join(' ')}`;
    if (memorialPattern.test(textToCheck)) {
      const payload = { ...formData };
      setPendingPayload(payload);
      setMemorialConfirmOpen(true);
      return;
    }

    // 1. 폼 데이터 유효성 검사
    const validation = validateForm();
    if (!validation.isValid) {
      const nextErrors = { topic: '', instructions0: '' };
      if (validation.field === 'topic') {
        nextErrors.topic = validation.error;
      } else if (validation.field === 'instructions0') {
        nextErrors.instructions0 = validation.error;
      }
      setFormErrors(nextErrors);
      showNotification(validation.error, 'error');

      const targetName = validation.field === 'topic'
        ? 'topic'
        : (validation.field === 'instructions0' ? 'instructions_0' : null);

      if (targetName) {
        requestAnimationFrame(() => {
          const target = document.querySelector(`[name="${targetName}"]`);
          if (target) {
            target.focus();
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
        });
      }
      return;
    }
    setFormErrors({ topic: '', instructions0: '' });

    // 2. 알림 권한 요청 (아직 결정 안 된 경우에만)
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }

    // 3. 유효하면 API 호출
    const payload = {
      ...formData
    };

    const result = await generate(payload);

    // 4. API 결과 처리 + 브라우저 알림
    if (result.success) {
      const successMessage = result.message + '\n\n💡 생성된 원고를 꼭 검수하시고, 필요에 따라 직위나 내용을 직접 편집해주세요.';
      showNotification(successMessage, 'success');
      if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
        new Notification('원고 생성 완료', { body: 'AI 원고가 성공적으로 생성되었습니다. 확인해 주세요.' });
      }
    } else {
      showNotification(result.error, 'error');
      if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
        new Notification('원고 생성 실패', { body: '오류가 발생했습니다. 다시 시도해 주세요.' });
      }
    }
  };

  /** 추모/애도 확인 다이얼로그 — 사용자가 "변환하기"를 선택한 경우 */
  const handleMemorialConfirm = async () => {
    setMemorialConfirmOpen(false);
    if (!pendingPayload) return;
    const result = await generate(pendingPayload);
    setPendingPayload(null);
    if (result.success) {
      const successMessage = result.message + '\n\n생성된 원고를 꼭 검수하시고, 필요에 따라 직접 편집해주세요.';
      showNotification(successMessage, 'success');
      if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
        new Notification('원고 생성 완료', { body: 'AI 원고가 성공적으로 생성되었습니다. 확인해 주세요.' });
      }
    } else {
      showNotification(result.error, 'error');
      if ('Notification' in window && Notification.permission === 'granted' && document.hidden) {
        new Notification('원고 생성 실패', { body: '오류가 발생했습니다. 다시 시도해 주세요.' });
      }
    }
  };

  /** 추모/애도 확인 다이얼로그 — 사용자가 "취소"를 선택한 경우 */
  const handleMemorialCancel = () => {
    setMemorialConfirmOpen(false);
    setPendingPayload(null);
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
        // 최종 선택 완료 → 브라우저에 임시 보관하던 폼 입력값은 이제 비운다.
        clearPersistedForm();
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
        // 최종 선택 완료 → 브라우저에 임시 보관하던 폼 입력값 제거
        clearPersistedForm();
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


          <PromptForm
            formData={formData}
            onChange={handleFormChange} // 폼 데이터가 변경될 때 호출될 함수
            disabled={loading}     // 로딩 중일 때는 입력 비활성화
            categories={CATEGORIES}
            isMobile={isMobile}
            user={user}            // 사용자 정보 전달 (검색어 추천에 필요)
            errors={formErrors}
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
              <Button onClick={() => setSelectedDraft(null)} sx={{ color: (theme) => theme.palette.mode === 'dark' ? '#ffffff' : undefined }}>
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

      {/* 추모/애도 확인 다이얼로그 */}
      <Dialog
        open={memorialConfirmOpen}
        onClose={handleMemorialCancel}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle sx={{ fontWeight: 'bold' }}>
          잠깐, 한 번 더 생각해 주세요
        </DialogTitle>
        <DialogContent>
          <Typography sx={{ lineHeight: 1.8 }}>
            때로는 서투르더라도 마음을 담은 진솔한 메시지가 더 필요한 순간이 있습니다.
            지금 입력하신 글을 그대로 블로그와 SNS에 올리셔도 좋습니다.
          </Typography>
          <Typography sx={{ mt: 2, fontWeight: 'bold' }}>
            정말 AI로 변환하시겠습니까?
          </Typography>
        </DialogContent>
        <DialogActions sx={{ p: 2 }}>
          <Button onClick={handleMemorialCancel} variant="contained" color="primary">
            아니요, 직접 쓰겠습니다
          </Button>
          <Button onClick={handleMemorialConfirm} color="inherit">
            변환하기
          </Button>
        </DialogActions>
      </Dialog>

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

