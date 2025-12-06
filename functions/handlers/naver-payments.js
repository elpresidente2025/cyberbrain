/**
 * handlers/naver-payments.js
 * 네이버페이 결제 처리 관련 함수들
 */

'use strict';

const { onCall, HttpsError } = require('firebase-functions/v2/https');
const { admin, db } = require('../utils/firebaseAdmin');
const axios = require('axios');

// 네이버페이 API 설정
const NAVER_CLIENT_ID = process.env.NAVER_CLIENT_ID;
const NAVER_CLIENT_SECRET = process.env.NAVER_CLIENT_SECRET;
const NAVER_PARTNER_ID = process.env.NAVER_PARTNER_ID;

/**
 * 네이버페이 결제 시작
 */
exports.initiateNaverPayment = onCall({
  cors: [
    'https://cyberbrain.kr',
    'https://ai-secretary-6e9c8.web.app',
    'https://ai-secretary-6e9c8.firebaseapp.com'
  ],
  memory: '512MiB',
  timeoutSeconds: 60
}, async (request) => {
  const { amount, orderId, orderName, customerEmail, customerName, successUrl, failUrl } = request.data;

  console.log('🔥 initiateNaverPayment 시작:', { orderId, amount, orderName });

  if (!amount || !orderId || !orderName) {
    throw new HttpsError('invalid-argument', '결제 정보가 누락되었습니다.');
  }

  const uid = request.auth?.uid;
  if (!uid) {
    throw new HttpsError('unauthenticated', '인증이 필요합니다.');
  }

  try {
    // 네이버페이 결제 준비 API 호출
    // 실제 API 스펙에 맞게 수정 필요
    const response = await axios.post(
      'https://dev.apis.naver.com/naverpay-partner/naverpay/payments/v2.2/reserve',
      {
        merchantPayKey: orderId,
        productName: orderName,
        totalPayAmount: amount,
        returnUrl: successUrl,
        // 추가 파라미터들
      },
      {
        headers: {
          'X-Naver-Client-Id': NAVER_CLIENT_ID,
          'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
          'Content-Type': 'application/json'
        }
      }
    );

    const paymentData = response.data;
    console.log('✅ 네이버페이 결제 준비 성공:', paymentData);

    // 결제 준비 정보를 Firestore에 저장
    await db.collection('payment_reserves').doc(orderId).set({
      userId: uid,
      orderId,
      amount,
      orderName,
      customerEmail,
      customerName,
      status: 'reserved',
      reservedAt: admin.firestore.FieldValue.serverTimestamp(),
      paymentData
    });

    console.log('✅ 결제 준비 완료:', orderId);

    return {
      success: true,
      paymentUrl: paymentData.paymentUrl || paymentData.redirectUrl,
      reserveId: paymentData.reserveId
    };

  } catch (error) {
    console.error('❌ 네이버페이 결제 준비 실패:', error.message);

    // 네이버페이 API 에러인 경우
    if (error.response?.data) {
      const naverError = error.response.data;
      console.error('네이버페이 에러 상세:', naverError);

      throw new HttpsError('failed-precondition', `결제 준비 실패: ${naverError.message || naverError.body?.message}`);
    }

    throw new HttpsError('internal', '결제 처리 중 오류가 발생했습니다.');
  }
});

/**
 * 네이버페이 결제 승인
 */
exports.confirmNaverPayment = onCall({
  cors: [
    'https://cyberbrain.kr',
    'https://ai-secretary-6e9c8.web.app',
    'https://ai-secretary-6e9c8.firebaseapp.com'
  ],
  memory: '512MiB',
  timeoutSeconds: 60
}, async (request) => {
  const { orderId, paymentId } = request.data;

  console.log('🔥 confirmNaverPayment 시작:', { orderId, paymentId });

  if (!orderId || !paymentId) {
    throw new HttpsError('invalid-argument', '결제 정보가 누락되었습니다.');
  }

  const uid = request.auth?.uid;
  if (!uid) {
    throw new HttpsError('unauthenticated', '인증이 필요합니다.');
  }

  try {
    // 네이버페이 결제 승인 API 호출
    const response = await axios.post(
      `https://dev.apis.naver.com/naverpay-partner/naverpay/payments/v2.2/apply/payment`,
      {
        merchantPayKey: orderId,
        paymentId
      },
      {
        headers: {
          'X-Naver-Client-Id': NAVER_CLIENT_ID,
          'X-Naver-Client-Secret': NAVER_CLIENT_SECRET,
          'Content-Type': 'application/json'
        }
      }
    );

    const paymentData = response.data;
    console.log('✅ 네이버페이 승인 성공:', paymentData);

    // 결제 정보를 Firestore에 저장
    const paymentRecord = {
      userId: uid,
      orderId,
      paymentId,
      amount: paymentData.body?.totalPayAmount || 0,
      status: 'completed',
      method: 'naverpay',
      approvedAt: new Date(),
      orderName: paymentData.body?.productName || '',
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      rawPaymentData: paymentData
    };

    // payments 컬렉션에 저장
    await db.collection('payments').doc(orderId).set(paymentRecord);

    // 결제 성공 시 사용자 플랜 업데이트
    await updateUserSubscription(uid, orderId, paymentData);

    console.log('✅ 결제 처리 완료:', orderId);

    return {
      success: true,
      payment: {
        orderId,
        paymentId,
        orderName: paymentData.body?.productName,
        totalAmount: paymentData.body?.totalPayAmount,
        approvedAt: new Date().toISOString()
      }
    };

  } catch (error) {
    console.error('❌ 네이버페이 결제 승인 실패:', error.message);

    // 네이버페이 API 에러인 경우
    if (error.response?.data) {
      const naverError = error.response.data;
      console.error('네이버페이 에러 상세:', naverError);

      // 실패한 결제 정보도 기록
      await db.collection('payment_failures').add({
        userId: uid,
        orderId,
        paymentId,
        errorCode: naverError.code,
        errorMessage: naverError.message || naverError.body?.message,
        createdAt: admin.firestore.FieldValue.serverTimestamp(),
        rawError: naverError
      });

      throw new HttpsError('failed-precondition', `결제 승인 실패: ${naverError.message || naverError.body?.message}`);
    }

    throw new HttpsError('internal', '결제 처리 중 오류가 발생했습니다.');
  }
});

/**
 * 결제 성공 시 사용자 구독 정보 업데이트
 */
async function updateUserSubscription(uid, orderId, paymentData) {
  try {
    // 주문번호에서 플랜 정보 추출
    const orderName = paymentData.body?.productName || '';
    const planName = '공식 파트너십';
    const monthlyLimit = 90; // 공식 파트너십: 월 90회

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
      lastPaymentAmount: paymentData.body?.totalPayAmount || 55000,
      lastPaymentKey: orderId,
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
      paymentKey: orderId,
      orderId: orderId,
      amount: paymentData.body?.totalPayAmount || 55000,
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
        orderId: data.orderId,
        orderName: data.orderName,
        amount: data.amount,
        method: data.method,
        status: data.status,
        approvedAt: data.approvedAt?.toDate?.()?.toISOString(),
        createdAt: data.createdAt?.toDate?.()?.toISOString()
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
