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
const { STATUS_CONFIG, CATEGORY_TO_WRITING_METHOD } = require('../utils/posts/constants');
const { loadUserProfile, getOrCreateSession, incrementSessionAttempts } = require('../services/posts/profile-loader');
const { extractKeywordsFromInstructions } = require('../services/posts/keyword-extractor');
const { validateAndRetry } = require('../services/posts/validation');
const { processGeneratedContent } = require('../services/posts/content-processor');
const { generateTitleFromContent } = require('../services/posts/title-generator');
const { buildSmartPrompt } = require('../prompts/prompts');
const { fetchNaverNews, compressNewsWithAI, formatNewsForPrompt, shouldFetchNews } = require('../services/news-fetcher');
const { ProgressTracker } = require('../utils/progress-tracker');
const { sanitizeElectionContent } = require('../services/election-compliance');
const { validateTopicRegion } = require('../services/region-detector');
const { isMultiAgentEnabled, generateWithMultiAgent } = require('../services/agents/pipeline-helper');
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
  const modelName = data.modelName || 'gemini-2.0-flash-exp';
  const targetWordCount = data.wordCount || 1700;

  if (!topic || typeof topic !== 'string' || topic.trim().length === 0) {
    throw new HttpsError('invalid-argument', '주제를 입력해주세요.');
  }

  if (!category || typeof category !== 'string' || category.trim().length === 0) {
    throw new HttpsError('invalid-argument', '카테고리를 선택해주세요.');
  }

  // 🔔 진행 상황 추적 시작
  const progressSessionId = `${uid}_${Date.now()}`;
  const progress = new ProgressTracker(progressSessionId);

  try {
    // 1단계: 준비 중
    await progress.stepPreparing();

    // 사용자 프로필 및 Bio 로딩
    const {
      userProfile,
      personalizedHints,
      dailyLimitWarning,
      ragContext,
      memoryContext,  // 🧠 메모리 컨텍스트 추가
      isAdmin,
      isTester
    } = await loadUserProfile(uid, category, topic);

    // 🔥 세션 조회 또는 생성 (attempts는 아직 증가하지 않음)
    // - 새 세션: attempts = 0으로 시작, 검증 성공 후 증가
    // - 기존 세션: 기존 attempts 유지, 검증 성공 후 증가
    // - 관리자: maxAttempts 999 (무제한)
    // - 테스터: 사용량 제한 면제, 하지만 maxAttempts는 3회 (일반 사용자와 동일)
    console.log('🔄 세션 관리:', sessionId ? '기존 세션 계속' : '새 세션 시작');
    let session = await getOrCreateSession(uid, isAdmin, isTester, category, topic);

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
    const fullRegion = generateNaturalRegionTitle(userProfile.regionLocal, userProfile.regionMetro);
    const customTitle = userProfile.customTitle || '';

    // 🔥 현역 의원 여부 판단 (politicalExperience 활용)
    const isCurrentLawmaker = ['초선', '재선', '3선이상'].includes(politicalExperience);

    // 가족 상황 (자녀 없는 사용자의 환각 방지용)
    const familyStatus = userProfile.familyStatus || '';

    // 호칭 결정
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
    if (shouldFetchNews(category)) {
      try {
        const news = await fetchNaverNews(sanitizedTopic, 3);
        if (news && news.length > 0) {
          const compressedNews = await compressNewsWithAI(news);
          newsContext = formatNewsForPrompt(compressedNews);
        }
      } catch (newsError) {
        console.warn('⚠️ 뉴스 조회 실패 (무시하고 계속):', newsError.message);
      }
    }

    // 🗺️ 지역 검증: 주제 지역과 사용자 지역구 (또는 목표 선거 지역) 비교
    // 직책별 관할 범위: 광역단체장(시도 전체), 기초단체장(시군구 전체), 의원(선거구 기준)
    let regionHint = '';
    try {
      const regionResult = await validateTopicRegion(
        userProfile.regionLocal,    // 현재 지역구 (예: "사하구")
        userProfile.regionMetro,    // 현재 광역단체 (예: "부산광역시")
        sanitizedTopic,
        userProfile.targetElection, // 목표 선거 정보 (있으면 이 지역/직책 기준으로 비교)
        userProfile.position        // 현재 직책 (예: "국회의원", "기초자치단체장")
      );
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

    // 🤖 Multi-Agent 모드 체크
    const useMultiAgent = await isMultiAgentEnabled();
    let generatedContent = null;
    let generatedTitle = null;
    let multiAgentMetadata = null;

    if (useMultiAgent) {
      // ═══════════════════════════════════════════════════════════════
      // 🤖 Multi-Agent 전체 파이프라인 (통합 리팩토링 버전)
      // KeywordAgent → WriterAgent → ComplianceAgent → SEOAgent
      // ═══════════════════════════════════════════════════════════════
      console.log('🤖 [Multi-Agent] 전체 파이프라인 모드 활성화');

      // 3단계: AI 원고 작성 중
      await progress.stepGenerating();

      try {
        const multiAgentResult = await generateWithMultiAgent({
          topic: sanitizedTopic,
          category,
          userProfile: {
            ...userProfile,
            status: currentStatus,
            isCurrentLawmaker,
            politicalExperience,
            familyStatus
          },
          memoryContext,
          instructions: data.instructions,
          newsContext,
          regionHint,
          keywords: backgroundKeywords,
          targetWordCount
        });

        generatedContent = multiAgentResult.content;
        generatedTitle = multiAgentResult.title;
        multiAgentMetadata = multiAgentResult.metadata;

        console.log('✅ [Multi-Agent] 생성 완료', {
          wordCount: multiAgentResult.wordCount,
          seoScore: multiAgentMetadata?.seo?.score,
          compliancePassed: multiAgentMetadata?.compliance?.passed
        });

      } catch (multiAgentError) {
        console.error('❌ [Multi-Agent] 파이프라인 실패, 기존 방식으로 폴백:', multiAgentError.message);
        // 폴백: 기존 방식으로 계속 진행 (아래 코드 실행)
      }
    }

    // 기존 방식 (Multi-Agent 비활성화 또는 실패 시)
    if (!generatedContent) {
      // 작법 결정
      const writingMethod = CATEGORY_TO_WRITING_METHOD[category] || 'emotional_writing';

      // 🧠 메모리 컨텍스트와 개인화 힌트 통합
      const combinedHints = [personalizedHints, memoryContext]
        .filter(h => h && h.trim())
        .join(' | ');

      // 프롬프트 생성
      const prompt = await buildSmartPrompt({
      writingMethod,
      topic: sanitizedTopic,
      authorBio: `${fullName} (${displayTitle}, ${fullRegion || ''})`,
      targetWordCount,
      instructions: data.instructions,
      keywords: backgroundKeywords,
      newsContext,
      personalizedHints: combinedHints,  // 🧠 통합된 힌트 사용
      applyEditorialRules: true,
      // 원외 인사 판단 정보 추가
      isCurrentLawmaker,
      politicalExperience,
      currentStatus,
      // 선거법 준수를 위한 사용자 상태 (준비/현역/예비/후보)
      status: currentStatus,
      // 가족 상황 (자녀 환각 방지)
      familyStatus,
      // 🗺️ 타 지역 주제 시 관점 안내
      regionHint
    });

    // 🔍 디버깅: 프롬프트 로깅 (처음 1000자만)
    console.log('📋 생성된 프롬프트 (처음 1000자):', prompt.substring(0, 1000));
    console.log('📋 프롬프트 전체 길이:', prompt.length, '자');

    // 3단계: AI 원고 작성 중
    await progress.stepGenerating();

    // AI 호출 및 휴리스틱 검증 + Critic Agent 검토
    const apiResponse = await validateAndRetry({
      prompt,
      modelName,
      fullName,
      fullRegion,
      targetWordCount,
      userKeywords,        // 사용자 입력 키워드 (엄격 검증)
      autoKeywords: extractedKeywords,  // 자동 추출 키워드 (완화 검증)
      status: currentStatus,  // 선거법 검증용 (준비/현역/예비/후보)
      ragContext,          // Critic Agent 팩트 검증용
      authorName: fullName,  // Corrector Agent 톤 유지용
      topic: sanitizedTopic,  // Critic Agent 문맥 이해용
      maxAttempts: 3,      // 휴리스틱 검증 실패 시 재시도 (빠름)
      maxCriticAttempts: 2   // Critic Agent 루프 최대 반복
    });

      // JSON 파싱
      let parsedResponse;
      try {
        try {
          console.log('🔍 AI 원본 응답 (첫 500자):', apiResponse.substring(0, 500));
          parsedResponse = JSON.parse(apiResponse);
          console.log('✅ 직접 JSON 파싱 성공');
        } catch (directParseError) {
          const jsonMatch = apiResponse.match(/```json\s*([\s\S]*?)\s*```/);
          if (jsonMatch) {
            parsedResponse = JSON.parse(jsonMatch[1]);
          } else {
            const cleaned = apiResponse.trim();
            const firstBrace = cleaned.indexOf('{');
            const lastBrace = cleaned.lastIndexOf('}');
            if (firstBrace !== -1 && lastBrace !== -1) {
              parsedResponse = JSON.parse(cleaned.substring(firstBrace, lastBrace + 1));
            } else {
              throw new Error('JSON 형식 찾기 실패');
            }
          }
        }
      } catch (parseError) {
        console.error('❌ JSON 파싱 실패:', parseError.message);
        parsedResponse = {
          title: `${sanitizedTopic} 관련 원고`,
          content: `<p>${sanitizedTopic}에 대한 의견을 나누고자 합니다.</p>`,
          wordCount: 100
        };
      }

      // 후처리
      if (parsedResponse && parsedResponse.content) {
        parsedResponse.content = processGeneratedContent({
          content: parsedResponse.content,
          fullName,
          fullRegion,
          currentStatus,
          userProfile,
          config,
          customTitle,
          displayTitle,
          isCurrentLawmaker
        });
      }

      generatedContent = parsedResponse.content;
      generatedTitle = parsedResponse.title;
    } // End of legacy generation path

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
      } else if (testMode || subscriptionStatus === 'trial') {
        // 데모/무료 체험: generationsRemaining 차감
        const currentRemaining = userData.generationsRemaining || userData.trialPostsRemaining || 0;

        if (currentRemaining > 0) {
          updateData.generationsRemaining = admin.firestore.FieldValue.increment(-1);
          const modeLabel = testMode ? '🧪 데모 모드' : '✅ 무료 체험';
          console.log(`${modeLabel} - 검증 성공, 생성 횟수 차감`, {
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

    // 4단계: 품질 검증 중
    await progress.stepValidating();

    // 5단계: 마무리 중
    await progress.stepFinalizing();

    // 제목 생성 (Multi-Agent에서 이미 생성된 경우 스킵)
    if (!generatedTitle) {
      generatedTitle = await generateTitleFromContent({
        content: generatedContent || '',
        backgroundInfo: data.instructions,
        keywords: backgroundKeywords,
        userKeywords: userKeywords,
        topic: sanitizedTopic,
        fullName,
        modelName,
        category: data.category,
        subCategory: data.subCategory,
        status: currentStatus
      });
    } else {
      console.log('🤖 [Multi-Agent] SEO 최적화 제목 사용:', generatedTitle);
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
          seoScore: multiAgentMetadata.seo?.score,
          keywords: multiAgentMetadata.keywords,
          duration: multiAgentMetadata.duration
        } : { enabled: false }
      }
    });

  } catch (error) {
    console.error('❌ generatePosts 오류:', error.message);

    // 에러 발생 시 진행 상황 업데이트
    if (progress) {
      await progress.error(error.message);
    }

    throw new HttpsError('internal', '원고 생성에 실패했습니다: ' + error.message);
  }
});
