'use strict';

const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');
const { auth } = require('../common/auth');
const { requireAdmin } = require('../common/rbac');
const { db } = require('../utils/firebaseAdmin');

/**
 * 시스템 설정 조회
 */
exports.getSystemConfig = wrap(async (req) => {
  // 로그인 사용자만 설정 조회 가능
  await auth(req);

  const configDoc = await db.collection('system').doc('config').get();
  const rawConfig = configDoc.exists ? configDoc.data() : {};

  // Timestamp를 ISO 문자열로 변환
  const config = {
    aiKeywordRecommendationEnabled: rawConfig.aiKeywordRecommendationEnabled ?? true,
    testMode: rawConfig.testMode ?? false,
    testModeSettings: rawConfig.testModeSettings || {
      freeMonthlyLimit: 8
    },
    lastUpdated: rawConfig.lastUpdated?.toDate?.()?.toISOString() || null,
    updatedBy: rawConfig.updatedBy || null
  };

  return ok({ config });
});

/**
 * 시스템 설정 업데이트 (관리자 전용)
 */
exports.updateSystemConfig = wrap(async (req) => {
  const { uid, token } = await auth(req);
  await requireAdmin(uid, token); // 관리자만 수정 가능

  const { aiKeywordRecommendationEnabled, testMode, testModeSettings } = req.data;

  const updates = {
    lastUpdated: new Date(),
    updatedBy: uid
  };

  // aiKeywordRecommendationEnabled 업데이트
  if (typeof aiKeywordRecommendationEnabled === 'boolean') {
    updates.aiKeywordRecommendationEnabled = aiKeywordRecommendationEnabled;
  }

  // testMode 업데이트
  if (typeof testMode === 'boolean') {
    updates.testMode = testMode;

    // testMode 변경 시 활성화 정보 기록
    if (testMode) {
      updates.testModeSettings = {
        freeMonthlyLimit: testModeSettings?.freeMonthlyLimit || 8,
        enabledAt: new Date(),
        enabledBy: uid
      };
    }
  }

  const configRef = db.collection('system').doc('config');
  await configRef.set(updates, { merge: true });

  console.log('✅ 시스템 설정 업데이트:', {
    ...updates,
    updatedBy: uid
  });

  return ok({
    message: '시스템 설정이 업데이트되었습니다.',
    config: updates
  });
});
