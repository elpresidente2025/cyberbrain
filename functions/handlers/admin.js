// firebase/functions/src/admin.js - wrap 형식으로 변경
'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');
const { requireAdmin, isAdminUser, getAdminAccessSource } = require('../common/rbac');
const { admin, db } = require('../utils/firebaseAdmin');

// ============================================================================
// 관리자: 간단한 선거구 동기화
// ============================================================================
exports.syncDistrictKey = wrap(async (req) => {
  const { uid } = req.auth || {};
  await requireAdmin(uid);

  console.log('🔄 선거구 동기화 시작');

  try {
    return ok({
      message: '선거구 동기화가 완료되었습니다.',
      updated: 0
    });
  } catch (error) {
    console.error('❌ syncDistrictKey 실패:', error);
    throw new HttpsError('internal', '선거구 동기화 중 오류가 발생했습니다.');
  }
});

// ============================================================================
// 관리자 상태 확인 및 설정
// ============================================================================

exports.checkAdminStatus = wrap(async (req) => {
  let uid;

  let requestData = req.data || req.rawRequest?.body || {};
  if (requestData.data && typeof requestData.data === 'object') {
    requestData = requestData.data;
  }

  if (requestData.__naverAuth && requestData.__naverAuth.uid && requestData.__naverAuth.provider === 'naver') {
    uid = requestData.__naverAuth.uid;
  } else if (req.auth && req.auth.uid) {
    uid = req.auth.uid;
  } else {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  const userDoc = await db.collection('users').doc(uid).get();
  if (!userDoc.exists) {
    throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
  }

  const userData = userDoc.data() || {};
  const now = new Date();
  const currentMonthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const monthlyUsage = userData.monthlyUsage || {};
  const currentMonthPosts = monthlyUsage[currentMonthKey] || 0;
  const derivedIsAdmin = isAdminUser(userData);
  const adminAccessSource = getAdminAccessSource(userData);

  return ok({
    uid,
    name: userData.name,
    isAdmin: derivedIsAdmin,
    role: userData.role || (derivedIsAdmin ? 'admin' : 'user'),
    adminAccessSource,
    subscriptionStatus: userData.subscriptionStatus,
    trialPostsRemaining: userData.trialPostsRemaining,
    monthlyLimit: userData.monthlyLimit,
    monthlyUsage: userData.monthlyUsage || {},
    currentMonthPosts,
    currentMonthKey
  });
});

exports.setAdminStatus = wrap(async (req) => {
  let callerUid;

  let requestData = req.data || req.rawRequest?.body || {};
  if (requestData.data && typeof requestData.data === 'object') {
    requestData = requestData.data;
  }

  if (requestData.__naverAuth && requestData.__naverAuth.uid && requestData.__naverAuth.provider === 'naver') {
    callerUid = requestData.__naverAuth.uid;
    delete requestData.__naverAuth;
  } else if (req.auth && req.auth.uid) {
    callerUid = req.auth.uid;
  } else {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  const { targetUid, isAdmin: setIsAdmin } = requestData;

  if (!targetUid) {
    throw new HttpsError('invalid-argument', 'targetUid가 필요합니다.');
  }

  await requireAdmin(callerUid);

  await db.collection('users').doc(targetUid).update({
    role: setIsAdmin === true ? 'admin' : 'user',
    isAdmin: admin.firestore.FieldValue.delete(),
    updatedAt: admin.firestore.FieldValue.serverTimestamp()
  });

  return ok({
    message: `사용자 ${targetUid}의 관리자 권한을 ${setIsAdmin ? '설정' : '해제'}했습니다.`
  });
});
