/**
 * 사용자 데이터 복구 스크립트
 * - isActive 필드가 boolean이 아닌 경우 수정
 * - 기본 프로필 필드가 누락된 사용자 확인
 *
 * 사용법: node scripts/fix-user-data.js [--dry-run]
 */

const admin = require('firebase-admin');
const path = require('path');

// Firebase Admin 초기화
const serviceAccountPath = path.join(__dirname, '..', 'serviceAccount.json');
try {
  const serviceAccount = require(serviceAccountPath);
  admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
  });
} catch (e) {
  console.error('서비스 계정 키 파일을 찾을 수 없습니다:', serviceAccountPath);
  process.exit(1);
}

const db = admin.firestore();

// 드라이런 모드 확인
const dryRun = process.argv.includes('--dry-run');

async function fixUserData() {
  console.log(`\n🔧 사용자 데이터 검사 및 복구 시작... ${dryRun ? '(DRY RUN)' : ''}\n`);

  const usersSnapshot = await db.collection('users').get();

  let issuesFound = 0;
  let issuesFixed = 0;

  for (const doc of usersSnapshot.docs) {
    const uid = doc.id;
    const data = doc.data();
    const issues = [];
    const fixes = {};

    // 1. isActive 필드가 boolean이 아닌 경우 확인
    if (data.isActive !== undefined && typeof data.isActive !== 'boolean') {
      issues.push({
        field: 'isActive',
        current: data.isActive,
        problem: `boolean이어야 하는데 ${typeof data.isActive} 타입`,
      });

      // Bio 컬렉션 확인하여 올바른 isActive 값 결정
      const bioDoc = await db.collection('bios').doc(uid).get();
      const hasValidBio = bioDoc.exists && (bioDoc.data()?.content?.length > 0 || bioDoc.data()?.entries?.length > 0);
      fixes.isActive = hasValidBio;
    }

    // 2. 필수 프로필 필드 누락 확인
    const requiredFields = ['position', 'regionMetro'];
    for (const field of requiredFields) {
      if (data[field] === undefined || data[field] === null) {
        issues.push({
          field,
          current: data[field],
          problem: '필수 필드 누락',
        });
      }
    }

    // 3. 빈 문자열인 지역 필드 확인 (경고만)
    const regionFields = ['regionMetro', 'regionLocal', 'electoralDistrict'];
    for (const field of regionFields) {
      if (data[field] === '') {
        issues.push({
          field,
          current: '""',
          problem: '빈 문자열 (저장되지 않음)',
          severity: 'warning',
        });
      }
    }

    // 문제가 발견된 경우 출력
    if (issues.length > 0) {
      issuesFound++;
      console.log(`\n${'='.repeat(60)}`);
      console.log(`⚠️ 문제 발견: ${data.name || '이름없음'} (${uid})`);
      console.log(`${'='.repeat(60)}`);

      for (const issue of issues) {
        const icon = issue.severity === 'warning' ? '⚡' : '❌';
        console.log(`  ${icon} ${issue.field}: ${issue.problem}`);
        console.log(`     현재 값: ${JSON.stringify(issue.current)}`);
      }

      // 수정 사항이 있는 경우
      if (Object.keys(fixes).length > 0) {
        console.log(`\n  📝 수정 예정:`);
        for (const [field, value] of Object.entries(fixes)) {
          console.log(`     ${field}: ${JSON.stringify(value)}`);
        }

        if (!dryRun) {
          try {
            await db.collection('users').doc(uid).update(fixes);
            console.log(`  ✅ 수정 완료!`);
            issuesFixed++;
          } catch (e) {
            console.log(`  ❌ 수정 실패: ${e.message}`);
          }
        }
      }
    }
  }

  console.log(`\n${'='.repeat(60)}`);
  console.log(`📊 결과 요약`);
  console.log(`${'='.repeat(60)}`);
  console.log(`  - 전체 사용자: ${usersSnapshot.size}명`);
  console.log(`  - 문제 발견: ${issuesFound}명`);
  console.log(`  - 수정 완료: ${issuesFixed}명`);

  if (dryRun && issuesFound > 0) {
    console.log(`\n💡 실제 수정을 원하면 --dry-run 플래그 없이 실행하세요.`);
  }

  console.log(`\n`);
}

fixUserData()
  .then(() => process.exit(0))
  .catch(err => {
    console.error('오류:', err);
    process.exit(1);
  });
