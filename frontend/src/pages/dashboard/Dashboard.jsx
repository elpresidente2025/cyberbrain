// frontend/src/pages/dashboard/Dashboard.jsx
// 리팩토링된 대시보드 메인 컴포넌트

import React, { useEffect } from 'react';
import {
    Box,
    Grid,
    Alert,
    Button,
    useTheme,
    useMediaQuery
} from '@mui/material';
import { useAuth } from '../../hooks/useAuth';

// 레이아웃 및 공통 컴포넌트
import DashboardLayout from '../../components/DashboardLayout';
import LoadingState from '../../components/ui/feedback/LoadingState';
import NoticeBanner from '../../components/dashboard/NoticeBanner';
import PostViewerModal from '../../components/PostViewerModal';
import SNSConversionModal from '../../components/SNSConversionModal';
import OnboardingWelcomeModal from '../../components/onboarding/OnboardingWelcomeModal';
import MobileToPCBanner from '../../components/MobileToPCBanner';
import ElectionDDay from '../../components/dashboard/ElectionDDay';

// 대시보드 컴포넌트 & 훅
import { UserStatusCard, NoticeCard, RecentPostsCard } from './components';
import { useDashboardData } from './hooks/useDashboardData';
import { useDashboardActions } from './hooks/useDashboardActions';

const Dashboard = () => {
    const { user } = useAuth();
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down('md'));

    const {
        usage, recentPosts, notices, isLoading, error,
        checkBioAndShowOnboarding, hasCheckedBio
    } = useDashboardData(user);

    const {
        localPosts, viewerOpen, viewerPost, onboardingOpen, setOnboardingOpen,
        snsOpen, snsPost,
        handleGeneratePost, handleViewAllPosts, handlePostClick,
        closeViewer, handleDelete, handleCopy, handleSNSConvert,
        dismissOnboarding, completeOnboarding, closeSns
    } = useDashboardActions(recentPosts);

    // 사용자 정보
    const isAdmin = user?.role === 'admin' || user?.isAdmin === true;
    const isTester = user?.isTester === true;
    const hasBio = user?.bio && user.bio.trim().length > 0;
    const showBioAlert = !hasBio && !isAdmin;
    const canGeneratePost = isAdmin || isTester || (hasBio && usage.postsGenerated < usage.monthlyLimit);

    // Bio 체크 및 온보딩
    useEffect(() => {
        if (user && !isLoading && !hasCheckedBio.current) {
            hasCheckedBio.current = true;
            if (checkBioAndShowOnboarding()) {
                setOnboardingOpen(true);
            }
        }
    }, [user, isLoading, checkBioAndShowOnboarding, hasCheckedBio, setOnboardingOpen]);

    if (isLoading) {
        return (
            <DashboardLayout>
                <LoadingState loading={true} type="fullPage" message="대시보드 로딩 중..." />
            </DashboardLayout>
        );
    }

    if (error) {
        return (
            <DashboardLayout>
                <Box sx={{ py: 4, px: { xs: 2, md: 4 }, maxWidth: '1200px', mx: 'auto' }}>
                    <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>
                    <Button variant="contained" onClick={() => window.location.reload()}>
                        다시 시도
                    </Button>
                </Box>
            </DashboardLayout>
        );
    }

    return (
        <DashboardLayout>
            <Box sx={{ py: 'var(--spacing-xl)', px: { xs: 2, md: 4 }, maxWidth: '1200px', mx: 'auto' }}>
                <NoticeBanner />
                {isMobile && <MobileToPCBanner />}

                <UserStatusCard
                    user={user}
                    usage={usage}
                    isAdmin={isAdmin}
                    isTester={isTester}
                    canGeneratePost={canGeneratePost}
                    showBioAlert={showBioAlert}
                    onGeneratePost={handleGeneratePost}
                />

                <Grid container spacing={3}>
                    <Grid item xs={12} md={8}>
                        <RecentPostsCard
                            posts={localPosts}
                            maxItems={isMobile ? 3 : 5}
                            onViewPost={handlePostClick}
                            onCopyPost={handleCopy}
                            onDeletePost={handleDelete}
                            onSNSConvert={handleSNSConvert}
                            onViewAll={handleViewAllPosts}
                        />
                    </Grid>
                    <Grid item xs={12} md={4}>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                            <ElectionDDay position={user?.position} status={user?.currentStatus} />
                            <NoticeCard notices={notices} maxItems={5} />
                        </Box>
                    </Grid>
                </Grid>
            </Box>

            <PostViewerModal
                open={viewerOpen}
                post={viewerPost}
                onClose={closeViewer}
                onDelete={handleDelete}
                onCopy={handleCopy}
                onSNSConvert={handleSNSConvert}
            />
            <SNSConversionModal open={snsOpen} onClose={closeSns} post={snsPost} />
            <OnboardingWelcomeModal
                open={onboardingOpen}
                onClose={dismissOnboarding}
                onComplete={completeOnboarding}
            />
        </DashboardLayout>
    );
};

export default Dashboard;
