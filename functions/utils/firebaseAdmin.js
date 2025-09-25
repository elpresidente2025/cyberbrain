'use strict';

const admin = require('firebase-admin');

// Firebase Admin 초기화 (이미 초기화되어 있지 않은 경우에만)
if (!admin.apps.length) {
  admin.initializeApp();
}

// 공통으로 사용할 인스턴스들 export
exports.admin = admin;
exports.db = admin.firestore();
exports.auth = admin.auth();