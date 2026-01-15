const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const { db } = require('./utils/firebaseAdmin');

async function main() {
  const snapshot = await db.collection('electoral_districts')
    .where('electionId', '==', '20140604')
    .limit(50)
    .get();

  console.log(`\n📊 2014년 선거구 샘플 (총 ${snapshot.size}개 조회):\n`);
  
  let incheonCount = 0;
  snapshot.forEach(doc => {
    const data = doc.data();
    if (data.regionMetro && data.regionMetro.includes('인천')) {
      console.log(`   - ${data.electoralDistrict} (${data.regionMetro} ${data.regionLocal}) [${data.position}]`);
      incheonCount++;
    }
  });

  console.log(`\n인천 관련: ${incheonCount}개`);
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
