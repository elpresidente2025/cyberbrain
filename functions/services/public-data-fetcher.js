/**
 * functions/services/public-data-fetcher.js
 * 공공데이터 포털 및 국회 API 조회 서비스
 */

'use strict';

const axios = require('axios');
const NodeCache = require('node-cache');

// 캐시 설정 (30분 TTL - 공공데이터는 자주 바뀌지 않음)
const cache = new NodeCache({ stdTTL: 1800 });

/**
 * 국회 의안정보 조회
 * @param {string} billNumber - 의안 번호
 * @returns {Promise<Object|null>} 의안 정보
 */
async function fetchAssemblyBill(billNumber) {
  if (!billNumber) {
    return null;
  }

  const cacheKey = `bill:${billNumber}`;

  if (cache.has(cacheKey)) {
    console.log('✅ 캐시에서 의안정보 반환:', billNumber);
    return cache.get(cacheKey);
  }

  try {
    // 국회 의안정보시스템 OPEN API
    // https://open.assembly.go.kr
    const url = `https://open.assembly.go.kr/portal/openapi/nwvrqwxyaytdsfvhu`;

    console.log('🏛️ 국회 의안정보 조회:', billNumber);

    const { data } = await axios.get(url, {
      params: {
        BILL_NO: billNumber,
        Type: 'json'
      },
      timeout: 10000
    });

    if (data && data.nwvrqwxyaytdsfvhu) {
      const billInfo = {
        billNumber,
        billName: data.nwvrqwxyaytdsfvhu[1]?.row?.[0]?.BILL_NAME || '',
        proposer: data.nwvrqwxyaytdsfvhu[1]?.row?.[0]?.PROPOSER || '',
        proposeDate: data.nwvrqwxyaytdsfvhu[1]?.row?.[0]?.PROPOSE_DT || '',
        procResult: data.nwvrqwxyaytdsfvhu[1]?.row?.[0]?.PROC_RESULT || ''
      };

      cache.set(cacheKey, billInfo);
      console.log('✅ 의안정보 조회 완료:', billNumber);

      return billInfo;
    }

    return null;

  } catch (error) {
    console.error('❌ 국회 의안정보 조회 실패:', error.message);
    return null;
  }
}

/**
 * 공공데이터 포털 API 호출 (일반)
 * @param {string} apiUrl - API 엔드포인트
 * @param {Object} params - API 파라미터
 * @returns {Promise<Object|null>} API 응답 데이터
 */
async function fetchPublicData(apiUrl, params = {}) {
  if (!apiUrl) {
    return null;
  }

  const cacheKey = `public:${apiUrl}:${JSON.stringify(params)}`;

  if (cache.has(cacheKey)) {
    console.log('✅ 캐시에서 공공데이터 반환');
    return cache.get(cacheKey);
  }

  try {
    console.log('🌐 공공데이터 조회:', apiUrl);

    const { data } = await axios.get(apiUrl, {
      params,
      timeout: 10000
    });

    cache.set(cacheKey, data);
    console.log('✅ 공공데이터 조회 완료');

    return data;

  } catch (error) {
    console.error('❌ 공공데이터 조회 실패:', error.message);
    return null;
  }
}

/**
 * 지역 예산 정보 조회 (예시)
 * @param {string} region - 지역명
 * @returns {Promise<Object|null>} 예산 정보
 */
async function fetchLocalBudget(region) {
  if (!region) {
    return null;
  }

  const cacheKey = `budget:${region}`;

  if (cache.has(cacheKey)) {
    console.log('✅ 캐시에서 예산정보 반환:', region);
    return cache.get(cacheKey);
  }

  try {
    // 지방재정통합공개시스템 API (실제 사용 시 API 키 필요)
    // const url = 'https://lofin.mois.go.kr/openapi/...';

    console.log('💰 지역 예산정보 조회:', region);

    // 실제 구현 예시 (API 키와 실제 엔드포인트 필요)
    // const { data } = await axios.get(url, {
    //   params: {
    //     region,
    //     serviceKey: process.env.PUBLIC_DATA_API_KEY
    //   },
    //   timeout: 10000
    // });

    // 임시: API 키 없이는 null 반환
    console.warn('⚠️ 공공데이터 API 키가 설정되지 않았습니다.');
    return null;

  } catch (error) {
    console.error('❌ 예산정보 조회 실패:', error.message);
    return null;
  }
}

/**
 * 공공데이터를 프롬프트용 텍스트로 변환
 * @param {Object} data - 공공데이터
 * @param {string} type - 데이터 타입 (bill, budget 등)
 * @returns {string} 프롬프트에 삽입할 텍스트
 */
function formatPublicDataForPrompt(data, type = 'general') {
  if (!data) {
    return '';
  }

  switch (type) {
    case 'bill':
      return `
[🏛️ 국회 의안정보]
- 의안번호: ${data.billNumber}
- 의안명: ${data.billName}
- 제안자: ${data.proposer}
- 제안일: ${data.proposeDate}
- 처리결과: ${data.procResult}

---
`;

    case 'budget':
      return `
[💰 예산 정보]
${JSON.stringify(data, null, 2)}

---
`;

    default:
      return `
[📊 공공데이터]
${JSON.stringify(data, null, 2)}

---
`;
  }
}

module.exports = {
  fetchAssemblyBill,
  fetchPublicData,
  fetchLocalBudget,
  formatPublicDataForPrompt
};
