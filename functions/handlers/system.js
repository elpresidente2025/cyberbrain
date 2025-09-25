'use strict';

const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');
const { auth } = require('../common/auth');
const { log } = require('../common/log');
const { admin, db } = require('../utils/firebaseAdmin');
const { callGenerativeModel } = require('../services/gemini');
const { testPrompt, getPolicySafe } = require('../templates/prompts');

// ?�스체크
exports.healthCheck = wrap(async () => {
  log('HEALTH', '?�태 ?�인');
  return ok({ message: '?�자?�뇌비서관 ?�비?��? ?�상 ?�동 중입?�다.', timestamp: new Date().toISOString() });
});

// ?�� getDashboardData ?�수 ?�전 ?�거 - index.js?�서�?처리

// prompt test
exports.testPrompt = wrap(async (req) => {
  const { uid } = await auth(req);
  const { prompt } = req.data || {};
  log('DEBUG', 'testPrompt ?�출', { userId: uid });

  if (!prompt) throw new (require('firebase-functions/v2/https').HttpsError)('invalid-argument', '?�스?�할 ?�롬?�트�??�력?�주?�요.');

  const responseText = await callGenerativeModel(prompt);

  log('DEBUG', 'testPrompt ?�공', { responseLength: responseText.length });
  return ok({ prompt, response: responseText, timestamp: new Date().toISOString() });
});

// Gemini ?�태 ?�인
exports.checkGeminiStatus = wrap(async () => {
  log('SYSTEM', 'checkGeminiStatus ?�출');

  try {
    const t = testPrompt();
    const responseText = await callGenerativeModel(t);

    await db.collection('system').doc('status').set({
      gemini: {
        state: 'healthy',
        lastChecked: admin.firestore.FieldValue.serverTimestamp(),
        testResponse: String(responseText).substring(0, 100),
      },
    }, { merge: true });

    log('SYSTEM', '?�상');
    return ok({ 
      status: 'healthy', 
      message: 'Gemini API가 ?�상?�으�??�동?�니??', 
      testResponse: String(responseText).substring(0, 100) 
    });
  } catch (error) {
    await db.collection('system').doc('status').set({
      gemini: {
        state: 'error',
        lastChecked: admin.firestore.FieldValue.serverTimestamp(),
        error: error.message,
      },
    }, { merge: true });

    log('SYSTEM', '?�류', error.message);
    return ok({ 
      status: 'error', 
      message: 'Gemini API??문제가 ?�습?�다.', 
      error: error.message 
    });
  }
});

// ?�책 ?�플�?조회
exports.getPolicyTemplate = wrap(async (req) => {
  const { category, subCategory } = req.data || {};
  log('POLICY', 'getPolicyTemplate ?�출', { category, subCategory });

  const template = getPolicySafe(category, subCategory);
  log('POLICY', '?�공');
  return ok({ template, category, subCategory });
});

// policy test
exports.testPolicy = wrap(async (req) => {
  const { uid } = await auth(req);
  const { policyId, testInput } = req.data || {};
  log('DEBUG', 'testPolicy ?�출', { userId: uid, policyId });

  if (!policyId || !testInput) {
    throw new (require('firebase-functions/v2/https').HttpsError)('invalid-argument', '?�책 ID?� ?�스???�력???�요?�니??');
  }

  const policyPrompt = getPolicySafe(policyId);
  if (!policyPrompt) {
    throw new (require('firebase-functions/v2/https').HttpsError)('not-found', '?�당 ?�책??찾을 ???�습?�다.');
  }

  const fullPrompt = `${policyPrompt}\n\n?�스???�력: ${testInput}`;
  const responseText = await callGenerativeModel(fullPrompt);

  log('DEBUG', '?�책 ?�스???�료', { policyId });
  return ok({ 
    policy: policyId, 
    response: responseText, 
    usage: apiResponse?.usage || null 
  });
});

// ?�용???�동 로그
exports.logUserActivity = wrap(async (req) => {
  const { uid } = await auth(req);
  const { action, metadata } = req.data || {};
  if (!action) throw new (require('firebase-functions/v2/https').HttpsError)('invalid-argument', '?�동 ?�형??지?�해주세??');

  try {
    await db.collection('user_activities').add({
      userId: uid,
      action,
      metadata: metadata || {},
      timestamp: admin.firestore.FieldValue.serverTimestamp(),
      userAgent: req.auth?.token?.ua || null,
      ip: req.auth?.token?.ip || null,
    });

    await db.collection('users').doc(uid).set({ 
      lastActivity: admin.firestore.FieldValue.serverTimestamp() 
    }, { merge: true });

    log('ACTIVITY', '?�??, { userId: uid, action });
    return ok({ message: '?�동??기록?�었?�니??' });
  } catch (e) {
    log('ACTIVITY', '?�패(무시)', e.message);
    return ok({ message: '?�료?�었?�니??' });
  }
});

// ?�스???�태 ?�체 조회
exports.getSystemStatus = wrap(async () => {
  log('SYSTEM', 'getSystemStatus ?�출');

  try {
    const statusDoc = await db.collection('system').doc('status').get();
    const statusData = statusDoc.exists ? statusDoc.data() : {};

    const systemStatus = {
      timestamp: new Date().toISOString(),
      gemini: statusData.gemini || { state: 'unknown' },
      database: { state: 'healthy' }, // Firestore가 ?�동?��?�?healthy
      version: process.env.FUNCTIONS_EMULATOR ? 'local' : 'production'
    };

    log('SYSTEM', '?�태 조회 ?�공');
    return ok({ status: systemStatus });
  } catch (error) {
    log('SYSTEM', '?�태 조회 ?�패', error.message);
    return ok({ 
      status: { 
        timestamp: new Date().toISOString(),
        gemini: { state: 'unknown' },
        database: { state: 'error', error: error.message },
        version: 'unknown'
      } 
    });
  }
});

// Gemini 상태 수동 업데이트 (관리자 전용)
exports.updateGeminiStatus = wrap(async (req) => {
  const { uid } = await auth(req);
  const { newState } = req.data || {};

  // 관리자 권한 확인
  const requesterDoc = await db.collection('users').doc(uid).get();
  const userData = requesterDoc.exists ? requesterDoc.data() : {};
  const isAdmin = userData.role === 'admin' || userData.isAdmin === true;
  if (!requesterDoc.exists || !isAdmin) {
    throw new (require('firebase-functions/v2/https').HttpsError)('permission-denied', '관리자만 변경할 수 있습니다.');
  }

  const allowed = ['active', 'maintenance', 'inactive'];
  if (!allowed.includes(newState)) {
    throw new (require('firebase-functions/v2/https').HttpsError)('invalid-argument', '유효하지 않은 상태 값입니다.');
  }

  await db.collection('system_status').doc('gemini').set({
    state: newState,
    lastUpdated: admin.firestore.FieldValue.serverTimestamp(),
    updatedBy: uid
  });

  return ok({ success: true, geminiStatus: { state: newState } });
});


