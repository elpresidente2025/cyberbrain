#!/usr/bin/env node
'use strict';

/**
 * 선거구 동기화 테스트 스크립트
 * 사용법: node test-district-sync.js
 */

const path = require('path');
require('dotenv').config({ path: path.join(__dirname, 'functions', '.env') });

// Firebase Admin SDK 초기화 (테스트 환경)
const admin = require('firebase-admin');
const serviceAccount = require('./serviceAccountKey.json');

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount)
});

const {
  syncUpcomingElections,
  fetchElectionList
} = require('./functions/services/district-sync');

async function main() {
  console.log('🧪 [TEST] 선거구 동기화 테스트 시작\n');

  try {
    // 1. 선거 목록 조회
    console.log('1️⃣ 선거 목록 조회...\n');
    const elections = await fetchElectionList();
    console.log(`   총 ${elections.length}개 선거 발견\n`);

    // 2020년 이후 선거만 필터링
    const upcomingElections = elections.filter(e => parseInt(e.sgId) >= 20200000);

    if (upcomingElections.length === 0) {
      console.log('ℹ️ 2020년 이후 선거 데이터 없음 (2026년 데이터 미등록)');
      console.log('   → 가장 최근 선거:', elections[elections.length - 1]);
    } else {
      console.log(`📋 미래 선거 목록 (2020년 이후):`);
      upcomingElections.forEach(e => {
        console.log(`   - ${e.sgName} (${e.sgId})`);
      });
    }

    console.log('\n2️⃣ 동기화 테스트 (실제 Firestore 저장)...\n');

    const result = await syncUpcomingElections();

    console.log('\n✅ [TEST] 동기화 테스트 완료!');
    console.log('결과:', JSON.stringify(result, null, 2));

  } catch (error) {
    console.error('\n❌ [TEST] 테스트 실패:', error);
    process.exit(1);
  }

  process.exit(0);
}

main();
