/**
 * functions/services/news-fetcher.js
 * 네이버 뉴스 크롤링 서비스
 * 최신 뉴스를 가져와서 원고 생성 시 구체적인 컨텍스트 제공
 */

'use strict';

const axios = require('axios');
const cheerio = require('cheerio');
const NodeCache = require('node-cache');
const { callGenerativeModel } = require('./gemini');

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
 * AI로 뉴스를 핵심만 압축 (토큰 절감)
 * @param {Array} news - 뉴스 목록
 * @returns {Promise<Object>} 압축된 뉴스 정보
 */
async function compressNewsWithAI(news) {
  if (!news || news.length === 0) {
    return null;
  }

  const cacheKey = `compressed:${JSON.stringify(news.map(n => n.title))}`;
  if (cache.has(cacheKey)) {
    console.log('✅ 캐시에서 압축 뉴스 반환');
    return cache.get(cacheKey);
  }

  const combined = news.map(n =>
    `${n.title}${n.summary ? `. ${n.summary}` : ''}`
  ).join('\n\n');

  const prompt = `다음 뉴스를 핵심만 100자 이내로 요약하세요:

${combined}

출력 형식 (반드시 JSON):
{
  "summary": "핵심 요약 (100자 이내)",
  "keyPoints": ["포인트1", "포인트2", "포인트3"]
}`;

  try {
    const result = await callGenerativeModel(prompt, 1, 'gemini-2.5-flash');

    // JSON 추출
    const jsonMatch = result.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0]);
      const compressed = {
        summary: parsed.summary,
        keyPoints: parsed.keyPoints || [],
        sources: news.map(n => n.link)
      };

      cache.set(cacheKey, compressed);
      console.log('✅ 뉴스 AI 압축 완료:', compressed.summary.substring(0, 50) + '...');
      return compressed;
    }
  } catch (error) {
    console.error('❌ 뉴스 압축 실패:', error.message);
  }

  // 폴백: 첫 번째 뉴스 제목만 사용
  return {
    summary: news[0]?.title || '',
    keyPoints: news.slice(0, 3).map(n => n.title),
    sources: news.map(n => n.link)
  };
}

/**
 * 뉴스 컨텍스트를 프롬프트용 텍스트로 변환
 * @param {Array|Object} news - 뉴스 목록 또는 압축된 뉴스
 * @returns {string} 프롬프트에 삽입할 텍스트
 */
function formatNewsForPrompt(news) {
  if (!news) {
    return '';
  }

  // 압축된 뉴스 형식인 경우
  if (news.summary && news.keyPoints) {
    return `
[📰 뉴스 핵심]
${news.summary}

주요 포인트:
${news.keyPoints.map((p, i) => `${i + 1}. ${p}`).join('\n')}

출처: ${news.sources?.slice(0, 2).join(', ') || '네이버 뉴스'}

---
`;
  }

  // 기존 형식 (배열)
  if (Array.isArray(news) && news.length > 0) {
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

  return '';
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
  compressNewsWithAI,
  formatNewsForPrompt,
  shouldFetchNews
};
