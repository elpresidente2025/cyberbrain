/**
 * functions/services/rag/chunker.js
 * 한국어 텍스트의 의미 기반 청킹 서비스
 * Bio 엔트리를 임베딩에 적합한 크기로 분할합니다.
 */

'use strict';

const { BIO_ENTRY_TYPES, TYPE_ANALYSIS_WEIGHTS } = require('../../constants/bio-types');

// 청킹 설정
const DEFAULT_CHUNK_OPTIONS = {
  maxChars: 350,       // 최대 청크 크기 (문자)
  minChars: 50,        // 최소 청크 크기
  overlap: 50,         // 청크 간 오버랩 (문맥 연속성)
  preserveSentences: true  // 문장 경계 보존
};

// 한국어 문장 종결 패턴
const KOREAN_SENTENCE_ENDINGS = /([.!?。？！])\s*/g;
const KOREAN_SENTENCE_SPLIT = /(?<=[.!?。？！])\s+/;

// 한국어 문단 구분자
const PARAGRAPH_SEPARATORS = /\n\n+|\r\n\r\n+/;

/**
 * 한국어 문장 경계 감지
 *
 * @param {string} text - 분석할 텍스트
 * @returns {number[]} - 문장 종료 위치 배열
 */
function detectKoreanSentenceBoundaries(text) {
  const boundaries = [];
  let match;

  const regex = /[.!?。？！]\s*/g;
  while ((match = regex.exec(text)) !== null) {
    boundaries.push(match.index + match[0].length);
  }

  return boundaries;
}

/**
 * 텍스트를 문장 단위로 분리
 *
 * @param {string} text - 분리할 텍스트
 * @returns {string[]} - 문장 배열
 */
function splitIntoSentences(text) {
  if (!text || text.trim().length === 0) {
    return [];
  }

  // 문장 종결 패턴으로 분리
  const sentences = text
    .split(KOREAN_SENTENCE_SPLIT)
    .map(s => s.trim())
    .filter(s => s.length > 0);

  // 분리가 안 되면 원본 반환
  if (sentences.length === 0) {
    return [text.trim()];
  }

  return sentences;
}

/**
 * 문장들을 청크로 결합
 * 최대 크기를 초과하지 않도록 문장을 그룹화합니다.
 *
 * @param {string[]} sentences - 문장 배열
 * @param {Object} options - 청킹 옵션
 * @returns {string[]} - 청크 배열
 */
function combineSentencesIntoChunks(sentences, options = {}) {
  const { maxChars, minChars, overlap } = { ...DEFAULT_CHUNK_OPTIONS, ...options };
  const chunks = [];
  let currentChunk = '';
  let overlapBuffer = '';

  for (let i = 0; i < sentences.length; i++) {
    const sentence = sentences[i];

    // 현재 청크에 문장 추가 가능 여부 확인
    const potentialChunk = currentChunk ? `${currentChunk} ${sentence}` : sentence;

    if (potentialChunk.length <= maxChars) {
      // 청크에 문장 추가
      currentChunk = potentialChunk;
    } else {
      // 현재 청크가 최소 크기 이상이면 저장
      if (currentChunk.length >= minChars) {
        chunks.push(currentChunk.trim());

        // 오버랩 처리: 마지막 문장을 다음 청크 시작에 포함
        if (overlap > 0 && currentChunk.length > overlap) {
          overlapBuffer = currentChunk.slice(-overlap);
        }
      }

      // 새 청크 시작 (오버랩 포함)
      currentChunk = overlapBuffer ? `${overlapBuffer} ${sentence}` : sentence;
      overlapBuffer = '';
    }
  }

  // 마지막 청크 저장
  if (currentChunk.trim().length >= minChars) {
    chunks.push(currentChunk.trim());
  } else if (currentChunk.trim().length > 0 && chunks.length > 0) {
    // 마지막 청크가 너무 짧으면 이전 청크에 병합
    chunks[chunks.length - 1] = `${chunks[chunks.length - 1]} ${currentChunk.trim()}`;
  } else if (currentChunk.trim().length > 0) {
    // 전체 텍스트가 하나의 짧은 청크인 경우
    chunks.push(currentChunk.trim());
  }

  return chunks;
}

/**
 * 텍스트를 청크로 분할
 *
 * @param {string} text - 분할할 텍스트
 * @param {Object} options - 청킹 옵션
 * @returns {string[]} - 청크 배열
 */
function chunkText(text, options = {}) {
  if (!text || text.trim().length === 0) {
    return [];
  }

  const mergedOptions = { ...DEFAULT_CHUNK_OPTIONS, ...options };
  const cleanText = text.trim();

  // 텍스트가 최대 크기보다 작으면 그대로 반환
  if (cleanText.length <= mergedOptions.maxChars) {
    return [cleanText];
  }

  // 문장 분리
  const sentences = splitIntoSentences(cleanText);

  // 문장을 청크로 결합
  const chunks = combineSentencesIntoChunks(sentences, mergedOptions);

  return chunks;
}

/**
 * Bio 엔트리를 청크로 분할
 * 엔트리 타입에 따른 메타데이터를 포함합니다.
 *
 * @param {Object} entry - Bio 엔트리 객체
 * @param {string} entry.id - 엔트리 ID
 * @param {string} entry.type - 엔트리 타입 (self_introduction, policy, etc.)
 * @param {string} entry.title - 엔트리 제목
 * @param {string} entry.content - 엔트리 내용
 * @param {string[]} entry.tags - 태그 배열
 * @param {number} entry.weight - 가중치
 * @param {Object} options - 청킹 옵션
 * @returns {Object} - { chunks: Array<{text, position, metadata}>, entryMetadata }
 */
function chunkBioEntry(entry, options = {}) {
  if (!entry || !entry.content) {
    return { chunks: [], entryMetadata: null };
  }

  const { id, type, title, content, tags = [], weight = 0.5 } = entry;
  const mergedOptions = { ...DEFAULT_CHUNK_OPTIONS, ...options };

  // 제목이 있으면 내용 앞에 추가 (컨텍스트 제공)
  const fullText = title ? `[${title}] ${content}` : content;

  // 텍스트 청킹
  const textChunks = chunkText(fullText, mergedOptions);

  // 엔트리 타입 정보 조회
  const typeConfig = Object.values(BIO_ENTRY_TYPES).find(t => t.id === type);
  const analysisWeight = TYPE_ANALYSIS_WEIGHTS[type] || 0.5;

  // 청크에 메타데이터 추가
  const chunks = textChunks.map((text, position) => ({
    text,
    position,
    metadata: {
      sourceEntryId: id,
      sourceType: type,
      sourceTypeName: typeConfig?.name || type,
      title: title || '',
      tags: tags,
      weight: weight * analysisWeight,
      charLength: text.length,
      totalChunks: textChunks.length
    }
  }));

  // 엔트리 전체 메타데이터
  const entryMetadata = {
    entryId: id,
    entryType: type,
    entryTypeName: typeConfig?.name || type,
    title,
    originalLength: content.length,
    chunkCount: chunks.length,
    analysisWeight,
    tags
  };

  return { chunks, entryMetadata };
}

/**
 * 여러 Bio 엔트리를 일괄 청킹
 *
 * @param {Object[]} entries - Bio 엔트리 배열
 * @param {Object} options - 청킹 옵션
 * @returns {Object} - { allChunks, entriesMetadata, stats }
 */
function chunkBioEntries(entries, options = {}) {
  if (!entries || entries.length === 0) {
    return {
      allChunks: [],
      entriesMetadata: [],
      stats: { totalEntries: 0, totalChunks: 0, totalChars: 0 }
    };
  }

  const allChunks = [];
  const entriesMetadata = [];
  let totalChars = 0;

  for (const entry of entries) {
    const { chunks, entryMetadata } = chunkBioEntry(entry, options);

    if (chunks.length > 0) {
      allChunks.push(...chunks);
      entriesMetadata.push(entryMetadata);
      totalChars += chunks.reduce((sum, c) => sum + c.text.length, 0);
    }
  }

  const stats = {
    totalEntries: entries.length,
    processedEntries: entriesMetadata.length,
    totalChunks: allChunks.length,
    totalChars,
    avgChunkSize: allChunks.length > 0 ? Math.round(totalChars / allChunks.length) : 0
  };

  console.log(`📝 청킹 완료:`, stats);

  return { allChunks, entriesMetadata, stats };
}

/**
 * 카테고리와 관련된 Bio 타입 필터링
 * 원고 카테고리에 따라 관련성 높은 타입을 우선합니다.
 *
 * @param {string} category - 원고 카테고리
 * @returns {string[]} - 관련 타입 ID 배열 (우선순위 순)
 */
function getRelevantBioTypesForCategory(category) {
  const typeMapping = {
    '일상소통': ['self_introduction', 'experience', 'vision'],
    '정책제안': ['policy', 'legislation', 'vision', 'achievement'],
    '의정활동': ['achievement', 'legislation', 'experience', 'policy'],
    '시사비평': ['policy', 'vision', 'self_introduction'],
    '지역현안': ['experience', 'achievement', 'policy', 'self_introduction']
  };

  return typeMapping[category] || Object.values(BIO_ENTRY_TYPES).map(t => t.id);
}

module.exports = {
  chunkText,
  chunkBioEntry,
  chunkBioEntries,
  splitIntoSentences,
  detectKoreanSentenceBoundaries,
  getRelevantBioTypesForCategory,
  DEFAULT_CHUNK_OPTIONS
};
