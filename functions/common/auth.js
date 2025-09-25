'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { db } = require('../utils/firebaseAdmin');

/**
 * 인증 정보 추출 - Firebase Auth 또는 네이버 세션 토큰 지원
 */
exports.auth = async (request) => {
  // Firebase Auth 토큰이 있는 경우 (기존 방식)
  if (request.auth) {
    return {
      uid: request.auth.uid,
      token: request.auth.token || {}
    };
  }
  
  // 네이버 사용자의 경우 요청 데이터에서 UID와 인증 정보 추출
  const naverAuth = request.data?.__naverAuth;
  if (naverAuth && naverAuth.uid && naverAuth.provider === 'naver') {
    // UID 검증 - Firestore에서 사용자 존재 확인
    try {
      const userDoc = await db.collection('users').doc(naverAuth.uid).get();
      if (userDoc.exists && userDoc.data().provider === 'naver') {
        // 인증된 요청 데이터에서 __naverAuth 제거
        delete request.data.__naverAuth;
        return {
          uid: naverAuth.uid,
          token: { provider: 'naver' }
        };
      }
    } catch (error) {
      console.error('네이버 사용자 검증 실패:', error);
    }
  }
  
  throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
};