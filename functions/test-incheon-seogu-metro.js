const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const { db } = require('./utils/firebaseAdmin');

async function main() {
  const snapshot = await db.collection('electoral_districts')
    .where('electionId', '==', '20220601')
    .where('regionMetro', '==', '인천광역시')
    .where('position', '==', '광역의원')
    .get();

  console.log(`\n📊 2022년 인천 광역의원: ${snapshot.size}개\n`);

  const byGu = {};
  snapshot.forEach(doc => {
    const data = doc.data();
    const gu = data.regionLocal || '(없음)';
    if (!byGu[gu]) byGu[gu] = [];
    byGu[gu].push(data.electoralDistrict);
  });

  Object.keys(byGu).sort().forEach(gu => {
    console.log(`${gu}: ${byGu[gu].length}개`);
    byGu[gu].forEach(d => console.log(`   - ${d}`));
  });
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
