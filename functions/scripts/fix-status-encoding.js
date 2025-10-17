/**
 * 사용자 status 필드의 인코딩 문제 수정 스크립트
 * 사용법: node functions/scripts/fix-status-encoding.js
 */
'use strict';
const path = require('path');
const fs = require('fs');
const admin = require('firebase-admin');

console.log('🚀 사용자 status 필드 수정 스크립트 시작...');

// 프로젝트 ID 명시적 설정
const PROJECT_ID = 'ai-secretary-6e9c8';

// Firebase Admin 초기화
let _app;
try {
  if (process.env.GOOGLE_APPLICATION_CREDENTIALS) {
    console.log('✅ 환경변수에서 서비스 계정 키 사용');
    _app = admin.initializeApp({
      credential: admin.credential.cert(require(process.env.GOOGLE_APPLICATION_CREDENTIALS)),
      projectId: PROJECT_ID
    });
  } else {
    const saPath = path.join(__dirname, '../serviceAccount.json');
    if (fs.existsSync(saPath)) {
      console.log('✅ serviceAccount.json 파일 사용');
      _app = admin.initializeApp({
        credential: admin.credential.cert(require(saPath)),
        projectId: PROJECT_ID
      });
    } else {
      console.log('✅ Firebase CLI 기본 자격증명 사용 (ADC)');
      _app = admin.initializeApp({
        credential: admin.credential.applicationDefault(),
        projectId: PROJECT_ID
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

// 깨진 문자 -> 올바른 문자 매핑
const STATUS_FIX_MAP = {
  '?�역': '현역',
  '?꾩뿭': '현역',
  '?�비': '예비',
  '?뺤낯': '예비',
  '?�보': '후보',
  '?꾨낫': '후보'
};

// 성별 수정 매핑
const GENDER_FIX_MAP = {
  '?�성': '남성',
  '?⑥꽦': '남성',
  '?�성': '여성',
  '?ъ꽦': '여성'
};

(async () => {
  try {
    console.log('\n🔍 깨진 status/gender 필드를 가진 사용자 검색 중...\n');

    // 모든 사용자 조회
    const usersSnapshot = await db.collection('users').get();
    console.log(`📊 총 ${usersSnapshot.size}명의 사용자 발견\n`);

    let fixedCount = 0;
    let skippedCount = 0;
    const batch = db.batch();
    const updates = [];

    for (const doc of usersSnapshot.docs) {
      const data = doc.data();
      const uid = doc.id;
      const updateData = {};
      let needsUpdate = false;

      // status 필드 확인 및 수정
      if (data.status) {
        const currentStatus = String(data.status);

        // 깨진 문자 패턴 확인 (?로 시작하거나 특수문자 포함)
        if (currentStatus.includes('?') || /[^\uAC00-\uD7A3\u0020-\u007E]/.test(currentStatus)) {
          // 매핑 테이블에서 찾기
          const fixedStatus = STATUS_FIX_MAP[currentStatus];

          if (fixedStatus) {
            updateData.status = fixedStatus;
            needsUpdate = true;
            console.log(`✅ [${uid}] status: "${currentStatus}" → "${fixedStatus}"`);
          } else {
            // 매핑에 없으면 기본값 '현역'으로 설정
            updateData.status = '현역';
            needsUpdate = true;
            console.log(`⚠️  [${uid}] status: "${currentStatus}" → "현역" (기본값)`);
          }
        }
      }

      // gender 필드 확인 및 수정
      if (data.gender) {
        const currentGender = String(data.gender);

        if (currentGender.includes('?') || /[^\uAC00-\uD7A3\u0020-\u007E]/.test(currentGender)) {
          const fixedGender = GENDER_FIX_MAP[currentGender];

          if (fixedGender) {
            updateData.gender = fixedGender;
            needsUpdate = true;
            console.log(`✅ [${uid}] gender: "${currentGender}" → "${fixedGender}"`);
          }
        }
      }

      if (needsUpdate) {
        updateData.updatedAt = admin.firestore.FieldValue.serverTimestamp();
        batch.update(doc.ref, updateData);
        updates.push({ uid, ...updateData });
        fixedCount++;
      } else {
        skippedCount++;
      }
    }

    if (fixedCount > 0) {
      console.log(`\n📝 ${fixedCount}명의 사용자 데이터 업데이트 중...`);
      await batch.commit();
      console.log('✅ 배치 업데이트 완료!');

      console.log('\n📊 업데이트 상세:');
      updates.forEach(({ uid, status, gender }) => {
        const changes = [];
        if (status) changes.push(`status: ${status}`);
        if (gender) changes.push(`gender: ${gender}`);
        console.log(`  - ${uid}: ${changes.join(', ')}`);
      });
    } else {
      console.log('\n✨ 수정이 필요한 사용자가 없습니다.');
    }

    console.log(`\n🎉 처리 완료!`);
    console.log(`   수정: ${fixedCount}명`);
    console.log(`   건너뜀: ${skippedCount}명`);
    console.log(`   총 처리: ${usersSnapshot.size}명`);

    process.exit(0);
  } catch (error) {
    console.error('❌ 처리 중 오류:', error);
    process.exit(1);
  }
})();
