/**
 * functions/services/calendar-sync.js
 * 외부 캘린더 데이터 동기화 서비스
 */

const https = require('https');

/**
 * 한국 공휴일 및 선거일정 동기화 서비스
 */
class CalendarSyncService {
  constructor() {
    this.sources = {
      // GitHub - hyunbinseo/holidays-kr (과기부 월력요항 기준)
      KOREAN_HOLIDAYS: 'https://holidays.hyunbin.page/basic.json',
      
      // 중앙선거관리위원회 선거일정 (향후 API 키 필요)
      ELECTION_SCHEDULE: 'https://www.nec.go.kr/site/nec/ex/bbs/List.do?cbIdx=1104',
      
      // 백업: ICS 형식
      KOREAN_HOLIDAYS_ICS: 'https://holidays.hyunbin.page/basic.ics'
    };
    
    this.cache = {
      holidays: null,
      elections: null,
      lastUpdated: null
    };
  }

  /**
   * 한국 공휴일 데이터 가져오기
   * @returns {Promise<Array>} 공휴일 목록
   */
  async fetchKoreanHolidays() {
    try {
      const data = await this.fetchJsonData(this.sources.KOREAN_HOLIDAYS);
      
      const holidays = data.map(holiday => ({
        date: holiday.date,
        name: holiday.name,
        type: 'HOLIDAY',
        isRecurring: holiday.isRecurring || false,
        source: 'GOVERNMENT_OFFICIAL'
      }));

      this.cache.holidays = holidays;
      this.cache.lastUpdated = new Date();
      
      console.log(`✅ 공휴일 ${holidays.length}개 동기화 완료`);
      return holidays;
      
    } catch (error) {
      console.error('❌ 공휴일 데이터 가져오기 실패:', error);
      console.log('📋 캐시된 공휴일 사용:', this.cache.holidays?.length || 0 + '개');
      return this.cache.holidays || [];
    }
  }

  /**
   * 선거일정 데이터 가져오기 (웹 스크래핑 방식)
   * @returns {Promise<Array>} 선거일정 목록
   */
  async fetchElectionSchedule() {
    try {
      // NECScraper 동적 import (require는 함수 내에서 사용)
      const { necScraper } = require('./nec-scraper');
      
      // 캐시된 데이터가 유효한지 확인
      const cachedElections = necScraper.getCachedElections();
      if (cachedElections) {
        console.log('📦 캐시된 선거일정 사용');
        this.cache.elections = cachedElections;
        return cachedElections;
      }
      
      // 중앙선거관리위원회에서 실시간 스크래핑
      const scrapedElections = await necScraper.scrapeElectionSchedule();
      
      // 데이터 정규화 (우리 시스템 형식에 맞게)
      const elections = scrapedElections.map(election => ({
        date: election.date,
        name: election.name,
        type: election.type,
        year: election.year,
        positions: this.getPositionsByType(election.type),
        source: election.source,
        scrapedAt: election.scrapedAt
      }));

      this.cache.elections = elections;
      console.log(`✅ 선거일정 ${elections.length}개 스크래핑 완료`);
      return elections;
      
    } catch (error) {
      console.error('❌ 선거일정 스크래핑 실패:', error);
      
      // 폴백: 기존 캐시 또는 하드코딩된 데이터
      console.log('⚠️ 스크래핑 실패, 폴백 데이터 사용');
      const fallbackElections = this.getFallbackElections();
      console.log('📋 폴백 선거 데이터:', fallbackElections.length + '개');
      
      this.cache.elections = fallbackElections;
      return fallbackElections;
    }
  }

  /**
   * 선거 유형별 직책 목록 반환
   * @param {string} electionType 
   * @returns {Array}
   */
  getPositionsByType(electionType) {
    const positionMap = {
      'PRESIDENTIAL': ['대통령'],
      'NATIONAL_ASSEMBLY': ['국회의원'],
      'LOCAL_GOVERNMENT': ['광역의원', '기초의원', '광역단체장', '기초단체장'],
      'BY_ELECTION': ['보궐선거 해당직']
    };
    
    return positionMap[electionType] || ['기타'];
  }

  /**
   * 폴백 선거일정 데이터
   * @returns {Array}
   */
  getFallbackElections() {
    console.log('📋 폴백 선거일정 사용');
    const today = new Date();
    const todayStr = today.toISOString().split('T')[0];
    
    const allElections = [
      {
        date: '2026-06-03',
        name: '제9회 전국동시지방선거',
        type: 'LOCAL_GOVERNMENT',
        year: 2026,
        positions: ['광역의원', '기초의원', '광역단체장', '기초단체장'],
        source: 'FALLBACK_DATA'
      },
      {
        date: '2028-04-12',
        name: '제23대 국회의원선거',
        type: 'NATIONAL_ASSEMBLY',
        year: 2028,
        positions: ['국회의원'],
        source: 'FALLBACK_DATA'
      }
    ];
    
    console.log('🔍 필터링 전 선거:', allElections.length + '개');
    console.log('📅 오늘 날짜:', todayStr);
    
    // 현재 날짜 이후의 선거만 반환
    const filtered = allElections.filter(election => {
      const isUpcoming = election.date >= todayStr;
      console.log(`- ${election.name}: ${election.date} >= ${todayStr} = ${isUpcoming}`);
      return isUpcoming;
    });
    
    console.log('🔍 필터링 후 선거:', filtered.length + '개');
    return filtered;
  }

  /**
   * 통합 캘린더 데이터 가져오기
   * @returns {Promise<Object>} 통합 캘린더 데이터
   */
  async syncAllCalendarData() {
    try {
      const [holidays, elections] = await Promise.all([
        this.fetchKoreanHolidays(),
        this.fetchElectionSchedule()
      ]);

      const result = {
        holidays,
        elections,
        combined: [...holidays, ...elections].sort((a, b) => 
          new Date(a.date) - new Date(b.date)
        ),
        lastUpdated: new Date(),
        sources: this.sources
      };

      console.log('📅 캘린더 동기화 완료:', {
        holidays: holidays.length,
        elections: elections.length,
        total: result.combined.length
      });

      return result;
      
    } catch (error) {
      console.error('❌ 캘린더 동기화 실패:', error);
      throw error;
    }
  }

  /**
   * 특정 날짜의 이벤트 조회
   * @param {string} date - YYYY-MM-DD 형식
   * @returns {Array} 해당 날짜의 이벤트 목록
   */
  async getEventsForDate(date) {
    if (!this.cache.holidays || !this.cache.elections) {
      await this.syncAllCalendarData();
    }

    const allEvents = [...(this.cache.holidays || []), ...(this.cache.elections || [])];
    return allEvents.filter(event => event.date === date);
  }

  /**
   * 다음 선거일 조회
   * @returns {Object|null} 다음 선거 정보
   */
  async getNextElection() {
    if (!this.cache.elections) {
      await this.fetchElectionSchedule();
    }

    const today = new Date();
    const upcomingElections = (this.cache.elections || [])
      .filter(election => new Date(election.date) >= today)
      .sort((a, b) => new Date(a.date) - new Date(b.date));

    console.log('🔍 다음 선거 조회:', {
      totalElections: this.cache.elections?.length || 0,
      upcomingElections: upcomingElections.length,
      today: today.toISOString().split('T')[0]
    });

    return upcomingElections.length > 0 ? upcomingElections[0] : null;
  }

  /**
   * JSON 데이터 가져오기 (HTTP 요청)
   * @param {string} url 
   * @returns {Promise<Object>}
   */
  fetchJsonData(url) {
    return new Promise((resolve, reject) => {
      https.get(url, (res) => {
        let data = '';
        
        res.on('data', (chunk) => {
          data += chunk;
        });
        
        res.on('end', () => {
          try {
            resolve(JSON.parse(data));
          } catch (error) {
            reject(new Error('JSON 파싱 실패: ' + error.message));
          }
        });
        
        res.on('error', (error) => {
          reject(error);
        });
      });
    });
  }

  /**
   * 캐시 데이터 유효성 검사 (24시간)
   * @returns {boolean}
   */
  isCacheValid() {
    if (!this.cache.lastUpdated) return false;
    
    const hoursSinceUpdate = (new Date() - this.cache.lastUpdated) / (1000 * 60 * 60);
    return hoursSinceUpdate < 24;
  }

  /**
   * 캐시 강제 새로고침
   */
  async refreshCache() {
    this.cache = {
      holidays: null,
      elections: null,
      lastUpdated: null
    };
    
    return await this.syncAllCalendarData();
  }
}

// 싱글톤 인스턴스
const calendarSync = new CalendarSyncService();

module.exports = {
  CalendarSyncService,
  calendarSync
};