/**
 * 관리자 권한 설정 스크립트
 *
 * 사용법:
 * node scripts/set-admin.js <UID>
 */

const admin = require('firebase-admin');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();

function isAdminUser(userData = {}) {
  const role = String(userData.role || '').trim().toLowerCase();
  return role === 'admin';
}

async function setAdmin(uid) {
  try {
    console.log(`🔍 사용자 조회 중: ${uid}`);

    const userRef = db.collection('users').doc(uid);
    const userDoc = await userRef.get();

    if (!userDoc.exists) {
      console.error(`❌ 사용자를 찾을 수 없습니다: ${uid}`);
      return;
    }

    const userData = userDoc.data() || {};
    console.log(`\n📋 현재 사용자: ${userData.name || 'Unknown'}`);
    console.log(`- 현재 role: ${userData.role || 'user'}`);
    console.log(`- 현재 isAdmin: ${userData.isAdmin || false}`);
    console.log(`- 파생 admin: ${isAdminUser(userData)}`);

    console.log('\n🔧 관리자 권한 설정 중...');

    await userRef.update({
      role: 'admin',
      isAdmin: admin.firestore.FieldValue.delete(),
      updatedAt: admin.firestore.FieldValue.serverTimestamp()
    });

    console.log('✅ 관리자 권한이 설정되었습니다.');

    const updatedDoc = await userRef.get();
    const updatedData = updatedDoc.data() || {};

    console.log('\n📋 업데이트된 데이터:');
    console.log(`- role: ${updatedData.role || 'user'}`);
    console.log(`- isAdmin: ${updatedData.isAdmin}`);
    console.log(`- 파생 admin: ${isAdminUser(updatedData)}`);
  } catch (error) {
    console.error('❌ 에러 발생:', error);
  } finally {
    process.exit(0);
  }
}

const uid = process.argv[2];

if (!uid) {
  console.error('❌ UID를 입력해주세요.');
  console.log('사용법: node scripts/set-admin.js <UID>');
  process.exit(1);
}

setAdmin(uid);
