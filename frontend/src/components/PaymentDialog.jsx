// frontend/src/components/PaymentDialog.jsx
import React, { useState } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
  Alert,
  IconButton,
  Stepper,
  Step,
  StepLabel
} from '@mui/material';
import { Close } from '@mui/icons-material';
import { useAuth } from '../hooks/useAuth';
import NaverPayment from './NaverPayment';
import { colors } from '../theme/tokens';

const PaymentDialog = ({ open, onClose, selectedPlan }) => {
  const { user } = useAuth();
  const [activeStep, setActiveStep] = useState(0);

  const steps = ['결제 정보 확인', '결제 수단 선택', '결제 완료'];

  // 주문 ID 생성 (유니크한 값)
  const generateOrderId = () => {
    const timestamp = Date.now();
    const random = Math.random().toString(36).substr(2, 9);
    return `order_${timestamp}_${random}`;
  };

  const orderId = generateOrderId();

  const handlePaymentError = (error) => {
    console.error('결제 오류:', error);
    // 에러 처리 로직
  };

  const handleNextStep = () => {
    setActiveStep((prevStep) => prevStep + 1);
  };

  const handleBackStep = () => {
    setActiveStep((prevStep) => prevStep - 1);
  };

  if (!selectedPlan) return null;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: { minHeight: '600px' }
      }}
    >
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
          {selectedPlan.name} 결제
        </Typography>
        <IconButton onClick={onClose} size="small">
          <Close />
        </IconButton>
      </DialogTitle>

      <DialogContent sx={{ px: 3, py: 2 }}>
        {/* 진행 단계 표시 */}
        <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
          {steps.map((label) => (
            <Step key={label}>
              <StepLabel>{label}</StepLabel>
            </Step>
          ))}
        </Stepper>

        {activeStep === 0 && (
          // 1단계: 결제 정보 확인
          <Box>
            <Alert severity="info" sx={{ mb: 3 }}>
              <Typography variant="body2">
                결제 정보를 확인해주세요. 결제 완료 즉시 서비스가 활성화됩니다.
              </Typography>
            </Alert>

            <Box sx={{ p: 3, bgcolor: 'grey.50', borderRadius: 2, mb: 3 }}>
              <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 2, color: selectedPlan.color || colors.brand.primary }}>
                {selectedPlan.name}
              </Typography>
              
              <Typography variant="h4" sx={{ fontWeight: 'bold', mb: 2 }}>
                {selectedPlan.price.toLocaleString()}원/월
              </Typography>

              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                VAT 포함 가격입니다
              </Typography>

              {selectedPlan.features && selectedPlan.features.length > 0 && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 'bold', mb: 1 }}>
                    포함 서비스:
                  </Typography>
                  {selectedPlan.features.map((feature, index) => (
                    <Typography key={index} variant="body2" sx={{ ml: 1, mb: 0.5 }}>
                      • {feature}
                    </Typography>
                  ))}
                </Box>
              )}

              <Typography variant="body2" color="text.secondary">
                구매자: {user?.displayName || user?.name || '사용자'}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                이메일: {user?.email}
              </Typography>
            </Box>

            <Alert severity="info" sx={{ mb: 2 }}>
              <Typography variant="body2">
                <strong>서비스 제공 방식</strong><br/>
                • 본 서비스는 월 단위 계약으로 매월 1일 자동 갱신됩니다<br/>
                • 원고 생성 횟수는 결제 완료 즉시 제공되어 바로 이용 가능합니다<br/>
                • 월간 서비스로 언제든 해지 가능합니다
              </Typography>
            </Alert>
            
            <Alert severity="warning" sx={{ mb: 2 }}>
              <Typography variant="body2">
                <strong>환불 정책</strong><br/>
                • 구매일로부터 7일 이내: 전액 환불 가능<br/>
                • 원고 생성 이용 후: 미사용 횟수만큼 일할 계산하여 환불<br/>
                • 환불 요청 시 7영업일 이내 처리 완료
              </Typography>
            </Alert>
          </Box>
        )}

        {activeStep === 1 && (
          // 2단계: 네이버페이 결제
          <Box>
            <NaverPayment
              amount={selectedPlan.price}
              orderId={orderId}
              orderName={`전자두뇌비서관 - ${selectedPlan.name} (1개월)`}
              customerEmail={user?.email}
              customerName={user?.displayName || user?.name}
              onError={handlePaymentError}
            />
          </Box>
        )}

        {activeStep === 2 && (
          // 3단계: 결제 완료 (실제로는 성공 페이지로 리다이렉트됨)
          <Box sx={{ textAlign: 'center', py: 4 }}>
            <Typography variant="h5" sx={{ mb: 2 }}>
              결제가 완료되었습니다!
            </Typography>
            <Typography variant="body1" color="text.secondary">
              결제 완료 페이지로 이동합니다...
            </Typography>
          </Box>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 3 }}>
        {activeStep === 0 && (
          <>
            <Button onClick={onClose} size="large">
              취소
            </Button>
            <Button
              variant="contained"
              onClick={handleNextStep}
              size="large"
              sx={{ bgcolor: selectedPlan.color || colors.brand.primary }}
            >
              결제하기
            </Button>
          </>
        )}
        
        {activeStep === 1 && (
          <Button
            onClick={handleBackStep}
            size="large"
          >
            이전 단계
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default PaymentDialog;