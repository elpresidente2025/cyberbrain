'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { wrap } = require('../../common/wrap');
const { admin, db } = require('../../utils/firebaseAdmin');
const { auth } = require('../../common/auth');
const { ok, okMessage } = require('../../utils/posts/helpers');

/**
 * 사용자 포스트 목록 조회
 */
exports.getUserPosts = wrap(async (req) => {
  const { uid } = req.auth || {};

  if (!uid) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  console.log('POST getUserPosts 시작:', { userId: uid });

  try {
    const postsSnapshot = await db.collection('posts')
      .where('userId', '==', uid)
      .orderBy('createdAt', 'desc')
      .limit(50)
      .get();

    const posts = [];
    postsSnapshot.forEach(doc => {
      const data = doc.data();
      if (data.status !== 'draft') {
        posts.push({
          id: doc.id,
          ...data,
          createdAt: data.createdAt?.toDate?.()?.toISOString() || null,
          updatedAt: data.updatedAt?.toDate?.()?.toISOString() || null
        });
      }
    });

    console.log('POST getUserPosts 완료:', { count: posts.length });
    return ok({ posts });
  } catch (error) {
    console.error('POST getUserPosts 오류:', error.message);
    throw new HttpsError('internal', '포스트 목록을 불러오는데 실패했습니다.');
  }
});

/**
 * 특정 포스트 조회
 */
exports.getPost = wrap(async (req) => {
  const { uid } = req.auth || {};

  if (!uid) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  const { postId } = req.data || {};
  console.log('POST getPost 시작:', { userId: uid, postId });

  if (!postId) {
    throw new HttpsError('invalid-argument', '포스트 ID를 입력해주세요.');
  }

  try {
    const postDoc = await db.collection('posts').doc(postId).get();
    if (!postDoc.exists) {
      throw new HttpsError('not-found', '포스트를 찾을 수 없습니다.');
    }

    const data = postDoc.data();
    if (data.userId !== uid) {
      throw new HttpsError('permission-denied', '포스트를 조회할 권한이 없습니다.');
    }

    const post = {
      id: postDoc.id,
      ...data,
      createdAt: data.createdAt?.toDate?.()?.toISOString() || null,
      updatedAt: data.updatedAt?.toDate?.()?.toISOString() || null
    };

    console.log('POST getPost 완료:', postId);
    return ok({ post });
  } catch (error) {
    if (error.code) throw error;
    console.error('POST getPost 오류:', error.message);
    throw new HttpsError('internal', '포스트를 불러오는데 실패했습니다.');
  }
});

/**
 * 포스트 업데이트
 */
exports.updatePost = wrap(async (req) => {
  const { uid } = req.auth || {};

  if (!uid) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  const { postId, updates } = req.data || {};
  console.log('POST updatePost 시작:', { userId: uid, postId });

  if (!postId || !updates) {
    throw new HttpsError('invalid-argument', '포스트 ID와 수정 데이터를 입력해주세요.');
  }

  try {
    const postDoc = await db.collection('posts').doc(postId).get();
    if (!postDoc.exists) {
      throw new HttpsError('not-found', '포스트를 찾을 수 없습니다.');
    }

    const current = postDoc.data() || {};
    if (current.userId !== uid) {
      throw new HttpsError('permission-denied', '포스트를 수정할 권한이 없습니다.');
    }

    const allowed = ['title', 'content', 'category', 'subCategory', 'keywords', 'status'];
    const sanitized = {};
    for (const k of allowed) {
      if (updates[k] !== undefined) sanitized[k] = updates[k];
    }

    if (sanitized.content) {
      sanitized.wordCount = String(sanitized.content).replace(/<[^>]*>/g, '').replace(/\s/g, '').length;
    }
    sanitized.updatedAt = admin.firestore.FieldValue.serverTimestamp();

    await db.collection('posts').doc(postId).update(sanitized);
    console.log('POST updatePost 완료:', postId);
    return okMessage('포스트가 성공적으로 수정되었습니다');
  } catch (error) {
    if (error.code) throw error;
    console.error('POST updatePost 오류:', error.message);
    throw new HttpsError('internal', '포스트 수정에 실패했습니다.');
  }
});

/**
 * 포스트 삭제
 */
exports.deletePost = wrap(async (req) => {
  const { uid } = req.auth || {};

  if (!uid) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  const { postId } = req.data || {};
  console.log('POST deletePost 시작:', { userId: uid, postId });

  if (!postId) {
    throw new HttpsError('invalid-argument', '포스트 ID를 입력해주세요.');
  }

  try {
    const postDoc = await db.collection('posts').doc(postId).get();
    if (!postDoc.exists) {
      throw new HttpsError('not-found', '포스트를 찾을 수 없습니다.');
    }

    const data = postDoc.data() || {};
    if (data.userId !== uid) {
      throw new HttpsError('permission-denied', '포스트를 삭제할 권한이 없습니다.');
    }

    await db.collection('posts').doc(postId).delete();
    console.log('POST deletePost 완료:', postId);
    return okMessage('포스트가 성공적으로 삭제되었습니다');
  } catch (error) {
    if (error.code) throw error;
    console.error('POST deletePost 오류:', error.message);
    throw new HttpsError('internal', '포스트 삭제에 실패했습니다.');
  }
});

/**
 * 사용량 제한 체크
 */
exports.checkUsageLimit = wrap(async (req) => {
  const { uid } = req.auth || {};

  if (!uid) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  console.log('USAGE checkUsageLimit 시작:', { userId: uid });

  try {
    const now = new Date();
    const thisMonth = new Date(now.getFullYear(), now.getMonth(), 1);

    const snap = await db.collection('posts')
      .where('userId', '==', uid)
      .where('createdAt', '>=', admin.firestore.Timestamp.fromDate(thisMonth))
      .get();

    const used = snap.size;
    const limit = 50;

    console.log('USAGE checkUsageLimit 완료:', { used, limit });
    return ok({
      postsGenerated: used,
      monthlyLimit: limit,
      canGenerate: used < limit,
      remainingPosts: Math.max(0, limit - used),
    });
  } catch (error) {
    console.error('USAGE 오류:', error.message);
    if (error.code === 'failed-precondition') {
      return ok({
        postsGenerated: 0,
        monthlyLimit: 50,
        canGenerate: true,
        remainingPosts: 50
      });
    }
    throw new HttpsError('internal', '사용량을 확인하는데 실패했습니다.');
  }
});
