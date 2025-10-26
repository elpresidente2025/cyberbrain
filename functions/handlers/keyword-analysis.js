/**
 * handlers/keyword-analysis.js
 * 키워드 추천 시스템 v3.0 메인 핸들러
 */

'use strict';

const { onCall, HttpsError, onRequest } = require('firebase-functions/v2/https');
const { CloudTasksClient } = require('@google-cloud/tasks');
const { admin, db } = require('../utils/firebaseAdmin');
const scraper = require('../services/scraper');
const trendsAnalyzer = require('../services/trends-analyzer');
const keywordScorer = require('../services/keyword-scorer');
const geminiExpander = require('../services/gemini-expander');

/**
 * Phase 1: 키워드 분석 요청 (비동기)
 * 클라이언트가 호출하는 함수
 */
exports.requestKeywordAnalysis = onCall({
  cors: true,
  memory: '512MiB',
  timeoutSeconds: 60
}, async (request) => {
  const { district, topic, userId } = request.data;

  console.log('🔥 [KeywordAnalysis] 분석 요청:', { district, topic, userId });

  // 입력 검증
  if (!district || !topic) {
    throw new HttpsError('invalid-argument', '지역구와 주제는 필수입니다.');
  }

  const uid = request.auth?.uid;
  if (!uid) {
    throw new HttpsError('unauthenticated', '인증이 필요합니다.');
  }

  try {
    // 1. keyword_tasks 문서 생성
    const taskRef = await db.collection('keyword_tasks').add({
      userId: uid,
      district,
      topic,
      status: 'pending',
      progress: 0,
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      updatedAt: admin.firestore.FieldValue.serverTimestamp()
    });

    const taskId = taskRef.id;

    console.log(`📝 [KeywordAnalysis] Task 생성: ${taskId}`);

    // 2. Cloud Tasks 생성
    const taskCreated = await createCloudTask(taskId, { district, topic, userId: uid });

    if (!taskCreated) {
      console.warn(`⚠️ [KeywordAnalysis] Cloud Tasks 생성 실패, 직접 실행 모드`);
      // Cloud Tasks 생성 실패 시 직접 실행
      processKeywordAnalysisDirectly(taskId, district, topic, uid);
    }

    // 3. 즉시 응답 반환
    return {
      success: true,
      taskId,
      status: 'processing',
      message: '키워드 분석이 시작되었습니다. 잠시 후 결과를 확인하세요.'
    };

  } catch (error) {
    console.error('❌ [KeywordAnalysis] 요청 처리 실패:', error);
    throw new HttpsError('internal', `분석 요청 실패: ${error.message}`);
  }
});

/**
 * Cloud Task 생성
 * @param {string} taskId - Task 문서 ID
 * @param {Object} payload - 페이로드
 * @returns {Promise<boolean>} 성공 여부
 */
async function createCloudTask(taskId, payload) {
  try {
    const client = new CloudTasksClient();

    const project = process.env.GCLOUD_PROJECT || 'ai-secretary-6e9c8';
    const location = 'asia-northeast3';
    const queue = 'keyword-analysis-queue';

    const parent = client.queuePath(project, location, queue);

    // 워커 함수 URL
    const url = `https://${location}-${project}.cloudfunctions.net/keywordAnalysisWorker`;

    const task = {
      httpRequest: {
        httpMethod: 'POST',
        url,
        headers: {
          'Content-Type': 'application/json'
        },
        body: Buffer.from(JSON.stringify({
          taskId,
          ...payload
        })).toString('base64')
      }
    };

    const [response] = await client.createTask({ parent, task });

    console.log(`✅ [CloudTasks] Task 생성 완료: ${response.name}`);
    return true;

  } catch (error) {
    console.error('❌ [CloudTasks] Task 생성 실패:', error.message);
    return false;
  }
}

/**
 * 직접 실행 모드 (Cloud Tasks 없이)
 * @param {string} taskId - Task ID
 * @param {string} district - 지역구
 * @param {string} topic - 주제
 * @param {string} userId - 사용자 ID
 */
function processKeywordAnalysisDirectly(taskId, district, topic, userId) {
  // 비동기로 백그라운드에서 실행
  setImmediate(async () => {
    try {
      await executeKeywordAnalysis({ taskId, district, topic, userId });
    } catch (error) {
      console.error('❌ [KeywordAnalysis] 직접 실행 실패:', error);
      await updateTaskStatus(taskId, 'failed', { error: error.message });
    }
  });
}

/**
 * Phase 1-3: 키워드 분석 워커
 * Cloud Tasks가 호출하는 함수
 */
exports.keywordAnalysisWorker = onRequest({
  region: 'asia-northeast3',
  memory: '1GiB',
  timeoutSeconds: 540, // 9분
  cors: false
}, async (req, res) => {
  if (req.method !== 'POST') {
    res.status(405).send('Method Not Allowed');
    return;
  }

  try {
    const payload = req.body;
    const { taskId, district, topic, userId } = payload;

    console.log('🔄 [Worker] 키워드 분석 작업 시작:', { taskId, district, topic });

    // 작업 실행
    await executeKeywordAnalysis({ taskId, district, topic, userId });

    res.status(200).json({ success: true, taskId });

  } catch (error) {
    console.error('❌ [Worker] 작업 실패:', error);
    res.status(500).json({ success: false, error: error.message });
  }
});

/**
 * 키워드 분석 실행 (핵심 로직)
 * @param {Object} params - 분석 파라미터
 */
async function executeKeywordAnalysis(params) {
  const { taskId, district, topic, userId } = params;

  try {
    // 상태 업데이트: processing
    await updateTaskStatus(taskId, 'processing', { progress: 10 });

    // 1. 캐시 확인
    const cacheKey = `${district}_${topic}`;
    const cachedResult = await checkCache(cacheKey);

    if (cachedResult) {
      console.log(`✅ [Worker] 캐시 hit: ${cacheKey}`);
      await updateTaskStatus(taskId, 'completed', {
        keywords: cachedResult.keywords,
        fromCache: true,
        progress: 100
      });
      return;
    }

    console.log(`🔄 [Worker] 캐시 miss: ${cacheKey}, 전체 분석 시작`);

    // 2. 기본 키워드 수집 (스크래핑)
    await updateTaskStatus(taskId, 'processing', { progress: 20, stage: '기본 키워드 수집 중...' });

    const baseKeywords = await scraper.getNaverSuggestions(topic);

    console.log(`📋 [Worker] 기본 키워드 ${baseKeywords.length}개 수집 완료`);

    // 3. Gemini로 확장 (30개)
    await updateTaskStatus(taskId, 'processing', { progress: 30, stage: 'AI 키워드 확장 중...' });

    const expandedKeywords = await geminiExpander.expandAndValidateKeywords({
      district,
      topic,
      baseKeywords,
      targetCount: 30
    });

    console.log(`🤖 [Worker] 확장 키워드 ${expandedKeywords.length}개 생성 완료`);

    // 4. 각 키워드 상세 분석
    await updateTaskStatus(taskId, 'processing', { progress: 40, stage: '키워드 분석 중...' });

    const analyzedKeywords = [];

    for (let i = 0; i < expandedKeywords.length; i++) {
      const keyword = expandedKeywords[i];

      console.log(`🔍 [Worker] [${i + 1}/${expandedKeywords.length}] "${keyword}" 분석 중...`);

      // 4-1. 개별 키워드 캐시 확인
      const keywordCache = await checkKeywordCache(keyword);

      if (keywordCache) {
        console.log(`✅ [Worker] "${keyword}" 캐시 hit`);
        analyzedKeywords.push(keywordCache);
        continue;
      }

      // 4-2. SERP 분석
      const serpData = await scraper.analyzeNaverSERP(keyword);

      // 4-3. 검색 결과 수
      const resultCount = await scraper.getSearchResultCount(keyword);

      // 4-4. 트렌드 분석 (캐시 활용)
      let trendData = await trendsAnalyzer.getCachedTrendScore(db, keyword);

      if (!trendData) {
        trendData = await trendsAnalyzer.getTrendScore(keyword);
        await trendsAnalyzer.cacheTrendScore(db, keyword, trendData);

        // API 호출 간격 (1초)
        await sleep(1000);
      }

      // 4-5. 종합 점수 계산
      const analysis = keywordScorer.analyzeKeyword({
        keyword,
        serpData,
        resultCount,
        trendScore: trendData.trendScore,
        district,
        topic
      });

      analyzedKeywords.push(analysis);

      // 4-6. 개별 키워드 캐싱
      await cacheKeywordAnalysis(keyword, analysis);

      // 진행률 업데이트
      const progress = 40 + Math.floor((i + 1) / expandedKeywords.length * 40);
      await updateTaskStatus(taskId, 'processing', {
        progress,
        stage: `키워드 분석 중... (${i + 1}/${expandedKeywords.length})`
      });
    }

    // 5. 점수순 정렬 및 상위 20개 선택
    await updateTaskStatus(taskId, 'processing', { progress: 90, stage: '최종 정리 중...' });

    analyzedKeywords.sort((a, b) => b.finalScore - a.finalScore);
    const top20Keywords = analyzedKeywords.slice(0, 20);

    console.log(`✅ [Worker] 상위 20개 키워드 선정 완료`);

    // 6. 결과 캐싱
    await saveToCache(cacheKey, { keywords: top20Keywords });

    // 7. 최종 결과 저장
    await updateTaskStatus(taskId, 'completed', {
      keywords: top20Keywords,
      totalAnalyzed: analyzedKeywords.length,
      fromCache: false,
      progress: 100,
      completedAt: new Date().toISOString()
    });

    console.log(`🎉 [Worker] 작업 완료: ${taskId}`);

  } catch (error) {
    console.error(`❌ [Worker] 작업 실패: ${taskId}`, error);
    await updateTaskStatus(taskId, 'failed', {
      error: error.message,
      errorStack: error.stack
    });
    throw error;
  }
}

/**
 * Task 상태 업데이트
 * @param {string} taskId - Task ID
 * @param {string} status - 상태
 * @param {Object} additionalData - 추가 데이터
 */
async function updateTaskStatus(taskId, status, additionalData = {}) {
  try {
    await db.collection('keyword_tasks').doc(taskId).update({
      status,
      ...additionalData,
      updatedAt: admin.firestore.FieldValue.serverTimestamp()
    });

    console.log(`📝 [Worker] Task 상태 업데이트: ${taskId} -> ${status}`);
  } catch (error) {
    console.error(`❌ [Worker] Task 상태 업데이트 실패:`, error);
  }
}

/**
 * 캐시 확인
 * @param {string} cacheKey - 캐시 키
 * @returns {Promise<Object|null>} 캐시된 데이터 또는 null
 */
async function checkCache(cacheKey) {
  try {
    const cacheDoc = await db.collection('keyword_cache').doc(cacheKey).get();

    if (!cacheDoc.exists) {
      return null;
    }

    const data = cacheDoc.data();
    const cacheAge = Date.now() - data.timestamp.toDate().getTime();
    const maxAge = 12 * 60 * 60 * 1000; // 12시간

    if (cacheAge > maxAge) {
      console.log(`⏰ [Cache] 캐시 만료: ${cacheKey}`);
      return null;
    }

    return data;

  } catch (error) {
    console.error(`❌ [Cache] 캐시 확인 실패:`, error);
    return null;
  }
}

/**
 * 캐시 저장
 * @param {string} cacheKey - 캐시 키
 * @param {Object} data - 저장할 데이터
 */
async function saveToCache(cacheKey, data) {
  try {
    await db.collection('keyword_cache').doc(cacheKey).set({
      ...data,
      timestamp: admin.firestore.FieldValue.serverTimestamp(),
      cachedAt: new Date().toISOString()
    });

    console.log(`💾 [Cache] 캐시 저장: ${cacheKey}`);
  } catch (error) {
    console.error(`❌ [Cache] 캐시 저장 실패:`, error);
  }
}

/**
 * 개별 키워드 캐시 확인
 * @param {string} keyword - 키워드
 * @returns {Promise<Object|null>} 캐시된 분석 결과
 */
async function checkKeywordCache(keyword) {
  try {
    const cacheDoc = await db.collection('keyword_analysis_cache').doc(keyword).get();

    if (!cacheDoc.exists) {
      return null;
    }

    const data = cacheDoc.data();
    const cacheAge = Date.now() - data.timestamp.toDate().getTime();
    const maxAge = 24 * 60 * 60 * 1000; // 24시간

    if (cacheAge > maxAge) {
      return null;
    }

    return data.analysis;

  } catch (error) {
    console.error(`❌ [Cache] 키워드 캐시 확인 실패:`, error);
    return null;
  }
}

/**
 * 개별 키워드 분석 결과 캐싱
 * @param {string} keyword - 키워드
 * @param {Object} analysis - 분석 결과
 */
async function cacheKeywordAnalysis(keyword, analysis) {
  try {
    await db.collection('keyword_analysis_cache').doc(keyword).set({
      analysis,
      timestamp: admin.firestore.FieldValue.serverTimestamp(),
      cachedAt: new Date().toISOString()
    });
  } catch (error) {
    console.error(`❌ [Cache] 키워드 캐시 저장 실패:`, error);
  }
}

/**
 * Sleep 유틸리티
 * @param {number} ms - 밀리초
 */
function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * 사용자의 키워드 분석 결과 조회
 */
exports.getKeywordAnalysisResult = onCall({
  cors: true,
  memory: '256MiB',
  timeoutSeconds: 30
}, async (request) => {
  const { taskId } = request.data;

  if (!taskId) {
    throw new HttpsError('invalid-argument', 'taskId가 필요합니다.');
  }

  const uid = request.auth?.uid;
  if (!uid) {
    throw new HttpsError('unauthenticated', '인증이 필요합니다.');
  }

  try {
    const taskDoc = await db.collection('keyword_tasks').doc(taskId).get();

    if (!taskDoc.exists) {
      throw new HttpsError('not-found', '작업을 찾을 수 없습니다.');
    }

    const data = taskDoc.data();

    // 본인의 작업인지 확인
    if (data.userId !== uid) {
      throw new HttpsError('permission-denied', '권한이 없습니다.');
    }

    return {
      success: true,
      taskId,
      status: data.status,
      progress: data.progress || 0,
      keywords: data.keywords || [],
      fromCache: data.fromCache || false,
      createdAt: data.createdAt?.toDate?.()?.toISOString(),
      completedAt: data.completedAt
    };

  } catch (error) {
    console.error('❌ [GetResult] 조회 실패:', error);
    throw new HttpsError('internal', `결과 조회 실패: ${error.message}`);
  }
});

/**
 * 사용자의 키워드 분석 히스토리 조회
 */
exports.getKeywordAnalysisHistory = onCall({
  cors: true,
  memory: '256MiB',
  timeoutSeconds: 30
}, async (request) => {
  const uid = request.auth?.uid;
  if (!uid) {
    throw new HttpsError('unauthenticated', '인증이 필요합니다.');
  }

  try {
    const { limit = 10 } = request.data || {};

    const snapshot = await db.collection('keyword_tasks')
      .where('userId', '==', uid)
      .orderBy('createdAt', 'desc')
      .limit(Math.min(limit, 50))
      .get();

    const history = [];

    snapshot.forEach(doc => {
      const data = doc.data();
      history.push({
        taskId: doc.id,
        district: data.district,
        topic: data.topic,
        status: data.status,
        progress: data.progress || 0,
        keywordCount: data.keywords?.length || 0,
        fromCache: data.fromCache || false,
        createdAt: data.createdAt?.toDate?.()?.toISOString(),
        completedAt: data.completedAt
      });
    });

    return {
      success: true,
      history,
      total: history.length
    };

  } catch (error) {
    console.error('❌ [GetHistory] 조회 실패:', error);
    throw new HttpsError('internal', `히스토리 조회 실패: ${error.message}`);
  }
});
