/**
 * 기존 Bio 문서에 Style Fingerprint 추가 마이그레이션 스크립트
 *
 * 사용법:
 *   node functions/scripts/migrate-stylometry.js [--batch-size=50] [--min-confidence=0.7] [--dry-run]
 *
 * 옵션:
 *   --batch-size: 배치당 처리할 문서 수 (기본: 50)
 *   --min-confidence: 재분석 기준 신뢰도 (기본: 0.7)
 *   --dry-run: 실제 저장 없이 시뮬레이션
 */

'use strict';

// 환경 변수 로드 (GEMINI_API_KEY 등)
require('dotenv').config({ path: require('path').join(__dirname, '..', '.env') });

const admin = require('firebase-admin');
const path = require('path');

// Firebase 초기화
const serviceAccountPath = path.join(__dirname, '..', 'serviceAccount.json');
const serviceAccount = require(serviceAccountPath);

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount)
});

const db = admin.firestore();

// Stylometry 모듈 로드
const { extractStyleFingerprint, buildStyleGuidePrompt } = require('../services/stylometry');

// 명령줄 인자 파싱
const args = process.argv.slice(2);
const options = {
  batchSize: 50,
  minConfidence: 0.7,
  dryRun: false
};

args.forEach(arg => {
  if (arg.startsWith('--batch-size=')) {
    options.batchSize = parseInt(arg.split('=')[1], 10);
  } else if (arg.startsWith('--min-confidence=')) {
    options.minConfidence = parseFloat(arg.split('=')[1]);
  } else if (arg === '--dry-run') {
    options.dryRun = true;
  }
});

console.log('🚀 Style Fingerprint 마이그레이션 시작');
console.log('옵션:', options);

async function migrateStyleFingerprints() {
  const stats = {
    total: 0,
    skipped: 0,
    processed: 0,
    success: 0,
    failed: 0,
    noContent: 0
  };

  try {
    // 모든 Bio 문서 조회
    const biosSnapshot = await db.collection('bios').get();
    stats.total = biosSnapshot.size;

    console.log(`\n📊 전체 Bio 문서: ${stats.total}개\n`);

    let batch = [];

    for (const doc of biosSnapshot.docs) {
      const uid = doc.id;
      const data = doc.data();

      // 이미 신뢰도 높은 styleFingerprint가 있으면 스킵
      const existingConfidence = data.styleFingerprint?.analysisMetadata?.confidence || 0;
      if (existingConfidence >= options.minConfidence) {
        console.log(`⏭️  [${uid}] 스킵 (기존 신뢰도: ${existingConfidence})`);
        stats.skipped++;
        continue;
      }

      // entries에서 콘텐츠 추출
      const entries = data.entries || [];
      let consolidatedContent = '';

      entries.forEach(entry => {
        if (entry.content) {
          consolidatedContent += `\n[${entry.type?.toUpperCase() || 'CONTENT'}] ${entry.title || ''}: ${entry.content}\n`;
        }
      });

      // 레거시 content 필드 체크
      if (!consolidatedContent && data.content) {
        consolidatedContent = data.content;
      }

      if (!consolidatedContent || consolidatedContent.length < 100) {
        console.log(`⚠️  [${uid}] 콘텐츠 부족 (${consolidatedContent.length}자)`);
        stats.noContent++;
        continue;
      }

      batch.push({ uid, consolidatedContent, data });

      // 배치 처리
      if (batch.length >= options.batchSize) {
        await processBatch(batch, stats, options.dryRun);
        batch = [];

        // 속도 제한 (Gemini API 쿼터)
        console.log('⏳ 30초 대기 (API 쿼터)...');
        await sleep(30000);
      }
    }

    // 남은 배치 처리
    if (batch.length > 0) {
      await processBatch(batch, stats, options.dryRun);
    }

    // 결과 출력
    console.log('\n' + '='.repeat(50));
    console.log('📊 마이그레이션 결과');
    console.log('='.repeat(50));
    console.log(`전체: ${stats.total}`);
    console.log(`스킵 (기존 OK): ${stats.skipped}`);
    console.log(`콘텐츠 부족: ${stats.noContent}`);
    console.log(`처리됨: ${stats.processed}`);
    console.log(`성공: ${stats.success}`);
    console.log(`실패: ${stats.failed}`);
    console.log('='.repeat(50));

  } catch (error) {
    console.error('❌ 마이그레이션 오류:', error);
    process.exit(1);
  }
}

async function processBatch(batch, stats, dryRun) {
  console.log(`\n📦 배치 처리 시작 (${batch.length}개)`);

  for (const item of batch) {
    const { uid, consolidatedContent, data } = item;
    stats.processed++;

    try {
      console.log(`🔍 [${uid}] 분석 중... (${consolidatedContent.length}자)`);

      const styleFingerprint = await extractStyleFingerprint(consolidatedContent, {
        userName: data.userName || '',
        region: data.region || ''
      });

      if (!styleFingerprint) {
        console.log(`⚠️  [${uid}] 분석 결과 없음`);
        stats.failed++;
        continue;
      }

      const confidence = styleFingerprint.analysisMetadata?.confidence || 0;
      console.log(`✅ [${uid}] 분석 완료 (신뢰도: ${confidence})`);
      const styleGuide = buildStyleGuidePrompt(styleFingerprint, {
        compact: false,
        sourceText: consolidatedContent
      });

      if (!dryRun) {
        await db.collection('bios').doc(uid).update({
          styleFingerprint,
          styleGuide,
          styleFingerprintUpdatedAt: admin.firestore.FieldValue.serverTimestamp()
        });
        await db.collection('users').doc(uid).set({
          styleGuide,
          styleGuideUpdatedAt: admin.firestore.FieldValue.serverTimestamp()
        }, { merge: true });
        console.log(`💾 [${uid}] 저장 완료`);
      } else {
        console.log(`🏃 [${uid}] DRY RUN - 저장 생략`);
      }

      stats.success++;

      // 개별 요청 간 딜레이
      await sleep(2000);

    } catch (error) {
      console.error(`❌ [${uid}] 실패:`, error.message);
      stats.failed++;
    }
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// 실행
migrateStyleFingerprints()
  .then(() => {
    console.log('\n✅ 마이그레이션 완료');
    process.exit(0);
  })
  .catch(err => {
    console.error('\n❌ 마이그레이션 실패:', err);
    process.exit(1);
  });
