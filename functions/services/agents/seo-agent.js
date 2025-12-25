'use strict';

/**
 * SEO Agent - 네이버 검색 최적화 (통합 리팩토링 버전)
 *
 * 역할:
 * - 네이버 SEO 최적화 적용
 * - 제목 최적화 (60자 이내)
 * - 메타 설명 생성
 * - 키워드 밀도 분석 및 조정
 *
 * prompts/guidelines의 SEO 규칙들을 import하여 사용
 */

const { BaseAgent } = require('./base');

// ✅ 기존 guidelines import
const { SEO_RULES, FORMAT_RULES, CONTENT_RULES } = require('../../prompts/guidelines/editorial');
const { calculateMinInsertions, calculateDistribution } = require('../../prompts/guidelines/seo');

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
    const writerResult = previousResults.WriterAgent;

    if (!complianceResult?.success || !complianceResult?.data?.content) {
      throw new Error('Compliance Agent 결과가 없습니다');
    }

    let content = complianceResult.data.content;
    const keywords = keywordResult?.data?.keywords || [];
    const primaryKeyword = keywordResult?.data?.primary || (keywords[0]?.keyword || keywords[0] || '');
    const writerTitle = writerResult?.data?.title || null;

    // 1. 제목 최적화 (60자 이내, 키워드 포함)
    const title = this.optimizeTitle(content, primaryKeyword, userProfile, writerTitle);

    // 2. 메타 설명 생성 (160자 이내)
    const metaDescription = this.generateMetaDescription(content, keywords);

    // 3. 본문 SEO 최적화
    const optimizedContent = this.optimizeContent(content, keywords);

    // 4. 키워드 밀도 분석
    const keywordDensity = this.analyzeKeywordDensity(optimizedContent, keywords);

    // 5. 구조 분석
    const structureAnalysis = this.analyzeStructure(optimizedContent);

    // 6. SEO 점수 계산
    const seoScore = this.calculateSEOScore({
      titleLength: title.length,
      hasKeywordInTitle: primaryKeyword ? title.includes(primaryKeyword) : false,
      metaLength: metaDescription.length,
      keywordDensity,
      contentLength: optimizedContent.replace(/<[^>]*>/g, '').length,
      structure: structureAnalysis
    });

    // 7. 개선 제안 생성
    const suggestions = this.generateSuggestions(seoScore, keywordDensity, structureAnalysis);

    console.log(`🔍 [SEOAgent] 최적화 완료`, {
      titleLength: title.length,
      contentLength: optimizedContent.replace(/<[^>]*>/g, '').length,
      seoScore,
      keywordCount: keywords.length
    });

    return {
      title,
      metaDescription,
      content: optimizedContent,
      keywords: keywords.slice(0, 5).map(k => k.keyword || k),
      seoScore,
      suggestions,
      analysis: {
        keywordDensity,
        structure: structureAnalysis
      }
    };
  }

  /**
   * 제목 최적화 (SEO_RULES 기반)
   */
  optimizeTitle(content, primaryKeyword, userProfile, existingTitle) {
    // 이미 좋은 제목이 있으면 길이만 체크
    if (existingTitle && existingTitle.length >= 15 && existingTitle.length <= 60) {
      // 키워드 포함 여부 확인
      if (!primaryKeyword || existingTitle.includes(primaryKeyword)) {
        return existingTitle;
      }
    }

    // 콘텐츠에서 첫 문장 추출
    const firstLine = content.split(/[.!?]\s/)[0] || '';
    const cleanFirstLine = firstLine.replace(/<[^>]*>/g, '').trim();

    // 지역명 추출
    const region = userProfile?.regionLocal || userProfile?.regionMetro || '';

    // 제목 생성
    let title = '';

    if (existingTitle && existingTitle.length > 5) {
      // 기존 제목 활용
      title = existingTitle;
    } else if (primaryKeyword && cleanFirstLine.includes(primaryKeyword)) {
      // 이미 키워드가 포함된 경우
      title = cleanFirstLine.substring(0, 55);
    } else if (primaryKeyword) {
      // 키워드 + 지역 조합
      if (region) {
        title = `${region} ${primaryKeyword} - ${cleanFirstLine.substring(0, 30)}`;
      } else {
        title = `${primaryKeyword} - ${cleanFirstLine.substring(0, 40)}`;
      }
    } else {
      title = cleanFirstLine.substring(0, 55);
    }

    // 60자 제한 (SEO_RULES 기반)
    const maxTitleLength = 60;
    if (title.length > maxTitleLength) {
      title = title.substring(0, maxTitleLength - 3) + '...';
    }

    return title;
  }

  /**
   * 메타 설명 생성
   */
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

  /**
   * 본문 SEO 최적화
   */
  optimizeContent(content, keywords) {
    let optimized = content;

    // 1. 소제목 태그 최적화 (이미 있으면 스킵)
    if (!optimized.includes('<h2>') && !optimized.includes('<h3>')) {
      // 줄바꿈 후 짧은 문장을 소제목으로 변환
      optimized = optimized.replace(
        /\n\n([^\n<]{5,40})\n\n/g,
        '\n\n<h3>$1</h3>\n\n'
      );
    }

    // 2. 문단 구분 최적화 (과도한 줄바꿈 정리)
    optimized = optimized.replace(/\n{3,}/g, '\n\n');

    // 3. 빈 태그 정리
    optimized = optimized.replace(/<p>\s*<\/p>/gi, '');
    optimized = optimized.replace(/<h[2-4]>\s*<\/h[2-4]>/gi, '');

    return optimized;
  }

  /**
   * 키워드 밀도 분석 (SEO_RULES.keywordPlacement.density 기준)
   */
  analyzeKeywordDensity(content, keywords) {
    const plainText = content.replace(/<[^>]*>/g, ' ').toLowerCase();
    const wordCount = plainText.split(/\s+/).length;
    const charCount = plainText.replace(/\s/g, '').length;

    const density = {};
    const optimalDensity = SEO_RULES.keywordPlacement.density;

    for (const kw of keywords.slice(0, 5)) {
      const keyword = (kw.keyword || kw).toLowerCase();
      const regex = new RegExp(keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      const matches = plainText.match(regex);
      const count = matches ? matches.length : 0;
      const percentage = ((count / wordCount) * 100);

      density[keyword] = {
        count,
        percentage: percentage.toFixed(2),
        status: this.getDensityStatus(percentage, optimalDensity)
      };
    }

    return density;
  }

  /**
   * 키워드 밀도 상태 판단
   */
  getDensityStatus(percentage, rules) {
    const optimal = parseFloat(rules.optimal.split('-')[0]); // 1.5
    const max = parseFloat(rules.maximum); // 3

    if (percentage < 0.3) return 'too_low';
    if (percentage >= optimal && percentage <= max) return 'optimal';
    if (percentage > max) return 'too_high';
    return 'acceptable';
  }

  /**
   * 구조 분석 (SEO_RULES.structure 기준)
   */
  analyzeStructure(content) {
    const structureRules = SEO_RULES.structure;

    // 태그 카운트
    const h2Count = (content.match(/<h2>/gi) || []).length;
    const h3Count = (content.match(/<h3>/gi) || []).length;
    const pCount = (content.match(/<p>/gi) || []).length;
    const listCount = (content.match(/<ul>|<ol>/gi) || []).length;

    // 글자수
    const charCount = content.replace(/<[^>]*>/g, '').replace(/\s/g, '').length;

    return {
      headings: {
        h2: { count: h2Count, optimal: structureRules.headings.h2.count },
        h3: { count: h3Count, optimal: structureRules.headings.h3.count }
      },
      paragraphs: {
        count: pCount,
        optimal: structureRules.paragraphs.count
      },
      lists: listCount,
      charCount,
      wordCountRange: {
        min: SEO_RULES.wordCount.min,
        max: SEO_RULES.wordCount.max,
        current: charCount,
        inRange: charCount >= SEO_RULES.wordCount.min && charCount <= SEO_RULES.wordCount.max
      }
    };
  }

  /**
   * SEO 점수 계산 (100점 만점)
   */
  calculateSEOScore(factors) {
    let score = 0;

    // 1. 제목 점수 (25점)
    // - 길이 30-60자: 15점
    // - 키워드 포함: 10점
    if (factors.titleLength >= 30 && factors.titleLength <= 60) {
      score += 15;
    } else if (factors.titleLength >= 20 && factors.titleLength <= 70) {
      score += 8;
    }

    if (factors.hasKeywordInTitle) {
      score += 10;
    }

    // 2. 메타 설명 점수 (15점)
    if (factors.metaLength >= 100 && factors.metaLength <= 160) {
      score += 15;
    } else if (factors.metaLength >= 50) {
      score += 8;
    }

    // 3. 콘텐츠 길이 점수 (20점)
    const { min, max } = SEO_RULES.wordCount;
    if (factors.contentLength >= min && factors.contentLength <= max) {
      score += 20;
    } else if (factors.contentLength >= min * 0.8 && factors.contentLength <= max * 1.2) {
      score += 12;
    } else if (factors.contentLength >= 500) {
      score += 5;
    }

    // 4. 키워드 밀도 점수 (25점)
    const densities = Object.values(factors.keywordDensity);
    if (densities.length > 0) {
      const optimalCount = densities.filter(d => d.status === 'optimal').length;
      const acceptableCount = densities.filter(d => d.status === 'acceptable').length;
      const tooHighCount = densities.filter(d => d.status === 'too_high').length;

      score += Math.min(25, (optimalCount * 10) + (acceptableCount * 5) - (tooHighCount * 5));
    } else {
      score += 10; // 키워드 없으면 기본 점수
    }

    // 5. 구조 점수 (15점)
    const structure = factors.structure;
    if (structure) {
      // 소제목 사용
      if (structure.headings.h2.count >= 1 || structure.headings.h3.count >= 2) {
        score += 8;
      }
      // 적절한 문단 수
      if (structure.paragraphs.count >= 5 && structure.paragraphs.count <= 10) {
        score += 7;
      } else if (structure.paragraphs.count >= 3) {
        score += 4;
      }
    }

    return Math.min(100, Math.max(0, score));
  }

  /**
   * 개선 제안 생성
   */
  generateSuggestions(seoScore, keywordDensity, structure) {
    const suggestions = [];

    // 점수 기반 제안
    if (seoScore < 50) {
      suggestions.push({
        priority: 'high',
        message: 'SEO 점수가 낮습니다. 키워드 배치와 구조를 개선하세요.'
      });
    }

    // 키워드 밀도 제안
    for (const [keyword, data] of Object.entries(keywordDensity)) {
      if (data.status === 'too_low') {
        suggestions.push({
          priority: 'medium',
          message: `"${keyword}" 키워드 사용 빈도가 낮습니다. (${data.count}회)`
        });
      } else if (data.status === 'too_high') {
        suggestions.push({
          priority: 'high',
          message: `"${keyword}" 키워드가 과도하게 사용되었습니다. (${data.percentage}%) - 스팸으로 분류될 수 있습니다.`
        });
      }
    }

    // 구조 제안
    if (structure) {
      if (!structure.wordCountRange.inRange) {
        const { current, min, max } = structure.wordCountRange;
        if (current < min) {
          suggestions.push({
            priority: 'high',
            message: `글자수가 부족합니다. (${current}자 / 최소 ${min}자)`
          });
        } else if (current > max) {
          suggestions.push({
            priority: 'medium',
            message: `글자수가 초과되었습니다. (${current}자 / 최대 ${max}자)`
          });
        }
      }

      if (structure.headings.h2.count === 0 && structure.headings.h3.count === 0) {
        suggestions.push({
          priority: 'medium',
          message: '소제목(h2, h3)을 추가하여 가독성을 높이세요.'
        });
      }
    }

    return suggestions;
  }
}

module.exports = { SEOAgent };
