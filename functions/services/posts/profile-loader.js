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

        // 월간 사용량 체크 (세션 자동 만료 포함)
        await checkUsageLimit(uid, userProfile, useBonus);
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
    // HttpsError는 그대로 다시 throw (사용 제한, 세션 제한 등)
    if (profileError.code && profileError.code !== 'internal') {
      throw profileError;
    }

    // 실제 프로필 조회 실패만 래핑
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
 * 사용량 제한 체크 (생성 vs 시도 구분)
 * - 1회 생성 = 3번 시도 세트
 * - 8회 생성 = 24회 시도
 * - 90회 생성 = 270회 시도
 * @param {string} uid - 사용자 ID
 * @param {Object} userProfile - 사용자 프로필
 * @param {boolean} useBonus - 보너스 사용 여부
 */
async function checkUsageLimit(uid, userProfile, useBonus) {
  // 🆕 세션 자동 만료 체크 (30분)
  const activeSession = userProfile.activeGenerationSession;
  if (activeSession && activeSession.startedAt) {
    const sessionStartTime = activeSession.startedAt.toMillis ? activeSession.startedAt.toMillis() : activeSession.startedAt;
    const now = admin.firestore.Timestamp.now().toMillis();
    const sessionAge = now - sessionStartTime;
    const SESSION_TIMEOUT = 30 * 60 * 1000; // 30분

    if (sessionAge > SESSION_TIMEOUT) {
      console.log('🕒 세션 자동 만료 - 30분 경과:', {
        sessionId: activeSession.id,
        startedAt: new Date(sessionStartTime).toISOString(),
        age: Math.floor(sessionAge / 1000 / 60) + '분'
      });

      // 세션 삭제
      await db.collection('users').doc(uid).update({
        activeGenerationSession: admin.firestore.FieldValue.delete()
      });

      // userProfile 객체도 업데이트 (이후 로직에서 사용)
      userProfile.activeGenerationSession = null;
    }
  }

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
    // === 데모 모드: 당원 인증 필수, 말일 제한 해제, 8회 생성 가능 ===
    // 1. 당원 인증 체크
    if (userProfile.verificationStatus !== 'verified') {
      throw new HttpsError('failed-precondition',
        '당원 인증이 필요합니다. 결제 페이지에서 당원 인증을 완료해주세요.');
    }

    // 2. 생성 횟수 체크
    const generationsRemaining = userProfile.generationsRemaining || userProfile.trialPostsRemaining || 0;

    if (generationsRemaining <= 0) {
      throw new HttpsError('resource-exhausted',
        '데모 기간 중 생성 가능 횟수(8회)를 모두 사용하셨습니다.');
    }

    // 3. 세션 내 시도 횟수 체크
    const activeSession = userProfile.activeGenerationSession;
    if (activeSession && activeSession.attempts >= 3) {
      throw new HttpsError('resource-exhausted',
        '현재 생성에서 최대 시도 횟수(3회)에 도달했습니다. 원고를 선택하거나 다음 생성을 시작해주세요.');
    }

    // 4. 데모 모드에서는 말일(trialExpiresAt) 체크 건너뜀 (타임 리미트 해제)
    console.log('🧪 데모 모드 - 원고 생성 가능 (말일 제한 해제)', {
      verificationStatus: userProfile.verificationStatus,
      generationsRemaining,
      currentSessionAttempts: activeSession?.attempts || 0
    });
  } else {
    // === 프로덕션 모드 ===
    const subscriptionStatus = userProfile.subscriptionStatus || 'trial';
    const monthlyLimit = userProfile.monthlyLimit || 8;
    const generationsRemaining = userProfile.generationsRemaining || userProfile.trialPostsRemaining || 0;

    if (subscriptionStatus === 'trial') {
      // 무료 체험 상태
      // 1️⃣ 생성 횟수 체크
      if (generationsRemaining <= 0) {
        throw new HttpsError('resource-exhausted', '무료 체험 횟수(8회 생성)를 모두 사용하셨습니다. 유료 플랜을 구독해주세요.');
      }

      // 2️⃣ 세션 내 시도 횟수 체크
      const activeSession = userProfile.activeGenerationSession;
      if (activeSession && activeSession.attempts >= 3) {
        throw new HttpsError('resource-exhausted',
          '현재 생성에서 최대 시도 횟수(3회)에 도달했습니다. 원고를 선택하거나 다음 생성을 시작해주세요.');
      }

      // 3️⃣ 말일 체크 (가입일이 속한 달의 말일까지만 사용 가능)
      const trialExpiresAt = userProfile.trialExpiresAt;
      if (trialExpiresAt) {
        const now = admin.firestore.Timestamp.now();
        if (trialExpiresAt.toMillis() < now.toMillis()) {
          throw new HttpsError('failed-precondition',
            '무료 체험 기간이 종료되었습니다. 유료 플랜을 구독해주세요.');
        }
      }

      console.log('✅ 무료 체험 원고 생성 가능', {
        generationsRemaining,
        currentSessionAttempts: activeSession?.attempts || 0
      });
    } else if (subscriptionStatus === 'active') {
      // 유료 구독 상태 (월별 키 사용)
      const currentMonthKey = getCurrentMonthKey();
      const monthlyUsage = userProfile.monthlyUsage || {};
      const currentMonthGenerations = monthlyUsage[currentMonthKey]?.generations || monthlyUsage[currentMonthKey] || 0;

      if (currentMonthGenerations >= monthlyLimit) {
        throw new HttpsError('resource-exhausted', `월간 생성 횟수(${monthlyLimit}회)를 초과했습니다.`);
      }

      // 세션 내 시도 횟수 체크
      const activeSession = userProfile.activeGenerationSession;
      if (activeSession && activeSession.attempts >= 3) {
        throw new HttpsError('resource-exhausted',
          '현재 생성에서 최대 시도 횟수(3회)에 도달했습니다. 원고를 선택하거나 다음 생성을 시작해주세요.');
      }

      console.log('✅ 유료 구독 원고 생성 가능', {
        monthKey: currentMonthKey,
        generationsCurrent: currentMonthGenerations,
        generationsLimit: monthlyLimit,
        generationsRemaining: monthlyLimit - currentMonthGenerations,
        currentSessionAttempts: activeSession?.attempts || 0
      });
    } else {
      // 만료 또는 기타 상태
      throw new HttpsError('failed-precondition', '구독이 만료되었거나 유효하지 않습니다. 플랜을 확인해주세요.');
    }
  }
}

/**
 * 세션 시작 또는 계속 (생성 vs 시도 구분)
 * - 새 세션: generationsRemaining 즉시 차감, 세션 생성, attempts = 1
 * - 기존 세션: attempts만 증가
 * @returns {Object} 세션 정보 { sessionId, attempts, maxAttempts, isNewSession }
 */
async function startOrContinueSession(uid, useBonus, isAdmin, category, topic) {
  if (!uid) return { sessionId: null, attempts: 0, maxAttempts: 3, isNewSession: false };

  const today = new Date();
  const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const currentMonthKey = getCurrentMonthKey();

  // System Config에서 testMode 확인
  const systemConfigDoc = await db.collection('system').doc('config').get();
  const testMode = systemConfigDoc.exists ? (systemConfigDoc.data().testMode || false) : false;

  let sessionInfo = { sessionId: null, attempts: 0, maxAttempts: 3, isNewSession: false };

  try {
    if (useBonus) {
      // 보너스 사용
      await db.collection('users').doc(uid).update({
        'usage.bonusUsed': admin.firestore.FieldValue.increment(1),
        [`dailyUsage.${todayKey}`]: isAdmin ? 0 : admin.firestore.FieldValue.increment(1),
        lastBonusUsed: admin.firestore.FieldValue.serverTimestamp()
      });
      console.log('✅ 보너스 원고 사용량 업데이트', isAdmin ? '(관리자 - 하루 카운트 제외)' : '');
      // 보너스는 세션 관리 없음
      sessionInfo = { sessionId: null, attempts: 1, maxAttempts: 1, isNewSession: true };
    } else {
      if (!isAdmin) {
        // 현재 사용자 데이터 조회
        const userDoc = await db.collection('users').doc(uid).get();
        const userData = userDoc.data() || {};
        const subscriptionStatus = userData.subscriptionStatus || 'trial';
        const activeSession = userData.activeGenerationSession;

        const updateData = {
          [`dailyUsage.${todayKey}`]: admin.firestore.FieldValue.increment(1),
          lastGenerated: admin.firestore.FieldValue.serverTimestamp(),
          'usage.postsGenerated': admin.firestore.FieldValue.increment(1)
        };

        // 세션 관리
        if (!activeSession) {
          // === 새 세션 시작: 생성 횟수 즉시 차감 ===
          const sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

          updateData.activeGenerationSession = {
            id: sessionId,
            startedAt: admin.firestore.FieldValue.serverTimestamp(),
            attempts: 1,
            category: category || '',
            topic: topic || ''
          };

          sessionInfo = { sessionId, attempts: 1, maxAttempts: 3, isNewSession: true };

          if (testMode || subscriptionStatus === 'trial') {
            // 데모/무료 체험: generationsRemaining 차감
            const currentRemaining = userData.generationsRemaining || userData.trialPostsRemaining || 0;

            if (currentRemaining > 0) {
              updateData.generationsRemaining = admin.firestore.FieldValue.increment(-1);
              const modeLabel = testMode ? '🧪 데모 모드' : '✅ 무료 체험';
              console.log(`${modeLabel} - 새 세션 시작, 생성 횟수 차감`, {
                sessionId,
                generationsBefore: currentRemaining,
                generationsAfter: currentRemaining - 1
              });
            } else {
              console.warn('⚠️ generationsRemaining이 이미 0 이하입니다. 차감하지 않습니다.');
            }
          } else if (subscriptionStatus === 'active') {
            // 유료 구독: monthlyUsage 증가
            const currentMonthGenerations = userData.monthlyUsage?.[currentMonthKey]?.generations || 0;
            updateData[`monthlyUsage.${currentMonthKey}.generations`] = admin.firestore.FieldValue.increment(1);
            updateData[`monthlyUsage.${currentMonthKey}.attempts`] = admin.firestore.FieldValue.increment(1);
            console.log('✅ 유료 구독 - 새 세션 시작, 월별 생성 횟수 증가', {
              sessionId,
              monthKey: currentMonthKey,
              generationsBefore: currentMonthGenerations,
              generationsAfter: currentMonthGenerations + 1
            });
          }
        } else {
          // === 기존 세션 계속: 시도 횟수만 증가 ===
          const newAttempts = activeSession.attempts + 1;
          updateData['activeGenerationSession.attempts'] = admin.firestore.FieldValue.increment(1);

          sessionInfo = {
            sessionId: activeSession.id,
            attempts: newAttempts,
            maxAttempts: 3,
            isNewSession: false
          };

          if (subscriptionStatus === 'active') {
            // 유료 구독: 시도 횟수도 기록
            updateData[`monthlyUsage.${currentMonthKey}.attempts`] = admin.firestore.FieldValue.increment(1);
          }

          console.log('✅ 기존 세션 계속 - 시도 횟수 증가', {
            sessionId: activeSession.id,
            attemptsBefore: activeSession.attempts,
            attemptsAfter: newAttempts
          });
        }

        await db.collection('users').doc(uid).update(updateData);
        console.log('✅ 세션 및 사용량 업데이트 완료');
      } else {
        // 관리자는 세션 관리 없이 기록만
        await db.collection('users').doc(uid).update({
          lastGenerated: admin.firestore.FieldValue.serverTimestamp()
        });
        console.log('✅ 관리자 계정 - 사용량 카운트 없이 기록만 업데이트');
        sessionInfo = { sessionId: 'admin', attempts: 1, maxAttempts: 999, isNewSession: false };
      }
    }

    return sessionInfo;
  } catch (updateError) {
    console.warn('⚠️ 세션 업데이트 실패:', updateError.message);
    throw updateError;
  }
}

/**
 * 세션 종료 (원고 저장 시)
 */
async function endSession(uid) {
  if (!uid) return;

  try {
    await db.collection('users').doc(uid).update({
      activeGenerationSession: admin.firestore.FieldValue.delete()
    });
    console.log('✅ 세션 종료 (원고 저장 완료)');
  } catch (error) {
    console.warn('⚠️ 세션 종료 실패:', error.message);
  }
}

module.exports = {
  loadUserProfile,
  startOrContinueSession,
  endSession
};
