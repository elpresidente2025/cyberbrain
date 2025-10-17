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
const { loadUserProfile, updateUsageStats } = require('../services/posts/profile-loader');
const { extractKeywordsFromInstructions } = require('../services/posts/keyword-extractor');
const { validateAndRetry } = require('../services/posts/validation');
const { processGeneratedContent } = require('../services/posts/content-processor');
const { generateTitleFromContent } = require('../services/posts/title-generator');
const { buildSmartPrompt } = require('../prompts/prompts');
const { fetchNaverNews, compressNewsWithAI, formatNewsForPrompt, shouldFetchNews } = require('../services/news-fetcher');
const { ProgressTracker } = require('../utils/progress-tracker');

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

  const useBonus = requestData?.useBonus || false;
  const data = requestData;

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
  const sessionId = `${uid}_${Date.now()}`;
  const progress = new ProgressTracker(sessionId);

  try {
    // 1단계: 준비 중
    await progress.stepPreparing();

    // 사용자 프로필 및 Bio 로딩
    const {
      userProfile,
      personalizedHints,
      dailyLimitWarning,
      isAdmin
    } = await loadUserProfile(uid, category, topic, useBonus);

    // 사용자 상태 설정
    const currentStatus = userProfile.status || '현역';
    const config = STATUS_CONFIG[currentStatus] || STATUS_CONFIG['현역'];

    // 사용자 정보
    const fullName = userProfile.name || '사용자';
    const fullRegion = generateNaturalRegionTitle(userProfile.regionLocal, userProfile.regionMetro);

    // 2단계: 자료 수집 중
    await progress.stepCollecting();

    // 뉴스 컨텍스트 조회
    let newsContext = '';
    if (shouldFetchNews(category)) {
      try {
        const news = await fetchNaverNews(topic, 3);
        if (news && news.length > 0) {
          const compressedNews = await compressNewsWithAI(news);
          newsContext = formatNewsForPrompt(compressedNews);
        }
      } catch (newsError) {
        console.warn('⚠️ 뉴스 조회 실패 (무시하고 계속):', newsError.message);
      }
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

    // 작법 결정
    const writingMethod = CATEGORY_TO_WRITING_METHOD[category] || 'emotional_writing';

    // 프롬프트 생성
    const prompt = await buildSmartPrompt({
      writingMethod,
      topic,
      authorBio: `${fullName} (${config.title || ''}, ${fullRegion || ''})`,
      targetWordCount,
      instructions: data.instructions,
      keywords: backgroundKeywords,
      newsContext,
      personalizedHints,
      applyEditorialRules: true
    });

    // 🔍 디버깅: 프롬프트 로깅 (처음 1000자만)
    console.log('📋 생성된 프롬프트 (처음 1000자):', prompt.substring(0, 1000));
    console.log('📋 프롬프트 전체 길이:', prompt.length, '자');

    // 3단계: AI 원고 작성 중
    await progress.stepGenerating();

    // AI 호출 및 검증
    const apiResponse = await validateAndRetry({
      prompt,
      modelName,
      fullName,
      fullRegion,
      targetWordCount,
      keywords: backgroundKeywords,
      maxAttempts: 3
    });

    // 4단계: 품질 검증 중 (validateAndRetry에서 이미 검증 완료)
    await progress.stepValidating();

    // JSON 파싱
    let parsedResponse;
    try {
      // Gemini 2.0은 순수 JSON을 반환하므로 직접 파싱 시도
      try {
        console.log('🔍 AI 원본 응답 (첫 500자):', apiResponse.substring(0, 500));
        parsedResponse = JSON.parse(apiResponse);
        console.log('✅ 직접 JSON 파싱 성공');
        console.log('🔍 파싱된 JSON:', JSON.stringify(parsedResponse).substring(0, 300));
      } catch (directParseError) {
        // 실패하면 코드 블록에서 추출 시도
        const jsonMatch = apiResponse.match(/```json\s*([\s\S]*?)\s*```/);
        if (jsonMatch) {
          parsedResponse = JSON.parse(jsonMatch[1]);
          console.log('✅ 코드 블록에서 JSON 파싱 성공');
        } else {
          // 마지막으로 전체에서 JSON 객체 찾기
          const cleaned = apiResponse.trim();
          const firstBrace = cleaned.indexOf('{');
          const lastBrace = cleaned.lastIndexOf('}');
          if (firstBrace !== -1 && lastBrace !== -1) {
            const jsonText = cleaned.substring(firstBrace, lastBrace + 1);
            parsedResponse = JSON.parse(jsonText);
            console.log('✅ 추출된 JSON 파싱 성공');
          } else {
            throw new Error('JSON 형식 찾기 실패');
          }
        }
      }
    } catch (parseError) {
      console.error('❌ JSON 파싱 실패:', parseError.message);
      console.error('❌ 원본 응답 (첫 500자):', apiResponse.substring(0, 500));
      parsedResponse = {
        title: `${topic} 관련 원고`,
        content: `<p>${topic}에 대한 의견을 나누고자 합니다.</p>`,
        wordCount: 100
      };
    }

    // 5단계: 마무리 중
    await progress.stepFinalizing();

    // 후처리
    if (parsedResponse && parsedResponse.content) {
      parsedResponse.content = processGeneratedContent({
        content: parsedResponse.content,
        fullName,
        fullRegion,
        currentStatus,
        userProfile,
        config
      });
    }

    // 제목 생성
    const generatedTitle = await generateTitleFromContent({
      content: parsedResponse.content || '',
      backgroundInfo: data.instructions,
      keywords: backgroundKeywords,
      topic,
      fullName,
      modelName
    });

    // 응답 데이터 구성
    const draftData = {
      id: `draft_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      title: generatedTitle,
      content: parsedResponse.content || `<p>${topic}에 대한 내용입니다.</p>`,
      wordCount: parsedResponse.wordCount || parsedResponse.content?.replace(/<[^>]*>/g, '').length || 0,
      category,
      subCategory: data.subCategory || '',
      keywords: data.keywords || '',
      generatedAt: new Date().toISOString()
    };

    // 사용량 업데이트
    await updateUsageStats(uid, useBonus, isAdmin);

    // 진행 상황 완료 표시
    await progress.complete();

    // 최종 응답
    let message = useBonus ? '보너스 원고가 성공적으로 생성되었습니다' : '원고가 성공적으로 생성되었습니다';
    if (dailyLimitWarning) {
      message += '\n\n⚠️ 하루 3회 이상 원고를 생성하셨습니다. 네이버 블로그 정책상 과도한 발행은 스팸으로 분류될 수 있으므로, 반드시 마지막 포스팅으로부터 3시간 경과 후 발행해 주세요';
    }

    return ok({
      success: true,
      message: message,
      dailyLimitWarning: dailyLimitWarning,
      drafts: draftData,
      sessionId: sessionId, // 프론트엔드에 세션 ID 전달
      metadata: {
        generatedAt: new Date().toISOString(),
        userId: uid,
        processingTime: Date.now(),
        usedBonus: useBonus
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
