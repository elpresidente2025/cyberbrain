/**
 * 특정 사용자의 Firestore 데이터 확인 스크립트
 * 사용법: node scripts/check-user-data.js "김상봉"
 */

const admin = require('firebase-admin');
const path = require('path');

// Firebase Admin 초기화
const serviceAccountPath = path.join(__dirname, '..', 'serviceAccount.json');
try {
  const serviceAccount = require(serviceAccountPath);
  admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
  });
} catch (e) {
  console.error('서비스 계정 키 파일을 찾을 수 없습니다:', serviceAccountPath);
  console.log('Firebase 에뮬레이터 또는 환경 변수를 사용해 주세요.');
  process.exit(1);
}

const db = admin.firestore();

async function checkUserData(searchName) {
  console.log(`\n🔍 "${searchName}" 사용자 데이터 조회 중...\n`);

  // 이름으로 사용자 검색
  const usersSnapshot = await db.collection('users').get();

  let foundUsers = [];
  usersSnapshot.forEach(doc => {
    const data = doc.data();
    if (data.name && data.name.includes(searchName)) {
      foundUsers.push({ uid: doc.id, ...data });
    }
  });

  if (foundUsers.length === 0) {
    console.log(`❌ "${searchName}" 이름을 포함한 사용자를 찾을 수 없습니다.`);

    // 전체 사용자 목록 출력
    console.log('\n📋 전체 사용자 목록:');
    usersSnapshot.forEach(doc => {
      const data = doc.data();
      console.log(`  - ${data.name || '이름없음'} (${data.email || '이메일없음'})`);
    });
    return;
  }

  for (const user of foundUsers) {
    console.log('='.repeat(60));
    console.log(`👤 사용자: ${user.name}`);
    console.log('='.repeat(60));

    // 주요 프로필 필드 확인
    const profileFields = [
      'name', 'email', 'position', 'status',
      'regionMetro', 'regionLocal', 'electoralDistrict',
      'districtKey', 'targetElection'
    ];

    console.log('\n📌 프로필 정보:');
    for (const field of profileFields) {
      const value = user[field];
      const status = value ? '✅' : '❌';
      console.log(`  ${status} ${field}: ${JSON.stringify(value) || '(없음)'}`);
    }

    // 개인화 정보 확인
    const personalFields = [
      'ageDecade', 'gender', 'familyStatus', 'backgroundCareer',
      'localConnection', 'politicalExperience', 'customTitle'
    ];

    console.log('\n📌 개인화 정보:');
    for (const field of personalFields) {
      const value = user[field];
      const status = value ? '✅' : '⬜';
      console.log(`  ${status} ${field}: ${JSON.stringify(value) || '(없음)'}`);
    }

    // 시스템 필드 확인
    console.log('\n📌 시스템 정보:');
    console.log(`  - uid: ${user.uid}`);
    console.log(`  - isActive: ${user.isActive}`);
    console.log(`  - role: ${user.role || '일반 사용자'}`);
    console.log(`  - createdAt: ${user.createdAt?.toDate?.() || user.createdAt || '(없음)'}`);
    console.log(`  - updatedAt: ${user.updatedAt?.toDate?.() || user.updatedAt || '(없음)'}`);

    // Bio 컬렉션 확인
    console.log('\n📌 Bio 정보:');
    try {
      const bioDoc = await db.collection('bios').doc(user.uid).get();
      if (bioDoc.exists) {
        const bioData = bioDoc.data();
        console.log(`  ✅ Bio 문서 존재`);
        console.log(`  - content 길이: ${bioData.content?.length || 0}자`);
        console.log(`  - entries 개수: ${bioData.entries?.length || 0}개`);
        console.log(`  - version: ${bioData.version || 0}`);
      } else {
        console.log(`  ❌ Bio 문서 없음`);
      }
    } catch (e) {
      console.log(`  ⚠️ Bio 조회 실패: ${e.message}`);
    }

    // 전체 필드 목록
    console.log('\n📌 전체 필드 목록:');
    const allFields = Object.keys(user).sort();
    console.log(`  총 ${allFields.length}개 필드: ${allFields.join(', ')}`);
  }

  console.log('\n');
}

// 메인 실행
const searchName = process.argv[2] || '김상봉';
checkUserData(searchName)
  .then(() => process.exit(0))
  .catch(err => {
    console.error('오류:', err);
    process.exit(1);
  });
