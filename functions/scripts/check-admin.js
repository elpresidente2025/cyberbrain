/**
 * 관리자 계정 확인 스크립트
 *
 * 사용법:
 * node scripts/check-admin.js <UID>
 */

const admin = require('firebase-admin');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();

function isAdminUser(userData = {}) {
  const role = String(userData.role || '').trim().toLowerCase();
  return role === 'admin' || userData.isAdmin === true;
}

async function checkAdmin(uid) {
  try {
    console.log(`🔍 사용자 조회 중: ${uid}`);

    const userDoc = await db.collection('users').doc(uid).get();

    if (!userDoc.exists) {
      console.error(`❌ 사용자를 찾을 수 없습니다: ${uid}`);
      return;
    }

    const userData = userDoc.data() || {};
    console.log('\n📋 현재 사용자 데이터:');
    console.log(JSON.stringify(userData, null, 2));

    console.log('\n🔑 주요 필드:');
    console.log(`- role: ${userData.role}`);
    console.log(`- isAdmin: ${userData.isAdmin}`);
    console.log(`- derivedAdmin: ${isAdminUser(userData)}`);
    console.log(`- subscriptionStatus: ${userData.subscriptionStatus}`);
    console.log(`- trialPostsRemaining: ${userData.trialPostsRemaining}`);
    console.log(`- monthlyLimit: ${userData.monthlyLimit}`);

    if (!isAdminUser(userData)) {
      console.log('\n⚠️ 관리자 role이 없고 legacy isAdmin도 없습니다.');
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

const uid = process.argv[2];

if (!uid) {
  console.error('❌ UID를 입력해주세요.');
  console.log('사용법: node scripts/check-admin.js <UID>');
  process.exit(1);
}

checkAdmin(uid);
