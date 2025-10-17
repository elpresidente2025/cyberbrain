/**
 * handlers/toss-payments.js
 * 토스페이먼츠 결제 처리 관련 함수들
 */

'use strict';

const { onCall, HttpsError } = require('firebase-functions/v2/https');
const { admin, db } = require('../utils/firebaseAdmin');
const axios = require('axios');

// 토스페이먼츠 API 설정
const TOSS_SECRET_KEY = process.env.TOSS_SECRET_KEY;
const TOSS_API_BASE = 'https://api.tosspayments.com/v1';

/**
 * 토스페이먼츠 결제 승인
 */
exports.confirmTossPayment = onCall({
  cors: [
    'https://cyberbrain.kr',
    'https://ai-secretary-6e9c8.web.app',
    'https://ai-secretary-6e9c8.firebaseapp.com'
  ],
  memory: '512MiB',
  timeoutSeconds: 60
}, async (request) => {
  const { paymentKey, orderId, amount } = request.data;
  
  console.log('🔥 confirmTossPayment 시작:', { paymentKey, orderId, amount });
  
  if (!paymentKey || !orderId || !amount) {
    throw new HttpsError('invalid-argument', '결제 정보가 누락되었습니다.');
  }
  
  const uid = request.auth?.uid;
  if (!uid) {
    throw new HttpsError('unauthenticated', '인증이 필요합니다.');
  }
  
  try {
    // 토스페이먼츠 결제 승인 API 호출
    const response = await axios.post(
      `${TOSS_API_BASE}/payments/confirm`,
      {
        paymentKey,
        orderId,
        amount
      },
      {
        headers: {
          'Authorization': `Basic ${Buffer.from(TOSS_SECRET_KEY + ':').toString('base64')}`,
          'Content-Type': 'application/json'
        }
      }
    );
    
    const paymentData = response.data;
    console.log('✅ 토스페이먼츠 승인 성공:', paymentData.paymentKey);
    
    // 결제 정보를 Firestore에 저장
    const paymentRecord = {
      userId: uid,
      paymentKey,
      orderId,
      amount,
      status: paymentData.status,
      method: paymentData.method,
      approvedAt: new Date(paymentData.approvedAt),
      orderName: paymentData.orderName,
      card: paymentData.card || null,
      virtualAccount: paymentData.virtualAccount || null,
      transfer: paymentData.transfer || null,
      receipt: paymentData.receipt || null,
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      rawPaymentData: paymentData
    };
    
    // payments 컬렉션에 저장
    await db.collection('payments').doc(paymentKey).set(paymentRecord);
    
    // 결제 성공 시 사용자 플랜 업데이트
    await updateUserSubscription(uid, orderId, paymentData);
    
    console.log('✅ 결제 처리 완료:', paymentKey);
    
    return {
      success: true,
      payment: {
        paymentKey: paymentData.paymentKey,
        orderId: paymentData.orderId,
        orderName: paymentData.orderName,
        method: paymentData.method,
        totalAmount: paymentData.totalAmount,
        approvedAt: paymentData.approvedAt,
        card: paymentData.card,
        receipt: paymentData.receipt
      }
    };
    
  } catch (error) {
    console.error('❌ 토스페이먼츠 결제 승인 실패:', error.message);
    
    // 토스페이먼츠 API 에러인 경우
    if (error.response?.data) {
      const tossError = error.response.data;
      console.error('토스페이먼츠 에러 상세:', tossError);
      
      // 실패한 결제 정보도 기록
      await db.collection('payment_failures').add({
        userId: uid,
        paymentKey,
        orderId,
        amount,
        errorCode: tossError.code,
        errorMessage: tossError.message,
        createdAt: admin.firestore.FieldValue.serverTimestamp(),
        rawError: tossError
      });
      
      throw new HttpsError('failed-precondition', `결제 승인 실패: ${tossError.message}`);
    }
    
    throw new HttpsError('internal', '결제 처리 중 오류가 발생했습니다.');
  }
});

/**
 * 결제 성공 시 사용자 구독 정보 업데이트
 */
async function updateUserSubscription(uid, orderId, paymentData) {
  try {
    // 주문번호에서 플랜 정보 추출 (예: "전자두뇌비서관 - 리전 인플루언서 (1개월)")
    const orderName = paymentData.orderName || '';
    let planName = '리전 인플루언서'; // 기본값
    let monthlyLimit = 20; // 기본값

    if (orderName.includes('로컬 블로거')) {
      planName = '로컬 블로거';
      monthlyLimit = 8;
    } else if (orderName.includes('리전 인플루언서')) {
      planName = '리전 인플루언서';
      monthlyLimit = 20;
    } else if (orderName.includes('오피니언 리더')) {
      planName = '오피니언 리더';
      monthlyLimit = 60;
    }

    // 사용자 정보 가져오기
    const userRef = db.collection('users').doc(uid);
    const userDoc = await userRef.get();
    const userData = userDoc.data() || {};

    // 현재 시간
    const now = new Date();

    // 다음 결제일 계산 (가입월 M+1월 1일)
    let nextBillingDate;
    if (!userData.subscriptionStartDate) {
      // 첫 결제인 경우: M+1월 1일
      nextBillingDate = new Date(now.getFullYear(), now.getMonth() + 1, 1);
    } else {
      // 이미 구독 중인 경우: 다음 달 1일
      const currentNext = userData.nextBillingDate?.toDate() || now;
      nextBillingDate = new Date(currentNext.getFullYear(), currentNext.getMonth() + 1, 1);
    }

    // 구독 데이터 준비
    const subscriptionData = {
      plan: planName,
      subscription: planName, // 호환성을 위해 둘 다 설정
      subscriptionStatus: 'active',
      monthlyLimit,
      subscriptionStartDate: userData.subscriptionStartDate || admin.firestore.FieldValue.serverTimestamp(),
      nextBillingDate: admin.firestore.Timestamp.fromDate(nextBillingDate),
      lastPaymentAt: admin.firestore.FieldValue.serverTimestamp(),
      lastPaymentAmount: paymentData.totalAmount,
      lastPaymentKey: paymentData.paymentKey,
      updatedAt: admin.firestore.FieldValue.serverTimestamp()
    };

    // 체험 상태였다면 체험 종료
    if (userData.subscriptionStatus === 'trial') {
      subscriptionData.trialEndedAt = admin.firestore.FieldValue.serverTimestamp();
    }

    await userRef.update(subscriptionData);

    // 구독 이력도 기록
    await db.collection('subscription_history').add({
      userId: uid,
      planName,
      monthlyLimit,
      paymentKey: paymentData.paymentKey,
      orderId: paymentData.orderId,
      amount: paymentData.totalAmount,
      status: 'active',
      billingDate: now,
      nextBillingDate: nextBillingDate,
      createdAt: admin.firestore.FieldValue.serverTimestamp()
    });

    console.log('✅ 사용자 구독 정보 업데이트 완료:', {
      uid,
      planName,
      monthlyLimit,
      nextBillingDate: nextBillingDate.toISOString()
    });

  } catch (error) {
    console.error('❌ 사용자 구독 정보 업데이트 실패:', error);
    // 구독 업데이트 실패해도 결제는 성공으로 처리 (수동으로 처리 가능)
  }
}

/**
 * 결제 내역 조회
 */
exports.getUserPayments = onCall({
  cors: true,
  memory: '256MiB',
  timeoutSeconds: 30
}, async (request) => {
  const uid = request.auth?.uid;
  if (!uid) {
    throw new HttpsError('unauthenticated', '인증이 필요합니다.');
  }
  
  try {
    const { limit = 10 } = request.data || {};
    
    const paymentsSnapshot = await db.collection('payments')
      .where('userId', '==', uid)
      .orderBy('createdAt', 'desc')
      .limit(Math.min(limit, 50))
      .get();
    
    const payments = [];
    paymentsSnapshot.forEach(doc => {
      const data = doc.data();
      payments.push({
        id: doc.id,
        paymentKey: data.paymentKey,
        orderId: data.orderId,
        orderName: data.orderName,
        amount: data.amount,
        method: data.method,
        status: data.status,
        approvedAt: data.approvedAt?.toDate?.()?.toISOString(),
        createdAt: data.createdAt?.toDate?.()?.toISOString(),
        receipt: data.receipt
      });
    });
    
    console.log('✅ 결제 내역 조회 완료:', { uid, count: payments.length });
    
    return {
      success: true,
      payments
    };
    
  } catch (error) {
    console.error('❌ 결제 내역 조회 실패:', error);
    throw new HttpsError('internal', '결제 내역 조회에 실패했습니다.');
  }
});