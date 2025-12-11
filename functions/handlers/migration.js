/**
 * functions/handlers/migration.js
 * 마이그레이션 HTTP 핸들러
 */

'use strict';

const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');
const { auth } = require('../common/auth');
const { HttpsError } = require('firebase-functions/v2/https');
const { admin, db } = require('../utils/firebaseAdmin');

/**
 * 우선권 시스템으로 마이그레이션 (관리자 전용)
 */
exports.migrateToPrioritySystem = wrap(async (req) => {
  const { uid } = await auth(req);
  const { dryRun = true } = req.data || {};

  // 관리자 확인
  const userDoc = await db.collection('users').doc(uid).get();
  if (!userDoc.exists || !userDoc.data().isAdmin) {
    throw new HttpsError('permission-denied', '관리자만 실행할 수 있습니다.');
  }

  console.log('🚀 우선권 시스템 마이그레이션 시작:', { dryRun, requestedBy: uid });

  const results = {
    districtClaims: { migrated: 0, skipped: 0, errors: 0 },
    users: { migrated: 0, skipped: 0, errors: 0 }
  };

  // 1. district_claims 마이그레이션
  try {
    const districtSnapshot = await db.collection('district_claims').get();
    console.log(`📊 총 ${districtSnapshot.size}개의 선거구 문서 발견`);

    for (const doc of districtSnapshot.docs) {
      const districtKey = doc.id;
      const oldData = doc.data();

      try {
        // 이미 새 구조인지 확인
        if (oldData.members && Array.isArray(oldData.members)) {
          console.log(`⏭️  건너뜀: ${districtKey} (이미 새 구조)`);
          results.districtClaims.skipped++;
          continue;
        }

        // 구 구조 확인
        if (!oldData.userId) {
          console.warn(`⚠️  건너뜀: ${districtKey} (userId 없음)`);
          results.districtClaims.skipped++;
          continue;
        }

        // 새 구조로 변환
        const newData = {
          members: [{
            userId: oldData.userId,
            registeredAt: oldData.claimedAt || admin.firestore.Timestamp.now(),
            paidAt: oldData.claimedAt || admin.firestore.Timestamp.now(),
            subscriptionStatus: 'active',
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

        if (dryRun) {
          console.log(`✅ [DRY-RUN] 변환 완료: ${districtKey}`);
        } else {
          await doc.ref.set(newData);
          console.log(`✅ 마이그레이션 완료: ${districtKey}`);
        }

        results.districtClaims.migrated++;

      } catch (error) {
        console.error(`❌ 오류 발생: ${districtKey}`, error.message);
        results.districtClaims.errors++;
      }
    }
  } catch (error) {
    console.error('❌ district_claims 마이그레이션 실패:', error);
    throw new HttpsError('internal', 'district_claims 마이그레이션 실패');
  }

  // 2. users 필드 추가
  try {
    const usersSnapshot = await db.collection('users').get();
    console.log(`📊 총 ${usersSnapshot.size}명의 사용자 발견`);

    const batch = db.batch();
    let batchCount = 0;

    for (const doc of usersSnapshot.docs) {
      const uid = doc.id;
      const userData = doc.data();

      try {
        // 이미 새 필드가 있는지 확인
        if (userData.districtPriority !== undefined || userData.isPrimaryInDistrict !== undefined) {
          console.log(`⏭️  건너뜀: ${uid} (이미 새 필드 존재)`);
          results.users.skipped++;
          continue;
        }

        // 선거구가 없으면 건너뜀
        if (!userData.districtKey) {
          console.log(`⏭️  건너뜀: ${uid} (선거구 없음)`);
          results.users.skipped++;
          continue;
        }

        // 새 필드 추가
        const updateData = {
          districtPriority: 1,
          isPrimaryInDistrict: true,
          districtStatus: 'primary',
          paidAt: userData.createdAt || admin.firestore.Timestamp.now()
        };

        if (!userData.subscriptionStatus) {
          updateData.subscriptionStatus = 'active';
        }

        if (dryRun) {
          console.log(`✅ [DRY-RUN] 업데이트: ${uid}`);
        } else {
          batch.update(doc.ref, updateData);
          batchCount++;

          // Firestore batch 제한 (500개)
          if (batchCount >= 500) {
            await batch.commit();
            console.log(`💾 배치 커밋: ${batchCount}개`);
            batchCount = 0;
          }

          console.log(`✅ 업데이트 예정: ${uid}`);
        }

        results.users.migrated++;

      } catch (error) {
        console.error(`❌ 오류 발생: ${uid}`, error.message);
        results.users.errors++;
      }
    }

    // 남은 배치 커밋
    if (!dryRun && batchCount > 0) {
      await batch.commit();
      console.log(`💾 최종 배치 커밋: ${batchCount}개`);
    }

  } catch (error) {
    console.error('❌ users 필드 추가 실패:', error);
    throw new HttpsError('internal', 'users 필드 추가 실패');
  }

  console.log('✅ 마이그레이션 완료:', results);

  return ok({
    message: dryRun ? '시뮬레이션 완료' : '마이그레이션 완료',
    dryRun,
    results
  });
});
