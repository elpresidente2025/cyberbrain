/**
 * 손상된 status 필드 복구 스크립트
 * "현역"이 "?역"으로 깨진 경우 복구
 */

const admin = require('firebase-admin');
const path = require('path');

const serviceAccountPath = path.join(__dirname, '..', 'serviceAccount.json');
const serviceAccount = require(serviceAccountPath);

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount)
});

const db = admin.firestore();

async function fixStatusEncoding() {
  console.log('손상된 status 필드 복구 시작...\n');

  const usersSnapshot = await db.collection('users').get();
  let fixed = 0;

  for (const doc of usersSnapshot.docs) {
    const data = doc.data();
    const status = data.status;

    if (!status) continue;

    // 손상된 패턴 확인
    const isCorrupted = status.includes('?') ||
                        status.charCodeAt(0) === 65533 ||
                        (status.length > 1 && status.charCodeAt(1) === 65533);

    if (isCorrupted) {
      console.log('발견:', doc.id, '-', data.name);
      console.log('  손상된 값:', status, '(길이:', status.length + ')');

      // 패턴 분석하여 복구
      let newStatus = null;
      if (status.endsWith('역')) {
        newStatus = '현역';
      } else if (status.endsWith('비')) {
        newStatus = '예비';
      }

      if (newStatus) {
        await db.collection('users').doc(doc.id).update({ status: newStatus });
        console.log('  복구:', newStatus);
        fixed++;
      } else {
        console.log('  복구 불가 - 수동 확인 필요');
      }
    }
  }

  console.log('\n결과: ' + fixed + '명 복구 완료');
}

fixStatusEncoding()
  .then(() => process.exit(0))
  .catch(err => {
    console.error('오류:', err);
    process.exit(1);
  });
