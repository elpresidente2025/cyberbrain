/**
 * functions/handlers/profile.js (통합본)
 * 사용자 프로필 관련 HTTP 요청 처리 및 Firestore 트리거를 모두 포함합니다.
 * 선거구 중복 방지 로직과 자동 스타일 분석 기능이 통합되었습니다.
 * [수정] 모든 onCall 함수에 CORS 옵션을 추가하여 통신 오류를 해결합니다.
 */

'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { wrap, wrapLite } = require('../common/wrap');
const { ok } = require('../common/response');
const { auth } = require('../common/auth');
const { logInfo } = require('../common/log');
const { admin, db } = require('../utils/firebaseAdmin');
const { resolvePaidPlan, getTrialMonthlyLimit } = require('../common/plan-catalog');
const { districtKey } = require('../services/district');
const { getDistrictStatus, addUserToDistrict } = require('../services/district-priority');
const TRIAL_MONTHLY_LIMIT = getTrialMonthlyLimit();

// 광역/기초자치단체장은 선거구(electoralDistrict) 불필요
function requiredRegionFieldsFor(position) {
  if (!position) return ['regionMetro'];
  if (position === '광역자치단체장') return ['regionMetro'];
  if (position === '기초자치단체장') return ['regionMetro', 'regionLocal'];
  return ['regionMetro', 'regionLocal', 'electoralDistrict'];
}

// 온보딩 완료 여부 판정 (백엔드 SSOT)
// 자기소개(bio)는 온보딩 완료 조건에서 제외하고 프로필 페이지에서 별도로 작성하도록 유도한다.
// status는 선거법 기준 판별의 핵심 지표이므로 예외 없이 필수로 요구한다.
function isOnboardingCompleteFields(profile) {
  if (!profile) return false;
  if (!profile.status) return false;
  if (!profile.position) return false;
  for (const key of requiredRegionFieldsFor(profile.position)) {
    if (!profile[key]) return false;
  }
  return true;
}

// ============================================================================
// HTTP Callable Functions
// ============================================================================

/**
 * 사용자 프로필 조회
 */
exports.getUserProfile = wrapLite(async (req) => {
  const { uid, token } = await auth(req);
  logInfo('getUserProfile 호출', { userId: uid });

  const userDoc = await db.collection('users').doc(uid).get();

  let profile = {
    name: token?.name || '',
    position: '',
    regionMetro: '',
    regionLocal: '',
    electoralDistrict: '',
    status: '',
    bio: '', // 호환성을 위해 유지하지만 bios 컬렉션에서 조회
    targetElection: null, // 목표 선거 정보 (현직과 별개로 출마 예정 선거)
  };

  if (userDoc.exists) profile = { ...profile, ...(userDoc.data() || {}) };
  // Derive ageDecade/age for response if one is missing
  try {
    if (!profile.ageDecade && profile.age) {
      const m1 = String(profile.age).trim().match(/^(\d{2})\s*-\s*\d{2}$/);
      if (m1) profile.ageDecade = `${m1[1]}대`;
    }
    if (!profile.age && profile.ageDecade) {
      const m2 = String(profile.ageDecade).trim().match(/^(\d{2})\s*대$/);
      if (m2) {
        const start = parseInt(m2[1], 10);
        if (!isNaN(start)) profile.age = `${start}-${start + 9}`;
      }
    }
  } catch (_) {}

  // Normalize gender if present (e.g., 'M'/'F' -> '남성'/'여성')
  if (profile.gender) {
    const g = String(profile.gender).trim().toUpperCase();
    if (g === 'M' || g === 'MALE' || g === '남' || g === '남자') profile.gender = '남성';
    else if (g === 'F' || g === 'FEMALE' || g === '여' || g === '여자') profile.gender = '여성';
  }

  // users 컬렉션의 bio 확인 (디버깅)
  console.log('📝 [getUserProfile] users 컬렉션의 bio:', {
    hasBio: !!profile.bio,
    bioLength: profile.bio?.length || 0,
    bioPreview: profile.bio?.substring(0, 50)
  });

  // bios 컬렉션에서 자기소개 조회 (호환성 유지)
  try {
    const bioDoc = await db.collection('bios').doc(uid).get();
    console.log('📝 [getUserProfile] bios 컬렉션 조회:', {
      exists: bioDoc.exists,
      hasContent: bioDoc.exists ? !!bioDoc.data()?.content : false,
      hasEntries: bioDoc.exists ? !!bioDoc.data()?.entries : false
    });
    if (bioDoc.exists) {
      const bioData = bioDoc.data();
      const biosContent = bioData.content || '';
      console.log('📝 [getUserProfile] bios 컬렉션 content 길이:', biosContent.length);
      profile.bio = biosContent;

      // bioEntries도 불러오기
      if (bioData.entries && Array.isArray(bioData.entries)) {
        profile.bioEntries = bioData.entries;
        console.log('📝 [getUserProfile] bioEntries 불러오기:', { count: bioData.entries.length });
      }
    }
  } catch (error) {
    console.error('❌ [getUserProfile] Bio 조회 실패:', error);
  }

  console.log('📝 [getUserProfile] 최종 bio:', {
    hasBio: !!profile.bio,
    bioLength: profile.bio?.length || 0
  });

  // onboardingCompleted 보정: 기존 유저도 조건 충족 시 true로 자동 세팅
  if (profile.onboardingCompleted !== true) {
    if (isOnboardingCompleteFields(profile)) {
      profile.onboardingCompleted = true;
      profile.profileComplete = true;
      try {
        await db.collection('users').doc(uid).set({
          onboardingCompleted: true,
          profileComplete: true,
          onboardingCompletedAt: admin.firestore.FieldValue.serverTimestamp(),
        }, { merge: true });
      } catch (e) {
        console.warn('[getUserProfile] onboardingCompleted 자동 세팅 실패:', e.message);
      }
    } else {
      profile.onboardingCompleted = false;
    }
  }

  logInfo('getUserProfile 성공', { userId: uid });
  return ok({ profile });
});

/**
 * 프로필 업데이트 (+ 선거구 유일성 락)
 */
exports.updateProfile = wrap(async (req) => {
  const { uid, token } = await auth(req);
  const profileData = req.data;
  if (!profileData || typeof profileData !== 'object') {
    throw new HttpsError('invalid-argument', '올바른 프로필 데이터를 입력해주세요.');
  }

  logInfo('updateProfile 호출', { userId: uid, email: token?.email });

  const allowed = [
    'name', 'position', 'regionMetro', 'regionLocal',
    'electoralDistrict', 'status', 'bio', 'customTitle', 'bioEntries', // bio는 별도 처리, customTitle 추가, bioEntries 추가
    'targetElection', // 목표 선거 정보 (현직과 별개로 출마 예정 선거)
    // 개인화 정보 필드들
    'ageDecade', 'ageDetail', 'familyStatus', 'backgroundCareer',
    'localConnection', 'politicalExperience', 'committees', 'customCommittees',
    'constituencyType', 'gender',
    // 슬로건
    'slogan', 'sloganEnabled',
    // 후원 안내
    'donationInfo', 'donationEnabled'
  ];
  const sanitized = {};
  for (const k of allowed) if (profileData[k] !== undefined) sanitized[k] = profileData[k];
  // age <-> ageDecade sync
  try {
    if (sanitized.age && !sanitized.ageDecade) {
      const m1 = String(sanitized.age).trim().match(/^(\d{2})\s*-\s*\d{2}$/);
      if (m1) sanitized.ageDecade = `${m1[1]}대`;
    }
    if (sanitized.ageDecade && !sanitized.age) {
      const m2 = String(sanitized.ageDecade).trim().match(/^(\d{2})\s*대$/);
      if (m2) {
        const start = parseInt(m2[1], 10);
        if (!isNaN(start)) sanitized.age = `${start}-${start + 9}`;
      }
    }
  } catch (_) {}

  // Normalize gender input from client
  if (sanitized.gender !== undefined && sanitized.gender !== null) {
    const g = String(sanitized.gender).trim().toUpperCase();
    if (g === 'M' || g === 'MALE' || g === '남' || g === '남자') sanitized.gender = '남성';
    else if (g === 'F' || g === 'FEMALE' || g === '여' || g === '여자') sanitized.gender = '여성';
    else sanitized.gender = String(sanitized.gender).trim();
  }

  const userRef = db.collection('users').doc(uid);
  const currentDoc = await userRef.get();
  const current = currentDoc.data() || {};

  const nextFields = {
    position: sanitized.position ?? current.position,
    regionMetro: sanitized.regionMetro ?? current.regionMetro,
    regionLocal: sanitized.regionLocal ?? current.regionLocal,
    electoralDistrict: sanitized.electoralDistrict ?? current.electoralDistrict,
  };

  const oldKey = current.districtKey || null;
  const newKey = (nextFields.position && nextFields.regionMetro && nextFields.regionLocal && nextFields.electoralDistrict)
    ? districtKey(nextFields)
    : null;

  console.log('🔍 [DEBUG] 선거구 키 생성 결과:', {
    uid,
    oldKey,
    newKey,
    nextFields,
    willChangeDistrict: !!(newKey && newKey !== oldKey),
    timestamp: new Date().toISOString()
  });

  // ✅ 우선권 시스템: 선거구 변경 처리
  if (newKey && newKey !== oldKey) {
    try {
      console.log('🔄 선거구 변경 중...', { uid, oldKey, newKey });
      const { changeUserDistrict } = require('../services/district-priority');
      await changeUserDistrict({ uid, oldDistrictKey: oldKey, newDistrictKey: newKey });
      logInfo('선거구 변경 성공', { oldKey, newKey });
    } catch (e) {
      console.error('❌ [updateProfile][changeUserDistrict] 실패:', {
        uid,
        oldKey,
        newKey,
        error: e?.message,
        code: e?.code
      });
      throw new HttpsError('failed-precondition', e?.message || '선거구 변경 중 오류');
    }
  } else if (newKey && newKey === oldKey) {
    console.log('ℹ️ 선거구 변경 없음 - 동일한 선거구:', newKey);
  } else {
    console.log('ℹ️ 선거구 키 생성 불가', {
      oldKey,
      newKey,
      hasAllFields: !!(nextFields.position && nextFields.regionMetro && nextFields.regionLocal && nextFields.electoralDistrict)
    });
  }

  // Bio 처리 (별도 컬렉션으로 분리)
  const bio = typeof sanitized.bio === 'string' ? sanitized.bio.trim() : '';
  const bioEntries = Array.isArray(sanitized.bioEntries) ? sanitized.bioEntries : null;
  let isActive = false;

  if (bio || bioEntries) {
    // bios 컬렉션에 저장
    const bioRef = db.collection('bios').doc(uid);
    const existingBio = await bioRef.get();
    const currentVersion = existingBio.exists ? (existingBio.data().version || 0) : 0;

    const bioData = {
      userId: uid,
      version: currentVersion + 1,
      updatedAt: admin.firestore.FieldValue.serverTimestamp(),
      createdAt: existingBio.exists ? existingBio.data().createdAt : admin.firestore.FieldValue.serverTimestamp(),
      metadataStatus: 'pending',
      usage: existingBio.exists ? existingBio.data().usage : {
        generatedPostsCount: 0,
        avgQualityScore: 0,
        lastUsedAt: null
      }
    };

    // bio가 있으면 content 필드 추가
    if (bio) {
      bioData.content = bio;
    }

    // bioEntries가 있으면 entries 필드 추가
    if (bioEntries) {
      bioData.entries = bioEntries;
      console.log('📝 [updateProfile] bioEntries 저장:', { count: bioEntries.length });
    }

    await bioRef.set(bioData, { merge: true });

    isActive = true;

    // 비동기 메타데이터 추출 (bio가 있는 경우만)
    if (bio) {
      const { extractMetadataAsync } = require('./bio');
      extractMetadataAsync(uid, bio);
    }
  } else {
    // users 컬렉션에서 기존 bio 컬렉션 확인
    const bioDoc = await db.collection('bios').doc(uid).get();
    // 반드시 boolean으로 변환 (&&는 마지막 truthy 값을 반환하므로 !! 필요)
    isActive = !!(bioDoc.exists && (bioDoc.data().content || bioDoc.data().entries));
  }

  delete sanitized.isAdmin;
  delete sanitized.role;
  delete sanitized.bio; // bio는 별도 컬렉션에 저장했으므로 users에서 제거
  delete sanitized.bioEntries; // bioEntries도 별도 컬렉션에 저장했으므로 users에서 제거

  await userRef.set(
    {
      ...sanitized,
      isActive,
      districtKey: newKey ?? oldKey,
      updatedAt: admin.firestore.FieldValue.serverTimestamp(),
    },
    { merge: true }
  );

  // 온보딩 완료 판정 및 플래그 세팅
  try {
    const mergedProfile = {
      position: nextFields.position,
      regionMetro: nextFields.regionMetro,
      regionLocal: nextFields.regionLocal,
      electoralDistrict: nextFields.electoralDistrict,
    };

    if (isOnboardingCompleteFields(mergedProfile) && current.onboardingCompleted !== true) {
      await userRef.set({
        onboardingCompleted: true,
        profileComplete: true,
        onboardingCompletedAt: admin.firestore.FieldValue.serverTimestamp(),
      }, { merge: true });
      logInfo('온보딩 완료 플래그 세팅', { uid });
    }
  } catch (e) {
    console.warn('[updateProfile] 온보딩 플래그 판정 실패:', e.message);
  }

  logInfo('updateProfile 성공', { isActive });
  return ok({ message: '프로필이 성공적으로 업데이트되었습니다.', isActive });
});

/**
 * 사용자 플랜 업데이트
 */
exports.updateUserPlan = wrap(async (req) => {
  const { uid, token } = await auth(req);
  const { planId, plan } = req.data || {};
  const selectedPlan = resolvePaidPlan(planId || plan);

  if (!selectedPlan) {
    throw new HttpsError('invalid-argument', '유효한 플랜을 선택해주세요.');
  }

  logInfo('updateUserPlan 호출', {
    userId: uid,
    email: token?.email,
    planId: selectedPlan.id,
    planName: selectedPlan.name,
  });

  const userRef = db.collection('users').doc(uid);

  try {
    await userRef.update({
      planId: selectedPlan.id,
      plan: selectedPlan.name,
      monthlyLimit: selectedPlan.monthlyLimit,
      subscriptionStatus: 'active',
      monthlyUsage: {}, // 월별 사용량 초기화
      'billing.planId': selectedPlan.id,
      'billing.planName': selectedPlan.name,
      'billing.status': 'active',
      'billing.monthlyLimit': selectedPlan.monthlyLimit,
      'billing.price': selectedPlan.price,
      'billing.currency': selectedPlan.currency,
      'billing.updatedAt': admin.firestore.FieldValue.serverTimestamp(),
      updatedAt: admin.firestore.FieldValue.serverTimestamp(),
    });

    logInfo('플랜 업데이트 성공', {
      userId: uid,
      planId: selectedPlan.id,
      planName: selectedPlan.name,
    });
    return ok({
      message: `${selectedPlan.name} 플랜으로 성공적으로 변경되었습니다.`,
      planId: selectedPlan.id,
      plan: selectedPlan.name,
    });
  } catch (error) {
    console.error('❌ 플랜 업데이트 실패:', error);
    throw new HttpsError('internal', '플랜 업데이트에 실패했습니다.');
  }
});

/**
 * 선거구 상태 확인 (1인 제한 폐지됨 - 항상 사용 가능)
 */
exports.checkDistrictAvailability = wrapLite(async (req) => {
  const { regionMetro, regionLocal, electoralDistrict, position } = req.data || {};
  if (!regionMetro || !regionLocal || !electoralDistrict || !position) {
    throw new HttpsError('invalid-argument', '지역/선거구/직책을 모두 입력해주세요.');
  }
  const newKey = districtKey({ position, regionMetro, regionLocal, electoralDistrict });

  // 1인 제한 폐지: 항상 사용 가능, 기존 사용자 정보만 제공
  const status = await getDistrictStatus({ districtKey: newKey });
  logInfo('선거구 상태 확인', { newKey, hasPrimary: status.hasPrimary });
  return ok({
    available: true,  // 항상 사용 가능
    hasPrimary: status.hasPrimary,
    message: status.message
  });
});

/**
 * 회원가입 + 선거구 등록 (중복 허용)
 */
exports.registerWithDistrictCheck = wrap(async (req) => {
  const { uid, token } = await auth(req);
  const { profileData } = req.data || {};
  if (!profileData) throw new HttpsError('invalid-argument', '프로필 데이터가 필요합니다.');

  logInfo('registerWithDistrictCheck 호출', { userId: uid, email: token?.email });

  const { position, regionMetro, regionLocal, electoralDistrict } = profileData;
  if (!position || !regionMetro || !regionLocal || !electoralDistrict) {
    throw new HttpsError('invalid-argument', '직책과 지역 정보를 모두 입력해주세요.');
  }

  const newKey = districtKey({ position, regionMetro, regionLocal, electoralDistrict });

  // ✅ 우선권 시스템: 중복 허용, 경고만 표시
  const districtStatus = await getDistrictStatus({ districtKey: newKey });

  console.log('📍 [registerWithDistrictCheck] 선거구 상태:', districtStatus);

  // 선거구에 사용자 추가 (중복 허용)
  await addUserToDistrict({ uid, districtKey: newKey });

  const bio = typeof profileData.bio === 'string' ? profileData.bio.trim() : '';
  const isActive = !!bio;

  // Bio를 bios 컬렉션에 저장 (users 컬렉션이 아닌!)
  if (bio) {
    await db.collection('bios').doc(uid).set({
      userId: uid,
      content: bio,
      version: 1,
      updatedAt: admin.firestore.FieldValue.serverTimestamp(),
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      metadataStatus: 'pending',
      usage: {
        generatedPostsCount: 0,
        avgQualityScore: 0,
        lastUsedAt: null
      }
    });

    // 비동기 메타데이터 추출
    const { extractMetadataAsync } = require('./bio');
    extractMetadataAsync(uid, bio);
  }

  const sanitizedProfileData = { ...profileData };
  delete sanitizedProfileData.isAdmin;
  delete sanitizedProfileData.role;
  delete sanitizedProfileData.bio; // bio는 bios 컬렉션에 저장했으므로 제거

  // 무료 체험 만료일 계산 (가입일이 속한 달의 말일 23:59:59)
  const now = new Date();
  const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59);

  await db.collection('users').doc(uid).set(
    {
      ...sanitizedProfileData,
      isActive,
      districtKey: newKey,
      // 우선권 시스템 필드
      districtPriority: null,  // 결제 전까지는 null
      isPrimaryInDistrict: false,  // 결제 전까지는 false
      districtStatus: 'trial',  // trial | primary | waiting | cancelled
      // 구독 정보
      subscriptionStatus: 'trial',  // 무료 체험 상태
      planId: null,
      plan: null,
      billing: {
        status: 'trial',
        monthlyLimit: TRIAL_MONTHLY_LIMIT,
      },
      paidAt: null,  // 결제 시점 (결제 후 업데이트)
      trialPostsRemaining: TRIAL_MONTHLY_LIMIT,
      generationsRemaining: TRIAL_MONTHLY_LIMIT,
      trialExpiresAt: admin.firestore.Timestamp.fromDate(endOfMonth),  // 말일까지 체험 가능
      monthlyLimit: TRIAL_MONTHLY_LIMIT,
      monthlyUsage: {},  // 월별 사용량 (자동 초기화되는 구조)
      activeGenerationSession: null,  // 활성 세션 없음
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      updatedAt: admin.firestore.FieldValue.serverTimestamp(),
    },
    { merge: true }
  );

  logInfo('회원가입 성공', {
    newKey,
    isActive,
    subscriptionStatus: 'trial',
    districtWarning: districtStatus.message
  });

  return ok({
    message: '회원가입이 완료되었습니다.',
    isActive,
    districtWarning: districtStatus.message  // 선거구 상황 안내
  });
});


// analyzeBioOnUpdate → Python py_stylometryOnBioUpdate로 이관 완료, 삭제됨.

/**
 * @trigger cleanupDistrictClaimsOnUserDelete
 * @description 사용자가 삭제되면 해당 사용자의 선거구 점유 기록을 자동으로 정리합니다.
 */
const { onDocumentDeleted } = require('firebase-functions/v2/firestore');

exports.cleanupDistrictClaimsOnUserDelete = onDocumentDeleted('users/{userId}', async (event) => {
  const userId = event.params.userId;
  const userData = event.data.data();

  console.log(`🧹 사용자 삭제 감지 - 선거구 점유 기록 정리 시작:`, { userId });

  try {
    // 해당 사용자가 점유한 모든 선거구 찾기
    const snapshot = await db.collection('district_claims').where('userId', '==', userId).get();

    if (snapshot.empty) {
      console.log(`ℹ️ 사용자 ${userId}의 선거구 점유 기록이 없습니다.`);
      return;
    }

    // 배치로 모든 점유 기록 삭제
    const batch = db.batch();
    const deletedDistricts = [];

    snapshot.forEach(doc => {
      batch.delete(doc.ref);
      deletedDistricts.push(doc.id);
    });

    await batch.commit();

    console.log(`✅ 사용자 ${userId}의 선거구 점유 기록 정리 완료:`, {
      deletedDistricts,
      count: deletedDistricts.length
    });

    // bios 컬렉션도 정리
    try {
      await db.collection('bios').doc(userId).delete();
      console.log(`✅ 사용자 ${userId}의 bio 기록도 정리 완료`);
    } catch (bioError) {
      console.warn(`⚠️ 사용자 ${userId}의 bio 정리 실패 (무시):`, bioError.message);
    }

  } catch (error) {
    console.error(`❌ 사용자 ${userId}의 선거구 점유 기록 정리 실패:`, error);
  }

  return null;
});
