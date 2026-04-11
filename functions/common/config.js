'use strict';

const { defineSecret } = require('firebase-functions/params');
const { getAllowedOrigins } = require('./branding');

// v2 onCall 옵션
const geminiApiKey = defineSecret('GEMINI_API_KEY');
const functionOptions = {
  region: 'asia-northeast3',
  memory: '2GiB',
  timeoutSeconds: 540,
  secrets: [geminiApiKey],
};

// 허용된 CORS 도메인 목록 (중앙집중화)
const ALLOWED_ORIGINS = getAllowedOrigins({ includeLocal: true });

module.exports = {
  functionOptions,
  ALLOWED_ORIGINS
};
