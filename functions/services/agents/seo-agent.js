'use strict';

/**
 * SEO Agent - 네이버 검색 최적화
 *
 * 역할:
 * - 네이버 SEO 최적화 적용
 * - 제목 최적화
 * - 메타 태그 생성
 * - 키워드 밀도 조정
 */

const { BaseAgent } = require('./base');

class SEOAgent extends BaseAgent {
  constructor() {
    super('SEOAgent');
  }

  getRequiredContext() {
    return ['previousResults'];
  }

  async execute(context) {
    const { previousResults = {}, userProfile = {} } = context;

    // Compliance Agent 결과에서 콘텐츠 가져오기
    const complianceResult = previousResults.ComplianceAgent;
    const keywordResult = previousResults.KeywordAgent;

    if (!complianceResult?.success || !complianceResult?.data?.content) {
      throw new Error('Compliance Agent 결과가 없습니다');
    }

    let content = complianceResult.data.content;
    const keywords = keywordResult?.data?.keywords || [];
    const primaryKeyword = keywordResult?.data?.primary || '';

    // 1. 제목 최적화 (60자 이내)
    const title = this.optimizeTitle(content, primaryKeyword, userProfile);

    // 2. 메타 설명 생성 (160자 이내)
    const metaDescription = this.generateMetaDescription(content, keywords);

    // 3. 본문 SEO 최적화
    const optimizedContent = this.optimizeContent(content, keywords);

    // 4. 키워드 밀도 분석
    const keywordDensity = this.analyzeKeywordDensity(optimizedContent, keywords);

    // 5. SEO 점수 계산
    const seoScore = this.calculateSEOScore({
      titleLength: title.length,
      hasKeywordInTitle: title.includes(primaryKeyword),
      metaLength: metaDescription.length,
      keywordDensity,
      contentLength: optimizedContent.replace(/<[^>]*>/g, '').length
    });

    return {
      title,
      metaDescription,
      content: optimizedContent,
      keywords: keywords.slice(0, 5).map(k => k.keyword || k),
      seoScore,
      suggestions: this.getSuggestions(seoScore, keywordDensity)
    };
  }

  optimizeTitle(content, primaryKeyword, userProfile) {
    // 콘텐츠에서 첫 문장 또는 핵심 구문 추출
    const firstLine = content.split(/[.!?]\s/)[0] || '';
    const cleanFirstLine = firstLine.replace(/<[^>]*>/g, '').trim();

    // 지역명 포함
    const region = userProfile?.regionLocal || userProfile?.regionMetro || '';

    // 제목 조합
    let title = '';

    if (primaryKeyword && cleanFirstLine.includes(primaryKeyword)) {
      // 이미 키워드가 포함된 경우
      title = cleanFirstLine.substring(0, 55);
    } else if (primaryKeyword) {
      // 키워드 + 지역 조합
      title = region
        ? `${region} ${primaryKeyword} - ${cleanFirstLine.substring(0, 30)}`
        : `${primaryKeyword} - ${cleanFirstLine.substring(0, 40)}`;
    } else {
      title = cleanFirstLine.substring(0, 55);
    }

    // 60자 제한
    if (title.length > 60) {
      title = title.substring(0, 57) + '...';
    }

    return title;
  }

  generateMetaDescription(content, keywords) {
    // HTML 태그 제거
    const plainText = content.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

    // 첫 2-3문장 추출
    const sentences = plainText.split(/[.!?]\s+/).filter(s => s.length > 10);
    let description = sentences.slice(0, 2).join('. ');

    // 160자 제한
    if (description.length > 160) {
      description = description.substring(0, 157) + '...';
    }

    return description;
  }

  optimizeContent(content, keywords) {
    let optimized = content;

    // 1. 첫 문단에 주요 키워드 강조 (이미 있으면 스킵)
    const primaryKeyword = keywords[0]?.keyword || keywords[0];
    if (primaryKeyword && !optimized.substring(0, 200).includes(primaryKeyword)) {
      // 자연스럽게 키워드 삽입은 복잡하므로 현재는 스킵
    }

    // 2. 소제목에 H2, H3 태그 적용 (이미 적용되어 있으면 스킵)
    if (!optimized.includes('<h2>') && !optimized.includes('<h3>')) {
      // 줄바꿈 후 짧은 문장을 소제목으로 변환
      optimized = optimized.replace(
        /\n\n([^\n]{5,30})\n\n/g,
        '\n\n<h3>$1</h3>\n\n'
      );
    }

    // 3. 문단 구분 최적화
    optimized = optimized.replace(/\n{3,}/g, '\n\n');

    return optimized;
  }

  analyzeKeywordDensity(content, keywords) {
    const plainText = content.replace(/<[^>]*>/g, ' ').toLowerCase();
    const wordCount = plainText.split(/\s+/).length;

    const density = {};
    for (const kw of keywords.slice(0, 5)) {
      const keyword = (kw.keyword || kw).toLowerCase();
      const regex = new RegExp(keyword, 'gi');
      const matches = plainText.match(regex);
      const count = matches ? matches.length : 0;
      density[keyword] = {
        count,
        percentage: ((count / wordCount) * 100).toFixed(2)
      };
    }

    return density;
  }

  calculateSEOScore(factors) {
    let score = 0;

    // 제목 길이 (30-60자 최적)
    if (factors.titleLength >= 30 && factors.titleLength <= 60) {
      score += 20;
    } else if (factors.titleLength >= 20 && factors.titleLength <= 70) {
      score += 10;
    }

    // 제목에 키워드 포함
    if (factors.hasKeywordInTitle) {
      score += 20;
    }

    // 메타 설명 길이 (100-160자 최적)
    if (factors.metaLength >= 100 && factors.metaLength <= 160) {
      score += 20;
    } else if (factors.metaLength >= 50) {
      score += 10;
    }

    // 콘텐츠 길이 (1000자 이상)
    if (factors.contentLength >= 1500) {
      score += 20;
    } else if (factors.contentLength >= 1000) {
      score += 15;
    } else if (factors.contentLength >= 500) {
      score += 10;
    }

    // 키워드 밀도 (0.5-2% 최적)
    const densities = Object.values(factors.keywordDensity);
    const avgDensity = densities.length > 0
      ? densities.reduce((sum, d) => sum + parseFloat(d.percentage), 0) / densities.length
      : 0;

    if (avgDensity >= 0.5 && avgDensity <= 2) {
      score += 20;
    } else if (avgDensity > 0 && avgDensity < 3) {
      score += 10;
    }

    return Math.min(100, score);
  }

  getSuggestions(seoScore, keywordDensity) {
    const suggestions = [];

    if (seoScore < 60) {
      suggestions.push('SEO 점수가 낮습니다. 제목과 본문에 핵심 키워드를 더 포함시키세요.');
    }

    const densities = Object.entries(keywordDensity);
    for (const [keyword, data] of densities) {
      if (parseFloat(data.percentage) < 0.3) {
        suggestions.push(`"${keyword}" 키워드 사용 빈도가 낮습니다.`);
      } else if (parseFloat(data.percentage) > 3) {
        suggestions.push(`"${keyword}" 키워드가 과도하게 사용되었습니다.`);
      }
    }

    return suggestions;
  }
}

module.exports = { SEOAgent };
