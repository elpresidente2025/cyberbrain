'use strict';

/**
 * Stylometry 재학습 공유 헬퍼.
 *
 * - buildDiaryAugmentedCorpus: 페이스북 다이어리 엔트리 + 바이오 컨텐츠를
 *   라벨링된 단일 코퍼스로 합친다. 다이어리가 주(主), 바이오가 부(副).
 * - refreshUserStyleFingerprint: 주어진 코퍼스로 stylometry를 다시 돌리고
 *   bios/{uid} 및 users/{uid}.styleGuide를 갱신한다. marker 필드까지 정리한다.
 */

const { admin, db } = require('../utils/firebaseAdmin');
const { extractStyleFingerprint, buildStyleGuidePrompt } = require('./stylometry');

const MAX_DIARY_ENTRIES = 30;
const MIN_CORPUS_LENGTH = 100;

function _formatEntryDate(createdAt) {
  if (!createdAt) return '';
  try {
    if (typeof createdAt.toDate === 'function') {
      return createdAt.toDate().toISOString().slice(0, 10);
    }
    if (createdAt instanceof Date) {
      return createdAt.toISOString().slice(0, 10);
    }
    return String(createdAt).slice(0, 10);
  } catch (_err) {
    return '';
  }
}

function _buildBioBlock(bioData = {}) {
  const entries = Array.isArray(bioData.entries) ? bioData.entries : [];
  const chunks = [];

  for (const entry of entries) {
    const content = String(entry?.content || '').trim();
    if (!content) continue;
    const type = String(entry?.type || 'content').trim().toUpperCase();
    const title = String(entry?.title || '').trim();
    chunks.push(`[${type}]${title ? ` ${title}` : ''}\n${content}`);
  }

  if (chunks.length === 0) {
    const flat = String(bioData.content || '').trim();
    return flat;
  }

  return chunks.join('\n\n');
}

/**
 * 사용자별 stylometry 학습용 코퍼스를 구성한다.
 * 다이어리 우선, 바이오 보조. LLM이 다이어리를 주된 신호로 읽도록 순서와 라벨을 준다.
 *
 * @param {string} uid
 * @param {Object} bioData - bios/{uid} 문서 데이터
 * @returns {Promise<{ text: string, source: 'diary-augmented'|'bio-only'|'diary-only'|'empty', stats: Object }>}
 */
async function buildDiaryAugmentedCorpus(uid, bioData = {}) {
  const stats = {
    bioChars: 0,
    diaryEntryCount: 0,
    diaryChars: 0,
    totalChars: 0,
  };

  const bioBlock = _buildBioBlock(bioData);
  stats.bioChars = bioBlock.length;

  let diarySnapshot;
  try {
    diarySnapshot = await db
      .collection('bios')
      .doc(uid)
      .collection('facebook_entries')
      .orderBy('createdAt', 'desc')
      .limit(MAX_DIARY_ENTRIES)
      .get();
  } catch (err) {
    console.warn(`[StyleRefresh] facebook_entries 조회 실패 (${uid}):`, err.message);
    diarySnapshot = null;
  }

  const diaryParts = [];
  if (diarySnapshot && !diarySnapshot.empty) {
    for (const doc of diarySnapshot.docs) {
      const entry = doc.data() || {};
      const text = String(entry.text || '').trim();
      if (!text) continue;
      const dateStr = _formatEntryDate(entry.createdAt);
      const category = String(entry.category || '').trim();
      const headerParts = ['[Facebook 입장문]'];
      if (dateStr) headerParts.push(dateStr);
      if (category) headerParts.push(`(${category})`);
      const header = headerParts.join(' ');
      diaryParts.push(`${header}\n${text}`);
      stats.diaryChars += text.length;
    }
    stats.diaryEntryCount = diaryParts.length;
  }

  const sections = [];
  if (diaryParts.length > 0) {
    sections.push(`[사용자 실제 입장문 모음 — 최신순]\n\n${diaryParts.join('\n\n---\n\n')}`);
  }
  if (bioBlock) {
    sections.push(`[사용자 바이오 — 보조 자료]\n\n${bioBlock}`);
  }

  const text = sections.join('\n\n====\n\n');
  stats.totalChars = text.length;

  let source;
  if (diaryParts.length > 0 && bioBlock) {
    source = 'diary-augmented';
  } else if (diaryParts.length > 0) {
    source = 'diary-only';
  } else if (bioBlock) {
    source = 'bio-only';
  } else {
    source = 'empty';
  }

  return { text, source, stats };
}

/**
 * 주어진 코퍼스로 stylometry를 재계산하고 Firestore를 갱신한다.
 *
 * @param {string} uid
 * @param {Object} opts
 * @param {string} opts.corpusText
 * @param {'diary-augmented'|'bio-only'|'diary-only'|'empty'} opts.source
 * @param {Object} [opts.corpusStats]
 * @param {Object} [opts.userMeta]
 * @returns {Promise<{ ok: boolean, version?: number, reason?: string }>}
 */
async function refreshUserStyleFingerprint(uid, {
  corpusText = '',
  source = 'bio-only',
  corpusStats = null,
  userMeta = {},
} = {}) {
  if (!uid) {
    return { ok: false, reason: 'missing-uid' };
  }
  if (!corpusText || corpusText.length < MIN_CORPUS_LENGTH) {
    await _recordRefreshError(uid, `corpus too short (${corpusText.length} chars)`);
    return { ok: false, reason: 'corpus-too-short' };
  }

  try {
    const fingerprint = await extractStyleFingerprint(corpusText, {
      userName: String(userMeta.userName || '').trim(),
      region: String(userMeta.region || '').trim(),
    });

    if (!fingerprint) {
      await _recordRefreshError(uid, 'extractStyleFingerprint returned null');
      return { ok: false, reason: 'empty-result' };
    }

    const styleGuide = buildStyleGuidePrompt(fingerprint, {
      compact: false,
      sourceText: corpusText,
    });

    const bioRef = db.collection('bios').doc(uid);
    const now = admin.firestore.FieldValue.serverTimestamp();

    await bioRef.set({
      styleFingerprint: fingerprint,
      styleGuide,
      styleFingerprintUpdatedAt: now,
      styleGuideUpdatedAt: now,
      styleFingerprintSource: source,
      styleFingerprintVersion: admin.firestore.FieldValue.increment(1),
      styleFingerprintCorpusStats: corpusStats || null,
      pendingStyleEntryCount: 0,
      styleRefreshRequestedAt: admin.firestore.FieldValue.delete(),
      styleRefreshError: admin.firestore.FieldValue.delete(),
      lastAnalyzed: now,
    }, { merge: true });

    const userRef = db.collection('users').doc(uid);
    const userSnap = await userRef.get();
    if (userSnap.exists) {
      await userRef.set({
        styleGuide: styleGuide || '',
        styleGuideUpdatedAt: now,
      }, { merge: true });
    }

    const updatedSnap = await bioRef.get();
    const version = Number(updatedSnap.data()?.styleFingerprintVersion || 0);

    console.log(`✅ [StyleRefresh] uid=${uid} source=${source} version=${version} chars=${corpusText.length}`);
    return { ok: true, version };
  } catch (error) {
    console.error(`❌ [StyleRefresh] uid=${uid} 실패:`, error);
    await _recordRefreshError(uid, error?.message || 'unknown-error');
    return { ok: false, reason: error?.message || 'unknown-error' };
  }
}

async function _recordRefreshError(uid, message) {
  try {
    await db.collection('bios').doc(uid).set({
      styleRefreshError: {
        message: String(message || 'unknown').slice(0, 500),
        at: admin.firestore.FieldValue.serverTimestamp(),
      },
    }, { merge: true });
  } catch (err) {
    console.warn(`[StyleRefresh] error 기록 실패 (${uid}):`, err.message);
  }
}

module.exports = {
  buildDiaryAugmentedCorpus,
  refreshUserStyleFingerprint,
  MIN_CORPUS_LENGTH,
  MAX_DIARY_ENTRIES,
};
