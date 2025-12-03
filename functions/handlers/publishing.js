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
      // 1. 원고 업데이트
      const postRef = db.collection('posts').doc(postId);
      const postDoc = await transaction.get(postRef);

      if (!postDoc.exists || postDoc.data().userId !== uid) {
        throw new HttpsError('not-found', '원고를 찾을 수 없습니다.');
      }

      // 이미 발행된 원고인지 확인
      if (postDoc.data().publishUrl) {
        throw new HttpsError('already-exists', '이미 발행된 원고입니다.');
      }

      transaction.update(postRef, {
        publishUrl: publishUrl,
        publishedAt: publishedAt,
        status: 'published',
        updatedAt: now
      });

      // 2. 발행 기록 추가
      const publishingRef = db.collection('user_publishing').doc(uid);
      const publishingDoc = await transaction.get(publishingRef);

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
    const monthlyTarget = getMonthlyTarget(userRole);

    // 현재 월 정보
    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

    // 현재 달에 생성된 포스트 개수 조회 (저장 시점 기준)
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59, 999);

    const postsSnapshot = await db.collection('posts')
      .where('userId', '==', uid)
      .where('createdAt', '>=', startOfMonth)
      .where('createdAt', '<=', endOfMonth)
      .get();

    const publishedThisMonth = postsSnapshot.size; // 저장된 포스트 개수

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

module.exports = {
  publishPost,
  getPublishingStats,
  checkBonusEligibility,
  useBonusGeneration,
  getMonthlyTarget
};