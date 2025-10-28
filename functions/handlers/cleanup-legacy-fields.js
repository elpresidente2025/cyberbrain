/**
 * functions/handlers/cleanup-legacy-fields.js
 *
 * 레거시 필드 제거를 위한 관리자 전용 Cloud Function
 */

'use strict';

const { onCall, HttpsError } = require('firebase-functions/v2/https');
const { admin, db } = require('../utils/firebaseAdmin');
const { logInfo, logError } = require('../common/log');

/**
 * 레거시 district 필드 제거
 * 관리자만 실행 가능
 */
exports.removeLegacyDistrictField = onCall({
  region: 'asia-northeast3',
  cors: true,
  timeoutSeconds: 540, // 9분
}, async (request) => {
  const { auth } = request;

  // 관리자 권한 확인
  if (!auth) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  const userDoc = await db.collection('users').doc(auth.uid).get();
  const userData = userDoc.data();

  if (!userData || userData.role !== 'admin') {
    throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
  }

  logInfo('removeLegacyDistrictField 시작', { adminUid: auth.uid });

  const stats = {
    totalUsers: 0,
    hasDistrictField: 0,
    removed: 0,
    errors: 0,
    details: []
  };

  try {
    const usersSnapshot = await db.collection('users').get();
    stats.totalUsers = usersSnapshot.size;

    const batch = db.batch();
    let operationCount = 0;
    const batchSize = 500;

    for (const userDoc of usersSnapshot.docs) {
      const userId = userDoc.id;
      const userData = userDoc.data();

      if (userData.district !== undefined) {
        stats.hasDistrictField++;

        const detail = {
          userId,
          oldDistrict: userData.district,
          regionMetro: userData.regionMetro || null,
          regionLocal: userData.regionLocal || null,
          electoralDistrict: userData.electoralDistrict || null
        };

        stats.details.push(detail);

        batch.update(userDoc.ref, {
          district: admin.firestore.FieldValue.delete(),
          updatedAt: admin.firestore.FieldValue.serverTimestamp()
        });

        operationCount++;
        stats.removed++;

        // 배치 크기 초과 시 커밋
        if (operationCount >= batchSize) {
          await batch.commit();
          operationCount = 0;
        }
      }
    }

    // 마지막 배치 커밋
    if (operationCount > 0) {
      await batch.commit();
    }

    logInfo('removeLegacyDistrictField 완료', stats);

    return {
      success: true,
      message: `레거시 district 필드 제거 완료`,
      stats: {
        totalUsers: stats.totalUsers,
        hasDistrictField: stats.hasDistrictField,
        removed: stats.removed,
        errors: stats.errors
      },
      details: stats.details
    };

  } catch (error) {
    logError('removeLegacyDistrictField 오류', error);
    stats.errors++;
    throw new HttpsError('internal', `오류 발생: ${error.message}`);
  }
});

/**
 * 레거시 profileImage 필드 제거
 * 관리자만 실행 가능
 * Firebase Auth의 photoURL을 사용하므로 Firestore에 중복 저장할 필요 없음
 */
exports.removeLegacyProfileImage = onCall({
  region: 'asia-northeast3',
  cors: true,
  timeoutSeconds: 540, // 9분
}, async (request) => {
  const { auth } = request;

  // 관리자 권한 확인
  if (!auth) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  const userDoc = await db.collection('users').doc(auth.uid).get();
  const userData = userDoc.data();

  if (!userData || userData.role !== 'admin') {
    throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
  }

  logInfo('removeLegacyProfileImage 시작', { adminUid: auth.uid });

  const stats = {
    totalUsers: 0,
    hasProfileImageField: 0,
    removed: 0,
    errors: 0,
    details: []
  };

  try {
    const usersSnapshot = await db.collection('users').get();
    stats.totalUsers = usersSnapshot.size;

    const batch = db.batch();
    let operationCount = 0;
    const batchSize = 500;

    for (const userDoc of usersSnapshot.docs) {
      const userId = userDoc.id;
      const userData = userDoc.data();

      if (userData.profileImage !== undefined) {
        stats.hasProfileImageField++;

        const detail = {
          userId,
          oldProfileImage: userData.profileImage
        };

        stats.details.push(detail);

        batch.update(userDoc.ref, {
          profileImage: admin.firestore.FieldValue.delete(),
          updatedAt: admin.firestore.FieldValue.serverTimestamp()
        });

        operationCount++;
        stats.removed++;

        // 배치 크기 초과 시 커밋
        if (operationCount >= batchSize) {
          await batch.commit();
          operationCount = 0;
        }
      }
    }

    // 마지막 배치 커밋
    if (operationCount > 0) {
      await batch.commit();
    }

    logInfo('removeLegacyProfileImage 완료', stats);

    return {
      success: true,
      message: `레거시 profileImage 필드 제거 완료`,
      stats: {
        totalUsers: stats.totalUsers,
        hasProfileImageField: stats.hasProfileImageField,
        removed: stats.removed,
        errors: stats.errors
      },
      details: stats.details
    };

  } catch (error) {
    logError('removeLegacyProfileImage 오류', error);
    stats.errors++;
    throw new HttpsError('internal', `오류 발생: ${error.message}`);
  }
});

/**
 * 레거시 isAdmin 필드 제거
 * 관리자만 실행 가능
 * role 필드로 통일하므로 isAdmin 중복 제거
 */
exports.removeLegacyIsAdmin = onCall({
  region: 'asia-northeast3',
  cors: true,
  timeoutSeconds: 540, // 9분
}, async (request) => {
  const { auth } = request;

  // 관리자 권한 확인
  if (!auth) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  const userDoc = await db.collection('users').doc(auth.uid).get();
  const userData = userDoc.data();

  if (!userData || userData.role !== 'admin') {
    throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
  }

  logInfo('removeLegacyIsAdmin 시작', { adminUid: auth.uid });

  const stats = {
    totalUsers: 0,
    hasIsAdminField: 0,
    removed: 0,
    errors: 0,
    details: []
  };

  try {
    const usersSnapshot = await db.collection('users').get();
    stats.totalUsers = usersSnapshot.size;

    const batch = db.batch();
    let operationCount = 0;
    const batchSize = 500;

    for (const userDoc of usersSnapshot.docs) {
      const userId = userDoc.id;
      const userData = userDoc.data();

      if (userData.isAdmin !== undefined) {
        stats.hasIsAdminField++;

        const detail = {
          userId,
          oldIsAdmin: userData.isAdmin,
          role: userData.role
        };

        stats.details.push(detail);

        batch.update(userDoc.ref, {
          isAdmin: admin.firestore.FieldValue.delete(),
          updatedAt: admin.firestore.FieldValue.serverTimestamp()
        });

        operationCount++;
        stats.removed++;

        // 배치 크기 초과 시 커밋
        if (operationCount >= batchSize) {
          await batch.commit();
          operationCount = 0;
        }
      }
    }

    // 마지막 배치 커밋
    if (operationCount > 0) {
      await batch.commit();
    }

    logInfo('removeLegacyIsAdmin 완료', stats);

    return {
      success: true,
      message: `레거시 isAdmin 필드 제거 완료`,
      stats: {
        totalUsers: stats.totalUsers,
        hasIsAdminField: stats.hasIsAdminField,
        removed: stats.removed,
        errors: stats.errors
      },
      details: stats.details
    };

  } catch (error) {
    logError('removeLegacyIsAdmin 오류', error);
    stats.errors++;
    throw new HttpsError('internal', `오류 발생: ${error.message}`);
  }
});
