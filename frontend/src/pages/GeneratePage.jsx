// frontend/src/pages/GeneratePage.jsx

// React 및 UI 라이브러리에서 필요한 기능들을 가져옵니다.
import React, { Suspense, useEffect, useCallback } from 'react';
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
  Typography
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
  const { formData, updateForm, resetForm, validateForm, canGenerate } = useGenerateForm();
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

  /** 원고 생성 버튼 클릭 시 실행되는 함수 */
  const handleGenerate = async () => {
    // 1. 폼 데이터 유효성 검사 (예: 주제가 비어있는지)
    const validation = validateForm();
    if (!validation.isValid) {
      // 유효하지 않으면 에러 스낵바를 띄움
      showNotification(validation.error, 'error');
      return;
    }

    // 2. 유효하면 API 호출
    const result = await generate(formData);

    // 3. API 결과에 따라 성공 또는 실패 스낵바를 띄움
    if (result.success) {
      // 원고 생성 성공 시 검수 안내 메시지 추가
      const successMessage = result.message + '\n\n💡 생성된 원고를 꼭 검수하시고, 필요에 따라 직위나 내용을 직접 편집해주세요.';
      showNotification(successMessage, 'success');
    } else {
      showNotification(result.error, 'error');
    }
  };

  /** 초기화 버튼 클릭 시 실행되는 함수 */
  const handleReset = () => {
    resetForm();        // 폼 데이터 초기화
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
  const finalCanGenerate = canGenerate && attempts < maxAttempts && !loading;

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

    </DashboardLayout>
  );
};

export default GeneratePage;