// frontend/src/pages/billing/BillingPage.jsx
// 결제 및 인증 페이지 (오케스트레이터)

import React from 'react';
import { motion } from 'framer-motion';
import { Container, Grid, Box, Button } from '@mui/material';
import DashboardLayout from '../../components/DashboardLayout';
import PaymentDialog from '../../components/PaymentDialog';
import PublishingProgress from '../../components/dashboard/PublishingProgress';
import { NotificationSnackbar } from '../../components/ui';
import useBillingData from './hooks/useBillingData';
import useBillingActions from './hooks/useBillingActions';
import {
    BillingHeroCard,
    SubscriptionCTA,
    AuthVerificationCard,
    BenefitsCard,
    RefundPolicyCard,
    SubscriptionInfoCard,
    PaymentHistoryCard,
    AuthDialog,
    CancelDialog,
} from './components';

const stagger = (i) => ({ duration: 0.5, delay: 0.15 + i * 0.08 });

const BillingPage = () => {
    const {
        user, refreshUserProfile, testMode, isAdmin, isSubscribed,
        adminOverrideSubscription, setAdminOverrideSubscription,
        authStatus, planInfo,
    } = useBillingData();

    const {
        notification, hideNotification, showNotification,
        authDialogOpen, setAuthDialogOpen,
        paymentDialogOpen, setPaymentDialogOpen,
        cancelDialogOpen, setCancelDialogOpen,
        selectedCertFile, setSelectedCertFile,
        selectedReceiptFile, setSelectedReceiptFile,
        uploading,
        handleStartSubscription, handleAuthClick,
        handleAuthSubmit, handleCancelSubscription,
    } = useBillingActions({ user, refreshUserProfile, testMode });

    return (
        <DashboardLayout>
            <Container maxWidth="lg" sx={{ py: 3 }}>
                {/* 히어로 카드 */}
                <BillingHeroCard
                    isSubscribed={isSubscribed}
                    isAdmin={isAdmin}
                    adminOverrideSubscription={adminOverrideSubscription}
                    user={user}
                    onAdminToggle={setAdminOverrideSubscription}
                />

                {/* 구독 상태별 본문 */}
                {!isSubscribed ? (
                    /* ── 미구독자 ── */
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                        {/* 상단 2열: CTA + 당원인증 */}
                        <Grid container spacing={3}>
                            <Grid item xs={12} md={6}>
                                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={stagger(0)}>
                                    <SubscriptionCTA
                                        planInfo={planInfo}
                                        testMode={testMode}
                                        onSubscribe={handleStartSubscription}
                                    />
                                </motion.div>
                            </Grid>
                            <Grid item xs={12} md={6}>
                                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={stagger(1)}>
                                    <AuthVerificationCard authStatus={authStatus} onAuthClick={handleAuthClick} />
                                </motion.div>
                            </Grid>
                        </Grid>

                        {/* 하단 2열: 혜택 + 환불 */}
                        <Grid container spacing={3}>
                            <Grid item xs={12} md={6}>
                                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={stagger(2)}>
                                    <BenefitsCard />
                                </motion.div>
                            </Grid>
                            <Grid item xs={12} md={6}>
                                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={stagger(3)}>
                                    <RefundPolicyCard />
                                </motion.div>
                            </Grid>
                        </Grid>
                    </Box>
                ) : (
                    /* ── 구독 중 ── */
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                        {/* 구독 정보 3단 */}
                        <Grid container spacing={3}>
                            <Grid item xs={12} md={4}>
                                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={stagger(0)}>
                                    <SubscriptionInfoCard user={user} planInfo={planInfo} />
                                </motion.div>
                            </Grid>
                            <Grid item xs={12} md={4}>
                                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={stagger(1)}>
                                    <PublishingProgress />
                                </motion.div>
                            </Grid>
                            <Grid item xs={12} md={4}>
                                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={stagger(2)}>
                                    <AuthVerificationCard authStatus={authStatus} onAuthClick={handleAuthClick} compact />
                                </motion.div>
                            </Grid>
                        </Grid>

                        {/* 결제 내역 */}
                        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={stagger(3)}>
                            <PaymentHistoryCard />
                        </motion.div>

                        {/* 구독 관리 */}
                        <Box sx={{ display: 'flex', gap: 2, justifyContent: 'center' }}>
                            <Button
                                variant="outlined"
                                color="error"
                                onClick={() => setCancelDialogOpen(true)}
                                sx={{ borderColor: 'var(--color-error)', color: 'var(--color-error)' }}
                            >
                                구독 해지
                            </Button>
                            <Button
                                variant="outlined"
                                onClick={() => showNotification('결제수단 변경 기능은 준비 중입니다.', 'info')}
                                sx={{ borderColor: 'var(--color-border)', color: 'var(--color-text-secondary)' }}
                            >
                                결제수단 변경
                            </Button>
                        </Box>
                    </Box>
                )}

                {/* 다이얼로그 */}
                <AuthDialog
                    open={authDialogOpen}
                    onClose={() => setAuthDialogOpen(false)}
                    selectedCertFile={selectedCertFile}
                    onCertFileChange={setSelectedCertFile}
                    selectedReceiptFile={selectedReceiptFile}
                    onReceiptFileChange={setSelectedReceiptFile}
                    uploading={uploading}
                    onSubmit={handleAuthSubmit}
                />

                <CancelDialog
                    open={cancelDialogOpen}
                    onClose={() => setCancelDialogOpen(false)}
                    onConfirm={handleCancelSubscription}
                />

                <PaymentDialog
                    open={paymentDialogOpen}
                    onClose={() => setPaymentDialogOpen(false)}
                    selectedPlan={planInfo}
                />

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

export default BillingPage;
