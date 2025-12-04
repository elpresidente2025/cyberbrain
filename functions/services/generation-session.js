'use strict';

const { admin, db } = require('../utils/firebaseAdmin');
const { HttpsError } = require('firebase-functions/v2/https');

const MAX_ATTEMPTS = 3;
const SESSION_EXPIRY_HOURS = 24;

/**
 * 새로운 생성 세션 생성
 * @param {string} uid - 사용자 ID
 * @returns {Promise<Object>} 생성된 세션 정보
 */
async function createGenerationSession(uid) {
  const sessionId = `sess_${uid}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  const now = admin.firestore.Timestamp.now();
  const expiresAt = admin.firestore.Timestamp.fromMillis(
    now.toMillis() + SESSION_EXPIRY_HOURS * 60 * 60 * 1000
  );

  const session = {
    sessionId,
    userId: uid,
    attempts: 1,
    maxAttempts: MAX_ATTEMPTS,
    createdAt: now,
    expiresAt,
    status: 'active'
  };

  await db.collection('generation_sessions').doc(sessionId).set(session);

  console.log('✅ 새 세션 생성:', { sessionId, userId: uid });

  return {
    sessionId,
    attempts: 1,
    maxAttempts: MAX_ATTEMPTS
  };
}

/**
 * 기존 세션 검증 및 시도 횟수 증가
 * @param {string} sessionId - 세션 ID
 * @param {string} uid - 사용자 ID
 * @returns {Promise<Object>} 업데이트된 세션 정보
 */
async function incrementSessionAttempt(sessionId, uid) {
  const sessionRef = db.collection('generation_sessions').doc(sessionId);
  const sessionDoc = await sessionRef.get();

  if (!sessionDoc.exists) {
    throw new HttpsError('not-found', '유효하지 않은 세션입니다. 새로운 원고를 생성해주세요.');
  }

  const session = sessionDoc.data();

  // 세션 소유자 확인
  if (session.userId !== uid) {
    throw new HttpsError('permission-denied', '세션 접근 권한이 없습니다.');
  }

  // 세션 만료 확인
  const now = admin.firestore.Timestamp.now();
  if (session.status !== 'active' || session.expiresAt.toMillis() < now.toMillis()) {
    throw new HttpsError('failed-precondition', '세션이 만료되었습니다. 새로운 원고를 생성해주세요.');
  }

  // 최대 시도 횟수 확인
  if (session.attempts >= MAX_ATTEMPTS) {
    throw new HttpsError(
      'resource-exhausted',
      `최대 ${MAX_ATTEMPTS}회까지만 재생성할 수 있습니다. 새로운 원고를 생성해주세요.`
    );
  }

  // 시도 횟수 증가
  await sessionRef.update({
    attempts: admin.firestore.FieldValue.increment(1),
    lastAttemptAt: admin.firestore.FieldValue.serverTimestamp()
  });

  const newAttempts = session.attempts + 1;

  console.log('✅ 세션 시도 증가:', { sessionId, attempts: newAttempts, maxAttempts: MAX_ATTEMPTS });

  return {
    sessionId,
    attempts: newAttempts,
    maxAttempts: MAX_ATTEMPTS
  };
}

/**
 * 세션 완료 처리 (저장 시)
 * @param {string} sessionId - 세션 ID
 */
async function completeSession(sessionId) {
  if (!sessionId) return;

  try {
    await db.collection('generation_sessions').doc(sessionId).update({
      status: 'completed',
      completedAt: admin.firestore.FieldValue.serverTimestamp()
    });
    console.log('✅ 세션 완료:', sessionId);
  } catch (error) {
    console.warn('⚠️ 세션 완료 처리 실패 (무시):', error.message);
  }
}

/**
 * 만료된 세션 정리 (Cloud Scheduler로 주기적 실행)
 */
async function cleanupExpiredSessions() {
  const now = admin.firestore.Timestamp.now();
  const expiredSessions = await db.collection('generation_sessions')
    .where('expiresAt', '<', now)
    .where('status', '==', 'active')
    .limit(100)
    .get();

  if (expiredSessions.empty) {
    console.log('ℹ️ 정리할 만료 세션 없음');
    return { cleaned: 0 };
  }

  const batch = db.batch();
  expiredSessions.forEach(doc => {
    batch.update(doc.ref, { status: 'expired' });
  });

  await batch.commit();

  console.log('✅ 만료 세션 정리 완료:', expiredSessions.size);
  return { cleaned: expiredSessions.size };
}

module.exports = {
  createGenerationSession,
  incrementSessionAttempt,
  completeSession,
  cleanupExpiredSessions,
  MAX_ATTEMPTS
};
