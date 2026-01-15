const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const { db } = require('./utils/firebaseAdmin');

async function main() {
  const snapshot = await db.collection('electoral_districts')
    .where('electionId', '==', '20220601')
    .where('regionMetro', '==', '인천광역시')
    .get();

  console.log(`\n📊 2022년 인천광역시: ${snapshot.size}개\n`);

  if (snapshot.size === 0) {
    console.log('❌ 2022년 인천 데이터가 없습니다!');
  } else {
    snapshot.forEach(doc => {
      const data = doc.data();
      console.log(`${data.position} - ${data.electoralDistrict} (${data.regionLocal})`);
    });
  }
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
