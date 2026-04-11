import React, { useState, useMemo, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Box,
  Container,
  Button,
  IconButton,
  Alert,
  LinearProgress,
  Typography,
} from '@mui/material';
import { ArrowBackIosNew } from '@mui/icons-material';
import { motion, AnimatePresence } from 'framer-motion';

const IOS_EASE = [0.32, 0.72, 0, 1];
const MotionBox = motion(Box);
import { useAuth } from '../../hooks/useAuth';
import { hasAdminAccess } from '../../utils/authz';
import {
  useOnboardingFlow,
  validateRegion,
} from './hooks/useOnboardingFlow';
import { isOnboardingComplete } from '../../components/OnboardingGuard';
import WelcomeStep from './steps/WelcomeStep';
import StatusStep from './steps/StatusStep';
import RoleStep from './steps/RoleStep';
import RegionStep from './steps/RegionStep';
import PersonalizationStep from './steps/PersonalizationStep';
import CompleteStep from './steps/CompleteStep';

const APPLE_BLUE = '#007AFF';

const OnboardingPage = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user, loading: authLoading } = useAuth();

  const isAdmin = useMemo(() => hasAdminAccess(user), [user]);
  const isPreview = isAdmin && searchParams.get('preview') === '1';

  const {
    data,
    loading,
    saving,
    error,
    setError,
    updateField,
    savePartial,
  } = useOnboardingFlow({ preview: isPreview });

  const [activeStep, setActiveStep] = useState(0);
  const [stepError, setStepError] = useState('');
  const directionRef = useRef(1);

  const userName = user?.displayName || user?.name;

  const isPreparing = data.status === '준비';

  const STEPS = useMemo(() => [
    {
      key: 'welcome',
      title: userName ? `안녕하세요,\n${userName}님` : '안녕하세요',
      subtitle: '전뇌비서관을 시작해 볼까요?',
      align: 'center',
    },
    {
      key: 'status',
      title: '현재 어떤\n상태이신가요?',
      subtitle: '이 답에 따라 다음 질문이 달라집니다.',
      align: 'left',
    },
    {
      key: 'role',
      title: isPreparing ? '어떤 자리에\n도전하시나요?' : '어떤 자리에\n해당하시나요?',
      subtitle: isPreparing
        ? '다음 선거에서 도전하려는 자리를 선택해주세요.'
        : '현재 또는 출마 중인 자리를 선택해주세요.',
      align: 'left',
    },
    {
      key: 'region',
      title: isPreparing ? '출마하실 지역은\n어디인가요?' : '활동 지역을\n알려주세요',
      subtitle: isPreparing
        ? '목표 선거의 지역을 선택해주세요.'
        : '지역 정보가 원고의 맥락에 반영됩니다.',
      align: 'left',
    },
    {
      key: 'personalization',
      title: '조금 더\n알려주시겠어요?',
      subtitle: '원고의 결을 더 정확히 잡기 위한 선택 정보예요. 건너뛰어도 괜찮습니다.',
      align: 'left',
    },
    {
      key: 'complete',
      title: '준비가\n끝났습니다',
      subtitle: '이제 프로필에서 자기소개만 작성하면 됩니다.',
      align: 'center',
    },
  ], [userName, isPreparing]);

  if (!authLoading && user && !isPreview && (isAdmin || isOnboardingComplete(user))) {
    navigate('/dashboard', { replace: true });
    return null;
  }

  const stepKey = STEPS[activeStep].key;

  const canProceed =
    stepKey === 'status' ? !!data.status
    : stepKey === 'role' ? !!data.position
    : stepKey === 'region' ? !validateRegion(data)
    : true;

  const handleNext = async () => {
    setStepError('');
    setError('');

    if (stepKey === 'status') {
      if (!data.status) {
        setStepError('현재 상태를 선택해주세요.');
        return;
      }
      const ok = await savePartial({ status: data.status });
      if (!ok) return;
    } else if (stepKey === 'role') {
      if (!data.position) {
        setStepError('직책을 선택해주세요.');
        return;
      }
      const ok = await savePartial({ position: data.position });
      if (!ok) return;
    } else if (stepKey === 'region') {
      const err = validateRegion(data);
      if (err) {
        setStepError(err);
        return;
      }
      const ok = await savePartial({
        regionMetro: data.regionMetro,
        regionLocal: data.regionLocal || '',
        electoralDistrict: data.electoralDistrict || '',
      });
      if (!ok) return;
    } else if (stepKey === 'personalization') {
      const ok = await savePartial({
        ageDecade: data.ageDecade || '',
        ageDetail: data.ageDetail || '',
        gender: data.gender || '',
        familyStatus: data.familyStatus || '',
        backgroundCareer: data.backgroundCareer || '',
        localConnection: data.localConnection || '',
        politicalExperience: data.politicalExperience || '',
      });
      if (!ok) return;
    }

    directionRef.current = 1;
    setActiveStep((s) => Math.min(s + 1, STEPS.length - 1));
  };

  const handleBack = () => {
    setStepError('');
    setError('');
    directionRef.current = -1;
    setActiveStep((s) => Math.max(s - 1, 0));
  };

  const handleFinish = () => {
    navigate(isPreview ? '/admin' : '/profile?welcome=1', { replace: true });
  };

  const renderStep = () => {
    switch (stepKey) {
      case 'welcome':
        return <WelcomeStep />;
      case 'status':
        return (
          <StatusStep
            value={data.status}
            onChange={(value) => updateField('status', value)}
          />
        );
      case 'role':
        return (
          <RoleStep
            value={data.position}
            onChange={(value) => updateField('position', value)}
          />
        );
      case 'region':
        return <RegionStep data={data} onChange={updateField} />;
      case 'personalization':
        return <PersonalizationStep data={data} onChange={updateField} />;
      case 'complete':
        return <CompleteStep data={data} isPreview={isPreview} />;
      default:
        return null;
    }
  };

  if (authLoading || loading) {
    return (
      <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Box sx={{ width: 200 }}>
          <LinearProgress sx={{ height: 2, borderRadius: 1 }} />
        </Box>
      </Box>
    );
  }

  const isLastStep = activeStep === STEPS.length - 1;
  const currentStep = STEPS[activeStep];
  const isCentered = currentStep.align === 'center';

  const hasAnyPersonalization =
    !!data.ageDecade ||
    !!data.gender ||
    !!data.familyStatus ||
    !!data.backgroundCareer ||
    !!data.localConnection ||
    !!data.politicalExperience;

  const ctaLabel = saving
    ? '저장 중'
    : isLastStep
      ? (isPreview ? '관리자 페이지로' : '프로필로 이동')
      : stepKey === 'personalization' && !hasAnyPersonalization
        ? '건너뛰기'
        : '계속';

  return (
    <Box
      sx={{
        minHeight: '100vh',
        bgcolor: 'background.default',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Box
        sx={{
          height: 56,
          display: 'flex',
          alignItems: 'center',
          px: { xs: 1, md: 2 },
          flexShrink: 0,
        }}
      >
        {activeStep > 0 && (
          <IconButton
            onClick={handleBack}
            disabled={saving}
            disableRipple
            sx={{
              color: APPLE_BLUE,
              borderRadius: 2,
              px: 1.5,
              '&:hover': { bgcolor: 'transparent', opacity: 0.6 },
              '&.Mui-disabled': { color: 'text.disabled' },
            }}
          >
            <ArrowBackIosNew sx={{ fontSize: 17, mr: 0.5 }} />
            <Typography sx={{ fontSize: '1.0625rem', fontWeight: 400, color: 'inherit' }}>
              뒤로
            </Typography>
          </IconButton>
        )}
      </Box>

      <Box
        component="main"
        sx={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          px: { xs: 3, md: 4 },
          pb: 2,
        }}
      >
        <Container
          maxWidth="sm"
          disableGutters
          sx={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            textAlign: isCentered ? 'center' : 'left',
          }}
        >
          <Box sx={{ flex: '0 1 12vh', minHeight: { xs: 24, md: 48 } }} />
          {isPreview && (
            <Alert
              severity="info"
              sx={{
                mb: 4,
                borderRadius: 2,
                border: 'none',
                bgcolor: 'action.hover',
                color: 'text.secondary',
                textAlign: 'left',
                '& .MuiAlert-icon': { color: 'text.secondary' },
              }}
            >
              관리자 미리보기 모드입니다. 입력값은 저장되지 않습니다.
            </Alert>
          )}

          <Box
            sx={{
              flex: 1,
              position: 'relative',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
            }}
          >
            <AnimatePresence mode="wait" custom={directionRef.current} initial={false}>
              <MotionBox
                key={stepKey}
                custom={directionRef.current}
                variants={{
                  enter: (dir) => ({ x: dir * 48, opacity: 0 }),
                  center: { x: 0, opacity: 1 },
                  exit: (dir) => ({ x: dir * -48, opacity: 0 }),
                }}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{
                  x: { duration: 0.45, ease: IOS_EASE },
                  opacity: { duration: 0.3, ease: IOS_EASE },
                }}
                sx={{
                  position: 'absolute',
                  inset: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  textAlign: isCentered ? 'center' : 'left',
                }}
              >
                <Typography
                  sx={{
                    fontWeight: 700,
                    letterSpacing: '-0.03em',
                    fontSize: { xs: '2.25rem', md: '2.75rem' },
                    lineHeight: 1.1,
                    mb: 2,
                    whiteSpace: 'pre-line',
                  }}
                >
                  {currentStep.title}
                </Typography>

                <Typography
                  sx={{
                    color: 'text.secondary',
                    fontSize: { xs: '1rem', md: '1.0625rem' },
                    lineHeight: 1.5,
                    mb: { xs: 5, md: 7 },
                  }}
                >
                  {currentStep.subtitle}
                </Typography>

                <Box sx={{ flex: 1, textAlign: 'left', overflowY: 'auto' }}>
                  {renderStep()}
                </Box>
              </MotionBox>
            </AnimatePresence>
          </Box>

          {(stepError || error) && (
            <Alert
              severity="error"
              sx={{
                mt: 3,
                borderRadius: 2,
                border: 'none',
                bgcolor: 'error.light',
                color: 'error.dark',
                textAlign: 'left',
              }}
            >
              {stepError || error}
            </Alert>
          )}
        </Container>
      </Box>

      <Box
        sx={{
          px: { xs: 3, md: 4 },
          pb: { xs: 4, md: 5 },
          pt: 2,
          flexShrink: 0,
        }}
      >
        <Container maxWidth="sm" disableGutters>
          <motion.div
            whileTap={saving || !canProceed ? {} : { scale: 0.97 }}
            transition={{ duration: 0.15, ease: IOS_EASE }}
          >
            <Button
              fullWidth
              onClick={isLastStep ? handleFinish : handleNext}
              disabled={saving || !canProceed}
              disableElevation
              sx={{
                bgcolor: APPLE_BLUE,
                color: '#fff',
                fontWeight: 600,
                fontSize: '1.0625rem',
                textTransform: 'none',
                borderRadius: '14px',
                py: 1.75,
                letterSpacing: '-0.01em',
                boxShadow: 'none',
                transition: 'background-color 200ms ease, opacity 200ms ease',
                '&:hover': { bgcolor: APPLE_BLUE, opacity: 0.88, boxShadow: 'none' },
                '&.Mui-disabled': {
                  bgcolor: 'rgba(0, 122, 255, 0.35)',
                  color: '#fff',
                },
              }}
            >
              <motion.span
                key={ctaLabel}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, ease: IOS_EASE }}
              >
                {ctaLabel}
              </motion.span>
            </Button>
          </motion.div>

          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 1.5, minHeight: 36 }}>
            {activeStep > 0 && (
              <Button
                onClick={handleBack}
                disabled={saving}
                disableRipple
                sx={{
                  color: APPLE_BLUE,
                  fontWeight: 400,
                  fontSize: '0.9375rem',
                  textTransform: 'none',
                  '&:hover': { bgcolor: 'transparent', opacity: 0.65 },
                  '&.Mui-disabled': { color: 'text.disabled' },
                }}
              >
                이전 단계로
              </Button>
            )}
          </Box>

          <Typography
            sx={{
              textAlign: 'center',
              fontSize: '0.8125rem',
              color: 'text.disabled',
              mt: 1,
              letterSpacing: '-0.005em',
            }}
          >
            여기에서 입력한 내용은 나중에 프로필에서 언제든 수정할 수 있습니다.
          </Typography>
        </Container>
      </Box>
    </Box>
  );
};

export default OnboardingPage;
