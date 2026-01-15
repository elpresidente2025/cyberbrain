const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });
const { db } = require('./utils/firebaseAdmin');

async function main() {
  const snapshot = await db.collection('electoral_districts')
    .where('electionId', '==', '20140604')
    .get();

  const incheonGus = new Set();
  snapshot.forEach(doc => {
    const data = doc.data();
    if (data.regionMetro && data.regionMetro.includes('인천')) {
      incheonGus.add(data.regionLocal || '(없음)');
    }
  });

  console.log(`\n📋 인천광역시 구/군 목록:\n`);
  Array.from(incheonGus).sort().forEach(gu => {
    console.log(`   - ${gu}`);
  });
}

main().then(() => process.exit(0)).catch(e => { console.error(e); process.exit(1); });
