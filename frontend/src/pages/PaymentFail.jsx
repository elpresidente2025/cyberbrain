// frontend/src/pages/PaymentFail.jsx
import React from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Paper,
  Typography,
  Box,
  Button,
  Alert,
  List,
  ListItem,
  ListItemText
} from '@mui/material';
import {
  Error,
  Refresh,
  Home,
  ContactSupport
} from '@mui/icons-material';
import DashboardLayout from '../components/DashboardLayout';

const PaymentFail = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // URL 파라미터에서 실패 정보 추출
  const code = searchParams.get('code');
  const message = searchParams.get('message');
  const orderId = searchParams.get('orderId');

  // 에러 코드별 상세 메시지
  const getErrorMessage = (code) => {
    switch (code) {
      case 'PAY_PROCESS_CANCELED':
        return '사용자가 결제를 취소했습니다.';
      case 'PAY_PROCESS_ABORTED':
        return '결제 진행 중 오류가 발생했습니다.';
      case 'REJECT_CARD_COMPANY':
        return '카드사에서 결제를 거절했습니다. 다른 카드를 이용해주세요.';
      case 'INSUFFICIENT_BALANCE':
        return '잔액이 부족합니다.';
      case 'INVALID_CARD_EXPIRATION':
        return '카드 유효기간을 확인해주세요.';
      case 'INVALID_STOPPED_CARD':
        return '정지된 카드입니다. 다른 카드를 이용해주세요.';
      case 'EXCEED_MAX_DAILY_PAYMENT_COUNT':
        return '일일 결제 한도를 초과했습니다.';
      case 'NOT_SUPPORTED_INSTALLMENT_PLAN':
        return '지원하지 않는 할부개월수입니다.';
      case 'INVALID_API_KEY':
        return '잘못된 API 키입니다.';
      case 'NOT_FOUND_TERMINAL_ID':
        return '단말기 정보를 찾을 수 없습니다.';
      default:
        return message || '알 수 없는 오류가 발생했습니다.';
    }
  };

  // 해결 방법 제안
  const getSolution = (code) => {
    switch (code) {
      case 'REJECT_CARD_COMPANY':
      case 'INVALID_STOPPED_CARD':
        return '다른 결제 수단을 이용해주세요.';
      case 'INSUFFICIENT_BALANCE':
        return '계좌 잔액을 확인하거나 다른 카드를 이용해주세요.';
      case 'INVALID_CARD_EXPIRATION':
        return '카드 유효기간을 확인하거나 다른 카드를 이용해주세요.';
      case 'EXCEED_MAX_DAILY_PAYMENT_COUNT':
        return '내일 다시 시도하거나 다른 카드를 이용해주세요.';
      case 'NOT_SUPPORTED_INSTALLMENT_PLAN':
        return '다른 할부개월수를 선택하거나 일시불로 결제해주세요.';
      default:
        return '잠시 후 다시 시도해주세요.';
    }
  };

  return (
    <DashboardLayout>
      <Container maxWidth="md" sx={{ py: 4 }}>
        {/* 실패 헤더 */}
        <Paper sx={{ p: 4, mb: 3, textAlign: 'center', bgcolor: 'error.light' }}>
          <Error sx={{ fontSize: 80, color: 'error.main', mb: 2 }} />
          <Typography variant="h4" sx={{ fontWeight: 'bold', mb: 1, color: 'error.dark' }}>
            결제에 실패했습니다
          </Typography>
          <Typography variant="body1" color="error.dark">
            결제 처리 중 문제가 발생했습니다. 아래 내용을 확인해주세요.
          </Typography>
        </Paper>

        {/* 오류 상세 정보 */}
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h6" sx={{ mb: 2, color: 'error.main' }}>
            오류 상세 정보
          </Typography>
          
          <List>
            {orderId && (
              <ListItem divider>
                <ListItemText 
                  primary="주문번호" 
                  secondary={orderId}
                />
              </ListItem>
            )}
            <ListItem divider>
              <ListItemText 
                primary="오류 코드" 
                secondary={code || '알 수 없음'}
              />
            </ListItem>
            <ListItem divider>
              <ListItemText 
                primary="오류 메시지" 
                secondary={getErrorMessage(code)}
              />
            </ListItem>
            <ListItem>
              <ListItemText 
                primary="해결 방법" 
                secondary={getSolution(code)}
              />
            </ListItem>
          </List>
        </Paper>

        {/* 해결 방안 안내 */}
        <Alert severity="warning" sx={{ mb: 3 }}>
          <Typography variant="body2" sx={{ mb: 1 }}>
            <strong>결제 실패 해결 방법</strong>
          </Typography>
          <Typography variant="body2">
            1. 카드 정보를 다시 확인해주세요 (유효기간, CVC 번호 등)<br/>
            2. 다른 결제 수단을 이용해보세요<br/>
            3. 카드 한도나 잔액을 확인해주세요<br/>
            4. 문제가 계속되면 카드사 또는 은행에 문의해주세요
          </Typography>
        </Alert>

        {/* 고객센터 안내 */}
        <Alert severity="info" sx={{ mb: 3 }}>
          <Typography variant="body2">
            <strong>도움이 필요하시면</strong><br/>
            결제 관련 문의: support@cyberbrain.kr<br/>
            전화 문의: 1588-1234 (평일 09:00-18:00)
          </Typography>
        </Alert>

        {/* 액션 버튼들 */}
        <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center', flexWrap: 'wrap' }}>
          <Button
            variant="contained"
            startIcon={<Refresh />}
            onClick={() => navigate('/billing')}
            size="large"
            color="primary"
          >
            다시 결제하기
          </Button>
          <Button
            variant="outlined"
            startIcon={<Home />}
            onClick={() => navigate('/dashboard')}
            size="large"
          >
            대시보드로 이동
          </Button>
          <Button
            variant="outlined"
            startIcon={<ContactSupport />}
            onClick={() => window.open('mailto:support@cyberbrain.kr', '_blank')}
            size="large"
            color="secondary"
          >
            고객센터 문의
          </Button>
        </Box>
      </Container>
    </DashboardLayout>
  );
};

export default PaymentFail;