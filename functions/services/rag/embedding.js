/**
 * functions/services/rag/embedding.js
 * Gemini text-embedding-004 모델을 사용한 텍스트 임베딩 서비스
 * RAG 시스템의 핵심 구성요소로, 텍스트를 768차원 벡터로 변환합니다.
 */

'use strict';

const { GoogleGenerativeAI } = require('@google/generative-ai');
const { logError } = require('../../common/log');
const { getGeminiApiKey } = require('../../common/secrets');

// Gemini API 키는 시크릿/환경변수에서 조회

// 임베딩 모델 설정
const EMBEDDING_MODEL = 'text-embedding-004';
const EMBEDDING_DIMENSION = 768;

// 배치 처리 설정
const DEFAULT_BATCH_SIZE = 10;
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;

/**
 * 단일 텍스트의 임베딩 벡터 생성
 *
 * @param {string} text - 임베딩할 텍스트
 * @param {string} taskType - 작업 유형 ('RETRIEVAL_DOCUMENT' | 'RETRIEVAL_QUERY')
 * @returns {Promise<number[]>} - 768차원 임베딩 벡터
 */
async function generateEmbedding(text, taskType = 'RETRIEVAL_DOCUMENT') {
  const apiKey = getGeminiApiKey();
  if (!apiKey) {
    logError('generateEmbedding', 'Gemini API 키가 설정되지 않았습니다.');
    throw new Error('AI 서비스 설정 오류: API 키 누락');
  }

  if (!text || text.trim().length === 0) {
    throw new Error('임베딩할 텍스트가 비어있습니다.');
  }

  const genAI = new GoogleGenerativeAI(apiKey);
  const model = genAI.getGenerativeModel({ model: EMBEDDING_MODEL });

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      console.log(`🔢 임베딩 생성 시도 (${attempt}/${MAX_RETRIES}) - ${text.length}자`);

      const result = await model.embedContent({
        content: { parts: [{ text: text.trim() }] },
        taskType: taskType
      });

      const embedding = result.embedding.values;

      if (!embedding || embedding.length !== EMBEDDING_DIMENSION) {
        throw new Error(`잘못된 임베딩 차원: ${embedding?.length || 0} (예상: ${EMBEDDING_DIMENSION})`);
      }

      console.log(`✅ 임베딩 생성 성공 (${EMBEDDING_DIMENSION}차원)`);
      return embedding;

    } catch (error) {
      console.error(`❌ 임베딩 생성 오류 (시도 ${attempt}):`, error.message);
      logError('generateEmbedding', `임베딩 생성 시도 ${attempt} 실패`, {
        error: error.message,
        textLength: text.length,
        taskType
      });

      if (attempt === MAX_RETRIES) {
        throw new Error(`임베딩 생성 실패 (${MAX_RETRIES}회 시도 후): ${error.message}`);
      }

      // 재시도 전 대기 (Exponential backoff)
      await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS * attempt));
    }
  }
}

/**
 * 검색 쿼리용 임베딩 생성 (RETRIEVAL_QUERY 타입)
 *
 * @param {string} query - 검색 쿼리 텍스트
 * @returns {Promise<number[]>} - 768차원 임베딩 벡터
 */
async function generateQueryEmbedding(query) {
  return generateEmbedding(query, 'RETRIEVAL_QUERY');
}

/**
 * 문서 저장용 임베딩 생성 (RETRIEVAL_DOCUMENT 타입)
 *
 * @param {string} document - 문서 텍스트
 * @returns {Promise<number[]>} - 768차원 임베딩 벡터
 */
async function generateDocumentEmbedding(document) {
  return generateEmbedding(document, 'RETRIEVAL_DOCUMENT');
}

/**
 * 여러 텍스트의 임베딩을 배치로 생성
 * API 호출 횟수를 줄이고 효율성을 높입니다.
 *
 * @param {string[]} texts - 임베딩할 텍스트 배열
 * @param {string} taskType - 작업 유형
 * @param {number} batchSize - 배치 크기 (기본: 10)
 * @returns {Promise<Array<{text: string, embedding: number[], success: boolean, error?: string}>>}
 */
async function batchGenerateEmbeddings(texts, taskType = 'RETRIEVAL_DOCUMENT', batchSize = DEFAULT_BATCH_SIZE) {
  if (!texts || texts.length === 0) {
    return [];
  }

  console.log(`📦 배치 임베딩 시작: ${texts.length}개 텍스트, 배치 크기: ${batchSize}`);

  const results = [];
  const batches = [];

  // 텍스트를 배치로 분할
  for (let i = 0; i < texts.length; i += batchSize) {
    batches.push(texts.slice(i, i + batchSize));
  }

  console.log(`📦 총 ${batches.length}개 배치 처리 예정`);

  for (let batchIndex = 0; batchIndex < batches.length; batchIndex++) {
    const batch = batches[batchIndex];
    console.log(`📦 배치 ${batchIndex + 1}/${batches.length} 처리 중 (${batch.length}개)`);

    // 각 배치 내 텍스트를 병렬로 처리
    const batchPromises = batch.map(async (text, textIndex) => {
      try {
        const embedding = await generateEmbedding(text, taskType);
        return {
          text,
          embedding,
          success: true,
          index: batchIndex * batchSize + textIndex
        };
      } catch (error) {
        console.warn(`⚠️ 텍스트 임베딩 실패 (${text.substring(0, 30)}...): ${error.message}`);
        return {
          text,
          embedding: null,
          success: false,
          error: error.message,
          index: batchIndex * batchSize + textIndex
        };
      }
    });

    const batchResults = await Promise.all(batchPromises);
    results.push(...batchResults);

    // 배치 간 딜레이 (API 레이트 리밋 방지)
    if (batchIndex < batches.length - 1) {
      await new Promise(resolve => setTimeout(resolve, 200));
    }
  }

  const successCount = results.filter(r => r.success).length;
  console.log(`📦 배치 임베딩 완료: ${successCount}/${texts.length} 성공`);

  return results;
}

/**
 * 두 임베딩 벡터 간의 코사인 유사도 계산
 *
 * @param {number[]} embedding1 - 첫 번째 임베딩 벡터
 * @param {number[]} embedding2 - 두 번째 임베딩 벡터
 * @returns {number} - 코사인 유사도 (-1 ~ 1)
 */
function cosineSimilarity(embedding1, embedding2) {
  if (!embedding1 || !embedding2 || embedding1.length !== embedding2.length) {
    throw new Error('유효하지 않은 임베딩 벡터');
  }

  let dotProduct = 0;
  let norm1 = 0;
  let norm2 = 0;

  for (let i = 0; i < embedding1.length; i++) {
    dotProduct += embedding1[i] * embedding2[i];
    norm1 += embedding1[i] * embedding1[i];
    norm2 += embedding2[i] * embedding2[i];
  }

  norm1 = Math.sqrt(norm1);
  norm2 = Math.sqrt(norm2);

  if (norm1 === 0 || norm2 === 0) {
    return 0;
  }

  return dotProduct / (norm1 * norm2);
}

module.exports = {
  generateEmbedding,
  generateQueryEmbedding,
  generateDocumentEmbedding,
  batchGenerateEmbeddings,
  cosineSimilarity,
  EMBEDDING_DIMENSION,
  EMBEDDING_MODEL
};
