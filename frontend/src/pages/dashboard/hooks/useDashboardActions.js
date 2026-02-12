// frontend/src/pages/dashboard/hooks/useDashboardActions.js
// 대시보드 이벤트 핸들러 커스텀 훅

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useNotification } from '../../../components/ui/feedback/useNotification';
import { callFunctionWithNaverAuth } from '../../../services/firebaseService';

export const useDashboardActions = (recentPosts) => {
    const navigate = useNavigate();
    const { notification, showNotification, hideNotification } = useNotification();

    // 모달 상태
    const [viewerOpen, setViewerOpen] = useState(false);
    const [viewerPost, setViewerPost] = useState(null);
    const [onboardingOpen, setOnboardingOpen] = useState(false);
    const [snsOpen, setSnsOpen] = useState(false);
    const [snsPost, setSnsPost] = useState(null);

    // 로컬 상태 (posts 낙관적 업데이트)
    const [localPosts, setLocalPosts] = useState([]);

    useEffect(() => {
        setLocalPosts(recentPosts);
    }, [recentPosts]);

    // 네비게이션
    const handleGeneratePost = useCallback(() => navigate('/generate'), [navigate]);
    const handleViewAllPosts = useCallback(() => navigate('/posts'), [navigate]);

    // 포스트 보기
    const handlePostClick = useCallback((postId) => {
        const post = localPosts.find(p => p.id === postId);
        if (post) {
            setViewerPost(post);
            setViewerOpen(true);
        }
    }, [localPosts]);

    const closeViewer = useCallback(() => {
        setViewerOpen(false);
        setViewerPost(null);
    }, []);

    // 삭제
    const handleDelete = useCallback(async (postId, e) => {
        if (e) e.stopPropagation();
        if (!postId) return;
        const ok = window.confirm('정말 이 원고를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.');
        if (!ok) return;
        try {
            await callFunctionWithNaverAuth('deletePost', { postId });
            setLocalPosts(prev => prev.filter(p => p.id !== postId));
            showNotification('삭제되었습니다.', 'info');
            if (viewerPost?.id === postId) {
                closeViewer();
            }
        } catch (err) {
            console.error(err);
            showNotification(err.message || '삭제에 실패했습니다.', 'error');
        }
    }, [viewerPost, closeViewer, showNotification]);

    // 복사
    const handleCopy = useCallback((content, e) => {
        if (e) e.stopPropagation();
        try {
            const doc = new DOMParser().parseFromString(content || '', 'text/html');
            const text = doc.body.textContent || '';
            navigator.clipboard.writeText(text);
            showNotification('클립보드에 복사되었습니다!', 'success');
        } catch (err) {
            console.error(err);
            showNotification('복사에 실패했습니다.', 'error');
        }
    }, [showNotification]);

    // SNS 변환
    const handleSNSConvert = useCallback((post, e) => {
        if (e) e.stopPropagation();
        setSnsPost(post);
        setSnsOpen(true);
    }, []);

    // 온보딩
    const dismissOnboarding = useCallback(() => {
        setOnboardingOpen(false);
        sessionStorage.setItem('onboardingDismissed', 'true');
    }, []);

    const completeOnboarding = useCallback(() => {
        setOnboardingOpen(false);
        sessionStorage.setItem('onboardingDismissed', 'true');
        navigate('/profile');
    }, [navigate]);

    return {
        // 상태
        localPosts,
        viewerOpen,
        viewerPost,
        onboardingOpen,
        setOnboardingOpen,
        snsOpen,
        snsPost,

        // 핸들러
        handleGeneratePost,
        handleViewAllPosts,
        handlePostClick,
        closeViewer,
        handleDelete,
        handleCopy,
        handleSNSConvert,
        dismissOnboarding,
        completeOnboarding,
        closeSns: useCallback(() => setSnsOpen(false), [])
    };
};
