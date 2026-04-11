/**
 * functions/handlers/payment.js
 * 결제 관련 핸들러
 */

'use strict';

const { wrap, wrapLite } = require('../common/wrap');
const { ok } = require('../common/response');
const { auth } = require('../common/auth');
const { HttpsError } = require('firebase-functions/v2/https');
const { db } = require('../utils/firebaseAdmin');
const { resolvePaidPlan, getUserMonthlyLimit, getTrialMonthlyLimit } = require('../common/plan-catalog');
const {
  handlePaymentSuccess,
  handleSubscriptionCancellation
} = require('../services/district-priority');
const { notifyPriorityChange } = require('../services/district');

/**
 * 결제 완료 처리 (Naver Pay 콜백 또는 수동 호출)
 */
exports.processPayment = wrap(async (req) => {
  const { uid } = await auth(req);
  const { planId, plan } = req.data || {};
  const selectedPlan = resolvePaidPlan(planId || plan);

  if (!selectedPlan) {
    throw new HttpsError('invalid-argument', '유효한 플랜을 선택해주세요.');
  }

  console.log('💳 [processPayment] 결제 처리 시작:', {
    uid,
    planId: selectedPlan.id,
    planName: selectedPlan.name,
  });

  // 1. 사용자 정보 조회
  const userDoc = await db.collection('users').doc(uid).get();
  if (!userDoc.exists) {
    throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
  }

  const userData = userDoc.data();
  const districtKey = userData.districtKey;

  if (!districtKey) {
    throw new HttpsError('invalid-argument', '선거구 정보가 없습니다. 프로필을 먼저 설정해주세요.');
  }

  // 2. 선거구 우선권 처리
  const priorityResult = await handlePaymentSuccess({ uid, districtKey });

  console.log('✅ [processPayment] 우선권 처리 결과:', priorityResult);

  // 3. 우선권 획득 시 알림 발송
  if (priorityResult.isPrimary) {
    await notifyPriorityChange({
      newPrimaryUserId: uid,
      oldPrimaryUserId: priorityResult.oldPrimaryUserId,
      districtKey
    });
  }

  // 4. 응답 메시지 생성
  let message = '결제가 완료되었습니다.';
  if (priorityResult.isPrimary) {
    message += ' 선거구 우선권을 획득했습니다!';
  } else {
    message += ` 현재 대기 순번: ${priorityResult.priority}번`;
  }

  return ok({
    message,
    isPrimary: priorityResult.isPrimary,
    priority: priorityResult.priority,
    districtKey
  });
});

/**
 * 구독 취소 처리
 */
exports.cancelSubscription = wrap(async (req) => {
  const { uid } = await auth(req);
  const { reason } = req.data || {};

  console.log('❌ [cancelSubscription] 구독 취소 시작:', { uid, reason });

  // 1. 사용자 정보 조회
  const userDoc = await db.collection('users').doc(uid).get();
  if (!userDoc.exists) {
    throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
  }

  const userData = userDoc.data();
  const districtKey = userData.districtKey;

  if (!districtKey) {
    throw new HttpsError('invalid-argument', '선거구 정보가 없습니다.');
  }

  // 2. 선거구 우선권 재배정
  const cancellationResult = await handleSubscriptionCancellation({ uid, districtKey });

  console.log('✅ [cancelSubscription] 우선권 재배정 결과:', cancellationResult);

  // 3. 우선권 변경 시 알림 발송
  if (cancellationResult.priorityChanged && cancellationResult.newPrimaryUserId) {
    await notifyPriorityChange({
      newPrimaryUserId: cancellationResult.newPrimaryUserId,
      oldPrimaryUserId: uid,
      districtKey
    });
  }

  // 4. 응답 메시지 생성
  let message = '구독이 취소되었습니다.';
  if (cancellationResult.wasPrimary && cancellationResult.newPrimaryUserId) {
    message += ' 우선권이 다음 순위자에게 이전되었습니다.';
  }

  return ok({
    message,
    wasPrimary: cancellationResult.wasPrimary,
    newPrimaryUserId: cancellationResult.newPrimaryUserId
  });
});

/**
 * 결제/우선권 상태 조회
 */
exports.getPaymentStatus = wrapLite(async (req) => {
  const { uid } = await auth(req);

  const userDoc = await db.collection('users').doc(uid).get();
  if (!userDoc.exists) {
    throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
  }

  const userData = userDoc.data();
  const districtKey = userData.districtKey;

  if (!districtKey) {
    return ok({
      hasDistrict: false,
      message: '선거구 정보가 없습니다.'
    });
  }

  // 선거구 정보 조회
  const districtDoc = await db.collection('district_claims').doc(districtKey).get();

  if (!districtDoc.exists) {
    return ok({
      hasDistrict: true,
      districtKey,
      isPrimary: false,
      subscriptionStatus: userData.subscriptionStatus,
      message: '선거구 정보를 찾을 수 없습니다.'
    });
  }

  const districtData = districtDoc.data();
  const member = districtData.members?.find(m => m.userId === uid);

  return ok({
    hasDistrict: true,
    districtKey,
    isPrimary: userData.isPrimaryInDistrict || false,
    priority: userData.districtPriority || null,
    districtStatus: userData.districtStatus || 'unknown',
    subscriptionStatus: userData.subscriptionStatus || 'trial',
    paidAt: member?.paidAt || null,
    monthlyLimit: getUserMonthlyLimit(userData, getTrialMonthlyLimit()),
    message: userData.isPrimaryInDistrict
      ? '우선권을 보유 중입니다.'
      : '대기 중입니다.'
  });
});
