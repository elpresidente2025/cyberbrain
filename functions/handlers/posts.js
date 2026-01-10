'use strict';

/**
 * Posts 핸들러 - 라우터
 *
 * 이 파일은 posts 관련 모든 엔드포인트의 라우터 역할을 합니다.
 * 실제 로직은 각 모듈로 분리되어 있습니다:
 *
 * - handlers/posts/crud-handlers.js: CRUD 작업
 * - handlers/posts/generation-handler.js: 원고 생성
 * - handlers/posts/save-handler.js: 원고 저장
 */

// CRUD handlers
const {
  getUserPosts,
  getPost,
  updatePost,
  deletePost,
  checkUsageLimit
} = require('./posts/crud-handlers');

// Save handler
const { saveSelectedPost } = require('./posts/save-handler');

// Generation handler는 아직 분리하지 않았으므로 기존 파일에서 가져옴
// TODO: generation-handler.js로 분리 예정
const { HttpsError } = require('firebase-functions/v2/https');
const { httpWrap } = require('../common/http-wrap');
const { admin, db } = require('../utils/firebaseAdmin');
const { ok, generateNaturalRegionTitle } = require('../utils/posts/helpers');
const { STATUS_CONFIG } = require('../utils/posts/constants');
const { buildFactAllowlist } = require('../utils/fact-guard');
const { loadUserProfile, getOrCreateSession, incrementSessionAttempts } = require('../services/posts/profile-loader');
const { extractKeywordsFromInstructions } = require('../services/posts/keyword-extractor');
const { validateKeywordInsertion } = require('../services/posts/validation');
const { refineWithLLM, buildFollowupValidation, applyHardConstraintsOnly, expandContentToTarget } = require('../services/posts/editor-agent');
const { processGeneratedContent, trimTrailingDiagnostics, trimAfterClosing, ensureParagraphTags, ensureSectionHeadings, moveSummaryToConclusionStart, cleanupPostContent, getIntroBlockCount, splitBlocksIntoSections } = require('../services/posts/content-processor');
const { generateAeoSubheadings, optimizeHeadingsInContent } = require('../services/posts/subheading-agent');
const { callGenerativeModel } = require('../services/gemini');
const { generateTitleFromContent } = require('../services/posts/title-generator');
// buildSmartPrompt는 더 이상 사용하지 않음 (Multi-Agent가 직접 프롬프트 생성)
const { fetchNaverNews, compressNewsWithAI, formatNewsForPrompt, shouldFetchNews } = require('../services/news-fetcher');
const { ProgressTracker } = require('../utils/progress-tracker');
const { sanitizeElectionContent } = require('../services/election-compliance');
const { validateTopicRegion } = require('../services/region-detector');
const { generateWithMultiAgent } = require('../services/agents/pipeline-helper');
// 세션 관리는 이제 profile-loader에서 통합 관리 (users 문서의 activeGenerationSession 필드)
// const { createGenerationSession, incrementSessionAttempt } = require('../services/generation-session');

// CRUD 엔드포인트 export
exports.getUserPosts = getUserPosts;
exports.getPost = getPost;
exports.updatePost = updatePost;
exports.deletePost = deletePost;
exports.checkUsageLimit = checkUsageLimit;

// Save 엔드포인트 export
exports.saveSelectedPost = saveSelectedPost;

// ============================================================================
// 🎯 슬로건 삽입 헬퍼 함수
// ============================================================================

/**
 * 원고 마지막에 슬로건을 삽입
 * - "감사합니다" 앞에 삽입
 * - 줄바꿈을 <br> 또는 <p> 태그로 변환
 * @param {string} content - 원고 내용 (HTML)
 * @param {string} slogan - 슬로건 텍스트
 * @returns {string} - 슬로건이 삽입된 원고
 */
function insertSlogan(content, slogan) {
  if (!content || !slogan) return content;

  // 슬로건을 HTML 형식으로 변환(줄바꿈을 <br>로 치환)
  const sloganHtml = `<p style="text-align: center; font-weight: bold; margin: 1.5em 0;">${slogan.trim().replace(/\n/g, '<br>')}</p>`;
  const trimmed = content.trim();
  return trimmed ? `${trimmed}\n${sloganHtml}` : sloganHtml;
}


function escapeRegExp(text) {
  return String(text || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function stripGeneratedSlogan(content, slogan) {
  if (!content) return content;
  const defaultMarkers = [
    '부산의 준비된 신상품',
    '부산경제는 이재성'
  ];
  const sloganLines = String(slogan || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const markers = [...new Set([...defaultMarkers, ...sloganLines])];
  if (markers.length === 0) return content;

  const escaped = markers.map(escapeRegExp).join('|');
  const paragraphRegex = new RegExp(`<p[^>]*>[^<]*(?:${escaped})[^<]*<\\/p>\\s*`, 'gi');
  let updated = content.replace(paragraphRegex, '');
  const lineRegex = new RegExp(`(?:^|\\n)\\s*(?:${escaped})\\s*(?=\\n|$)`, 'gi');
  updated = updated.replace(lineRegex, '\n');
  return updated.replace(/\n{3,}/g, '\n\n').trim();
}

const CONTENT_BLOCK_REGEX = /<p[^>]*>[\s\S]*?<\/p>|<ul[^>]*>[\s\S]*?<\/ul>|<ol[^>]*>[\s\S]*?<\/ol>/gi;

function stripHtmlTags(text) {
  return String(text || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

function extractContentBlocks(content) {
  if (!content) return [];
  const matches = content.match(CONTENT_BLOCK_REGEX);
  return matches || [];
}

async function inferIntroBlockCountWithLLM({ blocks, fullName, modelName }) {
  if (!blocks || blocks.length < 2) return null;
  const samples = blocks.slice(0, 3)
    .map(stripHtmlTags)
    .filter(Boolean)
    .map((text) => text.length > 240 ? `${text.slice(0, 240)}…` : text);
  if (samples.length < 2) return null;

  const nameHint = fullName ? `작성자 이름: ${fullName}` : '작성자 이름: 없음';
  const prompt = [
    '다음은 블로그 글의 앞부분 문단입니다.',
    '도입부(소제목 없는 구간)에 포함될 문단 수를 1 또는 2로 판정하세요.',
    '규칙:',
    '- 1문단에 인사와 자기소개가 함께 있으면 1',
    '- 인사 다음 문단이 자기소개면 2',
    '- 그 외는 1',
    '반드시 JSON 형식으로만 답하세요.',
    nameHint,
    '',
    `1) ${samples[0]}`,
    `2) ${samples[1] || ''}`,
    `3) ${samples[2] || ''}`,
    '',
    'JSON: {"introBlockCount":1,"reason":"..."}'
  ].join('\n');

  try {
    const response = await callGenerativeModel(prompt, 1, modelName, true);
    let parsed;
    try {
      parsed = JSON.parse(response);
    } catch (parseError) {
      const jsonMatch = response.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        parsed = JSON.parse(jsonMatch[0]);
      }
    }
    const count = Number(parsed?.introBlockCount);
    if (!Number.isFinite(count)) return null;
    return count;
  } catch (error) {
    console.warn('⚠️ 도입부 문단 수 LLM 판단 실패:', error.message);
    return null;
  }
}


function needsTitleRegeneration(title, topic, rawTopic) {
  if (!title || !title.trim()) return true;

  const normalized = title.trim();
  const topics = [topic, rawTopic].filter(Boolean);

  if (normalized.endsWith('관련 원고')) return true;

  return topics.some((t) =>
    normalized === t ||
    normalized.includes(`${t} 관련`)
  );
}

// Generation 엔드포인트 (아직 분리하지 않음)
exports.generatePosts = httpWrap(async (req) => {
  console.log('🔥 generatePosts HTTP 시작');

  let uid;

  // 데이터 추출 - Firebase SDK와 HTTP 요청 모두 처리
  let requestData = req.data || req.rawRequest?.body || {};

  // 중첩된 data 구조 처리
  if (requestData.data && typeof requestData.data === 'object') {
    requestData = requestData.data;
  }

  // 사용자 인증 데이터 확인
  if (requestData.__naverAuth && requestData.__naverAuth.uid && requestData.__naverAuth.provider === 'naver') {
    console.log('📱 사용자 인증 처리:', requestData.__naverAuth.uid);
    uid = requestData.__naverAuth.uid;
    delete requestData.__naverAuth;
  } else {
    const authHeader = (req.rawRequest && (req.rawRequest.headers.authorization || req.rawRequest.headers.Authorization)) || '';
    if (authHeader && authHeader.startsWith('Bearer ')) {
      const idToken = authHeader.split('Bearer ')[1];
      try {
        const verified = await admin.auth().verifyIdToken(idToken);
        uid = verified.uid;
      } catch (authError) {
        console.error('ID token verify failed:', authError);
        throw new HttpsError('unauthenticated', '유효하지 않은 인증 토큰입니다.');
      }
    } else {
      console.error('인증 정보 누락:', requestData);
      throw new HttpsError('unauthenticated', '인증이 필요합니다.');
    }
  }

  console.log('✅ 사용자 인증 완료:', uid);

  // 🔒 우선권 체크 (결제 기반 시스템)
  const { checkGenerationPermission } = require('../services/district-priority');
  const permissionCheck = await checkGenerationPermission({ uid });

  if (!permissionCheck.allowed) {
    console.warn('⚠️ 생성 권한 없음:', { uid, reason: permissionCheck.reason });
    throw new HttpsError('permission-denied', permissionCheck.message, {
      reason: permissionCheck.reason,
      suggestion: permissionCheck.suggestion
    });
  }

  console.log('✅ 생성 권한 확인:', { reason: permissionCheck.reason, remaining: permissionCheck.remaining });

  const sessionId = requestData?.sessionId || null; // 세션 ID (재생성 시)
  const data = requestData;

  // 🆕 새 생성 요청 시 기존 세션 삭제 (3회 제한 우회 방지가 아닌, 정상적인 새 시작 허용)
  if (!sessionId) {
    try {
      const userDoc = await db.collection('users').doc(uid).get();
      const userData = userDoc.data() || {};
      if (userData.activeGenerationSession) {
        console.log('🗑️ 새 생성 요청 - 기존 세션 삭제:', userData.activeGenerationSession.id);
        await db.collection('users').doc(uid).update({
          activeGenerationSession: admin.firestore.FieldValue.delete()
        });
      }
    } catch (clearError) {
      console.warn('⚠️ 기존 세션 삭제 실패 (무시하고 계속):', clearError.message);
    }
  }

  // 데이터 검증
  const topic = data.prompt || data.topic || '';
  const category = data.category || '';
  const modelName = data.modelName || 'gemini-2.5-flash-lite';

  // 카테고리별 최소 분량 설정 (블로그 원고 기준)
  // 키는 CATEGORY_TO_WRITING_METHOD와 일치해야 함
  const CATEGORY_MIN_WORD_COUNT = {
    // 지역 현안: 깊이 있는 분석 필요 (analytical_writing)
    'local-issues': 2000,
    // 정책 제안: 논거와 근거 제시 필요 (logical_writing)
    'policy-proposal': 2000,
    // 의정활동: 상세 보고 필요 (direct_writing)
    'activity-report': 2000,
    // 시사: 분석과 견해 필요 (critical_writing)
    'current-affairs': 2000,
    // 일상 소통: 상대적으로 짧아도 됨 (emotional_writing)
    'daily-communication': 2000,
  };

  const userWordCount = data.wordCount || 2000; // 기본값 상향
  const minWordCount = CATEGORY_MIN_WORD_COUNT[category] || 2000;
  const targetWordCount = Math.max(userWordCount, minWordCount);

  if (!topic || typeof topic !== 'string' || topic.trim().length === 0) {
    throw new HttpsError('invalid-argument', '주제를 입력해주세요.');
  }

  if (!category || typeof category !== 'string' || category.trim().length === 0) {
    throw new HttpsError('invalid-argument', '카테고리를 선택해주세요.');
  }

  // 🔔 진행 상황 추적 시작
  // 🔧 프론트엔드에서 전달받은 progressSessionId 사용 (실시간 동기화)
  const progressSessionId = data.progressSessionId || `${uid}_${Date.now()}`;
  const progress = new ProgressTracker(progressSessionId);
  const perfStartTime = Date.now();
  const perfMarks = [];
  const startPerf = (label) => {
    const started = Date.now();
    return () => {
      perfMarks.push({ label, ms: Date.now() - started });
    };
  };
  const logPerf = (context) => {
    const totalMs = Date.now() - perfStartTime;
    console.log('⏱️ 생성 성능 요약', {
      context,
      uid,
      sessionId: progressSessionId,
      totalMs,
      steps: perfMarks
    });
  };

  try {
    // 1단계: 준비 중
    await progress.stepPreparing();

    // 사용자 프로필 및 Bio 로딩
    const strictSourceOnly = true;
    const stopProfile = startPerf('loadUserProfile');
    const {
      userProfile,
      personalizedHints,
      dailyLimitWarning,
      ragContext,
      memoryContext,      // 🧠 메모리 컨텍스트 추가
      bioContent,
      bioEntries,
      styleGuide,         // 🎨 문체 가이드 (Style Fingerprint 기반)
      styleFingerprint,   // 🎨 Style Fingerprint 원본 (2단계 생성용)
      isAdmin,
      isTester,
      slogan,             // 🎯 슬로건
      sloganEnabled       // 🎯 슬로건 활성화 여부
    } = await loadUserProfile(uid, category, topic, { strictSourceOnly });
    stopProfile();

    // 🔥 세션 조회 또는 생성 (attempts는 아직 증가하지 않음)
    // - 새 세션: attempts = 0으로 시작, 검증 성공 후 증가
    // - 기존 세션: 기존 attempts 유지, 검증 성공 후 증가
    // - 관리자: maxAttempts 999 (무제한)
    // - 테스터: 사용량 제한 면제, 하지만 maxAttempts는 3회 (일반 사용자와 동일)
    console.log('🔄 세션 관리:', sessionId ? '기존 세션 계속' : '새 세션 시작');
    const stopSession = startPerf('getOrCreateSession');
    let session = await getOrCreateSession(uid, isAdmin, isTester, category, topic);
    stopSession();

    // 사용자 상태 설정
    const currentStatus = userProfile.status || '현역';
    const politicalExperience = userProfile.politicalExperience || '정치 신인';
    const config = STATUS_CONFIG[currentStatus] || STATUS_CONFIG['현역'];

    // 🛡️ 입력값 선거법 준수 치환 (사용자 상태에 따라)
    // 예: "준비" 상태에서 "청년 일자리 공약" → "청년 일자리 정책 방향"
    let sanitizedTopic = topic;
    const topicSanitizeResult = sanitizeElectionContent(topic, currentStatus);
    if (topicSanitizeResult.replacementsMade > 0) {
      sanitizedTopic = topicSanitizeResult.sanitizedContent;
      console.log(`🛡️ 입력 주제 선거법 준수 치환: "${topic}" → "${sanitizedTopic}"`);
    }

    // 사용자 정보
    const fullName = userProfile.name || '사용자';
    const customTitle = userProfile.customTitle || '';

    // 🎯 목표 선거가 있으면 해당 직책/지역 기준으로 원고 작성
    const targetElection = userProfile.targetElection;
    let fullRegion = '';
    let effectivePosition = userProfile.position || '';

    if (targetElection && targetElection.position) {
      // 목표 선거 기준
      effectivePosition = targetElection.position;
      const targetPosition = targetElection.position;

      if (targetPosition === '광역자치단체장' || targetPosition.includes('시장') || targetPosition.includes('도지사')) {
        // 광역단체장: 시/도 전체가 관할 (예: "부산광역시")
        fullRegion = targetElection.regionMetro || userProfile.regionMetro || '';
        console.log('🎯 [목표선거] 광역단체장 - 시도 전체 기준:', fullRegion);
      } else if (targetPosition === '기초자치단체장' || targetPosition.includes('구청장') || targetPosition.includes('군수')) {
        // 기초단체장: 시/군/구 전체가 관할 (예: "부산광역시 사하구")
        const metro = targetElection.regionMetro || userProfile.regionMetro || '';
        const local = targetElection.regionLocal || userProfile.regionLocal || '';
        fullRegion = generateNaturalRegionTitle(local, metro);
        console.log('🎯 [목표선거] 기초단체장 - 시군구 기준:', fullRegion);
      } else {
        // 국회의원/지방의원: 선거구 기준
        const metro = targetElection.regionMetro || userProfile.regionMetro || '';
        const local = targetElection.regionLocal || userProfile.regionLocal || '';
        const electoral = targetElection.electoralDistrict || userProfile.electoralDistrict || '';
        fullRegion = electoral ? `${metro} ${electoral}` : generateNaturalRegionTitle(local, metro);
        console.log('🎯 [목표선거] 의원 - 선거구 기준:', fullRegion);
      }
    } else {
      // 현재 직책 기준 (기존 로직)
      fullRegion = generateNaturalRegionTitle(userProfile.regionLocal, userProfile.regionMetro);
    }

    const titleScope = (() => {
      const position = effectivePosition || '';
      const isMetro = position === '광역자치단체장' || position.includes('시장') || position.includes('도지사');
      if (!isMetro) return null;
      return {
        avoidLocalInTitle: true,
        position,
        regionMetro: (targetElection && targetElection.regionMetro) || userProfile.regionMetro || '',
        regionLocal: (targetElection && targetElection.regionLocal) || userProfile.regionLocal || ''
      };
    })();

    // 🔥 현역 의원 여부 판단 (politicalExperience 활용)
    const isCurrentLawmaker = ['초선', '재선', '3선이상'].includes(politicalExperience);

    // 가족 상황 (자녀 없는 사용자의 환각 방지용)
    const familyStatus = userProfile.familyStatus || '';

    // 호칭 결정 (목표 선거 직책 기준)
    let displayTitle = '';
    if (isCurrentLawmaker && currentStatus !== '은퇴') {
      // 의원 경험 있음 → "의원" 사용
      displayTitle = '의원';
    } else if (currentStatus === '준비') {
      // 원외 인사 → customTitle 우선, 없으면 빈 문자열
      displayTitle = customTitle;

      if (!displayTitle && politicalExperience === '정치 신인') {
        console.warn('⚠️ 원외 출마 준비자의 직위 정보 없음 - AI 오판 위험 (customTitle 설정 권장)');
      }
    } else {
      displayTitle = config.title || '';
    }

    // 2단계: 자료 수집 중
    await progress.stepCollecting();

    // 뉴스 컨텍스트 조회
    let newsContext = '';
    if (!strictSourceOnly && shouldFetchNews(category)) {
      try {
        const stopNewsFetch = startPerf('fetchNaverNews');
        const news = await fetchNaverNews(sanitizedTopic, 3);
        stopNewsFetch();
        if (news && news.length > 0) {
          const stopNewsCompress = startPerf('compressNewsWithAI');
          const compressedNews = await compressNewsWithAI(news);
          stopNewsCompress();
          newsContext = formatNewsForPrompt(compressedNews);
        }
      } catch (newsError) {
        console.warn('⚠️ 뉴스 조회 실패 (무시하고 계속):', newsError.message);
      }
    }

    // 🗺️ 지역 검증: 주제 지역과 사용자 지역구 (또는 목표 선거 지역) 비교
    // 직책별 관할 범위: 광역단체장(시도 전체), 기초단체장(시군구 전체), 의원(선거구 기준)
    const safeNewsContext = strictSourceOnly ? '' : newsContext;
    const safeRagContext = strictSourceOnly ? '' : ragContext;
    const safeMemoryContext = strictSourceOnly ? '' : memoryContext;

    let regionHint = '';
    try {
      const stopRegionValidation = startPerf('validateTopicRegion');
      const regionResult = await validateTopicRegion(
        userProfile.regionLocal,    // 현재 지역구 (예: "사하구")
        userProfile.regionMetro,    // 현재 광역단체 (예: "부산광역시")
        sanitizedTopic,
        userProfile.targetElection, // 목표 선거 정보 (있으면 이 지역/직책 기준으로 비교)
        userProfile.position        // 현재 직책 (예: "국회의원", "기초자치단체장")
      );
      stopRegionValidation();
      if (!regionResult.isSameRegion && regionResult.promptHint) {
        regionHint = regionResult.promptHint;
        console.log('🗺️ 타 지역 주제 감지 - 프롬프트 힌트 추가');
      }
    } catch (regionError) {
      console.warn('⚠️ 지역 검증 실패 (무시하고 계속):', regionError.message);
    }

    // 노출 희망 검색어 및 자동 추출 키워드 병합
    const extractedKeywords = extractKeywordsFromInstructions(data.instructions);

    // 🔧 수정: 쉼표로만 구분, 띄어쓰기는 유지 (네이버 검색은 띄어쓰기를 구분함)
    // 예: "민주당 청년위원장" → ['민주당 청년위원장']
    // 예: "민주당 청년위원장, 경제활성화" → ['민주당 청년위원장', '경제활성화']
    const userKeywords = data.keywords
      ? (typeof data.keywords === 'string'
        ? data.keywords.split(',').map(k => k.trim()).filter(k => k)
        : data.keywords)
      : [];

    const backgroundKeywords = [...new Set([...userKeywords, ...extractedKeywords])];

    console.log('🔑 노출 희망 검색어 (사용자 입력):', userKeywords);
    console.log('🔑 자동 추출 키워드:', extractedKeywords);
    console.log('🔑 최종 병합 키워드:', backgroundKeywords);

    const referenceTexts = [];
    if (Array.isArray(data.instructions)) {
      referenceTexts.push(...data.instructions.filter(Boolean));
    } else if (data.instructions) {
      referenceTexts.push(data.instructions);
    }
    if (Array.isArray(data.references)) {
      referenceTexts.push(...data.references.filter(Boolean));
    } else if (data.references) {
      referenceTexts.push(data.references);
    }
    if (Array.isArray(data.referenceMaterials)) {
      referenceTexts.push(...data.referenceMaterials.filter(Boolean));
    }
    if (data.reference) {
      referenceTexts.push(data.reference);
    }
    if (data.sourceText) {
      referenceTexts.push(data.sourceText);
    }
    if (bioContent) {
      referenceTexts.push(bioContent);
    }
    if (Array.isArray(bioEntries) && bioEntries.length > 0) {
      const entryTexts = bioEntries
        .map((entry) => entry && entry.content ? String(entry.content).trim() : '')
        .filter(Boolean);
      if (entryTexts.length > 0) {
        referenceTexts.push(...entryTexts);
      }
    }
    if (Array.isArray(data.additionalInfo)) {
      referenceTexts.push(...data.additionalInfo.filter(Boolean));
    } else if (data.additionalInfo) {
      referenceTexts.push(data.additionalInfo);
    }

    const sourceMaterials = referenceTexts.filter(Boolean);
    const sourceInstruction = strictSourceOnly
      ? (() => {
        if (sourceMaterials.length === 0) {
          return [
            '[SOURCE LIMIT]',
            '- No sources provided. Do not invent facts, figures, names, or organizations.',
            '- Keep content general and omit uncertain claims.'
          ].join('\n');
        }
        const lines = ['[SOURCE MATERIALS]'];
        sourceMaterials.forEach((item, idx) => {
          lines.push(`${idx + 1}. ${String(item).trim()}`);
        });
        lines.push('', '[SOURCE LIMIT]');
        lines.push('- Use only the information in the sources above.');
        lines.push('- Do not add facts/figures/names/orgs/policies not present.');
        lines.push('- If unsure, omit.');
        return lines.join('\n');
      })()
      : '';
    const instructionPayload = [data.instructions, sourceInstruction]
      .filter(Boolean)
      .map((item) => Array.isArray(item) ? item.join('\n') : String(item))
      .join('\n\n');

    const factAllowlist = buildFactAllowlist([
      sanitizedTopic,
      ...referenceTexts,
      ...userKeywords
    ]);

    // ═══════════════════════════════════════════════════════════════
    // 🤖 Multi-Agent 전체 파이프라인 (통합 리팩토링 버전)
    // KeywordAgent → WriterAgent → ComplianceAgent → SEOAgent
    // ═══════════════════════════════════════════════════════════════
    console.log('🤖 [Multi-Agent] 전체 파이프라인 실행');

    let generatedContent = null;
    let generatedTitle = null;
    let multiAgentMetadata = null;

    // 3단계: AI 원고 작성 중
    await progress.stepGenerating();

    // 파이프라인 모드 결정
    let pipelineRoute = data.pipeline || 'standard';

    // 🔒 고품질 모드(highQuality) 권한 체크: 관리자/테스터만 허용
    if (pipelineRoute === 'highQuality' && !isAdmin && !isTester) {
      console.warn(`⚠️ [권한 제한] ${uid} 사용자는 highQuality 모드 접근 권한이 없습니다. standard 모드로 전환합니다.`);
      pipelineRoute = 'standard';
    }

    const stopMultiAgentGenerate = startPerf('multiAgentGenerate');
    try {
      const multiAgentResult = await generateWithMultiAgent({
        topic: sanitizedTopic,
        category,
        subCategory: data.subCategory || '',
        userProfile: {
          ...userProfile,
          status: currentStatus,
          isCurrentLawmaker,
          politicalExperience,
          familyStatus
        },
        memoryContext: safeMemoryContext,
        instructions: instructionPayload,
        newsContext: safeNewsContext,
        regionHint,
        keywords: backgroundKeywords,
        userKeywords,  // 🔑 사용자 직접 입력 키워드 (최우선)
        factAllowlist,
        targetWordCount,
        attemptNumber: session.attempts,  // 🎯 현재 시도 번호 (수사학 전략 변형용)
        rhetoricalPreferences: userProfile.rhetoricalPreferences || {},  // 🎯 수사학 전략 선호도
        pipeline: pipelineRoute  // 🆕 파이프라인 전달 (highQuality 지원)
      });
      stopMultiAgentGenerate();

      generatedContent = multiAgentResult.content;
      generatedTitle = multiAgentResult.title;
      multiAgentMetadata = multiAgentResult.metadata;

      // 🌟 [SubheadingAgent] 소제목 최적화 (AEO 가이드 적용)
      generatedContent = await optimizeHeadingsInContent({
        content: generatedContent,
        fullName,
        fullRegion
      });

      // 🚨 [필수 교정] 사용자가 금지한 "~라는 점입니다" 말투 강제 삭제 (정규식 후처리)
      if (generatedContent) {
        generatedContent = generatedContent
          .replace(/것이라는 점입니다/g, '것입니다')
          .replace(/거라는 점입니다/g, '것입니다')
          .replace(/한다는 점입니다/g, '합니다')
          .replace(/하다는 점입니다/g, '합니다')
          .replace(/된다는 점입니다/g, '됩니다')
          .replace(/있다는 점입니다/g, '있습니다')
          .replace(/없다는 점입니다/g, '없습니다')
          .replace(/이라는 점입니다/g, '입니다') // 명사 + 이라는 점입니다 -> 입니다
          .replace(/라는 점입니다/g, '입니다')  // 나머지 케이스
          .replace(/\(출처 필요\)/g, '')       // (출처 필요) 삭제
          .replace(/\[출처 필요\]/g, '');      // [출처 필요] 삭제
      }

      // 🎯 적용된 수사학 전략 저장
      multiAgentMetadata.appliedStrategy = multiAgentResult.appliedStrategy;

      console.log('✅ [Multi-Agent] 생성 완료', {
        wordCount: multiAgentResult.wordCount,
        seoPassed: multiAgentMetadata?.seo?.passed,
        compliancePassed: multiAgentMetadata?.compliance?.passed
      });

      if (generatedContent) {
        const stopPostProcess = startPerf('postProcess');
        generatedContent = processGeneratedContent({
          content: generatedContent,
          fullName,
          fullRegion,
          currentStatus,
          userProfile,
          config,
          customTitle,
          displayTitle,
          isCurrentLawmaker,
          category,
          subCategory: data.subCategory || ''
        });
        stopPostProcess();
      }

    } catch (multiAgentError) {
      stopMultiAgentGenerate();
      console.error('❌ [Multi-Agent] 파이프라인 실패:', multiAgentError.message);
      throw new Error(`원고 생성 실패: ${multiAgentError.message}`);
    }

    // 생성 결과 검증
    if (!generatedContent) {
      throw new Error('원고 생성 실패 - 콘텐츠가 생성되지 않았습니다.');
    }

    // 🎉 검증 성공! 이제 attempts 증가 및 생성 횟수 차감
    // 1단계: attempts 증가 (관리자만 DB에 기록 안 함, 테스터는 유료 사용자처럼 추적)
    session = await incrementSessionAttempts(uid, session, isAdmin, isTester);
    console.log('✅ 검증 성공 - attempts 증가 완료:', {
      sessionId: session.sessionId,
      attempts: session.attempts
    });

    // 2단계: 생성 횟수 차감 (새 세션인 경우, 관리자 제외)
    if (session.isNewSession && !isAdmin) {
      const userDoc = await db.collection('users').doc(uid).get();
      const userData = userDoc.data() || {};
      const subscriptionStatus = userData.subscriptionStatus || 'trial';

      // System Config에서 testMode 확인
      const systemConfigDoc = await db.collection('system').doc('config').get();
      const testMode = systemConfigDoc.exists ? (systemConfigDoc.data().testMode || false) : false;

      const updateData = {};

      // 테스터 또는 유료 구독: 월별 사용량 추적
      if (isTester || subscriptionStatus === 'active') {
        const currentMonthKey = (() => {
          const now = new Date();
          return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
        })();

        const currentMonthGenerations = userData.monthlyUsage?.[currentMonthKey]?.generations || 0;
        updateData[`monthlyUsage.${currentMonthKey}.generations`] = admin.firestore.FieldValue.increment(1);
        const label = isTester ? '🧪 테스터' : '✅ 유료 구독';
        console.log(`${label} - 검증 성공, 월별 생성 횟수 증가`, {
          sessionId: session.sessionId,
          monthKey: currentMonthKey,
          generationsBefore: currentMonthGenerations,
          generationsAfter: currentMonthGenerations + 1,
          monthlyLimit: 90
        });
      } else if (testMode) {
        // 🧪 데모 모드: 월별 사용량으로 관리 (매월 8회 자동 리셋)
        const currentMonthKey = (() => {
          const now = new Date();
          return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
        })();

        const currentMonthGenerations = userData.monthlyUsage?.[currentMonthKey]?.generations || 0;
        updateData[`monthlyUsage.${currentMonthKey}.generations`] = admin.firestore.FieldValue.increment(1);
        console.log('🧪 데모 모드 - 검증 성공, 월별 생성 횟수 증가', {
          sessionId: session.sessionId,
          monthKey: currentMonthKey,
          generationsBefore: currentMonthGenerations,
          generationsAfter: currentMonthGenerations + 1,
          monthlyLimit: 8
        });
      } else if (subscriptionStatus === 'trial') {
        // ✅ 무료 체험 (프로덕션 모드): generationsRemaining 차감
        const currentRemaining = userData.generationsRemaining || userData.trialPostsRemaining || 0;

        if (currentRemaining > 0) {
          updateData.generationsRemaining = admin.firestore.FieldValue.increment(-1);
          console.log('✅ 무료 체험 - 검증 성공, 생성 횟수 차감', {
            sessionId: session.sessionId,
            generationsBefore: currentRemaining,
            generationsAfter: currentRemaining - 1
          });
        }
      }

      // 업데이트 실행
      if (Object.keys(updateData).length > 0) {
        await db.collection('users').doc(uid).update(updateData);
        console.log('✅ 생성 횟수 업데이트 완료');
      }
    }

    // Quality check
    await progress.stepValidating();

    const isMultiAgent = Boolean(multiAgentMetadata);

    // Quality gate: Multi-Agent uses Orchestrator; legacy uses refinement loop
    if (isMultiAgent) {
      console.log('[Multi-Agent] Orchestrator 결과 요약', {
        qualityThresholdMet: multiAgentMetadata.quality?.thresholdMet,
        refinementAttempts: multiAgentMetadata.quality?.refinementAttempts,
        seoPassed: multiAgentMetadata.seo?.passed
      });

      const autoKeywords = backgroundKeywords.filter(k => !userKeywords.includes(k));
      const seoKeywordSource = userKeywords.length > 0 ? userKeywords : backgroundKeywords;
      const seoKeywords = [...new Set(seoKeywordSource)].slice(0, 5);
      const validationResult = buildFollowupValidation({
        content: generatedContent,
        title: generatedTitle,
        status: currentStatus,
        userKeywords,
        seoKeywords,
        factAllowlist,
        targetWordCount,
        maxAttempts: 1
      });
      const keywordResult = validateKeywordInsertion(
        generatedContent,
        userKeywords,
        autoKeywords,
        targetWordCount
      );

      if (!validationResult.passed || !keywordResult.valid) {
        const stopMultiAgentRefine = startPerf('multiAgentRefine');
        const refined = await refineWithLLM({
          content: generatedContent,
          title: generatedTitle,
          validationResult,
          keywordResult,
          userKeywords,
          seoKeywords,
          status: currentStatus,
          modelName,
          factAllowlist,
          targetWordCount
        });
        stopMultiAgentRefine();

        generatedContent = refined.content;
        generatedTitle = refined.title;
        console.log('? [Multi-Agent] 후속 보정 완료', {
          edited: refined.edited,
          editSummary: refined.editSummary
        });
      }
    }

    // Finalizing
    await progress.stepFinalizing();

    // 제목 생성 (Multi-Agent에서 이미 생성된 경우 스킵)
    // Quality gate: Multi-Agent uses Orchestrator; legacy uses refinement loop
    if (isMultiAgent) {
      if (needsTitleRegeneration(generatedTitle, sanitizedTopic, topic)) {
        console.log('🚨 제목 재생성 필요:', { generatedTitle, topic: sanitizedTopic });
        const stopTitleGeneration = startPerf('generateTitle');
        generatedTitle = await generateTitleFromContent({
          content: generatedContent || '',
          backgroundInfo: instructionPayload,
          keywords: backgroundKeywords,
          userKeywords: userKeywords,
          topic: sanitizedTopic,
          fullName,
          modelName,
          category: data.category,
          subCategory: data.subCategory,
          status: currentStatus,
          factAllowlist,
          titleScope
        });
        stopTitleGeneration();
      } else {
        console.log('✅ [Multi-Agent] SEO 제목 유지:', generatedTitle);
      }
    } else if (!generatedTitle || !generatedTitle.trim()) {
      console.log('🚨 [Legacy] 제목 재생성 필요:', { generatedTitle, topic: sanitizedTopic });
      const stopTitleGeneration = startPerf('generateTitle');
      generatedTitle = await generateTitleFromContent({
        content: generatedContent || '',
        backgroundInfo: instructionPayload,
        keywords: backgroundKeywords,
        userKeywords: userKeywords,
        topic: sanitizedTopic,
        fullName,
        modelName,
        category: data.category,
        subCategory: data.subCategory,
        status: currentStatus,
        factAllowlist,
        titleScope
      });
      stopTitleGeneration();
    }

    const seoKeywordSource = userKeywords.length > 0 ? userKeywords : backgroundKeywords;
    const seoKeywords = [...new Set(seoKeywordSource)].slice(0, 5);
    const finalFix = applyHardConstraintsOnly({
      content: generatedContent,
      title: generatedTitle,
      status: currentStatus,
      userKeywords,
      seoKeywords,
      factAllowlist,
      targetWordCount
    });

    if (finalFix.edited) {
      generatedContent = finalFix.content;
      generatedTitle = finalFix.title || generatedTitle;
      console.log('최종 구조/분량 보정 완료', { editSummary: finalFix.editSummary });
    }

    if (sloganEnabled && slogan && slogan.trim()) {
      // 슬로건 선거법 검증 (경고만 - 사용자 입력이므로 자동 수정 안 함)
      if (currentStatus === '준비' || currentStatus === '예비') {
        const sloganSanitizeResult = sanitizeElectionContent(slogan, currentStatus);
        if (sloganSanitizeResult.replacementsMade > 0) {
          console.warn(`⚠️ [슬로건] 선거법 위반 가능 표현 감지: "${slogan}"`);
        }
      }
    }

    if (generatedContent) {
      let normalizedContent = ensureParagraphTags(generatedContent);
      normalizedContent = stripGeneratedSlogan(normalizedContent, slogan);
      const blocks = extractContentBlocks(normalizedContent);
      const introBlockCount = getIntroBlockCount(blocks, { fullName });
      let bodyHeadings = null;
      const conclusionBlockCount = 1;
      const bodyBlocks = blocks.slice(introBlockCount, blocks.length - conclusionBlockCount);
      let desiredBodyHeadings = bodyBlocks.length >= 6 ? 3 : 2;
      if (bodyBlocks.length < desiredBodyHeadings) {
        desiredBodyHeadings = Math.max(1, bodyBlocks.length);
      }
      if (desiredBodyHeadings > 0 && bodyBlocks.length > 0) {
        const sections = splitBlocksIntoSections(bodyBlocks, desiredBodyHeadings);
        const sectionTexts = sections.map((section) => section.join('\n'));
        try {
          const generatedHeadings = await generateAeoSubheadings({
            sections: sectionTexts,
            modelName,
            fullName,
            fullRegion
          });
          if (generatedHeadings && generatedHeadings.length > 0) {
            bodyHeadings = generatedHeadings;
          }
        } catch (headingError) {
          console.warn('⚠️ AEO 소제목 생성 실패:', headingError.message);
        }
      }
      generatedContent = ensureSectionHeadings(
        normalizedContent,
        {
          category,
          subCategory: data.subCategory || '',
          fullName,
          introBlockCount,
          bodyHeadings
        }
      );
      const expanded = await expandContentToTarget({
        content: generatedContent,
        targetWordCount,
        modelName,
        status: currentStatus
      });
      if (expanded?.edited) {
        generatedContent = expanded.content;
      }
      generatedContent = moveSummaryToConclusionStart(generatedContent);
      generatedContent = cleanupPostContent(generatedContent);
      generatedContent = stripGeneratedSlogan(generatedContent, slogan);
      const allowDiagnosticTail = category === 'current-affairs'
        && data.subCategory === 'current_affairs_diagnosis';
      generatedContent = trimTrailingDiagnostics(generatedContent, { allowDiagnosticTail });
      generatedContent = trimAfterClosing(generatedContent);
      if (sloganEnabled && slogan && slogan.trim()) {
        generatedContent = insertSlogan(generatedContent, slogan);
      }
    }

    // 글자수 계산
    const wordCount = generatedContent
      ? generatedContent.replace(/<[^>]*>/g, '').length
      : 0;

    // 응답 데이터 구성
    const draftData = {
      id: `draft_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      title: generatedTitle,
      content: generatedContent || `<p>${sanitizedTopic}에 대한 내용입니다.</p>`,
      wordCount,
      category,
      subCategory: data.subCategory || '',
      keywords: data.keywords || '',
      generatedAt: new Date().toISOString()
    };

    // 진행 상황 완료 표시
    await progress.complete();

    // 최종 응답
    let message = '원고가 성공적으로 생성되었습니다';
    if (dailyLimitWarning) {
      message += '\n\n⚠️ 하루 3회 이상 원고를 생성하셨습니다. 네이버 블로그 정책상 과도한 발행은 스팸으로 분류될 수 있으므로, 반드시 마지막 포스팅으로부터 3시간 경과 후 발행해 주세요';
    }

    // 재생성 안내 메시지 추가
    if (session.attempts < session.maxAttempts) {
      message += `\n\n💡 마음에 들지 않으시면 재생성을 ${session.maxAttempts - session.attempts}회 더 하실 수 있습니다.`;
    }

    logPerf('success');

    return ok({
      success: true,
      message: message,
      dailyLimitWarning: dailyLimitWarning,
      drafts: draftData,
      // 세션 정보 (프론트엔드에서 재생성 시 사용)
      sessionId: session.sessionId,
      attempts: session.attempts,
      maxAttempts: session.maxAttempts,
      canRegenerate: session.attempts < session.maxAttempts,
      metadata: {
        generatedAt: new Date().toISOString(),
        userId: uid,
        processingTime: Date.now(),
        // 🤖 Multi-Agent 메타데이터 (활성화된 경우)
        multiAgent: multiAgentMetadata ? {
          enabled: true,
          pipeline: multiAgentMetadata.pipeline,
          compliancePassed: multiAgentMetadata.compliance?.passed,
          complianceIssues: multiAgentMetadata.compliance?.issueCount || 0,
          seoPassed: multiAgentMetadata.seo?.passed,
          keywords: multiAgentMetadata.keywords,
          duration: multiAgentMetadata.duration,
          appliedStrategy: multiAgentMetadata.appliedStrategy || null  // 🎯 적용된 수사학 전략
        } : { enabled: false },
        // 🎨 고품질 모드 메타데이터 (레거시 모드에서만 사용, 현재 비활성화)
        highQuality: { enabled: false }
      }
    });

  } catch (error) {
    console.error('❌ generatePosts 오류:', error.message);
    logPerf('error');

    // 에러 발생 시 진행 상황 업데이트
    if (progress) {
      await progress.error(error.message);
    }

    throw new HttpsError('internal', '원고 생성에 실패했습니다: ' + error.message);
  }
});
