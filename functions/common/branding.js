'use strict';

const DEFAULT_PROJECT_ID = 'ai-secretary-6e9c8';
const DEFAULT_REGION = 'asia-northeast3';
const DEFAULT_APP_URL = 'https://cyberbrain.kr';
const DEFAULT_SUPPORT_EMAIL = 'support@cyberbrain.kr';

function normalizeUrl(value) {
  return String(value || '').replace(/\/+$/, '');
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

const projectId = process.env.GCLOUD_PROJECT || process.env.GCP_PROJECT || DEFAULT_PROJECT_ID;
const appUrl = normalizeUrl(process.env.APP_URL || DEFAULT_APP_URL);
const primaryOrigins = [appUrl];

if (appUrl === 'https://cyberbrain.kr') {
  primaryOrigins.push('https://www.cyberbrain.kr');
}

const legacyOrigins = [
  `https://${projectId}.web.app`,
  `https://${projectId}.firebaseapp.com`,
];

const localOrigins = [
  'http://localhost:3000',
  'http://localhost:5173',
  'http://localhost:5174',
  'http://127.0.0.1:5173',
];

const BRANDING = Object.freeze({
  companyNameKo: '사이버브레인',
  companyNameEn: 'CyberBrain',
  projectName: 'CyberBrain',
  serviceName: '전자두뇌비서관',
  serviceShortName: '전뇌비서관',
  appUrl,
  supportEmail: process.env.SUPPORT_EMAIL || DEFAULT_SUPPORT_EMAIL,
});

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function getAllowedOrigins({ includeLocal = false } = {}) {
  return unique([
    ...primaryOrigins,
    ...legacyOrigins,
    ...(includeLocal ? localOrigins : []),
  ]);
}

function buildFunctionsBaseUrl(region = DEFAULT_REGION) {
  return `https://${region}-${projectId}.cloudfunctions.net`;
}

function buildShortUrlPattern() {
  const originPattern = unique([BRANDING.appUrl, ...legacyOrigins])
    .map(escapeRegExp)
    .join('|');
  return new RegExp(`(?:${originPattern})\\/s\\/[0-9A-Za-z]+`, 'g');
}

module.exports = {
  BRANDING,
  DEFAULT_REGION,
  PROJECT_ID: projectId,
  getAllowedOrigins,
  buildFunctionsBaseUrl,
  buildShortUrlPattern,
};
