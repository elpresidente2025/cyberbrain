/**
 * 특정 사용자의 세션 초기화
 *
 * 사용법: node functions/scripts/reset-user-session.js <userId>
 */

'use strict';

const { admin, db } = require('../utils/firebaseAdmin');

async function resetUserSession(userId) {
  if (!userId) {
    console.error('❌ 사용법: node reset-user-session.js <userId>');
    process.exit(1);
  }

  console.log('🔄 세션 초기화 시작:', userId);

  try {
    const userRef = db.collection('users').doc(userId);
    const userDoc = await userRef.get();

    if (!userDoc.exists) {
      console.error('❌ 사용자를 찾을 수 없습니다:', userId);
      process.exit(1);
    }

    const userData = userDoc.data();
    console.log('📊 현재 세션 상태:', userData.activeGenerationSession);

    await userRef.update({
      activeGenerationSession: null
    });

    console.log('✅ 세션 초기화 완료!');
    console.log('💡 이제 새 생성을 시작할 수 있습니다.');

  } catch (error) {
    console.error('❌ 오류 발생:', error.message);
    process.exit(1);
  }

  process.exit(0);
}

// 실행
const userId = process.argv[2];
resetUserSession(userId);
