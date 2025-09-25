/* 네이버 사용자를 관리자로 설정하는 스크립트
   사용법: node functions/scripts/bootstrap-naver-admin.js --naverUserId your_naver_id
*/
'use strict';
const path = require('path');
const fs = require('fs');
const admin = require('firebase-admin');

console.log('🚀 네이버 관리자 부트스트랩 시작...');

// 프로젝트 ID 명시적 설정
const PROJECT_ID = 'ai-secretary-6e9c8';

let _app;

try {
  // Firebase Admin SDK 초기화 (기존 bootstrap-admin.js와 동일한 로직)
  if (process.env.GOOGLE_APPLICATION_CREDENTIALS) {
    console.log('✅ 환경변수에서 서비스 계정 키 사용');
    _app = admin.initializeApp({ 
      credential: admin.credential.cert(require(process.env.GOOGLE_APPLICATION_CREDENTIALS)),
      projectId: PROJECT_ID
    });
  } else {
    const saPath = path.join(__dirname, '../serviceAccount.json');
    if (fs.existsSync(saPath)) {
      console.log('✅ serviceAccount.json 파일 사용');
      _app = admin.initializeApp({ 
        credential: admin.credential.cert(require(saPath)),
        projectId: PROJECT_ID
      });
    } else {
      console.log('✅ Firebase CLI 기본 자격증명 사용 (ADC)');
      _app = admin.initializeApp({
        credential: admin.credential.applicationDefault(),
        projectId: PROJECT_ID
      });
    }
  }
  
  console.log('🔥 Firebase Admin SDK 초기화 성공');
} catch (error) {
  console.error('❌ Firebase Admin 초기화 실패:', error.message);
  process.exit(1);
}

const db = admin.firestore();

(async () => {
  try {
    const args = process.argv.slice(2);
    const getArg = (name) => {
      const i = args.indexOf(`--${name}`);
      if (i >= 0) return args[i+1];
      const eq = args.find(a => a.startsWith(`--${name}=`));
      return eq ? eq.split('=')[1] : undefined;
    };

    const naverUserId = getArg('naverUserId');
    if (!naverUserId) {
      console.error('❌ 네이버 사용자 ID 필요: --naverUserId');
      console.log('예시: node scripts/bootstrap-naver-admin.js --naverUserId your_naver_id');
      process.exit(1);
    }

    console.log('🔍 네이버 사용자 검색 중:', naverUserId);

    // 네이버 사용자 찾기 (naverUserId 기준)
    const userQuery = await db.collection('users')
      .where('naverUserId', '==', naverUserId)
      .limit(1)
      .get();

    if (userQuery.empty) {
      console.error('❌ 해당 네이버 ID로 등록된 사용자를 찾을 수 없습니다:', naverUserId);
      console.log('💡 먼저 네이버 로그인으로 회원가입을 완료해주세요.');
      process.exit(1);
    }

    const userDoc = userQuery.docs[0];
    const userData = userDoc.data();
    const uid = userDoc.id;

    console.log('👤 네이버 사용자 찾음:');
    console.log('   UID:', uid);
    console.log('   네이버 ID:', userData.naverUserId);
    console.log('   이름:', userData.name || '(이름 없음)');
    console.log('   이메일:', userData.email || '(이메일 없음)');

    // 이미 관리자인지 확인
    if (userData.isAdmin === true) {
      console.log('ℹ️ 이미 관리자입니다.');
    }

    // Firestore 문서 업데이트 (네이버 사용자용)
    console.log('💾 네이버 사용자를 관리자로 설정 중...');
    await userDoc.ref.set({
      isAdmin: true,
      role: 'admin',
      updatedAt: admin.firestore.FieldValue.serverTimestamp(),
    }, { merge: true });

    console.log('✅ 네이버 관리자 설정 완료');
    console.log('');
    console.log('🎉 네이버 관리자 부트스트랩 성공!');
    console.log('   네이버 ID:', naverUserId);
    console.log('   사용자 이름:', userData.name);
    console.log('   UID:', uid);
    console.log('   권한: admin');
    console.log('');
    console.log('📋 다음 단계:');
    console.log('1. 브라우저에서 로그아웃 후 네이버로 다시 로그인');
    console.log('2. /admin 페이지 접속 시도');
    
    process.exit(0);
  } catch (error) {
    console.error('❌ 처리 중 오류:', error);
    process.exit(1);
  }
})();