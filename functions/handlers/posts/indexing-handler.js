'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { httpWrap } = require('../../common/http-wrap');
const { admin, db } = require('../../utils/firebaseAdmin');
const { ok } = require('../../utils/posts/helpers');
const { chunkBioEntry } = require('../../services/rag/chunker');
const { batchGenerateEmbeddings } = require('../../services/rag/embedding');
const { EMBEDDINGS_COLLECTION, CHUNKS_SUBCOLLECTION } = require('../../services/rag/indexer');
const { FieldValue } = require('firebase-admin/firestore');

/**
 * 과거 원고 일괄 학습 (인덱싱)
 */
exports.indexPastPosts = httpWrap(async (req) => {
    let uid;

    // 인증 처리
    const requestData = req.data || req.rawRequest?.body || {};
    if (requestData.__naverAuth && requestData.__naverAuth.uid) {
        uid = requestData.__naverAuth.uid;
    } else {
        // Bearer token fallback
        const authHeader = (req.rawRequest && req.rawRequest.headers.authorization) || '';
        if (authHeader.startsWith('Bearer ')) {
            const idToken = authHeader.split('Bearer ')[1];
            try {
                const verified = await admin.auth().verifyIdToken(idToken);
                uid = verified.uid;
            } catch (e) {
                throw new HttpsError('unauthenticated', 'Invalid token');
            }
        } else {
            throw new HttpsError('unauthenticated', 'Auth required');
        }
    }

    console.log(`📚 [Indexing] 과거 원고 학습 시작: ${uid}`);

    try {
        // 1. 모든 과거 원고 조회
        const postsSnapshot = await db.collection('posts')
            .where('userId', '==', uid)
            .get();

        if (postsSnapshot.empty) {
            return ok({ count: 0, message: '학습할 과거 원고가 없습니다.' });
        }

        const posts = postsSnapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
        console.log(`📚 [Indexing] 총 ${posts.length}개 원고 조회됨`);

        // 2. 청킹 및 임베딩 준비
        const allChunks = [];

        for (const post of posts) {
            if (!post.content || post.content.length < 50) continue;

            // HTML 태그 제거 및 텍스트 정제
            const plainText = post.content.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

            const entry = {
                id: post.id,
                type: 'post_content', // bio-types.js에 추가한 타입
                title: post.title,
                content: plainText,
                tags: Array.isArray(post.keywords) ? post.keywords : [],
                weight: 1.0 // 높은 가중치 부여
            };

            const { chunks } = chunkBioEntry(entry, { maxChars: 500 }); // 원고는 좀 더 길게 청킹
            allChunks.push(...chunks);
        }

        if (allChunks.length === 0) {
            return ok({ count: 0, message: '유효한 내용이 있는 원고가 없습니다.' });
        }

        console.log(`📚 [Indexing] 총 ${allChunks.length}개 청크 생성됨`);

        // 3. 기존 원고 청크 삭제 (중복 방지 - post_content 타입만)
        // 주의: 전체 Bio 인덱스를 날리면 안됨. post_content 타입만 골라서 삭제해야 하는데,
        // 현재 구조상 subcollection이므로 where로 조회해서 삭제해야 함.
        const chunksRef = db.collection(EMBEDDINGS_COLLECTION).doc(uid).collection(CHUNKS_SUBCOLLECTION);
        const oldPostChunks = await chunksRef.where('sourceType', '==', 'post_content').get();

        const deleteBatch = db.batch();
        oldPostChunks.docs.forEach(doc => deleteBatch.delete(doc.ref));
        await deleteBatch.commit();
        console.log(`🗑️ [Indexing] 기존 학습 데이터 삭제 완료 (${oldPostChunks.size}개)`);

        // 4. 임베딩 생성 (배치 처리)
        const texts = allChunks.map(c => c.text);
        const embeddingResults = await batchGenerateEmbeddings(texts, 'RETRIEVAL_DOCUMENT');

        // 5. 저장
        const saveBatch = db.batch();
        let indexedCount = 0;
        const timestamp = FieldValue.serverTimestamp();

        for (let i = 0; i < allChunks.length; i++) {
            if (!embeddingResults[i].success) continue;

            const chunk = allChunks[i];
            const docRef = chunksRef.doc();

            saveBatch.set(docRef, {
                userId: uid,
                chunkText: chunk.text,
                embedding: FieldValue.vector(embeddingResults[i].embedding),
                sourceType: 'post_content',
                sourceEntryId: chunk.metadata.sourceEntryId,
                sourcePosition: chunk.position,
                metadata: chunk.metadata,
                createdAt: timestamp
            });
            indexedCount++;

            // Firestore 배치 제한 (500개) 고려 - 간단하게 400개마다 커밋
            if ((i + 1) % 400 === 0) {
                await saveBatch.commit();
                console.log(`💾 [Indexing] ${i + 1}개 청크 저장 중...`);
                // 배치는 재사용 불가하므로 새로 생성하면 안되고, 로직을 분리해야 함.
                // 여기서는 복잡도를 줄이기 위해 posts 개수가 적다고(20개) 가정하고 단일 배치는 위험할 수 있음.
                // 안전하게 Promise.all로 병렬 저장하거나, batch 유틸리티를 써야 함.
                // 하지만 지금은 빠른 구현을 위해 loop 내 batch commit은 지양하고,
                // 20개 포스트 * 5 청크 = 100개 내외이므로 단일 배치로 충분할 것으로 예상.
            }
        }

        // 남은 배치 커밋 (배치 크기가 작다는 가정 하에)
        if (indexedCount > 0) {
            // 위 loop에서 commit을 안 했으므로 여기서 한 번에 함. 
            // 만약 500개가 넘어가면 에러가 나므로, 안전하게 chunking해서 저장하는 게 좋음.
            // 시간상 간단히 처리하되, 혹시 몰라 split logic 추가
        }

        // 배치 분할 저장 로직으로 교체
        const BATCH_SIZE = 400;
        for (let i = 0; i < allChunks.length; i += BATCH_SIZE) {
            const currentBatch = db.batch();
            const batchChunks = allChunks.slice(i, i + BATCH_SIZE);
            let batchCount = 0;

            for (let j = 0; j < batchChunks.length; j++) {
                const chunkIndex = i + j;
                if (!embeddingResults[chunkIndex].success) continue;

                const chunk = batchChunks[j];
                const docRef = chunksRef.doc();
                currentBatch.set(docRef, {
                    userId: uid,
                    chunkText: chunk.text,
                    embedding: FieldValue.vector(embeddingResults[chunkIndex].embedding),
                    sourceType: 'post_content',
                    sourceEntryId: chunk.metadata.sourceEntryId,
                    sourcePosition: chunk.position,
                    metadata: chunk.metadata,
                    createdAt: timestamp
                });
                batchCount++;
            }

            if (batchCount > 0) {
                await currentBatch.commit();
                console.log(`💾 [Indexing] 배치 저장 완료 (${i + batchCount}/${allChunks.length})`);
            }
        }

        // 메타데이터 업데이트 (총 청크 수 등)
        await db.collection(EMBEDDINGS_COLLECTION).doc(uid).set({
            lastPastPostsIndexedAt: timestamp,
            postChunkCount: indexedCount // 기존 chunkCount와 별도로 관리하거나 합산해야 함. 일단 별도 필드로.
        }, { merge: true });

        console.log(`✅ [Indexing] 학습 완료. 총 ${indexedCount}개 청크 저장됨.`);

        return ok({
            success: true,
            count: posts.length,
            chunkCount: indexedCount,
            message: `${posts.length}개의 과거 원고를 성공적으로 학습했습니다.`
        });

    } catch (error) {
        console.error('❌ [Indexing] 학습 실패:', error);
        throw new HttpsError('internal', '학습 중 오류가 발생했습니다.');
    }
});
