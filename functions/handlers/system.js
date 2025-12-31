'use strict';

const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');
const { auth } = require('../common/auth');
const { log } = require('../common/log');
const { admin, db } = require('../utils/firebaseAdmin');
const { callGenerativeModel } = require('../services/gemini');
const { testPrompt, getPolicySafe } = require('../prompts/prompts');

// 헬스체크
exports.healthCheck = wrap(async () => {
  log('HEALTH', '상태 확인');
  return ok({ message: '전자뇌비서관 서비스가 정상 작동 중입니다.', timestamp: new Date().toISOString() });
});

// 기존 getDashboardData 함수 완전 제거 - index.js에서 처리

// prompt test
exports.testPrompt = wrap(async (req) => {
  const { uid } = await auth(req);
  const { prompt } = req.data || {};
  log('DEBUG', 'testPrompt 호출', { userId: uid });

  if (!prompt) throw new (require('firebase-functions/v2/https').HttpsError)('invalid-argument', '테스트할 프롬프트를 입력해주세요.');

  const responseText = await callGenerativeModel(prompt);

  log('DEBUG', 'testPrompt 성공', { responseLength: responseText.length });
  return ok({ prompt, response: responseText, timestamp: new Date().toISOString() });
});

// Gemini 상태 확인
exports.checkGeminiStatus = wrap(async () => {
  log('SYSTEM', 'checkGeminiStatus 호출');

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

    log('SYSTEM', '정상');
    return ok({ 
      status: 'healthy', 
      message: 'Gemini API가 정상적으로 동작합니다.', 
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

    log('SYSTEM', '오류', error.message);
    return ok({ 
      status: 'error', 
      message: 'Gemini API에 문제가 있습니다.', 
      error: error.message 
    });
  }
});

// 정책 템플릿 조회
exports.getPolicyTemplate = wrap(async (req) => {
  const { category, subCategory } = req.data || {};
  log('POLICY', 'getPolicyTemplate 호출', { category, subCategory });

  const template = getPolicySafe(category, subCategory);
  log('POLICY', '성공');
  return ok({ template, category, subCategory });
});

// policy test
exports.testPolicy = wrap(async (req) => {
  const { uid } = await auth(req);
  const { policyId, testInput } = req.data || {};
  log('DEBUG', 'testPolicy 호출', { userId: uid, policyId });

  if (!policyId || !testInput) {
    throw new (require('firebase-functions/v2/https').HttpsError)('invalid-argument', '정책 ID와 테스트 입력이 필요합니다.');
  }

  const policyPrompt = getPolicySafe(policyId);
  if (!policyPrompt) {
    throw new (require('firebase-functions/v2/https').HttpsError)('not-found', '해당 정책을 찾을 수 없습니다.');
  }

  const fullPrompt = `${policyPrompt}\n\n테스트 입력: ${testInput}`;
  const responseText = await callGenerativeModel(fullPrompt);

  log('DEBUG', '정책 테스트 완료', { policyId });
  return ok({
    policy: policyId,
    response: responseText
    // usage 정보는 callGenerativeModel이 반환하지 않으므로 제거
  });
});

// 사용자 활동 로그
exports.logUserActivity = wrap(async (req) => {
  const { uid } = await auth(req);
  const { action, metadata } = req.data || {};
  if (!action) throw new (require('firebase-functions/v2/https').HttpsError)('invalid-argument', '활동 유형을 지정해주세요.');

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

    log('ACTIVITY', '완료', { userId: uid, action });
    return ok({ message: '활동이 기록되었습니다' });
  } catch (e) {
    log('ACTIVITY', '실패(무시)', e.message);
    return ok({ message: '완료되었습니다' });
  }
});

// 시스템 상태 전체 조회
exports.getSystemStatus = wrap(async () => {
  log('SYSTEM', 'getSystemStatus 호출');

  try {
    const statusDoc = await db.collection('system').doc('status').get();
    const statusData = statusDoc.exists ? statusDoc.data() : {};

    // 프론트엔드가 기대하는 형태: { status: 'active' | 'maintenance' | 'inactive', ... }
    const response = {
      status: statusData.status || 'active',  // 문자열: 'active', 'maintenance', 'inactive'
      timestamp: new Date().toISOString(),
      gemini: statusData.gemini || { state: 'unknown' },
      database: { state: 'healthy' },
      version: process.env.FUNCTIONS_EMULATOR ? 'local' : 'production'
    };

    // 점검 중인 경우 추가 정보 포함
    if (statusData.status === 'maintenance' && statusData.maintenanceInfo) {
      response.maintenanceInfo = statusData.maintenanceInfo;
    }

    // 변경 이력 정보도 포함
    if (statusData.reason) {
      response.reason = statusData.reason;
    }
    if (statusData.updatedBy) {
      response.updatedBy = statusData.updatedBy;
    }

    log('SYSTEM', '상태 조회 성공', { status: response.status });
    return ok(response);
  } catch (error) {
    log('SYSTEM', '상태 조회 실패', error.message);
    return ok({
      status: 'active',  // 실패 시 정상 상태로 간주
      timestamp: new Date().toISOString(),
      gemini: { state: 'unknown' },
      database: { state: 'error', error: error.message },
      version: 'unknown'
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

// 시스템 상태 업데이트 (관리자 전용) - 프론트엔드 StatusUpdateModal에서 사용
exports.updateSystemStatus = wrap(async (req) => {
  const { uid } = await auth(req);
  const { status, reason, maintenanceInfo } = req.data || {};

  log('SYSTEM', 'updateSystemStatus 호출', { userId: uid, status });

  // 관리자 권한 확인
  const requesterDoc = await db.collection('users').doc(uid).get();
  const userData = requesterDoc.exists ? requesterDoc.data() : {};
  const isAdmin = userData.role === 'admin' || userData.isAdmin === true;
  if (!requesterDoc.exists || !isAdmin) {
    throw new (require('firebase-functions/v2/https').HttpsError)('permission-denied', '관리자만 시스템 상태를 변경할 수 있습니다.');
  }

  const allowed = ['active', 'maintenance', 'inactive'];
  if (!allowed.includes(status)) {
    throw new (require('firebase-functions/v2/https').HttpsError)('invalid-argument', '유효하지 않은 상태 값입니다. (active, maintenance, inactive 중 하나)');
  }

  if (!reason || !reason.trim()) {
    throw new (require('firebase-functions/v2/https').HttpsError)('invalid-argument', '변경 사유를 입력해주세요.');
  }

  // Firestore에 시스템 상태 저장
  const updateData = {
    status,
    reason: reason.trim(),
    lastUpdated: admin.firestore.FieldValue.serverTimestamp(),
    updatedBy: uid,
    timestamp: new Date().toISOString()
  };

  // 점검 중인 경우 추가 정보 포함
  if (status === 'maintenance' && maintenanceInfo) {
    updateData.maintenanceInfo = {
      title: maintenanceInfo.title || '시스템 점검 안내',
      message: maintenanceInfo.message || '',
      estimatedEndTime: maintenanceInfo.estimatedEndTime || '',
      contactInfo: maintenanceInfo.contactInfo || '',
      allowAdminAccess: maintenanceInfo.allowAdminAccess !== false
    };
  } else {
    // 점검이 아니면 maintenanceInfo 제거
    updateData.maintenanceInfo = admin.firestore.FieldValue.delete();
  }

  await db.collection('system').doc('status').set(updateData, { merge: true });

  log('SYSTEM', '시스템 상태 업데이트 완료', { status, reason });
  return ok({
    success: true,
    status,
    message: '시스템 상태가 성공적으로 업데이트되었습니다.',
    timestamp: updateData.timestamp
  });
});

