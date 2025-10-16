'use strict';

const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');
const { auth } = require('../common/auth');
const { log } = require('../common/log');
const { admin, db } = require('../utils/firebaseAdmin');
const { callGenerativeModel } = require('../services/gemini');
const { testPrompt, getPolicySafe } = require('../prompts/prompts');
const { HttpsError } = require('firebase-functions/v2/https');

// Health check
exports.healthCheck = wrap(async () => {
  log('HEALTH', 'status check');
  return ok({ message: 'AI Secretary backend is running.', timestamp: new Date().toISOString() });
});

// Prompt test
exports.testPrompt = wrap(async (req) => {
  const { uid } = await auth(req);
  const { prompt } = req.data || {};
  log('DEBUG', 'testPrompt request', { userId: uid });

  if (!prompt) throw new HttpsError('invalid-argument', 'Prompt is required.');

  const responseText = await callGenerativeModel(prompt);
  log('DEBUG', 'testPrompt success', { responseLength: (responseText || '').length });
  return ok({ prompt, response: responseText, timestamp: new Date().toISOString() });
});

// Gemini health check
exports.checkGeminiStatus = wrap(async () => {
  log('SYSTEM', 'checkGeminiStatus request');

  try {
    const t = testPrompt();
    const responseText = await callGenerativeModel(t);

    await db.collection('system').doc('status').set({
      gemini: {
        state: 'healthy',
        lastChecked: admin.firestore.FieldValue.serverTimestamp(),
        testResponse: String(responseText || '').substring(0, 100),
      },
    }, { merge: true });

    log('SYSTEM', 'healthy');
    return ok({ 
      status: 'healthy', 
      message: 'Gemini API is operational.', 
      testResponse: String(responseText || '').substring(0, 100) 
    });
  } catch (error) {
    await db.collection('system').doc('status').set({
      gemini: {
        state: 'error',
        lastChecked: admin.firestore.FieldValue.serverTimestamp(),
        error: error.message,
      },
    }, { merge: true });

    log('SYSTEM', 'error', error.message);
    return ok({ 
      status: 'error', 
      message: 'Gemini API issue detected.', 
      error: error.message 
    });
  }
});

// Policy template fetch
exports.getPolicyTemplate = wrap(async (req) => {
  const { category, subCategory } = req.data || {};
  log('POLICY', 'getPolicyTemplate request', { category, subCategory });

  const template = getPolicySafe(category, subCategory);
  log('POLICY', 'success');
  return ok({ template, category, subCategory });
});

// Policy test
exports.testPolicy = wrap(async (req) => {
  const { uid } = await auth(req);
  const { policyId, testInput } = req.data || {};
  log('DEBUG', 'testPolicy request', { userId: uid, policyId });

  if (!policyId || !testInput) {
    throw new HttpsError('invalid-argument', 'policyId and testInput are required.');
  }

  const policyPrompt = getPolicySafe(policyId);
  if (!policyPrompt) {
    throw new HttpsError('not-found', 'Policy template not found.');
  }

  const fullPrompt = `${policyPrompt}\n\n입력: ${testInput}`;
  const responseText = await callGenerativeModel(fullPrompt);

  log('DEBUG', 'testPolicy done', { policyId });
  return ok({ 
    policy: policyId, 
    response: responseText, 
    usage: null 
  });
});

// User activity log
exports.logUserActivity = wrap(async (req) => {
  const { uid } = await auth(req);
  const { action, metadata } = req.data || {};
  if (!action) throw new HttpsError('invalid-argument', 'action is required.');

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

    log('ACTIVITY', 'ok', { userId: uid, action });
    return ok({ message: 'Recorded.' });
  } catch (e) {
    log('ACTIVITY', 'ignored', e.message);
    return ok({ message: 'Skipped.' });
  }
});

// System status fetch
exports.getSystemStatus = wrap(async () => {
  log('SYSTEM', 'getSystemStatus request');

  try {
    const statusDoc = await db.collection('system').doc('status').get();
    const statusData = statusDoc.exists ? statusDoc.data() : {};

    const systemStatus = {
      timestamp: new Date().toISOString(),
      gemini: statusData.gemini || { state: 'unknown' },
      database: { state: 'healthy' },
      version: process.env.FUNCTIONS_EMULATOR ? 'local' : 'production'
    };

    log('SYSTEM', 'status ok');
    return ok({ status: systemStatus });
  } catch (error) {
    log('SYSTEM', 'status error', error.message);
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

// Gemini status manual update (admin only)
exports.updateGeminiStatus = wrap(async (req) => {
  const { uid } = await auth(req);
  const { newState } = req.data || {};

  const requesterDoc = await db.collection('users').doc(uid).get();
  const userData = requesterDoc.exists ? requesterDoc.data() : {};
  const isAdmin = userData.role === 'admin' || userData.isAdmin === true;
  if (!requesterDoc.exists || !isAdmin) {
    throw new HttpsError('permission-denied', 'Admin only.');
  }

  const allowed = ['active', 'maintenance', 'inactive'];
  if (!allowed.includes(newState)) {
    throw new HttpsError('invalid-argument', 'Invalid state.');
  }

  await db.collection('system').doc('status').set({
    geminiStatus: {
      state: newState,
      lastUpdated: admin.firestore.FieldValue.serverTimestamp(),
    }
  }, { merge: true });

  return ok({ success: true, geminiStatus: { state: newState } });
});

