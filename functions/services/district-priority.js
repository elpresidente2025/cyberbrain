/**
 * functions/services/district-priority.js
 * 결제 기반 우선권 시스템
 *
 * 주요 기능:
 * - 동일 선거구에 여러 사용자 가입 가능
 * - 결제 순서에 따른 우선권 부여
 * - 우선권자 구독 취소 시 자동 재배정
 */

'use strict';

const { admin, db } = require('../utils/firebaseAdmin');
const { districtKey } = require('./district');
const { notifyPriorityChange } = require('./district');
const {
  getDefaultPaidPlan,
  getDefaultPaidPlanMonthlyLimit,
  getTrialMonthlyLimit,
} = require('../common/plan-catalog');

let HttpsError;
try {
  HttpsError = require('firebase-functions/v2/https').HttpsError;
} catch (_) {
  HttpsError = require('firebase-functions').https.HttpsError;
}

const DEFAULT_PAID_PLAN = getDefaultPaidPlan();
const DEFAULT_PAID_MONTHLY_LIMIT = getDefaultPaidPlanMonthlyLimit();
const TRIAL_MONTHLY_LIMIT = getTrialMonthlyLimit();

function parseMonthlyLimit(value) {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

/**
 * 선거구에 사용자 추가 (가입 시)
 * 중복을 허용하며, 트라이얼 상태로 추가
 */
async function addUserToDistrict({ uid, districtKey }) {
  if (!uid || !districtKey) {
    throw new HttpsError('invalid-argument', 'uid와 districtKey가 필요합니다.');
  }

  const districtRef = db.collection('district_claims').doc(districtKey);

  return await db.runTransaction(async (tx) => {
    const districtDoc = await tx.get(districtRef);

    const newMember = {
      userId: uid,
      registeredAt: new Date(),  // 배열 내에서는 serverTimestamp() 사용 불가
      paidAt: null,
      subscriptionStatus: 'trial',
      priority: null,
      isPrimary: false
    };

    if (!districtDoc.exists) {
      // 첫 가입자 - 문서 생성
      tx.set(districtRef, {
        members: [newMember],
        primaryUserId: null,
        totalMembers: 1,
        paidMembers: 0,
        waitlistCount: 1,
        createdAt: admin.firestore.FieldValue.serverTimestamp(),
        lastUpdated: admin.firestore.FieldValue.serverTimestamp()
      });

      console.log('✅ [addUserToDistrict] 첫 가입자 - 선거구 생성:', { uid, districtKey });
    } else {
      // 기존 선거구에 추가
      const data = districtDoc.data();
      const members = data.members || [];

      // 이미 가입되어 있는지 확인
      const existingMember = members.find(m => m.userId === uid);
      if (existingMember) {
        console.log('ℹ️ [addUserToDistrict] 이미 가입된 사용자:', { uid, districtKey });
        return { success: true, alreadyMember: true };
      }

      // 멤버 추가
      members.push(newMember);

      tx.update(districtRef, {
        members,
        totalMembers: members.length,
        waitlistCount: admin.firestore.FieldValue.increment(1),
        lastUpdated: admin.firestore.FieldValue.serverTimestamp()
      });

      console.log('✅ [addUserToDistrict] 선거구에 추가:', {
        uid,
        districtKey,
        totalMembers: members.length
      });
    }

    return { success: true, alreadyMember: false };
  });
}

/**
 * 결제 완료 시 우선권 처리
 */
async function handlePaymentSuccess({ uid, districtKey }) {
  if (!uid || !districtKey) {
    throw new HttpsError('invalid-argument', 'uid와 districtKey가 필요합니다.');
  }

  const districtRef = db.collection('district_claims').doc(districtKey);
  const userRef = db.collection('users').doc(uid);

  return await db.runTransaction(async (tx) => {
    const [districtDoc, userDoc] = await Promise.all([
      tx.get(districtRef),
      tx.get(userRef)
    ]);

    if (!districtDoc.exists) {
      throw new HttpsError('not-found', '선거구 정보를 찾을 수 없습니다.');
    }

    const data = districtDoc.data();
    const members = data.members || [];
    const paidAt = admin.firestore.Timestamp.now();

    // 현재 결제한 사용자가 멤버에 있는지 확인
    const memberIndex = members.findIndex(m => m.userId === uid);
    if (memberIndex === -1) {
      throw new HttpsError('not-found', '선거구 멤버가 아닙니다.');
    }

    // 이미 결제한 사용자인지 확인
    if (members[memberIndex].paidAt) {
      console.log('ℹ️ [handlePaymentSuccess] 이미 결제한 사용자:', uid);
      return {
        success: true,
        isPrimary: members[memberIndex].isPrimary,
        priority: members[memberIndex].priority
      };
    }

    // 현재 결제한 사용자 수 확인
    const paidMembers = members.filter(m => m.paidAt !== null);
    const newPriority = paidMembers.length + 1;

    // 첫 결제자인지 확인
    const isFirstPayer = paidMembers.length === 0;
    const oldPrimaryUserId = data.primaryUserId;

    // members 배열 업데이트
    members[memberIndex] = {
      ...members[memberIndex],
      paidAt,
      subscriptionStatus: 'active',
      priority: newPriority,
      isPrimary: isFirstPayer
    };

    // district_claims 업데이트
    const updateData = {
      members,
      paidMembers: paidMembers.length + 1,
      waitlistCount: admin.firestore.FieldValue.increment(-1),
      lastUpdated: admin.firestore.FieldValue.serverTimestamp()
    };

    if (isFirstPayer) {
      updateData.primaryUserId = uid;
      updateData.priorityHistory = admin.firestore.FieldValue.arrayUnion({
        userId: uid,
        becamePrimaryAt: paidAt,
        reason: 'first_payment'
      });
    }

    tx.update(districtRef, updateData);

    // users 문서 업데이트
    tx.update(userRef, {
      districtPriority: newPriority,
      isPrimaryInDistrict: isFirstPayer,
      districtStatus: isFirstPayer ? 'primary' : 'waiting',
      subscriptionStatus: 'active',
      planId: DEFAULT_PAID_PLAN?.id || null,
      plan: DEFAULT_PAID_PLAN?.name || null,
      'billing.planId': DEFAULT_PAID_PLAN?.id || null,
      'billing.planName': DEFAULT_PAID_PLAN?.name || null,
      'billing.status': 'active',
      'billing.monthlyLimit': DEFAULT_PAID_MONTHLY_LIMIT,
      'billing.updatedAt': admin.firestore.FieldValue.serverTimestamp(),
      paidAt,
      monthlyLimit: isFirstPayer ? DEFAULT_PAID_MONTHLY_LIMIT : 0
    });

    console.log('✅ [handlePaymentSuccess] 결제 처리 완료:', {
      uid,
      districtKey,
      isPrimary: isFirstPayer,
      priority: newPriority,
      totalPaidMembers: paidMembers.length + 1
    });

    return {
      success: true,
      isPrimary: isFirstPayer,
      priority: newPriority,
      totalPaidMembers: paidMembers.length + 1,
      oldPrimaryUserId
    };
  });
}

/**
 * 구독 취소/만료 시 우선권 재배정
 */
async function handleSubscriptionCancellation({ uid, districtKey }) {
  if (!uid || !districtKey) {
    throw new HttpsError('invalid-argument', 'uid와 districtKey가 필요합니다.');
  }

  const districtRef = db.collection('district_claims').doc(districtKey);
  const userRef = db.collection('users').doc(uid);

  return await db.runTransaction(async (tx) => {
    const [districtDoc, userDoc] = await Promise.all([
      tx.get(districtRef),
      tx.get(userRef)
    ]);

    if (!districtDoc.exists) {
      console.warn('⚠️ [handleSubscriptionCancellation] 선거구 정보 없음:', districtKey);
      return { success: false, reason: 'district_not_found' };
    }

    const data = districtDoc.data();
    const members = data.members || [];

    // 취소한 사용자가 우선권자인지 확인
    const wasPrimary = data.primaryUserId === uid;
    const memberIndex = members.findIndex(m => m.userId === uid);

    if (memberIndex === -1) {
      console.warn('⚠️ [handleSubscriptionCancellation] 멤버가 아님:', uid);
      return { success: false, reason: 'not_a_member' };
    }

    // 멤버 상태 업데이트
    members[memberIndex] = {
      ...members[memberIndex],
      subscriptionStatus: 'cancelled',
      isPrimary: false,
      priority: null
    };

    let newPrimaryUserId = null;
    let newPrimaryMemberIndex = -1;

    if (wasPrimary) {
      // 우선권자가 취소한 경우 - 다음 순위자 찾기
      const activePaidMembers = members
        .map((m, idx) => ({ ...m, originalIndex: idx }))
        .filter(m =>
          m.userId !== uid &&
          m.paidAt !== null &&
          m.subscriptionStatus === 'active'
        )
        .sort((a, b) => a.priority - b.priority);

      if (activePaidMembers.length > 0) {
        // 다음 순위자에게 우선권 이전
        const newPrimary = activePaidMembers[0];
        newPrimaryUserId = newPrimary.userId;
        newPrimaryMemberIndex = newPrimary.originalIndex;

        members[newPrimaryMemberIndex] = {
          ...members[newPrimaryMemberIndex],
          isPrimary: true
        };

        console.log('🔄 [handleSubscriptionCancellation] 우선권 이전:', {
          from: uid,
          to: newPrimaryUserId,
          priority: newPrimary.priority
        });
      } else {
        console.log('ℹ️ [handleSubscriptionCancellation] 다음 순위자 없음');
      }
    }

    // district_claims 업데이트
    const updateData = {
      members,
      primaryUserId: newPrimaryUserId,
      paidMembers: admin.firestore.FieldValue.increment(-1),
      lastUpdated: admin.firestore.FieldValue.serverTimestamp()
    };

    if (wasPrimary && newPrimaryUserId) {
      updateData.priorityHistory = admin.firestore.FieldValue.arrayUnion({
        userId: newPrimaryUserId,
        becamePrimaryAt: new Date(),  // 배열 내에서는 serverTimestamp() 사용 불가
        reason: 'previous_cancelled',
        previousUserId: uid
      });
    }

    tx.update(districtRef, updateData);

    // 취소한 사용자 문서 업데이트
    tx.update(userRef, {
      isPrimaryInDistrict: false,
      districtStatus: 'cancelled',
      subscriptionStatus: 'cancelled',
      'billing.status': 'cancelled',
      'billing.updatedAt': admin.firestore.FieldValue.serverTimestamp(),
      monthlyLimit: 0
    });

    // 새 우선권자 문서 업데이트
    if (newPrimaryUserId) {
      const newPrimaryRef = db.collection('users').doc(newPrimaryUserId);
      tx.update(newPrimaryRef, {
        isPrimaryInDistrict: true,
        districtStatus: 'primary',
        'billing.status': 'active',
        'billing.updatedAt': admin.firestore.FieldValue.serverTimestamp(),
        monthlyLimit: DEFAULT_PAID_MONTHLY_LIMIT
      });
    }

    console.log('✅ [handleSubscriptionCancellation] 구독 취소 처리 완료:', {
      uid,
      wasPrimary,
      newPrimaryUserId
    });

    return {
      success: true,
      wasPrimary,
      newPrimaryUserId,
      priorityChanged: wasPrimary
    };
  });
}

/**
 * 선거구 변경 시 처리
 */
async function changeUserDistrict({ uid, oldDistrictKey, newDistrictKey }) {
  if (!uid || !newDistrictKey) {
    throw new HttpsError('invalid-argument', 'uid와 newDistrictKey가 필요합니다.');
  }

  console.log('🔄 [changeUserDistrict] 선거구 변경 시작:', { uid, oldDistrictKey, newDistrictKey });

  // 1. 기존 선거구에서 제거 및 우선권 재배정
  let cancellationResult = null;
  if (oldDistrictKey && oldDistrictKey !== newDistrictKey) {
    cancellationResult = await handleSubscriptionCancellation({
      uid,
      districtKey: oldDistrictKey
    });
  }

  // 2. 새 선거구에 추가
  await addUserToDistrict({ uid, districtKey: newDistrictKey });

  // 3. 유료 사용자인 경우 새 선거구에서도 결제 처리
  const userDoc = await db.collection('users').doc(uid).get();
  const userData = userDoc.data();

  if (userData.subscriptionStatus === 'active' && userData.paidAt) {
    const paymentResult = await handlePaymentSuccess({ uid, districtKey: newDistrictKey });

    // 4. 기존 선거구에서 우선권 변경이 있었다면 알림
    if (cancellationResult?.newPrimaryUserId) {
      await notifyPriorityChange({
        newPrimaryUserId: cancellationResult.newPrimaryUserId,
        oldPrimaryUserId: uid,
        districtKey: oldDistrictKey
      });
    }

    // 5. 새 선거구에서 우선권 획득 시 알림
    if (paymentResult.isPrimary) {
      await notifyPriorityChange({
        newPrimaryUserId: uid,
        oldPrimaryUserId: paymentResult.oldPrimaryUserId,
        districtKey: newDistrictKey
      });
    }
  }

  console.log('✅ [changeUserDistrict] 선거구 변경 완료:', { uid, newDistrictKey });

  return {
    success: true,
    oldDistrictKey,
    newDistrictKey
  };
}

/**
 * 선거구 상태 조회 (정보 최소화 - 인원수 숨김)
 */
async function getDistrictStatus({ districtKey, userId }) {
  if (!districtKey) {
    throw new HttpsError('invalid-argument', 'districtKey가 필요합니다.');
  }

  const doc = await db.collection('district_claims').doc(districtKey).get();

  if (!doc.exists) {
    return {
      exists: false,
      available: true,
      message: '사용 가능한 선거구입니다.'
    };
  }

  const data = doc.data();

  // 요청한 사용자의 정보만 반환
  if (userId) {
    const member = data.members?.find(m => m.userId === userId);
    if (member) {
      return {
        exists: true,
        isMember: true,
        isPrimary: member.isPrimary,
        priority: member.priority,
        subscriptionStatus: member.subscriptionStatus,
        message: member.isPrimary
          ? '회원님은 이 선거구의 우선권자입니다.'
          : '현재 이 선거구는 다른 사용자가 이용 중입니다.'
      };
    }
  }

  // 비회원 또는 타인이 조회 시 - 최소 정보만
  return {
    exists: true,
    available: !data.primaryUserId,  // 우선권자 없으면 사용 가능
    hasPrimary: !!data.primaryUserId,
    message: data.primaryUserId
      ? '이 선거구에는 다른 사용자가 있습니다. 가입 후 결제하시면 대기 순번을 확보하실 수 있습니다.'
      : '가장 먼저 결제하시면 우선권을 획득하실 수 있습니다.'
  };
}

/**
 * 콘텐츠 생성 권한 확인
 */
async function checkGenerationPermission({ uid }) {
  const userDoc = await db.collection('users').doc(uid).get();
  if (!userDoc.exists) {
    throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
  }

  const userData = userDoc.data();

  // 0. 관리자는 모든 제한 스킵 (무제한)
  if (userData.role === 'admin') {
    console.log('✅ 관리자 권한 - 사용량 무제한:', uid);
    return { allowed: true, reason: 'admin', remaining: 999 };
  }

  // 0-1. 테스터는 무료 체험 제한 스킵, 유료 사용자와 동일한 90회/월 제한 적용
  if (userData.role === 'tester') {
    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const monthlyUsage = userData.monthlyUsage || {};
    const used = monthlyUsage[currentMonth] || 0;
    const limit = DEFAULT_PAID_MONTHLY_LIMIT;

    if (used >= limit) {
      return {
        allowed: false,
        reason: 'monthly_limit_exceeded',
        message: `이번 달 생성 한도(${limit}회)를 모두 사용했습니다.`
      };
    }

    console.log('✅ 테스터 권한 - 유료 사용자 기준 적용:', { uid, used, limit, remaining: limit - used });
    return { allowed: true, reason: 'tester', remaining: limit - used };
  }

  // 1. 무료 체험 사용자 (우선권 체크 없이 통과)
  if (userData.subscriptionStatus === 'trial' || !userData.subscriptionStatus) {
    // generationsRemaining이 undefined인 경우 = 레거시 사용자, 8회로 초기화
    const remaining = userData.generationsRemaining !== undefined
      ? userData.generationsRemaining
      : (userData.trialPostsRemaining !== undefined ? userData.trialPostsRemaining : TRIAL_MONTHLY_LIMIT);

    if (remaining <= 0) {
      return {
        allowed: false,
        reason: 'trial_exhausted',
        message: '무료 체험 횟수를 모두 사용했습니다. 결제하시면 계속 이용하실 수 있습니다.'
      };
    }
    return { allowed: true, reason: 'trial', remaining };
  }

  // 2. 구독 상태 확인
  if (userData.subscriptionStatus === 'cancelled' || userData.subscriptionStatus === 'expired') {
    return {
      allowed: false,
      reason: 'subscription_inactive',
      message: '구독이 만료되었습니다. 구독을 갱신해주세요.'
    };
  }

  // 3. 유료 사용자 - 우선권 확인 (명시적으로 false인 경우만 차단)
  // isPrimaryInDistrict가 undefined인 경우는 마이그레이션 전이므로 통과
  if (userData.isPrimaryInDistrict === false) {
    return {
      allowed: false,
      reason: 'not_primary',
      message: '현재 이 선거구는 다른 사용자가 우선권을 보유 중입니다.',
      suggestion: '다른 선거구로 변경하시면 즉시 이용하실 수 있습니다.'
    };
  }

  // 4. 우선권자 또는 마이그레이션 전 사용자 - 월 사용량 확인
  const now = new Date();
  const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const monthlyUsage = userData.monthlyUsage || {};
  const used = monthlyUsage[currentMonth] || 0;
  const limit = parseMonthlyLimit(userData.monthlyLimit) ?? DEFAULT_PAID_MONTHLY_LIMIT;

  if (used >= limit) {
    return {
      allowed: false,
      reason: 'monthly_limit_exceeded',
      message: `이번 달 생성 한도(${limit}회)를 모두 사용했습니다.`
    };
  }

  return {
    allowed: true,
    reason: userData.isPrimaryInDistrict === true ? 'primary' : 'legacy',
    remaining: limit - used
  };
}

module.exports = {
  addUserToDistrict,
  handlePaymentSuccess,
  handleSubscriptionCancellation,
  changeUserDistrict,
  getDistrictStatus,
  checkGenerationPermission
};
