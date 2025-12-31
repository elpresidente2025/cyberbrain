'use strict';

const { defineSecret } = require('firebase-functions/params');

const NAVER_CLIENT_ID = defineSecret('NAVER_CLIENT_ID');
const NAVER_CLIENT_SECRET = defineSecret('NAVER_CLIENT_SECRET');
const GEMINI_API_KEY = defineSecret('GEMINI_API_KEY');

function getSecretValue(secretObj, envName) {
  try {
    if (secretObj && typeof secretObj.value === 'function') {
      const value = secretObj.value();
      if (value) return value;
    }
  } catch (_err) {}
  return process.env[envName];
}

function getGeminiApiKey() {
  return getSecretValue(GEMINI_API_KEY, 'GEMINI_API_KEY');
}

module.exports = {
  NAVER_CLIENT_ID,
  NAVER_CLIENT_SECRET,
  GEMINI_API_KEY,
  getSecretValue,
  getGeminiApiKey
};
