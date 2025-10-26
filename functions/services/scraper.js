/**
 * services/scraper.js
 * 비용 효율적인 웹 스크래퍼 모듈
 * - 기본: axios + cheerio (빠르고 저렴)
 * - 폴백: puppeteer (동적 콘텐츠 대응)
 */

'use strict';

const axios = require('axios');
const cheerio = require('cheerio');

/**
 * 네이버 자동완성 키워드 가져오기
 * @param {string} keyword - 검색할 키워드
 * @returns {Promise<Array<string>>} 추천 키워드 배열
 */
async function getNaverSuggestions(keyword) {
  try {
    console.log(`🔍 [Scraper] 네이버 자동완성 검색: ${keyword}`);

    // 1차: axios로 네이버 자동완성 API 호출
    const suggestions = await getNaverAutocomplete(keyword);

    if (suggestions && suggestions.length > 0) {
      console.log(`✅ [Scraper] 자동완성 ${suggestions.length}개 발견`);
      return suggestions;
    }

    // 2차: 검색 결과 페이지에서 연관 검색어 추출
    console.log(`🔄 [Scraper] 검색 결과 페이지에서 연관 검색어 추출 시도`);
    const relatedKeywords = await getRelatedKeywordsFromSearchPage(keyword);

    if (relatedKeywords && relatedKeywords.length > 0) {
      console.log(`✅ [Scraper] 연관 검색어 ${relatedKeywords.length}개 발견`);
      return relatedKeywords;
    }

    // 3차: Puppeteer 폴백 (동적 콘텐츠)
    console.log(`⚠️ [Scraper] axios/cheerio 실패, Puppeteer 폴백 시도`);
    return await getKeywordsWithPuppeteer(keyword);

  } catch (error) {
    console.error(`❌ [Scraper] 스크래핑 실패:`, error.message);

    // 최후의 수단: Puppeteer 시도
    try {
      console.log(`🔄 [Scraper] 에러 발생, Puppeteer로 재시도`);
      return await getKeywordsWithPuppeteer(keyword);
    } catch (puppeteerError) {
      console.error(`❌ [Scraper] Puppeteer도 실패:`, puppeteerError.message);
      return [keyword]; // 최소한 원본 키워드라도 반환
    }
  }
}

/**
 * 네이버 자동완성 API 호출
 * @param {string} keyword - 검색 키워드
 * @returns {Promise<Array<string>>} 자동완성 키워드 배열
 */
async function getNaverAutocomplete(keyword) {
  try {
    const url = 'https://ac.search.naver.com/nx/ac';
    const params = {
      q: keyword,
      con: 1,
      frm: 'nv',
      ans: 2,
      r_format: 'json',
      r_enc: 'UTF-8',
      r_unicode: 0,
      t_koreng: 1,
      run: 2,
      rev: 4,
      q_enc: 'UTF-8',
      st: 100
    };

    const response = await axios.get(url, {
      params,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Referer': 'https://www.naver.com/'
      },
      timeout: 10000
    });

    if (response.data && response.data.items) {
      // items 배열의 첫 번째 요소가 자동완성 결과
      const suggestions = response.data.items[0] || [];
      return suggestions
        .map(item => item[0]) // 각 항목의 첫 번째 요소가 키워드
        .filter(k => k && k.trim().length > 0)
        .slice(0, 15); // 최대 15개
    }

    return [];
  } catch (error) {
    console.error(`❌ [Scraper] 자동완성 API 호출 실패:`, error.message);
    return [];
  }
}

/**
 * 검색 결과 페이지에서 연관 검색어 추출
 * @param {string} keyword - 검색 키워드
 * @returns {Promise<Array<string>>} 연관 검색어 배열
 */
async function getRelatedKeywordsFromSearchPage(keyword) {
  try {
    const url = `https://search.naver.com/search.naver?query=${encodeURIComponent(keyword)}`;

    const response = await axios.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
      },
      timeout: 15000
    });

    const $ = cheerio.load(response.data);
    const relatedKeywords = [];

    // 연관 검색어 영역 탐색
    $('.related_srch .keyword').each((i, elem) => {
      const text = $(elem).text().trim();
      if (text && text.length > 0) {
        relatedKeywords.push(text);
      }
    });

    // 다른 방식으로도 시도
    if (relatedKeywords.length === 0) {
      $('a.related_keyword').each((i, elem) => {
        const text = $(elem).text().trim();
        if (text && text.length > 0) {
          relatedKeywords.push(text);
        }
      });
    }

    return [...new Set(relatedKeywords)].slice(0, 15);
  } catch (error) {
    console.error(`❌ [Scraper] 검색 페이지 파싱 실패:`, error.message);
    return [];
  }
}

/**
 * Puppeteer를 이용한 동적 스크래핑 (폴백)
 * @param {string} keyword - 검색 키워드
 * @returns {Promise<Array<string>>} 키워드 배열
 */
async function getKeywordsWithPuppeteer(keyword) {
  let browser = null;

  try {
    // Puppeteer는 선택적 의존성으로 처리
    const puppeteer = require('puppeteer');

    console.log(`🚀 [Scraper] Puppeteer 브라우저 시작`);

    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage();
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36');

    // 네이버 검색 페이지 접속
    const url = `https://search.naver.com/search.naver?query=${encodeURIComponent(keyword)}`;
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });

    // 연관 검색어 추출
    const relatedKeywords = await page.evaluate(() => {
      const keywords = [];

      // 여러 선택자 시도
      const selectors = [
        '.related_srch .keyword',
        'a.related_keyword',
        '.lst_related_srch a'
      ];

      for (const selector of selectors) {
        const elements = document.querySelectorAll(selector);
        elements.forEach(el => {
          const text = el.textContent.trim();
          if (text && text.length > 0) {
            keywords.push(text);
          }
        });

        if (keywords.length > 0) break;
      }

      return [...new Set(keywords)];
    });

    await browser.close();
    console.log(`✅ [Scraper] Puppeteer로 ${relatedKeywords.length}개 키워드 수집`);

    return relatedKeywords.slice(0, 15);

  } catch (error) {
    console.error(`❌ [Scraper] Puppeteer 실행 실패:`, error.message);
    if (browser) {
      await browser.close();
    }
    return [keyword]; // 최소한 원본 키워드 반환
  }
}

/**
 * 네이버 검색 결과 페이지 분석 (SERP)
 * @param {string} keyword - 검색 키워드
 * @returns {Promise<Object>} SERP 분석 결과
 */
async function analyzeNaverSERP(keyword) {
  try {
    console.log(`📊 [Scraper] SERP 분석 시작: ${keyword}`);

    const url = `https://search.naver.com/search.naver?query=${encodeURIComponent(keyword)}`;

    const response = await axios.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html'
      },
      timeout: 15000
    });

    const $ = cheerio.load(response.data);
    const results = [];

    // 통합검색 결과 추출
    $('.total_wrap, .api_subject_bx').each((i, elem) => {
      if (i >= 5) return false; // 상위 5개만

      const $elem = $(elem);
      const title = $elem.find('.total_tit, .api_txt_lines').text().trim();
      const url = $elem.find('a').attr('href');
      const snippet = $elem.find('.total_txt, .api_txt_lines').text().trim();

      if (title && url) {
        results.push({
          title,
          url,
          snippet: snippet.substring(0, 150)
        });
      }
    });

    // 블로그 결과도 시도
    if (results.length < 5) {
      $('.sh_blog_top').each((i, elem) => {
        if (results.length >= 5) return false;

        const $elem = $(elem);
        const title = $elem.find('.sh_blog_title').text().trim();
        const url = $elem.find('.sh_blog_title').attr('href');
        const snippet = $elem.find('.sh_blog_passage').text().trim();

        if (title && url) {
          results.push({
            title,
            url,
            snippet: snippet.substring(0, 150)
          });
        }
      });
    }

    // 결과 분석
    const blogCount = results.filter(r =>
      r.url.includes('blog.naver.com') ||
      r.url.includes('tistory.com')
    ).length;

    const officialCount = results.filter(r =>
      r.url.includes('.go.kr') ||
      r.url.includes('.or.kr') ||
      r.url.includes('news.naver.com')
    ).length;

    console.log(`✅ [Scraper] SERP 분석 완료: 총 ${results.length}개, 블로그 ${blogCount}개, 공식 ${officialCount}개`);

    return {
      results: results.slice(0, 5),
      blogCount,
      officialCount,
      totalResults: results.length
    };

  } catch (error) {
    console.error(`❌ [Scraper] SERP 분석 실패:`, error.message);
    return {
      results: [],
      blogCount: 0,
      officialCount: 0,
      totalResults: 0
    };
  }
}

/**
 * 검색 결과 수 추정
 * @param {string} keyword - 검색 키워드
 * @returns {Promise<number>} 예상 검색 결과 수
 */
async function getSearchResultCount(keyword) {
  try {
    const url = `https://search.naver.com/search.naver?query=${encodeURIComponent(keyword)}`;

    const response = await axios.get(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      },
      timeout: 10000
    });

    const $ = cheerio.load(response.data);

    // 검색 결과 수 텍스트 추출 시도
    const resultText = $('.title_desc').text();
    const match = resultText.match(/(\d+(?:,\d+)*)/);

    if (match) {
      const count = parseInt(match[1].replace(/,/g, ''));
      console.log(`📊 [Scraper] "${keyword}" 검색 결과 약 ${count.toLocaleString()}개`);
      return count;
    }

    // 기본값: 결과가 있으면 1000, 없으면 0
    return $('.total_wrap, .api_subject_bx').length > 0 ? 1000 : 0;

  } catch (error) {
    console.error(`❌ [Scraper] 검색 결과 수 조회 실패:`, error.message);
    return 1000; // 기본값
  }
}

module.exports = {
  getNaverSuggestions,
  analyzeNaverSERP,
  getSearchResultCount
};
