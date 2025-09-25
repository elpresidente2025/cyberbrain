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
  try {
    console.log('🔥 getAdminStats 시작');
    
    return ok({ message: '관리자 통계 기능은 현재 구현 중입니다.' });
    
  } catch (error) {
    console.error('❌ getAdminStats 오류:', error);
    throw new HttpsError('internal', `관리자 통계 조회 실패: ${error.message}`);
  }
});

// ============================================================================
// 에러 로그 조회 (관리자용)
// ============================================================================
exports.getErrorLogs = wrap(async (request) => {
  try {
    console.log('🔥 getErrorLogs 시작');
    
    return ok({ message: '에러 로그 기능은 현재 구현 중입니다.' });
    
  } catch (error) {
    console.error('❌ getErrorLogs 오류:', error);
    throw new HttpsError('internal', `에러 로그 조회 실패: ${error.message}`);
  }
});

// ============================================================================
// 공지사항 조회 (관리자용, getActiveNotices와 별도)
// ============================================================================
exports.getNotices = wrap(async (request) => {
  try {
    console.log('🔥 getNotices 시작');
    
    return ok({ notices: [] });
    
  } catch (error) {
    console.error('❌ getNotices 오류:', error);
    throw new HttpsError('internal', `공지사항 조회 실패: ${error.message}`);
  }
});
