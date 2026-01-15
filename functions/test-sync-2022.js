const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const { syncSpecificElection } = require('./services/district-sync');

async function main() {
  console.log('🧪 [TEST] 2022년 제8회 지방선거 (현행) 데이터 동기화\n');
  const result = await syncSpecificElection('20220601');
  console.log('\n✅ 결과:', JSON.stringify(result, null, 2));
  process.exit(0);
}

main().catch(e => { console.error(e); process.exit(1); });
