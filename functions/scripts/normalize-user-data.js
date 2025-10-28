/**
 * functions/scripts/normalize-user-data.js
 *
 * 사용자 데이터 정규화 스크립트
 *
 * 목적:
 * 1. 성별 필드를 '남성'/'여성'으로 통일
 * 2. ageDecade 기반으로 age 필드 자동 생성
 * 3. bio 필드가 users 컬렉션에 남아있는 경우 bios 컬렉션으로 마이그레이션
 *
 * 실행 방법:
 * node functions/scripts/normalize-user-data.js [--dry-run] [--batch-size=500]
 */

'use strict';

const { admin, db } = require('../utils/firebaseAdmin');

// 성별 정규화 함수
function normalizeGender(gender) {
  if (!gender) return null;
  const g = String(gender).trim().toUpperCase();
  if (g === 'M' || g === 'MALE' || g === '남' || g === '남자') return '남성';
  if (g === 'F' || g === 'FEMALE' || g === '여' || g === '여자') return '여성';
  return String(gender).trim(); // 이미 정규화된 경우
}

// ageDecade에서 age 생성
function generateAgeFromDecade(ageDecade) {
  if (!ageDecade) return null;
  const match = String(ageDecade).trim().match(/^(\d{2})\s*대$/);
  if (!match) return null;
  const start = parseInt(match[1], 10);
  if (isNaN(start)) return null;
  return `${start}-${start + 9}`;
}

// age에서 ageDecade 생성
function generateDecadeFromAge(age) {
  if (!age) return null;
  const match = String(age).trim().match(/^(\d{2})\s*-\s*\d{2}$/);
  if (!match) return null;
  return `${match[1]}대`;
}

// 명령줄 인자 파싱
const args = process.argv.slice(2);
const isDryRun = args.includes('--dry-run');
const batchSizeArg = args.find(arg => arg.startsWith('--batch-size='));
const batchSize = batchSizeArg ? parseInt(batchSizeArg.split('=')[1], 10) : 500;

console.log('====================================');
console.log('사용자 데이터 정규화 스크립트');
console.log('====================================');
console.log(`모드: ${isDryRun ? 'DRY RUN (실제 변경 없음)' : 'PRODUCTION (실제 변경 적용)'}`);
console.log(`배치 크기: ${batchSize}`);
console.log('====================================\n');

// 통계 변수
const stats = {
  totalUsers: 0,
  genderNormalized: 0,
  ageGenerated: 0,
  ageDecadeGenerated: 0,
  bioMigrated: 0,
  errors: 0,
};

async function normalizeUserData() {
  try {
    console.log('사용자 데이터 조회 중...\n');

    // 모든 사용자 조회
    const usersSnapshot = await db.collection('users').get();
    stats.totalUsers = usersSnapshot.size;

    console.log(`총 ${stats.totalUsers}명의 사용자 발견\n`);

    // 배치 처리
    let batch = db.batch();
    let operationCount = 0;

    for (const userDoc of usersSnapshot.docs) {
      const userId = userDoc.id;
      const userData = userDoc.data();
      const updates = {};
      let needsUpdate = false;

      // 1. 성별 정규화
      if (userData.gender) {
        const normalizedGender = normalizeGender(userData.gender);
        if (normalizedGender !== userData.gender) {
          console.log(`[${userId}] 성별 정규화: "${userData.gender}" → "${normalizedGender}"`);
          updates.gender = normalizedGender;
          needsUpdate = true;
          stats.genderNormalized++;
        }
      }

      // 2. ageDecade에서 age 생성
      if (userData.ageDecade && !userData.age) {
        const generatedAge = generateAgeFromDecade(userData.ageDecade);
        if (generatedAge) {
          console.log(`[${userId}] age 생성: ageDecade "${userData.ageDecade}" → age "${generatedAge}"`);
          updates.age = generatedAge;
          needsUpdate = true;
          stats.ageGenerated++;
        }
      }

      // 3. age에서 ageDecade 생성
      if (userData.age && !userData.ageDecade) {
        const generatedDecade = generateDecadeFromAge(userData.age);
        if (generatedDecade) {
          console.log(`[${userId}] ageDecade 생성: age "${userData.age}" → ageDecade "${generatedDecade}"`);
          updates.ageDecade = generatedDecade;
          needsUpdate = true;
          stats.ageDecadeGenerated++;
        }
      }

      // 4. bio 마이그레이션 (users.bio → bios.content)
      if (userData.bio && typeof userData.bio === 'string' && userData.bio.trim()) {
        console.log(`[${userId}] bio 마이그레이션 감지: ${userData.bio.length}자`);

        // bios 컬렉션 확인
        const bioDoc = await db.collection('bios').doc(userId).get();

        if (!bioDoc.exists) {
          // bios 컬렉션에 없으면 생성
          console.log(`[${userId}] bios 컬렉션으로 마이그레이션`);

          if (!isDryRun) {
            const bioRef = db.collection('bios').doc(userId);
            batch.set(bioRef, {
              userId: userId,
              content: userData.bio.trim(),
              version: 1,
              createdAt: admin.firestore.FieldValue.serverTimestamp(),
              updatedAt: admin.firestore.FieldValue.serverTimestamp(),
              metadataStatus: 'pending',
              usage: {
                generatedPostsCount: 0,
                avgQualityScore: 0,
                lastUsedAt: null
              }
            });
            operationCount++;
          }

          stats.bioMigrated++;
        }

        // users 컬렉션에서 bio 필드 제거
        updates.bio = admin.firestore.FieldValue.delete();
        needsUpdate = true;
      }

      // 업데이트 적용
      if (needsUpdate && !isDryRun) {
        if (Object.keys(updates).length > 0) {
          updates.updatedAt = admin.firestore.FieldValue.serverTimestamp();
          batch.update(userDoc.ref, updates);
          operationCount++;
        }

        // 배치 크기 초과 시 커밋
        if (operationCount >= batchSize) {
          console.log(`\n배치 커밋 중 (${operationCount}개 작업)...\n`);
          await batch.commit();
          batch = db.batch();
          operationCount = 0;
        }
      }
    }

    // 마지막 배치 커밋
    if (operationCount > 0 && !isDryRun) {
      console.log(`\n마지막 배치 커밋 중 (${operationCount}개 작업)...\n`);
      await batch.commit();
    }

    console.log('\n====================================');
    console.log('정규화 완료!');
    console.log('====================================');
    console.log(`총 사용자: ${stats.totalUsers}`);
    console.log(`성별 정규화: ${stats.genderNormalized}`);
    console.log(`age 생성: ${stats.ageGenerated}`);
    console.log(`ageDecade 생성: ${stats.ageDecadeGenerated}`);
    console.log(`bio 마이그레이션: ${stats.bioMigrated}`);
    console.log(`오류: ${stats.errors}`);
    console.log('====================================\n');

    if (isDryRun) {
      console.log('⚠️  DRY RUN 모드: 실제 변경사항이 적용되지 않았습니다.');
      console.log('실제 적용하려면 --dry-run 옵션을 제거하고 다시 실행하세요.\n');
    } else {
      console.log('✅ 모든 변경사항이 성공적으로 적용되었습니다.\n');
    }

  } catch (error) {
    console.error('❌ 오류 발생:', error);
    stats.errors++;
    throw error;
  }
}

// 스크립트 실행
normalizeUserData()
  .then(() => {
    console.log('스크립트 종료');
    process.exit(0);
  })
  .catch((error) => {
    console.error('스크립트 실행 실패:', error);
    process.exit(1);
  });
