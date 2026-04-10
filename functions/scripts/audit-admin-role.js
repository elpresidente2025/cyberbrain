/**
 * 관리자 role / legacy isAdmin 분포를 감사하는 스크립트
 *
 * 사용법:
 * node scripts/audit-admin-role.js
 * node scripts/audit-admin-role.js --json
 */
'use strict';

const path = require('path');
const fs = require('fs');
const admin = require('firebase-admin');

const PROJECT_ID = 'ai-secretary-6e9c8';
const OUTPUT_JSON = process.argv.includes('--json');

function initAdmin() {
  if (admin.apps.length) {
    return admin.app();
  }

  if (process.env.GOOGLE_APPLICATION_CREDENTIALS) {
    return admin.initializeApp({
      credential: admin.credential.cert(require(process.env.GOOGLE_APPLICATION_CREDENTIALS)),
      projectId: PROJECT_ID
    });
  }

  const saPath = path.join(__dirname, '../serviceAccount.json');
  if (fs.existsSync(saPath)) {
    return admin.initializeApp({
      credential: admin.credential.cert(require(saPath)),
      projectId: PROJECT_ID
    });
  }

  return admin.initializeApp({
    credential: admin.credential.applicationDefault(),
    projectId: PROJECT_ID
  });
}

function normalizeRole(role) {
  return String(role || '').trim().toLowerCase();
}

function isRoleAdmin(userData = {}) {
  return normalizeRole(userData.role) === 'admin';
}

function isLegacyAdmin(userData = {}) {
  return userData.isAdmin === true;
}

async function main() {
  initAdmin();

  const db = admin.firestore();
  const snapshot = await db.collection('users').get();

  const summary = {
    totalUsers: snapshot.size,
    roleAdmin: 0,
    legacyAdmin: 0,
    bothAdmin: 0,
    roleOnlyAdmin: 0,
    legacyOnlyAdmin: 0,
    neitherAdmin: 0,
    conflicts: 0,
    conflictSamples: []
  };

  snapshot.forEach((doc) => {
    const data = doc.data() || {};
    const roleAdmin = isRoleAdmin(data);
    const legacyAdmin = isLegacyAdmin(data);

    if (roleAdmin) summary.roleAdmin += 1;
    if (legacyAdmin) summary.legacyAdmin += 1;

    if (roleAdmin && legacyAdmin) {
      summary.bothAdmin += 1;
    } else if (roleAdmin) {
      summary.roleOnlyAdmin += 1;
    } else if (legacyAdmin) {
      summary.legacyOnlyAdmin += 1;
    } else {
      summary.neitherAdmin += 1;
    }

    const hasConflict =
      (normalizeRole(data.role) && normalizeRole(data.role) !== 'admin' && legacyAdmin) ||
      (roleAdmin && data.isAdmin === false);

    if (hasConflict) {
      summary.conflicts += 1;
      if (summary.conflictSamples.length < 20) {
        summary.conflictSamples.push({
          uid: doc.id,
          email: data.email || null,
          name: data.name || null,
          role: data.role ?? null,
          isAdmin: data.isAdmin ?? null
        });
      }
    }
  });

  if (OUTPUT_JSON) {
    console.log(JSON.stringify(summary, null, 2));
    return;
  }

  console.log('관리자 권한 감사 결과');
  console.log('====================');
  console.log(`총 사용자 수: ${summary.totalUsers}`);
  console.log(`role admin: ${summary.roleAdmin}`);
  console.log(`legacy isAdmin: ${summary.legacyAdmin}`);
  console.log(`둘 다 admin: ${summary.bothAdmin}`);
  console.log(`role only admin: ${summary.roleOnlyAdmin}`);
  console.log(`legacy only admin: ${summary.legacyOnlyAdmin}`);
  console.log(`neither admin: ${summary.neitherAdmin}`);
  console.log(`conflicts: ${summary.conflicts}`);

  if (summary.conflictSamples.length > 0) {
    console.log('\n충돌 샘플:');
    summary.conflictSamples.forEach((sample, index) => {
      console.log(`${index + 1}. uid=${sample.uid}, role=${sample.role}, isAdmin=${sample.isAdmin}, email=${sample.email || '-'}`);
    });
  }
}

main().catch((error) => {
  console.error('관리자 감사 스크립트 실패:', error);
  process.exit(1);
});
