'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { db } = require('../utils/firebaseAdmin');

/**
 * 관리자 권한 확인
 */
exports.requireAdmin = async (uid, token) => {
  // Custom Claims 확인
  if (!token?.admin) {
    throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
  }

  // Firestore 문서 확인 (이중 검증)
  try {
    const userDoc = await db.collection('users').doc(uid).get();
    const userData = userDoc.data();

    if (userData?.role !== 'admin') {
      throw new HttpsError('permission-denied', '관리자 권한이 확인되지 않습니다.');
    }
  } catch (error) {
    if (error instanceof HttpsError) throw error;
    console.warn('관리자 권한 Firestore 확인 실패:', error);
    // Custom Claims가 있으면 통과
  }
};