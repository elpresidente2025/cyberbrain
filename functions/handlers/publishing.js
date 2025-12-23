const admin = require('firebase-admin');
const { onCall, HttpsError } = require('firebase-functions/v2/https');
const { wrap } = require('../common/wrap');
const { auth } = require('../common/auth');

// 원고 발행 등록
const publishPost = wrap(async (request) => {
  const { uid } = await auth(request);
  const { postId, publishUrl } = request.data;

  if (!postId || !publishUrl) {
    throw new HttpsError('invalid-argument', '원고 ID와 발행 URL이 필요합니다.');
  }

  try {
    const db = admin.firestore();
    const now = admin.firestore.FieldValue.serverTimestamp();
    const publishedAt = new Date();

    // 트랜잭션으로 처리
    await db.runTransaction(async (transaction) => {
      // 모든 읽기 작업을 먼저 수행 (Firestore 트랜잭션 규칙)
      const postRef = db.collection('posts').doc(postId);
      const postDoc = await transaction.get(postRef);

      const publishingRef = db.collection('user_publishing').doc(uid);
      const publishingDoc = await transaction.get(publishingRef);

      // 검증
      if (!postDoc.exists || postDoc.data().userId !== uid) {
        throw new HttpsError('not-found', '원고를 찾을 수 없습니다.');
      }

      // 이미 발행된 원고인지 확인
      if (postDoc.data().publishUrl) {
        throw new HttpsError('already-exists', '이미 발행된 원고입니다.');
      }

      // 발행 데이터 준비
      const currentYear = publishedAt.getFullYear();
      const currentMonth = publishedAt.getMonth() + 1;
      const monthKey = `${currentYear}-${String(currentMonth).padStart(2, '0')}`;

      const publishingData = publishingDoc.exists ? publishingDoc.data() : {};

      if (!publishingData.months) {
        publishingData.months = {};
      }

      if (!publishingData.months[monthKey]) {
        publishingData.months[monthKey] = {
          published: 0,
          posts: []
        };
      }

      publishingData.months[monthKey].published += 1;
      publishingData.months[monthKey].posts.push({
        postId: postId,
        publishUrl: publishUrl,
        publishedAt: publishedAt,
        title: postDoc.data().title || '제목 없음'
      });

      publishingData.lastUpdated = now;
      publishingData.totalPublished = (publishingData.totalPublished || 0) + 1;

      // 모든 쓰기 작업 수행
      transaction.update(postRef, {
        publishUrl: publishUrl,
        publishedAt: publishedAt,
        status: 'published',
        updatedAt: now
      });

      transaction.set(publishingRef, publishingData, { merge: true });
    });

    return {
      success: true,
      message: '발행이 등록되었습니다!',
      publishedAt: publishedAt.toISOString()
    };

  } catch (error) {
    console.error('Publish post error:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '발행 등록 중 오류가 발생했습니다.');
  }
});

// 발행 통계 조회
const getPublishingStats = wrap(async (request) => {
  const { uid } = await auth(request);

  try {
    const db = admin.firestore();

    // 사용자 정보 조회 (없으면 기본값 사용)
    const userDoc = await db.collection('users').doc(uid).get();
    const userData = userDoc.exists ? userDoc.data() : {};
    const userRole = userData.role || 'local_blogger';
    const isAdmin = userData.isAdmin === true || userData.role === 'admin';
    const isTester = userData.isTester === true;
    // 관리자/테스터는 90회, 그 외는 monthlyLimit 필드 또는 role 기반
    const monthlyTarget = (isAdmin || isTester) ? 90 : (userData.monthlyLimit || getMonthlyTarget(userRole));

    // 현재 월 정보
    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

    // 현재 달에 생성된 포스트 개수 조회 (저장 시점 기준, excludeFromCount 제외)
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59, 999);

    const postsSnapshot = await db.collection('posts')
      .where('userId', '==', uid)
      .where('createdAt', '>=', startOfMonth)
      .where('createdAt', '<=', endOfMonth)
      .get();

    // excludeFromCount가 true인 포스트는 제외
    const publishedThisMonth = postsSnapshot.docs.filter(doc => !doc.data().excludeFromCount).length;

    // 발행 데이터 조회 (기존 발행 기록용)
    const publishingDoc = await db.collection('user_publishing').doc(uid).get();
    const publishingData = publishingDoc.exists ? publishingDoc.data() : { months: {} };
    const currentMonthData = publishingData.months[currentMonth] || { published: 0, posts: [] };

    return {
      success: true,
      data: {
        currentMonth: {
          published: publishedThisMonth,
          target: monthlyTarget,
          posts: currentMonthData.posts || []
        },
        userRole: userRole,
        totalPublished: publishingData.totalPublished || 0,
        monthlyHistory: publishingData.months || {}
      }
    };

  } catch (error) {
    console.error('Get publishing stats error:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '통계 조회 중 오류가 발생했습니다.');
  }
});

// 보너스 원고 생성 권한 확인
const checkBonusEligibility = wrap(async (request) => {
  const { uid } = await auth(request);

  // auth 함수에서 이미 인증 검증이 완료됨

  try {
    const db = admin.firestore();
    const userDoc = await db.collection('users').doc(uid).get();
    
    if (!userDoc.exists) {
      throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
    }

    const userData = userDoc.data();
    const isAdmin = userData.role === 'admin' || userData.isAdmin === true;
    
    // 관리자는 무제한 보너스 제공
    if (isAdmin) {
      return {
        success: true,
        data: {
          hasBonus: true,
          availableBonus: 999999, // 관리자는 사실상 무제한
          totalBonusGenerated: 999999,
          bonusUsed: 0,
          accessMethod: 'admin'
        }
      };
    }
    
    const usage = userData.usage || { postsGenerated: 0, monthlyLimit: 50, bonusGenerated: 0 };
    
    // NaN 방지를 위한 안전한 숫자 변환
    const bonusGenerated = parseInt(usage.bonusGenerated) || 0;
    const bonusUsed = parseInt(usage.bonusUsed) || 0;
    
    // 보너스 사용 가능 개수 계산
    const availableBonus = Math.max(0, bonusGenerated - bonusUsed);

    return {
      success: true,
      data: {
        hasBonus: availableBonus > 0,
        availableBonus: availableBonus,
        totalBonusGenerated: bonusGenerated,
        bonusUsed: bonusUsed
      }
    };

  } catch (error) {
    console.error('Check bonus eligibility error:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '보너스 확인 중 오류가 발생했습니다.');
  }
});

// 보너스 원고 사용
const useBonusGeneration = wrap(async (request) => {
  const { uid } = await auth(request);

  // auth 함수에서 이미 인증 검증이 완료됨

  try {
    const db = admin.firestore();

    await db.runTransaction(async (transaction) => {
      const userRef = db.collection('users').doc(uid);
      const userDoc = await transaction.get(userRef);

      if (!userDoc.exists) {
        throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
      }

      const userData = userDoc.data();
      const isAdmin = userData.role === 'admin' || userData.isAdmin === true;
      
      // 관리자는 무제한 보너스 사용 가능
      if (isAdmin) {
        console.log('관리자 계정 보너스 사용 - 제한 없음:', uid);
        return {
          success: true,
          message: '관리자 권한으로 보너스 원고를 사용했습니다.'
        };
      }
      
      const usage = userData.usage || { postsGenerated: 0, monthlyLimit: 50, bonusGenerated: 0, bonusUsed: 0 };
      
      const availableBonus = Math.max(0, usage.bonusGenerated - (usage.bonusUsed || 0));

      if (availableBonus <= 0) {
        throw new HttpsError('failed-precondition', '사용 가능한 보너스 원고가 없습니다.');
      }

      // 보너스 사용 횟수 증가
      transaction.update(userRef, {
        'usage.bonusUsed': (usage.bonusUsed || 0) + 1
      });
    });

    return {
      success: true,
      message: '보너스 원고를 사용했습니다.'
    };

  } catch (error) {
    console.error('Use bonus generation error:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '보너스 사용 중 오류가 발생했습니다.');
  }
});

// 헬퍼 함수들
const getMonthlyTarget = (role) => {
  switch (role) {
    case 'opinion_leader':
    case '오피니언 리더':
      return 60;
    case 'regional_influencer':
    case '리전 인플루언서':
      return 20;
    case 'local_blogger':
    case '로컬 블로거':
    default:
      return 8;
  }
};

// 관리자: 사용자 사용량 초기화 (월별 사용량 리셋)
const resetUserUsage = wrap(async (request) => {
  const { uid: adminUid } = await auth(request);
  const { targetUserId } = request.data;

  if (!targetUserId) {
    throw new HttpsError('invalid-argument', '대상 사용자 ID가 필요합니다.');
  }

  try {
    const db = admin.firestore();

    // 관리자 권한 확인
    const adminDoc = await db.collection('users').doc(adminUid).get();
    const isAdmin = adminDoc.exists && (adminDoc.data().role === 'admin' || adminDoc.data().isAdmin === true);

    if (!isAdmin) {
      throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
    }

    // System Config에서 testMode 확인
    const systemConfigDoc = await db.collection('system').doc('config').get();
    const testMode = systemConfigDoc.exists ? (systemConfigDoc.data().testMode || false) : false;

    // 대상 사용자 정보 조회
    const userDoc = await db.collection('users').doc(targetUserId).get();
    if (!userDoc.exists) {
      throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
    }

    const userData = userDoc.data();
    const subscriptionStatus = userData.subscriptionStatus || 'trial';

    // 현재 월 키 생성
    const now = new Date();
    const currentMonthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

    // 현재 사용량 확인
    const monthlyUsage = userData.monthlyUsage || {};
    const currentMonthUsage = monthlyUsage[currentMonthKey] || 0;
    const trialRemaining = userData.trialPostsRemaining || 0;

    // 업데이트할 데이터
    const updateData = {
      updatedAt: admin.firestore.FieldValue.serverTimestamp()
    };

    if (testMode) {
      // === 데모 모드: generationsRemaining 및 세션 초기화 ===
      const monthlyLimit = userData.monthlyLimit || 8;
      updateData.generationsRemaining = monthlyLimit;
      updateData.activeGenerationSession = admin.firestore.FieldValue.delete();
      updateData[`monthlyUsage.${currentMonthKey}`] = 0;

      console.log(`🧪 데모 모드 사용자 초기화: generationsRemaining ${userData.generationsRemaining || 0} -> ${monthlyLimit}`);
    } else if (subscriptionStatus === 'trial') {
      // 무료 체험: generationsRemaining 복구
      const monthlyLimit = userData.monthlyLimit || 8;
      updateData.generationsRemaining = monthlyLimit;
      updateData.trialPostsRemaining = monthlyLimit;  // 하위 호환성
      updateData.activeGenerationSession = admin.firestore.FieldValue.delete();

      console.log(`✅ 무료 체험 사용자 초기화: generationsRemaining ${userData.generationsRemaining || 0} -> ${monthlyLimit}`);
    } else if (subscriptionStatus === 'active') {
      // 유료 구독: monthlyUsage 초기화 및 세션 초기화
      updateData[`monthlyUsage.${currentMonthKey}`] = 0;
      updateData.activeGenerationSession = admin.firestore.FieldValue.delete();

      console.log(`✅ 유료 구독 사용자 초기화: ${currentMonthUsage} -> 0`);
    }

    // 사용자 문서 업데이트
    await db.collection('users').doc(targetUserId).update(updateData);

    // 응답 메시지 생성
    let message, before, after;
    const currentGenerationsRemaining = userData.generationsRemaining || userData.trialPostsRemaining || 0;

    if (testMode) {
      const monthlyLimit = userData.monthlyLimit || 8;
      message = `데모 모드 생성 횟수가 초기화되었습니다. (${currentGenerationsRemaining}회 -> ${monthlyLimit}회)`;
      before = currentGenerationsRemaining;
      after = monthlyLimit;
    } else if (subscriptionStatus === 'trial') {
      const monthlyLimit = userData.monthlyLimit || 8;
      message = `무료 체험 생성 횟수가 초기화되었습니다. (${currentGenerationsRemaining}회 -> ${monthlyLimit}회)`;
      before = currentGenerationsRemaining;
      after = monthlyLimit;
    } else {
      message = `이번 달 사용량이 초기화되었습니다. (${currentMonthUsage}회 -> 0회)`;
      before = currentMonthUsage;
      after = 0;
    }

    return {
      success: true,
      message,
      mode: testMode ? 'demo' : subscriptionStatus,
      before,
      after,
      monthKey: currentMonthKey
    };

  } catch (error) {
    console.error('Reset user usage error:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '사용량 초기화 중 오류가 발생했습니다.');
  }
});

// 관리자: 테스터 권한 토글 (관리자와 동일한 90회 생성 권한 부여)
const toggleTester = wrap(async (request) => {
  const { uid: adminUid } = await auth(request);
  const { targetUserId } = request.data;

  if (!targetUserId) {
    throw new HttpsError('invalid-argument', '대상 사용자 ID가 필요합니다.');
  }

  try {
    const db = admin.firestore();

    // 관리자 권한 확인
    const adminDoc = await db.collection('users').doc(adminUid).get();
    const isAdmin = adminDoc.exists && (adminDoc.data().role === 'admin' || adminDoc.data().isAdmin === true);

    if (!isAdmin) {
      throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
    }

    // 대상 사용자 정보 조회
    const userDoc = await db.collection('users').doc(targetUserId).get();
    if (!userDoc.exists) {
      throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
    }

    const userData = userDoc.data();
    const currentTesterStatus = userData.isTester === true;
    const newTesterStatus = !currentTesterStatus;

    // 테스터 상태 토글 + monthlyLimit 연동
    await db.collection('users').doc(targetUserId).update({
      isTester: newTesterStatus,
      monthlyLimit: newTesterStatus ? 90 : 8,  // 테스터는 90회, 해제 시 8회
      testerUpdatedAt: admin.firestore.FieldValue.serverTimestamp(),
      testerUpdatedBy: adminUid
    });

    console.log(`✅ 테스터 권한 ${newTesterStatus ? '부여' : '해제'}:`, {
      targetUserId,
      by: adminUid,
      newStatus: newTesterStatus
    });

    return {
      success: true,
      message: newTesterStatus
        ? `${userData.name || '사용자'}님에게 테스터 권한이 부여되었습니다. (90회 생성 가능)`
        : `${userData.name || '사용자'}님의 테스터 권한이 해제되었습니다.`,
      isTester: newTesterStatus
    };

  } catch (error) {
    console.error('테스터 권한 토글 실패:', error);
    if (error.code) {
      throw error;
    }
    throw new HttpsError('internal', '테스터 권한 변경 중 오류가 발생했습니다.');
  }
});

module.exports = {
  publishPost,
  getPublishingStats,
  checkBonusEligibility,
  useBonusGeneration,
  getMonthlyTarget,
  resetUserUsage,
  toggleTester
};