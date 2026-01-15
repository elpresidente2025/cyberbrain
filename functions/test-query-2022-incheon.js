const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const { db } = require('./utils/firebaseAdmin');

async function main() {
  const snapshot = await db.collection('electoral_districts')
    .where('electionId', '==', '20220601')
    .get();

  console.log(`\n📊 2022년 전체 선거구: ${snapshot.size}개\n`);
  
  const incheonData = [];
  snapshot.forEach(doc => {
    const data = doc.data();
    if (data.regionMetro && data.regionMetro.includes('인천')) {
      incheonData.push(data);
    }
  });

  console.log(`인천광역시 전체: ${incheonData.length}개\n`);

  // 구/군 목록
  const gus = [...new Set(incheonData.map(d => d.regionLocal))];
  console.log('인천 구/군 목록:');
  gus.sort().forEach(g => console.log(`   - ${g}`));

  // 서구 데이터
  const seoguData = incheonData.filter(d => d.regionLocal && d.regionLocal.includes('서구'));
  console.log(`\n인천 서구: ${seoguData.length}개\n`);

  seoguData.forEach(d => {
    console.log(`   - ${d.electoralDistrict} [${d.position}] (정수: ${d.selectedCount}명)`);
  });
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
