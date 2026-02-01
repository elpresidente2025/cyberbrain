'use strict';

const path = require('path');
process.env.DOTENV_CONFIG_QUIET = 'true';
require('dotenv').config({ path: path.join(__dirname, '.env') });

const { setGlobalOptions } = require('firebase-functions/v2');
require('firebase-functions/v2/https');

// ✅ [수정됨] 리전 설정 + 타임아웃 540초(9분)로 증가
// AI 생성 작업은 오래 걸릴 수 있으므로 넉넉하게 잡아줍니다.
setGlobalOptions({
  region: 'asia-northeast3',
  timeoutSeconds: 540,
  memory: '1GiB'
});

// 환경 변수 검증 (로컬/에뮬레이터 전용)
if (process.env.NODE_ENV === 'development' || process.env.FUNCTIONS_EMULATOR) {
  const REQUIRED_ENV_VARS = [
    'NAVER_CLIENT_ID',
    'NAVER_CLIENT_SECRET',
    'GEMINI_API_KEY'
  ];

  const missingVars = REQUIRED_ENV_VARS.filter(varName => !process.env[varName]);
  if (missingVars.length > 0) {
    console.error('❌ 필수 환경 변수 누락:', missingVars.join(', '));
    console.error('⚠️ 일부 기능이 정상 작동하지 않을 수 있습니다.');
  } else {
    console.log('✅ 모든 필수 환경 변수 확인 완료');
  }
}

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

// Add getPost handler
try {
  const postHandler = require('./handlers/posts-getPost');
  Object.assign(exports, postHandler);
} catch (e) {
  console.warn('[index] posts-getPost handler warning:', e?.message);
}

// Add emergency admin restore handler
try {
  const emergencyAdminHandlers = require('./handlers/emergency-admin');
  Object.assign(exports, emergencyAdminHandlers);
} catch (e) {
  console.warn('[index] emergency-admin handler warning:', e?.message);
}

// Add cleanup legacy fields handler
try {
  const cleanupLegacyFieldsHandlers = require('./handlers/cleanup-legacy-fields');
  Object.assign(exports, cleanupLegacyFieldsHandlers);
} catch (e) {
  console.warn('[index] cleanup-legacy-fields handler warning:', e?.message);
}

// Add merge user handler
try {
  const mergeUserHandlers = require('./handlers/merge-user');
  Object.assign(exports, mergeUserHandlers);
} catch (e) {
  console.warn('[index] merge-user handler warning:', e?.message);
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

// Add system config handlers
try {
  const systemConfigHandlers = require('./handlers/system-config');
  Object.assign(exports, systemConfigHandlers);
} catch (e) {
  console.warn('[index] system-config handler warning:', e?.message);
}

// Add notices handlers
try {
  const noticesHandlers = require('./handlers/notices');
  Object.assign(exports, noticesHandlers);
} catch (e) {
  console.warn('[index] notices handler warning:', e?.message);
}

// Add notifications handlers
try {
  const notificationsHandlers = require('./handlers/notifications');
  Object.assign(exports, notificationsHandlers);
} catch (e) {
  console.warn('[index] notifications handler warning:', e?.message);
}

// Add payment handlers
try {
  const paymentHandlers = require('./handlers/payment');
  Object.assign(exports, paymentHandlers);
} catch (e) {
  console.warn('[index] payment handler warning:', e?.message);
}

// Add migration handlers
try {
  const migrationHandlers = require('./handlers/migration');
  Object.assign(exports, migrationHandlers);
} catch (e) {
  console.warn('[index] migration handler warning:', e?.message);
}

// Add session handlers
try {
  const sessionHandlers = require('./handlers/session');
  Object.assign(exports, sessionHandlers);
} catch (e) {
  console.warn('[index] session handler warning:', e?.message);
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

// Add Naver Payments handlers
try {
  const naverPaymentsHandlers = require('./handlers/naver-payments');
  Object.assign(exports, naverPaymentsHandlers);
} catch (e) {
  console.warn('[index] naver-payments handler warning:', e?.message);
}

// Add Party Verification handlers
try {
  const partyVerificationHandlers = require('./handlers/party-verification');
  Object.assign(exports, partyVerificationHandlers);
} catch (e) {
  console.warn('[index] party-verification handler warning:', e?.message);
}

// Add Keyword Analysis handlers (v3.0)
try {
  const keywordAnalysisHandlers = require('./handlers/keyword-analysis');
  Object.assign(exports, keywordAnalysisHandlers);
} catch (e) {
  console.warn('[index] keyword-analysis handler warning:', e?.message);
}

// Add admin handlers
try {
  const adminHandlers = require('./handlers/admin');
  Object.assign(exports, adminHandlers);
} catch (e) {
  console.warn('[index] admin handler warning:', e?.message);
}

// Add admin-users handlers
try {
  const adminUsersHandlers = require('./handlers/admin-users');
  Object.assign(exports, adminUsersHandlers);
} catch (e) {
  console.warn('[index] admin-users handler warning:', e?.message);
}

// CRUD handlers (onCall with Firebase Auth)
try {
  const crudHandlers = require('./handlers/posts/crud-handlers');
  Object.assign(exports, crudHandlers);
} catch (e) {
  console.warn('[index] crud-handlers warning:', e?.message);
}
// Add user style trigger (Firestore)
try {
  const userStyleHandler = require('./handlers/user-style-trigger');
  Object.assign(exports, userStyleHandler);
} catch (e) {
  console.warn('[index] user-style-trigger warning:', e?.message);
}

// Add district sync handlers (scheduled + manual)
try {
  const districtSyncHandlers = require('./handlers/district-sync-handler');
  Object.assign(exports, districtSyncHandlers);
} catch (e) {
  console.warn('[index] district-sync-handler warning:', e?.message);
}
// Add URL Shortener handlers
try {
  const urlShortenerHandlers = require('./handlers/url-shortener');
  Object.assign(exports, urlShortenerHandlers);
} catch (e) {
  console.warn('[index] url-shortener handler warning:', e?.message);
}

// Add Politician Sync handlers (일 1회 동기화)
try {
  const politicianSyncHandlers = require('./handlers/politician-sync-handler');
  Object.assign(exports, politicianSyncHandlers);
} catch (e) {
  console.warn('[index] politician-sync-handler warning:', e?.message);
}

// Add Test Utils handlers (일회성 시딩용)
try {
  const testUtilsHandlers = require('./handlers/test-utils');
  Object.assign(exports, testUtilsHandlers);
} catch (e) {
  console.warn('[index] test-utils handler warning:', e?.message);
}

// Add Multimodal handlers (테스터 전용 - 카드뉴스, 숏폼, 지식 그래프)
try {
  const multimodalHandlers = require('./handlers/multimodal');
  Object.assign(exports, multimodalHandlers);
} catch (e) {
  console.warn('[index] multimodal handler warning:', e?.message);
}

