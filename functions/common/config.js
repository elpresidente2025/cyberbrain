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

module.exports = { functionOptions };
