'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { httpWrap } = require('../../common/http-wrap');
const { admin, db } = require('../../utils/firebaseAdmin');
const { ok } = require('../../utils/posts/helpers');

/**
 * 선택된 원고 저장
 */
exports.saveSelectedPost = httpWrap(async (req) => {
  let uid;

  // 데이터 추출 - Firebase SDK와 HTTP 요청 모두 처리
  let requestData = req.data || req.rawRequest?.body || {};

  // 중첩된 data 구조 처리
  if (requestData.data && typeof requestData.data === 'object') {
    requestData = requestData.data;
  }

  // 사용자 인증 데이터 확인 (모든 사용자는 네이버 로그인)
  if (requestData.__naverAuth && requestData.__naverAuth.uid && requestData.__naverAuth.provider === 'naver') {
    console.log('📱 사용자 인증 처리:', requestData.__naverAuth.uid);
    uid = requestData.__naverAuth.uid;
    delete requestData.__naverAuth;
  } else {
    const authHeader = (req.rawRequest && (req.rawRequest.headers.authorization || req.rawRequest.headers.Authorization)) || '';
    if (authHeader && authHeader.startsWith('Bearer ')) {
      const idToken = authHeader.split('Bearer ')[1];
      try {
        const verified = await admin.auth().verifyIdToken(idToken);
        uid = verified.uid;
      } catch (authError) {
        console.error('ID token verify failed:', authError);
        throw new HttpsError('unauthenticated', '유효하지 않은 인증 토큰입니다.');
      }
    } else {
      console.error('인증 정보 누락:', requestData);
      throw new HttpsError('unauthenticated', '인증이 필요합니다.');
    }
  }

  const data = requestData;

  console.log('POST saveSelectedPost 시작:', { userId: uid, data });

  if (!data.title || !data.content) {
    throw new HttpsError('invalid-argument', '제목과 내용이 필요합니다');
  }

  try {
    const wordCount = data.content.replace(/<[^>]*>/g, '').length;

    const postData = {
      userId: uid,
      title: data.title,
      content: data.content,
      category: data.category || '일반',
      subCategory: data.subCategory || '',
      keywords: data.keywords || '',
      wordCount,
      status: 'published',
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      updatedAt: admin.firestore.FieldValue.serverTimestamp()
    };

    const docRef = await db.collection('posts').add(postData);

    console.log('POST saveSelectedPost 완료:', { postId: docRef.id, wordCount });

    return ok({
      success: true,
      message: '원고가 성공적으로 저장되었습니다.',
      postId: docRef.id
    });

  } catch (error) {
    console.error('POST saveSelectedPost 오류:', error.message);
    throw new HttpsError('internal', '원고 저장에 실패했습니다.');
  }
});
