/**
 * 알림 시스템 테스트 스크립트
 *
 * 사용법:
 * node functions/scripts/test-notification.js <userId> <districtKey>
 *
 * 예시:
 * node functions/scripts/test-notification.js abc123 "국회의원__서울특별시__강남구__가선거구"
 */

'use strict';

const { admin, db } = require('../utils/firebaseAdmin');
const { notifyPriorityGained } = require('../services/notification');

async function testNotification() {
  const userId = process.argv[2];
  const districtKey = process.argv[3] || '국회의원__서울특별시__강남구__가선거구';

  if (!userId) {
    console.error('❌ 사용법: node test-notification.js <userId> [districtKey]');
    console.error('예시: node test-notification.js abc123');
    process.exit(1);
  }

  console.log('📧 알림 테스트 시작...');
  console.log('사용자:', userId);
  console.log('선거구:', districtKey);
  console.log('');

  try {
    // 1. 사용자 확인
    console.log('1️⃣ 사용자 정보 확인 중...');
    const userDoc = await db.collection('users').doc(userId).get();

    if (!userDoc.exists) {
      console.error('❌ 사용자를 찾을 수 없습니다:', userId);
      process.exit(1);
    }

    const userData = userDoc.data();
    console.log('✅ 사용자 확인:', userData.name || userData.email);
    console.log('');

    // 2. 이메일 확인
    console.log('2️⃣ 이메일 주소 확인 중...');
    const userRecord = await admin.auth().getUser(userId);
    console.log('✅ 이메일:', userRecord.email);
    console.log('');

    // 3. 알림 발송
    console.log('3️⃣ 우선권 획득 알림 발송 중...');
    const result = await notifyPriorityGained({
      userId,
      districtKey,
      previousUserId: null
    });

    if (result.success) {
      console.log('✅ 알림 발송 완료!');
      console.log('');
      console.log('📝 다음 항목을 확인하세요:');
      console.log('1. Firestore → notifications 컬렉션에 새 문서 추가됨');
      console.log('2. Firestore → mail 컬렉션에 새 문서 추가됨');
      console.log('3. 이메일 수신함 확인 (스팸함도 확인)');
      console.log('');
      console.log('💡 mail 컬렉션에서 delivery.state를 확인하여 발송 상태를 볼 수 있습니다.');
    } else {
      console.error('❌ 알림 발송 실패:', result.error);
    }

  } catch (error) {
    console.error('❌ 오류 발생:', error.message);
    console.error(error.stack);
    process.exit(1);
  }

  process.exit(0);
}

// 스크립트 실행
testNotification();
