'use strict';

const { admin, db } = require('../../utils/firebaseAdmin');
const { HttpsError } = require('firebase-functions/v2/https');
const { generatePersonalizedHints, generatePersonaHints } = require('./personalization');
const { generateEnhancedMetadataHints } = require('../../utils/enhanced-metadata-hints');

/**
 * 사용자 프로필 및 Bio 메타데이터 로딩
 * @param {string} uid - 사용자 ID
 * @param {string} category - 글 카테고리
 * @param {string} topic - 글 주제
 * @param {boolean} useBonus - 보너스 사용 여부
 * @returns {Promise<Object>} 프로필 데이터
 */
async function loadUserProfile(uid, category, topic, useBonus = false) {
  let userProfile = {};
  let bioMetadata = null;
  let personalizedHints = '';
  let dailyLimitWarning = false;
  let userMetadata = null;

  try {
    // 사용자 기본 정보 조회
    console.log(`🔍 프로필 조회 시도 - UID: ${uid}, 길이: ${uid?.length}`);
    const userDoc = await Promise.race([
      db.collection('users').doc(uid).get(),
      new Promise((_, reject) => setTimeout(() => reject(new Error('프로필 조회 타임아웃')), 5000))
    ]);

    console.log(`📋 프로필 문서 존재 여부: ${userDoc.exists}`);

    if (userDoc.exists) {
      userProfile = userDoc.data();
      console.log('✅ 사용자 프로필 조회 완료:', userProfile.name || 'Unknown');

      // 권한 및 사용량 체크 (isAdmin 필드 또는 role 필드 체크)
      const isAdmin = userProfile.isAdmin === true || userProfile.role === 'admin';

      if (!isAdmin) {
        // 하루 생성량 체크
        dailyLimitWarning = checkDailyLimit(userProfile);

        // 월간 사용량 체크
        await checkUsageLimit(userProfile, useBonus);
      } else {
        console.log('✅ 관리자 계정 - 제한 무시');
      }
    }

    // Bio 메타데이터 조회
    console.log(`🔍 Bio 메타데이터 조회 시도 - UID: ${uid}`);
    const bioDoc = await db.collection('bios').doc(uid).get();
    console.log(`📋 Bio 문서 존재 여부: ${bioDoc.exists}`);

    if (bioDoc.exists && bioDoc.data().extractedMetadata) {
      bioMetadata = bioDoc.data().extractedMetadata;

      // 메타데이터 기반 개인화 힌트 생성
      personalizedHints = generatePersonalizedHints(bioMetadata);
      console.log('✅ Bio 메타데이터 사용:', Object.keys(bioMetadata));

      // Bio 사용 통계 업데이트
      await db.collection('bios').doc(uid).update({
        'usage.generatedPostsCount': admin.firestore.FieldValue.increment(1),
        'usage.lastUsedAt': admin.firestore.FieldValue.serverTimestamp()
      });
    }

    // 개인정보 기반 페르소나 힌트 생성 및 추가
    const personaHints = generatePersonaHints(userProfile, category, topic);
    if (personaHints) {
      personalizedHints = personalizedHints ? `${personalizedHints} | ${personaHints}` : personaHints;
      console.log('✅ 페르소나 힌트 추가:', personaHints);
    }

    // 향상된 메타데이터 로드
    try {
      const bioDoc = await db.collection('bios').doc(uid).get();

      if (bioDoc.exists && bioDoc.data().metadataStatus === 'completed') {
        const bioData = bioDoc.data();

        userMetadata = {
          extractedMetadata: bioData.extractedMetadata,
          typeMetadata: bioData.typeMetadata?.[category],
          hints: bioData.optimizationHints
        };

        console.log('✅ 향상된 메타데이터 로드 완료:', uid);
      }
    } catch (metaError) {
      console.warn('⚠️ 메타데이터 로드 실패 (무시하고 계속):', metaError.message);
    }

    // 향상된 메타데이터 힌트 추가
    const enhancedHints = generateEnhancedMetadataHints(userMetadata, category);
    if (enhancedHints) {
      personalizedHints = personalizedHints ? `${personalizedHints} | ${enhancedHints}` : enhancedHints;
      console.log('✅ 향상된 메타데이터 힌트 추가:', enhancedHints);
    }

  } catch (profileError) {
    console.error('❌ 프로필/Bio 조회 실패:', {
      error: profileError.message,
      stack: profileError.stack,
      uid: uid,
      uidType: typeof uid,
      uidLength: uid?.length
    });

    throw new HttpsError('internal', `프로필 조회 실패: ${profileError.message}`);
  }

  return {
    userProfile,
    bioMetadata,
    personalizedHints,
    dailyLimitWarning,
    userMetadata,
    isAdmin: userProfile.isAdmin === true
  };
}

/**
 * 하루 생성량 제한 확인
 */
function checkDailyLimit(userProfile) {
  const today = new Date();
  const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const dailyUsage = userProfile.dailyUsage || {};
  const todayGenerated = dailyUsage[todayKey] || 0;

  if (todayGenerated >= 3) {
    console.log('⚠️ 하루 3회 초과 생성 - 경고만 표시');
    return true;
  }

  console.log('✅ 일반 사용자 하루 사용량 확인:', { todayGenerated, warning: todayGenerated >= 3 });
  return false;
}

/**
 * 현재 월 키 생성 (YYYY-MM 형식)
 */
function getCurrentMonthKey() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
}

/**
 * 사용량 제한 체크
 */
async function checkUsageLimit(userProfile, useBonus) {
  // System Config에서 testMode 확인
  const systemConfigDoc = await db.collection('system').doc('config').get();
  const testMode = systemConfigDoc.exists ? (systemConfigDoc.data().testMode || false) : false;

  if (useBonus) {
    const usage = userProfile.usage || { bonusGenerated: 0, bonusUsed: 0 };
    const availableBonus = Math.max(0, usage.bonusGenerated - (usage.bonusUsed || 0));

    if (availableBonus <= 0) {
      throw new HttpsError('failed-precondition', '사용 가능한 보너스 원고가 없습니다.');
    }

    console.log('✅ 보너스 원고 사용 가능', { availableBonus });
  } else if (testMode) {
    // === 데모 모드: 당원 인증 필수, 구독 불필요, 월 8회 무료 제공 ===
    // 1. 당원 인증 체크
    if (userProfile.verificationStatus !== 'verified') {
      throw new HttpsError('failed-precondition',
        '당원 인증이 필요합니다. 결제 페이지에서 당원 인증을 완료해주세요.');
    }

    // 2. 월간 생성 횟수 체크 (월별 키 사용)
    const testModeLimit = systemConfigDoc.data()?.testModeSettings?.freeMonthlyLimit || 8;
    const currentMonthKey = getCurrentMonthKey();
    const monthlyUsage = userProfile.monthlyUsage || {};
    const currentMonthPosts = monthlyUsage[currentMonthKey] || 0;

    if (currentMonthPosts >= testModeLimit) {
      throw new HttpsError('resource-exhausted',
        `데모 기간 중 이번 달 생성 가능 횟수(${testModeLimit}회)를 초과했습니다.`);
    }

    console.log('🧪 데모 모드 - 원고 생성 가능', {
      verificationStatus: userProfile.verificationStatus,
      monthKey: currentMonthKey,
      current: currentMonthPosts,
      limit: testModeLimit,
      remaining: testModeLimit - currentMonthPosts
    });
  } else {
    // === 프로덕션 모드: 기존 로직 ===
    const subscriptionStatus = userProfile.subscriptionStatus || 'trial';
    const monthlyLimit = userProfile.monthlyLimit || 8;
    const trialPostsRemaining = userProfile.trialPostsRemaining || 0;

    if (subscriptionStatus === 'trial') {
      // 무료 체험 상태
      if (trialPostsRemaining <= 0) {
        throw new HttpsError('resource-exhausted', '무료 체험 횟수를 모두 사용하셨습니다. 유료 플랜을 구독해주세요.');
      }
      console.log('✅ 무료 체험 원고 생성 가능', {
        remaining: trialPostsRemaining
      });
    } else if (subscriptionStatus === 'active') {
      // 유료 구독 상태 (월별 키 사용)
      const currentMonthKey = getCurrentMonthKey();
      const monthlyUsage = userProfile.monthlyUsage || {};
      const currentMonthPosts = monthlyUsage[currentMonthKey] || 0;

      if (currentMonthPosts >= monthlyLimit) {
        throw new HttpsError('resource-exhausted', '월간 생성 횟수를 초과했습니다.');
      }
      console.log('✅ 유료 구독 원고 생성 가능', {
        monthKey: currentMonthKey,
        current: currentMonthPosts,
        limit: monthlyLimit,
        remaining: monthlyLimit - currentMonthPosts
      });
    } else {
      // 만료 또는 기타 상태
      throw new HttpsError('failed-precondition', '구독이 만료되었거나 유효하지 않습니다. 플랜을 확인해주세요.');
    }
  }
}

/**
 * 사용량 업데이트
 */
async function updateUsageStats(uid, useBonus, isAdmin) {
  if (!uid) return;

  const today = new Date();
  const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const currentMonthKey = getCurrentMonthKey();

  // System Config에서 testMode 확인
  const systemConfigDoc = await db.collection('system').doc('config').get();
  const testMode = systemConfigDoc.exists ? (systemConfigDoc.data().testMode || false) : false;

  try {
    if (useBonus) {
      await db.collection('users').doc(uid).update({
        'usage.bonusUsed': admin.firestore.FieldValue.increment(1),
        [`dailyUsage.${todayKey}`]: isAdmin ? 0 : admin.firestore.FieldValue.increment(1),
        lastBonusUsed: admin.firestore.FieldValue.serverTimestamp()
      });
      console.log('✅ 보너스 원고 사용량 업데이트', isAdmin ? '(관리자 - 하루 카운트 제외)' : '');
    } else {
      if (!isAdmin) {
        const updateData = {
          [`dailyUsage.${todayKey}`]: admin.firestore.FieldValue.increment(1),
          lastGenerated: admin.firestore.FieldValue.serverTimestamp(),
          'usage.postsGenerated': admin.firestore.FieldValue.increment(1)
        };

        if (testMode) {
          // === 데모 모드: monthlyUsage 증가 (월별 키 사용) ===
          updateData[`monthlyUsage.${currentMonthKey}`] = admin.firestore.FieldValue.increment(1);
          console.log('🧪 데모 모드 - 이번 달 사용량 증가', { monthKey: currentMonthKey });
        } else {
          // === 프로덕션 모드: 구독 상태에 따라 처리 ===
          const userDoc = await db.collection('users').doc(uid).get();
          const userData = userDoc.data() || {};
          const subscriptionStatus = userData.subscriptionStatus || 'trial';

          if (subscriptionStatus === 'trial') {
            // 무료 체험: trialPostsRemaining 감소 (음수 방지를 위해 현재 값 확인)
            const currentRemaining = userData.trialPostsRemaining || 0;

            if (currentRemaining > 0) {
              updateData.trialPostsRemaining = admin.firestore.FieldValue.increment(-1);
              console.log('✅ 무료 체험 횟수 차감', {
                before: currentRemaining,
                after: currentRemaining - 1
              });
            } else {
              console.warn('⚠️ trialPostsRemaining이 이미 0 이하입니다. 차감하지 않습니다.');
            }
          } else if (subscriptionStatus === 'active') {
            // 유료 구독: monthlyUsage 증가 (월별 키 사용)
            updateData[`monthlyUsage.${currentMonthKey}`] = admin.firestore.FieldValue.increment(1);
            console.log('✅ 이번 달 사용량 증가', { monthKey: currentMonthKey });
          }
        }

        await db.collection('users').doc(uid).update(updateData);
        console.log('✅ 일반 원고 사용량 및 하루 사용량 업데이트');
      } else {
        await db.collection('users').doc(uid).update({
          lastGenerated: admin.firestore.FieldValue.serverTimestamp()
        });
        console.log('✅ 관리자 계정 - 사용량 카운트 없이 기록만 업데이트');
      }
    }
  } catch (updateError) {
    console.warn('⚠️ 사용량 업데이트 실패:', updateError.message);
  }
}

module.exports = {
  loadUserProfile,
  updateUsageStats
};
