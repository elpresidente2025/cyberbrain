/**
 * functions/handlers/session.js
 * 생성 세션 관리
 */

'use strict';

const { wrapLite } = require('../common/wrap');
const { ok } = require('../common/response');
const { auth } = require('../common/auth');
const { requireAdmin } = require('../common/rbac');
const { db } = require('../utils/firebaseAdmin');

/**
 * 현재 활성 세션 초기화 (새 생성 시작)
 */
exports.resetGenerationSession = wrapLite(async (req) => {
  const { uid } = await auth(req);

  console.log('🔄 [resetGenerationSession] 세션 초기화:', uid);

  await db.collection('users').doc(uid).update({
    activeGenerationSession: null
  });

  console.log('✅ [resetGenerationSession] 세션 초기화 완료:', uid);

  return ok({
    message: '새 생성을 시작할 수 있습니다.',
    success: true
  });
});

/**
 * 현재 세션 상태 조회
 */
exports.getGenerationSession = wrapLite(async (req) => {
  const { uid } = await auth(req);

  const userDoc = await db.collection('users').doc(uid).get();
  if (!userDoc.exists) {
    return ok({ hasSession: false });
  }

  const session = userDoc.data().activeGenerationSession;

  if (!session) {
    return ok({
      hasSession: false,
      message: '활성 세션이 없습니다.'
    });
  }

  return ok({
    hasSession: true,
    session: {
      sessionId: session.sessionId,
      attempts: session.attempts,
      maxAttempts: session.maxAttempts,
      category: session.category,
      topic: session.topic,
      startedAt: session.startedAt
    }
  });
});

/**
 * 특정 사용자의 세션 초기화 (관리자 전용)
 */
exports.adminResetSession = wrapLite(async (req) => {
  const { uid: adminUid } = await auth(req);
  const { targetUserId } = req.data || {};

  await requireAdmin(adminUid);

  if (!targetUserId) {
    throw new Error('targetUserId가 필요합니다.');
  }

  console.log('🔄 [adminResetSession] 세션 초기화:', { adminUid, targetUserId });

  const targetRef = db.collection('users').doc(targetUserId);
  const targetDoc = await targetRef.get();

  if (!targetDoc.exists) {
    throw new Error('대상 사용자를 찾을 수 없습니다.');
  }

  await targetRef.update({
    activeGenerationSession: null
  });

  console.log('✅ [adminResetSession] 세션 초기화 완료:', targetUserId);

  return ok({
    message: `${targetUserId}의 세션이 초기화되었습니다.`,
    success: true
  });
});
