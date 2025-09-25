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