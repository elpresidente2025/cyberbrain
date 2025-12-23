/**
 * functions/services/rag/reranker.js
 * Hugging Face Inference API를 사용한 BGE Reranker 서비스
 *
 * 벡터 검색 결과를 Cross-Encoder로 재순위하여 정확도를 높입니다.
 * Upstash Redis 캐싱으로 중복 호출을 방지합니다.
 */

'use strict';

const { Redis } = require('@upstash/redis');
const crypto = require('crypto');
const { logError } = require('../../common/log');

// Hugging Face 설정
const HF_API_URL = 'https://api-inference.huggingface.co/models/BAAI/bge-reranker-base';
const HF_API_TOKEN = process.env.HF_API_TOKEN;

// Upstash Redis 설정
const UPSTASH_REDIS_REST_URL = process.env.UPSTASH_REDIS_REST_URL;
const UPSTASH_REDIS_REST_TOKEN = process.env.UPSTASH_REDIS_REST_TOKEN;

// Redis 클라이언트 (lazy initialization)
let redisClient = null;

function getRedisClient() {
  if (!redisClient && UPSTASH_REDIS_REST_URL && UPSTASH_REDIS_REST_TOKEN) {
    redisClient = new Redis({
      url: UPSTASH_REDIS_REST_URL,
      token: UPSTASH_REDIS_REST_TOKEN
    });
  }
  return redisClient;
}

// Reranker 설정
const RERANKER_TIMEOUT_MS = 10000;  // 10초 타임아웃
const MAX_RETRIES = 2;
const RETRY_DELAY_MS = 500;
const CACHE_TTL_SECONDS = 3600;  // 1시간 캐시

/**
 * 캐시 키 생성 (쿼리 + 문서 텍스트 해시)
 */
function generateCacheKey(query, texts) {
  const content = JSON.stringify({ q: query, t: texts });
  const hash = crypto.createHash('sha256').update(content).digest('hex').substring(0, 16);
  return `rerank:${hash}`;
}

/**
 * 캐시에서 결과 조회
 */
async function getFromCache(cacheKey) {
  const redis = getRedisClient();
  if (!redis) return null;

  try {
    const cached = await redis.get(cacheKey);
    if (cached) {
      console.log(`📦 Reranker 캐시 히트: ${cacheKey}`);
      return cached;
    }
  } catch (error) {
    console.warn('⚠️ Redis 캐시 조회 실패:', error.message);
  }
  return null;
}

/**
 * 결과를 캐시에 저장
 */
async function saveToCache(cacheKey, scores) {
  const redis = getRedisClient();
  if (!redis) return;

  try {
    await redis.set(cacheKey, scores, { ex: CACHE_TTL_SECONDS });
    console.log(`💾 Reranker 결과 캐싱: ${cacheKey} (TTL: ${CACHE_TTL_SECONDS}s)`);
  } catch (error) {
    console.warn('⚠️ Redis 캐시 저장 실패:', error.message);
  }
}

/**
 * Hugging Face Inference API를 사용하여 문서 재순위
 *
 * @param {string} query - 검색 쿼리
 * @param {Array<{text: string, ...}>} documents - 재순위할 문서 배열
 * @returns {Promise<Array<{index: number, score: number}>>} - 재순위 결과
 */
async function rerank(query, documents) {
  if (!HF_API_TOKEN) {
    console.warn('⚠️ HF_API_TOKEN이 설정되지 않음 - reranker 스킵');
    return null;
  }

  if (!query || !documents || documents.length === 0) {
    return null;
  }

  // 문서 텍스트 추출
  const texts = documents.map(doc => doc.text || doc.chunkText || '');

  // 캐시 확인
  const cacheKey = generateCacheKey(query, texts);
  const cachedScores = await getFromCache(cacheKey);
  if (cachedScores) {
    return cachedScores;
  }

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      console.log(`🔄 Reranker 호출 (시도 ${attempt}/${MAX_RETRIES}) - ${texts.length}개 문서`);

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), RERANKER_TIMEOUT_MS);

      const response = await fetch(HF_API_URL, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${HF_API_TOKEN}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          inputs: {
            query: query,
            texts: texts
          }
        }),
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorText = await response.text();

        // 모델 로딩 중인 경우 (503)
        if (response.status === 503) {
          console.log('⏳ 모델 로딩 중... 재시도 대기');
          await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS * 2));
          continue;
        }

        throw new Error(`HF API 오류 (${response.status}): ${errorText}`);
      }

      const result = await response.json();

      // HF API 응답 형식: [score1, score2, ...] 또는 [{index, score}, ...]
      let scores;
      if (Array.isArray(result) && typeof result[0] === 'number') {
        // 점수 배열 형식
        scores = result.map((score, index) => ({ index, score }));
      } else if (Array.isArray(result) && result[0]?.score !== undefined) {
        // {index, score} 객체 배열 형식
        scores = result;
      } else {
        console.warn('⚠️ 예상치 못한 HF API 응답 형식:', JSON.stringify(result).substring(0, 200));
        return null;
      }

      // 점수 기준 내림차순 정렬
      scores.sort((a, b) => b.score - a.score);

      console.log(`✅ Reranker 완료 - 상위 점수: ${scores[0]?.score?.toFixed(3) || 'N/A'}`);

      // 결과 캐싱
      await saveToCache(cacheKey, scores);

      return scores;

    } catch (error) {
      if (error.name === 'AbortError') {
        console.warn(`⚠️ Reranker 타임아웃 (${RERANKER_TIMEOUT_MS}ms)`);
      } else {
        console.error(`❌ Reranker 오류 (시도 ${attempt}):`, error.message);
      }

      logError('rerank', `Reranker 시도 ${attempt} 실패`, {
        error: error.message,
        queryLength: query.length,
        docCount: documents.length
      });

      if (attempt === MAX_RETRIES) {
        return null;  // 실패 시 null 반환 (기존 로직으로 폴백)
      }

      await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS * attempt));
    }
  }

  return null;
}

/**
 * 문서 배열에 reranker 점수를 적용하여 재정렬
 *
 * @param {string} query - 검색 쿼리
 * @param {Object[]} documents - 원본 문서 배열
 * @returns {Promise<Object[]>} - 재순위된 문서 배열
 */
async function rerankDocuments(query, documents) {
  if (!documents || documents.length === 0) {
    return documents;
  }

  const scores = await rerank(query, documents);

  if (!scores) {
    // Reranker 실패 시 원본 순서 유지
    console.log('⚠️ Reranker 스킵 - 기존 순서 유지');
    return documents;
  }

  // 점수 순서대로 문서 재배열
  const rerankedDocuments = scores.map(({ index, score }) => ({
    ...documents[index],
    rerankerScore: score
  }));

  return rerankedDocuments;
}

/**
 * Reranker 사용 가능 여부 확인
 *
 * @returns {boolean}
 */
function isRerankerAvailable() {
  return !!HF_API_TOKEN;
}

/**
 * Redis 캐시 사용 가능 여부 확인
 *
 * @returns {boolean}
 */
function isCacheAvailable() {
  return !!(UPSTASH_REDIS_REST_URL && UPSTASH_REDIS_REST_TOKEN);
}

module.exports = {
  rerank,
  rerankDocuments,
  isRerankerAvailable,
  isCacheAvailable
};
