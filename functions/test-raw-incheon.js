const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const { db } = require('./utils/firebaseAdmin');

async function main() {
  const snapshot = await db.collection('electoral_districts')
    .where('electionId', '==', '20220601')
    .get();

  console.log(`전체 선거구: ${snapshot.size}개\n`);

  // 인천 관련 모든 데이터 확인
  const incheonAll = [];
  snapshot.forEach(doc => {
    const data = doc.data();
    const id = doc.id;
    if (id.includes('인천') || (data.regionMetro && data.regionMetro.includes('인천')) ||
        (data.regionLocal && data.regionLocal.includes('서구'))) {
      incheonAll.push({ id, ...data });
    }
  });

  console.log(`인천 관련 데이터: ${incheonAll.length}개\n`);

  // 서구 포함 데이터만
  const seogu = incheonAll.filter(d =>
    d.id.includes('서구') ||
    (d.regionLocal && d.regionLocal.includes('서구')) ||
    (d.electoralDistrict && d.electoralDistrict.includes('서구'))
  );

  console.log(`서구 관련: ${seogu.length}개\n`);

  if (seogu.length > 0) {
    console.log('서구 데이터:');
    seogu.forEach(d => {
      console.log(`  [${d.position}] ${d.electoralDistrict} (${d.regionMetro} ${d.regionLocal})`);
    });
  } else {
    console.log('⚠️ 서구 데이터가 정말 없습니다.\n');
  }

  // 인천의 모든 구 목록
  const gus = [...new Set(incheonAll.map(d => d.regionLocal))].sort();
  console.log(`인천 구/군 목록: ${gus.length}개`);
  gus.forEach(g => console.log(`  - ${g}`));
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
