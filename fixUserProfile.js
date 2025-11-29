const admin = require('./functions/node_modules/firebase-admin');

admin.initializeApp();

const uid = 'DIedFGGUOzmoVU1rUWeF';

const updates = {
  profileComplete: true,
  trialPostsRemaining: 8,
  age: 20,
  bio: '인천 계양구 기초의원 출마를 준비하는 강정구입니다.',
  district: '계양구',
  updatedAt: admin.firestore.FieldValue.serverTimestamp()
};

admin.firestore().collection('users').doc(uid).update(updates)
  .then(() => {
    console.log('✅ 사용자 프로필 업데이트 완료');
    console.log('업데이트된 필드:', updates);
    process.exit(0);
  })
  .catch(err => {
    console.error('❌ 업데이트 실패:', err);
    process.exit(1);
  });
