const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const { db } = require('./utils/firebaseAdmin');

async function main() {
  const snapshot = await db.collection('electoral_districts')
    .where('regionMetro', '==', '인천광역시')
    .limit(5)
    .get();

  console.log('\n📊 인천광역시 선거구 샘플:\n');
  snapshot.forEach(doc => {
    const data = doc.data();
    console.log(JSON.stringify({
      electionId: data.electionId,
      position: data.position,
      district: data.electoralDistrict,
      metro: data.regionMetro,
      local: data.regionLocal
    }, null, 2));
  });
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
