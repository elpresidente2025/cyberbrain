'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { httpWrap } = require('../../common/http-wrap');
const { admin, db } = require('../../utils/firebaseAdmin');
const { ok } = require('../../utils/posts/helpers');
const { endSession } = require('../../services/posts/profile-loader');
const { updateMemoryOnSelection } = require('../../services/memory');
const { evaluateContent, meetsQualityThreshold } = require('../../services/evaluation');

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
  const sessionId = data.sessionId || null; // 생성 세션 ID

  console.log('POST saveSelectedPost 시작:', { userId: uid, sessionId, data });

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
      status: 'scheduled',
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      updatedAt: admin.firestore.FieldValue.serverTimestamp()
    };

    // 원고 저장
    const docRef = await db.collection('posts').add(postData);
    const postId = docRef.id;

    // 📊 품질 평가 (비동기 - 응답 대기 없이 진행)
    const evaluationPromise = (async () => {
      try {
        const evaluation = await evaluateContent({
          content: data.content,
          category: data.category,
          topic: data.topic || data.title,
          author: data.authorName || '작성자'
        });

        // 평가 결과를 posts 문서에 업데이트
        await docRef.update({
          evaluation: {
            overallScore: evaluation.overallScore,
            scores: evaluation.scores,
            summary: evaluation.summary,
            evaluatedAt: admin.firestore.FieldValue.serverTimestamp()
          }
        });

        console.log('📊 [Evaluation] 평가 완료:', {
          postId,
          score: evaluation.overallScore,
          meetsThreshold: meetsQualityThreshold(evaluation)
        });

        return evaluation;
      } catch (evalError) {
        console.warn('⚠️ [Evaluation] 평가 실패 (무시):', evalError.message);
        return null;
      }
    })();

    // 🧠 메모리 업데이트 (선택된 글 학습) - 평가 결과 포함
    try {
      const keywords = Array.isArray(data.keywords)
        ? data.keywords
        : (data.keywords || '').split(',').map(k => k.trim()).filter(k => k);

      // 평가 완료 대기 (최대 5초)
      let evaluation = null;
      try {
        evaluation = await Promise.race([
          evaluationPromise,
          new Promise(resolve => setTimeout(() => resolve(null), 5000))
        ]);
      } catch (e) {
        // 평가 타임아웃 - 무시
      }

      await updateMemoryOnSelection(uid, {
        category: data.category,
        content: data.content,
        title: data.title,
        topic: data.topic || '',
        keywords,
        qualityScore: evaluation?.overallScore || null
      });
      console.log('✅ 메모리 업데이트 완료 (선택된 글 학습)');
    } catch (memoryError) {
      console.warn('⚠️ 메모리 업데이트 실패 (무시):', memoryError.message);
    }

    // 세션 종료 처리 (activeGenerationSession 삭제)
    await endSession(uid);
    console.log('✅ 생성 세션 종료 (원고 저장 완료)');

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
