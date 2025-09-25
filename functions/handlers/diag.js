'use strict';

const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');
const { auth } = require('../common/auth');
const { admin, db } = require('../utils/firebaseAdmin');

// 로그인만 하면 누구나 호출 가능 (관리자 확인용)
exports.diagWhoami = wrap(async (req) => {
  const { uid, token } = await auth(req);

  // 함수 런타임이 바라보는 프로젝트/에뮬레이터 환경 확인
  const projectId = process.env.GCLOUD_PROJECT || process.env.GCP_PROJECT || admin.app().options?.projectId || null;
  const firestoreEmu = process.env.FIRESTORE_EMULATOR_HOST || null;
  const authEmu = process.env.FIREBASE_AUTH_EMULATOR_HOST || null;
  const region = process.env.FUNCTION_REGION || 'asia-northeast3';

  // 함수 쪽 DB에서 users/{uid} 문서 읽어 admin 플래그 보이는지 확인
  let dbUser = { hasDoc: false };
  try {
    const snap = await db.collection('users').doc(uid).get();
    if (snap.exists) {
      const doc = snap.data();
      dbUser = {
        isAdmin: !!doc.isAdmin,
        role: doc.role || null,
        name: doc.name || '',
        email: doc.email || '',
        hasDoc: true
      };
    }
  } catch (dbError) {
    console.warn('Firestore 사용자 조회 실패:', dbError);
  }

  return ok({
    runtime: { 
      projectId, 
      region, 
      emulators: { 
        firestore: firestoreEmu, 
        auth: authEmu 
      } 
    },
    auth: {
      uid,
      email: token?.email || null,
      name: token?.name || null,
      tokenAdmin: !!token?.admin      // 커스텀 클레임
    },
    dbUser
  });
});