// frontend/src/components/TossPayment.jsx
import React, { useEffect, useRef } from 'react';
import { Box, Button, Alert, Typography } from '@mui/material';
import { loadPaymentWidget, ANONYMOUS } from '@tosspayments/payment-widget-sdk';

const TossPayment = ({ 
  amount, 
  orderId, 
  orderName, 
  customerEmail, 
  customerName, 
  onSuccess, 
  onError 
}) => {
  const paymentWidgetRef = useRef(null);
  const paymentMethodsWidgetRef = useRef(null);
  const agreementsWidgetRef = useRef(null);

  // 토스페이먼츠 클라이언트 키 (환경변수에서 가져오기)
  const clientKey = import.meta.env.VITE_TOSS_CLIENT_KEY || 'test_ck_DnyRpQWGrNdJvP7ZLPx8VKwv1M9E';

  useEffect(() => {
    (async () => {
      try {
        // 결제위젯 초기화
        const paymentWidget = await loadPaymentWidget(clientKey, customerEmail || ANONYMOUS);
        
        // 결제 UI 렌더링
        const paymentMethodsWidget = paymentWidget.renderPaymentMethods(
          '#payment-methods',
          { value: amount },
          { variantKey: 'DEFAULT' }
        );
        
        // 이용약관 UI 렌더링 
        const agreementsWidget = paymentWidget.renderAgreements(
          '#agreements',
          { variantKey: 'AGREEMENT' }
        );

        paymentWidgetRef.current = paymentWidget;
        paymentMethodsWidgetRef.current = paymentMethodsWidget;
        agreementsWidgetRef.current = agreementsWidget;
      } catch (error) {
        console.error('토스페이먼츠 위젯 로딩 실패:', error);
        if (onError) onError(error);
      }
    })();
  }, [clientKey, customerEmail, amount]);

  const handlePayment = async () => {
    if (!paymentWidgetRef.current) return;

    try {
      // 결제 요청
      await paymentWidgetRef.current?.requestPayment({
        orderId,
        orderName,
        customerName,
        customerEmail,
        successUrl: `${window.location.origin}/payment/success`,
        failUrl: `${window.location.origin}/payment/fail`,
      });
    } catch (error) {
      console.error('결제 요청 실패:', error);
      if (onError) onError(error);
    }
  };

  return (
    <Box sx={{ width: '100%', maxWidth: 540, mx: 'auto' }}>
      {/* 결제 금액 표시 */}
      <Box sx={{ mb: 3, p: 2, bgcolor: 'grey.50', borderRadius: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 'bold', mb: 1 }}>
          결제 정보
        </Typography>
        <Typography variant="body1">
          상품명: {orderName}
        </Typography>
        <Typography variant="h5" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
          결제금액: {amount?.toLocaleString()}원
        </Typography>
        {customerName && (
          <Typography variant="body2" color="text.secondary">
            구매자: {customerName}
          </Typography>
        )}
      </Box>

      {/* 결제 수단 선택 */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="subtitle1" sx={{ mb: 1, fontWeight: 'bold' }}>
          결제 수단 선택
        </Typography>
        <div id="payment-methods" style={{ minHeight: '200px' }} />
      </Box>

      {/* 이용약관 */}
      <Box sx={{ mb: 3 }}>
        <div id="agreements" />
      </Box>

      {/* 결제 버튼 */}
      <Button
        variant="contained"
        size="large"
        fullWidth
        onClick={handlePayment}
        sx={{
          py: 2,
          fontSize: '1.1rem',
          fontWeight: 'bold',
          bgcolor: '#3182f6',
          '&:hover': {
            bgcolor: '#2563eb'
          }
        }}
      >
        결제하기
      </Button>

      {/* 주의사항 */}
      <Alert severity="info" sx={{ mt: 2 }}>
        <Typography variant="body2">
          • 결제 완료 후 즉시 서비스가 활성화됩니다.<br/>
          • 결제 내역은 '결제 내역' 메뉴에서 확인할 수 있습니다.<br/>
          • 환불 관련 문의는 고객센터로 연락해주세요.
        </Typography>
      </Alert>
    </Box>
  );
};

export default TossPayment;