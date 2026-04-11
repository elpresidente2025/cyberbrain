const admin = require('firebase-admin');
const { HttpsError } = require('firebase-functions/v2/https');
const wrap = require('../common/wrap').wrap;
const { auth } = require('../common/auth');
const { requireAdmin } = require('../common/rbac');
const {
  buildDiaryAugmentedCorpus,
  refreshUserStyleFingerprint,
  MIN_CORPUS_LENGTH,
} = require('../services/style-refresh');

const MIN_BIO_STYLE_CONTENT_LENGTH = MIN_CORPUS_LENGTH;

const buildConsolidatedBioContent = (bioData = {}) => {
  const entries = Array.isArray(bioData.entries) ? bioData.entries : [];
  let consolidatedContent = '';

  entries.forEach((entry) => {
    const content = String(entry?.content || '').trim();
    if (!content) return;
    const type = String(entry?.type || 'content').trim().toUpperCase();
    const title = String(entry?.title || '').trim();
    consolidatedContent += `\n[${type}] ${title}: ${content}\n`;
  });

  if (!consolidatedContent.trim()) {
    consolidatedContent = String(bioData.content || '').trim();
  }

  return consolidatedContent.trim();
};

const getAdminRequesterContext = async (uid) => {
  const { userDoc, userData, adminAccessSource } = await requireAdmin(uid);
  return {
    db: admin.firestore(),
    requesterDoc: userDoc,
    userData,
    adminAccessSource
  };
};

// 모든 사용자 조회 (관리자 전용)
const getAllUsers = wrap(async (request) => {
  const { uid } = await auth(request);

  try {
    const { db } = await getAdminRequesterContext(uid);

    // 모든 사용자 조회
    const usersSnapshot = await db.collection('users').orderBy('createdAt', 'desc').get();
    const users = [];
    
    usersSnapshot.forEach(doc => {
      const data = doc.data();
      
      // Timestamp 필드들을 ISO 문자열로 변환
      const convertedData = { ...data };
      if (data.createdAt && data.createdAt.toDate) {
        convertedData.createdAt = data.createdAt.toDate().toISOString();
      }
      if (data.updatedAt && data.updatedAt.toDate) {
        convertedData.updatedAt = data.updatedAt.toDate().toISOString();
      }
      if (data.deactivatedAt && data.deactivatedAt.toDate) {
        convertedData.deactivatedAt = data.deactivatedAt.toDate().toISOString();
      }
      if (data.reactivatedAt && data.reactivatedAt.toDate) {
        convertedData.reactivatedAt = data.reactivatedAt.toDate().toISOString();
      }
      
      users.push({
        uid: doc.id,
        ...convertedData
      });
    });

    return {
      success: true,
      users: users
    };

  } catch (error) {
    console.error('Get all users error:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '사용자 목록 조회 중 오류가 발생했습니다.');
  }
});

// 사용자 계정 비활성화 (관리자 전용)
const deactivateUser = wrap(async (request) => {
  const { uid } = await auth(request);
  const { userId } = request.data;

  if (!userId) {
    throw new HttpsError('invalid-argument', '사용자 ID가 필요합니다.');
  }

  try {
    const { db } = await getAdminRequesterContext(uid);

    // 자기 자신은 비활성화할 수 없음
    if (uid === userId) {
      throw new HttpsError('failed-precondition', '자신의 계정은 비활성화할 수 없습니다.');
    }

    // Firestore에서 사용자 비활성화
    await db.collection('users').doc(userId).update({
      isActive: false,
      deactivatedAt: admin.firestore.FieldValue.serverTimestamp(),
      deactivatedBy: uid
    });

    // Firebase Auth에서 사용자 비활성화
    await admin.auth().updateUser(userId, {
      disabled: true
    });

    console.log(`User ${userId} deactivated by admin ${uid}`);

    return {
      success: true,
      message: '사용자 계정이 비활성화되었습니다.'
    };

  } catch (error) {
    console.error('Deactivate user error:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '계정 비활성화 중 오류가 발생했습니다.');
  }
});

// 사용자 계정 재활성화 (관리자 전용)
const reactivateUser = wrap(async (request) => {
  const { uid } = await auth(request);
  const { userId } = request.data;

  if (!userId) {
    throw new HttpsError('invalid-argument', '사용자 ID가 필요합니다.');
  }

  try {
    const { db } = await getAdminRequesterContext(uid);

    // Firestore에서 사용자 재활성화
    await db.collection('users').doc(userId).update({
      isActive: true,
      reactivatedAt: admin.firestore.FieldValue.serverTimestamp(),
      reactivatedBy: uid
    });

    // Firebase Auth에서 사용자 재활성화
    await admin.auth().updateUser(userId, {
      disabled: false
    });

    console.log(`User ${userId} reactivated by admin ${uid}`);

    return {
      success: true,
      message: '사용자 계정이 재활성화되었습니다.'
    };

  } catch (error) {
    console.error('Reactivate user error:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '계정 재활성화 중 오류가 발생했습니다.');
  }
});

// 사용자 계정 완전 삭제 (관리자 전용)
const deleteUser = wrap(async (request) => {
  const { uid } = await auth(request);
  const { userId } = request.data;

  if (!userId) {
    throw new HttpsError('invalid-argument', '사용자 ID가 필요합니다.');
  }

  try {
    const { db } = await getAdminRequesterContext(uid);

    // 자기 자신은 삭제할 수 없음
    if (uid === userId) {
      throw new HttpsError('failed-precondition', '자신의 계정은 삭제할 수 없습니다.');
    }

    // 삭제 로그를 위해 사용자 정보 백업
    const userDoc = await db.collection('users').doc(userId).get();
    const userDataToDelete = userDoc.data();

    // 관련된 모든 데이터 삭제
    const batch = db.batch();

    // 사용자 프로필 삭제
    batch.delete(db.collection('users').doc(userId));

    // 사용자의 게시물 삭제
    const postsSnapshot = await db.collection('posts').where('userId', '==', userId).get();
    postsSnapshot.forEach(doc => {
      batch.delete(doc.ref);
    });

    // 사용자의 발행 기록 삭제
    const publishingDoc = db.collection('user_publishing').doc(userId);
    if ((await publishingDoc.get()).exists) {
      batch.delete(publishingDoc);
    }

    // 사용자의 바이오 삭제
    const bioDoc = db.collection('bios').doc(userId);
    if ((await bioDoc.get()).exists) {
      batch.delete(bioDoc);
    }

    // 삭제 로그 추가
    batch.set(db.collection('admin_logs').doc(), {
      action: 'USER_DELETED',
      adminId: uid,
      deletedUserId: userId,
      deletedUserData: userDataToDelete,
      timestamp: admin.firestore.FieldValue.serverTimestamp()
    });

    // Firestore 일괄 삭제 실행
    await batch.commit();

    // Firebase Auth에서 사용자 삭제
    await admin.auth().deleteUser(userId);

    console.log(`User ${userId} completely deleted by admin ${uid}`);

    return {
      success: true,
      message: '사용자 계정과 모든 관련 데이터가 삭제되었습니다.'
    };

  } catch (error) {
    console.error('Delete user error:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '계정 삭제 중 오류가 발생했습니다.');
  }
});

// 사용자 바이오 문체 분석 일괄 실행 (관리자 전용)
const batchAnalyzeBioStyles = wrap(async (request) => {
  const { uid } = await auth(request);
  const { db } = await getAdminRequesterContext(uid);

  const requestData = request.data || {};
  const rawLimit = Number.parseInt(requestData.limit, 10);
  const limit = Number.isFinite(rawLimit) ? Math.min(Math.max(rawLimit, 1), 20) : 10;
  const startAfter = String(requestData.startAfter || '').trim();
  const rawMinConfidence = Number.parseFloat(requestData.minConfidence);
  const minConfidence = Number.isFinite(rawMinConfidence)
    ? Math.min(Math.max(rawMinConfidence, 0), 1)
    : 0.7;
  const force = requestData.force === true;
  const useDiary = requestData.useDiary === true;

  let query = db.collection('bios')
    .orderBy(admin.firestore.FieldPath.documentId())
    .limit(limit);

  if (startAfter) {
    query = query.startAfter(startAfter);
  }

  const snapshot = await query.get();
  if (snapshot.empty) {
    return {
      success: true,
      processedCount: 0,
      successCount: 0,
      skippedCount: 0,
      failedCount: 0,
      noContentCount: 0,
      hasMore: false,
      lastUid: '',
      message: '처리할 bio 문서가 없습니다.'
    };
  }

  let successCount = 0;
  let skippedCount = 0;
  let failedCount = 0;
  let noContentCount = 0;
  const failures = [];

  for (const doc of snapshot.docs) {
    const bioData = doc.data() || {};
    const existingConfidence = Number(bioData?.styleFingerprint?.analysisMetadata?.confidence || 0);

    if (!force && existingConfidence >= minConfidence) {
      skippedCount += 1;
      continue;
    }

    let corpusText;
    let corpusSource;
    let corpusStats = null;

    if (useDiary) {
      const corpus = await buildDiaryAugmentedCorpus(doc.id, bioData);
      corpusText = corpus.text;
      corpusSource = corpus.source;
      corpusStats = corpus.stats;
    } else {
      corpusText = buildConsolidatedBioContent(bioData);
      corpusSource = 'bio-only';
      corpusStats = { bioChars: corpusText.length, diaryEntryCount: 0, diaryChars: 0, totalChars: corpusText.length };
    }

    if (!corpusText || corpusText.length < MIN_BIO_STYLE_CONTENT_LENGTH) {
      noContentCount += 1;
      continue;
    }

    const result = await refreshUserStyleFingerprint(doc.id, {
      corpusText,
      source: corpusSource,
      corpusStats,
      userMeta: {
        userName: String(bioData.userName || bioData.name || '').trim(),
        region: String(bioData.region || '').trim(),
      },
    });

    if (result.ok) {
      successCount += 1;
    } else {
      failedCount += 1;
      failures.push({ uid: doc.id, reason: result.reason || 'unknown-error' });
    }
  }

  const lastUid = snapshot.docs[snapshot.docs.length - 1]?.id || '';
  const hasMore = snapshot.docs.length === limit && Boolean(lastUid);

  return {
    success: true,
    processedCount: snapshot.size,
    successCount,
    skippedCount,
    failedCount,
    noContentCount,
    hasMore,
    lastUid,
    failures: failures.slice(0, 10),
    minConfidence,
    force,
    useDiary
  };
});

module.exports = {
  getAllUsers,
  deactivateUser,
  reactivateUser,
  deleteUser,
  batchAnalyzeBioStyles
};
