'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { db } = require('../utils/firebaseAdmin');

function normalizeRole(role) {
  return String(role || '').trim().toLowerCase();
}

function isAdminRole(role) {
  return normalizeRole(role) === 'admin';
}

function hasLegacyAdminFlag(userData) {
  return userData?.isAdmin === true;
}

function getAdminAccessSource(userData) {
  if (isAdminRole(userData?.role)) {
    return 'role';
  }

  if (hasLegacyAdminFlag(userData)) {
    return 'legacy-isAdmin';
  }

  return null;
}

function isAdminUser(userData) {
  return Boolean(getAdminAccessSource(userData));
}

async function requireAdmin(uid) {
  if (!uid) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  const userDoc = await db.collection('users').doc(uid).get();
  if (!userDoc.exists) {
    throw new HttpsError('not-found', '사용자 정보를 찾을 수 없습니다.');
  }

  const userData = userDoc.data() || {};
  const adminAccessSource = getAdminAccessSource(userData);

  if (!adminAccessSource) {
    throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
  }

  if (adminAccessSource === 'legacy-isAdmin') {
    console.warn('[rbac] legacy isAdmin fallback used:', { uid });
  }

  return {
    userDoc,
    userData,
    adminAccessSource
  };
}

exports.normalizeRole = normalizeRole;
exports.isAdminRole = isAdminRole;
exports.hasLegacyAdminFlag = hasLegacyAdminFlag;
exports.getAdminAccessSource = getAdminAccessSource;
exports.isAdminUser = isAdminUser;
exports.requireAdmin = requireAdmin;
