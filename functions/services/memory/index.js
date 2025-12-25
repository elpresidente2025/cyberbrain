'use strict';

/**
 * Memory Systems - 사용자별 장기 메모리 관리
 *
 * Context Engineering 적용:
 * - 단기 메모리: 현재 세션 (기존 activeGenerationSession)
 * - 장기 메모리: 선호도, 패턴, 피드백 (user_memory)
 * - 에피소딕 메모리: 잘된 글 예시 (best_posts)
 */

const { admin, db } = require('../../utils/firebaseAdmin');

// ============================================================================
// 장기 메모리 (Long-term Memory)
// ============================================================================

/**
 * 사용자 메모리 조회
 * @param {string} uid - 사용자 ID
 * @returns {Promise<Object>} 메모리 데이터
 */
async function getUserMemory(uid) {
  if (!uid) return null;

  try {
    const memoryDoc = await db.collection('users').doc(uid)
      .collection('memory').doc('preferences').get();

    if (!memoryDoc.exists) {
      return getDefaultMemory();
    }

    return memoryDoc.data();
  } catch (error) {
    console.warn('⚠️ [Memory] 메모리 조회 실패:', error.message);
    return getDefaultMemory();
  }
}

/**
 * 기본 메모리 구조
 */
function getDefaultMemory() {
  return {
    preferences: {
      favoriteKeywords: [],
      preferredLength: 'medium',
      preferredTone: null,
      avoidKeywords: []
    },
    patterns: {
      commonPhrases: [],
      effectiveOpenings: [],
      effectiveClosings: []
    },
    feedback: {
      liked: [],
      disliked: []
    },
    stats: {
      totalGenerated: 0,
      totalSelected: 0,
      selectionRate: 0,
      categoryBreakdown: {}
    }
  };
}

/**
 * 사용자 메모리 업데이트 (생성 완료 시)
 * @param {string} uid - 사용자 ID
 * @param {Object} postData - 생성된 글 데이터
 */
async function updateMemoryOnGeneration(uid, postData) {
  if (!uid || !postData) return;

  const { category, keywords = [] } = postData;
  const memoryRef = db.collection('users').doc(uid)
    .collection('memory').doc('preferences');

  try {
    await db.runTransaction(async (tx) => {
      const memoryDoc = await tx.get(memoryRef);
      const memory = memoryDoc.exists ? memoryDoc.data() : getDefaultMemory();

      // 통계 업데이트
      memory.stats.totalGenerated = (memory.stats.totalGenerated || 0) + 1;
      memory.stats.categoryBreakdown = memory.stats.categoryBreakdown || {};
      memory.stats.categoryBreakdown[category] =
        (memory.stats.categoryBreakdown[category] || 0) + 1;

      // 키워드 빈도 업데이트
      if (keywords.length > 0) {
        memory.preferences.favoriteKeywords = updateKeywordFrequency(
          memory.preferences.favoriteKeywords || [],
          keywords
        );
      }

      memory.updatedAt = admin.firestore.FieldValue.serverTimestamp();

      tx.set(memoryRef, memory, { merge: true });
    });

    console.log('✅ [Memory] 생성 메모리 업데이트 완료:', { uid, category });
  } catch (error) {
    console.warn('⚠️ [Memory] 생성 메모리 업데이트 실패:', error.message);
  }
}

/**
 * 사용자 메모리 업데이트 (글 선택/저장 시)
 * @param {string} uid - 사용자 ID
 * @param {Object} postData - 선택된 글 데이터
 */
async function updateMemoryOnSelection(uid, postData) {
  if (!uid || !postData) return;

  const { category, content, title, keywords = [], qualityScore = null } = postData;
  const memoryRef = db.collection('users').doc(uid)
    .collection('memory').doc('preferences');

  try {
    await db.runTransaction(async (tx) => {
      const memoryDoc = await tx.get(memoryRef);
      const memory = memoryDoc.exists ? memoryDoc.data() : getDefaultMemory();

      // 선택 통계 업데이트
      memory.stats.totalSelected = (memory.stats.totalSelected || 0) + 1;
      memory.stats.selectionRate = memory.stats.totalGenerated > 0
        ? memory.stats.totalSelected / memory.stats.totalGenerated
        : 0;

      // 효과적인 패턴 추출 및 저장
      const patterns = extractEffectivePatterns(content);
      if (patterns.opening) {
        memory.patterns.effectiveOpenings = updatePatternList(
          memory.patterns.effectiveOpenings || [],
          patterns.opening,
          5  // 최대 5개 저장
        );
      }
      if (patterns.closing) {
        memory.patterns.effectiveClosings = updatePatternList(
          memory.patterns.effectiveClosings || [],
          patterns.closing,
          5
        );
      }

      memory.updatedAt = admin.firestore.FieldValue.serverTimestamp();

      tx.set(memoryRef, memory, { merge: true });
    });

    // 베스트 포스트로 저장 (품질 점수 7.0 이상 또는 평가 미수행 시)
    if (qualityScore === null || qualityScore >= 7.0) {
      await saveBestPost(uid, { ...postData, qualityScore });
      console.log('✅ [Memory] 베스트 포스트 저장:', { uid, category, qualityScore });
    } else {
      console.log('ℹ️ [Memory] 품질 기준 미달로 베스트 포스트 미저장:', { uid, qualityScore });
    }

    console.log('✅ [Memory] 선택 메모리 업데이트 완료:', { uid, category });
  } catch (error) {
    console.warn('⚠️ [Memory] 선택 메모리 업데이트 실패:', error.message);
  }
}

// ============================================================================
// 에피소딕 메모리 (Episodic Memory) - Best Posts
// ============================================================================

/**
 * 베스트 포스트 저장
 * @param {string} uid - 사용자 ID
 * @param {Object} postData - 글 데이터
 */
async function saveBestPost(uid, postData) {
  if (!uid || !postData) return;

  const { category, content, title, topic, keywords = [], qualityScore = null } = postData;
  const bestPostsRef = db.collection('users').doc(uid).collection('best_posts');

  try {
    // 카테고리별 최대 3개만 유지
    const existingPosts = await bestPostsRef
      .where('category', '==', category)
      .orderBy('savedAt', 'desc')
      .limit(3)
      .get();

    // 3개 초과 시 가장 오래된 것 삭제
    if (existingPosts.size >= 3) {
      const oldestDoc = existingPosts.docs[existingPosts.size - 1];
      await oldestDoc.ref.delete();
    }

    // 새 베스트 포스트 저장
    await bestPostsRef.add({
      category,
      topic: topic || '',
      title: title || '',
      contentPreview: content ? content.substring(0, 300) : '',
      contentLength: content ? content.length : 0,
      keywords: keywords.slice(0, 10),
      qualityScore,  // 📊 품질 점수 저장
      savedAt: admin.firestore.FieldValue.serverTimestamp()
    });

    console.log('✅ [Memory] 베스트 포스트 저장:', { uid, category });
  } catch (error) {
    console.warn('⚠️ [Memory] 베스트 포스트 저장 실패:', error.message);
  }
}

/**
 * 베스트 포스트 조회 (생성 시 참조용)
 * @param {string} uid - 사용자 ID
 * @param {string} category - 카테고리 (optional)
 * @param {number} limit - 최대 개수
 * @returns {Promise<Array>} 베스트 포스트 목록
 */
async function getBestPosts(uid, category = null, limit = 3) {
  if (!uid) return [];

  try {
    let query = db.collection('users').doc(uid).collection('best_posts')
      .orderBy('savedAt', 'desc')
      .limit(limit);

    if (category) {
      query = db.collection('users').doc(uid).collection('best_posts')
        .where('category', '==', category)
        .orderBy('savedAt', 'desc')
        .limit(limit);
    }

    const snapshot = await query.get();
    return snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
  } catch (error) {
    console.warn('⚠️ [Memory] 베스트 포스트 조회 실패:', error.message);
    return [];
  }
}

// ============================================================================
// 컨텍스트 생성 (프롬프트용)
// ============================================================================

/**
 * 메모리 기반 컨텍스트 생성 (프롬프트에 포함할 내용)
 * @param {string} uid - 사용자 ID
 * @param {string} category - 현재 카테고리
 * @returns {Promise<string>} 컨텍스트 문자열
 */
async function generateMemoryContext(uid, category) {
  if (!uid) return '';

  try {
    const [memory, bestPosts] = await Promise.all([
      getUserMemory(uid),
      getBestPosts(uid, category, 2)
    ]);

    const contextParts = [];

    // 선호 키워드 (상위 5개)
    if (memory?.preferences?.favoriteKeywords?.length > 0) {
      const topKeywords = memory.preferences.favoriteKeywords
        .slice(0, 5)
        .map(k => k.keyword || k)
        .join(', ');
      contextParts.push(`[자주 사용하는 키워드: ${topKeywords}]`);
    }

    // 효과적인 시작 패턴
    if (memory?.patterns?.effectiveOpenings?.length > 0) {
      const opening = memory.patterns.effectiveOpenings[0];
      contextParts.push(`[효과적인 시작 패턴: "${opening}"]`);
    }

    // 베스트 포스트 참조
    if (bestPosts.length > 0) {
      const bestPostHint = bestPosts
        .map(p => `"${p.contentPreview?.substring(0, 100)}..."`)
        .join(' / ');
      contextParts.push(`[이전에 잘 쓴 글 스타일 참조: ${bestPostHint}]`);
    }

    // 선택률 기반 힌트
    if (memory?.stats?.selectionRate > 0.7) {
      contextParts.push('[이 사용자는 생성된 글을 자주 채택함 - 현재 스타일 유지]');
    } else if (memory?.stats?.selectionRate < 0.3 && memory?.stats?.totalGenerated > 5) {
      contextParts.push('[채택률이 낮음 - 다양한 스타일 시도 권장]');
    }

    return contextParts.join(' ');
  } catch (error) {
    console.warn('⚠️ [Memory] 컨텍스트 생성 실패:', error.message);
    return '';
  }
}

// ============================================================================
// 헬퍼 함수
// ============================================================================

/**
 * 키워드 빈도 업데이트
 */
function updateKeywordFrequency(existing, newKeywords) {
  const keywordMap = new Map();

  // 기존 키워드 로드
  existing.forEach(item => {
    const keyword = typeof item === 'string' ? item : item.keyword;
    const count = typeof item === 'object' ? (item.count || 1) : 1;
    keywordMap.set(keyword, count);
  });

  // 새 키워드 추가/업데이트
  newKeywords.forEach(keyword => {
    keywordMap.set(keyword, (keywordMap.get(keyword) || 0) + 1);
  });

  // 빈도순 정렬, 상위 20개 유지
  return Array.from(keywordMap.entries())
    .map(([keyword, count]) => ({ keyword, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 20);
}

/**
 * 패턴 리스트 업데이트 (중복 제거, 최대 개수 유지)
 */
function updatePatternList(existing, newPattern, maxCount) {
  if (!newPattern) return existing;

  // 중복 제거
  const filtered = existing.filter(p => p !== newPattern);

  // 앞에 추가
  filtered.unshift(newPattern);

  // 최대 개수 유지
  return filtered.slice(0, maxCount);
}

/**
 * 효과적인 패턴 추출 (시작/끝 문장)
 */
function extractEffectivePatterns(content) {
  if (!content) return {};

  const sentences = content.split(/[.!?]\s+/).filter(s => s.trim().length > 10);

  return {
    opening: sentences[0]?.substring(0, 100) || null,
    closing: sentences.length > 1
      ? sentences[sentences.length - 1]?.substring(0, 100)
      : null
  };
}

module.exports = {
  // 메모리 조회
  getUserMemory,
  getBestPosts,

  // 메모리 업데이트
  updateMemoryOnGeneration,
  updateMemoryOnSelection,
  saveBestPost,

  // 컨텍스트 생성
  generateMemoryContext
};
