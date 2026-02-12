// frontend/src/pages/billing/hooks/useBillingData.js
// 결제 페이지 상태 관리

import { useState, useEffect } from 'react';
import { useAuth } from '../../../hooks/useAuth';
import { callFunctionWithNaverAuth } from '../../../services/firebaseService';

/**
 * 당원 인증 상태 판단
 */
const getAuthStatus = (user) => {
    if (user?.faceVerified === true) {
        return {
            status: 'active',
            image: '/buttons/AuthPass.png',
            title: '대면 인증 완료',
            message: '관리자에 의해 대면 인증이 완료되었습니다',
        };
    }
    if (user?.verificationStatus === 'verified' && user?.lastVerification) {
        return {
            status: 'active',
            image: '/buttons/AuthPass.png',
            title: '인증 완료',
            message: `${user.lastVerification.quarter} 인증 완료`,
        };
    }
    if (user?.verificationStatus === 'pending_manual_review') {
        return {
            status: 'pending',
            image: '/buttons/AuthFail.png',
            title: '수동 검토 대기 중',
            message: '관리자가 확인 중입니다. 1-2 영업일 소요됩니다.',
        };
    }
    return {
        status: 'warning',
        image: '/buttons/AuthFail.png',
        title: '인증 필요',
        message: '당원 인증이 필요합니다',
    };
};

const PLAN_INFO = {
    name: '공식 파트너십',
    price: 55000,
    monthlyLimit: 90,
    features: [
        '월 90회 원고 생성',
        'SNS 원고 무료 생성',
        '최대 3회 재생성',
        '더불어민주당 당원 전용',
    ],
};

export default function useBillingData() {
    const { user, refreshUserProfile } = useAuth();
    const [testMode, setTestMode] = useState(false);
    const [adminOverrideSubscription, setAdminOverrideSubscription] = useState(null);

    const isAdmin = user?.role === 'admin';
    const isSubscribed = adminOverrideSubscription !== null
        ? adminOverrideSubscription
        : user?.subscriptionStatus === 'active';
    const authStatus = getAuthStatus(user);

    useEffect(() => {
        const loadSystemConfig = async () => {
            try {
                const configResponse = await callFunctionWithNaverAuth('getSystemConfig');
                if (configResponse?.config) {
                    setTestMode(configResponse.config.testMode || false);
                }
            } catch (error) {
                console.error('시스템 설정 로드 실패:', error);
            }
        };
        loadSystemConfig();
    }, []);

    return {
        user,
        refreshUserProfile,
        testMode,
        isAdmin,
        isSubscribed,
        adminOverrideSubscription,
        setAdminOverrideSubscription,
        authStatus,
        planInfo: PLAN_INFO,
    };
}
