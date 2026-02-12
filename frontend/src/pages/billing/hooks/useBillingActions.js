// frontend/src/pages/billing/hooks/useBillingActions.js
// 결제 페이지 액션 (인증 제출, 결제, 해지)

import { useState } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../../../services/firebase';
import { useNotification } from '../../../components/ui';

/**
 * 파일을 base64로 변환
 */
const fileToBase64 = (file) =>
    new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = reject;
    });

export default function useBillingActions({ user, refreshUserProfile, testMode }) {
    const { notification, showNotification, hideNotification } = useNotification();
    const [authDialogOpen, setAuthDialogOpen] = useState(false);
    const [paymentDialogOpen, setPaymentDialogOpen] = useState(false);
    const [cancelDialogOpen, setCancelDialogOpen] = useState(false);
    const [selectedCertFile, setSelectedCertFile] = useState(null);
    const [selectedReceiptFile, setSelectedReceiptFile] = useState(null);
    const [uploading, setUploading] = useState(false);

    const handleStartSubscription = () => {
        if (testMode) {
            showNotification('데모 모드에서는 구독을 이용할 수 없습니다. 정식 출시를 기다려 주세요!', 'info');
            return;
        }
        setPaymentDialogOpen(true);
    };

    const handleAuthClick = () => {
        if (user?.faceVerified === true) {
            showNotification('대면 인증이 완료된 계정입니다. 분기별 인증이 영구적으로 면제됩니다.', 'success');
            return;
        }
        if (user?.verificationStatus === 'verified') {
            showNotification('이미 당원 인증이 완료되었습니다. 추가 인증이 필요한 경우 고객센터로 문의해주세요.', 'info');
            return;
        }
        if (user?.verificationStatus === 'pending_manual_review') {
            showNotification('현재 관리자가 제출하신 인증서를 검토 중입니다. 1-2 영업일 내에 완료됩니다.', 'info');
            return;
        }
        setAuthDialogOpen(true);
    };

    const handleAuthSubmit = async () => {
        if (!selectedCertFile && !selectedReceiptFile) {
            showNotification('당적증명서 또는 당비납부 영수증 중 하나 이상 업로드해주세요.', 'warning');
            return;
        }

        setUploading(true);
        try {
            const results = [];

            if (selectedCertFile) {
                const ext = selectedCertFile.name.split('.').pop();
                const base64Data = await fileToBase64(selectedCertFile);
                const verifyPartyCertificate = httpsCallable(functions, 'verifyPartyCertificate');
                const result = await verifyPartyCertificate({
                    userId: user.uid,
                    base64Data,
                    fileName: `${Date.now()}.${ext}`,
                    imageFormat: ext,
                });
                results.push({ type: '당적증명서', result: result.data });
            }

            if (selectedReceiptFile) {
                const ext = selectedReceiptFile.name.split('.').pop();
                const base64Data = await fileToBase64(selectedReceiptFile);
                const verifyPaymentReceipt = httpsCallable(functions, 'verifyPaymentReceipt');
                const result = await verifyPaymentReceipt({
                    userId: user.uid,
                    base64Data,
                    fileName: `${Date.now()}.${ext}`,
                    imageFormat: ext,
                });
                results.push({ type: '당비납부 영수증', result: result.data });
            }

            setAuthDialogOpen(false);
            setSelectedCertFile(null);
            setSelectedReceiptFile(null);

            const successCount = results.filter((r) => r.result.success).length;
            const reviewCount = results.filter((r) => r.result.requiresManualReview).length;

            if (successCount > 0) {
                showNotification(`당원 인증이 완료되었습니다! (${successCount}개 문서 처리 완료)`, 'success');
                if (refreshUserProfile) await refreshUserProfile();
            } else if (reviewCount > 0) {
                showNotification('문서가 수동 검토 대기 중입니다.', 'info');
            } else {
                showNotification('인증 처리 중 문제가 발생했습니다.', 'error');
            }
        } catch (error) {
            console.error('당원 인증 오류:', error);
            showNotification('인증 요청 중 오류가 발생했습니다. 다시 시도해주세요.', 'error');
        } finally {
            setUploading(false);
        }
    };

    const handleCancelSubscription = () => {
        setCancelDialogOpen(false);
        showNotification('구독 해지 요청이 접수되었습니다. 고객센터에서 확인 후 처리해드리겠습니다.', 'info');
    };

    return {
        notification,
        hideNotification,
        showNotification,
        // 다이얼로그 상태
        authDialogOpen,
        setAuthDialogOpen,
        paymentDialogOpen,
        setPaymentDialogOpen,
        cancelDialogOpen,
        setCancelDialogOpen,
        // 파일 업로드
        selectedCertFile,
        setSelectedCertFile,
        selectedReceiptFile,
        setSelectedReceiptFile,
        uploading,
        // 액션
        handleStartSubscription,
        handleAuthClick,
        handleAuthSubmit,
        handleCancelSubscription,
    };
}
