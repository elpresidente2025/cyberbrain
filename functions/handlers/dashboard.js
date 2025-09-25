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

  // 사용량 정보
  const now = new Date();
  const thisMonth = new Date(now.getFullYear(), now.getMonth(), 1);
  const usageSnapshot = await db.collection('posts')
    .where('userId', '==', uid)
    .where('createdAt', '>=', admin.firestore.Timestamp.fromDate(thisMonth))
    .get();

  const usage = {
    postsGenerated: usageSnapshot.size,
    monthlyLimit: 50, // 이 값은 나중에 설정에서 가져오도록 변경 가능
    canGenerate: usageSnapshot.size < 50
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
