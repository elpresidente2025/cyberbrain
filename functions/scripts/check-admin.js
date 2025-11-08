/**
 * 관리자 계정 확인 및 업데이트 스크립트
 *
 * 사용법:
 * node scripts/check-admin.js <UID>
 */

const admin = require('firebase-admin');

// Firebase Admin 초기화
if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();

async function checkAndUpdateAdmin(uid) {
  try {
    console.log(`🔍 사용자 조회 중: ${uid}`);

    const userDoc = await db.collection('users').doc(uid).get();

    if (!userDoc.exists) {
      console.error(`❌ 사용자를 찾을 수 없습니다: ${uid}`);
      return;
    }

    const userData = userDoc.data();
    console.log('\n📋 현재 사용자 데이터:');
    console.log(JSON.stringify(userData, null, 2));

    console.log('\n🔑 주요 필드:');
    console.log(`- isAdmin: ${userData.isAdmin}`);
    console.log(`- role: ${userData.role}`);
    console.log(`- subscriptionStatus: ${userData.subscriptionStatus}`);
    console.log(`- trialPostsRemaining: ${userData.trialPostsRemaining}`);
    console.log(`- monthlyLimit: ${userData.monthlyLimit}`);

    // isAdmin 필드가 없거나 false인 경우
    if (!userData.isAdmin) {
      console.log('\n⚠️ isAdmin 필드가 false이거나 없습니다.');
      console.log('관리자로 설정하려면 다음 명령어를 사용하세요:');
      console.log(`\nnode scripts/set-admin.js ${uid}\n`);
    } else {
      console.log('\n✅ 이미 관리자로 설정되어 있습니다.');
    }

  } catch (error) {
    console.error('❌ 에러 발생:', error);
  } finally {
    process.exit(0);
  }
}

// 명령줄 인자 확인
const uid = process.argv[2];

if (!uid) {
  console.error('❌ UID를 입력해주세요.');
  console.log('사용법: node scripts/check-admin.js <UID>');
  process.exit(1);
}

checkAndUpdateAdmin(uid);
