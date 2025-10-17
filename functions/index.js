'use strict';

const { setGlobalOptions } = require('firebase-functions/v2');
const { onRequest } = require('firebase-functions/v2/https');

// Set region for all functions
setGlobalOptions({ region: 'asia-northeast3' });

// Add profile handlers for getUserProfile debug
try {
  const profileHandlers = require('./handlers/profile');
  Object.assign(exports, profileHandlers);
} catch (e) {
  console.warn('[index] profile handler warning:', e?.message);
}

// Add getUserPosts handler
try {
  const postsUserHandler = require('./handlers/posts-getUserPosts');
  Object.assign(exports, postsUserHandler);
} catch (e) {
  console.warn('[index] posts-getUserPosts handler warning:', e?.message);
}

// Add dashboard handlers
try {
  const dashboardHandlers = require('./handlers/dashboard');
  Object.assign(exports, dashboardHandlers);
} catch (e) {
  console.warn('[index] dashboard handler warning:', e?.message);
}

// Add system handlers
try {
  const systemHandlers = require('./handlers/system');
  Object.assign(exports, systemHandlers);
} catch (e) {
  console.warn('[index] system handler warning:', e?.message);
}

// Add notices handlers
try {
  const noticesHandlers = require('./handlers/notices');
  Object.assign(exports, noticesHandlers);
} catch (e) {
  console.warn('[index] notices handler warning:', e?.message);
}

// Add publishing handlers
try {
  const publishingHandlers = require('./handlers/publishing');
  Object.assign(exports, publishingHandlers);
} catch (e) {
  console.warn('[index] publishing handler warning:', e?.message);
}

// Add posts handlers (full version with advanced prompt system)
try {
  const postsHandlers = require('./handlers/posts');
  Object.assign(exports, postsHandlers);
} catch (e) {
  console.warn('[index] posts handler warning:', e?.message);
}

// Add SNS addon handlers
try {
  const snsAddonHandlers = require('./handlers/sns-addon');
  Object.assign(exports, snsAddonHandlers);
} catch (e) {
  console.warn('[index] sns-addon handler warning:', e?.message);
}

// Add Naver login handlers
try {
  const naverLoginHandlers = require('./handlers/naver-login');
  Object.assign(exports, naverLoginHandlers);
} catch (e) {
  console.warn('[index] naver-login handler warning:', e?.message);
}

// Delete post (HTTP onRequest, Naver-only via __naverAuth)
exports.deletePost = onRequest({ region: 'asia-northeast3', cors: true }, async (req, res) => {
  try {
    if (req.method === 'OPTIONS') {
      res.status(204).end();
      return;
    }

    const { admin, db } = require('./utils/firebaseAdmin');

    // Support both Firebase SDK and raw requests
    let body = req.body || {};
    if (body && typeof body === 'object' && body.data && typeof body.data === 'object') {
      body = body.data;
    }

    // Naver-only auth
    const naverAuth = body && body.__naverAuth;
    if (!naverAuth || naverAuth.provider !== 'naver' || !naverAuth.uid) {
      res.status(401).json({ error: 'unauthenticated', message: 'Naver auth required' });
      return;
    }
    const uid = naverAuth.uid;
    delete body.__naverAuth;

    const postId = body && body.postId;
    if (!postId) {
      res.status(400).json({ error: 'invalid-argument', message: 'postId is required' });
      return;
    }

    const doc = await db.collection('posts').doc(postId).get();
    if (!doc.exists) {
      res.status(404).json({ error: 'not-found', message: 'Post not found' });
      return;
    }

    const data = doc.data() || {};
    if (data.userId !== uid) {
      res.status(403).json({ error: 'permission-denied', message: 'Not allowed' });
      return;
    }

    await db.collection('posts').doc(postId).delete();
    res.json({ data: { success: true, postId } });
  } catch (err) {
    res.status(500).json({ data: { error: 'internal', message: err.message } });
  }
});
