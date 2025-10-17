/**
 * functions/handlers/dashboard.js
 * 대시보드 데이터 조회를 위한 함수입니다.
 */

'use strict';

const { db, admin } = require('../utils/firebaseAdmin');
const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');
const { auth } = require('../common/auth');

exports.getDashboardData = wrap(async (req) => {
  const { uid } = await auth(req);

  // 사용자 정보 가져오기 (구독 상태 확인)
  const userDoc = await db.collection('users').doc(uid).get();
  const userData = userDoc.data() || {};

  const subscriptionStatus = userData.subscriptionStatus || 'trial';
  const monthlyLimit = userData.monthlyLimit || 8;
  const trialPostsRemaining = userData.trialPostsRemaining || 0;

  // 사용량 정보
  const now = new Date();
  const thisMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  const usageSnapshot = await db.collection('posts')
    .where('userId', '==', uid)
    .where('createdAt', '>=', admin.firestore.Timestamp.fromDate(thisMonth))
    .get();

  const postsGenerated = usageSnapshot.size;

  // 구독 상태별 사용량 계산
  let canGenerate;
  let remainingPosts;

  if (subscriptionStatus === 'trial') {
    // 무료 체험: trialPostsRemaining 기준
    canGenerate = trialPostsRemaining > 0;
    remainingPosts = trialPostsRemaining;
  } else if (subscriptionStatus === 'active') {
    // 유료 구독: monthlyLimit 기준
    canGenerate = postsGenerated < monthlyLimit;
    remainingPosts = monthlyLimit - postsGenerated;
  } else {
    // 만료 또는 기타 상태
    canGenerate = false;
    remainingPosts = 0;
  }

  const usage = {
    postsGenerated,
    monthlyLimit,
    trialPostsRemaining,
    subscriptionStatus,
    canGenerate,
    remainingPosts
  };

  // 최근 포스트 조회 (최대 5개)
  const recentPostsSnapshot = await db.collection('posts')
    .where('userId', '==', uid)
    .orderBy('createdAt', 'desc')
    .limit(5)
    .get();

  const recentPosts = [];
  recentPostsSnapshot.forEach(doc => {
    const data = doc.data();
    recentPosts.push({
      id: doc.id,
      title: data.title || '제목 없음',
      category: data.options?.category || '일반',
      status: data.status || 'draft',
      content: data.content || '', // content 필드 추가
      wordCount: data.wordCount || 0, // 추가로 wordCount도 포함
      createdAt: data.createdAt?.toDate?.().toISOString() || new Date().toISOString(),
      updatedAt: data.updatedAt?.toDate?.().toISOString() || null // updatedAt도 추가
    });
  });

  return ok({
    usage,
    recentPosts
  });
});
