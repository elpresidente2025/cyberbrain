/* 사용법:
   node functions/scripts/bootstrap-admin.js --email admin@yourdomain.com
   환경: Firebase CLI 로그인 또는 serviceAccount.json 사용
*/
'use strict';
const path = require('path');
const fs = require('fs');
const admin = require('firebase-admin');

console.log('🚀 관리자 부트스트랩 시작...');

// 🔥 프로젝트 ID 명시적 설정
const PROJECT_ID = 'ai-secretary-6e9c8';

// 🔧 수정: app 변수를 _app으로 변경 (사용되지 않는 변수 ESLint 에러 해결)
let _app;

try {
  // 방법 1: 환경변수 GOOGLE_APPLICATION_CREDENTIALS 확인
  if (process.env.GOOGLE_APPLICATION_CREDENTIALS) {
    console.log('✅ 환경변수에서 서비스 계정 키 사용');
    _app = admin.initializeApp({ 
      credential: admin.credential.cert(require(process.env.GOOGLE_APPLICATION_CREDENTIALS)),
      projectId: PROJECT_ID  // 🔥 프로젝트 ID 명시
    });
  } 
  // 방법 2: serviceAccount.json 파일 확인
  else {
    const saPath = path.join(__dirname, '../serviceAccount.json');
    if (fs.existsSync(saPath)) {
      console.log('✅ serviceAccount.json 파일 사용');
      _app = admin.initializeApp({ 
        credential: admin.credential.cert(require(saPath)),
        projectId: PROJECT_ID  // 🔥 프로젝트 ID 명시
      });
    }
    // 방법 3: Firebase CLI 기본 자격증명 사용
    else {
      console.log('✅ Firebase CLI 기본 자격증명 사용 (ADC)');
      _app = admin.initializeApp({
        credential: admin.credential.applicationDefault(),
        projectId: PROJECT_ID  // 🔥 프로젝트 ID 명시
      });
    }
  }
  
  console.log('🔥 Firebase Admin SDK 초기화 성공');
  console.log('📋 프로젝트 ID:', PROJECT_ID);
} catch (error) {
  console.error('❌ Firebase Admin 초기화 실패:', error.message);
  console.log('\n📋 해결 방법:');
  console.log('1. Firebase CLI 로그인: firebase login');
  console.log('2. 또는 serviceAccount.json 파일을 functions/ 폴더에 배치');
  console.log('3. 또는 GOOGLE_APPLICATION_CREDENTIALS 환경변수 설정');
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

    const email = getArg('email');
    const uidArg = getArg('uid');
    if (!email && !uidArg) {
      console.error('❌ 사용자 지정 필요: --email 또는 --uid');
      console.log('예시: node scripts/bootstrap-admin.js --email kjk6206@gmail.com');
      process.exit(1);
    }

    console.log('🔍 사용자 검색 중:', email || uidArg);

    // 이미 관리자 있는지 확인
    const exists = await db.collection('users').where('isAdmin','==',true).limit(1).get();
    if (!exists.empty) {
      console.log('ℹ️ 이미 관리자가 존재합니다. 새 관리자도 추가합니다.');
    }

    // 사용자 찾기
    const user = uidArg ? await admin.auth().getUser(uidArg)
                        : await admin.auth().getUserByEmail(email);

    console.log('👤 사용자 찾음:');
    console.log('   UID:', user.uid);
    console.log('   Email:', user.email);
    console.log('   Name:', user.displayName || '(이름 없음)');

    // Custom Claims 설정
    console.log('🔑 Custom Claims 설정 중...');
    await admin.auth().setCustomUserClaims(user.uid, { admin: true });
    console.log('✅ Custom Claims 설정 완료 (admin: true)');

    // Firestore 문서 업데이트
    console.log('💾 Firestore 문서 업데이트 중...');
    await db.collection('users').doc(user.uid).set({
      isAdmin: true,
      role: 'admin',
      updatedAt: admin.firestore.FieldValue.serverTimestamp(),
      // 기존 데이터 유지를 위한 추가 필드
      email: user.email,
      name: user.displayName || '',
    }, { merge: true });

    console.log('✅ Firestore 문서 업데이트 완료');
    console.log('');
    console.log('🎉 관리자 부트스트랩 성공!');
    console.log('   사용자:', user.email);
    console.log('   UID:', user.uid);
    console.log('   권한: admin');
    console.log('');
    console.log('📋 다음 단계:');
    console.log('1. 브라우저에서 로그아웃 후 다시 로그인');
    console.log('2. 또는 브라우저 새로고침 (F5)');
    console.log('3. /admin 페이지 접속 시도');
    console.log('4. 토큰 새로고침이 필요하면 로그아웃/로그인');
    
    process.exit(0);
  } catch (error) {
    console.error('❌ 처리 중 오류:', error);
    if (error.code === 'auth/user-not-found') {
      console.log('💡 해당 이메일로 등록된 사용자를 찾을 수 없습니다.');
      console.log('   먼저 웹 앱에서 회원가입을 완료해주세요.');
    }
    process.exit(1);
  }
})();