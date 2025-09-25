'use strict';

const { onCall, onRequest, HttpsError } = require('firebase-functions/v2/https');
const { defineSecret } = require('firebase-functions/params');
const { admin, db } = require('../utils/firebaseAdmin');
const fetch = require('node-fetch');

const NAVER_CLIENT_ID = defineSecret('NAVER_CLIENT_ID');
const NAVER_CLIENT_SECRET = defineSecret('NAVER_CLIENT_SECRET');

// Normalize gender to app standard labels
function mapGender(g) {
  if (!g) return '';
  const s = String(g).trim().toUpperCase();
  if (s === 'M' || s === 'MALE' || s === '?? || s === '?⑥옄') return '?⑥꽦';
  if (s === 'F' || s === 'FEMALE' || s === '?? || s === '?ъ옄') return '?ъ꽦';
  return String(g).trim();
}
function getSecretValue(secretObj, envName) {
  try {
    if (secretObj && typeof secretObj.value === 'function') {
      const v = secretObj.value();
      if (v) return v;
    }
  } catch (_err) {}
  return process.env[envName];
}

async function getNaverUserInfo(accessToken) {
  const resp = await fetch('https://openapi.naver.com/v1/nid/me', {
    method: 'GET', headers: { Authorization: `Bearer ${accessToken}` }
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    throw new Error(`Naver userinfo failed: ${resp.status} ${text}`);
  }
  const data = await resp.json();
  if (data.resultcode !== '00' || !data.response) throw new Error(`Naver userinfo error: ${data.message || 'unknown'}`);
  return data.response;
}

async function claimUsernameForUid(uid, username) {
  const unameRef = db.collection('usernames').doc(String(username));
  await db.runTransaction(async (tx) => {
    const snap = await tx.get(unameRef);
    if (!snap.exists) {
      tx.set(unameRef, { uid, username: String(username), createdAt: admin.firestore.FieldValue.serverTimestamp() });
    } else if (snap.get('uid') !== uid) {
      // If already taken by another uid, just log (should not happen for naver.id)
      console.warn('username already taken by another uid', { username, owner: snap.get('uid') });
    }
    tx.set(db.collection('users').doc(uid), { username: String(username), updatedAt: admin.firestore.FieldValue.serverTimestamp() }, { merge: true });
  });
}

const naverLogin = onCall({ region: 'asia-northeast3' }, async () => {
  return { success: false, message: 'Use naverLoginHTTP instead' };
});

const naverLoginHTTP = onRequest({ region: 'asia-northeast3', cors: true, timeoutSeconds: 60, secrets: [NAVER_CLIENT_ID, NAVER_CLIENT_SECRET] }, async (req, res) => {
  const allowedOrigins = [
    'https://cyberbrain.kr',
    'https://www.cyberbrain.kr',
    'https://ai-secretary-6e9c8.web.app',
    'https://ai-secretary-6e9c8.firebaseapp.com',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:3000'
  ];
  const origin = req.headers.origin;
  if (allowedOrigins.includes(origin)) {
    res.set('Access-Control-Allow-Origin', origin);
  }
  res.set('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.set('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'METHOD_NOT_ALLOWED' });

  let stage = 'init';
  try {
    const body = req.body?.data || req.body || {};
    const { accessToken, naverUserInfo, code, state } = body;
    let naver;

    if (naverUserInfo) {
      stage = 'use_client_userinfo';
      naver = naverUserInfo;
    } else if (accessToken) {
      stage = 'fetch_userinfo_with_token';
      naver = await getNaverUserInfo(accessToken);
    } else if (code) {
      stage = 'exchange_code_for_token';
      const clientId = getSecretValue(NAVER_CLIENT_ID, 'NAVER_CLIENT_ID');
      const clientSecret = getSecretValue(NAVER_CLIENT_SECRET, 'NAVER_CLIENT_SECRET');
      if (!clientId || !clientSecret) throw new Error('NAVER env missing: NAVER_CLIENT_ID/SECRET');
      const params = new URLSearchParams();
      params.append('grant_type', 'authorization_code');
      params.append('client_id', clientId);
      params.append('client_secret', clientSecret);
      params.append('code', code);
      if (state) params.append('state', state);
      const tokenResp = await fetch('https://nid.naver.com/oauth2.0/token', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: params.toString() });
      if (!tokenResp.ok) throw new Error(`Token exchange failed: ${tokenResp.status} ${await tokenResp.text().catch(()=> '')}`);
      const tokenJson = await tokenResp.json();
      if (!tokenJson.access_token) throw new Error('No access_token');
      stage = 'fetch_userinfo_after_exchange';
      naver = await getNaverUserInfo(tokenJson.access_token);
    } else {
      throw new HttpsError('invalid-argument', 'accessToken or code required');
    }

    if (!naver?.id) return res.status(400).json({ error: { code: 'invalid-argument', message: 'Missing naver id', details: { stage } } });

    stage = 'query_user';
    const snap = await db.collection('users').where('naverUserId', '==', naver.id).limit(1).get();

    if (snap.empty) {
      // 誘멸????뚯썝 - ?뚯썝媛???꾩슂
      stage = 'registration_required';
      return res.status(200).json({
        result: {
          success: true, 
          registrationRequired: true,
          user: null,
          naver: { 
            id: naver.id, 
            name: naver.name || naver.nickname || null, 
            gender: naver.gender || null, 
            age: naver.age || null, 
            profile_image: naver.profile_image || null 
          },
          message: 'registration required'
        }
      });
    }

    // 湲곗〈 ?뚯썝 - 濡쒓렇???깃났 (Firebase Custom Token 諛쒓툒)
    const docSnap = snap.docs[0];
    const userData = docSnap.data();
    
    // 愿由ъ옄 沅뚰븳 ?뺤씤 諛??낅뜲?댄듃
    const adminNaverIds = (process.env.ADMIN_NAVER_IDS || 'kjk6206').split(',').map(id => id.trim());
    const shouldBeAdmin = adminNaverIds.includes(naver.id);
    const isCurrentlyAdmin = userData.isAdmin === true;
    
    const updateData = { 
      lastLoginAt: admin.firestore.FieldValue.serverTimestamp(), 
      naverUserId: naver.id 
    };
    // Backfill gender if missing
    if (!userData.gender && naver.gender) {
      updateData.gender = mapGender(naver.gender);
    }
    // (removed duplicate raw gender assignment)
    
    if (shouldBeAdmin && !isCurrentlyAdmin) {
      console.log(`?뵎 湲곗〈 ?ъ슜?먮? 愿由ъ옄濡??밴꺽: ${naver.id}`);
      updateData.isAdmin = true;
      updateData.role = 'admin';
      updateData.updatedAt = admin.firestore.FieldValue.serverTimestamp();
    }
    
    await docSnap.ref.update(updateData);

    // Ensure Firebase Auth user exists for this uid (use Firestore doc id as Auth uid)
    const uid = docSnap.id;
    try {
      await admin.auth().getUser(uid);
    } catch (_e) {
      await admin.auth().createUser({
        uid,
        displayName: userData.name || userData.displayName || null,
        photoURL: userData.profileImage || naver.profile_image || null,
        disabled: false
      }).catch(() => {});
    }
    const customToken = await admin.auth().createCustomToken(uid, { provider: 'naver' });
    
    // backfill username if missing
    try { if (!userData.username) await claimUsernameForUid(docSnap.id, naver.id); } catch (e) { console.warn('username backfill failed:', e.message); }

    return res.status(200).json({
      result: {
        success: true, 
        registrationRequired: false,
        user: { 
          uid: uid, 
          naverUserId: userData.naverUserId, 
          displayName: userData.name || userData.displayName, 
          photoURL: userData.profileImage || naver.profile_image, 
          provider: 'naver', 
          profileComplete: userData.profileComplete || false,
          isAdmin: shouldBeAdmin || isCurrentlyAdmin
        },
        customToken: customToken,
        naver: { 
          id: naver.id, 
          name: naver.name || naver.nickname || null, 
          gender: naver.gender || null, 
          age: naver.age || null, 
          profile_image: naver.profile_image || null 
        },
        message: 'login successful'
      }
    });
  } catch (err) {
    console.error('naverLoginHTTP error', { stage, error: err.message });
    return res.status(500).json({ error: { code: 'internal', message: err.message, details: { stage } } });
  }
});

const naverCompleteRegistration = onRequest({ region: 'asia-northeast3', cors: true, timeoutSeconds: 60 }, async (req, res) => {
  const allowedOrigins = ['https://cyberbrain.kr', 'https://www.cyberbrain.kr', 'https://ai-secretary-6e9c8.web.app', 'https://ai-secretary-6e9c8.firebaseapp.com'];
  const origin = req.headers.origin;
  if (allowedOrigins.includes(origin)) {
    res.set('Access-Control-Allow-Origin', origin);
  }
  res.set('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.set('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'METHOD_NOT_ALLOWED' });
  
  try {
    const { naverUserData, profileData } = req.body || {};
    
    if (!naverUserData?.id || typeof profileData !== 'object') {
      return res.status(400).json({ error: { code: 'invalid-argument', message: 'naverUserData? profileData媛 ?꾩슂?⑸땲??' } });
    }
    
    const required = ['name', 'position', 'regionMetro', 'regionLocal', 'electoralDistrict'];
    for (const k of required) { 
      if (!profileData[k] || String(profileData[k]).trim() === '') {
        return res.status(400).json({ error: { code: 'invalid-argument', message: `${k} ?꾨뱶媛 ?꾩슂?⑸땲??` } });
      }
    }
    
    // ???ъ슜??臾몄꽌 ?앹꽦
    const ref = db.collection('users').doc();
    const adminNaverIds = (process.env.ADMIN_NAVER_IDS || 'kjk6206').split(',').map(id => id.trim());
    const isAdmin = adminNaverIds.includes(naverUserData.id);
    
    const doc = {
      naverUserId: naverUserData.id,
      name: String(profileData.name).trim(),
      profileImage: naverUserData.profile_image || null,
      gender: mapGender(profileData.gender) || mapGender(naverUserData.gender) || null,
      age: naverUserData.age || null,
      position: profileData.position,
      regionMetro: profileData.regionMetro,
      regionLocal: profileData.regionLocal,
      electoralDistrict: profileData.electoralDistrict,
      status: profileData.status || '?꾩뿭',
      bio: profileData.bio || '',
      provider: 'naver',
      isNaverUser: true,
      isAdmin: isAdmin,
      role: isAdmin ? 'admin' : null,
      profileComplete: true,
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      updatedAt: admin.firestore.FieldValue.serverTimestamp()
    };
    
    // ?좏깮 ?꾨뱶??
    const optionalFields = ['ageDecade', 'ageDetail', 'familyStatus', 'backgroundCareer', 'localConnection', 'politicalExperience', 'committees', 'customCommittees', 'constituencyType', 'twitterPremium'];
    for (const field of optionalFields) {
      if (profileData[field] !== undefined) {
        doc[field] = profileData[field];
      }
    }
    
    await ref.set(doc);

    // Ensure Firebase Auth user exists and issue custom token
    try {
      await admin.auth().getUser(ref.id);
    } catch (_e) {
      await admin.auth().createUser({
        uid: ref.id,
        displayName: doc.name,
        photoURL: doc.profileImage || null,
        disabled: false
      }).catch(() => {});
    }
    const customToken = await admin.auth().createCustomToken(ref.id, { provider: 'naver' });
    
    // username ?먮룞 ?좊떦
    try { 
      await claimUsernameForUid(ref.id, naverUserData.id); 
    } catch (e) { 
      console.warn('username auto-claim failed:', e.message); 
    }
    
    if (isAdmin) {
      console.log(`?뵎 愿由ъ옄 ?ㅼ씠踰??ъ슜???깅줉: ${naverUserData.id}`);
    }
    
    return res.status(200).json({ 
      result: { 
        success: true, 
        message: '?뚯썝媛?낆씠 ?꾨즺?섏뿀?듬땲?? 濡쒓렇???섏씠吏?먯꽌 ?ㅼ씠踰꾨줈 濡쒓렇?명빐二쇱꽭??',
        user: { 
          uid: ref.id, 
          naverUserId: naverUserData.id, 
          // displayName? ??ν븯吏 ?딆?留? ?명솚?깆쓣 ?꾪빐 ?묐떟?먮뒗 name???대젮以띾땲??
          displayName: doc.name,
          isAdmin: isAdmin
        }
      } 
    });
  } catch (err) {
    console.error('naverCompleteRegistration error', err);
    return res.status(500).json({ error: { code: 'internal', message: err.message } });
  }
});

module.exports = { naverLogin, naverLoginHTTP, naverCompleteRegistration };


