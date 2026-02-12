// frontend/src/pages/profile/hooks/useProfileActions.js
// 프로필 저장, 삭제, 검증 액션

import { useState, useCallback } from 'react';
import { callFunctionWithNaverAuth } from '../../../services/firebaseService';
import { useNotification } from '../../../components/ui';

export function useProfileActions(profile, bioEntries, user, reloadProfile, setError) {
    const [saving, setSaving] = useState(false);
    const [deleting, setDeleting] = useState(false);
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
    const [deleteConfirmText, setDeleteConfirmText] = useState('');
    const [isFirstTimeBioSave, setIsFirstTimeBioSave] = useState(false);
    const [congratulationsOpen, setCongratulationsOpen] = useState(false);

    const { notification, showNotification, hideNotification } = useNotification();

    // 검증
    const validate = useCallback(() => {
        const bioTrim = (profile.bio || '').trim();
        if (!bioTrim) {
            setError('자기소개 및 출마선언문은 필수입니다. 간단히라도 본인을 설명해 주세요.');
            return false;
        }
        if (bioTrim.length < 10) {
            setError('자기소개 및 출마선언문이 너무 짧습니다. 최소 10자 이상 입력해 주세요. (권장: 100~300자)');
            return false;
        }
        if (!profile.name || !profile.position || !profile.regionMetro) {
            setError('모든 필수 정보를 입력해 주세요.');
            return false;
        }
        if (profile.position === '기초자치단체장' && !profile.regionLocal) {
            setError('기초자치단체를 선택해 주세요.');
            return false;
        }
        if (profile.position !== '광역자치단체장' && profile.position !== '기초자치단체장') {
            if (!profile.regionLocal || !profile.electoralDistrict) {
                setError('모든 필수 정보를 입력해 주세요.');
                return false;
            }
        }
        return true;
    }, [profile, setError]);

    // 에러 메시지 해석 헬퍼
    const parseErrorMessage = (e) => {
        const actualMessage = e?.message || e?.details?.message || '';

        if (actualMessage.includes('선거구') || actualMessage.includes('사용 중') || actualMessage.includes('다른 사용자')) {
            return '해당 선거구는 이미 다른 사용자가 사용 중입니다. 다른 선거구를 선택해주세요.';
        }
        if (e.code === 'functions/already-exists') return '해당 선거구에는 이미 등록된 사용자가 있습니다.';
        if (e.code === 'functions/failed-precondition') return actualMessage || '선거구 정보 업데이트에 실패했습니다.';
        if (e.code === 'functions/not-found') return '일시적으로 서비스에 접속할 수 없습니다. 잠시 후 다시 시도해주세요.';
        if (e.code === 'functions/unauthenticated') return '로그인이 만료되었습니다. 다시 로그인해주세요.';
        if (e.code === 'functions/internal') return '서버에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요.';
        if (e.code === 'functions/permission-denied') return '권한이 없습니다. 관리자에게 문의해주세요.';
        if (e.message?.includes('CORS')) return '서비스 연결에 문제가 있습니다. 잠시 후 다시 시도해주세요.';

        return '저장 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.';
    };

    // 전체 프로필 저장
    const handleSubmit = useCallback(async (e) => {
        if (e?.preventDefault) e.preventDefault();
        setError('');

        if (!validate()) return;

        try {
            setSaving(true);

            const hadSufficientBio = user?.bio && user.bio.trim().length >= 200;
            const willHaveSufficientBio = profile.bio && profile.bio.trim().length >= 200;
            const isFirstBioCompletion = !hadSufficientBio && willHaveSufficientBio;

            if (isFirstBioCompletion) setIsFirstTimeBioSave(true);

            const payload = {
                name: profile.name,
                status: profile.status,
                position: profile.position,
                regionMetro: profile.regionMetro,
                regionLocal: profile.regionLocal,
                electoralDistrict: profile.electoralDistrict,
                bio: profile.bio,
                customTitle: profile.customTitle,
                targetElection: profile.targetElection,
                bioEntries,
                ageDecade: profile.ageDecade,
                ageDetail: profile.ageDetail,
                familyStatus: profile.familyStatus,
                backgroundCareer: profile.backgroundCareer,
                localConnection: profile.localConnection,
                politicalExperience: profile.politicalExperience,
                gender: profile.gender,
                committees: profile.committees,
                customCommittees: profile.customCommittees,
                constituencyType: profile.constituencyType,
                slogan: profile.slogan,
                sloganEnabled: profile.sloganEnabled,
                donationInfo: profile.donationInfo,
                donationEnabled: profile.donationEnabled,
            };

            const res = await callFunctionWithNaverAuth('updateProfile', payload);

            if (res) {
                try { await reloadProfile(); } catch (_) { /* 리로드 실패해도 저장은 성공 */ }

                if (isFirstBioCompletion) {
                    setCongratulationsOpen(true);
                } else {
                    showNotification(res.message || '프로필이 저장되었습니다.', 'success');
                }
            } else {
                throw new Error('서버 응답이 올바르지 않습니다.');
            }
        } catch (e) {
            console.error('[updateProfile 오류]', e);
            setError(parseErrorMessage(e));
        } finally {
            setSaving(false);
        }
    }, [profile, bioEntries, user, validate, reloadProfile, setError, showNotification]);

    // 직위 즉시 저장
    const handleCustomTitleSave = useCallback(async (newCustomTitle, action = 'save') => {
        try {
            setSaving(true);
            const res = await callFunctionWithNaverAuth('updateProfile', { customTitle: newCustomTitle });
            if (res) {
                await reloadProfile();
                showNotification(action === 'delete' ? '직위가 삭제되었습니다.' : '직위가 저장되었습니다.', 'success');
            } else {
                throw new Error('서버 응답이 올바르지 않습니다.');
            }
        } catch (e) {
            console.error('[직위 저장 오류]', e);
            setError('직위 저장 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.');
            await reloadProfile();
        } finally {
            setSaving(false);
        }
    }, [reloadProfile, setError, showNotification]);

    // 과거 원고 학습
    const handlePastPostsIndexing = useCallback(async () => {
        try {
            setSaving(true);
            showNotification('과거 원고 학습을 시작합니다. 잠시만 기다려주세요...', 'info');
            const res = await callFunctionWithNaverAuth('indexPastPosts');
            showNotification(
                res?.message || (res?.success ? '과거 원고 학습이 완료되었습니다.' : '학습에 실패했습니다.'),
                res?.success ? 'success' : 'error'
            );
        } catch (e) {
            console.error('[과거 원고 학습 오류]', e);
            showNotification('학습 중 오류가 발생했습니다.', 'error');
        } finally {
            setSaving(false);
        }
    }, [showNotification]);

    // 회원탈퇴
    const handleDeleteAccount = useCallback(async (logout) => {
        if (deleteConfirmText !== '회원탈퇴') {
            showNotification('확인 문구를 정확히 입력해주세요.', 'error');
            return;
        }

        setDeleting(true);
        try {
            await callFunctionWithNaverAuth('deleteUserAccount');
            showNotification('회원탈퇴가 완료되었습니다. 그동안 이용해 주셔서 감사합니다.', 'success');
            setTimeout(async () => {
                try { await logout(); } catch (_) { window.location.href = '/login'; }
            }, 2000);
        } catch (e) {
            console.error('회원탈퇴 오류:', e);
            const msg = e.code === 'unauthenticated' ? '로그인이 필요합니다.' : (e.message || '회원탈퇴 처리 중 오류가 발생했습니다.');
            showNotification(msg, 'error');
        } finally {
            setDeleting(false);
            setDeleteDialogOpen(false);
            setDeleteConfirmText('');
        }
    }, [deleteConfirmText, showNotification]);

    const closeDeleteDialog = useCallback(() => {
        setDeleteDialogOpen(false);
        setDeleteConfirmText('');
    }, []);

    return {
        saving, deleting,
        deleteDialogOpen, setDeleteDialogOpen,
        deleteConfirmText, setDeleteConfirmText,
        isFirstTimeBioSave,
        congratulationsOpen, setCongratulationsOpen,
        notification, showNotification, hideNotification,
        handleSubmit,
        handleCustomTitleSave,
        handlePastPostsIndexing,
        handleDeleteAccount,
        closeDeleteDialog,
    };
}
