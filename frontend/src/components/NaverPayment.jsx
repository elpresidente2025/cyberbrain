// frontend/src/components/NaverPayment.jsx
import React, { useState } from 'react';
import { Box, Button, Alert, Typography, CircularProgress } from '@mui/material';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../services/firebase';

const NaverPayment = ({
  amount,
  orderId,
  orderName,
  customerEmail,
  customerName,
  onError
}) => {
  const [loading, setLoading] = useState(false);

  const handlePayment = async () => {
    setLoading(true);

    try {
      // Firebase Function을 통해 네이버페이 결제 요청
      const initiateNaverPayment = httpsCallable(functions, 'initiateNaverPayment');

      const result = await initiateNaverPayment({
        amount,
        orderId,
        orderName,
        customerEmail,
        customerName,
        successUrl: `${window.location.origin}/payment/success`,
        failUrl: `${window.location.origin}/payment/fail`,
      });

      if (result.data.success && result.data.paymentUrl) {
        // 네이버페이 결제 페이지로 리다이렉트
        window.location.href = result.data.paymentUrl;
      } else {
        throw new Error(result.data.message || '결제 요청에 실패했습니다.');
      }
    } catch (error) {
      console.error('네이버페이 결제 요청 실패:', error);
      setLoading(false);
      if (onError) onError(error);
    }
  };

  return (
    <Box sx={{ width: '100%', maxWidth: 540, mx: 'auto' }}>
      {/* 결제 금액 표시 */}
      <Box sx={{ mb: 3, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
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

      {/* 네이버페이 안내 */}
      <Alert severity="info" sx={{ mb: 3 }}>
        <Typography variant="body2">
          • 네이버페이로 안전하게 결제하실 수 있습니다.<br/>
          • 네이버페이 간편결제를 통해 빠르게 결제를 완료하세요.<br/>
          • 결제 버튼 클릭 시 네이버페이 결제 페이지로 이동합니다.
        </Typography>
      </Alert>

      {/* 네이버페이 결제 버튼 */}
      <Button
        variant="contained"
        size="large"
        fullWidth
        onClick={handlePayment}
        disabled={loading}
        sx={{
          py: 2,
          fontSize: '1.1rem',
          fontWeight: 'bold',
          bgcolor: '#03C75A',
          '&:hover': {
            bgcolor: '#02B350'
          },
          '&:disabled': {
            bgcolor: '#cccccc'
          }
        }}
      >
        {loading ? (
          <>
            <CircularProgress size={24} sx={{ mr: 1, color: 'white' }} />
            결제 준비 중...
          </>
        ) : (
          '네이버페이로 결제하기'
        )}
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

export default NaverPayment;
