// frontend/src/pages/Billing.jsx
import React, { useState, useEffect } from 'react';
import {
  Container,
  Paper,
  Typography,
  Box,
  Grid,
  Card,
  CardContent,
  CardActions,
  Button,
  Chip,
  Divider,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Alert,
  LinearProgress,
  useTheme,
  Avatar,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem
} from '@mui/material';
import {
  CreditCard,
  CheckCircle,
  Cancel,
  Warning,
  Upload,
  Schedule,
  Payment,
  VerifiedUser,
  Person,
  AttachFile
} from '@mui/icons-material';
import DashboardLayout from '../components/DashboardLayout';
import PaymentDialog from '../components/PaymentDialog';
import { useAuth } from '../hooks/useAuth';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../services/firebase';
import { NotificationSnackbar, useNotification } from '../components/ui';
import { colors, spacing, typography, visualWeight, verticalRhythm } from '../theme/tokens';

const Billing = () => {
  const { user, refreshUserProfile } = useAuth();
  const theme = useTheme();
  const { notification, showNotification, hideNotification } = useNotification();
  const [authDialogOpen, setAuthDialogOpen] = useState(false);
  const [paymentDialogOpen, setPaymentDialogOpen] = useState(false);
  const [selectedCertFile, setSelectedCertFile] = useState(null);
  const [selectedReceiptFile, setSelectedReceiptFile] = useState(null);
  const [uploading, setUploading] = useState(false);

  // 구독 상태 확인
  const isSubscribed = user?.subscriptionStatus === 'active';
  const planInfo = {
    name: '스탠다드 플랜',
    price: 55000,
    monthlyLimit: 90,
    color: colors.brand.primary,
    features: [
      '월 90회 원고 생성',
      'SNS 원고 무료 생성',
      '무제한 수정 및 재생성',
      '더불어민주당 당원 전용'
    ]
  };

  // 결제 시작
  const handleStartSubscription = () => {
    setPaymentDialogOpen(true);
  };

  const handlePaymentClose = () => {
    setPaymentDialogOpen(false);
  };

  const handleCertFileUpload = (event) => {
    const file = event.target.files[0];
    setSelectedCertFile(file);
  };

  const handleReceiptFileUpload = (event) => {
    const file = event.target.files[0];
    setSelectedReceiptFile(file);
  };

  const handleAuthClick = () => {
    // 인증 완료 상태 체크 (verificationStatus가 'verified'인 경우)
    if (user?.verificationStatus === 'verified') {
      showNotification(
        '이미 당원 인증이 완료되었습니다. 추가 인증이 필요한 경우 고객센터로 문의해주세요.',
        'info'
      );
      return;
    }
    // 인증 안 된 경우 다이얼로그 열기
    setAuthDialogOpen(true);
  };

  // 파일을 base64로 변환하는 헬퍼 함수
  const fileToBase64 = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => {
        // "data:image/jpeg;base64,..." 형식에서 base64 부분만 추출
        const base64 = reader.result.split(',')[1];
        resolve(base64);
      };
      reader.onerror = error => reject(error);
    });
  };

  const handleAuthSubmit = async () => {
    if (!selectedCertFile && !selectedReceiptFile) {
      showNotification('당적증명서 또는 당비납부 영수증 중 하나 이상 업로드해주세요.', 'warning');
      return;
    }

    setUploading(true);

    try {
      const results = [];

      // 1. 당적증명서 처리
      if (selectedCertFile) {
        const fileExtension = selectedCertFile.name.split('.').pop();
        const fileName = `${Date.now()}.${fileExtension}`;
        const base64Data = await fileToBase64(selectedCertFile);

        const verifyPartyCertificate = httpsCallable(functions, 'verifyPartyCertificate');
        const result = await verifyPartyCertificate({
          userId: user.uid,
          base64Data: base64Data,
          fileName: fileName,
          imageFormat: fileExtension
        });

        results.push({ type: '당적증명서', result: result.data });
      }

      // 2. 당비납부 영수증 처리
      if (selectedReceiptFile) {
        const fileExtension = selectedReceiptFile.name.split('.').pop();
        const fileName = `${Date.now()}.${fileExtension}`;
        const base64Data = await fileToBase64(selectedReceiptFile);

        const verifyPaymentReceipt = httpsCallable(functions, 'verifyPaymentReceipt');
        const result = await verifyPaymentReceipt({
          userId: user.uid,
          base64Data: base64Data,
          fileName: fileName,
          imageFormat: fileExtension
        });

        results.push({ type: '당비납부 영수증', result: result.data });
      }

      setAuthDialogOpen(false);
      setSelectedCertFile(null);
      setSelectedReceiptFile(null);
      setUploading(false);

      // 결과 메시지 생성
      const successCount = results.filter(r => r.result.success).length;
      const reviewCount = results.filter(r => r.result.requiresManualReview).length;

      if (successCount > 0) {
        showNotification(`당원 인증이 완료되었습니다! (${successCount}개 문서 처리 완료)`, 'success');
        if (refreshUserProfile) {
          await refreshUserProfile();
        }
      } else if (reviewCount > 0) {
        showNotification('문서가 수동 검토 대기 중입니다.', 'info');
      } else {
        showNotification('인증 처리 중 문제가 발생했습니다.', 'error');
      }

    } catch (error) {
      console.error('당원 인증 오류:', error);
      setUploading(false);
      showNotification('인증 요청 중 오류가 발생했습니다. 다시 시도해주세요.', 'error');
    }
  };

  return (
    <DashboardLayout>
      <Container maxWidth="lg" sx={{ py: `${spacing.xl}px` }}>
        {/* 페이지 헤더 */}
        <Box sx={{ mb: `${spacing.xl}px` }}>
          <Typography variant="h4" sx={{
            fontWeight: 'bold',
            mb: `${spacing.xs}px`,
            color: theme.palette.mode === 'dark' ? 'white' : 'black',
            display: 'flex',
            alignItems: 'center',
            gap: `${spacing.xs}px`
          }}>
            <CreditCard sx={{ color: theme.palette.mode === 'dark' ? 'white' : 'black' }} />
            {isSubscribed ? '구독 관리' : '구독 시작하기'}
          </Typography>
          <Typography variant="body1" sx={{ color: theme.palette.mode === 'dark' ? 'rgba(255, 255, 255, 0.7)' : 'rgba(0, 0, 0, 0.6)' }}>
            {isSubscribed ? '구독 정보와 당원 인증을 관리하세요' : '전자두뇌비서관으로 효율적인 의정활동을 시작하세요'}
          </Typography>
        </Box>

        {/* 구독 상태별 UI */}
        {!isSubscribed ? (
          // 미구독자: Hero CTA
          <Box sx={{
            display: 'flex',
            flexDirection: 'column',
            gap: `${spacing.xl}px`
          }}>
            {/* Hero CTA */}
            <Paper elevation={0} sx={{
              p: `${spacing.xxl || spacing.xl * 1.5}px`,
              background: `linear-gradient(135deg, ${colors.brand.primary} 0%, ${colors.brand.primaryHover} 100%)`,
              color: 'white',
              textAlign: 'center',
              borderRadius: 3
            }}>
              <Typography variant="h3" sx={{ fontWeight: 'bold', mb: `${spacing.md}px`, color: 'white' }}>
                전자두뇌비서관 시작하기
              </Typography>
              <Typography variant="h4" sx={{ mb: `${spacing.xs}px`, fontWeight: 'bold', color: 'white' }}>
                {planInfo.price.toLocaleString()}원/월
              </Typography>
              <Typography variant="body1" sx={{ mb: `${spacing.xl}px`, opacity: 0.9, color: 'white' }}>
                VAT 포함 · 월 {planInfo.monthlyLimit}회 원고 생성
              </Typography>
              <Button
                variant="contained"
                size="large"
                onClick={handleStartSubscription}
                sx={{
                  bgcolor: 'white',
                  color: colors.brand.primary,
                  fontSize: '1.2rem',
                  fontWeight: 'bold',
                  py: 2,
                  px: 6,
                  '&:hover': {
                    bgcolor: '#f0f0f0'
                  }
                }}
              >
                💳 지금 시작하기
              </Button>
            </Paper>

            {/* 포함 혜택 */}
            <Paper elevation={0} sx={{ p: `${spacing.lg}px` }}>
              <Typography variant="h6" sx={{ mb: `${spacing.lg}px`, fontWeight: 'bold' }}>
                포함된 혜택
              </Typography>
              <Grid container spacing={3}>
                <Grid item xs={12} md={4}>
                  <Box sx={{ textAlign: 'center' }}>
                    <CheckCircle sx={{ fontSize: 48, color: colors.brand.primary, mb: 2 }} />
                    <Typography variant="h6" sx={{ mb: 1, fontWeight: 'bold' }}>
                      월 90회 원고 생성
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      지역구 주민과 소통할 양질의 콘텐츠를 충분히 생성하세요
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Box sx={{ textAlign: 'center' }}>
                    <CheckCircle sx={{ fontSize: 48, color: colors.brand.primary, mb: 2 }} />
                    <Typography variant="h6" sx={{ mb: 1, fontWeight: 'bold' }}>
                      SNS 원고 무료 생성
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      블로그 원고를 Instagram, Facebook 등 SNS용으로 자동 변환
                    </Typography>
                  </Box>
                </Grid>
                <Grid item xs={12} md={4}>
                  <Box sx={{ textAlign: 'center' }}>
                    <CheckCircle sx={{ fontSize: 48, color: colors.brand.primary, mb: 2 }} />
                    <Typography variant="h6" sx={{ mb: 1, fontWeight: 'bold' }}>
                      무제한 수정 및 재생성
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      만족할 때까지 원고를 수정하고 재생성할 수 있습니다
                    </Typography>
                  </Box>
                </Grid>
              </Grid>
            </Paper>

            {/* 당원 인증 및 환불 정책 */}
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Paper elevation={0} sx={{ p: `${spacing.lg}px` }}>
                  <Typography variant="h6" sx={{ mb: `${spacing.md}px`, display: 'flex', alignItems: 'center' }}>
                    <VerifiedUser sx={{ mr: `${spacing.xs}px`, color: colors.brand.primary }} />
                    당원 인증
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: `${spacing.md}px` }}>
                    더불어민주당 당원 인증을 완료하시면 서비스를 이용하실 수 있습니다.
                  </Typography>
                  <Button
                    variant="outlined"
                    onClick={handleAuthClick}
                    startIcon={<Upload />}
                    fullWidth
                  >
                    당원 인증하기
                  </Button>
                </Paper>
              </Grid>

              <Grid item xs={12} md={6}>
                <Paper elevation={0} sx={{ p: `${spacing.lg}px` }}>
                  <Typography variant="h6" sx={{ mb: `${spacing.md}px`, display: 'flex', alignItems: 'center' }}>
                    <Warning sx={{ mr: `${spacing.xs}px`, color: '#ff9800' }} />
                    환불 정책
                  </Typography>
                  <List dense>
                    <ListItem sx={{ px: 0 }}>
                      <ListItemText
                        primary="구매일로부터 7일 이내: 전액 환불 가능"
                        primaryTypographyProps={{ variant: 'body2' }}
                      />
                    </ListItem>
                    <ListItem sx={{ px: 0 }}>
                      <ListItemText
                        primary="원고 생성 이용 후: 미사용 횟수만큼 일할 계산하여 환불"
                        primaryTypographyProps={{ variant: 'body2' }}
                      />
                    </ListItem>
                    <ListItem sx={{ px: 0 }}>
                      <ListItemText
                        primary="환불 요청 시 7영업일 이내 처리 완료"
                        primaryTypographyProps={{ variant: 'body2' }}
                      />
                    </ListItem>
                  </List>
                </Paper>
              </Grid>
            </Grid>
          </Box>
        ) : (
          // 구독 중인 사용자
          <Box sx={{
            display: 'flex',
            flexDirection: 'column',
            gap: `${spacing.lg}px`
          }}>
            {/* 구독 정보 카드 3단 */}
            <Grid container spacing={3}>
              {/* 구독 정보 */}
              <Grid item xs={12} md={4}>
                <Paper elevation={0} sx={{ p: `${spacing.lg}px`, height: '100%' }}>
                  <Typography variant="h6" sx={{ mb: `${spacing.md}px`, display: 'flex', alignItems: 'center' }}>
                    <CreditCard sx={{ mr: `${spacing.xs}px`, color: colors.brand.primary }} />
                    구독 정보
                  </Typography>
                  <Box sx={{ mb: `${spacing.md}px` }}>
                    <Typography variant="h5" sx={{ fontWeight: 'bold', color: colors.brand.primary, mb: 1 }}>
                      {planInfo.name}
                    </Typography>
                    <Typography variant="h6" sx={{ mb: 1 }}>
                      {planInfo.price.toLocaleString()}원/월
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      VAT 포함
                    </Typography>
                  </Box>
                  <Divider sx={{ my: `${spacing.md}px` }} />
                  <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
                    다음 결제일
                  </Typography>
                  <Typography variant="body1" sx={{ fontWeight: 'bold' }}>
                    {(() => {
                      const nextBilling = user?.nextBillingDate?.toDate?.() || new Date(new Date().getFullYear(), new Date().getMonth() + 1, 1);
                      return nextBilling.toLocaleDateString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric' });
                    })()}
                  </Typography>
                </Paper>
              </Grid>

              {/* 이번 달 사용량 */}
              <Grid item xs={12} md={4}>
                <Paper elevation={0} sx={{ p: `${spacing.lg}px`, height: '100%' }}>
                  <Typography variant="h6" sx={{ mb: `${spacing.md}px`, display: 'flex', alignItems: 'center' }}>
                    <Schedule sx={{ mr: `${spacing.xs}px`, color: colors.brand.primary }} />
                    이번 달 사용량
                  </Typography>
                  <Box sx={{ mb: `${spacing.md}px` }}>
                    <Typography variant="h3" sx={{ fontWeight: 'bold', color: colors.brand.primary, mb: 1 }}>
                      45 / {planInfo.monthlyLimit}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      원고 생성 횟수
                    </Typography>
                  </Box>
                  <LinearProgress
                    variant="determinate"
                    value={50}
                    sx={{
                      height: 10,
                      borderRadius: 5,
                      bgcolor: colors.brand.primaryLight10,
                      '& .MuiLinearProgress-bar': {
                        bgcolor: colors.brand.primary
                      }
                    }}
                  />
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                    50% 사용
                  </Typography>
                </Paper>
              </Grid>

              {/* 당원 인증 상태 */}
              <Grid item xs={12} md={4}>
                <Paper elevation={0} sx={{ p: `${spacing.lg}px`, height: '100%' }}>
                  <Typography variant="h6" sx={{ mb: `${spacing.md}px`, display: 'flex', alignItems: 'center' }}>
                    <VerifiedUser sx={{ mr: `${spacing.xs}px`, color: user?.verificationStatus === 'verified' ? '#4caf50' : '#ff9800' }} />
                    당원 인증
                  </Typography>
                  {user?.verificationStatus === 'verified' && user?.lastVerification ? (
                    <>
                      <Alert severity="success" sx={{ mb: `${spacing.md}px` }}>
                        <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
                          인증 완료
                        </Typography>
                        <Typography variant="caption">
                          {user.lastVerification.quarter}
                        </Typography>
                      </Alert>
                      <Button
                        variant="outlined"
                        size="small"
                        onClick={handleAuthClick}
                        startIcon={<Upload />}
                        fullWidth
                      >
                        재인증
                      </Button>
                    </>
                  ) : (
                    <>
                      <Alert severity="warning" sx={{ mb: `${spacing.md}px` }}>
                        <Typography variant="body2">
                          당원 인증이 필요합니다
                        </Typography>
                      </Alert>
                      <Button
                        variant="contained"
                        onClick={handleAuthClick}
                        startIcon={<Upload />}
                        fullWidth
                        sx={{ bgcolor: '#ff9800', '&:hover': { bgcolor: '#f57c00' } }}
                      >
                        당원 인증하기
                      </Button>
                    </>
                  )}
                </Paper>
              </Grid>
            </Grid>

            {/* 결제 내역 */}
            <Paper elevation={0} sx={{ p: `${spacing.lg}px` }}>
              <Typography variant="h6" sx={{ mb: `${spacing.md}px`, display: 'flex', alignItems: 'center' }}>
                <Payment sx={{ mr: `${spacing.xs}px` }} />
                결제 내역
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: `${spacing.md}px` }}>
                최근 결제 내역을 확인할 수 있습니다.
              </Typography>
              {/* TODO: 실제 결제 내역 불러오기 */}
              <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
                결제 내역이 없습니다
              </Typography>
            </Paper>

            {/* 구독 관리 버튼 */}
            <Box sx={{ display: 'flex', gap: `${spacing.md}px`, justifyContent: 'center' }}>
              <Button
                variant="outlined"
                color="error"
                onClick={() => showNotification('구독 해지 기능은 고객센터로 문의해주세요.', 'info')}
              >
                구독 해지
              </Button>
              <Button
                variant="outlined"
                onClick={() => showNotification('결제수단 변경 기능은 준비 중입니다.', 'info')}
              >
                결제수단 변경
              </Button>
            </Box>
          </Box>
        )}


        {/* 당원 인증 다이얼로그 */}
        <Dialog open={authDialogOpen} onClose={() => setAuthDialogOpen(false)} maxWidth="sm" fullWidth>
          <DialogTitle>당원 인증서 제출</DialogTitle>
          <DialogContent>
            <Box sx={{ mt: `${spacing.md}px` }}>
              {/* 당적증명서 업로드 */}
              <Typography variant="subtitle2" sx={{ mb: `${spacing.xs}px`, fontWeight: 'bold' }}>
                1. 당적증명서
              </Typography>
              <Button
                variant="outlined"
                component="label"
                startIcon={<AttachFile />}
                fullWidth
                sx={{ mb: `${spacing.xs}px` }}
              >
                당적증명서 업로드
                <input
                  type="file"
                  hidden
                  accept=".pdf,.jpg,.jpeg,.png"
                  onChange={handleCertFileUpload}
                />
              </Button>

              {selectedCertFile && (
                <Alert severity="success" sx={{ mb: `${spacing.md}px` }}>
                  선택된 파일: {selectedCertFile.name}
                </Alert>
              )}

              {/* 당비납부 영수증 업로드 */}
              <Typography variant="subtitle2" sx={{ mb: `${spacing.xs}px`, mt: `${spacing.md}px`, fontWeight: 'bold' }}>
                2. 당비납부 영수증
              </Typography>
              <Button
                variant="outlined"
                component="label"
                startIcon={<AttachFile />}
                fullWidth
                sx={{ mb: `${spacing.xs}px` }}
              >
                당비납부 영수증 업로드
                <input
                  type="file"
                  hidden
                  accept=".pdf,.jpg,.jpeg,.png"
                  onChange={handleReceiptFileUpload}
                />
              </Button>

              {selectedReceiptFile && (
                <Alert severity="success">
                  선택된 파일: {selectedReceiptFile.name}
                </Alert>
              )}
            </Box>

            <Typography variant="caption" color="text.secondary" sx={{ mt: `${spacing.md}px`, display: 'block' }}>
              * 지원 파일 형식: PDF, JPG, PNG<br />
              * 개인정보는 인증 완료 후 즉시 삭제됩니다
            </Typography>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setAuthDialogOpen(false)} disabled={uploading}>취소</Button>
            <Button onClick={handleAuthSubmit} variant="contained" disabled={uploading || (!selectedCertFile && !selectedReceiptFile)}>
              {uploading ? '처리중...' : '제출'}
            </Button>
          </DialogActions>
        </Dialog>

        {/* 네이버페이 결제 다이얼로그 */}
        <PaymentDialog
          open={paymentDialogOpen}
          onClose={handlePaymentClose}
          selectedPlan={planInfo}
        />

        {/* 알림 스낵바 */}
        <NotificationSnackbar
          open={notification.open}
          onClose={hideNotification}
          message={notification.message}
          severity={notification.severity}
          autoHideDuration={4000}
        />
      </Container>
    </DashboardLayout>
  );
};

export default Billing;