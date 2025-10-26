/**
 * services/keyword-scorer.js
 * 키워드 점수 계산 및 품질 분석
 */

'use strict';

/**
 * SERP 점수 계산 (검색 결과 페이지 분석)
 * @param {Object} serpData - SERP 분석 데이터
 * @returns {number} 0-10 점수
 */
function calculateSERPScore(serpData) {
  if (!serpData || !serpData.results || serpData.results.length === 0) {
    return 5; // 기본 중립 점수
  }

  let score = 10; // 최고 점수에서 시작

  const { blogCount, officialCount, totalResults } = serpData;

  // 1. 공식 사이트 패널티
  // .go.kr, .or.kr, 뉴스 사이트가 많으면 경쟁이 어려움
  const officialRatio = totalResults > 0 ? officialCount / totalResults : 0;

  if (officialRatio > 0.6) {
    score -= 4; // 60% 이상 공식 사이트면 큰 패널티
  } else if (officialRatio > 0.4) {
    score -= 3;
  } else if (officialRatio > 0.2) {
    score -= 2;
  }

  // 2. 블로그 비율 보너스
  // 블로그가 많으면 개인도 경쟁 가능
  const blogRatio = totalResults > 0 ? blogCount / totalResults : 0;

  if (blogRatio > 0.6) {
    score += 3; // 60% 이상 블로그면 큰 보너스
  } else if (blogRatio > 0.4) {
    score += 2;
  } else if (blogRatio > 0.2) {
    score += 1;
  }

  // 3. 오래된 콘텐츠 보너스
  // (날짜 정보가 있다면 분석)
  // 여기서는 간단히 처리, 실제로는 serpData.results에서 날짜 추출 필요

  // 점수 범위 제한
  return Math.max(0, Math.min(10, score));
}

/**
 * 경쟁도 점수 계산
 * @param {number} resultCount - 검색 결과 수
 * @returns {number} 0-10 점수
 */
function calculateCompetitionScore(resultCount) {
  // 검색 결과가 적을수록 경쟁이 낮음 = 높은 점수
  if (resultCount < 100) {
    return 10;
  } else if (resultCount < 500) {
    return 9;
  } else if (resultCount < 1000) {
    return 8;
  } else if (resultCount < 5000) {
    return 7;
  } else if (resultCount < 10000) {
    return 6;
  } else if (resultCount < 50000) {
    return 5;
  } else if (resultCount < 100000) {
    return 4;
  } else if (resultCount < 500000) {
    return 3;
  } else if (resultCount < 1000000) {
    return 2;
  } else {
    return 1;
  }
}

/**
 * 구체성 점수 계산 (단어 수 기반)
 * @param {string} keyword - 키워드
 * @returns {number} 0-10 점수
 */
function calculateSpecificityScore(keyword) {
  // 띄어쓰기로 단어 수 계산
  const words = keyword.trim().split(/\s+/);
  const wordCount = words.length;

  // 롱테일 키워드일수록 높은 점수
  if (wordCount >= 5) {
    return 10;
  } else if (wordCount === 4) {
    return 9;
  } else if (wordCount === 3) {
    return 7;
  } else if (wordCount === 2) {
    return 5;
  } else {
    return 3; // 단일 단어는 경쟁이 너무 높음
  }
}

/**
 * 블로그 비율 점수 계산
 * @param {Object} serpData - SERP 분석 데이터
 * @returns {number} 0-10 점수
 */
function calculateBlogRatioScore(serpData) {
  if (!serpData || !serpData.totalResults || serpData.totalResults === 0) {
    return 5;
  }

  const blogRatio = serpData.blogCount / serpData.totalResults;

  // 블로그 비율이 높을수록 높은 점수
  if (blogRatio >= 0.8) {
    return 10;
  } else if (blogRatio >= 0.6) {
    return 9;
  } else if (blogRatio >= 0.4) {
    return 7;
  } else if (blogRatio >= 0.2) {
    return 5;
  } else {
    return 3;
  }
}

/**
 * 정치 관련성 점수 계산
 * @param {string} keyword - 키워드
 * @param {string} district - 지역구
 * @param {string} topic - 주제
 * @returns {number} 0-10 점수
 */
function calculateRelevanceScore(keyword, district, topic) {
  let score = 5; // 기본 점수

  const lowerKeyword = keyword.toLowerCase();

  // 지역구 포함 여부
  if (district && lowerKeyword.includes(district.toLowerCase())) {
    score += 3;
  }

  // 주제 포함 여부
  if (topic && lowerKeyword.includes(topic.toLowerCase())) {
    score += 2;
  }

  // 정치 관련 키워드
  const politicalKeywords = [
    '의원', '국회', '시의회', '구의회', '정책', '공약',
    '지역', '주민', '시민', '민생', '복지', '개발',
    '예산', '조례', '의정', '활동', '행정', '사업'
  ];

  const hasPoliticalKeyword = politicalKeywords.some(pk =>
    lowerKeyword.includes(pk)
  );

  if (hasPoliticalKeyword) {
    score += 2;
  }

  return Math.min(10, score);
}

/**
 * 최종 점수 계산 (가중 평균)
 * @param {Object} scores - 각 항목별 점수
 * @returns {number} 최종 점수 (0-100)
 */
function calculateFinalScore(scores) {
  const {
    competitionScore = 5,
    specificityScore = 5,
    blogRatioScore = 5,
    trendScore = 5,
    relevanceScore = 5
  } = scores;

  // 가중치
  const weights = {
    competition: 0.35,    // 35%
    specificity: 0.25,    // 25%
    blogRatio: 0.20,      // 20%
    trend: 0.10,          // 10%
    relevance: 0.10       // 10%
  };

  // 가중 평균 계산
  const finalScore =
    (competitionScore * weights.competition) +
    (specificityScore * weights.specificity) +
    (blogRatioScore * weights.blogRatio) +
    (trendScore * weights.trend) +
    (relevanceScore * weights.relevance);

  // 0-100 범위로 변환
  return Math.round(finalScore * 10);
}

/**
 * 키워드 등급 부여
 * @param {number} finalScore - 최종 점수
 * @returns {string} 등급 (S, A, B, C, D)
 */
function getKeywordGrade(finalScore) {
  if (finalScore >= 85) return 'S'; // 최상급
  if (finalScore >= 70) return 'A'; // 상급
  if (finalScore >= 55) return 'B'; // 중상급
  if (finalScore >= 40) return 'C'; // 중급
  return 'D'; // 하급
}

/**
 * 키워드 종합 분석
 * @param {Object} params - 분석 파라미터
 * @returns {Object} 종합 분석 결과
 */
function analyzeKeyword(params) {
  const {
    keyword,
    serpData,
    resultCount,
    trendScore,
    district,
    topic
  } = params;

  // 각 항목별 점수 계산
  const scores = {
    competitionScore: calculateCompetitionScore(resultCount),
    specificityScore: calculateSpecificityScore(keyword),
    blogRatioScore: calculateBlogRatioScore(serpData),
    trendScore: trendScore || 5,
    relevanceScore: calculateRelevanceScore(keyword, district, topic),
    serpScore: calculateSERPScore(serpData)
  };

  // 최종 점수
  const finalScore = calculateFinalScore(scores);
  const grade = getKeywordGrade(finalScore);

  // 추천 이유 생성
  const reasons = generateRecommendationReasons(scores, finalScore);

  return {
    keyword,
    finalScore,
    grade,
    scores,
    reasons,
    metadata: {
      resultCount,
      blogRatio: serpData ? (serpData.blogCount / serpData.totalResults) : 0,
      officialRatio: serpData ? (serpData.officialCount / serpData.totalResults) : 0
    }
  };
}

/**
 * 추천 이유 생성
 * @param {Object} scores - 점수 객체
 * @param {number} finalScore - 최종 점수
 * @returns {Array<string>} 추천 이유 배열
 */
function generateRecommendationReasons(scores, finalScore) {
  const reasons = [];

  if (scores.competitionScore >= 8) {
    reasons.push('🎯 경쟁이 낮아 상위 노출 가능성이 높습니다');
  }

  if (scores.specificityScore >= 7) {
    reasons.push('📝 구체적인 롱테일 키워드로 타겟팅이 명확합니다');
  }

  if (scores.blogRatioScore >= 7) {
    reasons.push('📰 블로그 콘텐츠가 많아 개인도 경쟁 가능합니다');
  }

  if (scores.trendScore >= 8) {
    reasons.push('📈 검색량이 증가하는 트렌드입니다');
  }

  if (scores.relevanceScore >= 8) {
    reasons.push('🏛️ 정치/지역 관련성이 매우 높습니다');
  }

  if (finalScore >= 85) {
    reasons.push('⭐ 최상위 등급 키워드입니다');
  }

  if (reasons.length === 0) {
    reasons.push('💡 일반적인 키워드입니다');
  }

  return reasons;
}

/**
 * 키워드 배치 분석
 * @param {Array<Object>} keywords - 키워드 배열 (각각 분석 파라미터 포함)
 * @returns {Array<Object>} 분석 결과 배열 (점수순 정렬)
 */
function analyzeKeywordBatch(keywords) {
  console.log(`📊 [Scorer] 배치 분석 시작: ${keywords.length}개 키워드`);

  const results = keywords.map(params => analyzeKeyword(params));

  // 최종 점수 기준 내림차순 정렬
  results.sort((a, b) => b.finalScore - a.finalScore);

  console.log(`✅ [Scorer] 배치 분석 완료`);

  return results;
}

module.exports = {
  calculateSERPScore,
  calculateCompetitionScore,
  calculateSpecificityScore,
  calculateBlogRatioScore,
  calculateRelevanceScore,
  calculateFinalScore,
  getKeywordGrade,
  analyzeKeyword,
  analyzeKeywordBatch
};
