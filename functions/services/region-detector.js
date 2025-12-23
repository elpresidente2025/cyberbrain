'use strict';

/**
 * functions/services/region-detector.js
 * 지역명 감지 및 행정구역 조회 서비스
 * 네이버 Geocoding API를 활용하여 지역 간 관계 파악
 */

const axios = require('axios');
const NodeCache = require('node-cache');

// 캐시 설정 (24시간 TTL - 행정구역은 자주 변경되지 않음)
const cache = new NodeCache({ stdTTL: 86400 });

// 네이버 클라우드 플랫폼 Geocoding API
const NCP_CLIENT_ID = process.env.NCP_CLIENT_ID;
const NCP_CLIENT_SECRET = process.env.NCP_CLIENT_SECRET;
const GEOCODING_API_URL = 'https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode';

/**
 * 텍스트에서 지역명(동/읍/면/구/시) 추출
 * @param {string} text - 검색할 텍스트
 * @returns {Array<string>} 추출된 지역명 목록
 */
function extractRegionNames(text) {
  if (!text) return [];

  // 지역명 패턴 (동, 읍, 면, 구, 시, 군, 지구 등)
  const patterns = [
    // "OO동", "OO읍", "OO면" 패턴
    /([가-힣]{1,10}[동읍면리])\s*(?:선도)?지구/g,
    /([가-힣]{1,10}[동읍면리])(?:에서|에|의|을|를|이|가|은|는)/g,
    // "OO구", "OO시", "OO군" 패턴
    /([가-힣]{1,5}[구시군])(?:에서|에|의|을|를|이|가|은|는|\s)/g,
    // 단독 지역명 (문맥상)
    /([가-힣]{2,4}(?:동|읍|면))\b/g
  ];

  const regions = new Set();

  for (const pattern of patterns) {
    const matches = text.matchAll(pattern);
    for (const match of matches) {
      if (match[1]) {
        regions.add(match[1]);
      }
    }
  }

  return [...regions];
}

/**
 * 네이버 Geocoding API로 지역 정보 조회
 * @param {string} regionName - 지역명 (예: "화명동")
 * @returns {Promise<Object|null>} 지역 정보 { sido, sigungu, dong }
 */
async function getRegionInfo(regionName) {
  if (!regionName) return null;

  // 캐시 확인
  const cacheKey = `region:${regionName}`;
  if (cache.has(cacheKey)) {
    console.log('✅ 캐시에서 지역 정보 반환:', regionName);
    return cache.get(cacheKey);
  }

  // API 키 확인
  if (!NCP_CLIENT_ID || !NCP_CLIENT_SECRET) {
    console.warn('⚠️ NCP API 키 미설정 - 지역 검증 건너뜀');
    return null;
  }

  try {
    console.log('🗺️ 네이버 Geocoding API 호출:', regionName);

    const response = await axios.get(GEOCODING_API_URL, {
      params: { query: regionName },
      headers: {
        'X-NCP-APIGW-API-KEY-ID': NCP_CLIENT_ID,
        'X-NCP-APIGW-API-KEY': NCP_CLIENT_SECRET
      },
      timeout: 5000
    });

    if (response.data.status !== 'OK' || !response.data.addresses?.length) {
      console.log('ℹ️ 지역 정보 없음:', regionName);
      return null;
    }

    const address = response.data.addresses[0];
    const elements = address.addressElements || [];

    // 시도, 시군구, 읍면동 추출
    const result = {
      sido: elements.find(e => e.types?.includes('SIDO'))?.longName || '',
      sigungu: elements.find(e => e.types?.includes('SIGUGUN'))?.longName || '',
      dong: elements.find(e => e.types?.includes('DONGMYUN'))?.longName || '',
      fullAddress: address.roadAddress || address.jibunAddress || ''
    };

    console.log('✅ 지역 정보 조회 완료:', result);

    // 캐시 저장
    cache.set(cacheKey, result);

    return result;

  } catch (error) {
    console.error('❌ Geocoding API 오류:', error.message);
    return null;
  }
}

/**
 * 사용자 지역구와 주제 지역 비교
 * @param {string} userRegion - 사용자 지역구 (예: "사하구")
 * @param {string} topicText - 글 주제 텍스트
 * @returns {Promise<Object>} 비교 결과
 */
async function compareRegions(userRegion, topicText) {
  const result = {
    isSameRegion: true,
    userRegion: userRegion || '',
    topicRegions: [],
    mismatchedRegions: [],
    promptHint: ''
  };

  if (!userRegion || !topicText) {
    return result;
  }

  // 주제에서 지역명 추출
  const extractedRegions = extractRegionNames(topicText);

  if (extractedRegions.length === 0) {
    return result;
  }

  console.log('🔍 추출된 지역명:', extractedRegions);

  // 각 지역의 상세 정보 조회
  for (const regionName of extractedRegions) {
    const info = await getRegionInfo(regionName);

    if (info && info.sigungu) {
      result.topicRegions.push({
        name: regionName,
        ...info
      });

      // 사용자 지역구와 비교 (시군구 단위)
      // "사하구" vs "북구" 비교
      const userSigungu = userRegion.replace(/\s/g, '');
      const topicSigungu = info.sigungu.replace(/\s/g, '');

      if (!topicSigungu.includes(userSigungu) && !userSigungu.includes(topicSigungu)) {
        result.isSameRegion = false;
        result.mismatchedRegions.push({
          name: regionName,
          sigungu: info.sigungu,
          sido: info.sido
        });
      }
    }
  }

  // 불일치 시 프롬프트 힌트 생성
  if (!result.isSameRegion && result.mismatchedRegions.length > 0) {
    const regions = result.mismatchedRegions.map(r => `${r.sido} ${r.sigungu} ${r.name}`).join(', ');
    result.promptHint = `
[⚠️ 타 지역 주제 안내]
이 글의 주제는 "${regions}"에 관한 것입니다.
작성자의 지역구는 "${userRegion}"이므로, 다음 사항에 유의하세요:

1. "우리 지역", "우리 동네" 표현 사용 금지
2. 대신 "${result.mismatchedRegions[0].name}", "${result.mismatchedRegions[0].sigungu}" 등 구체적 지역명 사용
3. "부산 시민의 한 사람으로서", "같은 시민으로서" 등의 관점 사용 권장
4. 해당 지역 주민을 축하/격려하는 톤 유지
5. 자신의 지역구(${userRegion})에도 유사한 발전이 이루어지길 바란다는 메시지 가능
`;
  }

  return result;
}

/**
 * 글 생성 전 지역 검증 (통합 함수)
 * @param {string} userRegionLocal - 사용자 기초자치단체 (예: "사하구")
 * @param {string} userRegionMetro - 사용자 광역자치단체 (예: "부산광역시")
 * @param {string} topic - 글 주제
 * @param {Object} targetElection - 목표 선거 정보 (선택) { position, regionMetro, regionLocal, electoralDistrict }
 * @param {string} position - 현재 직책 (예: "국회의원", "광역자치단체장", "기초자치단체장")
 * @returns {Promise<Object>} 검증 결과 및 프롬프트 힌트
 */
async function validateTopicRegion(userRegionLocal, userRegionMetro, topic, targetElection = null, position = '') {
  try {
    // 목표 선거가 있으면 해당 직책/지역 기준, 없으면 현재 직책/지역 기준
    const effectivePosition = targetElection?.position || position;
    let effectiveRegionLocal = targetElection?.regionLocal || userRegionLocal;
    let effectiveRegionMetro = targetElection?.regionMetro || userRegionMetro;

    console.log('🎯 지역 검증 기준:', {
      effectivePosition,
      effectiveRegionLocal,
      effectiveRegionMetro,
      hasTargetElection: !!targetElection
    });

    // 직책별 관할 범위 결정
    // - 광역자치단체장: 광역시/도 전체 (시군구 비교 불필요)
    // - 기초자치단체장: 해당 시군구 전체 (선거구와 무관하게 regionLocal 기준)
    // - 의원류: 선거구 기준 (현재 로직 유지)

    if (effectivePosition === '광역자치단체장') {
      // 광역자치단체장: 같은 시도 내 모든 지역이 "우리 지역"
      const comparison = await compareRegionsForMetro(effectiveRegionMetro, topic);

      console.log('🗺️ 광역단체장 지역 검증:', {
        regionMetro: effectiveRegionMetro,
        isSameRegion: comparison.isSameRegion
      });

      return {
        valid: true,
        isSameRegion: comparison.isSameRegion,
        promptHint: comparison.promptHint,
        details: comparison
      };
    }

    if (effectivePosition === '기초자치단체장') {
      // 기초자치단체장: 해당 시군구 전체가 "우리 지역"
      // 선거구(electoralDistrict)와 무관하게 regionLocal 기준
      const comparison = await compareRegions(effectiveRegionLocal, topic);

      console.log('🗺️ 기초단체장 지역 검증:', {
        regionLocal: effectiveRegionLocal,
        isSameRegion: comparison.isSameRegion
      });

      return {
        valid: true,
        isSameRegion: comparison.isSameRegion,
        promptHint: comparison.promptHint,
        details: comparison
      };
    }

    // 의원류 (국회의원, 광역의원, 기초의원): 기존 로직 유지 (regionLocal 비교)
    const comparison = await compareRegions(effectiveRegionLocal, topic);

    console.log('🗺️ 의원 지역 검증:', {
      position: effectivePosition,
      regionLocal: effectiveRegionLocal,
      isSameRegion: comparison.isSameRegion,
      topicRegions: comparison.topicRegions.map(r => r.name),
      mismatchedCount: comparison.mismatchedRegions.length
    });

    return {
      valid: true,
      isSameRegion: comparison.isSameRegion,
      promptHint: comparison.promptHint,
      details: comparison
    };

  } catch (error) {
    console.error('❌ 지역 검증 실패:', error.message);
    // 오류 시에도 원고 생성은 계속 진행
    return {
      valid: true,
      isSameRegion: true,
      promptHint: '',
      details: null
    };
  }
}

/**
 * 광역단체장용 지역 비교 (시도 단위)
 * @param {string} userRegionMetro - 사용자 광역자치단체 (예: "부산광역시")
 * @param {string} topicText - 글 주제 텍스트
 * @returns {Promise<Object>} 비교 결과
 */
async function compareRegionsForMetro(userRegionMetro, topicText) {
  const result = {
    isSameRegion: true,
    userRegion: userRegionMetro || '',
    topicRegions: [],
    mismatchedRegions: [],
    promptHint: ''
  };

  if (!userRegionMetro || !topicText) {
    return result;
  }

  // 주제에서 지역명 추출
  const extractedRegions = extractRegionNames(topicText);

  if (extractedRegions.length === 0) {
    return result;
  }

  console.log('🔍 광역단체장 - 추출된 지역명:', extractedRegions);

  // 각 지역의 상세 정보 조회
  for (const regionName of extractedRegions) {
    const info = await getRegionInfo(regionName);

    if (info && info.sido) {
      result.topicRegions.push({
        name: regionName,
        ...info
      });

      // 광역단체 비교 (시도 단위)
      // "부산광역시" vs "부산광역시" 비교
      const userSido = userRegionMetro.replace(/\s/g, '');
      const topicSido = info.sido.replace(/\s/g, '');

      if (!topicSido.includes(userSido) && !userSido.includes(topicSido)) {
        result.isSameRegion = false;
        result.mismatchedRegions.push({
          name: regionName,
          sigungu: info.sigungu,
          sido: info.sido
        });
      }
    }
  }

  // 불일치 시 프롬프트 힌트 생성
  if (!result.isSameRegion && result.mismatchedRegions.length > 0) {
    const regions = result.mismatchedRegions.map(r => `${r.sido} ${r.sigungu} ${r.name}`).join(', ');
    result.promptHint = `
[⚠️ 타 지역 주제 안내]
이 글의 주제는 "${regions}"에 관한 것입니다.
작성자의 관할은 "${userRegionMetro}"이므로, 다음 사항에 유의하세요:

1. "우리 지역", "우리 시/도" 표현 사용 금지
2. 대신 "${result.mismatchedRegions[0].sido}" 등 구체적 지역명 사용
3. 타 지역 사례를 참고하는 관점으로 작성
4. 해당 지역 발전을 축하/격려하는 톤 유지
`;
  }

  return result;
}

module.exports = {
  extractRegionNames,
  getRegionInfo,
  compareRegions,
  compareRegionsForMetro,
  validateTopicRegion
};
