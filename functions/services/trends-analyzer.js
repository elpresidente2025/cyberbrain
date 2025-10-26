/**
 * services/trends-analyzer.js
 * Google Trends API를 이용한 트렌드 분석
 */

'use strict';

const googleTrends = require('google-trends-api');

/**
 * Google Trends 점수 계산
 * @param {string} keyword - 분석할 키워드
 * @returns {Promise<Object>} { trendScore, trend, data }
 */
async function getTrendScore(keyword) {
  try {
    console.log(`📈 [Trends] Google Trends 분석 시작: ${keyword}`);

    const now = new Date();
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

    // Google Trends API 호출
    const result = await googleTrends.interestOverTime({
      keyword: keyword,
      startTime: sevenDaysAgo,
      endTime: now,
      geo: 'KR', // 대한민국
      granularTimeResolution: true
    });

    const data = JSON.parse(result);

    if (!data.default || !data.default.timelineData || data.default.timelineData.length === 0) {
      console.log(`⚠️ [Trends] "${keyword}" 트렌드 데이터 없음`);
      return {
        trendScore: 5, // 중립 점수
        trend: 'stable',
        data: []
      };
    }

    // 시간별 데이터 추출
    const timelineData = data.default.timelineData;
    const values = timelineData.map(point => point.value[0]);

    // 트렌드 계산
    const trendAnalysis = analyzeTrend(values);

    console.log(`✅ [Trends] "${keyword}" 분석 완료: ${trendAnalysis.trend} (점수: ${trendAnalysis.trendScore})`);

    return {
      trendScore: trendAnalysis.trendScore,
      trend: trendAnalysis.trend,
      data: values,
      average: trendAnalysis.average,
      change: trendAnalysis.change
    };

  } catch (error) {
    console.error(`❌ [Trends] 트렌드 분석 실패: ${keyword}`, error.message);

    // 에러 시 중립 점수 반환
    return {
      trendScore: 5,
      trend: 'unknown',
      data: [],
      error: error.message
    };
  }
}

/**
 * 트렌드 데이터 분석
 * @param {Array<number>} values - 시간별 검색량 값
 * @returns {Object} 트렌드 분석 결과
 */
function analyzeTrend(values) {
  if (!values || values.length === 0) {
    return {
      trendScore: 5,
      trend: 'stable',
      average: 0,
      change: 0
    };
  }

  // 평균값 계산
  const average = values.reduce((sum, v) => sum + v, 0) / values.length;

  // 최근 3일과 이전 4일 비교
  const recentDays = values.slice(-3);
  const previousDays = values.slice(0, -3);

  const recentAvg = recentDays.reduce((sum, v) => sum + v, 0) / recentDays.length;
  const previousAvg = previousDays.length > 0
    ? previousDays.reduce((sum, v) => sum + v, 0) / previousDays.length
    : recentAvg;

  // 변화율 계산
  const change = previousAvg > 0
    ? ((recentAvg - previousAvg) / previousAvg) * 100
    : 0;

  // 트렌드 판정
  let trend = 'stable';
  let trendScore = 5;

  if (change > 20) {
    trend = 'rising_fast';
    trendScore = 10;
  } else if (change > 10) {
    trend = 'rising';
    trendScore = 8;
  } else if (change > 5) {
    trend = 'slightly_rising';
    trendScore = 7;
  } else if (change < -20) {
    trend = 'falling_fast';
    trendScore = 2;
  } else if (change < -10) {
    trend = 'falling';
    trendScore = 3;
  } else if (change < -5) {
    trend = 'slightly_falling';
    trendScore = 4;
  } else {
    trend = 'stable';
    trendScore = 6;
  }

  // 검색량이 매우 낮으면 점수 하향
  if (average < 10) {
    trendScore = Math.max(1, trendScore - 2);
  }

  return {
    trendScore,
    trend,
    average,
    change: Math.round(change * 10) / 10
  };
}

/**
 * 여러 키워드의 트렌드 일괄 분석 (배치 처리)
 * @param {Array<string>} keywords - 키워드 배열
 * @returns {Promise<Object>} 키워드별 트렌드 결과
 */
async function getBatchTrendScores(keywords) {
  console.log(`📊 [Trends] 배치 분석 시작: ${keywords.length}개 키워드`);

  const results = {};

  // Google API 속도 제한 고려하여 순차 처리 (간격 추가)
  for (let i = 0; i < keywords.length; i++) {
    const keyword = keywords[i];

    try {
      results[keyword] = await getTrendScore(keyword);

      // API 호출 간격 (2초)
      if (i < keywords.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
    } catch (error) {
      console.error(`❌ [Trends] "${keyword}" 분석 실패:`, error.message);
      results[keyword] = {
        trendScore: 5,
        trend: 'unknown',
        error: error.message
      };
    }
  }

  console.log(`✅ [Trends] 배치 분석 완료: ${Object.keys(results).length}개`);

  return results;
}

/**
 * 트렌드 점수 캐싱 (Firestore)
 * @param {Object} db - Firestore 인스턴스
 * @param {string} keyword - 키워드
 * @param {Object} trendData - 트렌드 데이터
 */
async function cacheTrendScore(db, keyword, trendData) {
  try {
    await db.collection('trend_cache').doc(keyword).set({
      ...trendData,
      timestamp: new Date(),
      cachedAt: new Date().toISOString()
    });
    console.log(`💾 [Trends] 캐시 저장: ${keyword}`);
  } catch (error) {
    console.error(`❌ [Trends] 캐시 저장 실패:`, error.message);
  }
}

/**
 * 캐시된 트렌드 점수 조회
 * @param {Object} db - Firestore 인스턴스
 * @param {string} keyword - 키워드
 * @param {number} maxAgeHours - 캐시 유효 시간 (기본 12시간)
 * @returns {Promise<Object|null>} 캐시된 데이터 또는 null
 */
async function getCachedTrendScore(db, keyword, maxAgeHours = 12) {
  try {
    const doc = await db.collection('trend_cache').doc(keyword).get();

    if (!doc.exists) {
      return null;
    }

    const data = doc.data();
    const cacheAge = Date.now() - data.timestamp.toDate().getTime();
    const maxAge = maxAgeHours * 60 * 60 * 1000;

    if (cacheAge > maxAge) {
      console.log(`⏰ [Trends] 캐시 만료: ${keyword} (${Math.round(cacheAge / 1000 / 60)}분 전)`);
      return null;
    }

    console.log(`✅ [Trends] 캐시 hit: ${keyword}`);
    return data;

  } catch (error) {
    console.error(`❌ [Trends] 캐시 조회 실패:`, error.message);
    return null;
  }
}

module.exports = {
  getTrendScore,
  getBatchTrendScores,
  cacheTrendScore,
  getCachedTrendScore
};
