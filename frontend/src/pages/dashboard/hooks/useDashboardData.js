// frontend/src/pages/dashboard/hooks/useDashboardData.js
// 대시보드 데이터 로딩 커스텀 훅

import { useState, useEffect, useCallback } from 'react';
import { callFunctionWithNaverAuth } from '../../../services/firebaseService';

/**
 * 대시보드 데이터 로딩을 담당하는 커스텀 훅
 * @param {Object} user - 현재 사용자 객체
 * @returns {Object} 대시보드 데이터 및 상태
 */
export const useDashboardData = (user) => {
    // 상태 관리
    const [usage, setUsage] = useState({ postsGenerated: 0, monthlyLimit: 50 });
    const [recentPosts, setRecentPosts] = useState([]);
    const [notices, setNotices] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState(null);
    const [testMode, setTestMode] = useState(false);

    // 메인 데이터 로딩 함수
    const fetchDashboardData = useCallback(async () => {
        if (!user?.uid) return;

        setIsLoading(true);
        setError(null);

        try {
            // 병렬로 사용량 정보와 포스트 목록 호출
            const [dashboardData, postsData] = await Promise.all([
                callFunctionWithNaverAuth('getDashboardData'),
                callFunctionWithNaverAuth('getUserPosts')
            ]);

            const postsArray = postsData?.data?.posts || postsData?.posts || [];

            // 사용량 정보 설정
            setUsage(dashboardData.usage || { postsGenerated: 0, monthlyLimit: 50 });

            // 최신순으로 정렬
            const sortedPosts = postsArray.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
            setRecentPosts(sortedPosts);

        } catch (err) {
            console.error('❌ Dashboard: 데이터 요청 실패:', err);

            let errorMessage = '데이터를 불러오는 데 실패했습니다.';
            if (err.code === 'functions/unauthenticated') {
                errorMessage = '로그인이 필요합니다.';
            } else if (err.code === 'functions/internal') {
                errorMessage = '서버에서 오류가 발생했습니다.';
            } else if (err.message) {
                errorMessage = err.message;
            }

            setError(errorMessage);
        } finally {
            setIsLoading(false);
        }
    }, [user?.uid]);

    // 공지사항 로딩 함수
    const fetchNotices = useCallback(async () => {
        if (!user?.uid) return;

        try {
            const noticesResponse = await callFunctionWithNaverAuth('getActiveNotices');
            const noticesData = noticesResponse?.notices || [];
            setNotices(noticesData);
        } catch (noticeError) {
            console.error('❌ 공지사항 로딩 실패:', noticeError);
            setNotices([]);
        }
    }, [user?.uid]);

    // 시스템 설정 로드
    const loadSystemConfig = useCallback(async () => {
        if (!user?.uid) return;

        try {
            const configResponse = await callFunctionWithNaverAuth('getSystemConfig');
            if (configResponse?.config) {
                setTestMode(configResponse.config.testMode || false);
            }
        } catch (error) {
            console.error('시스템 설정 로드 실패:', error);
        }
    }, [user?.uid]);

    // 데이터 로딩 (user가 있을 때)
    useEffect(() => {
        if (user?.uid) {
            console.log('📊 Dashboard: 데이터 로딩 시작');
            fetchDashboardData();
            fetchNotices();
            loadSystemConfig();
        }
    }, [user?.uid, fetchDashboardData, fetchNotices, loadSystemConfig]);

    // 데이터 새로고침 함수
    const refreshData = useCallback(() => {
        fetchDashboardData();
        fetchNotices();
    }, [fetchDashboardData, fetchNotices]);

    return {
        // 데이터
        usage,
        recentPosts,
        notices,
        testMode,

        // 상태
        isLoading,
        error,

        // 액션
        refreshData,
    };
};

export default useDashboardData;
