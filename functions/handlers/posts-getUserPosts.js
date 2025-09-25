'use strict';

const { wrap } = require('../common/wrap');
const { auth } = require('../common/auth');
const { admin, db } = require('../utils/firebaseAdmin');

// 사용자의 포스트 목록 조회
exports.getUserPosts = wrap(async (req) => {
  const { uid } = await auth(req);

  console.log('📋 getUserPosts 호출됨:', { uid });

  try {
    // Firestore에서 사용자의 posts 가져오기
    const postsRef = db.collection('posts');
    const snapshot = await postsRef
      .where('userId', '==', uid)
      .orderBy('createdAt', 'desc')
      .limit(100)
      .get();

    const posts = [];
    snapshot.forEach(doc => {
      const data = doc.data();
      posts.push({
        id: doc.id,
        ...data,
        createdAt: data.createdAt?.toDate?.()?.toISOString() || data.createdAt,
        updatedAt: data.updatedAt?.toDate?.()?.toISOString() || data.updatedAt,
        publishedAt: data.publishedAt?.toDate?.()?.toISOString() || data.publishedAt
      });
    });

    console.log('✅ getUserPosts 성공:', {
      uid,
      postsCount: posts.length,
      firstPost: posts[0]?.id
    });

    return {
      success: true,
      data: {
        posts: posts,
        count: posts.length
      }
    };

  } catch (error) {
    console.error('❌ getUserPosts 오류:', error);
    throw new Error('포스트 목록을 가져오는 중 오류가 발생했습니다: ' + error.message);
  }
});