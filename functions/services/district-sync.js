'use strict';

/**
 * 선관위 API 기반 선거구 데이터 동기화 서비스
 * - 월 1회 자동 동기화 (매월 1일 새벽 3시)
 * - 2026년 지방선거 데이터가 등록되면 자동으로 가져옴
 * - 현재 데이터: 1992~2015년 선거 데이터 (2026년 데이터는 추후 등록 예정)
 */

const axios = require('axios');
const { admin, db } = require('../utils/firebaseAdmin');

const API_BASE_URL = 'http://apis.data.go.kr/9760000/CommonCodeService';

/**
 * Secret Manager에서 API 키 가져오기
 */
async function getApiKey() {
  // Secret Manager 설정 전에는 환경변수 사용
  if (process.env.NEC_API_KEY) {
    return process.env.NEC_API_KEY;
  }

  // Secret Manager 통합 (추후 구현)
  try {
    const { SecretManagerServiceClient } = require('@google-cloud/secret-manager');
    const client = new SecretManagerServiceClient();
    const projectId = process.env.GCLOUD_PROJECT || 'ai-secretary-442305';
    const name = `projects/${projectId}/secrets/NEC_API_KEY/versions/latest`;
    const [version] = await client.accessSecretVersion({ name });
    return version.payload.data.toString('utf8');
  } catch (error) {
    console.error('❌ [getApiKey] Secret Manager 접근 실패:', error.message);
    throw new Error('NEC_API_KEY를 찾을 수 없습니다. 환경변수 또는 Secret Manager를 설정해주세요.');
  }
}

/**
 * 선거 목록 조회 (전체 페이지 자동 처리)
 */
async function fetchElectionList() {
  const apiKey = await getApiKey();
  const url = `${API_BASE_URL}/getCommonSgCodeList`;

  console.log('📋 [fetchElectionList] 선거 목록 조회 시작...');

  try {
    let allItems = [];
    let pageNo = 1;

    while (pageNo <= 3) {  // 최대 3페이지 (300개 선거)
      const response = await axios.get(url, {
        params: {
          serviceKey: apiKey,
          pageNo: pageNo,
          numOfRows: 100,
          resultType: 'json'
        }
      });

      const data = response.data?.response;
      if (data?.header?.resultCode !== 'INFO-00') {
        if (pageNo === 1) {
          throw new Error(`API 오류: ${data?.header?.resultMsg || '알 수 없는 오류'}`);
        }
        break;
      }

      const items = data.body?.items?.item || [];
      if (!items || items.length === 0) break;

      const itemsArray = Array.isArray(items) ? items : [items];
      allItems = allItems.concat(itemsArray);

      pageNo++;
      await new Promise(resolve => setTimeout(resolve, 100));
    }

    console.log(`✅ [fetchElectionList] 총 ${allItems.length}개 선거 조회 완료`);
    return allItems;
  } catch (error) {
    console.error('❌ [fetchElectionList] 오류:', error.message);
    throw error;
  }
}

/**
 * 특정 선거의 구시군 목록 조회
 */
async function fetchGusigunList(sgId) {
  const apiKey = await getApiKey();
  const url = `${API_BASE_URL}/getCommonGusigunCodeList`;

  console.log(`📍 [fetchGusigunList] 선거 ${sgId}의 구시군 목록 조회...`);

  try {
    const response = await axios.get(url, {
      params: {
        serviceKey: apiKey,
        sgId: sgId,
        pageNo: 1,
        numOfRows: 300,
        resultType: 'json'
      }
    });

    const data = response.data?.response;
    if (data?.header?.resultCode !== 'INFO-00') {
      throw new Error(`API 오류: ${data?.header?.resultMsg || '알 수 없는 오류'}`);
    }

    const items = data.body?.items?.item || [];
    console.log(`✅ [fetchGusigunList] ${items.length}개 구시군 조회 완료`);
    return items;
  } catch (error) {
    console.error(`❌ [fetchGusigunList] 오류 (sgId: ${sgId}):`, error.message);
    return [];
  }
}

/**
 * 특정 선거의 선거구 목록 조회 (전체 페이지 자동 처리)
 * @param {string} sgId - 선거ID (예: 20140604)
 * @param {string} sgTypecode - 선거종류코드 (2:국회의원, 5:시도의원, 6:구시군의원)
 */
async function fetchElectoralDistrictList(sgId, sgTypecode) {
  const apiKey = await getApiKey();
  const url = `${API_BASE_URL}/getCommonSggCodeList`;

  console.log(`🗳️ [fetchElectoralDistrictList] 선거구 조회 (sgId: ${sgId}, type: ${sgTypecode})...`);

  try {
    let allItems = [];
    let pageNo = 1;
    let totalCount = 0;

    while (true) {
      const response = await axios.get(url, {
        params: {
          serviceKey: apiKey,
          sgId: sgId,
          sgTypecode: sgTypecode,
          pageNo: pageNo,
          numOfRows: 100,
          resultType: 'json'
        }
      });

      const data = response.data?.response;
      if (data?.header?.resultCode !== 'INFO-00') {
        if (pageNo === 1) {
          console.warn(`⚠️ [fetchElectoralDistrictList] API 오류: ${data?.header?.resultMsg}`);
        }
        break;
      }

      const items = data.body?.items?.item || [];
      const itemsArray = Array.isArray(items) ? items : (items ? [items] : []);

      if (itemsArray.length === 0) break;

      allItems = allItems.concat(itemsArray);
      totalCount = parseInt(data.body?.totalCount) || 0;

      console.log(`   📄 [fetchElectoralDistrictList] 페이지 ${pageNo}: ${itemsArray.length}개 (총 ${totalCount}개 중 ${allItems.length}개)`);

      // 전체 데이터를 다 가져왔으면 종료
      if (allItems.length >= totalCount) break;

      pageNo++;

      // 안전장치: 최대 20페이지 (2000개)
      if (pageNo > 20) break;

      // API 요청 제한을 위한 짧은 대기
      await new Promise(resolve => setTimeout(resolve, 100));
    }

    console.log(`✅ [fetchElectoralDistrictList] 총 ${allItems.length}개 선거구 조회 완료`);
    return allItems;
  } catch (error) {
    console.error(`❌ [fetchElectoralDistrictList] 오류:`, error.message);
    return [];
  }
}

/**
 * 선거구 데이터를 Firestore에 저장
 */
async function saveElectoralDistrictsToFirestore(sgId, sgTypecode, districts) {
  if (!districts || districts.length === 0) {
    console.log(`ℹ️ [saveElectoralDistrictsToFirestore] 저장할 선거구 없음 (sgId: ${sgId}, type: ${sgTypecode})`);
    return 0;
  }

  const batch = db.batch();
  let count = 0;

  // 선거종류코드를 직책으로 매핑
  const positionMap = {
    '1': '대통령',
    '2': '국회의원',
    '3': '광역자치단체장',
    '4': '기초자치단체장',
    '5': '광역의원',
    '6': '기초의원',
    '7': '국회의원비례',
    '8': '광역의원비례',
    '9': '기초의원비례',
    '10': '교육의원',
    '11': '교육감'
  };

  for (const district of districts) {
    const docId = `${sgId}_${sgTypecode}_${district.sggName}`.replace(/\s+/g, '_');
    const docRef = db.collection('electoral_districts').doc(docId);

    batch.set(docRef, {
      electionId: sgId,
      electionType: sgTypecode,
      position: positionMap[sgTypecode] || '기타',
      electoralDistrict: district.sggName || '',
      regionMetro: district.sdName || '',
      regionLocal: district.wiwName || '',
      selectedCount: parseInt(district.sggJungsu) || 1,
      order: parseInt(district.sOrder) || 0,
      source: 'NEC_API',
      syncedAt: admin.firestore.FieldValue.serverTimestamp(),
      createdAt: admin.firestore.FieldValue.serverTimestamp()
    }, { merge: true });

    count++;
  }

  await batch.commit();
  console.log(`✅ [saveElectoralDistrictsToFirestore] ${count}개 선거구 저장 완료`);
  return count;
}

/**
 * 특정 선거의 모든 선거구 데이터 동기화
 */
async function syncElectionData(sgId, sgName) {
  console.log(`\n🔄 [syncElectionData] 선거 동기화 시작: ${sgName} (${sgId})`);

  let totalSaved = 0;

  // 주요 선거 종류만 동기화 (국회의원, 광역의원, 기초의원)
  const electionTypes = [
    { code: '2', name: '국회의원' },
    { code: '5', name: '광역의원' },
    { code: '6', name: '기초의원' }
  ];

  for (const type of electionTypes) {
    console.log(`  ⏳ [syncElectionData] ${type.name} 선거구 동기화 중...`);
    const districts = await fetchElectoralDistrictList(sgId, type.code);
    const saved = await saveElectoralDistrictsToFirestore(sgId, type.code, districts);
    totalSaved += saved;
  }

  console.log(`✅ [syncElectionData] ${sgName} 동기화 완료: 총 ${totalSaved}개 선거구 저장\n`);
  return totalSaved;
}

/**
 * 2026년 이후 선거 데이터 동기화 (미래 선거 대상)
 */
async function syncUpcomingElections() {
  console.log('🚀 [syncUpcomingElections] 미래 선거 데이터 동기화 시작...\n');

  try {
    const elections = await fetchElectionList();

    // 2020년 이후 선거만 필터링 (2026년 데이터가 등록되면 자동 감지)
    const upcomingElections = elections.filter(election => {
      const sgId = election.sgId;
      return parseInt(sgId) >= 20200000;
    });

    if (upcomingElections.length === 0) {
      console.log('ℹ️ [syncUpcomingElections] 2020년 이후 선거 데이터 없음 (2026년 데이터 미등록)');
      return {
        success: true,
        message: '2026년 선거 데이터가 아직 등록되지 않았습니다.',
        electionsSynced: 0,
        districtsSaved: 0
      };
    }

    console.log(`📋 [syncUpcomingElections] ${upcomingElections.length}개 미래 선거 발견:`);
    upcomingElections.forEach(e => console.log(`   - ${e.sgName} (${e.sgId})`));
    console.log('');

    let totalDistrictsSaved = 0;

    for (const election of upcomingElections) {
      const saved = await syncElectionData(election.sgId, election.sgName);
      totalDistrictsSaved += saved;
    }

    console.log(`\n🎉 [syncUpcomingElections] 동기화 완료!`);
    console.log(`   - 선거 수: ${upcomingElections.length}개`);
    console.log(`   - 선거구 수: ${totalDistrictsSaved}개\n`);

    return {
      success: true,
      message: '선거구 데이터 동기화 완료',
      electionsSynced: upcomingElections.length,
      districtsSaved: totalDistrictsSaved,
      elections: upcomingElections.map(e => ({
        id: e.sgId,
        name: e.sgName,
        date: e.sgVotedate
      }))
    };
  } catch (error) {
    console.error('❌ [syncUpcomingElections] 동기화 실패:', error);
    return {
      success: false,
      message: error.message,
      electionsSynced: 0,
      districtsSaved: 0
    };
  }
}

/**
 * 특정 선거 데이터만 동기화 (수동 트리거용)
 */
async function syncSpecificElection(sgId) {
  console.log(`🎯 [syncSpecificElection] 특정 선거 동기화: ${sgId}`);

  try {
    const elections = await fetchElectionList();
    const election = elections.find(e => e.sgId === sgId);

    if (!election) {
      throw new Error(`선거 ID ${sgId}를 찾을 수 없습니다.`);
    }

    const districtsSaved = await syncElectionData(election.sgId, election.sgName);

    return {
      success: true,
      message: `${election.sgName} 동기화 완료`,
      electionsSynced: 1,
      districtsSaved
    };
  } catch (error) {
    console.error('❌ [syncSpecificElection] 오류:', error);
    throw error;
  }
}

module.exports = {
  syncUpcomingElections,
  syncSpecificElection,
  fetchElectionList,
  fetchGusigunList,
  fetchElectoralDistrictList
};
