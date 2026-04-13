// frontend/src/pages/profile/ProfilePage.jsx
// 리팩토링된 프로필 페이지 메인 컴포넌트

import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
    Box,
    Grid,
    Alert,
    AlertTitle,
    Container,
    Button
} from '@mui/material';
import {
    Person,
    AutoAwesome,
    Campaign,
    VolunteerActivism,
    Description,
    Save,
    DeleteForever
} from '@mui/icons-material';
import { useAuth } from '../../hooks/useAuth';
import DashboardLayout from '../../components/DashboardLayout';
import UserInfoForm from '../../components/UserInfoForm';
import { LoadingSpinner, LoadingButton } from '../../components/loading';
import { NotificationSnackbar } from '../../components/ui';
import { VALIDATION_RULES } from '../../constants/bio-types';

// 프로필 훅
import { useProfileData } from './hooks/useProfileData';
import { useBioEntries } from './hooks/useBioEntries';
import { useProfileActions } from './hooks/useProfileActions';

// 프로필 컴포넌트
import {
    ProfileHeroCard,
    SectionCard,
    PersonalizationFields,
    CommitteeEditor,
    BioPersonalSection,
    SloganSection,
    DonationSection,
    BioPerformanceSection,
    DeleteAccountDialog,
} from './components';

const CONTAINER_MAX_WIDTH = {
    xs: '100%', sm: '100%', md: '900px',
    lg: '1200px', xl: '1400px', xxl: '1800px', xxxl: '2400px',
};

export default function ProfilePage() {
    const { user, logout } = useAuth();
    const [searchParams] = useSearchParams();
    const showWelcome = searchParams.get('welcome') === '1';

    // 데이터 훅
    const {
        profile, setProfile,
        bioEntries, setBioEntries,
        savedCustomTitle,
        loading, error, setError,
        reloadProfile,
        handleFieldChange,
    } = useProfileData(user);

    // Bio 엔트리 훅
    const {
        handleBioEntryChange,
        getEntriesByCategory,
        addBioEntry,
        removeBioEntry,
    } = useBioEntries(bioEntries, setBioEntries, setProfile, setError);

    // 액션 훅
    const {
        saving, deleting,
        deleteDialogOpen, setDeleteDialogOpen,
        deleteConfirmText, setDeleteConfirmText,
        notification, hideNotification,
        handleSubmit,
        handleCustomTitleSave,
        handlePastPostsIndexing,
        handleDeleteAccount,
        closeDeleteDialog,
    } = useProfileActions(profile, bioEntries, user, reloadProfile, setError);

    if (loading) {
        return (
            <DashboardLayout>
                <Container maxWidth="xl" sx={{ py: 4, maxWidth: CONTAINER_MAX_WIDTH }}>
                    <LoadingSpinner message="프로필 로딩 중..." fullHeight={true} />
                </Container>
            </DashboardLayout>
        );
    }

    const personalEntries = getEntriesByCategory('PERSONAL');
    const performanceEntries = getEntriesByCategory('PERFORMANCE');

    return (
        <DashboardLayout title="프로필 설정">
            <Container maxWidth="xl" sx={{ py: 'var(--spacing-xl)', maxWidth: CONTAINER_MAX_WIDTH }}>
                {/* 히어로 카드 */}
                <ProfileHeroCard
                    user={user}
                    profile={profile}
                    bioEntries={bioEntries}
                    saving={saving}
                    onPastPostsIndexing={handlePastPostsIndexing}
                />

                {/* 온보딩 직후 환영 배너 */}
                {showWelcome && (
                    <Alert
                        severity="info"
                        sx={{ mb: 3, borderRadius: 'var(--radius-lg)' }}
                    >
                        <AlertTitle sx={{ fontWeight: 700 }}>
                            기본 설정이 완료되었습니다
                        </AlertTitle>
                        오른쪽 <strong>자기소개 · 출마선언문</strong> 섹션에 이미 준비해 두신 출마선언문이나 자기소개 글을 그대로 붙여넣어 주세요. 처음에는 짧게 작성해도 괜찮고, 나중에 언제든 보완할 수 있습니다.
                    </Alert>
                )}

                {/* 에러 메시지 */}
                {error && (
                    <Alert severity="error" sx={{ mb: 3, borderRadius: 'var(--radius-lg)' }}>{error}</Alert>
                )}

                {/* 2단 레이아웃: md(900px)부터 */}
                <Grid container spacing={3}>
                    {/* 좌측: 기본 정보 */}
                    <Grid item xs={12} md={6}>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                            {/* 기본 정보 섹션 */}
                            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.2 }}>
                                <SectionCard
                                    icon={<Person />}
                                    title="기본 정보"
                                    subtitle="필수 항목"
                                    titleColor="var(--color-primary)"
                                >
                                    <Grid container spacing={3}>
                                        <UserInfoForm
                                            name={profile.name}
                                            status={profile.status}
                                            customTitle={profile.customTitle}
                                            savedCustomTitle={savedCustomTitle}
                                            position={profile.position}
                                            regionMetro={profile.regionMetro}
                                            regionLocal={profile.regionLocal}
                                            electoralDistrict={profile.electoralDistrict}
                                            targetElection={profile.targetElection}
                                            onChange={handleFieldChange}
                                            onCustomTitleSave={handleCustomTitleSave}
                                            nameDisabled={true}
                                            disabled={saving}
                                            showTitle={false}
                                        />
                                    </Grid>
                                </SectionCard>
                            </motion.div>

                            {/* 개인화 정보 섹션 */}
                            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.3 }}>
                                <SectionCard
                                    icon={<AutoAwesome />}
                                    title="개인화 정보"
                                    subtitle="선택 사항 · 원고 품질 향상"
                                    titleColor="var(--color-primary)"
                                    defaultOpen={false}
                                >
                                    <Grid container spacing={3}>
                                        <PersonalizationFields
                                            profile={profile}
                                            onChange={handleFieldChange}
                                            disabled={saving}
                                        />
                                        <CommitteeEditor
                                            committees={profile.committees}
                                            customCommittees={profile.customCommittees}
                                            onChange={handleFieldChange}
                                            disabled={saving}
                                        />
                                    </Grid>
                                </SectionCard>
                            </motion.div>
                        </Box>
                    </Grid>

                    {/* 우측: Bio + 부가 정보 */}
                    <Grid item xs={12} md={6}>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                            {/* 자기소개 섹션 */}
                            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.25 }}>
                                <SectionCard
                                    icon={<Person />}
                                    title="자기소개 · 출마선언문"
                                    subtitle="필수 항목 · 최소 10자"
                                    titleColor="var(--color-info)"
                                >
                                    <BioPersonalSection
                                        entries={personalEntries}
                                        bioEntries={bioEntries}
                                        onEntryChange={handleBioEntryChange}
                                        onAdd={addBioEntry}
                                        onRemove={removeBioEntry}
                                        disabled={saving}
                                        totalEntries={bioEntries.length}
                                    />
                                </SectionCard>
                            </motion.div>

                            {/* 슬로건 섹션 */}
                            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.3 }}>
                                <SectionCard
                                    icon={<Campaign />}
                                    title="슬로건"
                                    subtitle="선택 · 원고 끝에 자동 삽입"
                                    titleColor="var(--color-warning)"
                                    defaultOpen={!!profile.sloganEnabled}
                                >
                                    <SloganSection
                                        slogan={profile.slogan}
                                        sloganEnabled={profile.sloganEnabled}
                                        onChange={handleFieldChange}
                                        disabled={saving}
                                    />
                                </SectionCard>
                            </motion.div>

                            {/* 후원 안내 섹션 */}
                            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.35 }}>
                                <SectionCard
                                    icon={<VolunteerActivism />}
                                    title="후원 안내"
                                    subtitle="선택 · 슬로건 위에 삽입"
                                    titleColor="var(--color-success)"
                                    defaultOpen={!!profile.donationEnabled}
                                >
                                    <DonationSection
                                        donationInfo={profile.donationInfo}
                                        donationEnabled={profile.donationEnabled}
                                        onChange={handleFieldChange}
                                        disabled={saving}
                                    />
                                </SectionCard>
                            </motion.div>

                            {/* 추가 정보 섹션 */}
                            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.4 }}>
                                <SectionCard
                                    icon={<Description />}
                                    title="추가 정보"
                                    subtitle="정책 · 공약 · 실적 등"
                                    titleColor="var(--color-primary)"
                                    defaultOpen={performanceEntries.some(e => e.content?.trim())}
                                >
                                    <BioPerformanceSection
                                        entries={performanceEntries}
                                        bioEntries={bioEntries}
                                        onEntryChange={handleBioEntryChange}
                                        onAdd={addBioEntry}
                                        onRemove={removeBioEntry}
                                        disabled={saving}
                                        totalEntries={bioEntries.length}
                                    />

                                    {bioEntries.length >= VALIDATION_RULES.maxEntries && (
                                        <Alert severity="info" sx={{ mt: 2 }}>
                                            최대 {VALIDATION_RULES.maxEntries}개의 엔트리까지 추가할 수 있습니다.
                                        </Alert>
                                    )}
                                </SectionCard>
                            </motion.div>
                        </Box>
                    </Grid>
                </Grid>

                {/* 전체 프로필 저장 버튼 */}
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.45 }}>
                    <Box sx={{ mt: 3 }}>
                        <LoadingButton
                            fullWidth
                            variant="contained"
                            onClick={handleSubmit}
                            loading={saving}
                            disabled={saving}
                            startIcon={<Save />}
                            sx={{
                                py: 2,
                                background: 'var(--gradient-primary-dark)',
                                color: '#fff', fontWeight: 700, fontSize: '1.1rem',
                                borderRadius: 'var(--radius-lg)',
                                boxShadow: 'var(--shadow-glow-primary)',
                                border: 'none',
                                '&:hover': {
                                    background: 'var(--gradient-primary)',
                                    transform: 'translateY(-2px)',
                                    boxShadow: 'var(--shadow-xl)',
                                },
                                '&:disabled': {
                                    background: 'var(--color-border)',
                                    color: 'var(--color-text-tertiary)',
                                    boxShadow: 'none',
                                },
                                transition: 'all var(--transition-normal)',
                            }}
                        >
                            전체 프로필 저장
                        </LoadingButton>
                    </Box>
                </motion.div>

                {/* 회원탈퇴 - 작은 텍스트 링크 */}
                <Box sx={{
                    mt: 'var(--spacing-3xl)',
                    pt: 'var(--spacing-lg)',
                    borderTop: '1px solid var(--color-border-light)',
                    textAlign: 'center',
                }}>
                    <Button
                        size="small"
                        startIcon={<DeleteForever sx={{ fontSize: 16 }} />}
                        onClick={() => setDeleteDialogOpen(true)}
                        sx={{
                            color: 'var(--color-text-tertiary)',
                            fontSize: '0.8rem',
                            textTransform: 'none',
                            '&:hover': { color: 'var(--color-error)', bgcolor: 'var(--color-error-light)' },
                        }}
                    >
                        회원탈퇴
                    </Button>
                </Box>

                {/* 알림 스낵바 */}
                <NotificationSnackbar
                    open={notification.open}
                    onClose={hideNotification}
                    message={notification.message}
                    severity={notification.severity}
                    autoHideDuration={6000}
                />

                {/* 다이얼로그 */}
                <DeleteAccountDialog
                    open={deleteDialogOpen}
                    onClose={closeDeleteDialog}
                    confirmText={deleteConfirmText}
                    onConfirmTextChange={setDeleteConfirmText}
                    onDelete={() => handleDeleteAccount(logout)}
                    deleting={deleting}
                />
            </Container>
        </DashboardLayout>
    );
}
