/**
 * 긴급 관리자 권한 복구 함수
 */

'use strict';

const { onCall, HttpsError } = require('firebase-functions/v2/https');
const admin = require('firebase-admin');
const db = admin.firestore();

exports.emergencyRestoreAdmin = onCall({
  region: 'asia-northeast3',
  cors: true
}, async (request) => {

  // 새로운 uid로 관리자 권한 부여
  const newUid = 'wRk4hx6x8QdTQYoZQu8l';
  const oldUid = 'DIedFGGUOzmoVU1rUWeF';

  // ⚠️ 관리자 권한만 부여하고 기존 프로필 데이터는 보존
  const adminOnlyData = {
    role: 'admin',
    updatedAt: admin.firestore.FieldValue.serverTimestamp()
  };

  try {
    // 새 uid로 관리자 권한 부여 (기존 데이터 보존)
    await db.collection('users').doc(newUid).set(adminOnlyData, { merge: true });

    // 기존 uid로도 관리자 권한 부여 (기존 데이터 보존)
    await db.collection('users').doc(oldUid).set(adminOnlyData, { merge: true });

    return {
      success: true,
      message: '관리자 권한 복구 완료',
      uids: [newUid, oldUid]
    };
  } catch (error) {
    console.error('관리자 권한 복구 실패:', error);
    throw new HttpsError('internal', '복구 실패: ' + error.message);
  }
});
