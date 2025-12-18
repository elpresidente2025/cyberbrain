/**
 * functions/services/rag/indexer.js
 * Bio 데이터를 벡터 임베딩으로 변환하여 Firestore에 저장하는 인덱싱 파이프라인
 *
 * 스키마: embeddings/{uid}/chunks/{chunkId}
 */

'use strict';

const { getFirestore, FieldValue } = require('firebase-admin/firestore');
const { batchGenerateEmbeddings, EMBEDDING_DIMENSION } = require('./embedding');
const { chunkBioEntries } = require('./chunker');
const { logError } = require('../../common/log');

const db = getFirestore();

// 컬렉션 경로
const EMBEDDINGS_COLLECTION = 'embeddings';
const CHUNKS_SUBCOLLECTION = 'chunks';

/**
 * 사용자의 임베딩 청크 컬렉션 참조 반환
 *
 * @param {string} uid - 사용자 UID
 * @returns {FirebaseFirestore.CollectionReference}
 */
function getChunksCollection(uid) {
  return db.collection(EMBEDDINGS_COLLECTION).doc(uid).collection(CHUNKS_SUBCOLLECTION);
}

/**
 * Bio 엔트리들을 임베딩으로 변환하여 저장
 *
 * @param {string} uid - 사용자 UID
 * @param {Object[]} entries - Bio 엔트리 배열
 * @param {Object} options - 옵션
 * @param {number} options.bioVersion - Bio 문서 버전
 * @returns {Promise<Object>} - { indexed: number, failed: number, removed: number }
 */
async function indexBioEntries(uid, entries, options = {}) {
  if (!uid) {
    throw new Error('UID가 필요합니다.');
  }

  if (!entries || entries.length === 0) {
    console.log(`📭 ${uid}: 인덱싱할 엔트리가 없습니다.`);
    return { indexed: 0, failed: 0, removed: 0 };
  }

  console.log(`🔄 ${uid}: Bio 인덱싱 시작 (${entries.length}개 엔트리)`);

  const { bioVersion = 1 } = options;
  const chunksRef = getChunksCollection(uid);

  try {
    // 1. 기존 청크 삭제 (전체 재인덱싱)
    const existingChunks = await chunksRef.get();
    const deletePromises = existingChunks.docs.map(doc => doc.ref.delete());
    await Promise.all(deletePromises);
    console.log(`🗑️ ${uid}: 기존 ${existingChunks.size}개 청크 삭제`);

    // 2. 엔트리 청킹
    const { allChunks, stats } = chunkBioEntries(entries);

    if (allChunks.length === 0) {
      console.log(`📭 ${uid}: 생성된 청크가 없습니다.`);
      return { indexed: 0, failed: 0, removed: existingChunks.size };
    }

    // 3. 임베딩 생성 (배치)
    console.log(`🔢 ${uid}: ${allChunks.length}개 청크 임베딩 생성 중...`);
    const texts = allChunks.map(c => c.text);
    const embeddingResults = await batchGenerateEmbeddings(texts, 'RETRIEVAL_DOCUMENT');

    // 4. Firestore에 저장
    let indexed = 0;
    let failed = 0;
    const batch = db.batch();
    const timestamp = FieldValue.serverTimestamp();

    for (let i = 0; i < allChunks.length; i++) {
      const chunk = allChunks[i];
      const embeddingResult = embeddingResults[i];

      if (!embeddingResult.success || !embeddingResult.embedding) {
        console.warn(`⚠️ 청크 ${i} 임베딩 실패: ${embeddingResult.error}`);
        failed++;
        continue;
      }

      const chunkDoc = chunksRef.doc();
      batch.set(chunkDoc, {
        userId: uid,
        chunkText: chunk.text,
        embedding: FieldValue.vector(embeddingResult.embedding),
        sourceType: chunk.metadata.sourceType,
        sourceEntryId: chunk.metadata.sourceEntryId,
        sourcePosition: chunk.position,
        metadata: {
          title: chunk.metadata.title,
          tags: chunk.metadata.tags,
          weight: chunk.metadata.weight,
          charLength: chunk.metadata.charLength,
          totalChunks: chunk.metadata.totalChunks
        },
        bioVersion,
        createdAt: timestamp
      });

      indexed++;
    }

    await batch.commit();

    // 5. 메타문서 업데이트 (인덱싱 상태)
    await db.collection(EMBEDDINGS_COLLECTION).doc(uid).set({
      lastIndexedAt: timestamp,
      bioVersion,
      chunkCount: indexed,
      entriesCount: entries.length,
      stats: {
        totalChars: stats.totalChars,
        avgChunkSize: stats.avgChunkSize
      }
    }, { merge: true });

    console.log(`✅ ${uid}: 인덱싱 완료 - ${indexed}개 성공, ${failed}개 실패`);

    return {
      indexed,
      failed,
      removed: existingChunks.size
    };

  } catch (error) {
    console.error(`❌ ${uid}: 인덱싱 오류:`, error.message);
    logError('indexBioEntries', `Bio 인덱싱 실패`, { uid, error: error.message });
    throw error;
  }
}

/**
 * 주문형 인덱싱 (원고 생성 시 인덱스가 없거나 오래된 경우)
 *
 * @param {string} uid - 사용자 UID
 * @param {Object} bioDoc - Bio 문서 데이터
 * @returns {Promise<boolean>} - 인덱싱 수행 여부
 */
async function indexOnDemand(uid, bioDoc) {
  if (!uid || !bioDoc) {
    return false;
  }

  const entries = bioDoc.entries || [];
  if (entries.length === 0) {
    return false;
  }

  try {
    // 현재 인덱스 상태 확인
    const metaDoc = await db.collection(EMBEDDINGS_COLLECTION).doc(uid).get();
    const meta = metaDoc.exists ? metaDoc.data() : null;

    // Bio 버전 확인
    const currentBioVersion = bioDoc.version || 1;
    const indexedBioVersion = meta?.bioVersion || 0;

    // 인덱스가 최신이면 스킵
    if (meta && indexedBioVersion >= currentBioVersion && meta.chunkCount > 0) {
      console.log(`✅ ${uid}: 인덱스가 최신 상태 (v${indexedBioVersion})`);
      return false;
    }

    // 인덱싱 필요
    console.log(`🔄 ${uid}: 주문형 인덱싱 시작 (v${indexedBioVersion} → v${currentBioVersion})`);
    await indexBioEntries(uid, entries, { bioVersion: currentBioVersion });
    return true;

  } catch (error) {
    console.error(`❌ ${uid}: 주문형 인덱싱 실패:`, error.message);
    // 실패해도 원고 생성은 계속 진행
    return false;
  }
}

/**
 * 사용자의 모든 임베딩 청크 삭제
 *
 * @param {string} uid - 사용자 UID
 * @returns {Promise<number>} - 삭제된 청크 수
 */
async function removeAllChunks(uid) {
  if (!uid) {
    return 0;
  }

  const chunksRef = getChunksCollection(uid);
  const chunks = await chunksRef.get();

  if (chunks.empty) {
    return 0;
  }

  const batch = db.batch();
  chunks.docs.forEach(doc => batch.delete(doc.ref));
  await batch.commit();

  // 메타문서도 삭제
  await db.collection(EMBEDDINGS_COLLECTION).doc(uid).delete();

  console.log(`🗑️ ${uid}: ${chunks.size}개 청크 삭제 완료`);
  return chunks.size;
}

/**
 * 인덱스 상태 조회
 *
 * @param {string} uid - 사용자 UID
 * @returns {Promise<Object|null>} - 인덱스 메타데이터
 */
async function getIndexStatus(uid) {
  if (!uid) {
    return null;
  }

  try {
    const metaDoc = await db.collection(EMBEDDINGS_COLLECTION).doc(uid).get();

    if (!metaDoc.exists) {
      return {
        indexed: false,
        chunkCount: 0,
        bioVersion: 0,
        lastIndexedAt: null
      };
    }

    const data = metaDoc.data();
    return {
      indexed: true,
      chunkCount: data.chunkCount || 0,
      entriesCount: data.entriesCount || 0,
      bioVersion: data.bioVersion || 0,
      lastIndexedAt: data.lastIndexedAt?.toDate() || null,
      stats: data.stats || {}
    };

  } catch (error) {
    console.error(`❌ ${uid}: 인덱스 상태 조회 실패:`, error.message);
    return null;
  }
}

/**
 * 전체 사용자 인덱스 재구축 (관리용)
 *
 * @param {string[]} uids - 재구축할 사용자 UID 배열
 * @returns {Promise<Object>} - { success: number, failed: number }
 */
async function rebuildIndexes(uids) {
  let success = 0;
  let failed = 0;

  for (const uid of uids) {
    try {
      // Bio 문서 조회
      const bioDoc = await db.collection('bios').doc(uid).get();

      if (!bioDoc.exists) {
        console.log(`⚠️ ${uid}: Bio 문서 없음 - 스킵`);
        continue;
      }

      const bioData = bioDoc.data();
      const entries = bioData.entries || [];

      if (entries.length === 0) {
        console.log(`⚠️ ${uid}: 엔트리 없음 - 스킵`);
        continue;
      }

      await indexBioEntries(uid, entries, { bioVersion: bioData.version || 1 });
      success++;

    } catch (error) {
      console.error(`❌ ${uid}: 재구축 실패:`, error.message);
      failed++;
    }
  }

  return { success, failed };
}

module.exports = {
  indexBioEntries,
  indexOnDemand,
  removeAllChunks,
  getIndexStatus,
  rebuildIndexes,
  getChunksCollection,
  EMBEDDINGS_COLLECTION,
  CHUNKS_SUBCOLLECTION
};
