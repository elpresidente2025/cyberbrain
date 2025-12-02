const admin = require('./functions/node_modules/firebase-admin');
const serviceAccount = require('./functions/serviceAccountKey.json');

if (!admin.apps.length) {
  admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
  });
}

const db = admin.firestore();

async function checkVerification() {
  const userId = 'YQLKaL6onagwrOSSrOWf';

  console.log('=== 사용자 프로필 확인 ===');
  const userDoc = await db.collection('users').doc(userId).get();
  if (userDoc.exists) {
    const userData = userDoc.data();
    console.log('verificationStatus:', userData.verificationStatus);
    console.log('lastVerification:', userData.lastVerification);
    console.log('name:', userData.name);
  }

  console.log('\n=== 인증 요청 확인 ===');
  const requests = await db.collection('verification_requests')
    .where('userId', '==', userId)
    .orderBy('requestedAt', 'desc')
    .limit(5)
    .get();

  requests.forEach(doc => {
    const data = doc.data();
    console.log('\n요청 ID:', doc.id);
    console.log('타입:', data.type);
    console.log('상태:', data.status);
    console.log('사유:', data.reason);
    console.log('요청 시간:', data.requestedAt?.toDate());
    if (data.partyInfo) {
      console.log('추출된 정보:', data.partyInfo);
    }
    if (data.paymentInfo) {
      console.log('추출된 정보:', data.paymentInfo);
    }
  });

  console.log('\n=== 인증 이력 확인 ===');
  const verifications = await db.collection('users').doc(userId)
    .collection('verifications')
    .orderBy('verifiedAt', 'desc')
    .limit(5)
    .get();

  verifications.forEach(doc => {
    const data = doc.data();
    console.log('\n인증 ID:', doc.id);
    console.log('타입:', data.type);
    console.log('상태:', data.status);
    console.log('분기:', data.quarter);
    console.log('인증 시간:', data.verifiedAt?.toDate());
  });
}

checkVerification().then(() => {
  console.log('\n완료');
  process.exit(0);
}).catch(err => {
  console.error('에러:', err);
  process.exit(1);
});
