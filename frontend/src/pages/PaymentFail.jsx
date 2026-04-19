// frontend/src/pages/PaymentFail.jsx
import React from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Typography,
  Box,
  Button,
  Alert,
  Divider,
} from '@mui/material';
import { ErrorOutline, Refresh, Home, ContactSupport } from '@mui/icons-material';
import { motion } from 'framer-motion';
import DashboardLayout from '../components/DashboardLayout';
import { BRANDING } from '../config/branding';

const springTransition = 'all 0.35s cubic-bezier(0.16, 1, 0.3, 1)';

const getErrorMessage = (code) => {
  switch (code) {
    case 'PAY_PROCESS_CANCELED': return '사용자가 결제를 취소했습니다.';
    case 'PAY_PROCESS_ABORTED': return '결제 진행 중 오류가 발생했습니다.';
    case 'REJECT_CARD_COMPANY': return '카드사에서 결제를 거절했습니다. 다른 카드를 이용해주세요.';
    case 'INSUFFICIENT_BALANCE': return '잔액이 부족합니다.';
    case 'INVALID_CARD_EXPIRATION': return '카드 유효기간을 확인해주세요.';
    case 'INVALID_STOPPED_CARD': return '정지된 카드입니다. 다른 카드를 이용해주세요.';
    case 'EXCEED_MAX_DAILY_PAYMENT_COUNT': return '일일 결제 한도를 초과했습니다.';
    case 'NOT_SUPPORTED_INSTALLMENT_PLAN': return '지원하지 않는 할부개월수입니다.';
    case 'INVALID_API_KEY': return '잘못된 API 키입니다.';
    case 'NOT_FOUND_TERMINAL_ID': return '단말기 정보를 찾을 수 없습니다.';
    default: return '알 수 없는 오류가 발생했습니다.';
  }
};

const getSolution = (code) => {
  switch (code) {
    case 'REJECT_CARD_COMPANY':
    case 'INVALID_STOPPED_CARD': return '다른 결제 수단을 이용해주세요.';
    case 'INSUFFICIENT_BALANCE': return '계좌 잔액을 확인하거나 다른 카드를 이용해주세요.';
    case 'INVALID_CARD_EXPIRATION': return '카드 유효기간을 확인하거나 다른 카드를 이용해주세요.';
    case 'EXCEED_MAX_DAILY_PAYMENT_COUNT': return '내일 다시 시도하거나 다른 카드를 이용해주세요.';
    case 'NOT_SUPPORTED_INSTALLMENT_PLAN': return '다른 할부개월수를 선택하거나 일시불로 결제해주세요.';
    default: return '잠시 후 다시 시도해주세요.';
  }
};

const PaymentFail = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const code = searchParams.get('code');
  const message = searchParams.get('message');
  const orderId = searchParams.get('orderId');

  const infoRows = [
    ...(orderId ? [{ label: '주문번호', value: orderId }] : []),
    { label: '오류 코드', value: code || '알 수 없음' },
    { label: '오류 메시지', value: message || getErrorMessage(code) },
    { label: '해결 방법', value: getSolution(code) },
  ];

  return (
    <DashboardLayout>
      <Container maxWidth="sm" sx={{ py: 'var(--spacing-xl)' }}>
        {/* 실패 헤더 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        >
          <Box sx={{ textAlign: 'center', mb: 4, pt: 4 }}>
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.15, ease: [0.16, 1, 0.3, 1] }}
            >
              <Box sx={{
                width: 88,
                height: 88,
                mx: 'auto',
                mb: 3,
                borderRadius: 'var(--radius-xl)',
                bgcolor: 'var(--color-error-light)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                <ErrorOutline sx={{ fontSize: 48, color: 'var(--color-error)' }} />
              </Box>
            </motion.div>
            <Typography sx={{
              fontWeight: 700,
              fontSize: { xs: '1.5rem', sm: '1.75rem' },
              color: 'var(--color-text-primary)',
              letterSpacing: '-0.02em',
              mb: 1,
            }}>
              결제에 실패했습니다
            </Typography>
            <Typography sx={{ color: 'var(--color-text-secondary)', fontSize: '0.95rem', wordBreak: 'keep-all' }}>
              아래 내용을 확인해 주세요
            </Typography>
          </Box>
        </motion.div>

        {/* 오류 상세 정보 */}
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
            <Typography sx={{ fontWeight: 700, fontSize: '1rem', color: 'var(--color-error)', mb: 2 }}>
              오류 상세 정보
            </Typography>

            {infoRows.map((row, idx) => (
              <React.Fragment key={row.label}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', py: 1.5, gap: 2 }}>
                  <Typography sx={{ color: 'var(--color-text-tertiary)', fontSize: '0.9rem', flexShrink: 0 }}>
                    {row.label}
                  </Typography>
                  <Typography sx={{
                    color: 'var(--color-text-primary)',
                    fontSize: '0.9rem',
                    fontWeight: 500,
                    textAlign: 'right',
                    wordBreak: 'keep-all',
                  }}>
                    {row.value}
                  </Typography>
                </Box>
                {idx < infoRows.length - 1 && <Divider sx={{ borderColor: 'var(--color-border)' }} />}
              </React.Fragment>
            ))}
          </Box>
        </motion.div>

        {/* 해결 방안 */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.25, ease: [0.16, 1, 0.3, 1] }}
        >
          <Alert severity="warning" sx={{ mb: 3, borderRadius: 'var(--radius-lg)' }}>
            <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>결제 실패 해결 방법</Typography>
            <Typography variant="body2" sx={{ lineHeight: 1.8 }}>
              1. 카드 정보를 다시 확인해 주세요<br />
              2. 다른 결제 수단을 이용해 보세요<br />
              3. 카드 한도나 잔액을 확인해 주세요
            </Typography>
          </Alert>

          <Alert severity="info" sx={{ mb: 4, borderRadius: 'var(--radius-lg)' }}>
            <Typography variant="body2">
              <strong>도움이 필요하시면</strong><br />
              결제 관련 문의: {BRANDING.supportEmail}
            </Typography>
          </Alert>
        </motion.div>

        {/* 액션 버튼 */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.35, ease: [0.16, 1, 0.3, 1] }}
        >
          <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', flexWrap: 'wrap' }}>
            <Button
              variant="contained"
              startIcon={<Refresh />}
              onClick={() => navigate('/billing')}
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
              다시 결제하기
            </Button>
            <Button
              variant="outlined"
              startIcon={<Home />}
              onClick={() => navigate('/dashboard')}
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
              대시보드로 이동
            </Button>
            <Button
              variant="outlined"
              startIcon={<ContactSupport />}
              onClick={() => window.open(`mailto:${BRANDING.supportEmail}`, '_blank')}
              size="large"
              sx={{
                color: 'var(--color-text-secondary)',
                borderColor: 'var(--color-border)',
                fontWeight: 600,
                textTransform: 'none',
                borderRadius: 'var(--radius-md)',
                px: 3,
                py: 1.5,
                transition: springTransition,
                '&:hover': { borderColor: 'var(--color-text-secondary)', bgcolor: 'var(--color-surface)' },
              }}
            >
              고객센터 문의
            </Button>
          </Box>
        </motion.div>
      </Container>
    </DashboardLayout>
  );
};

export default PaymentFail;
