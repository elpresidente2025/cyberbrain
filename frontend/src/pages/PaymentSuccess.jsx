// frontend/src/pages/PaymentSuccess.jsx
import React, { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Paper,
  Typography,
  Box,
  Button,
  Alert,
  CircularProgress,
  List,
  ListItem,
  ListItemText,
  Divider
} from '@mui/material';
import {
  CheckCircle,
  Receipt,
  Home
} from '@mui/icons-material';
import DashboardLayout from '../components/DashboardLayout';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../services/firebase';

const PaymentSuccess = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [paymentData, setPaymentData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // URL 파라미터에서 결제 정보 추출
  const paymentKey = searchParams.get('paymentKey');
  const orderId = searchParams.get('orderId');
  const amount = searchParams.get('amount');

  useEffect(() => {
    const confirmPayment = async () => {
      if (!paymentKey || !orderId || !amount) {
        setError('결제 정보가 올바르지 않습니다.');
        setLoading(false);
        return;
      }

      try {
        // Firebase Functions를 통해 결제 승인
        const confirmPaymentFn = httpsCallable(functions, 'confirmTossPayment');
        const result = await confirmPaymentFn({
          paymentKey,
          orderId,
          amount: parseInt(amount)
        });

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
  }, [paymentKey, orderId, amount]);

  if (loading) {
    return (
      <DashboardLayout>
        <Container maxWidth="md" sx={{ py: 4 }}>
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <CircularProgress size={60} sx={{ mb: 3 }} />
            <Typography variant="h6" color="text.secondary">
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
        <Container maxWidth="md" sx={{ py: 4 }}>
          <Alert severity="error" sx={{ mb: 3 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              결제 처리 실패
            </Typography>
            <Typography>{error}</Typography>
          </Alert>
          <Box sx={{ textAlign: 'center' }}>
            <Button
              variant="contained"
              startIcon={<Home />}
              onClick={() => navigate('/billing')}
              sx={{ mr: 2 }}
            >
              결제 페이지로 돌아가기
            </Button>
          </Box>
        </Container>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <Container maxWidth="md" sx={{ py: 4 }}>
        {/* 성공 헤더 */}
        <Paper sx={{ p: 4, mb: 3, textAlign: 'center', bgcolor: 'success.light' }}>
          <CheckCircle sx={{ fontSize: 80, color: 'success.main', mb: 2 }} />
          <Typography variant="h4" sx={{ fontWeight: 'bold', mb: 1, color: 'success.dark' }}>
            결제가 완료되었습니다!
          </Typography>
          <Typography variant="body1" color="success.dark">
            서비스가 즉시 활성화되었습니다. 이용해주셔서 감사합니다.
          </Typography>
        </Paper>

        {/* 결제 상세 정보 */}
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center' }}>
            <Receipt sx={{ mr: 1 }} />
            결제 상세 정보
          </Typography>
          
          {paymentData && (
            <List>
              <ListItem divider>
                <ListItemText 
                  primary="주문번호" 
                  secondary={paymentData.orderId}
                />
              </ListItem>
              <ListItem divider>
                <ListItemText 
                  primary="결제 수단" 
                  secondary={`${paymentData.method} (${paymentData.card?.company || ''})`}
                />
              </ListItem>
              <ListItem divider>
                <ListItemText 
                  primary="결제 금액" 
                  secondary={`${paymentData.totalAmount?.toLocaleString()}원`}
                />
              </ListItem>
              <ListItem divider>
                <ListItemText 
                  primary="결제 일시" 
                  secondary={new Date(paymentData.approvedAt).toLocaleString('ko-KR')}
                />
              </ListItem>
              <ListItem>
                <ListItemText 
                  primary="상품명" 
                  secondary={paymentData.orderName}
                />
              </ListItem>
            </List>
          )}
        </Paper>

        {/* 안내 사항 */}
        <Alert severity="info" sx={{ mb: 3 }}>
          <Typography variant="body2" sx={{ mb: 1 }}>
            <strong>다음 단계 안내</strong>
          </Typography>
          <Typography variant="body2">
            • 결제 완료와 함께 선택하신 플랜이 즉시 적용되었습니다.<br/>
            • 결제 영수증은 등록하신 이메일로 발송됩니다.<br/>
            • 서비스 이용 중 문의사항이 있으시면 고객센터로 연락해주세요.
          </Typography>
        </Alert>

        {/* 액션 버튼들 */}
        <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center' }}>
          <Button
            variant="contained"
            startIcon={<Home />}
            onClick={() => navigate('/dashboard')}
            size="large"
          >
            대시보드로 이동
          </Button>
          <Button
            variant="outlined"
            onClick={() => navigate('/billing')}
            size="large"
          >
            결제 내역 보기
          </Button>
        </Box>
      </Container>
    </DashboardLayout>
  );
};

export default PaymentSuccess;