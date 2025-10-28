'use strict';

const { setGlobalOptions } = require('firebase-functions/v2');
const { defineSecret } = require('firebase-functions/params');

setGlobalOptions({
  region: 'asia-northeast3',
  memory: '2GiB',
  timeoutSeconds: 540,
});

// v2 onCall 옵션
const geminiApiKey = defineSecret('GEMINI_API_KEY');
const functionOptions = {
  region: 'asia-northeast3',
  memory: '2GiB',
  timeoutSeconds: 540,
  secrets: [geminiApiKey],
};

// 허용된 CORS 도메인 목록 (중앙집중화)
const ALLOWED_ORIGINS = [
  'https://cyberbrain.kr',
  'https://ai-secretary-6e9c8.web.app',
  'https://ai-secretary-6e9c8.firebaseapp.com'
];

// 개발 환경에서 localhost 추가
if (process.env.NODE_ENV === 'development' || process.env.FUNCTIONS_EMULATOR) {
  ALLOWED_ORIGINS.push('http://localhost:5173', 'http://localhost:5174');
}

module.exports = {
  functionOptions,
  ALLOWED_ORIGINS
};
