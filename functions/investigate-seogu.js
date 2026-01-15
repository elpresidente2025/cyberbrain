const axios = require('axios');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '.env') });

const API_KEY = process.env.NEC_API_KEY;
const BASE_URL = 'http://apis.data.go.kr/9760000/CommonCodeService';

async function investigateAll() {
  console.log('🔍 인천 서구 완전 조사 시작\n');

  // 1. 구시군 목록에서 서구 확인
  console.log('1️⃣ 구시군 목록 API 확인...');
  const gusigunRes = await axios.get(`${BASE_URL}/getCommonGusigunCodeList`, {
    params: {
      serviceKey: API_KEY,
      sgId: '20220601',
      pageNo: 1,
      numOfRows: 300,
      resultType: 'json'
    }
  });

  const gusigun = gusigunRes.data.response.body.items.item;
  const incheonGus = gusigun.filter(x => x.sdName === '인천광역시');
  console.log(`   인천 구/군: ${incheonGus.length}개`);
  incheonGus.forEach(g => console.log(`   - ${g.wiwName} (wOrder: ${g.wOrder})`));

  const seogu = incheonGus.find(g => g.wiwName === '서구');
  if (seogu) {
    console.log(`\n   ✅ 서구 발견! wOrder: ${seogu.wOrder}\n`);
  } else {
    console.log(`\n   ❌ 서구 없음!\n`);
    return;
  }

  // 2. 광역의원 선거구에서 서구 검색
  console.log('2️⃣ 광역의원 선거구(sgTypecode=5) 전체 조회...');
  let allMetro = [];
  for (let page = 1; page <= 10; page++) {
    const res = await axios.get(`${BASE_URL}/getCommonSggCodeList`, {
      params: {
        serviceKey: API_KEY,
        sgId: '20220601',
        sgTypecode: '5',
        pageNo: page,
        numOfRows: 100,
        resultType: 'json'
      }
    });

    const data = res.data.response;
    if (data.header.resultCode !== 'INFO-00') break;

    const items = data.body.items.item;
    const arr = Array.isArray(items) ? items : [items];
    allMetro.push(...arr);

    if (arr.length < 100) break;
    await new Promise(r => setTimeout(r, 100));
  }

  const incheonMetro = allMetro.filter(x => x.sdName === '인천광역시');
  console.log(`   인천 광역의원 선거구: ${incheonMetro.length}개`);

  const seoguMetro = incheonGus.filter(x => x.wiwName && x.wiwName.includes('서구'));
  console.log(`   서구 관련: ${seoguMetro.length}개`);
  if (seoguMetro.length > 0) {
    seoguMetro.forEach(x => console.log(`   - ${x.sggName}`));
  }

  // 3. 기초의원 선거구에서 서구 검색
  console.log('\n3️⃣ 기초의원 선거구(sgTypecode=6) 전체 조회...');
  let allDistricts = [];
  for (let page = 1; page <= 11; page++) {
    const res = await axios.get(`${BASE_URL}/getCommonSggCodeList`, {
      params: {
        serviceKey: API_KEY,
        sgId: '20220601',
        sgTypecode: '6',
        pageNo: page,
        numOfRows: 100,
        resultType: 'json'
      }
    });

    const items = res.data?.response?.body?.items?.item || [];
    const itemsArray = Array.isArray(items) ? items : [items];
    allDistricts = allDistricts.concat(itemsArray);
    if (itemsArray.length < 100) break;
    await new Promise(r => setTimeout(r, 100));
  }

  const incheonDistricts = allDistricts.filter(x => x.sdName === '인천광역시');
  console.log(`   인천 기초의원 선거구: ${incheonDistricts.length}개`);

  const seoguDistricts = incheonDistricts.filter(d =>
    d.wiwName === '서구' || d.sggName.includes('서구')
  );

  if (seoguDistricts.length > 0) {
    console.log(`\n   ✅ 서구 선거구 발견: ${seoguDistricts.length}개`);
    seoguDistricts.forEach(d => console.log(`   - ${d.sggName}`));
  } else {
    console.log(`\n   ❌ 서구 선거구 없음!`);
    console.log(`   🔍 인천 전체 선거구 목록:`);
    const uniqueGus = [...new Set(incheonDistricts.map(x => x.wiwName))];
    uniqueGus.forEach(g => console.log(`      - ${g}`));
  }


}

investigateAll().catch(console.error);
