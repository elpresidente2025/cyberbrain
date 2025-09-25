/**
 * functions/services/nec-scraper.js
 * 중앙선거관리위원회 선거일정 웹 스크래핑 서비스
 */

const https = require('https');

/**
 * 중앙선거관리위원회 선거일정 스크래퍼
 */
class NECElectionScraper {
  constructor() {
    this.baseUrl = 'https://www.nec.go.kr/site/nec/ex/bbs/List.do?cbIdx=1104';
    this.cache = {
      elections: null,
      lastUpdated: null
    };
  }

  /**
   * 중앙선거관리위원회에서 선거일정 스크래핑
   * @returns {Promise<Array>} 선거일정 목록
   */
  async scrapeElectionSchedule() {
    try {
      console.log('🔍 중앙선거관리위원회 선거일정 스크래핑 시작...');
      
      const htmlContent = await this.fetchHtmlContent(this.baseUrl);
      const elections = this.parseElectionData(htmlContent);
      
      // 캐시 업데이트
      this.cache.elections = elections;
      this.cache.lastUpdated = new Date();
      
      console.log(`✅ 선거일정 ${elections.length}개 스크래핑 완료`);
      return elections;
      
    } catch (error) {
      console.error('❌ 선거일정 스크래핑 실패:', error.message);
      
      // 캐시된 데이터가 있으면 반환
      if (this.cache.elections) {
        console.log('📦 캐시된 선거일정 데이터 사용');
        return this.cache.elections;
      }
      
      // 폴백 데이터 반환
      return this.getFallbackElectionData();
    }
  }

  /**
   * HTML 콘텐츠 가져오기
   * @param {string} url 
   * @returns {Promise<string>}
   */
  fetchHtmlContent(url) {
    return new Promise((resolve, reject) => {
      const request = https.get(url, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
      }, (res) => {
        let data = '';
        
        // 인코딩 설정 (중앙선거관리위원회는 EUC-KR 사용)
        res.setEncoding('utf8');
        
        res.on('data', (chunk) => {
          data += chunk;
        });
        
        res.on('end', () => {
          resolve(data);
        });
        
        res.on('error', (error) => {
          reject(error);
        });
      });
      
      request.on('error', (error) => {
        reject(error);
      });
      
      request.setTimeout(10000, () => {
        request.abort();
        reject(new Error('Request timeout'));
      });
    });
  }

  /**
   * HTML에서 선거일정 데이터 파싱
   * @param {string} htmlContent 
   * @returns {Array}
   */
  parseElectionData(htmlContent) {
    try {
      const elections = [];
      
      // 리스트 형태의 선거 정보 파싱 (더 정확한 패턴)
      // 중앙선거관리위원회의 실제 HTML 구조에 맞게 수정
      const electionPatterns = [
        // 패턴 1: [ 선거유형 ] 선거명 (연도) 날짜
        /\[\s*([^\]]+)\s*\][^>]*>([^<]+)<[\s\S]*?(\d{4})[^<]*<[\s\S]*?(\d{4}-\d{2}-\d{2})/gi,
        // 패턴 2: 2026-06-03 형태의 날짜 먼저 찾기
        /(\d{4}-\d{2}-\d{2})[\s\S]*?\[\s*([^\]]+)\s*\][\s\S]*?>([^<]+)</gi,
        // 패턴 3: 제9회 전국동시지방선거 같은 형태
        /(제\d+회[^<]*선거)[\s\S]*?(\d{4}-\d{2}-\d{2})/gi
      ];
      
      for (const electionPattern of electionPatterns) {
        let match;
        while ((match = electionPattern.exec(htmlContent)) !== null) {
        try {
          const electionType = match[1].trim(); // 선거 유형
          const electionName = match[2].trim(); // 선거명
          const year = parseInt(match[3]); // 연도
          const dateStr = match[4]; // 날짜 문자열
          
          // 날짜 정규화
          const normalizedDate = this.extractDateFromText(dateStr);
          
          if (normalizedDate && year >= new Date().getFullYear()) {
            elections.push({
              date: normalizedDate,
              name: electionName || `${year} ${electionType}`,
              type: this.normalizeElectionType(electionType),
              year: year,
              source: 'NEC_SCRAPED',
              scrapedAt: new Date().toISOString(),
              rawData: {
                electionType,
                electionName,
                dateStr
              }
            });
          }
        } catch (parseError) {
          console.warn('개별 선거 데이터 파싱 실패:', parseError.message);
        }
        }
      }
      
      // 대안 파싱 방법: 더 넓은 패턴
      if (elections.length === 0) {
        console.log('🔄 대안 파싱 방법 시도...');
        elections.push(...this.parseElectionDataAlternative(htmlContent));
      }
      
      console.log(`📊 파싱된 선거 수: ${elections.length}`);
      
      // 중복 제거 및 날짜순 정렬
      const uniqueElections = this.removeDuplicates(elections);
      return this.sortElectionsByDate(uniqueElections);
      
    } catch (error) {
      console.error('❌ HTML 파싱 오류:', error.message);
      return [];
    }
  }

  /**
   * 대안 파싱 방법
   * @param {string} htmlContent 
   * @returns {Array}
   */
  parseElectionDataAlternative(htmlContent) {
    try {
      const elections = [];
      
      // 더 간단한 패턴: 2026년 이후의 모든 날짜 찾기
      const datePatterns = [
        /202[6-9]-\d{2}-\d{2}/g,
        /203\d-\d{2}-\d{2}/g,
        /202[6-9]\.\d{2}\.\d{2}/g,
        /202[6-9]년\s*\d{1,2}월\s*\d{1,2}일/g
      ];
      
      for (const pattern of datePatterns) {
        let match;
        while ((match = pattern.exec(htmlContent)) !== null) {
          const dateStr = match[0];
          const normalizedDate = this.extractDateFromText(dateStr);
          
          if (normalizedDate) {
            const year = parseInt(normalizedDate.split('-')[0]);
            elections.push({
              date: normalizedDate,
              name: `${year}년 선거`,
              type: 'OTHER',
              year: year,
              source: 'NEC_SCRAPED_ALT',
              scrapedAt: new Date().toISOString()
            });
          }
        }
      }
      
      return elections;
    } catch (error) {
      console.error('❌ 대안 파싱 오류:', error.message);
      return [];
    }
  }

  /**
   * 선거일정 행 데이터 파싱
   * @param {Array} cells 
   * @returns {Object|null}
   */
  parseElectionRow(cells) {
    try {
      // 선거 유형 추출 ([대통령선거], [국회의원선거] 등)
      const typeMatch = cells[0]?.match(/\[([^\]]+)\]/);
      if (!typeMatch) return null;
      
      const electionType = typeMatch[1];
      const electionName = cells[0]?.replace(/\[[^\]]+\]/, '').trim();
      const year = cells[1]?.match(/\d{4}/)?.[0];
      
      // 날짜 추출 (YYYY-MM-DD, YYYY.MM.DD, YYYY년 MM월 DD일 등 다양한 형식 지원)
      let electionDate = null;
      for (let i = cells.length - 1; i >= 0; i--) {
        const dateMatch = this.extractDateFromText(cells[i]);
        if (dateMatch) {
          electionDate = dateMatch;
          break;
        }
      }
      
      if (!electionDate && year) {
        // 연도만 있는 경우 추정 날짜 생성
        electionDate = this.estimateElectionDate(electionType, year);
      }
      
      if (!electionDate) return null;
      
      return {
        date: electionDate,
        name: electionName || `${year} ${electionType}`,
        type: this.normalizeElectionType(electionType),
        year: parseInt(year),
        source: 'NEC_SCRAPED',
        scrapedAt: new Date().toISOString()
      };
      
    } catch (error) {
      console.error('❌ 선거 행 파싱 오류:', error.message);
      return null;
    }
  }

  /**
   * 텍스트에서 날짜 추출
   * @param {string} text 
   * @returns {string|null} YYYY-MM-DD 형식
   */
  extractDateFromText(text) {
    if (!text) return null;
    
    // 다양한 날짜 형식 패턴
    const patterns = [
      /(\d{4})-(\d{1,2})-(\d{1,2})/,  // 2028-04-12
      /(\d{4})\.(\d{1,2})\.(\d{1,2})/, // 2028.04.12
      /(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일/, // 2028년 4월 12일
      /(\d{4})\/(\d{1,2})\/(\d{1,2})/, // 2028/04/12
    ];
    
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) {
        const year = match[1];
        const month = match[2].padStart(2, '0');
        const day = match[3].padStart(2, '0');
        return `${year}-${month}-${day}`;
      }
    }
    
    return null;
  }

  /**
   * 선거 유형별 추정 날짜 생성
   * @param {string} electionType 
   * @param {string} year 
   * @returns {string}
   */
  estimateElectionDate(electionType, year) {
    const estimatedDates = {
      '대통령선거': `${year}-03-15`, // 보통 3월 중순
      '국회의원선거': `${year}-04-12`, // 보통 4월 둘째 주
      '지방선거': `${year}-06-03`, // 보통 6월 첫째 주
      '전국동시지방선거': `${year}-06-03`
    };
    
    return estimatedDates[electionType] || `${year}-01-01`;
  }

  /**
   * 선거 유형 정규화
   * @param {string} type 
   * @returns {string}
   */
  normalizeElectionType(type) {
    const typeMap = {
      '대통령선거': 'PRESIDENTIAL',
      '국회의원선거': 'NATIONAL_ASSEMBLY',
      '지방선거': 'LOCAL_GOVERNMENT',
      '전국동시지방선거': 'LOCAL_GOVERNMENT',
      '보궐선거': 'BY_ELECTION',
      '재보궐선거': 'BY_ELECTION'
    };
    
    return typeMap[type] || 'OTHER';
  }

  /**
   * 중복 제거
   * @param {Array} elections 
   * @returns {Array}
   */
  removeDuplicates(elections) {
    const seen = new Set();
    return elections.filter(election => {
      const key = `${election.date}-${election.type}`;
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
  }

  /**
   * 날짜순 정렬
   * @param {Array} elections 
   * @returns {Array}
   */
  sortElectionsByDate(elections) {
    return elections.sort((a, b) => new Date(a.date) - new Date(b.date));
  }

  /**
   * 폴백 데이터 반환 (스크래핑 실패 시)
   * @returns {Array}
   */
  getFallbackElectionData() {
    console.log('📋 폴백 선거일정 데이터 사용');
    return [
      {
        date: '2026-06-03',
        name: '제9회 전국동시지방선거',
        type: 'LOCAL_GOVERNMENT',
        year: 2026,
        source: 'FALLBACK_DATA',
        scrapedAt: new Date().toISOString()
      },
      {
        date: '2028-04-12',
        name: '제23대 국회의원선거',
        type: 'NATIONAL_ASSEMBLY',
        year: 2028,
        source: 'FALLBACK_DATA',
        scrapedAt: new Date().toISOString()
      }
    ];
  }

  /**
   * 캐시 유효성 검사 (24시간)
   * @returns {boolean}
   */
  isCacheValid() {
    if (!this.cache.lastUpdated) return false;
    
    const hoursSinceUpdate = (new Date() - this.cache.lastUpdated) / (1000 * 60 * 60);
    return hoursSinceUpdate < 24;
  }

  /**
   * 캐시된 데이터 반환 (유효한 경우)
   * @returns {Array|null}
   */
  getCachedElections() {
    return this.isCacheValid() ? this.cache.elections : null;
  }
}

// 싱글톤 인스턴스
const necScraper = new NECElectionScraper();

module.exports = {
  NECElectionScraper,
  necScraper
};