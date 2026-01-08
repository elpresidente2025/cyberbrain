'use strict';

const { admin, db } = require('../../utils/firebaseAdmin');
const { HttpsError } = require('firebase-functions/v2/https');
const { generatePersonalizedHints, generatePersonaHints, generateStyleHints } = require('./personalization');
const { generateEnhancedMetadataHints } = require('../../utils/enhanced-metadata-hints');
const { generateMemoryContext } = require('../memory');

/**
 * 사용자 프로필 및 Bio 메타데이터 로딩
 * @param {string} uid - 사용자 ID
 * @param {string} category - 글 카테고리
 * @param {string} topic - 글 주제
 * @returns {Promise<Object>} 프로필 데이터
 */
async function loadUserProfile(uid, category, topic, options = {}) {
  const { strictSourceOnly = false } = options;
  let userProfile = {};
  let bioMetadata = null;
  let personalizedHints = '';
  let dailyLimitWarning = false;
  let userMetadata = null;
  let ragContext = '';  // RAG 컨텍스트 (try 블록 외부에서도 접근 가능하도록)
  let memoryContext = '';  // 메모리 컨텍스트 (장기 메모리 기반)
  let styleFingerprint = null;  // 🎨 Style Fingerprint (try 블록 외부에서도 접근 가능하도록)
  let styleGuide = '';
  let bioContent = '';
  let bioEntries = [];

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

      // 권한 및 사용량 체크 (isAdmin, isTester 필드 체크)
      const isAdmin = userProfile.isAdmin === true || userProfile.role === 'admin';
      const isTester = userProfile.isTester === true;

      if (!isAdmin && !isTester) {
        // 하루 생성량 체크
        dailyLimitWarning = checkDailyLimit(userProfile);

        // 월간 사용량 체크 (세션 자동 만료 포함)
        await checkUsageLimit(uid, userProfile);
      } else {
        console.log(`✅ ${isAdmin ? '관리자' : '테스터'} 계정 - 제한 무시`);
      }
    }

    // Bio 메타데이터 조회
    console.log(`🔍 Bio 메타데이터 조회 시도 - UID: ${uid}`);
    const bioDoc = await db.collection('bios').doc(uid).get();

    if (bioDoc.exists) {
      const bioData = bioDoc.data() || {};
      bioContent = bioData.content || '';
      if (bioContent) {
        userProfile.bio = bioContent;
      }
      if (Array.isArray(bioData.entries)) {
        bioEntries = bioData.entries;
        userProfile.bioEntries = bioEntries;
      }
    }

    if (bioDoc.exists && bioDoc.data().extractedMetadata) {
      bioMetadata = bioDoc.data().extractedMetadata;

      // 메타데이터 기반 개인화 힌트 생성
      personalizedHints = generatePersonalizedHints(bioMetadata);
      console.log('✅ Bio 메타데이터 사용:', Object.keys(bioMetadata));

      // 🎨 Style Fingerprint 로드 및 스타일 가이드 생성
      styleFingerprint = bioDoc.data().styleFingerprint || null;
      if (styleFingerprint) {
        styleGuide = generateStyleHints(styleFingerprint, { compact: false });
        console.log(`✅ Style Fingerprint 로드 (신뢰도: ${styleFingerprint.analysisMetadata?.confidence || 0})`);
      }

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

    // 🔍 RAG 컨텍스트 조회 (주제 기반 관련 정보 검색)
    if (topic && !strictSourceOnly) {
      try {
        const { generateRagContext } = require('../rag/retriever');
        const { indexOnDemand } = require('../rag/indexer');

        // 하이브리드 인덱싱: 필요시 주문형 인덱싱 실행
        const bioDoc = await db.collection('bios').doc(uid).get();
        if (bioDoc.exists) {
          await indexOnDemand(uid, bioDoc.data());
        }

        // RAG 검색 실행
        ragContext = await generateRagContext(uid, topic, category, { topK: 7 });

        if (ragContext) {
          console.log(`✅ RAG 컨텍스트 로드 완료: ${ragContext.length}자`);
        }
      } catch (ragError) {
        console.warn('⚠️ RAG 컨텍스트 로드 실패 (무시하고 계속):', ragError.message);
        // RAG 실패해도 원고 생성은 계속 진행
      }
    }
    if (!strictSourceOnly) {

      // 🧠 메모리 컨텍스트 로드 (장기 메모리 기반 개인화)
      try {
        memoryContext = await generateMemoryContext(uid, category);
        if (memoryContext) {
          console.log(`✅ 메모리 컨텍스트 로드 완료: ${memoryContext.length}자`);
        }
      } catch (memoryError) {
        console.warn('⚠️ 메모리 컨텍스트 로드 실패 (무시하고 계속):', memoryError.message);
      }
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
    ragContext,
    memoryContext,
    bioContent,
    bioEntries,
    styleGuide,         // 🎨 문체 가이드 (Style Fingerprint 기반)
    styleFingerprint,   // 🎨 Style Fingerprint 원본 (2단계 생성용)
    isAdmin: userProfile.isAdmin === true || userProfile.role === 'admin',
    isTester: userProfile.isTester === true,
    // 🎯 슬로건 정보
    slogan: userProfile.slogan || '',
    sloganEnabled: userProfile.sloganEnabled || false
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
 */
async function checkUsageLimit(uid, userProfile) {
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

  if (testMode) {
    // === 데모 모드: 당원 인증만 확인, 월 8회 무료 (가입시기/결제 무관) ===
    // 1. 당원 인증 체크 (대면 인증 사용자는 면제)
    if (userProfile.verificationStatus !== 'verified' && userProfile.faceVerified !== true) {
      throw new HttpsError('failed-precondition',
        '당원 인증이 필요합니다. 결제 페이지에서 당원 인증을 완료해주세요.');
    }

    // 2. 월별 생성 횟수 체크 (매월 8회 자동 리셋)
    const demoMonthlyLimit = 8;
    const currentMonthKey = getCurrentMonthKey();
    const monthlyUsage = userProfile.monthlyUsage || {};
    const currentMonthGenerations = monthlyUsage[currentMonthKey]?.generations || 0;

    if (currentMonthGenerations >= demoMonthlyLimit) {
      throw new HttpsError('resource-exhausted',
        `이번 달 데모 생성 횟수(${demoMonthlyLimit}회)를 모두 사용하셨습니다. 다음 달에 다시 이용해주세요.`);
    }

    // 3. 세션 내 시도 횟수 체크
    const activeSession = userProfile.activeGenerationSession;
    if (activeSession && activeSession.attempts >= 3) {
      throw new HttpsError('resource-exhausted',
        '현재 생성에서 최대 시도 횟수(3회)에 도달했습니다. 원고를 선택하거나 다음 생성을 시작해주세요.');
    }

    // 4. 데모 모드: 가입시기(trialExpiresAt), 결제상태(subscriptionStatus) 체크하지 않음
    console.log('🧪 데모 모드 - 월 8회 무료 사용 가능 (가입시기/결제 무관)', {
      verificationStatus: userProfile.verificationStatus,
      currentMonth: currentMonthKey,
      used: currentMonthGenerations,
      remaining: demoMonthlyLimit - currentMonthGenerations,
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
 * 세션 조회 또는 생성 (attempts는 변경하지 않음)
 * - 새 세션: 세션 생성, attempts = 0
 * - 기존 세션: 기존 세션 정보 반환
 * @param {string} uid - 사용자 ID
 * @param {boolean} isAdmin - 관리자 여부 (maxAttempts 999)
 * @param {boolean} isTester - 테스터 여부 (사용량 제한 면제, maxAttempts는 3)
 * @returns {Object} 세션 정보 { sessionId, attempts, maxAttempts, isNewSession }
 */
async function getOrCreateSession(uid, isAdmin, isTester, category, topic) {
  if (!uid) return { sessionId: null, attempts: 0, maxAttempts: 3, isNewSession: false };

  // 관리자만 사용량 제한 완전 면제 (테스터는 유료 사용자처럼 추적)
  const hasUnlimitedUsage = isAdmin;

  const today = new Date();
  const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const currentMonthKey = getCurrentMonthKey();

  // System Config에서 testMode 확인
  const systemConfigDoc = await db.collection('system').doc('config').get();
  const testMode = systemConfigDoc.exists ? (systemConfigDoc.data().testMode || false) : false;

  let sessionInfo = { sessionId: null, attempts: 0, maxAttempts: 3, isNewSession: false };

  try {
    if (!hasUnlimitedUsage) {
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
        // === 새 세션 생성: attempts는 0으로 시작 (검증 성공 후 증가) ===
        const sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

        updateData.activeGenerationSession = {
          id: sessionId,
          startedAt: admin.firestore.FieldValue.serverTimestamp(),
          attempts: 0,
          category: category || '',
          topic: topic || '',
          subscriptionStatus: subscriptionStatus
        };

        sessionInfo = { sessionId, attempts: 0, maxAttempts: 3, isNewSession: true, subscriptionStatus };

        const currentRemaining = userData.generationsRemaining || userData.trialPostsRemaining || 0;
        const currentMonthGenerations = userData.monthlyUsage?.[currentMonthKey]?.generations || 0;

        // 테스터는 유료 사용자처럼 월별 사용량 추적
        if (isTester) {
          console.log('🧪 테스터 - 새 세션 생성 (유료 사용자 기준 추적)', {
            sessionId,
            monthKey: currentMonthKey,
            currentMonthGenerations,
            monthlyLimit: 90
          });
        } else if (testMode) {
          // 데모 모드: 월별 사용량 기준
          console.log('🧪 데모 모드 - 새 세션 생성 (월 8회 무료)', {
            sessionId,
            monthKey: currentMonthKey,
            currentMonthGenerations,
            monthlyLimit: 8
          });
        } else if (subscriptionStatus === 'trial') {
          // 프로덕션 무료 체험: generationsRemaining 기준
          console.log('✅ 무료 체험 - 새 세션 생성 (attempts=0, 검증 성공 후 증가)', {
            sessionId,
            currentRemaining
          });
        } else if (subscriptionStatus === 'active') {
          console.log('✅ 유료 구독 - 새 세션 생성 (attempts=0, 검증 성공 후 증가)', {
            sessionId,
            monthKey: currentMonthKey,
            currentMonthGenerations
          });
        }
      } else {
        // === 기존 세션 조회: attempts는 현재 값 유지 (검증 성공 후 증가) ===
        const currentAttempts = activeSession.attempts || 0;
        const maxAttempts = 3;

        // 🚫 최대 시도 횟수 초과 검사
        if (currentAttempts >= maxAttempts) {
          console.warn(`⚠️ 최대 재생성 횟수 초과: ${currentAttempts}/${maxAttempts}`);
          throw new HttpsError(
            'resource-exhausted',
            `최대 ${maxAttempts}회까지만 재생성할 수 있습니다. 새로운 원고를 생성해주세요.`
          );
        }

        sessionInfo = {
          sessionId: activeSession.id,
          attempts: currentAttempts,
          maxAttempts,
          isNewSession: false
        };

        console.log('✅ 기존 세션 조회', {
          sessionId: activeSession.id,
          currentAttempts,
          remainingAttempts: maxAttempts - currentAttempts
        });
      }

      await db.collection('users').doc(uid).update(updateData);
      console.log('✅ 세션 정보 업데이트 완료 (attempts 변경 없음)');
    } else {
      // 관리자/테스터는 세션 관리 없이 기록만
      await db.collection('users').doc(uid).update({
        lastGenerated: admin.firestore.FieldValue.serverTimestamp()
      });
      // 관리자/테스터 모두 maxAttempts 3회
      const maxAttempts = 3;
      console.log(`✅ ${isAdmin ? '관리자' : '테스터'} 계정 - 사용량 카운트 없이 기록만 업데이트 (maxAttempts: ${maxAttempts})`);
      sessionInfo = { sessionId: isAdmin ? 'admin' : 'tester', attempts: 0, maxAttempts, isNewSession: false };
    }

    return sessionInfo;
  } catch (updateError) {
    console.warn('⚠️ 세션 업데이트 실패:', updateError.message);
    throw updateError;
  }
}

/**
 * 검증 성공 후 세션 attempts 증가
 * @param {string} uid - 사용자 ID
 * @param {Object} session - 세션 정보
 * @param {boolean} isAdmin - 관리자 여부
 * @param {boolean} isTester - 테스터 여부
 * @returns {Object} 업데이트된 세션 정보
 */
async function incrementSessionAttempts(uid, session, isAdmin, isTester = false) {
  if (!uid || isAdmin) {
    // 관리자는 attempts 관리 안 함
    return { ...session, attempts: session.attempts + 1 };
  }

  const currentMonthKey = getCurrentMonthKey();

  try {
    // 세션 attempts 증가
    const updateData = {
      'activeGenerationSession.attempts': admin.firestore.FieldValue.increment(1)
    };

    // 유료 구독 또는 테스터: 월별 시도 횟수 기록
    const userDoc = await db.collection('users').doc(uid).get();
    const userData = userDoc.data() || {};
    const subscriptionStatus = userData.subscriptionStatus || 'trial';

    if (subscriptionStatus === 'active' || isTester) {
      updateData[`monthlyUsage.${currentMonthKey}.attempts`] = admin.firestore.FieldValue.increment(1);
    }

    await db.collection('users').doc(uid).update(updateData);

    const newAttempts = session.attempts + 1;
    console.log('✅ 세션 attempts 증가 (검증 성공)', {
      sessionId: session.sessionId,
      attemptsBefore: session.attempts,
      attemptsAfter: newAttempts,
      isTester
    });

    return { ...session, attempts: newAttempts };
  } catch (error) {
    console.error('❌ attempts 증가 실패:', error.message);
    throw error;
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
  getOrCreateSession,
  incrementSessionAttempts,
  endSession
};
