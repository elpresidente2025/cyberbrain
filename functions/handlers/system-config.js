'use strict';

const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');
const { auth } = require('../common/auth');
const { requireRole } = require('../common/rbac');
const { db } = require('../utils/firebaseAdmin');

/**
 * 시스템 설정 조회
 */
exports.getSystemConfig = wrap(async (req) => {
  // 로그인 사용자만 설정 조회 가능
  await auth(req);

  const configDoc = await db.collection('system').doc('config').get();
  const config = configDoc.exists ? configDoc.data() : {};

  // 기본값 설정
  const defaultConfig = {
    aiKeywordRecommendationEnabled: true, // 기본값: 활성화
    lastUpdated: null,
    updatedBy: null
  };

  return ok({
    config: { ...defaultConfig, ...config }
  });
});

/**
 * 시스템 설정 업데이트 (관리자 전용)
 */
exports.updateSystemConfig = wrap(async (req) => {
  const { uid } = await auth(req);
  await requireRole(req, 'admin'); // 관리자만 수정 가능

  const { aiKeywordRecommendationEnabled } = req.data;

  if (typeof aiKeywordRecommendationEnabled !== 'boolean') {
    throw new Error('aiKeywordRecommendationEnabled는 boolean 값이어야 합니다.');
  }

  const configRef = db.collection('system').doc('config');
  await configRef.set({
    aiKeywordRecommendationEnabled,
    lastUpdated: new Date(),
    updatedBy: uid
  }, { merge: true });

  console.log('✅ 시스템 설정 업데이트:', {
    aiKeywordRecommendationEnabled,
    updatedBy: uid
  });

  return ok({
    message: '시스템 설정이 업데이트되었습니다.',
    config: {
      aiKeywordRecommendationEnabled
    }
  });
});
