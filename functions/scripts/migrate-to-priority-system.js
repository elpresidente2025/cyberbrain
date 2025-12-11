/**
 * 우선권 기반 시스템으로 마이그레이션 스크립트
 *
 * 실행 방법:
 * node functions/scripts/migrate-to-priority-system.js [--dry-run]
 *
 * --dry-run: 실제 변경 없이 시뮬레이션만 수행
 */

'use strict';

const { admin, db } = require('../utils/firebaseAdmin');

const DRY_RUN = process.argv.includes('--dry-run');

async function migrateDistrictClaims() {
  console.log('\n🔄 district_claims 컬렉션 마이그레이션 시작...\n');

  const snapshot = await db.collection('district_claims').get();

  console.log(`📊 총 ${snapshot.size}개의 선거구 문서 발견`);

  let migratedCount = 0;
  let skippedCount = 0;
  let errorCount = 0;

  for (const doc of snapshot.docs) {
    const districtKey = doc.id;
    const oldData = doc.data();

    try {
      // 이미 새 구조인지 확인
      if (oldData.members && Array.isArray(oldData.members)) {
        console.log(`⏭️  건너뜀: ${districtKey} (이미 새 구조)`);
        skippedCount++;
        continue;
      }

      // 구 구조 확인
      if (!oldData.userId) {
        console.warn(`⚠️  건너뜀: ${districtKey} (userId 없음)`);
        skippedCount++;
        continue;
      }

      // 새 구조로 변환
      const newData = {
        members: [{
          userId: oldData.userId,
          registeredAt: oldData.claimedAt || admin.firestore.Timestamp.now(),
          paidAt: oldData.claimedAt || admin.firestore.Timestamp.now(),
          subscriptionStatus: 'active',  // 기존 사용자는 active로 간주
          priority: 1,
          isPrimary: true
        }],
        primaryUserId: oldData.userId,
        totalMembers: 1,
        paidMembers: 1,
        waitlistCount: 0,
        createdAt: oldData.claimedAt || admin.firestore.Timestamp.now(),
        lastUpdated: admin.firestore.Timestamp.now()
      };

      if (DRY_RUN) {
        console.log(`✅ [DRY-RUN] 변환 완료: ${districtKey}`);
        console.log('   기존:', { userId: oldData.userId });
        console.log('   새로:', { primaryUserId: newData.primaryUserId, totalMembers: 1 });
      } else {
        await doc.ref.set(newData);
        console.log(`✅ 마이그레이션 완료: ${districtKey} (사용자: ${oldData.userId})`);
      }

      migratedCount++;

    } catch (error) {
      console.error(`❌ 오류 발생: ${districtKey}`, error.message);
      errorCount++;
    }
  }

  console.log(`\n📊 district_claims 마이그레이션 결과:`);
  console.log(`   - 마이그레이션: ${migratedCount}개`);
  console.log(`   - 건너뜀: ${skippedCount}개`);
  console.log(`   - 오류: ${errorCount}개`);
}

async function migrateUserFields() {
  console.log('\n🔄 users 컬렉션 필드 추가 시작...\n');

  const snapshot = await db.collection('users').get();

  console.log(`📊 총 ${snapshot.size}명의 사용자 발견`);

  let migratedCount = 0;
  let skippedCount = 0;
  let errorCount = 0;

  const batch = db.batch();
  let batchCount = 0;

  for (const doc of snapshot.docs) {
    const uid = doc.id;
    const userData = doc.data();

    try {
      // 이미 새 필드가 있는지 확인
      if (userData.districtPriority !== undefined || userData.isPrimaryInDistrict !== undefined) {
        console.log(`⏭️  건너뜀: ${uid} (이미 새 필드 존재)`);
        skippedCount++;
        continue;
      }

      // 선거구가 없으면 건너뜀
      if (!userData.districtKey) {
        console.log(`⏭️  건너뜀: ${uid} (선거구 없음)`);
        skippedCount++;
        continue;
      }

      // 새 필드 추가
      const updateData = {
        districtPriority: 1,  // 기존 사용자는 1순위
        isPrimaryInDistrict: true,  // 기존 사용자는 우선권자
        districtStatus: 'primary',
        paidAt: userData.createdAt || admin.firestore.Timestamp.now()
      };

      // subscriptionStatus가 없으면 추가
      if (!userData.subscriptionStatus) {
        updateData.subscriptionStatus = 'active';
      }

      if (DRY_RUN) {
        console.log(`✅ [DRY-RUN] 업데이트: ${uid}`);
        console.log('   추가 필드:', Object.keys(updateData));
      } else {
        batch.update(doc.ref, updateData);
        batchCount++;
        migratedCount++;

        // Firestore batch 제한 (500개)
        if (batchCount >= 500) {
          await batch.commit();
          console.log(`   💾 배치 커밋: ${batchCount}개`);
          batchCount = 0;
        }

        console.log(`✅ 업데이트 예정: ${uid} (선거구: ${userData.districtKey})`);
      }

    } catch (error) {
      console.error(`❌ 오류 발생: ${uid}`, error.message);
      errorCount++;
    }
  }

  // 남은 배치 커밋
  if (!DRY_RUN && batchCount > 0) {
    await batch.commit();
    console.log(`   💾 최종 배치 커밋: ${batchCount}개`);
  }

  console.log(`\n📊 users 필드 추가 결과:`);
  console.log(`   - 업데이트: ${migratedCount}개`);
  console.log(`   - 건너뜀: ${skippedCount}개`);
  console.log(`   - 오류: ${errorCount}개`);
}

async function verifyMigration() {
  console.log('\n🔍 마이그레이션 검증 중...\n');

  // 1. district_claims 검증
  const districtSnapshot = await db.collection('district_claims').get();
  let newStructureCount = 0;
  let oldStructureCount = 0;

  districtSnapshot.forEach(doc => {
    const data = doc.data();
    if (data.members && Array.isArray(data.members)) {
      newStructureCount++;
    } else {
      oldStructureCount++;
    }
  });

  console.log(`📊 district_claims 검증:`);
  console.log(`   - 새 구조: ${newStructureCount}개`);
  console.log(`   - 구 구조: ${oldStructureCount}개`);

  // 2. users 검증
  const usersSnapshot = await db.collection('users')
    .where('districtKey', '!=', null)
    .get();

  let hasNewFieldsCount = 0;
  let missingFieldsCount = 0;

  usersSnapshot.forEach(doc => {
    const data = doc.data();
    if (data.isPrimaryInDistrict !== undefined) {
      hasNewFieldsCount++;
    } else {
      missingFieldsCount++;
    }
  });

  console.log(`\n📊 users 필드 검증:`);
  console.log(`   - 새 필드 있음: ${hasNewFieldsCount}명`);
  console.log(`   - 새 필드 없음: ${missingFieldsCount}명`);

  if (oldStructureCount === 0 && missingFieldsCount === 0) {
    console.log(`\n✅ 모든 데이터가 새 구조로 마이그레이션되었습니다!`);
  } else {
    console.log(`\n⚠️  마이그레이션이 완료되지 않은 데이터가 있습니다.`);
  }
}

async function main() {
  console.log('========================================');
  console.log('🚀 우선권 시스템 마이그레이션');
  console.log('========================================');

  if (DRY_RUN) {
    console.log('\n⚠️  DRY-RUN 모드: 실제 변경하지 않습니다.\n');
  } else {
    console.log('\n⚠️  실제 데이터를 변경합니다! 계속하시겠습니까?');
    console.log('   Ctrl+C로 취소할 수 있습니다. 5초 후 시작...\n');
    await new Promise(resolve => setTimeout(resolve, 5000));
  }

  try {
    // 1. district_claims 마이그레이션
    await migrateDistrictClaims();

    // 2. users 필드 추가
    await migrateUserFields();

    // 3. 검증
    await verifyMigration();

    console.log('\n========================================');
    console.log('✅ 마이그레이션 완료!');
    console.log('========================================\n');

    if (DRY_RUN) {
      console.log('💡 실제로 적용하려면 --dry-run 옵션 없이 실행하세요:');
      console.log('   node functions/scripts/migrate-to-priority-system.js\n');
    }

  } catch (error) {
    console.error('\n❌ 마이그레이션 실패:', error);
    process.exit(1);
  }

  process.exit(0);
}

// 스크립트 실행
main();
