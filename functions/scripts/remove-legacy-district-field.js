/**
 * functions/scripts/remove-legacy-district-field.js
 *
 * 레거시 district 필드를 모든 사용자에서 제거하는 스크립트
 *
 * 실행 방법:
 * node functions/scripts/remove-legacy-district-field.js [--dry-run]
 */

'use strict';

const { admin, db } = require('../utils/firebaseAdmin');

const args = process.argv.slice(2);
const isDryRun = args.includes('--dry-run');

console.log('====================================');
console.log('레거시 district 필드 제거 스크립트');
console.log('====================================');
console.log(`모드: ${isDryRun ? 'DRY RUN (실제 변경 없음)' : 'PRODUCTION (실제 변경 적용)'}`);
console.log('====================================\n');

const stats = {
  totalUsers: 0,
  hasDistrictField: 0,
  removed: 0,
  errors: 0,
};

async function removeLegacyDistrictField() {
  try {
    console.log('사용자 데이터 조회 중...\n');

    const usersSnapshot = await db.collection('users').get();
    stats.totalUsers = usersSnapshot.size;

    console.log(`총 ${stats.totalUsers}명의 사용자 발견\n`);

    const batch = db.batch();
    let operationCount = 0;

    for (const userDoc of usersSnapshot.docs) {
      const userId = userDoc.id;
      const userData = userDoc.data();

      if (userData.district !== undefined) {
        stats.hasDistrictField++;

        console.log(`[${userId}] district 필드 발견: "${userData.district}"`);
        console.log(`  - regionMetro: ${userData.regionMetro || '없음'}`);
        console.log(`  - regionLocal: ${userData.regionLocal || '없음'}`);
        console.log(`  - electoralDistrict: ${userData.electoralDistrict || '없음'}`);

        if (!isDryRun) {
          batch.update(userDoc.ref, {
            district: admin.firestore.FieldValue.delete(),
            updatedAt: admin.firestore.FieldValue.serverTimestamp()
          });
          operationCount++;
          stats.removed++;
        }

        console.log('');
      }
    }

    if (operationCount > 0 && !isDryRun) {
      console.log(`배치 커밋 중 (${operationCount}개 작업)...\n`);
      await batch.commit();
    }

    console.log('\n====================================');
    console.log('완료!');
    console.log('====================================');
    console.log(`총 사용자: ${stats.totalUsers}`);
    console.log(`district 필드 보유: ${stats.hasDistrictField}`);
    console.log(`제거됨: ${stats.removed}`);
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

removeLegacyDistrictField()
  .then(() => {
    console.log('스크립트 종료');
    process.exit(0);
  })
  .catch((error) => {
    console.error('스크립트 실행 실패:', error);
    process.exit(1);
  });
