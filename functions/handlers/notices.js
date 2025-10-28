/**
 * functions/handlers/notices.js
 * 공지사항 관련 함수입니다. (wrap 형식으로 통일)
 */

'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');
const { admin, db } = require('../utils/firebaseAdmin');

// ============================================================================
// 공지사항 생성
// ============================================================================
exports.createNotice = wrap(async (request) => {
  if (!request.auth) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }
  const userDoc = await db.collection('users').doc(request.auth.uid).get();
  if (!userDoc.exists || userDoc.data().role !== 'admin') {
    throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
  }
  const { title, content, type, priority, isActive, expiresAt } = request.data;
  if (!title || !content) {
    throw new HttpsError('invalid-argument', '제목과 내용을 입력해주세요.');
  }
  const noticeData = {
    title: title.trim(),
    content: content.trim(),
    type: type || 'info',
    priority: priority || 'medium',
    isActive: isActive !== false,
    createdBy: request.auth.uid,
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    updatedAt: admin.firestore.FieldValue.serverTimestamp()
  };
  if (expiresAt) {
    noticeData.expiresAt = admin.firestore.Timestamp.fromDate(new Date(expiresAt));
  }
  const docRef = await db.collection('notices').add(noticeData);
  return ok({ noticeId: docRef.id, message: '공지사항이 생성되었습니다.' });
});

// ============================================================================
// 공지사항 수정
// ============================================================================
exports.updateNotice = wrap(async (request) => {
  if (!request.auth) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }
  const userDoc = await db.collection('users').doc(request.auth.uid).get();
  if (!userDoc.exists || userDoc.data().role !== 'admin') {
    throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
  }
  const { noticeId, ...updateData } = request.data;
  if (!noticeId) {
    throw new HttpsError('invalid-argument', '공지 ID가 필요합니다.');
  }
  const updates = {
    ...updateData,
    updatedAt: admin.firestore.FieldValue.serverTimestamp()
  };
  if (updateData.expiresAt) {
    updates.expiresAt = admin.firestore.Timestamp.fromDate(new Date(updateData.expiresAt));
  } else if (updateData.expiresAt === '') {
    updates.expiresAt = admin.firestore.FieldValue.delete();
  }
  await db.collection('notices').doc(noticeId).update(updates);
  return ok({ message: '공지사항이 수정되었습니다.' });
});

// ============================================================================
// 공지사항 삭제
// ============================================================================
exports.deleteNotice = wrap(async (request) => {
  if (!request.auth) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }
  const userDoc = await db.collection('users').doc(request.auth.uid).get();
  if (!userDoc.exists || userDoc.data().role !== 'admin') {
    throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
  }
  const { noticeId } = request.data;
  if (!noticeId) {
    throw new HttpsError('invalid-argument', '공지 ID가 필요합니다.');
  }
  await db.collection('notices').doc(noticeId).delete();
  return ok({ message: '공지사항이 삭제되었습니다.' });
});

// ============================================================================
// 공지사항 목록 조회 (관리자용)
// ============================================================================
exports.getNotices = wrap(async (request) => {
  if (!request.auth) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }
  const userDoc = await db.collection('users').doc(request.auth.uid).get();
  if (!userDoc.exists || userDoc.data().role !== 'admin') {
    throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
  }
  const snapshot = await db.collection('notices').orderBy('createdAt', 'desc').get();
  const notices = [];
  snapshot.docs.forEach(doc => {
    const data = doc.data();
    notices.push({
      id: doc.id,
      ...data,
      createdAt: data.createdAt?.toDate?.().toISOString(),
      updatedAt: data.updatedAt?.toDate?.().toISOString(),
      expiresAt: data.expiresAt?.toDate?.().toISOString()
    });
  });
  return ok({ notices });
});

// ============================================================================
// 활성 공지사항 조회 (일반 사용자용)
// ============================================================================
exports.getActiveNotices = wrap(async (request) => {
  try {
    console.log('🔥 getActiveNotices 시작');
    
    // 단순히 빈 배열 반환으로 테스트
    return ok({ notices: [] });
    
  } catch (error) {
    console.error('❌ getActiveNotices 오류:', error);
    throw new HttpsError('internal', `공지사항 조회 실패: ${error.message}`);
  }
});

// ============================================================================
// 관리자 통계 조회 (관리자용)
// ============================================================================
exports.getAdminStats = wrap(async (request) => {
  if (!request.auth) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }
  const userDoc = await db.collection('users').doc(request.auth.uid).get();
  if (!userDoc.exists || userDoc.data().role !== 'admin') {
    throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
  }

  try {
    console.log('🔥 getAdminStats 시작');

    const now = new Date();
    const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const thirtyMinAgo = new Date(now.getTime() - 30 * 60 * 1000);
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

    // 오늘 생성된 문서 통계
    const postsSnapshot = await db.collection('posts')
      .where('createdAt', '>=', todayStart)
      .get();

    let todaySuccess = 0;
    let todayFail = 0;
    postsSnapshot.forEach(doc => {
      const data = doc.data();
      if (data.status === 'completed') {
        todaySuccess++;
      } else if (data.status === 'failed') {
        todayFail++;
      }
    });

    // 최근 30분 에러 (에러 로그 컬렉션이 있다면)
    let last30mErrors = 0;
    try {
      const errorsSnapshot = await db.collection('errors')
        .where('timestamp', '>=', thirtyMinAgo)
        .get();
      last30mErrors = errorsSnapshot.size;
    } catch (e) {
      console.log('에러 로그 컬렉션 없음, 기본값 사용');
    }

    // 최근 7일간 활성 사용자 (복합 인덱스 불필요하도록 단순화)
    const activeUsersSnapshot = await db.collection('users')
      .where('updatedAt', '>=', sevenDaysAgo)
      .get();

    // 클라이언트 측에서 isActive 필터링
    let activeUsers = 0;
    activeUsersSnapshot.forEach(doc => {
      const data = doc.data();
      if (data.isActive !== false) { // isActive가 false가 아닌 모든 경우 (true 또는 undefined)
        activeUsers++;
      }
    });

    // Gemini 상태
    let geminiStatus = { state: 'active' };
    try {
      const statusDoc = await db.collection('system').doc('gemini_status').get();
      if (statusDoc.exists) {
        const statusData = statusDoc.data();
        geminiStatus = {
          state: statusData.state || 'active',
          // Timestamp를 ISO 문자열로 변환
          lastUpdated: statusData.lastUpdated?.toDate?.()?.toISOString() || null
        };
      }
    } catch (e) {
      console.log('Gemini 상태 문서 없음, 기본값 사용');
    }

    return ok({
      todaySuccess,
      todayFail,
      last30mErrors,
      activeUsers,
      geminiStatus
    });

  } catch (error) {
    console.error('❌ getAdminStats 오류:', error);
    throw new HttpsError('internal', `관리자 통계 조회 실패: ${error.message}`);
  }
});

// ============================================================================
// 에러 로그 조회 (관리자용)
// ============================================================================
exports.getErrorLogs = wrap(async (request) => {
  if (!request.auth) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }
  const userDoc = await db.collection('users').doc(request.auth.uid).get();
  if (!userDoc.exists || userDoc.data().role !== 'admin') {
    throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
  }

  try {
    console.log('🔥 getErrorLogs 시작');

    const snapshot = await db.collection('errors')
      .orderBy('timestamp', 'desc')
      .limit(50)
      .get();

    const errors = [];
    snapshot.forEach(doc => {
      const data = doc.data();
      errors.push({
        id: doc.id,
        ...data,
        timestamp: data.timestamp?.toDate?.().toISOString()
      });
    });

    return ok({ errors });

  } catch (error) {
    console.error('❌ getErrorLogs 오류:', error);
    // 에러 로그 컬렉션이 없는 경우 빈 배열 반환
    return ok({ errors: [] });
  }
});
