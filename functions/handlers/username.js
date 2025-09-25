'use strict';

const { onRequest } = require('firebase-functions/v2/https');
const { admin, db } = require('../utils/firebaseAdmin');

function normalizeUsername(u) {
  return String(u || '').trim().toLowerCase();
}

// 아이디 사용 가능 여부 확인
const checkUsername = onRequest({ region: 'asia-northeast3', cors: true, timeoutSeconds: 30 }, async (req, res) => {
  const allowedOrigins = ['https://cyberbrain.kr', 'https://ai-secretary-6e9c8.web.app', 'https://ai-secretary-6e9c8.firebaseapp.com'];
  const origin = req.headers.origin;
  if (allowedOrigins.includes(origin)) {
    res.set('Access-Control-Allow-Origin', origin);
  }
  res.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.set('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(204).end();
  const { username } = req.method === 'GET' ? req.query : (req.body || {});
  const key = normalizeUsername(username);
  if (!key) return res.status(400).json({ available: false, reason: 'INVALID' });
  const doc = await db.collection('usernames').doc(key).get();
  return res.json({ available: !doc.exists });
});

// 아이디 선점 (트랜잭션)
const claimUsername = onRequest({ region: 'asia-northeast3', cors: true, timeoutSeconds: 60 }, async (req, res) => {
  const allowedOrigins = ['https://cyberbrain.kr', 'https://ai-secretary-6e9c8.web.app', 'https://ai-secretary-6e9c8.firebaseapp.com'];
  const origin = req.headers.origin;
  if (allowedOrigins.includes(origin)) {
    res.set('Access-Control-Allow-Origin', origin);
  }
  res.set('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.set('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'METHOD_NOT_ALLOWED' });
  try {
    const { uid, username } = req.body || {};
    const key = normalizeUsername(username);
    if (!uid || !key) return res.status(400).json({ error: 'INVALID_ARGUMENT' });
    const unameRef = db.collection('usernames').doc(key);
    await db.runTransaction(async (tx) => {
      const snap = await tx.get(unameRef);
      if (snap.exists && snap.get('uid') !== uid) {
        throw new Error('USERNAME_TAKEN');
      }
      tx.set(unameRef, { uid, username: key, createdAt: admin.firestore.FieldValue.serverTimestamp() });
      tx.set(db.collection('users').doc(uid), { username: key, updatedAt: admin.firestore.FieldValue.serverTimestamp() }, { merge: true });
    });
    return res.json({ success: true, username: key });
  } catch (e) {
    const code = e.message === 'USERNAME_TAKEN' ? 409 : 500;
    return res.status(code).json({ success: false, error: e.message });
  }
});

module.exports = { checkUsername, claimUsername };

