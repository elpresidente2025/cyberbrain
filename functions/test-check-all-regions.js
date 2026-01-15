const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const { db } = require('./utils/firebaseAdmin');

async function main() {
  const snapshot = await db.collection('electoral_districts')
    .where('electionId', '==', '20220601')
    .where('position', '==', '기초의원')
    .get();

  const regions = {};
  snapshot.forEach(doc => {
    const data = doc.data();
    const metro = data.regionMetro || '(없음)';
    regions[metro] = (regions[metro] || 0) + 1;
  });

  console.log('\n📊 2022년 기초의원 선거구 - 광역시도별:\n');
  Object.entries(regions).sort((a, b) => b[1] - a[1]).forEach(([region, count]) => {
    console.log(`   ${region}: ${count}개`);
  });
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
