#!/usr/bin/env node
'use strict';

const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });

const {
  syncSpecificElection
} = require('./services/district-sync');

async function main() {
  console.log('🧪 [TEST] 2014년 지방선거 데이터 동기화 테스트\n');

  try {
    const result = await syncSpecificElection('20140604');

    console.log('\n✅ [TEST] 동기화 완료!');
    console.log('결과:', JSON.stringify(result, null, 2));
  } catch (error) {
    console.error('\n❌ [TEST] 실패:', error);
    process.exit(1);
  }

  process.exit(0);
}

main();
