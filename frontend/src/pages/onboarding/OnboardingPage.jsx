import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Container,
  Paper,
  Stepper,
  Step,
  StepLabel,
  Button,
  Alert,
  LinearProgress,
  Typography,
} from '@mui/material';
import { useAuth } from '../../hooks/useAuth';
import { hasAdminAccess } from '../../utils/authz';
import {
  useOnboardingFlow,
  validateRegion,
  validateBio,
  MIN_BIO_LENGTH,
} from './hooks/useOnboardingFlow';
import { isOnboardingComplete } from '../../components/OnboardingGuard';
import WelcomeStep from './steps/WelcomeStep';
import RoleStep from './steps/RoleStep';
import RegionStep from './steps/RegionStep';
import BioStep from './steps/BioStep';
import CompleteStep from './steps/CompleteStep';

const STEPS = [
  { key: 'welcome', label: '환영' },
  { key: 'role', label: '직책' },
  { key: 'region', label: '선거구' },
  { key: 'bio', label: '자기소개' },
  { key: 'complete', label: '완료' },
];

const OnboardingPage = () => {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const {
    data,
    loading,
    saving,
    error,
    setError,
    updateField,
    savePartial,
  } = useOnboardingFlow();

  const [activeStep, setActiveStep] = useState(0);
  const [stepError, setStepError] = useState('');

  const isAdmin = useMemo(() => hasAdminAccess(user), [user]);

  // 관리자 또는 이미 완료된 사용자는 대시보드로
  if (!authLoading && user && (isAdmin || isOnboardingComplete(user))) {
    navigate('/dashboard', { replace: true });
    return null;
  }

  const stepKey = STEPS[activeStep].key;

  const handleNext = async () => {
    setStepError('');
    setError('');

    if (stepKey === 'role') {
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
    } else if (stepKey === 'bio') {
      const err = validateBio(data.bio);
      if (err) {
        setStepError(err);
        return;
      }
      const ok = await savePartial({ bio: data.bio });
      if (!ok) return;
    }

    setActiveStep((s) => Math.min(s + 1, STEPS.length - 1));
  };

  const handleBack = () => {
    setStepError('');
    setError('');
    setActiveStep((s) => Math.max(s - 1, 0));
  };

  const handleFinish = () => {
    navigate('/dashboard', { replace: true });
  };

  const renderStep = () => {
    switch (stepKey) {
      case 'welcome':
        return <WelcomeStep userName={user?.displayName || user?.name} />;
      case 'role':
        return (
          <RoleStep
            value={data.position}
            onChange={(value) => updateField('position', value)}
          />
        );
      case 'region':
        return <RegionStep data={data} onChange={updateField} />;
      case 'bio':
        return (
          <BioStep
            value={data.bio}
            onChange={(value) => updateField('bio', value)}
          />
        );
      case 'complete':
        return <CompleteStep data={data} />;
      default:
        return null;
    }
  };

  if (authLoading || loading) {
    return (
      <Box sx={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Box sx={{ width: 320 }}>
          <Typography variant="body2" color="text.secondary" align="center" sx={{ mb: 1 }}>
            불러오는 중...
          </Typography>
          <LinearProgress />
        </Box>
      </Box>
    );
  }

  const isLastStep = activeStep === STEPS.length - 1;

  return (
    <Box
      sx={{
        minHeight: '100vh',
        bgcolor: 'background.default',
        py: { xs: 3, md: 6 },
        px: 2,
      }}
    >
      <Container maxWidth="sm">
        <Paper
          elevation={3}
          sx={{
            p: { xs: 3, md: 5 },
            borderRadius: 3,
          }}
        >
          <Stepper activeStep={activeStep} alternativeLabel sx={{ mb: 4 }}>
            {STEPS.map((step) => (
              <Step key={step.key}>
                <StepLabel>{step.label}</StepLabel>
              </Step>
            ))}
          </Stepper>

          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textAlign: 'right', mb: 2 }}>
            {activeStep + 1} / {STEPS.length} 단계
          </Typography>

          <Box sx={{ minHeight: 320 }}>
            {renderStep()}
          </Box>

          {(stepError || error) && (
            <Alert severity="error" sx={{ mt: 3 }}>
              {stepError || error}
            </Alert>
          )}

          <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 4 }}>
            <Button
              onClick={handleBack}
              disabled={activeStep === 0 || saving}
              variant="text"
            >
              이전
            </Button>

            {isLastStep ? (
              <Button
                onClick={handleFinish}
                variant="contained"
                color="primary"
                size="large"
              >
                대시보드로 이동
              </Button>
            ) : (
              <Button
                onClick={handleNext}
                variant="contained"
                color="primary"
                disabled={saving}
                size="large"
              >
                {saving ? '저장 중...' : '다음'}
              </Button>
            )}
          </Box>

          {stepKey === 'bio' && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', textAlign: 'center', mt: 2 }}>
              최소 {MIN_BIO_LENGTH}자 이상 입력해야 다음 단계로 넘어갈 수 있습니다.
            </Typography>
          )}
        </Paper>
      </Container>
    </Box>
  );
};

export default OnboardingPage;
