/**
 * functions/handlers/bio.js
 * 사용자 자기소개 관리 및 메타데이터 추출 핸들러
 */

'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { onDocumentWritten } = require('firebase-functions/v2/firestore');
const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');
const { auth } = require('../common/auth');
const { logInfo, logError } = require('../common/log');
const { admin, db } = require('../utils/firebaseAdmin');
const { extractBioMetadata, generateOptimizationHints, extractStyleFingerprint } = require('../services/bio-analysis');
const { buildStyleGuidePrompt } = require('../services/stylometry');
const { BIO_ENTRY_TYPES, VALIDATION_RULES, TYPE_ANALYSIS_WEIGHTS } = require('../constants/bio-types');

// ============================================================================
// Bio CRUD Functions
// ============================================================================

/**
 * 사용자 자기소개 조회
 */
exports.getUserBio = wrap(async (req) => {
  const { uid } = await auth(req);
  logInfo('getUserBio 호출', { userId: uid });

  const bioDoc = await db.collection('bios').doc(uid).get();
  
  if (!bioDoc.exists) {
    logInfo('자기소개 없음', { userId: uid });
    return ok({ 
      bio: null,
      hasMetadata: false,
      message: '등록된 자기소개가 없습니다.'
    });
  }

  const bioData = bioDoc.data();
  logInfo('getUserBio 성공', { userId: uid, hasMetadata: !!bioData.extractedMetadata });
  
  return ok({ 
    bio: bioData,
    hasMetadata: !!bioData.extractedMetadata
  });
});

/**
 * Bio 엔트리 추가/업데이트 (새로운 구조화 시스템)
 */
exports.updateBioEntry = wrap(async (req) => {
  const { uid } = await auth(req);
  const { entryId, type, title, content, tags = [], weight = 1.0 } = req.data || {};
  
  // 입력 유효성 검사
  if (!type || !BIO_ENTRY_TYPES[type.toUpperCase()]) {
    throw new HttpsError('invalid-argument', '올바른 Bio 엔트리 타입을 선택해주세요.');
  }
  
  if (!content || typeof content !== 'string' || content.trim().length < VALIDATION_RULES.minContentLength) {
    throw new HttpsError('invalid-argument', `내용은 최소 ${VALIDATION_RULES.minContentLength}자 이상 입력해주세요.`);
  }

  const typeConfig = Object.values(BIO_ENTRY_TYPES).find(t => t.id === type);
  if (content.length > typeConfig.maxLength) {
    throw new HttpsError('invalid-argument', `${typeConfig.name}은 최대 ${typeConfig.maxLength}자까지 입력 가능합니다.`);
  }

  logInfo('updateBioEntry 호출', { userId: uid, type, contentLength: content.length });

  const bioRef = db.collection('bios').doc(uid);
  const existingDoc = await bioRef.get();
  const existingData = existingDoc.exists ? existingDoc.data() : {};
  const entries = existingData.entries || [];

  // 새로운 엔트리 생성 또는 기존 엔트리 업데이트
  const newEntry = {
    id: entryId || `entry_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    type,
    title: title || typeConfig.name,
    content: content.trim(),
    tags: Array.isArray(tags) ? tags.slice(0, 10) : [],
    weight: Math.max(0, Math.min(1, weight)),
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    updatedAt: admin.firestore.FieldValue.serverTimestamp()
  };

  let updatedEntries;
  if (entryId) {
    // 기존 엔트리 업데이트
    updatedEntries = entries.map(entry => 
      entry.id === entryId 
        ? { ...newEntry, createdAt: entry.createdAt }
        : entry
    );
    
    if (!updatedEntries.some(entry => entry.id === entryId)) {
      throw new HttpsError('not-found', '수정하려는 엔트리를 찾을 수 없습니다.');
    }
  } else {
    // 새 엔트리 추가
    if (entries.length >= VALIDATION_RULES.maxEntries) {
      throw new HttpsError('failed-precondition', `최대 ${VALIDATION_RULES.maxEntries}개의 엔트리까지 추가 가능합니다.`);
    }
    
    // 같은 타입의 엔트리 개수 확인
    const sameTypeCount = entries.filter(entry => entry.type === type).length;
    if (sameTypeCount >= VALIDATION_RULES.maxEntriesPerType) {
      throw new HttpsError('failed-precondition', `${typeConfig.name}은 최대 ${VALIDATION_RULES.maxEntriesPerType}개까지 추가 가능합니다.`);
    }

    updatedEntries = [...entries, newEntry];
  }

  // Bio 문서 업데이트
  const bioData = {
    userId: uid,
    entries: updatedEntries,
    version: (existingData.version || 0) + 1,
    updatedAt: admin.firestore.FieldValue.serverTimestamp(),
    
    // 메타데이터 추출 상태 초기화
    metadataStatus: 'pending',
    lastAnalyzed: null,
    
    // 사용 통계 유지
    usage: existingData.usage || {
      generatedPostsCount: 0,
      avgQualityScore: 0,
      lastUsedAt: null
    }
  };

  if (!existingDoc.exists) {
    bioData.createdAt = admin.firestore.FieldValue.serverTimestamp();
  }

  await bioRef.set(bioData, { merge: true });

  // 전체 엔트리 통합 메타데이터 추출 (비동기)
  extractEntriesMetadataAsync(uid, updatedEntries);

  // users 컬렉션 활성 상태 업데이트
  await db.collection('users').doc(uid).update({
    isActive: true,
    bioUpdatedAt: admin.firestore.FieldValue.serverTimestamp()
  });

  logInfo('updateBioEntry 성공', { userId: uid, entryId: newEntry.id, type });
  return ok({ 
    message: `${typeConfig.name}이 저장되었습니다. 메타데이터 분석이 진행 중입니다.`,
    entryId: newEntry.id,
    version: bioData.version
  });
});

/**
 * Bio 엔트리 삭제
 */
exports.deleteBioEntry = wrap(async (req) => {
  const { uid } = await auth(req);
  const { entryId } = req.data || {};
  
  if (!entryId) {
    throw new HttpsError('invalid-argument', '삭제할 엔트리 ID가 필요합니다.');
  }

  logInfo('deleteBioEntry 호출', { userId: uid, entryId });

  const bioRef = db.collection('bios').doc(uid);
  const bioDoc = await bioRef.get();
  
  if (!bioDoc.exists) {
    throw new HttpsError('not-found', 'Bio 데이터를 찾을 수 없습니다.');
  }

  const bioData = bioDoc.data();
  const entries = bioData.entries || [];
  const entryToDelete = entries.find(entry => entry.id === entryId);
  
  if (!entryToDelete) {
    throw new HttpsError('not-found', '삭제할 엔트리를 찾을 수 없습니다.');
  }

  // 필수 타입 삭제 방지
  if (VALIDATION_RULES.requiredTypes.includes(entryToDelete.type)) {
    const sameTypeCount = entries.filter(entry => entry.type === entryToDelete.type).length;
    if (sameTypeCount === 1) {
      const typeConfig = Object.values(BIO_ENTRY_TYPES).find(t => t.id === entryToDelete.type);
      throw new HttpsError('failed-precondition', `${typeConfig.name}은 최소 1개는 있어야 합니다.`);
    }
  }

  const updatedEntries = entries.filter(entry => entry.id !== entryId);

  await bioRef.update({
    entries: updatedEntries,
    version: (bioData.version || 0) + 1,
    updatedAt: admin.firestore.FieldValue.serverTimestamp(),
    metadataStatus: 'pending'
  });

  // 남은 엔트리들로 메타데이터 재분석 (비동기)
  if (updatedEntries.length > 0) {
    extractEntriesMetadataAsync(uid, updatedEntries);
  } else {
    // users 컬렉션 비활성 상태로 변경
    await db.collection('users').doc(uid).update({
      isActive: false,
      bioUpdatedAt: admin.firestore.FieldValue.serverTimestamp()
    });
  }

  logInfo('deleteBioEntry 성공', { userId: uid, entryId });
  return ok({ message: '엔트리가 삭제되었습니다.' });
});

/**
 * 사용자 자기소개 생성/업데이트 (기존 호환성 유지)
 */
exports.updateUserBio = wrap(async (req) => {
  const { uid } = await auth(req);
  const { content } = req.data || {};
  
  if (!content || typeof content !== 'string' || content.trim().length < 10) {
    throw new HttpsError('invalid-argument', '자기소개는 최소 10자 이상 입력해주세요.');
  }

  logInfo('updateUserBio 호출 (기존 호환성)', { userId: uid, contentLength: content.length });

  // 기존 방식을 새로운 엔트리 시스템으로 변환
  return exports.updateBioEntry.handler({
    auth: { uid },
    data: {
      type: 'self_introduction',
      title: '자기소개',
      content: content.trim(),
      tags: ['자기소개'],
      weight: 1.0
    }
  });
});

/**
 * 사용자 자기소개 삭제
 */
exports.deleteUserBio = wrap(async (req) => {
  const { uid } = await auth(req);
  logInfo('deleteUserBio 호출', { userId: uid });

  await db.collection('bios').doc(uid).delete();
  
  // users 컬렉션의 isActive 상태 업데이트
  await db.collection('users').doc(uid).update({
    isActive: false,
    bioUpdatedAt: admin.firestore.FieldValue.serverTimestamp()
  });

  logInfo('deleteUserBio 성공', { userId: uid });
  return ok({ message: '자기소개가 삭제되었습니다.' });
});

/**
 * 메타데이터 재분석 강제 실행
 */
exports.reanalyzeBioMetadata = wrap(async (req) => {
  const { uid } = await auth(req);
  logInfo('reanalyzeBioMetadata 호출', { userId: uid });

  const bioDoc = await db.collection('bios').doc(uid).get();
  if (!bioDoc.exists) {
    throw new HttpsError('not-found', '등록된 자기소개가 없습니다.');
  }

  const bioData = bioDoc.data();
  if (!bioData.content || bioData.content.length < 50) {
    throw new HttpsError('invalid-argument', '자기소개가 너무 짧아서 분석할 수 없습니다.');
  }

  // 메타데이터 분석 상태 업데이트
  await db.collection('bios').doc(uid).update({
    metadataStatus: 'analyzing',
    lastAnalyzed: admin.firestore.FieldValue.serverTimestamp()
  });

  try {
    const metadata = await extractBioMetadata(bioData.content);
    const hints = generateOptimizationHints(metadata);

    await db.collection('bios').doc(uid).update({
      extractedMetadata: metadata,
      optimizationHints: hints,
      metadataStatus: 'completed',
      lastAnalyzed: admin.firestore.FieldValue.serverTimestamp()
    });

    logInfo('reanalyzeBioMetadata 성공', { userId: uid });
    return ok({ 
      message: '메타데이터 분석이 완료되었습니다.',
      metadata: metadata,
      hints: hints
    });

  } catch (error) {
    logError('reanalyzeBioMetadata 실패', error, { userId: uid });
    
    await db.collection('bios').doc(uid).update({
      metadataStatus: 'failed',
      metadataError: error.message,
      lastAnalyzed: admin.firestore.FieldValue.serverTimestamp()
    });

    throw new HttpsError('internal', '메타데이터 분석에 실패했습니다: ' + error.message);
  }
});

// ============================================================================
// 비동기 메타데이터 추출 함수
// ============================================================================

/**
 * 백그라운드에서 메타데이터 추출 실행 (기존 단일 content 방식)
 */
async function extractMetadataAsync(uid, content) {
  try {
    console.log(`🧠 메타데이터 추출 시작: ${uid}`);
    
    // 분석 중 상태 업데이트
    await db.collection('bios').doc(uid).update({
      metadataStatus: 'analyzing'
    });

    const metadata = await extractBioMetadata(content);
    const hints = generateOptimizationHints(metadata);

    await db.collection('bios').doc(uid).update({
      extractedMetadata: metadata,
      optimizationHints: hints,
      metadataStatus: 'completed',
      lastAnalyzed: admin.firestore.FieldValue.serverTimestamp()
    });

    console.log(`✅ 메타데이터 추출 완료: ${uid}`);

  } catch (error) {
    console.error(`❌ 메타데이터 추출 실패: ${uid}`, error);
    
    await db.collection('bios').doc(uid).update({
      metadataStatus: 'failed',
      metadataError: error.message,
      lastAnalyzed: admin.firestore.FieldValue.serverTimestamp()
    });
  }
}

/**
 * 백그라운드에서 다중 엔트리 통합 메타데이터 추출 실행
 */
async function extractEntriesMetadataAsync(uid, entries) {
  try {
    console.log(`🧠 다중 엔트리 메타데이터 추출 시작: ${uid}`, { entriesCount: entries.length });
    
    // 분석 중 상태 업데이트
    await db.collection('bios').doc(uid).update({
      metadataStatus: 'analyzing'
    });

    // 엔트리들을 타입별로 그룹화하고 가중치 적용
    const typeGroupedEntries = {};
    let consolidatedContent = '';

    entries.forEach(entry => {
      if (!typeGroupedEntries[entry.type]) {
        typeGroupedEntries[entry.type] = [];
      }
      typeGroupedEntries[entry.type].push(entry);

      // 타입별 가중치를 적용해서 통합 텍스트 생성
      const typeWeight = TYPE_ANALYSIS_WEIGHTS[entry.type] || 0.5;
      const entryWeight = entry.weight || 1.0;
      const finalWeight = typeWeight * entryWeight;
      
      // 가중치에 따라 반복 추가 (높은 가중치일수록 더 많이 반영)
      const repetitions = Math.ceil(finalWeight * 3);
      for (let i = 0; i < repetitions; i++) {
        consolidatedContent += `\n[${entry.type.toUpperCase()}] ${entry.title}: ${entry.content}\n`;
      }
    });

    // 통합된 내용으로 메타데이터 추출
    const consolidatedMetadata = await extractBioMetadata(consolidatedContent);

    // 타입별 개별 메타데이터 추출 (선택적)
    const typeMetadata = {};
    for (const [type, typeEntries] of Object.entries(typeGroupedEntries)) {
      const typeContent = typeEntries.map(e => `${e.title}: ${e.content}`).join('\n\n');
      if (typeContent.length >= 100) { // 최소 길이 확보된 경우만
        try {
          typeMetadata[type] = await extractBioMetadata(typeContent);
        } catch (error) {
          console.warn(`타입별 메타데이터 추출 실패 (${type}):`, error.message);
        }
      }
    }

    const hints = generateOptimizationHints(consolidatedMetadata);

    // 🎨 Stylometry 분석 (Style Fingerprint 추출)
    let styleFingerprint = null;
    let styleGuide = '';
    try {
      console.log(`🎨 [Stylometry] 분석 시작: ${uid}`);
      styleFingerprint = await extractStyleFingerprint(consolidatedContent, {
        userName: '',
        region: ''
      });
      styleGuide = buildStyleGuidePrompt(styleFingerprint, {
        compact: false,
        sourceText: consolidatedContent
      });
      console.log(`✅ [Stylometry] 분석 완료: ${uid} (신뢰도: ${styleFingerprint?.analysisMetadata?.confidence || 0})`);
    } catch (styleError) {
      console.warn(`⚠️ [Stylometry] 분석 실패 (무시): ${uid}`, styleError.message);
    }

    await db.collection('bios').doc(uid).update({
      extractedMetadata: consolidatedMetadata,
      typeMetadata: typeMetadata,
      optimizationHints: hints,
      // 🎨 Style Fingerprint 저장
      styleFingerprint: styleFingerprint || null,
      styleGuide: styleGuide || '',
      metadataStatus: 'completed',
      lastAnalyzed: admin.firestore.FieldValue.serverTimestamp(),

      // 엔트리 정보도 함께 저장
      entryStats: {
        totalEntries: entries.length,
        typeDistribution: Object.keys(typeGroupedEntries).reduce((acc, type) => {
          acc[type] = typeGroupedEntries[type].length;
          return acc;
        }, {}),
        lastProcessedAt: admin.firestore.FieldValue.serverTimestamp()
      }
    });

    await db.collection('users').doc(uid).set({
      styleGuide: styleGuide || '',
      styleGuideUpdatedAt: admin.firestore.FieldValue.serverTimestamp()
    }, { merge: true });

    console.log(`✅ 다중 엔트리 메타데이터 추출 완료: ${uid}`, {
      entriesProcessed: entries.length,
      typesFound: Object.keys(typeGroupedEntries).length
    });

    // 🔍 RAG 인덱싱 트리거 (비동기 - 실패해도 메타데이터 추출은 완료)
    try {
      const { indexBioEntries } = require('../services/rag/indexer');
      const bioDoc = await db.collection('bios').doc(uid).get();
      const bioVersion = bioDoc.exists ? (bioDoc.data().version || 1) : 1;

      console.log(`🔄 RAG 인덱싱 시작: ${uid}`);
      await indexBioEntries(uid, entries, { bioVersion });
      console.log(`✅ RAG 인덱싱 완료: ${uid}`);
    } catch (ragError) {
      console.warn(`⚠️ RAG 인덱싱 실패 (무시): ${uid}`, ragError.message);
      // RAG 인덱싱 실패는 무시하고 계속 진행
    }

    // 🧠 LightRAG 지식 그래프 색인 (Python Cloud Function 호출)
    try {
      const { getFunctions } = require('firebase-admin/functions');
      const projectId = process.env.GCLOUD_PROJECT || process.env.GCP_PROJECT || 'ai-secretary-6e9c8';
      const region = 'asia-northeast3';
      const functionUrl = `https://${region}-${projectId}.cloudfunctions.net/index_bio_to_rag`;

      console.log(`🧠 LightRAG 색인 시작: ${uid}`);
      const response = await fetch(functionUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ uid, entries }),
        signal: AbortSignal.timeout(60000),
      });
      const result = await response.json();
      if (result.success) {
        console.log(`✅ LightRAG 색인 완료: ${uid} (${result.documentLength}자)`);
      } else {
        console.warn(`⚠️ LightRAG 색인 실패: ${uid}`, result.error);
      }
    } catch (lightragError) {
      console.warn(`⚠️ LightRAG 색인 실패 (무시): ${uid}`, lightragError.message);
    }

  } catch (error) {
    console.error(`❌ 다중 엔트리 메타데이터 추출 실패: ${uid}`, error);
    
    await db.collection('bios').doc(uid).update({
      metadataStatus: 'failed',
      metadataError: error.message,
      lastAnalyzed: admin.firestore.FieldValue.serverTimestamp()
    });
  }
}

// ============================================================================
// Firestore 트리거
// ============================================================================

/**
 * bios 컬렉션 변경 시 자동 메타데이터 추출 트리거
 */
exports.onBioUpdate = onDocumentWritten('bios/{userId}', async (event) => {
  const userId = event.params.userId;
  const newData = event.data?.after?.data();
  const oldData = event.data?.before?.data();

  // 문서가 삭제된 경우 처리하지 않음
  if (!newData) {
    console.log(`Bio 문서 삭제됨: ${userId}`);
    return null;
  }

  // content가 변경되었고, 50자 이상인 경우에만 메타데이터 추출
  const contentChanged = newData.content !== oldData?.content;
  const hasValidContent = newData.content && newData.content.length >= 50;
  const needsAnalysis = contentChanged && hasValidContent;

  console.log(`Bio 트리거 조건 체크: ${userId}`, {
    contentChanged,
    hasValidContent,
    needsAnalysis,
    contentLength: newData.content?.length || 0
  });

  if (needsAnalysis && newData.metadataStatus !== 'analyzing') {
    console.log(`🔄 Bio 변경 감지, 메타데이터 추출 시작: ${userId}`);
    extractMetadataAsync(userId, newData.content);
  }

  return null;
});

// extractMetadataAsync는 다른 핸들러에서 사용할 수 있도록 추가 export
module.exports.extractMetadataAsync = extractMetadataAsync;
