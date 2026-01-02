'use strict';

/**
 * SEO Agent - 네이버 검색 최적화 (통합 리팩토링 버전)
 *
 * 역할:
 * - 네이버 SEO 최적화 적용
 * - 제목 최적화 (25자 이내)
 * - 메타 설명 생성
 * - 키워드 밀도 분석 및 조정
 *
 * prompts/guidelines의 SEO 규칙들을 import하여 사용
 */

const { BaseAgent } = require('./base');

// ✅ 기존 guidelines import
const { SEO_RULES, FORMAT_RULES, CONTENT_RULES } = require('../../prompts/guidelines/editorial');
const { calculateMinInsertions, calculateDistribution } = require('../../prompts/guidelines/seo');

const TITLE_LIMITS = {
  min: 18,
  max: 25
};

const META_LIMITS = {
  min: 100,
  max: 160
};

class SEOAgent extends BaseAgent {
  constructor() {
    super('SEOAgent');
  }

  getRequiredContext() {
    return ['previousResults'];
  }

  async execute(context) {
    const { previousResults = {}, userProfile = {}, targetWordCount } = context;

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

    // 1. 제목 최적화 (25자 이내, 키워드 포함)
    const title = this.optimizeTitle(content, primaryKeyword, userProfile, writerTitle);

    // 2. 메타 설명 생성 (160자 이내)
    const metaDescription = this.generateMetaDescription(content, keywords);

    // 3. 본문 SEO 최적화
    const optimizedContent = this.optimizeContent(content, keywords);

    // 4. 키워드 밀도 분석
    const keywordDensity = this.analyzeKeywordDensity(optimizedContent, keywords);

    // 5. 구조 분석
    const wordCountRange = this.getWordCountRange(targetWordCount);
    const structureAnalysis = this.analyzeStructure(optimizedContent, wordCountRange);

    // 6. SEO Pass/Fail 평가
    const seoEvaluation = this.evaluateSEOCompliance({
      title,
      primaryKeyword,
      metaDescription,
      keywordDensity,
      contentLength: optimizedContent.replace(/<[^>]*>/g, '').length,
      structure: structureAnalysis,
      keywordCount: keywords.length,
      wordCountRange
    });

    // 7. 개선 제안 생성
    const suggestions = this.generateSuggestions(seoEvaluation.issues);

    console.log(`🔍 [SEOAgent] 최적화 완료`, {
      titleLength: title.length,
      contentLength: optimizedContent.replace(/<[^>]*>/g, '').length,
      seoPassed: seoEvaluation.passed,
      issueCount: seoEvaluation.issues.length,
      keywordCount: keywords.length
    });

    return {
      title,
      metaDescription,
      content: optimizedContent,
      keywords: keywords.slice(0, 5).map(k => k.keyword || k),
      seoPassed: seoEvaluation.passed,
      issues: seoEvaluation.issues,
      suggestions,
      analysis: {
        keywordDensity,
        structure: structureAnalysis,
        seoEvaluation
      }
    };
  }

  getWordCountRange(targetWordCount) {
    const baseRange = SEO_RULES.wordCount;
    if (!targetWordCount || typeof targetWordCount !== 'number') {
      return baseRange;
    }

    const min = Math.max(baseRange.min, targetWordCount);
    const max = Math.max(baseRange.max, Math.round(min * 1.1));

    return {
      ...baseRange,
      min,
      max
    };
  }

  /**
   * 제목 최적화 (SEO_RULES 기반)
   */
  optimizeTitle(content, primaryKeyword, userProfile, existingTitle) {
    const minLength = TITLE_LIMITS.min;
    const maxLength = TITLE_LIMITS.max;

    // 이미 좋은 제목이 있으면 길이만 체크
    if (existingTitle && existingTitle.length >= minLength && existingTitle.length <= maxLength) {
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
      title = cleanFirstLine.substring(0, maxLength);
    } else if (primaryKeyword) {
      // 키워드 + 지역 조합
      if (region) {
        title = `${region} ${primaryKeyword} ${cleanFirstLine}`;
      } else {
        title = `${primaryKeyword} ${cleanFirstLine}`;
      }
    } else {
      title = cleanFirstLine.substring(0, maxLength);
    }

    title = title.replace(/\s+/g, ' ').trim();

    if (primaryKeyword && !title.includes(primaryKeyword)) {
      title = `${primaryKeyword} ${title}`.trim();
    }

    if (region && title.length < minLength && !title.includes(region)) {
      title = `${region} ${title}`.trim();
    }

    if (title.length > maxLength) {
      const cutPoint = title.lastIndexOf(' ', maxLength);
      title = title.substring(0, cutPoint > minLength ? cutPoint : maxLength).trim();
    }

    return title;
  }

  /**
   * 메타 설명 생성
   */
  generateMetaDescription(content, keywords) {
    // HTML 태그 제거
    const plainText = content.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

    // 첫 문장부터 100자 이상 확보
    const sentences = plainText.split(/[.!?]\s+/).filter(s => s.length > 10);
    let description = '';

    for (const sentence of sentences) {
      description = description ? `${description}. ${sentence}` : sentence;
      if (description.length >= META_LIMITS.min) break;
    }

    if (!description && plainText) {
      description = plainText.substring(0, META_LIMITS.max);
    }

    if (description.length > META_LIMITS.max) {
      description = description.substring(0, META_LIMITS.max - 3) + '...';
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
  analyzeStructure(content, wordCountRange = SEO_RULES.wordCount) {
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
        min: wordCountRange.min,
        max: wordCountRange.max,
        current: charCount,
        inRange: charCount >= wordCountRange.min && charCount <= wordCountRange.max
      }
    };
  }

  /**
   * SEO Pass/Fail 평가
   */
  evaluateSEOCompliance({
    title,
    primaryKeyword,
    metaDescription,
    keywordDensity,
    contentLength,
    structure,
    keywordCount,
    wordCountRange = SEO_RULES.wordCount
  }) {
    const issues = [];
    const titleLength = title.length;
    const titleHasKeyword = primaryKeyword ? title.includes(primaryKeyword) : true;

    if (titleLength < TITLE_LIMITS.min || titleLength > TITLE_LIMITS.max) {
      issues.push({
        id: 'title_length',
        severity: 'critical',
        message: `제목 길이 ${titleLength}자: ${TITLE_LIMITS.min}-${TITLE_LIMITS.max}자 범위가 필요합니다.`
      });
    }

    if (!titleHasKeyword) {
      issues.push({
        id: 'title_keyword',
        severity: 'critical',
        message: `제목에 핵심 키워드("${primaryKeyword}")가 없습니다.`
      });
    }

    if (metaDescription.length < META_LIMITS.min || metaDescription.length > META_LIMITS.max) {
      issues.push({
        id: 'meta_length',
        severity: 'high',
        message: `메타 설명 길이 ${metaDescription.length}자: ${META_LIMITS.min}-${META_LIMITS.max}자 범위가 필요합니다.`
      });
    }

    const { min, max } = wordCountRange;
    if (contentLength < min || contentLength > max) {
      issues.push({
        id: 'content_length',
        severity: 'critical',
        message: `본문 분량 ${contentLength}자: ${min}-${max}자 범위를 충족해야 합니다.`
      });
    }

    if (!keywordCount || keywordCount === 0) {
      issues.push({
        id: 'keywords_missing',
        severity: 'critical',
        message: 'SEO 키워드가 없습니다. 키워드를 최소 1개 이상 포함해야 합니다.'
      });
    } else {
      const primaryKey = primaryKeyword ? primaryKeyword.toLowerCase() : '';
      for (const [keyword, data] of Object.entries(keywordDensity)) {
        const isPrimary = primaryKey && keyword === primaryKey;
        if (data.status === 'too_low' || data.status === 'too_high') {
          issues.push({
            id: 'keyword_density',
            severity: isPrimary ? 'critical' : 'high',
            message: `키워드 "${keyword}" 밀도가 기준을 벗어났습니다. (${data.count}회, ${data.percentage}%)`
          });
        } else if (isPrimary && data.status !== 'optimal') {
          issues.push({
            id: 'primary_keyword_density',
            severity: 'critical',
            message: `핵심 키워드 "${keyword}" 밀도가 최적 범위가 아닙니다. (${data.count}회, ${data.percentage}%)`
          });
        }
      }
    }

    if (structure) {
      const hasHeadings = structure.headings.h2.count >= 1 || structure.headings.h3.count >= 2;
      if (!hasHeadings) {
        issues.push({
          id: 'structure_headings',
          severity: 'high',
          message: '소제목(H2/H3)이 부족합니다. H2 1개 이상 또는 H3 2개 이상이 필요합니다.'
        });
      }

      if (structure.paragraphs.count < 5 || structure.paragraphs.count > 10) {
        issues.push({
          id: 'structure_paragraphs',
          severity: 'high',
          message: `문단 수 ${structure.paragraphs.count}개: 5-10개 범위가 필요합니다.`
        });
      }
    }

    return {
      passed: issues.length === 0,
      issues
    };
  }

  /**
   * 개선 제안 생성
   */
  generateSuggestions(issues = []) {
    return issues.map(issue => ({
      priority: issue.severity === 'critical' ? 'high' : 'medium',
      message: issue.message
    }));
  }
}

module.exports = { SEOAgent };
