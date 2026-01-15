const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const { db } = require('./utils/firebaseAdmin');

async function main() {
  const snapshot = await db.collection('electoral_districts')
    .where('regionMetro', '==', '인천광역시')
    .where('regionLocal', '==', '서구')
    .where('position', '==', '기초의원')
    .get();

  console.log(`\n📊 인천 서구 기초의원 선거구 (총 ${snapshot.size}개):\n`);
  
  snapshot.forEach(doc => {
    const data = doc.data();
    console.log(`   - ${data.electoralDistrict} (정수: ${data.selectedCount}명)`);
  });
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
