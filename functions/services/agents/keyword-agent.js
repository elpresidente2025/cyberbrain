'use strict';

/**
 * Keyword Agent - 키워드 분석 및 추천
 *
 * 역할:
 * - 주제에서 핵심 키워드 추출
 * - SEO 최적화 키워드 추천
 * - 사용자 메모리 기반 선호 키워드 반영
 */

const { BaseAgent } = require('./base');
const { GoogleGenerativeAI } = require('@google/generative-ai');

let genAI = null;
function getGenAI() {
  if (!genAI) {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) return null;
    genAI = new GoogleGenerativeAI(apiKey);
  }
  return genAI;
}

class KeywordAgent extends BaseAgent {
  constructor() {
    super('KeywordAgent');
  }

  getRequiredContext() {
    return ['topic', 'category'];
  }

  async execute(context) {
    const { topic, category, userProfile, memoryContext } = context;

    // 기본 키워드 추출 (주제에서)
    const baseKeywords = this.extractBaseKeywords(topic);

    // 지역 키워드 추가
    const regionKeywords = this.getRegionKeywords(userProfile);

    // 카테고리별 추천 키워드
    const categoryKeywords = this.getCategoryKeywords(category);

    // 메모리 기반 선호 키워드
    const preferredKeywords = this.extractPreferredKeywords(memoryContext);

    // 키워드 통합 및 우선순위 정렬
    const allKeywords = this.mergeAndRank([
      ...baseKeywords.map(k => ({ keyword: k, weight: 1.0, source: 'topic' })),
      ...regionKeywords.map(k => ({ keyword: k, weight: 0.8, source: 'region' })),
      ...categoryKeywords.map(k => ({ keyword: k, weight: 0.6, source: 'category' })),
      ...preferredKeywords.map(k => ({ keyword: k, weight: 0.7, source: 'memory' }))
    ]);

    return {
      keywords: allKeywords.slice(0, 10),
      primary: allKeywords[0]?.keyword || topic,
      secondary: allKeywords.slice(1, 4).map(k => k.keyword),
      forSEO: allKeywords.filter(k => k.source !== 'memory').slice(0, 5).map(k => k.keyword)
    };
  }

  extractBaseKeywords(topic) {
    if (!topic) return [];

    // 불용어 제거 및 키워드 추출
    const stopWords = ['의', '에', '를', '이', '가', '은', '는', '과', '와', '에서', '으로', '하는', '대한', '관한'];
    const words = topic.split(/\s+/)
      .filter(w => w.length >= 2)
      .filter(w => !stopWords.includes(w));

    return [...new Set(words)];
  }

  getRegionKeywords(userProfile) {
    if (!userProfile) return [];

    const keywords = [];
    if (userProfile.regionMetro) keywords.push(userProfile.regionMetro);
    if (userProfile.regionLocal) keywords.push(userProfile.regionLocal);
    if (userProfile.electoralDistrict) keywords.push(userProfile.electoralDistrict);

    return keywords.filter(k => k);
  }

  getCategoryKeywords(category) {
    const categoryMap = {
      'daily-communication': ['소통', '일상', '주민'],
      'policy-proposal': ['정책', '제안', '개선'],
      'activity-report': ['활동', '성과', '의정'],
      'local-issues': ['지역', '현안', '해결'],
      'current-affairs': ['시사', '이슈', '논평']
    };

    return categoryMap[category] || [];
  }

  extractPreferredKeywords(memoryContext) {
    if (!memoryContext) return [];

    // 메모리 컨텍스트에서 키워드 추출
    const match = memoryContext.match(/자주 사용하는 키워드:\s*([^[\]]+)/);
    if (match) {
      return match[1].split(',').map(k => k.trim()).filter(k => k);
    }

    return [];
  }

  mergeAndRank(keywordItems) {
    // 중복 제거 및 가중치 합산
    const keywordMap = new Map();

    for (const item of keywordItems) {
      const existing = keywordMap.get(item.keyword);
      if (existing) {
        existing.weight += item.weight;
        existing.sources.push(item.source);
      } else {
        keywordMap.set(item.keyword, {
          keyword: item.keyword,
          weight: item.weight,
          sources: [item.source]
        });
      }
    }

    // 가중치순 정렬
    return Array.from(keywordMap.values())
      .sort((a, b) => b.weight - a.weight);
  }
}

module.exports = { KeywordAgent };
