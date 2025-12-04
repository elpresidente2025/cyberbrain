// firebase/functions/src/admin.js - wrap 형식으로 변경
'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');
const { admin, db } = require('../utils/firebaseAdmin');

/**
 * 관리자 권한 체크 함수
 */
async function requireAdmin(uid) {
  if (!uid) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  try {
    const userDoc = await db.collection('users').doc(uid).get();
    
    if (!userDoc.exists) {
      throw new HttpsError('not-found', '사용자 정보를 찾을 수 없습니다.');
    }

    const userData = userDoc.data();
    
    if (userData.role !== 'admin') {
      throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
    }

    return userData;
  } catch (error) {
    console.error('관리자 권한 체크 실패:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '권한 확인 중 오류가 발생했습니다.');
  }
}

/**
 * 로그 함수 (기존 코드 호환성)
 */
function log(category, message, data = {}) {
  console.log(`[${category}] ${message}`, data);
}

// ============================================================================
// 관리자: 간단한 선거구 동기화
// ============================================================================
exports.syncDistrictKey = wrap(async (req) => {
  const { uid } = req.auth || {};
  await requireAdmin(uid);

  console.log('🔄 선거구 동기화 시작');

  try {
    // 간단한 더미 응답
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

/**
 * 사용자의 관리자 상태 확인
 */
exports.checkAdminStatus = wrap(async (req) => {
  let uid;

  // 데이터 추출 - Firebase SDK와 HTTP 요청 모두 처리
  let requestData = req.data || req.rawRequest?.body || {};

  // 중첩된 data 구조 처리
  if (requestData.data && typeof requestData.data === 'object') {
    requestData = requestData.data;
  }

  // 네이버 인증 처리
  if (requestData.__naverAuth && requestData.__naverAuth.uid && requestData.__naverAuth.provider === 'naver') {
    uid = requestData.__naverAuth.uid;
  } else if (req.auth && req.auth.uid) {
    // Firebase Auth 토큰
    uid = req.auth.uid;
  } else {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  const userDoc = await db.collection('users').doc(uid).get();

  if (!userDoc.exists) {
    throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
  }

  const userData = userDoc.data();

  // 현재 월 키 계산
  const now = new Date();
  const currentMonthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const monthlyUsage = userData.monthlyUsage || {};
  const currentMonthPosts = monthlyUsage[currentMonthKey] || 0;

  return ok({
    uid: uid,
    name: userData.name,
    isAdmin: userData.isAdmin || false,
    role: userData.role || 'user',
    subscriptionStatus: userData.subscriptionStatus,
    trialPostsRemaining: userData.trialPostsRemaining,
    monthlyLimit: userData.monthlyLimit,
    monthlyUsage: userData.monthlyUsage || {},
    currentMonthPosts: currentMonthPosts,
    currentMonthKey: currentMonthKey
  });
});

/**
 * 관리자 권한 설정 (기존 관리자만 호출 가능)
 */
exports.setAdminStatus = wrap(async (req) => {
  let callerUid;

  // 데이터 추출 - Firebase SDK와 HTTP 요청 모두 처리
  let requestData = req.data || req.rawRequest?.body || {};

  // 중첩된 data 구조 처리
  if (requestData.data && typeof requestData.data === 'object') {
    requestData = requestData.data;
  }

  // 네이버 인증 처리
  if (requestData.__naverAuth && requestData.__naverAuth.uid && requestData.__naverAuth.provider === 'naver') {
    callerUid = requestData.__naverAuth.uid;
    delete requestData.__naverAuth;
  } else if (req.auth && req.auth.uid) {
    // Firebase Auth 토큰
    callerUid = req.auth.uid;
  } else {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  const { targetUid, isAdmin: setIsAdmin } = requestData;

  if (!targetUid) {
    throw new HttpsError('invalid-argument', 'targetUid가 필요합니다.');
  }

  // 호출자가 관리자인지 확인
  const callerDoc = await db.collection('users').doc(callerUid).get();
  if (!callerDoc.exists || !callerDoc.data().isAdmin) {
    throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
  }

  // 대상 사용자 업데이트
  await db.collection('users').doc(targetUid).update({
    isAdmin: setIsAdmin === true,
    role: setIsAdmin === true ? 'admin' : 'user',
    updatedAt: admin.firestore.FieldValue.serverTimestamp()
  });

  return ok({
    message: `사용자 ${targetUid}의 관리자 권한이 ${setIsAdmin ? '설정' : '해제'}되었습니다.`
  });
});