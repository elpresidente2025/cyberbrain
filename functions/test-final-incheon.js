const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const { db } = require('./utils/firebaseAdmin');

async function main() {
  const snapshot = await db.collection('electoral_districts')
    .where('electionId', '==', '20220601')
    .where('regionMetro', '==', '인천광역시')
    .get();

  const byGu = {};
  snapshot.forEach(doc => {
    const data = doc.data();
    const gu = data.regionLocal;
    if (!byGu[gu]) byGu[gu] = { 국회의원: 0, 광역의원: 0, 기초의원: 0 };
    byGu[gu][data.position]++;
  });

  console.log('\n📊 2022년 인천광역시 선거구 현황:\n');
  Object.keys(byGu).sort().forEach(gu => {
    const counts = byGu[gu];
    const total = counts.국회의원 + counts.광역의원 + counts.기초의원;
    console.log(`${gu}: 총 ${total}개`);
    console.log(`  국회의원: ${counts.국회의원}개, 광역의원: ${counts.광역의원}개, 기초의원: ${counts.기초의원}개`);
  });

  const hasSeogu = Object.keys(byGu).includes('서구');
  console.log(`\n❓ 서구 존재 여부: ${hasSeogu ? 'YES ✅' : 'NO ❌'}`);

  if (!hasSeogu) {
    console.log('\n🔍 결론: 2022년 제8회 지방선거 API 데이터에 인천 서구가 실제로 없습니다.');
  }
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
