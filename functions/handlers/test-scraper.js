/**
 * functions/handlers/test-scraper.js
 * 스크래핑 서비스 테스트용 핸들러
 */

const { onCall } = require('firebase-functions/v2/https');
const { necScraper } = require('../services/nec-scraper');
const { calendarSync } = require('../services/calendar-sync');

/**
 * 선거일정 스크래핑 테스트 (간단화)
 */
const testElectionScraping = onCall({ 
  region: 'asia-northeast3',
  cors: true 
}, async (request) => {
  try {
    console.log('🧪 간단화된 선거일정 테스트 시작');
    
    // 직접 폴백 데이터 사용
    const testElections = [
      {
        date: '2026-06-03',
        name: '제9회 전국동시지방선거',
        type: 'LOCAL_GOVERNMENT',
        source: 'TEST_DATA'
      },
      {
        date: '2028-04-12', 
        name: '제23대 국회의원선거',
        type: 'NATIONAL_ASSEMBLY',
        source: 'TEST_DATA'
      }
    ];
    
    // 다음 선거 찾기
    const today = new Date().toISOString().split('T')[0];
    const upcomingElections = testElections.filter(e => e.date >= today);
    const nextElection = upcomingElections.length > 0 ? upcomingElections[0] : null;
    
    console.log('📊 테스트 결과:', {
      총선거수: testElections.length,
      미래선거수: upcomingElections.length,
      다음선거: nextElection?.name
    });
    
    return {
      timestamp: new Date().toISOString(),
      success: true,
      data: {
        scrapedElections: {
          count: testElections.length,
          data: testElections
        },
        calendarData: {
          holidays: 0,
          elections: testElections.length,
          combined: testElections.length,
          lastUpdated: new Date().toISOString()
        },
        sampleData: {
          nextElection: nextElection,
          recentHolidays: []
        }
      },
      error: null,
      performance: {
        startTime: Date.now(),
        endTime: Date.now(),
        duration: 0
      }
    };
    
  } catch (error) {
    console.error('❌ 스크래핑 테스트 실패:', error);
    
    return {
      timestamp: new Date().toISOString(),
      success: false,
      error: {
        message: error.message,
        stack: error.stack
      },
      data: null
    };
  }
});

/**
 * 캐시 상태 확인
 */
const checkCacheStatus = onCall({ 
  region: 'asia-northeast3',
  cors: true 
}, async (request) => {
  try {
    const necCacheStatus = {
      isValid: necScraper.isCacheValid(),
      lastUpdated: necScraper.cache.lastUpdated,
      dataCount: necScraper.cache.elections?.length || 0
    };
    
    const calendarCacheStatus = {
      isValid: calendarSync.isCacheValid(),
      lastUpdated: calendarSync.cache.lastUpdated,
      holidayCount: calendarSync.cache.holidays?.length || 0,
      electionCount: calendarSync.cache.elections?.length || 0
    };
    
    return {
      timestamp: new Date().toISOString(),
      necScraper: necCacheStatus,
      calendarSync: calendarCacheStatus
    };
    
  } catch (error) {
    console.error('❌ 캐시 상태 확인 실패:', error);
    throw new Error('캐시 상태 확인에 실패했습니다.');
  }
});

/**
 * 캐시 강제 새로고침
 */
const refreshCache = onCall({ 
  region: 'asia-northeast3',
  cors: true 
}, async (request) => {
  try {
    console.log('🔄 캐시 강제 새로고침 시작');
    
    // 캐시 초기화
    necScraper.cache = { elections: null, lastUpdated: null };
    calendarSync.cache = { holidays: null, elections: null, lastUpdated: null };
    
    // 새로운 데이터 가져오기
    const refreshedData = await calendarSync.syncAllCalendarData();
    
    console.log('✅ 캐시 새로고침 완료');
    
    return {
      timestamp: new Date().toISOString(),
      success: true,
      data: {
        holidays: refreshedData.holidays.length,
        elections: refreshedData.elections.length,
        lastUpdated: refreshedData.lastUpdated
      }
    };
    
  } catch (error) {
    console.error('❌ 캐시 새로고침 실패:', error);
    throw new Error('캐시 새로고침에 실패했습니다.');
  }
});

module.exports = {
  testElectionScraping,
  checkCacheStatus,
  refreshCache
};