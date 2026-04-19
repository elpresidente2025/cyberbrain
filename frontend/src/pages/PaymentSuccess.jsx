// frontend/src/pages/PaymentSuccess.jsx
import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Typography,
  Box,
  Button,
  Alert,
  CircularProgress,
  Divider,
} from '@mui/material';
import { CheckCircle, Home, Receipt } from '@mui/icons-material';
import { motion } from 'framer-motion';
import DashboardLayout from '../components/DashboardLayout';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../services/firebase';

const springTransition = 'all 0.35s cubic-bezier(0.16, 1, 0.3, 1)';

const PaymentSuccess = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [paymentData, setPaymentData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const paymentId = searchParams.get('paymentId');
  const orderId = searchParams.get('orderId');

  useEffect(() => {
    const confirmPayment = async () => {
      if (!paymentId || !orderId) {
        setError('결제 정보가 올바르지 않습니다.');
        setLoading(false);
        return;
      }

      try {
        const confirmPaymentFn = httpsCallable(functions, 'confirmNaverPayment');
        const result = await confirmPaymentFn({ paymentId, orderId });

        if (result.data.success) {
          setPaymentData(result.data.payment);
        } else {
          throw new Error(result.data.message || '결제 승인에 실패했습니다.');
        }
      } catch (err) {
        console.error('결제 승인 실패:', err);
        setError(err.message || '결제 처리 중 오류가 발생했습니다.');
      } finally {
        setLoading(false);
      }
    };

    confirmPayment();
  }, [paymentId, orderId]);

  if (loading) {
    return (
      <DashboardLayout>
        <Container maxWidth="md" sx={{ py: 'var(--spacing-xl)' }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
            <CircularProgress size={48} sx={{ mb: 3, color: 'var(--color-primary)' }} />
            <Typography sx={{ color: 'var(--color-text-secondary)', fontSize: '1.05rem' }}>
              결제를 처리하고 있습니다...
            </Typography>
          </Box>
        </Container>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout>
        <Container maxWidth="md" sx={{ py: 'var(--spacing-xl)' }}>
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          >
            <Alert severity="error" sx={{ mb: 3, borderRadius: 'var(--radius-lg)' }}>
              <Typography sx={{ fontWeight: 700, mb: 0.5 }}>결제 처리 실패</Typography>
              <Typography variant="body2">{error}</Typography>
            </Alert>
            <Box sx={{ textAlign: 'center' }}>
              <Button
                variant="contained"
                startIcon={<Home />}
                onClick={() => navigate('/billing')}
                sx={{
                  bgcolor: 'var(--color-primary)',
                  color: 'var(--color-text-inverse)',
                  fontWeight: 600,
                  textTransform: 'none',
                  borderRadius: 'var(--radius-md)',
                  px: 4,
                  py: 1.5,
                  transition: springTransition,
                  '&:hover': { bgcolor: 'var(--color-primary-hover)', transform: 'scale(1.02)' },
                  '&:active': { transform: 'scale(0.98)' },
                }}
              >
                결제 페이지로 돌아가기
              </Button>
            </Box>
          </motion.div>
        </Container>
      </DashboardLayout>
    );
  }

  const infoRows = paymentData ? [
    { label: '주문번호', value: paymentData.orderId },
    { label: '결제 수단', value: '네이버페이' },
    { label: '결제 금액', value: `${paymentData.totalAmount?.toLocaleString()}원` },
    { label: '결제 일시', value: new Date(paymentData.approvedAt).toLocaleString('ko-KR') },
    { label: '상품명', value: paymentData.orderName },
  ] : [];

  return (
    <DashboardLayout>
      <Container maxWidth="sm" sx={{ py: 'var(--spacing-xl)' }}>
        {/* 성공 헤더 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        >
          <Box sx={{ textAlign: 'center', mb: 4, pt: 4 }}>
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ duration: 0.5, delay: 0.2, type: 'spring', stiffness: 200 }}
            >
              <Box sx={{
                width: 88,
                height: 88,
                mx: 'auto',
                mb: 3,
                borderRadius: 'var(--radius-xl)',
                bgcolor: 'var(--color-success-light)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                <CheckCircle sx={{ fontSize: 48, color: 'var(--color-success)' }} />
              </Box>
            </motion.div>
            <Typography sx={{
              fontWeight: 700,
              fontSize: { xs: '1.5rem', sm: '1.75rem' },
              color: 'var(--color-text-primary)',
              letterSpacing: '-0.02em',
              mb: 1,
            }}>
              결제가 완료되었습니다
            </Typography>
            <Typography sx={{ color: 'var(--color-text-secondary)', fontSize: '0.95rem' }}>
              서비스가 즉시 활성화되었습니다
            </Typography>
          </Box>
        </motion.div>

        {/* 결제 상세 정보 */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
        >
          <Box sx={{
            p: { xs: 3, sm: 4 },
            mb: 3,
            borderRadius: 'var(--radius-xl)',
            bgcolor: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            boxShadow: 'var(--shadow-md)',
          }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2.5 }}>
              <Receipt sx={{ fontSize: 20, color: 'var(--color-primary)' }} />
              <Typography sx={{ fontWeight: 700, fontSize: '1rem', color: 'var(--color-text-primary)' }}>
                결제 상세
              </Typography>
            </Box>

            {infoRows.map((row, idx) => (
              <React.Fragment key={row.label}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', py: 1.5 }}>
                  <Typography sx={{ color: 'var(--color-text-tertiary)', fontSize: '0.9rem' }}>
                    {row.label}
                  </Typography>
                  <Typography sx={{
                    color: 'var(--color-text-primary)',
                    fontSize: '0.9rem',
                    fontWeight: 500,
                    fontVariantNumeric: 'tabular-nums',
                    textAlign: 'right',
                    maxWidth: '60%',
                    wordBreak: 'break-word',
                  }}>
                    {row.value}
                  </Typography>
                </Box>
                {idx < infoRows.length - 1 && <Divider sx={{ borderColor: 'var(--color-border)' }} />}
              </React.Fragment>
            ))}
          </Box>
        </motion.div>

        {/* 안내 사항 */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.25, ease: [0.16, 1, 0.3, 1] }}
        >
          <Alert severity="info" sx={{ mb: 4, borderRadius: 'var(--radius-lg)' }}>
            <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>다음 단계 안내</Typography>
            <Typography variant="body2" sx={{ lineHeight: 1.8 }}>
              선택하신 플랜이 즉시 적용되었습니다.<br />
              결제 영수증은 등록하신 이메일로 발송됩니다.
            </Typography>
          </Alert>
        </motion.div>

        {/* 액션 버튼 */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.35, ease: [0.16, 1, 0.3, 1] }}
        >
          <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center' }}>
            <Button
              variant="contained"
              startIcon={<Home />}
              onClick={() => navigate('/dashboard')}
              size="large"
              sx={{
                bgcolor: 'var(--color-primary)',
                color: 'var(--color-text-inverse)',
                fontWeight: 700,
                textTransform: 'none',
                borderRadius: 'var(--radius-md)',
                px: 4,
                py: 1.5,
                transition: springTransition,
                '&:hover': { bgcolor: 'var(--color-primary-hover)', transform: 'scale(1.02)', boxShadow: 'var(--shadow-glow-primary)' },
                '&:active': { transform: 'scale(0.98)' },
              }}
            >
              대시보드로 이동
            </Button>
            <Button
              variant="outlined"
              onClick={() => navigate('/billing')}
              size="large"
              sx={{
                color: 'var(--color-primary)',
                borderColor: 'var(--color-border)',
                fontWeight: 600,
                textTransform: 'none',
                borderRadius: 'var(--radius-md)',
                px: 3,
                py: 1.5,
                transition: springTransition,
                '&:hover': { borderColor: 'var(--color-primary)', bgcolor: 'var(--color-primary-lighter)' },
              }}
            >
              결제 내역 보기
            </Button>
          </Box>
        </motion.div>
      </Container>
    </DashboardLayout>
  );
};

export default PaymentSuccess;
