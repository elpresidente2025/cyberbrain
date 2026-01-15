#!/usr/bin/env node
'use strict';

/**
 * 선거구 동기화 테스트 스크립트
 * 사용법: cd functions && node test-district-sync.js
 */

const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });

// Firebase Admin SDK는 이미 utils/firebaseAdmin에서 초기화됨
const {
  syncUpcomingElections,
  fetchElectionList
} = require('./services/district-sync');

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
      const latest = elections[elections.length - 1];
      console.log(`   → 가장 최근 선거: ${latest.sgName} (${latest.sgId})\n`);
    } else {
      console.log(`📋 미래 선거 목록 (2020년 이후):`);
      upcomingElections.forEach(e => {
        console.log(`   - ${e.sgName} (${e.sgId})`);
      });
      console.log('');
    }

    console.log('2️⃣ 동기화 테스트 (실제 Firestore 저장)...\n');
    console.log('   ⚠️ 주의: 이 작업은 실제 Firestore에 데이터를 저장합니다.\n');

    const result = await syncUpcomingElections();

    console.log('\n✅ [TEST] 동기화 테스트 완료!');
    console.log('\n📊 결과:');
    console.log(`   - 성공 여부: ${result.success ? '✅' : '❌'}`);
    console.log(`   - 메시지: ${result.message}`);
    console.log(`   - 동기화된 선거 수: ${result.electionsSynced}개`);
    console.log(`   - 저장된 선거구 수: ${result.districtsSaved}개`);

    if (result.elections && result.elections.length > 0) {
      console.log('\n   동기화된 선거:');
      result.elections.forEach(e => {
        console.log(`   - ${e.name} (${e.id})`);
      });
    }

  } catch (error) {
    console.error('\n❌ [TEST] 테스트 실패:', error);
    process.exit(1);
  }

  process.exit(0);
}

main();
