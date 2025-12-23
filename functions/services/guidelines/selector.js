/**
 * functions/services/guidelines/selector.js
 * 지침 선택기 - 메타데이터 필터 + 키워드 매칭
 *
 * 특징:
 * - 메모리 캐시로 빠른 접근 (Firestore 호출 없음)
 * - 메타데이터 기반 하드 필터링
 * - topic 키워드 매칭으로 관련성 점수 계산
 */

'use strict';

const NodeCache = require('node-cache');

// 청크 모듈 import
const { ELECTION_LAW_CHUNKS } = require('./chunks/election-law');
const { SEO_CHUNKS } = require('./chunks/seo');
const { QUALITY_CHUNKS } = require('./chunks/quality');
const { NAMING_CHUNKS, isCriticalContext } = require('./chunks/naming');

// 메모리 캐시 (1시간 TTL)
const cache = new NodeCache({ stdTTL: 3600, checkperiod: 600 });
const CACHE_KEY = 'ALL_GUIDELINE_CHUNKS';

/**
 * 모든 청크를 메모리에 로드
 */
function loadAllChunks() {
  const cached = cache.get(CACHE_KEY);
  if (cached) return cached;

  const allChunks = [
    ...ELECTION_LAW_CHUNKS,
    ...SEO_CHUNKS,
    ...QUALITY_CHUNKS,
    ...NAMING_CHUNKS
  ];

  cache.set(CACHE_KEY, allChunks);
  console.log(`📚 Guideline Chunks 로드 완료: ${allChunks.length}개`);

  return allChunks;
}

/**
 * 메타데이터 기반 필터링
 *
 * @param {Object} chunk - 청크 객체
 * @param {Object} context - 컨텍스트 { status, category, writingMethod }
 * @returns {boolean} 적용 가능 여부
 */
function matchesMetadata(chunk, context) {
  const { status, category, writingMethod } = context;
  const appliesTo = chunk.applies_to || {};

  // status 필터
  if (appliesTo.status && appliesTo.status.length > 0) {
    if (!appliesTo.status.includes(status)) {
      return false;
    }
  }

  // category 필터 ('all'은 항상 통과)
  if (appliesTo.category && !appliesTo.category.includes('all')) {
    if (!appliesTo.category.includes(category)) {
      return false;
    }
  }

  // writingMethod 필터
  if (appliesTo.writingMethod && appliesTo.writingMethod.length > 0) {
    if (!appliesTo.writingMethod.includes(writingMethod)) {
      return false;
    }
  }

  return true;
}

/**
 * 키워드 관련성 점수 계산
 *
 * @param {Object} chunk - 청크 객체
 * @param {string} topic - 주제
 * @returns {number} 관련성 점수 (0~)
 */
function calculateRelevance(chunk, topic) {
  if (!topic || !chunk.keywords) return 0;

  const topicLower = topic.toLowerCase();
  const topicWords = topicLower.split(/\s+/);

  let score = 0;

  // 청크 키워드가 topic에 포함되는지 확인
  for (const keyword of chunk.keywords) {
    const keywordLower = keyword.toLowerCase();

    // 정확히 포함
    if (topicLower.includes(keywordLower)) {
      score += 2;
    }

    // 단어 단위 매칭
    for (const word of topicWords) {
      if (word.includes(keywordLower) || keywordLower.includes(word)) {
        score += 1;
      }
    }
  }

  return score;
}

/**
 * 우선순위 정렬 (CRITICAL > HIGH > MEDIUM > LOW)
 */
function sortByPriority(chunks) {
  const priorityOrder = {
    'CRITICAL': 0,
    'HIGH': 1,
    'MEDIUM': 2,
    'LOW': 3
  };

  return [...chunks].sort((a, b) => {
    const priorityDiff = (priorityOrder[a.priority] || 3) - (priorityOrder[b.priority] || 3);
    if (priorityDiff !== 0) return priorityDiff;

    // 같은 우선순위면 관련성 점수로 정렬
    return (b.relevance || 0) - (a.relevance || 0);
  });
}

/**
 * 지침 선택 메인 함수
 *
 * @param {Object} context
 * @param {string} context.status - 사용자 상태 (준비/현역/예비/후보)
 * @param {string} context.category - 글 카테고리
 * @param {string} context.writingMethod - 작법
 * @param {string} context.topic - 주제
 * @returns {Object} { critical, high, contextual }
 */
function selectGuidelines(context) {
  const { status, category, writingMethod, topic } = context;

  console.log(`🎯 Guideline 선택 시작:`, { status, category, writingMethod, topic: topic?.substring(0, 30) });

  const allChunks = loadAllChunks();

  // 1단계: 메타데이터 필터링
  const filtered = allChunks.filter(chunk => matchesMetadata(chunk, context));

  // 2단계: 관련성 점수 계산
  const scored = filtered.map(chunk => ({
    ...chunk,
    relevance: calculateRelevance(chunk, topic)
  }));

  // 3단계: 우선순위별 분류
  const critical = scored.filter(c => c.priority === 'CRITICAL');
  const high = scored.filter(c => c.priority === 'HIGH');
  const medium = scored.filter(c => c.priority === 'MEDIUM');

  // 4단계: 정렬
  const sortedCritical = sortByPriority(critical);
  const sortedHigh = sortByPriority(high);

  // 5단계: 컨텍스트별 선택 (관련성 높은 MEDIUM 청크)
  const contextual = medium
    .filter(c => c.relevance > 0)
    .sort((a, b) => (b.relevance || 0) - (a.relevance || 0))
    .slice(0, 3);  // 상위 3개만

  console.log(`📋 선택된 Guidelines:`, {
    critical: sortedCritical.length,
    high: sortedHigh.length,
    contextual: contextual.length
  });

  return {
    critical: sortedCritical,
    high: sortedHigh,
    contextual,
    all: [...sortedCritical, ...sortedHigh, ...contextual]
  };
}

/**
 * 특정 타입의 청크만 선택
 *
 * @param {string} type - 'election_law' | 'seo' | 'quality' | 'naming'
 * @param {Object} context - 컨텍스트
 * @returns {Array} 필터링된 청크 배열
 */
function selectByType(type, context) {
  const allChunks = loadAllChunks();

  return allChunks
    .filter(c => c.type === type)
    .filter(c => matchesMetadata(c, context))
    .map(c => ({
      ...c,
      relevance: calculateRelevance(c, context.topic)
    }));
}

/**
 * CRITICAL 청크만 빠르게 조회 (리마인더용)
 */
function getCriticalChunks(context) {
  const allChunks = loadAllChunks();

  return allChunks
    .filter(c => c.priority === 'CRITICAL')
    .filter(c => matchesMetadata(c, context));
}

/**
 * 캐시 초기화 (테스트/디버깅용)
 */
function clearCache() {
  cache.del(CACHE_KEY);
  console.log('🗑️ Guideline 캐시 초기화');
}

module.exports = {
  loadAllChunks,
  selectGuidelines,
  selectByType,
  getCriticalChunks,
  matchesMetadata,
  calculateRelevance,
  clearCache
};
