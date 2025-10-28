'use strict';

const { HttpsError } = require('firebase-functions/v2/https');

/**
 * 인증 정보 추출 - Firebase Auth 토큰만 허용
 *
 * 보안: 모든 사용자는 Firebase Custom Token을 통해 인증되어야 합니다.
 * 클라이언트가 제공하는 인증 정보는 절대 신뢰하지 않습니다.
 */
exports.auth = async (request) => {
  // Firebase Auth 토큰 검증
  if (!request.auth || !request.auth.uid) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  return {
    uid: request.auth.uid,
    token: request.auth.token || {}
  };
};