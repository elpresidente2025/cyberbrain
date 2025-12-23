/**
 * functions/services/rag/retriever.js
 * UID 기반 격리된 벡터 검색 및 RAG 컨텍스트 생성
 *
 * Firestore의 findNearest() 벡터 검색을 사용하여
 * 사용자의 데이터 내에서만 관련 청크를 검색합니다.
 */

'use strict';

const { getFirestore, FieldValue } = require('firebase-admin/firestore');
const { generateQueryEmbedding, cosineSimilarity } = require('./embedding');
const { getRelevantBioTypesForCategory } = require('./chunker');
const { rerankDocuments, isRerankerAvailable } = require('./reranker');
const { logError } = require('../../common/log');

const db = getFirestore();

// 기본 검색 옵션
const DEFAULT_RETRIEVAL_OPTIONS = {
  topK: 7,           // 반환할 최대 청크 수
  minScore: 0.55,    // 최소 유사도 점수
  distanceThreshold: 0.8,  // findNearest 거리 임계값
  useReranker: true  // BGE Reranker 사용 여부
};

// 컬렉션 경로
const EMBEDDINGS_COLLECTION = 'embeddings';
const CHUNKS_SUBCOLLECTION = 'chunks';

/**
 * 사용자의 청크 컬렉션에서 관련 청크 검색
 *
 * @param {string} uid - 사용자 UID
 * @param {string} query - 검색 쿼리 (원고 주제)
 * @param {Object} options - 검색 옵션
 * @returns {Promise<Object[]>} - 관련 청크 배열
 */
async function retrieveRelevantChunks(uid, query, options = {}) {
  if (!uid || !query) {
    console.warn('⚠️ RAG 검색: UID 또는 쿼리 누락');
    return [];
  }

  const { topK, minScore, distanceThreshold, useReranker } = { ...DEFAULT_RETRIEVAL_OPTIONS, ...options };

  console.log(`🔍 RAG 검색 시작: uid=${uid}, query="${query.substring(0, 50)}..."`);

  try {
    // 1. 쿼리 임베딩 생성
    console.log('🔢 쿼리 임베딩 생성 중...');
    const queryEmbedding = await generateQueryEmbedding(query);

    // 2. 청크 컬렉션 참조
    const chunksRef = db
      .collection(EMBEDDINGS_COLLECTION)
      .doc(uid)
      .collection(CHUNKS_SUBCOLLECTION);

    // UID equality 필터를 추가로 적용해 방어적인 닫힌 검색을 보장
    const chunksQuery = chunksRef.where('userId', '==', uid);

    // 3. 벡터 검색 실행 (findNearest)
    console.log(`🔍 벡터 검색 실행 (topK=${topK})...`);

    const vectorQuery = chunksQuery.findNearest('embedding', FieldValue.vector(queryEmbedding), {
      limit: topK * 2,  // 필터링 여유분 확보
      distanceMeasure: 'COSINE'
    });

    const snapshot = await vectorQuery.get();

    if (snapshot.empty) {
      console.log(`📭 ${uid}: 검색 결과 없음`);
      return [];
    }

    // 4. 결과 처리 및 점수 계산
    const results = [];

    for (const doc of snapshot.docs) {
      const data = doc.data();

      // 코사인 유사도 계산 (거리 → 유사도 변환)
      const embedding = data.embedding;
      let similarityScore = 0;

      if (embedding && embedding.toArray) {
        // Firestore Vector 객체에서 배열 추출
        const embeddingArray = embedding.toArray();
        similarityScore = cosineSimilarity(queryEmbedding, embeddingArray);
      }

      // 최소 점수 필터링
      if (similarityScore < minScore) {
        continue;
      }

      results.push({
        id: doc.id,
        text: data.chunkText,
        sourceType: data.sourceType,
        sourceEntryId: data.sourceEntryId,
        metadata: data.metadata || {},
        score: similarityScore,
        weight: data.metadata?.weight || 0.5
      });
    }

    // 5. Reranker 또는 기존 점수 기반 정렬
    let rankedResults;

    if (useReranker && isRerankerAvailable() && results.length > 1) {
      console.log('🔄 BGE Reranker로 재순위 중...');
      rankedResults = await rerankDocuments(query, results);
    } else {
      // Reranker 미사용 시 기존 방식 (가중치 적용 점수 정렬)
      results.sort((a, b) => {
        const scoreA = a.score * (1 + a.weight * 0.3);
        const scoreB = b.score * (1 + b.weight * 0.3);
        return scoreB - scoreA;
      });
      rankedResults = results;
    }

    // 6. Top-K 선택
    const topResults = rankedResults.slice(0, topK);

    console.log(`✅ RAG 검색 완료: ${topResults.length}개 청크 (총 ${results.length}개 중)`);

    return topResults;

  } catch (error) {
    console.error(`❌ RAG 검색 오류:`, error.message);
    logError('retrieveRelevantChunks', 'RAG 검색 실패', { uid, query: query.substring(0, 100), error: error.message });
    return [];
  }
}

/**
 * 카테고리 기반 재순위 (선택적)
 * 원고 카테고리와 관련된 Bio 타입에 가산점 부여
 *
 * @param {Object[]} chunks - 검색된 청크 배열
 * @param {string} category - 원고 카테고리
 * @returns {Object[]} - 재순위된 청크 배열
 */
function reRankBySourceType(chunks, category) {
  if (!chunks || chunks.length === 0 || !category) {
    return chunks;
  }

  const relevantTypes = getRelevantBioTypesForCategory(category);

  // 관련 타입에 가산점 부여
  const reRanked = chunks.map(chunk => {
    const typeIndex = relevantTypes.indexOf(chunk.sourceType);
    const typeBonus = typeIndex >= 0 ? (relevantTypes.length - typeIndex) * 0.05 : 0;

    return {
      ...chunk,
      adjustedScore: chunk.score + typeBonus
    };
  });

  // 조정된 점수로 재정렬
  reRanked.sort((a, b) => b.adjustedScore - a.adjustedScore);

  return reRanked;
}

/**
 * 검색된 청크들을 프롬프트용 텍스트로 포맷
 *
 * @param {Object[]} chunks - 검색된 청크 배열
 * @param {Object} options - 포맷 옵션
 * @returns {string} - 프롬프트에 삽입할 텍스트
 */
function formatChunksForPrompt(chunks, options = {}) {
  if (!chunks || chunks.length === 0) {
    return '';
  }

  const { showScore = false, showSource = true, maxChars = 2000 } = options;

  const typeNameMap = {
    'self_introduction': '자기소개',
    'policy': '정책/공약',
    'legislation': '법안/조례',
    'experience': '경험/활동',
    'achievement': '성과/실적',
    'vision': '비전/목표',
    'reference': '참고자료'
  };

  let formattedText = '';
  let currentLength = 0;

  for (let i = 0; i < chunks.length; i++) {
    const chunk = chunks[i];
    const typeName = typeNameMap[chunk.sourceType] || chunk.sourceType;

    let chunkText = '';

    if (showSource) {
      chunkText += `[${typeName}]`;
      if (chunk.metadata?.title) {
        chunkText += ` ${chunk.metadata.title}`;
      }
      chunkText += '\n';
    }

    chunkText += chunk.text;

    if (showScore) {
      chunkText += ` (관련도: ${(chunk.score * 100).toFixed(0)}%)`;
    }

    // 길이 제한 확인
    if (currentLength + chunkText.length > maxChars) {
      // 남은 공간에 맞게 잘라서 추가
      const remaining = maxChars - currentLength;
      if (remaining > 100) {
        formattedText += '\n\n' + chunkText.substring(0, remaining - 3) + '...';
      }
      break;
    }

    if (i > 0) {
      formattedText += '\n\n';
    }
    formattedText += chunkText;
    currentLength += chunkText.length;
  }

  return formattedText.trim();
}

/**
 * 통합 RAG 컨텍스트 생성
 * 검색 + 재순위 + 포맷을 한 번에 수행
 *
 * @param {string} uid - 사용자 UID
 * @param {string} topic - 원고 주제
 * @param {string} category - 원고 카테고리
 * @param {Object} options - 옵션
 * @returns {Promise<string>} - 프롬프트에 삽입할 RAG 컨텍스트
 */
async function generateRagContext(uid, topic, category, options = {}) {
  if (!uid || !topic) {
    return '';
  }

  try {
    // 1. 관련 청크 검색
    const chunks = await retrieveRelevantChunks(uid, topic, options);

    if (chunks.length === 0) {
      console.log(`📭 ${uid}: RAG 컨텍스트 없음`);
      return '';
    }

    // 2. 카테고리 기반 재순위
    const reRankedChunks = reRankBySourceType(chunks, category);

    // 3. 프롬프트용 텍스트 생성
    const ragContext = formatChunksForPrompt(reRankedChunks, {
      showScore: false,
      showSource: true,
      maxChars: 2500  // 프롬프트 내 RAG 컨텍스트 최대 길이
    });

    console.log(`✅ RAG 컨텍스트 생성 완료: ${ragContext.length}자 (${chunks.length}개 청크)`);

    return ragContext;

  } catch (error) {
    console.error(`❌ RAG 컨텍스트 생성 오류:`, error.message);
    return '';
  }
}

/**
 * RAG 검색 테스트용 함수
 *
 * @param {string} uid - 사용자 UID
 * @param {string} query - 검색 쿼리
 * @returns {Promise<Object>} - 상세 검색 결과
 */
async function testRagSearch(uid, query) {
  const startTime = Date.now();

  const chunks = await retrieveRelevantChunks(uid, query, { topK: 10, minScore: 0.4 });

  const endTime = Date.now();

  return {
    query,
    uid,
    resultsCount: chunks.length,
    latencyMs: endTime - startTime,
    results: chunks.map(c => ({
      text: c.text.substring(0, 100) + '...',
      sourceType: c.sourceType,
      score: c.score.toFixed(3),
      metadata: c.metadata
    }))
  };
}

module.exports = {
  retrieveRelevantChunks,
  reRankBySourceType,
  formatChunksForPrompt,
  generateRagContext,
  testRagSearch,
  DEFAULT_RETRIEVAL_OPTIONS
};
