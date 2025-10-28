/**
 * functions/scripts/debug-user-district.js
 *
 * 사용자의 선거구 정보를 디버깅하는 스크립트
 *
 * 실행 방법:
 * node functions/scripts/debug-user-district.js <userId>
 */

'use strict';

const { admin, db } = require('../utils/firebaseAdmin');
const { districtKey } = require('../services/district');

async function debugUserDistrict(userId) {
  try {
    console.log('========================================');
    console.log(`사용자 ${userId}의 선거구 정보 디버깅`);
    console.log('========================================\n');

    // 1. users 컬렉션에서 사용자 정보 조회
    const userDoc = await db.collection('users').doc(userId).get();

    if (!userDoc.exists) {
      console.log('❌ 사용자를 찾을 수 없습니다.');
      return;
    }

    const userData = userDoc.data();
    console.log('📄 Users 컬렉션 데이터:');
    console.log('  - regionMetro:', userData.regionMetro);
    console.log('  - regionLocal:', userData.regionLocal);
    console.log('  - electoralDistrict:', userData.electoralDistrict);
    console.log('  - position:', userData.position);
    console.log('  - status:', userData.status);
    console.log('  - districtKey (저장된 값):', userData.districtKey);
    console.log('');

    // 2. districtKey 재계산
    let calculatedKey;
    try {
      calculatedKey = districtKey({
        position: userData.position,
        regionMetro: userData.regionMetro,
        regionLocal: userData.regionLocal,
        electoralDistrict: userData.electoralDistrict
      });
      console.log('🔑 계산된 districtKey:', calculatedKey);
    } catch (error) {
      console.log('❌ districtKey 계산 실패:', error.message);
    }
    console.log('');

    // 3. 키 일치 여부 확인
    if (calculatedKey && calculatedKey !== userData.districtKey) {
      console.log('⚠️  저장된 districtKey와 계산된 districtKey가 다릅니다!');
      console.log('  저장된 값:', userData.districtKey);
      console.log('  계산된 값:', calculatedKey);
    } else if (calculatedKey === userData.districtKey) {
      console.log('✅ districtKey가 일치합니다.');
    }
    console.log('');

    // 4. district_claims 컬렉션 조회
    if (calculatedKey) {
      const claimDoc = await db.collection('district_claims').doc(calculatedKey).get();

      if (claimDoc.exists) {
        const claimData = claimDoc.data();
        console.log('📋 District Claims 컬렉션 데이터:');
        console.log('  - userId:', claimData.userId);
        console.log('  - claimedAt:', claimData.claimedAt?.toDate?.());
        console.log('  - lastUpdated:', claimData.lastUpdated?.toDate?.());

        if (claimData.userId !== userId) {
          console.log('');
          console.log('⚠️  이 선거구는 다른 사용자가 점유하고 있습니다!');
          console.log('  점유자:', claimData.userId);
        }
      } else {
        console.log('📋 District Claims: 점유 기록 없음');
      }
    }
    console.log('');

    // 5. 잘못된 districtKey로 점유된 경우 확인
    if (userData.districtKey && userData.districtKey !== calculatedKey) {
      const wrongClaimDoc = await db.collection('district_claims').doc(userData.districtKey).get();

      if (wrongClaimDoc.exists) {
        const wrongClaimData = wrongClaimDoc.data();
        console.log('🔍 잘못된 districtKey로 점유된 데이터:');
        console.log('  - Key:', userData.districtKey);
        console.log('  - userId:', wrongClaimData.userId);
        console.log('  - claimedAt:', wrongClaimData.claimedAt?.toDate?.());
      }
      console.log('');
    }

    // 6. 해당 사용자의 모든 district claims 조회
    const allClaims = await db.collection('district_claims').where('userId', '==', userId).get();

    if (!allClaims.empty) {
      console.log('🔍 이 사용자가 점유한 모든 선거구:');
      allClaims.forEach(doc => {
        console.log(`  - ${doc.id}`);
      });

      if (allClaims.size > 1) {
        console.log('');
        console.log('⚠️  사용자가 여러 선거구를 점유하고 있습니다! (비정상)');
      }
    } else {
      console.log('🔍 이 사용자가 점유한 선거구 없음');
    }
    console.log('');

    console.log('========================================');
    console.log('디버깅 완료');
    console.log('========================================');

  } catch (error) {
    console.error('❌ 오류 발생:', error);
    throw error;
  }
}

// 스크립트 실행
const userId = process.argv[2];

if (!userId) {
  console.error('사용법: node debug-user-district.js <userId>');
  process.exit(1);
}

debugUserDistrict(userId)
  .then(() => {
    console.log('\n스크립트 종료');
    process.exit(0);
  })
  .catch((error) => {
    console.error('\n스크립트 실행 실패:', error);
    process.exit(1);
  });
