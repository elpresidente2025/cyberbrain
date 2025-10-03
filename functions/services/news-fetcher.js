/**
 * functions/services/news-fetcher.js
 * 네이버 뉴스 크롤링 서비스
 * 최신 뉴스를 가져와서 원고 생성 시 구체적인 컨텍스트 제공
 */

'use strict';

const axios = require('axios');
const cheerio = require('cheerio');
const NodeCache = require('node-cache');

// 캐시 설정 (10분 TTL)
const cache = new NodeCache({ stdTTL: 600 });

/**
 * 네이버 뉴스 검색
 * @param {string} topic - 검색 키워드
 * @param {number} limit - 가져올 뉴스 개수 (기본 3개)
 * @returns {Promise<Array>} 뉴스 목록
 */
async function fetchNaverNews(topic, limit = 3) {
  if (!topic || topic.trim() === '') {
    return [];
  }

  const cacheKey = `news:${topic}:${limit}`;

  // 캐시 확인
  if (cache.has(cacheKey)) {
    console.log('✅ 캐시에서 뉴스 반환:', topic);
    return cache.get(cacheKey);
  }

  try {
    const url = `https://search.naver.com/search.naver?where=news&query=${encodeURIComponent(topic)}&sort=date`;

    console.log('🔍 네이버 뉴스 검색:', topic);

    const { data } = await axios.get(url, {
      timeout: 5000,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
      }
    });

    const $ = cheerio.load(data);
    const news = [];

    // 네이버 뉴스 검색 결과 파싱
    $('.news_area').slice(0, limit).each((i, el) => {
      const $el = $(el);
      const title = $el.find('.news_tit').attr('title') || $el.find('.news_tit').text().trim();
      const link = $el.find('.news_tit').attr('href');
      const summary = $el.find('.news_dsc').text().trim();
      const press = $el.find('.info.press').text().trim();
      const date = $el.find('.info').last().text().trim();

      if (title) {
        news.push({
          title,
          summary,
          press,
          date,
          link
        });
      }
    });

    console.log(`✅ 뉴스 ${news.length}개 수집 완료:`, topic);

    // 캐시 저장
    cache.set(cacheKey, news);

    return news;

  } catch (error) {
    console.error('❌ 네이버 뉴스 조회 실패:', error.message);

    // 네트워크 오류 등으로 실패해도 원고 생성은 계속 진행
    return [];
  }
}

/**
 * 뉴스 컨텍스트를 프롬프트용 텍스트로 변환
 * @param {Array} news - 뉴스 목록
 * @returns {string} 프롬프트에 삽입할 텍스트
 */
function formatNewsForPrompt(news) {
  if (!news || news.length === 0) {
    return '';
  }

  const newsText = news.map((item, idx) => {
    return `${idx + 1}. ${item.title}${item.date ? ` (${item.date})` : ''}${item.summary ? `\n   요약: ${item.summary}` : ''}`;
  }).join('\n\n');

  return `
[📰 최신 뉴스 정보]
아래는 실제 최신 뉴스입니다. 이 정보를 참고하여 구체적이고 사실 기반의 원고를 작성하세요.

${newsText}

---
`;
}

/**
 * 카테고리별로 뉴스가 필요한지 판단
 * @param {string} category - 글 카테고리
 * @returns {boolean} 뉴스 필요 여부
 */
function shouldFetchNews(category) {
  const needsNews = [
    '시사비평',
    '정책제안',
    '의정활동',
    '지역현안'
  ];

  return needsNews.includes(category);
}

module.exports = {
  fetchNaverNews,
  formatNewsForPrompt,
  shouldFetchNews
};
