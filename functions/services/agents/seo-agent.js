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

function normalizeSpaces(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

function pickShortFallback(primaryKeyword, limit) {
  const candidates = [];
  if (primaryKeyword) {
    candidates.push(`${primaryKeyword} 현황`);
    candidates.push(`${primaryKeyword} 진단`);
    candidates.push(primaryKeyword);
  }
  candidates.push('현황 진단');
  candidates.push('현안 점검');

  for (const candidate of candidates) {
    if (candidate && candidate.length <= limit) return candidate;
  }

  const keywordTokens = primaryKeyword ? primaryKeyword.split(/\s+/).filter(Boolean) : [];
  for (let i = keywordTokens.length; i > 0; i -= 1) {
    const candidate = keywordTokens.slice(0, i).join(' ');
    if (candidate.length <= limit) return candidate;
  }

  return '현황 진단';
}

function shrinkTitleByRules(title, { primaryKeyword, limit }) {
  let normalized = normalizeSpaces(title);
  if (normalized.length <= limit) return normalized;

  normalized = normalized.replace(/[-–—|,]+$/g, '').trim();
  if (normalized.length <= limit) return normalized;

  const separatorRegex = /\s*[-–—|,]\s*/;
  if (separatorRegex.test(normalized)) {
    const parts = normalized.split(separatorRegex).map((part) => part.trim()).filter(Boolean);
    if (parts.length > 0) {
      const head = parts[0];
      if (head.length <= limit) return head;
      normalized = head;
    }
  }

  const words = normalized.split(' ').filter(Boolean);
  while (words.length > 1 && words.join(' ').length > limit) {
    words.pop();
  }
  const compact = normalizeSpaces(words.join(' '));
  if (compact.length <= limit) return compact;

  return pickShortFallback(primaryKeyword, limit);
}

class SEOAgent extends BaseAgent {
  constructor() {
    super('SEOAgent');
  }

  getRequiredContext() {
    return ['previousResults'];
  }

  async execute(context) {
    const { previousResults = {}, userProfile = {}, targetWordCount, userKeywords = [] } = context;

    // Compliance Agent 결과에서 콘텐츠 가져오기
    const complianceResult = previousResults.ComplianceAgent;
    const keywordResult = previousResults.KeywordAgent;
    const writerResult = previousResults.WriterAgent;
    const titleAgentResult = previousResults.TitleAgent;  // 🔧 TitleAgent 결과 참조

    if (!complianceResult?.success || !complianceResult?.data?.content) {
      throw new Error('Compliance Agent 결과가 없습니다');
    }

    const content = complianceResult.data.content;
    const keywords = keywordResult?.data?.keywords || [];
    const primaryKeyword = keywordResult?.data?.primary || (keywords[0]?.keyword || keywords[0] || '');

    // 🔧 [FIX] TitleAgent → ComplianceAgent → WriterAgent 순으로 제목 가져오기
    // modular 파이프라인에는 WriterAgent가 없으므로 TitleAgent를 우선 참조
    const existingTitle = titleAgentResult?.data?.title
      || complianceResult?.data?.title
      || writerResult?.data?.title
      || null;

    console.log(`🏷️ [SEOAgent] 제목 소스: ${titleAgentResult?.data?.title ? 'TitleAgent' : complianceResult?.data?.title ? 'ComplianceAgent' : writerResult?.data?.title ? 'WriterAgent' : 'none'} - "${existingTitle}"`);

    // 1. 제목 최적화 (25자 이내, 키워드 포함)
    const title = this.optimizeTitle(content, primaryKeyword, userProfile, existingTitle);

    // 2. 메타 설명 생성 (160자 이내)
    const metaDescription = this.generateMetaDescription(content, keywords);

    // 3. 본문 SEO 최적화
    const optimizedContent = this.optimizeContent(content, keywords);

    // 4. 키워드 밀도 분석
    const keywordDensity = this.analyzeKeywordDensity(optimizedContent, keywords);

    // 🔍 4-1. userKeywords 검증 (절대 횟수 체크)
    const userKeywordValidation = this.validateUserKeywords(optimizedContent, userKeywords, targetWordCount);

    // 🔍 4-2. 키워드 희석 감지 (경쟁 구문 탐지)
    const dilutionAnalysis = this.detectKeywordDilution(optimizedContent, userKeywords);

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
      wordCountRange,
      userKeywordValidation,  // 🔑 검색어 검증 결과 추가
      dilutionAnalysis        // 🔑 키워드 희석 분석 추가
    });

    // 7. 개선 제안 생성
    const suggestions = this.generateSuggestions(seoEvaluation.issues);

    // 🔍 로그 출력 (userKeywords 검증 결과 포함)
    const logData = {
      titleLength: title.length,
      contentLength: optimizedContent.replace(/<[^>]*>/g, '').length,
      seoPassed: seoEvaluation.passed,
      issueCount: seoEvaluation.issues.length,
      keywordCount: keywords.length
    };

    if (userKeywordValidation && userKeywordValidation.details) {
      logData.userKeywordCounts = Object.entries(userKeywordValidation.details)
        .map(([kw, info]) => `"${kw}": ${info.count}회`)
        .join(', ');
    }

    console.log(`🔍 [SEOAgent] 최적화 완료`, logData);

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
        userKeywordValidation,  // 🔑 검색어 검증 결과 추가
        dilutionAnalysis,       // 🔑 키워드 희석 분석 추가
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
      title = cleanFirstLine;
    } else if (primaryKeyword) {
      // 키워드 + 지역 조합
      if (region) {
        title = `${region} ${primaryKeyword} ${cleanFirstLine}`;
      } else {
        title = `${primaryKeyword} ${cleanFirstLine}`;
      }
    } else {
      title = cleanFirstLine;
    }

    title = normalizeSpaces(title);

    if (primaryKeyword && !title.includes(primaryKeyword)) {
      title = `${primaryKeyword} ${title}`.trim();
    }

    if (region && title.length < minLength && !title.includes(region)) {
      title = `${region} ${title}`.trim();
    }

    if (title.length > maxLength) {
      title = shrinkTitleByRules(title, { primaryKeyword, limit: maxLength });
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
   * 사용자 검색어(userKeywords) 검증 (400자당 1개 기준)
   * - 실제 글자수 기반으로 적정 횟수 계산
   * - 부족/과다 모두 오류
   *
   * @param {string} content - HTML 본문
   * @param {Array<string>} userKeywords - 사용자가 입력한 검색어 목록
   * @param {number} targetWordCount - 목표 글자수 (사용 안 함, 실제 글자수로 계산)
   * @returns {Object} 검증 결과 { passed, issues, details }
   */
  validateUserKeywords(content, userKeywords, targetWordCount = 2000) {
    const issues = [];
    const details = {};

    if (!userKeywords || userKeywords.length === 0) {
      return { passed: true, issues: [], details: {} };
    }

    const plainText = content.replace(/<[^>]*>/g, ' ');
    const actualLength = plainText.replace(/\s+/g, '').length; // 공백 제외 글자수

    // 키워드 2개 기준: 각 3~4회, 총합 7~8회 (15문단 기준 약 2문단당 1회)
    const kwCount = userKeywords.length || 1;
    const minRequired = kwCount >= 2 ? 3 : 5;
    const maxAllowed = minRequired + 1; // 3→4, 5→6
    const idealCount = minRequired;

    console.log(`🔍 [SEOAgent] 검색어 검증 시작: ${userKeywords.length}개`);
    console.log(`📏 [SEOAgent] 글자수: ${actualLength}자, 적정 횟수: 각 ${minRequired}~${maxAllowed}회 (총합 ${minRequired * kwCount}~${maxAllowed * kwCount}회)`);

    const plainTextLower = plainText.toLowerCase();

    for (const keyword of userKeywords) {
      const regex = new RegExp(keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      const matches = plainTextLower.match(regex);
      const count = matches ? matches.length : 0;

      details[keyword] = {
        count,
        idealCount,
        minRequired,
        maxAllowed,
        actualLength,
        status: count < minRequired ? 'insufficient' : (count > maxAllowed ? 'spam_risk' : 'valid')
      };

      // 부족 검증
      if (count < minRequired) {
        const missing = minRequired - count;
        issues.push({
          id: 'user_keyword_insufficient',
          severity: 'warning',
          message: `검색어 "${keyword}" 부족: ${count}회 (적정 ${idealCount}회, 최소 ${minRequired}회)`,
          description: `검색어 "${keyword}" 부족: 현재 ${count}회 (${actualLength}자 기준 적정 ${idealCount}회)`,
          instruction: `문맥에 맞게 "${keyword}"를 ${missing}회 더 추가하세요.`
        });
        console.warn(`⚠️ [SEOAgent] 검색어 부족: "${keyword}" ${count}회 < ${minRequired}회`);
      }

      // 과다 검증 (네이버 스팸 필터 방지)
      if (count > maxAllowed) {
        const excess = count - maxAllowed;
        issues.push({
          id: 'user_keyword_spam_risk',
          severity: 'warning',
          message: `검색어 "${keyword}" 과다: ${count}회 (적정 ${idealCount}회, 최대 ${maxAllowed}회)`,
          description: `검색어 "${keyword}" 과다: ${count}회 (${actualLength}자 기준 최대 ${maxAllowed}회)`,
          instruction: `"${keyword}"를 ${excess}회 줄여 ${maxAllowed}회 이하로 맞추세요.`
        });
        console.warn(`⚠️ [SEOAgent] 검색어 과다: "${keyword}" ${count}회 > ${maxAllowed}회`);
      }

      // 정상 범위
      if (count >= minRequired && count <= maxAllowed) {
        console.log(`✅ [SEOAgent] 검색어 적정: "${keyword}" ${count}회 (적정 ${idealCount}회, 범위 ${minRequired}~${maxAllowed}회)`);
      }
    }

    return {
      passed: issues.length === 0,
      issues,
      details
    };
  }

  /**
   * 키워드 희석(Keyword Dilution) 감지
   * - 메인 키워드보다 더 자주 등장하는 경쟁 구문 탐지
   * - SEO 효과 감소 위험 경고
   *
   * @param {string} content - HTML 본문
   * @param {Array<string>} userKeywords - 사용자 입력 메인 키워드
   * @returns {Object} { hasDilution, competitors, suggestions }
   */
  detectKeywordDilution(content, userKeywords) {
    if (!userKeywords || userKeywords.length === 0) {
      return { hasDilution: false, competitors: [], suggestions: [] };
    }

    const plainText = content.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

    // 1. 메인 키워드 출현 횟수 (가장 많은 것 기준)
    let maxMainCount = 0;
    let primaryKeyword = userKeywords[0];

    for (const keyword of userKeywords) {
      const regex = new RegExp(keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      const count = (plainText.match(regex) || []).length;
      if (count > maxMainCount) {
        maxMainCount = count;
        primaryKeyword = keyword;
      }
    }

    // 2. N-gram 추출 (2~4어절 구문) - 띄어쓰기 있는 구문
    const words = plainText.split(/\s+/).filter(w => w.length > 1);
    const phraseCount = {};

    for (let n = 2; n <= 4; n++) {
      for (let i = 0; i <= words.length - n; i++) {
        const phrase = words.slice(i, i + n).join(' ');
        // 너무 짧거나 조사로만 된 구문 제외
        if (phrase.length < 4) continue;
        // 메인 키워드와 동일하면 제외
        if (userKeywords.some(kw => phrase.toLowerCase() === kw.toLowerCase())) continue;
        // 메인 키워드를 포함하면 제외 (변형 카운트 방지)
        if (userKeywords.some(kw => phrase.toLowerCase().includes(kw.toLowerCase()))) continue;
        // 메인 키워드의 일부이면 제외 (예: "부산 병원"은 "부산 병원 순위"의 일부)
        if (userKeywords.some(kw => kw.toLowerCase().includes(phrase.toLowerCase()))) continue;

        phraseCount[phrase] = (phraseCount[phrase] || 0) + 1;
      }
    }

    // 2-1. 복합어+조사 패턴 감지 (예: "서울대병원 유치")
    // 주요 반복 구문을 직접 검색 (4글자 이상 한글 단어가 3회 이상 등장)
    const compoundPatterns = {};

    // 본문에서 모든 단어(조사 포함) 추출
    const allWords = plainText.split(/\s+/).filter(w => w.length >= 3);

    // 각 단어에서 핵심 어근 추출 (조사 제거)
    const particles = ['은', '는', '이', '가', '을', '를', '에', '의', '로', '으로', '와', '과', '에서', '부터', '까지', '도', '만', '조차'];

    for (const word of allWords) {
      // 조사 제거하여 어근 추출
      let stem = word;
      for (const p of particles) {
        if (word.endsWith(p) && word.length > p.length + 2) {
          stem = word.slice(0, -p.length);
          break;
        }
      }

      // 4글자 이상 어근만 카운트
      if (stem.length >= 4 && /^[가-힣]+$/.test(stem)) {
        // 메인 키워드와 관련 없는 것만
        const isRelatedToMain = userKeywords.some(kw =>
          stem.includes(kw.replace(/\s/g, '')) ||
          kw.replace(/\s/g, '').includes(stem)
        );
        if (!isRelatedToMain) {
          compoundPatterns[stem] = (compoundPatterns[stem] || 0) + 1;
        }
      }
    }

    // 복합어 중 빈도수가 높은 것을 phraseCount에 병합
    for (const [word, count] of Object.entries(compoundPatterns)) {
      if (count >= 3) { // 최소 3회 이상 등장
        phraseCount[word] = (phraseCount[word] || 0) + count;
      }
    }

    // 3. 메인 키워드보다 많이 등장하는 경쟁 구문 탐지
    const competitors = [];
    const threshold = maxMainCount; // 메인 키워드와 같거나 더 많으면 경쟁자

    for (const [phrase, count] of Object.entries(phraseCount)) {
      if (count >= threshold && count >= 3) { // 최소 3회 이상 등장
        // 의미 있는 구문인지 확인
        const words = phrase.split(' ');

        // 복합어(띄어쓰기 없는 4글자 이상 단일 단어)도 의미있음
        const isCompoundWord = words.length === 1 && phrase.length >= 4 && /^[가-힣]+$/.test(phrase);

        // 다중 단어 구문: 조사만 있는 구문 제외
        const meaningfulWords = words.filter(w =>
          !['의', '를', '을', '에', '가', '이', '는', '은', '로', '와', '과', '에서', '으로', '이다', '있다'].includes(w)
        );

        if (isCompoundWord || meaningfulWords.length >= 2) {
          competitors.push({
            phrase,
            count,
            mainKeywordCount: maxMainCount,
            ratio: (count / maxMainCount).toFixed(2),
            severity: count > maxMainCount ? 'high' : 'medium'
          });
        }
      }
    }

    // 4. 심각도순 정렬 (횟수 많은 순)
    competitors.sort((a, b) => b.count - a.count);

    // 5. 상위 3개만 추출
    const topCompetitors = competitors.slice(0, 3);

    // 6. 대체어 제안 생성
    const suggestions = topCompetitors.map(comp => ({
      original: comp.phrase,
      suggestion: `"${comp.phrase}" → 동의어/유사어로 분산 권장`,
      reason: `메인 키워드 "${primaryKeyword}"(${maxMainCount}회)보다 ${comp.count}회 등장 - SEO 희석 위험`
    }));

    const hasDilution = topCompetitors.length > 0;

    if (hasDilution) {
      console.warn(`⚠️ [SEOAgent] 키워드 희석 감지: ${topCompetitors.length}개 경쟁 구문 발견`);
      topCompetitors.forEach(c => {
        console.warn(`   - "${c.phrase}": ${c.count}회 (메인: ${maxMainCount}회)`);
      });
    }

    return {
      hasDilution,
      primaryKeyword,
      primaryCount: maxMainCount,
      competitors: topCompetitors,
      suggestions
    };
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
    wordCountRange = SEO_RULES.wordCount,
    userKeywordValidation = null,  // 🔑 검색어 검증 결과
    dilutionAnalysis = null        // 🔑 키워드 희석 분석 결과
  }) {
    const issues = [];

    // 🔑 1순위: userKeywords 검증 (가장 중요)
    if (userKeywordValidation && !userKeywordValidation.passed) {
      issues.push(...userKeywordValidation.issues);
    }

    // 🔑 2순위: 키워드 희석 검증 (경쟁 구문 감지)
    if (dilutionAnalysis && dilutionAnalysis.hasDilution) {
      for (const comp of dilutionAnalysis.competitors) {
        issues.push({
          id: 'keyword_dilution',
          severity: comp.severity === 'high' ? 'high' : 'medium',
          message: `키워드 희석 위험: "${comp.phrase}"가 ${comp.count}회 등장 (메인 키워드 "${dilutionAnalysis.primaryKeyword}": ${dilutionAnalysis.primaryCount}회)`,
          description: `경쟁 구문 "${comp.phrase}"이 메인 키워드보다 많거나 같게 등장하여 SEO 효과가 분산될 수 있습니다.`,
          instruction: `"${comp.phrase}"을 동의어(예: "의료 인프라 확충", "대형병원 유치" 등)로 분산하세요.`
        });
      }
    }
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
