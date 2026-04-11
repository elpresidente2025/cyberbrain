/* 네이버 사용자 목록을 확인하는 스크립트 */
'use strict';

const path = require('path');
const fs = require('fs');
const admin = require('firebase-admin');

const PROJECT_ID = 'ai-secretary-6e9c8';

let _app;

try {
  if (process.env.GOOGLE_APPLICATION_CREDENTIALS) {
    _app = admin.initializeApp({
      credential: admin.credential.cert(require(process.env.GOOGLE_APPLICATION_CREDENTIALS)),
      projectId: PROJECT_ID
    });
  } else {
    const saPath = path.join(__dirname, '../serviceAccount.json');
    if (fs.existsSync(saPath)) {
      _app = admin.initializeApp({
        credential: admin.credential.cert(require(saPath)),
        projectId: PROJECT_ID
      });
    } else {
      _app = admin.initializeApp({
        credential: admin.credential.applicationDefault(),
        projectId: PROJECT_ID
      });
    }
  }
} catch (error) {
  console.error('❌ Firebase Admin 초기화 실패:', error.message);
  process.exit(1);
}

const db = admin.firestore();

function isAdminUser(userData = {}) {
  const role = String(userData.role || '').trim().toLowerCase();
  return role === 'admin';
}

(async () => {
  try {
    console.log('🔍 네이버 사용자 목록 조회 중...');

    const naverUsers = await db.collection('users')
      .where('provider', '==', 'naver')
      .get();

    if (naverUsers.empty) {
      console.log('❌ 네이버 사용자가 없습니다.');
      process.exit(0);
    }

    console.log('\n📋 네이버 사용자 목록:');
    console.log('=====================================');

    naverUsers.forEach((doc, index) => {
      const data = doc.data() || {};
      console.log(`${index + 1}. UID: ${doc.id}`);
      console.log(`   네이버 ID: ${data.naverUserId || '(없음)'}`);
      console.log(`   이름: ${data.name || '(없음)'}`);
      console.log(`   관리자: ${isAdminUser(data) ? 'YES' : 'NO'}`);
      console.log(`   등록일: ${data.createdAt ? new Date(data.createdAt.toDate()).toLocaleString() : '(없음)'}`);
      console.log('-------------------------------------');
    });

    console.log('\n💡 관리자로 설정하려면:');
    console.log('node scripts/bootstrap-naver-admin.js --naverUserId [네이버_ID]');
  } catch (error) {
    console.error('❌ 오류:', error);
  }
})();
