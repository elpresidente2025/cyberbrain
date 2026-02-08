// functions/handlers/sns-addon.js
const { onCall, HttpsError } = require('firebase-functions/v2/https');
const { wrap } = require('../common/wrap');
const { httpWrap } = require('../common/http-wrap');
const { ok, error } = require('../common/response');
const { admin, db } = require('../utils/firebaseAdmin');
const { callGenerativeModel } = require('../services/gemini');
const { buildFactAllowlist, findUnsupportedNumericTokens } = require('../utils/fact-guard');
const { buildSNSPrompt, SNS_LIMITS } = require('../prompts/builders/sns-conversion');
const { rankAndSelect } = require('../services/sns-ranker');

// Base62 definition for shortener
const CHARS = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ';
function generateCode(length = 6) {
  let result = '';
  for (let i = 0; i < length; i++) {
    result += CHARS.charAt(Math.floor(Math.random() * CHARS.length));
  }
  return result;
}

/**
 * Generate Short URL (Internal Helper)
 */
async function generateShortLink(originalUrl, uid, postId, platform) {
  if (!originalUrl) return '';

  try {
    // Check for existing link for this exact context to avoid duplicates?
    // For simplicity and speed, just generate new one.

    let shortCode;
    let isUnique = false;
    let attempts = 0;

    // Retry loop for uniqueness
    while (!isUnique && attempts < 3) {
      shortCode = generateCode(6);
      const doc = await db.collection('short_links').doc(shortCode).get();
      if (!doc.exists) isUnique = true;
      attempts++;
    }

    if (!isUnique) return originalUrl; // Fallback to original if fails

    await db.collection('short_links').doc(shortCode).set({
      originalUrl,
      shortCode,
      userId: uid || 'system',
      postId: postId || null,
      platform: platform || 'sns-autogen',
      clicks: 0,
      createdAt: admin.firestore.FieldValue.serverTimestamp()
    });

    // Return the relative path, frontend/client handles domain
    // Or if we know the domain... 
    // Construct absolute URL if possible, or just returned simplified one.
    // For CTA text, absolute URL is needed.
    // We'll use a placeholder domain or relative if the client fills it?
    // "https://ai-secretary-6e9c8.web.app/s/" + shortCode
    // Better to use a configured base URL.
    // For now hardcode the hosting URL since I saw it in logs: https://ai-secretary-6e9c8.web.app
    const baseUrl = 'https://ai-secretary-6e9c8.web.app';
    return `${baseUrl}/s/${shortCode}`;

  } catch (error) {
    console.error('Short link generation failed:', error);
    return originalUrl;
  }
}

/**
 * 공백 제외 글자수 계산
// ... (rest of imports)


/**
 * 공백 제외 글자수 계산 (Java 코드와 동일한 로직)
 * @param {string} str - 계산할 문자열
 * @returns {number} 공백을 제외한 글자수
 */
function countWithoutSpace(str) {
  if (!str) return 0;
  let count = 0;
  for (let i = 0; i < str.length; i++) {
    if (!/\s/.test(str.charAt(i))) { // 공백 문자가 아닌 경우
      count++;
    }
  }
  return count;
}

function collectUnsupportedNumbers(text, allowlist) {
  if (!allowlist) return [];
  const check = findUnsupportedNumericTokens(text, allowlist);
  // 상세 로그 (디버그용)
  if (check.derived?.length > 0) {
    console.log('📊 [FactGuard] 파생 수치 허용:', check.derived.join(', '));
  }
  if (check.common?.length > 0) {
    console.log('📊 [FactGuard] 일반 상식 허용:', check.common.join(', '));
  }
  return check.unsupported || [];
}

function collectUnsupportedNumbersFromPosts(posts, allowlist) {
  if (!allowlist || !Array.isArray(posts)) return [];
  const unsupported = new Set();
  posts.forEach((post) => {
    const check = findUnsupportedNumericTokens(post.content || '', allowlist);
    (check.unsupported || []).forEach((token) => unsupported.add(token));
  });
  return Array.from(unsupported);
}

function getThreadLengthStats(posts, minLength) {
  const lengths = posts.map(post => countWithoutSpace((post.content || '').trim()));
  const total = lengths.reduce((sum, length) => sum + length, 0);
  const averageLength = lengths.length ? Math.round(total / lengths.length) : 0;
  const shortCount = lengths.filter(length => length < minLength).length;
  return { lengths, averageLength, shortCount };
}

function getThreadLengthAdjustment(posts, minLength, minPosts) {
  if (!Array.isArray(posts) || posts.length === 0) return null;
  if (posts.length <= minPosts) return null;

  const stats = getThreadLengthStats(posts, minLength);
  const tooShort = stats.averageLength < minLength || stats.shortCount >= Math.ceil(posts.length / 2);

  if (!tooShort) return null;

  return {
    targetPostCount: Math.max(minPosts, posts.length - 1),
    stats
  };
}

function normalizeBlogUrl(url) {
  if (!url) return '';
  const trimmed = String(url).trim();
  if (!trimmed || trimmed === 'undefined' || trimmed === 'null') return '';
  return trimmed;
}

function buildThreadCtaText(blogUrl) {
  if (!blogUrl) return '';
  return `더 자세한 내용은 블로그에서 확인해주세요: ${blogUrl}`;
}

async function applyThreadCtaToLastPost(posts, blogUrl, platform, platformConfig, context = {}) {
  const normalizedUrl = normalizeBlogUrl(blogUrl);
  if (!normalizedUrl || !Array.isArray(posts) || posts.length === 0) return posts;

  // 🔗 Generate Short Link
  const shortUrl = await generateShortLink(
    normalizedUrl,
    context.uid,
    context.postId,
    platform
  );

  const ctaText = buildThreadCtaText(shortUrl);
  if (!ctaText) return posts;

  const lastIndex = posts.length - 1;
  const lastPost = posts[lastIndex] || {};
  const lastContent = (lastPost.content || '').trim();

  // Check if original URL is already there (unlikely if we just generated short one)
  if (lastContent.includes(normalizedUrl)) return posts;

  const separator = lastContent ? '\n' : '';
  const nextContent = `${lastContent}${separator}${ctaText}`.trim();

  return posts.map((post, index) => {
    if (index !== lastIndex) return post;
    return {
      ...post,
      content: nextContent,
      wordCount: countWithoutSpace(nextContent)
    };
  });
}

// SNS 플랫폼별 제한사항은 prompts/builders/sns-conversion.js에서 import

/**
 * 사용자 프로필에 따른 X(트위터) 글자수 제한 반환
 * @param {Object} userProfile - 사용자 프로필 정보
 * @param {number} originalLength - 원본 글자수 (공백 제외)
 * @returns {Object} X 플랫폼 제한 정보
 */
function getXLimits(userProfile, originalLength = 0) {
  const isPremium = userProfile.twitterPremium === '구독';
  const premiumLimit = isPremium ? Math.min(originalLength, 25000) : 250; // 원본 글자수를 넘지 않음
  return {
    maxLength: premiumLimit,
    recommendedLength: premiumLimit,
    hashtagLimit: 2
  };
}


/**
 * SNS 변환 테스트 함수
 */
exports.testSNS = wrap(async (req) => {
  console.log('🔥 testSNS 함수 호출됨');
  return { success: true, message: 'SNS 함수가 정상 작동합니다.' };
});

/**
 * 원고를 모든 SNS용으로 변환
 */
exports.convertToSNS = wrap(async (req) => {
  console.log('🔥 convertToSNS 함수 시작');

  const { uid } = req.auth || {};

  if (!uid) {
    console.log('❌ 인증되지 않은 요청');
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  const { postId, modelName, targetPlatform } = req.data || {};

  console.log('📝 입력 데이터:', { uid, postId, modelName });

  console.log('🔍 받은 데이터:', { uid, postId, modelName, typeof_postId: typeof postId });

  if (!postId) {
    throw new HttpsError('invalid-argument', '원고 ID가 필요합니다.');
  }

  // postId를 문자열로 변환 (숫자나 문자열 모두 허용)
  const postIdStr = String(postId).trim();

  if (!postIdStr || postIdStr === 'undefined' || postIdStr === 'null') {
    throw new HttpsError('invalid-argument', `유효하지 않은 원고 ID: "${postId}"`);
  }

  try {
    // 1. 사용자 정보 및 SNS 애드온 상태 확인
    const userDoc = await db.collection('users').doc(uid).get();
    if (!userDoc.exists) {
      throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
    }

    const userData = userDoc.data();
    const userRole = userData.role || 'local_blogger';
    const userPlan = userData.plan || userData.subscription;

    // 관리자는 모든 제한 무시
    const isAdmin = userData.role === 'admin' || userData.isAdmin === true;

    // 2. 원고 조회 (사용량 제한 없음)
    const postDoc = await db.collection('posts').doc(postIdStr).get();
    if (!postDoc.exists) {
      throw new HttpsError('not-found', '원고를 찾을 수 없습니다.');
    }

    const postData = postDoc.data();
    const blogUrl = normalizeBlogUrl(postData.publishUrl);

    // 원고 소유권 확인
    if (postData.userId !== uid) {
      throw new HttpsError('permission-denied', '본인의 원고만 변환할 수 있습니다.');
    }

    // 3. 사용자 메타데이터 가져오기
    const userProfile = userData.profile || {};
    const userInfo = {
      name: userProfile.name || '정치인',
      position: userProfile.position || '의원',
      region: userProfile.region || '지역',
      experience: userProfile.experience || '',
      values: userProfile.values || '',
      tone: userProfile.tone || 'formal' // formal, friendly, professional
    };

    // 4. 모든 플랫폼에 대해 SNS 변환 실행
    const originalContent = postData.content;
    const postKeywords = postData.keywords || '';
    let platforms = Object.keys(SNS_LIMITS);

    // 🎯 특정 플랫폼만 재생성하는 경우
    if (targetPlatform) {
      if (!platforms.includes(targetPlatform)) {
        throw new HttpsError('invalid-argument', `지원하지 않는 플랫폼입니다: ${targetPlatform}`);
      }
      platforms = [targetPlatform];
      console.log(`🎯 단일 플랫폼 재생성 모드: ${targetPlatform}`);
    }

    const results = {};

    // 사용할 모델 결정 (기본값: gemini-2.5-flash-lite)
    const selectedModel = modelName || 'gemini-2.5-flash';
    console.log('🔄 모든 SNS 플랫폼 변환 시작:', { postId: postIdStr, userRole, userInfo, selectedModel });

    // 각 플랫폼별로 병렬 처리로 변환 (재시도 로직 포함)
    console.log(`🚀 ${platforms.length}개 플랫폼 병렬 변환 시작`);

    // 원본 글자수 계산 (공백 제외)
    const originalLength = countWithoutSpace(originalContent);
    const cleanedOriginalContent = cleanContent(originalContent || '');
    const cleanedOriginalLength = countWithoutSpace(cleanedOriginalContent);
    const factAllowlist = buildFactAllowlist([originalContent]);

    const platformPromises = platforms.map(async (platform) => {
      // X(트위터)는 사용자 프리미엄 구독 여부에 따라 동적 제한 적용
      const baseConfig = SNS_LIMITS[platform];
      const platformConfig = platform === 'x'
        ? { ...baseConfig, ...getXLimits(userData, originalLength) }
        : baseConfig;
      const threadConstraints = platformConfig.isThread ? {
        minPosts: baseConfig.minPosts || 3,
        maxPosts: baseConfig.maxPosts || 7,
        minLengthPerPost: baseConfig.minLengthPerPost || 130
      } : null;
      const minimumContentLength = platformConfig.minLength
        ? Math.min(platformConfig.minLength, cleanedOriginalLength)
        : 0;

      console.log(`🔄 ${platform} 변환 시작 (2단계 랭킹)`);

      let convertedResult = null;

      try {
        // ── Stage 1: 프롬프트 생성 & 2단계 랭킹 (Light → Heavy) ──
        const snsPrompt = buildSNSPrompt(
          originalContent, platform, platformConfig, postKeywords, userInfo,
          { blogUrl, category: postData.category || '', subCategory: postData.subCategory || '' }
        );

        // 🚀 Twitter Light→Heavy Ranker 패턴: flash-lite×3 병렬 → flash 스코어링
        const { text: convertedText, ranking } = await Promise.race([
          rankAndSelect(snsPrompt, platform, cleanedOriginalContent, { platformConfig, userInfo }),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('랭킹 파이프라인 타임아웃 (60초)')), 60000)
          )
        ]);

        console.log(`🏆 ${platform} 랭킹 결과:`, {
          candidatesEvaluated: ranking.rankings?.length || 0,
          bestIndex: ranking.bestIndex,
          reason: ranking.reason,
          length: convertedText?.length || 0,
          preview: convertedText?.substring(0, 100) + '...'
        });

        // ── Stage 2: 파싱 & 검증 ──
        if (convertedText && convertedText.trim().length > 0) {
          const parsedResult = parseConvertedContent(convertedText, platform, platformConfig);

          if (parsedResult.isThread) {
            const unsupportedNumbers = collectUnsupportedNumbersFromPosts(parsedResult.posts, factAllowlist);
            if (unsupportedNumbers.length > 0) {
              console.warn('⚠️ [FactGuard] ' + platform + ' 출처 미확인 수치: ' + unsupportedNumbers.join(', ') + ' (배경자료에 없는 수치)');
            }

            const minPosts = threadConstraints?.minPosts || 3;
            const hasValidPosts = Array.isArray(parsedResult.posts) && parsedResult.posts.length >= minPosts;
            const hasHashtags = Array.isArray(parsedResult.hashtags) && parsedResult.hashtags.length > 0;
            const isValidX = platform === 'x' && Array.isArray(parsedResult.posts) && parsedResult.posts.length === 1;

            if (hasValidPosts || isValidX) {
              let threadResult = {
                isThread: true,
                posts: parsedResult.posts,
                hashtags: hasHashtags ? parsedResult.hashtags : generateDefaultHashtags(platform),
                totalWordCount: parsedResult.totalWordCount,
                postCount: parsedResult.postCount
              };

              // ── Stage 3: 타래 길이 조정 (필요 시 targetPostCount로 단일 재생성) ──
              const lengthAdjustment = (platform !== 'x' && threadConstraints)
                ? getThreadLengthAdjustment(threadResult.posts, threadConstraints.minLengthPerPost, threadConstraints.minPosts)
                : null;

              if (lengthAdjustment) {
                console.log(`🔄 ${platform} 게시물 길이 부족, ${lengthAdjustment.targetPostCount}개로 재생성`, {
                  averageLength: lengthAdjustment.stats.averageLength,
                  shortCount: lengthAdjustment.stats.shortCount
                });

                const refinedPrompt = buildSNSPrompt(
                  originalContent, platform, platformConfig, postKeywords, userInfo,
                  { targetPostCount: lengthAdjustment.targetPostCount, blogUrl, category: postData.category || '', subCategory: postData.subCategory || '' }
                );
                const refinedText = await Promise.race([
                  callGenerativeModel(refinedPrompt, 1, selectedModel),
                  new Promise((_, reject) => setTimeout(() => reject(new Error('재생성 타임아웃')), 30000))
                ]).catch(() => null);

                if (refinedText) {
                  const refinedParsed = parseConvertedContent(refinedText, platform, platformConfig);
                  if (refinedParsed.isThread && Array.isArray(refinedParsed.posts) && refinedParsed.posts.length >= minPosts) {
                    threadResult = {
                      isThread: true,
                      posts: refinedParsed.posts,
                      hashtags: (Array.isArray(refinedParsed.hashtags) && refinedParsed.hashtags.length > 0)
                        ? refinedParsed.hashtags : threadResult.hashtags,
                      totalWordCount: refinedParsed.totalWordCount,
                      postCount: refinedParsed.postCount
                    };
                  }
                }
                // 재생성 실패 시 원래 threadResult 유지
              }

              convertedResult = threadResult;
              console.log(`✅ ${platform} 타래 성공:`, {
                postCount: convertedResult.postCount,
                totalWordCount: convertedResult.totalWordCount,
                hashtagCount: convertedResult.hashtags.length
              });
            } else {
              console.warn(`⚠️ ${platform}: 타래 게시물 수 부족`);
            }
          }
          // 단일 게시물 형식 검증 (Facebook/Instagram)
          else {
            const content = (parsedResult.content || '').trim();
            const contentLength = countWithoutSpace(content);
            const meetsMinLength = minimumContentLength === 0 || contentLength >= minimumContentLength;
            const unsupportedNumbers = collectUnsupportedNumbers(content, factAllowlist);
            if (unsupportedNumbers.length > 0) {
              console.warn('⚠️ [FactGuard] ' + platform + ' 출처 미확인 수치: ' + unsupportedNumbers.join(', ') + ' (배경자료에 없는 수치)');
            }

            if (content.length > 20 && meetsMinLength) {
              convertedResult = {
                isThread: false,
                content,
                hashtags: (Array.isArray(parsedResult.hashtags) && parsedResult.hashtags.length > 0)
                  ? parsedResult.hashtags : generateDefaultHashtags(platform)
              };
              console.log(`✅ ${platform} 단일 성공: ${contentLength}자`);
            } else {
              console.warn(`⚠️ ${platform}: 콘텐츠 길이 부족 (${contentLength}자)`);
            }
          }
        }
      } catch (error) {
        console.error(`❌ ${platform} 랭킹 파이프라인 오류:`, error.message);
      }

      // ── Fallback: 랭킹+검증 모두 실패 시 기본 콘텐츠 ──
      if (!convertedResult) {
        console.warn(`⚠️ ${platform} fallback 콘텐츠 생성`);
        if (platform === 'facebook-instagram') {
          const fallbackBase = cleanedOriginalContent || `${userInfo.name}입니다. 원고 내용을 공유드립니다.`;
          convertedResult = {
            isThread: false,
            content: enforceLength(fallbackBase, platform, platformConfig),
            hashtags: generateDefaultHashtags(platform)
          };
        } else if (platform === 'x') {
          convertedResult = {
            isThread: true,
            posts: [{ order: 1, content: `${userInfo.name}입니다.\n원고 내용을 공유드립니다.`, wordCount: 20 }],
            hashtags: generateDefaultHashtags(platform),
            totalWordCount: 20,
            postCount: 1
          };
        } else {
          convertedResult = {
            isThread: true,
            posts: [
              { order: 1, content: `${userInfo.name}입니다.`, wordCount: 10 },
              { order: 2, content: originalContent.substring(0, 100), wordCount: 50 },
              { order: 3, content: '앞으로도 소통하겠습니다.', wordCount: 12 }
            ],
            hashtags: generateDefaultHashtags(platform),
            totalWordCount: 72,
            postCount: 3
          };
        }
      }

      console.log(`✅ ${platform} 변환 완료`);
      if (convertedResult?.isThread) {
        const basePosts = Array.isArray(convertedResult.posts) ? convertedResult.posts : [];
        // CTA 추가 (숏링크 생성 포함, Async)
        const threadPosts = await applyThreadCtaToLastPost(
          basePosts,
          blogUrl,
          platform,
          platformConfig,
          { uid, postId: postIdStr }
        );
        const totalWordCount = threadPosts.reduce((sum, post) => sum + countWithoutSpace(post.content), 0);
        convertedResult = {
          ...convertedResult,
          posts: threadPosts,
          totalWordCount,
          postCount: threadPosts.length
        };
      }

      return { platform, result: convertedResult };
    });

    // 모든 플랫폼 병렬 처리 완료 대기 (최대 4분)
    try {
      const platformResults = await Promise.race([
        Promise.all(platformPromises),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('전체 변환 타임아웃 (4분)')), 240000)
        )
      ]);

      // 결과 정리
      platformResults.forEach(({ platform, result }) => {
        results[platform] = result;
      });

      console.log(`🎉 모든 플랫폼 변환 완료: ${Object.keys(results).length}개`);

    } catch (error) {
      console.error('❌ 병렬 변환 실패:', error.message);
      throw new HttpsError('internal', `SNS 변환 중 타임아웃 또는 오류가 발생했습니다: ${error.message}`);
    }

    // 4. 변환 기록 저장 (모든 플랫폼 결과를 하나로 저장)
    const conversionData = {
      userId: uid,
      originalPostId: postIdStr,
      platforms: platforms,
      originalContent: originalContent,
      results: results,
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      metadata: {
        originalWordCount: originalContent.length,
        platformCount: platforms.length
      }
    };

    await db.collection('sns_conversions').add(conversionData);

    // 🆕 원고 문서에도 SNS 변환 결과 저장 (재오픈 시 불러오기 위해)
    // 🆕 원고 문서에도 SNS 변환 결과 저장 (재오픈 시 불러오기 위해)
    const updateData = {
      snsConvertedAt: admin.firestore.FieldValue.serverTimestamp()
    };

    if (targetPlatform) {
      // 단일 플랫폼 업데이트 (Dot Notation 사용)
      updateData[`snsConversions.${targetPlatform}`] = results[targetPlatform];
    } else {
      // 전체 업데이트
      updateData.snsConversions = results;
    }

    await db.collection('posts').doc(postIdStr).update(updateData);
    console.log('✅ SNS 변환 결과를 원고 문서에 저장 완료');

    // 5. 관리자가 아닌 경우 사용량 차감
    if (!isAdmin) {
      const now = new Date();
      const currentMonthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

      await db.collection('users').doc(uid).update({
        [`snsAddon.monthlyUsage.${currentMonthKey}`]: admin.firestore.FieldValue.increment(1),
        'snsAddon.lastUsedAt': admin.firestore.FieldValue.serverTimestamp()
      });

      console.log('📊 SNS 변환 사용량 차감 완료:', { uid, monthKey: currentMonthKey });
    }

    console.log('✅ 모든 SNS 플랫폼 변환 완료:', { postId: postIdStr, platformCount: platforms.length, isAdmin });

    return ok({
      results: results,
      platforms: platforms,
      metadata: conversionData.metadata
    });

  } catch (error) {
    console.error('❌ SNS 변환 실패:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', 'SNS 변환 중 오류가 발생했습니다.');
  }
});

/**
 * SNS 애드온 사용량 조회
 */
exports.getSNSUsage = wrap(async (req) => {
  const { uid } = req.auth || {};

  if (!uid) {
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  try {
    const userDoc = await db.collection('users').doc(uid).get();
    if (!userDoc.exists) {
      throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
    }

    // SNS 기능은 모든 사용자에게 무제한 제공
    return ok({
      isActive: true,
      monthlyLimit: 999999,
      currentMonthUsage: 0,
      remaining: 999999,
      accessMethod: 'basic'
    });

  } catch (error) {
    console.error('❌ SNS 사용량 조회 실패:', error);
    throw new HttpsError('internal', 'SNS 사용량 조회 중 오류가 발생했습니다.');
  }
});

/**
 * SNS 변환 결과 품질 검증 (블로그 원고 방식 적용)
 */
function validateSNSResult(parsedResult, platform, platformConfig, userInfo, targetLength) {
  try {
    const { content = '', hashtags = [] } = parsedResult;

    // 1. 기본 구조 검증
    if (!content || content.trim().length === 0) {
      return { valid: false, reason: '콘텐츠가 비어있음' };
    }

    // 2. 글자수 검증 (공백 제외)
    const actualLength = countWithoutSpace(content);
    const maxLength = platformConfig.maxLength;
    const minLength = Math.max(50, Math.floor(targetLength * 0.5)); // 최소 50자 또는 목표의 50%

    if (actualLength > maxLength) {
      return { valid: false, reason: `글자수 초과: ${actualLength}자 > ${maxLength}자` };
    }

    if (actualLength < minLength) {
      return { valid: false, reason: `글자수 부족: ${actualLength}자 < ${minLength}자` };
    }

    // 3. 사용자 이름 포함 검증
    const hasUserName = content.includes(userInfo.name);
    if (!hasUserName && userInfo.name && userInfo.name !== '사용자') {
      return { valid: false, reason: `사용자 이름 누락: "${userInfo.name}" 미포함` };
    }

    // 4. 문장 완결성 검증
    const sentences = content.split(/[.!?]/).filter(s => s.trim().length > 0);
    const lastSentence = content.trim();
    const isComplete = /[.!?]$/.test(lastSentence) || /[다니습]$/.test(lastSentence);

    if (!isComplete) {
      return { valid: false, reason: '문장이 완전히 끝나지 않음' };
    }

    // 5. 금지 표현 검증
    const forbiddenWords = ['요약', 'summary', '정리하면', '...', '[', ']', '(예시)', '(내용)'];
    const hasForbiddenWord = forbiddenWords.some(word => content.includes(word));

    if (hasForbiddenWord) {
      const foundWord = forbiddenWords.find(word => content.includes(word));
      return { valid: false, reason: `금지 표현 포함: "${foundWord}"` };
    }

    // 6. 해시태그 검증
    if (!Array.isArray(hashtags)) {
      return { valid: false, reason: '해시태그가 배열이 아님' };
    }

    const expectedHashtagCount = platformConfig.hashtagLimit;
    if (hashtags.length < 1 || hashtags.length > expectedHashtagCount) {
      return { valid: false, reason: `해시태그 개수 오류: ${hashtags.length}개 (예상: 1-${expectedHashtagCount}개)` };
    }

    // 7. 해시태그 형식 검증
    const invalidHashtags = hashtags.filter(tag => !tag.startsWith('#') || tag.trim().length < 2);
    if (invalidHashtags.length > 0) {
      return { valid: false, reason: `잘못된 해시태그 형식: ${invalidHashtags.join(', ')}` };
    }

    // 8. 플랫폼별 특별 검증
    if (platform === 'x' && actualLength > 280) {
      return { valid: false, reason: 'X 플랫폼 280자 초과' };
    }

    if (platform === 'threads' && actualLength > 500) {
      return { valid: false, reason: 'Threads 플랫폼 500자 초과' };
    }

    // 모든 검증 통과
    return {
      valid: true,
      score: calculateQualityScore(content, actualLength, targetLength, hashtags.length, expectedHashtagCount)
    };

  } catch (error) {
    console.error('품질 검증 오류:', error);
    return { valid: false, reason: `검증 오류: ${error.message}` };
  }
}

/**
 * 품질 점수 계산
 */
function calculateQualityScore(content, actualLength, targetLength, hashtagCount, expectedHashtagCount) {
  let score = 100;

  // 글자수 정확도 (±20% 이내면 만점)
  const lengthDiff = Math.abs(actualLength - targetLength) / targetLength;
  if (lengthDiff > 0.2) score -= (lengthDiff - 0.2) * 100;

  // 해시태그 정확도
  const hashtagDiff = Math.abs(hashtagCount - expectedHashtagCount);
  score -= hashtagDiff * 5;

  // 문장 구조 점수
  const sentences = content.split(/[.!?]/).filter(s => s.trim().length > 0);
  if (sentences.length < 1) score -= 20;
  if (sentences.length > 10) score -= 10;

  return Math.max(0, Math.round(score));
}

/**
 * 변환된 내용 파싱 (타래 형식 지원)
 */
function parseConvertedContent(rawContent, platform, platformConfig = null) {
  try {
    console.log(`🔍 ${platform} 파싱 시작:`, {
      rawContentLength: rawContent?.length || 0,
      rawContentPreview: rawContent?.substring(0, 200) + '...'
    });

    // 1차 시도: JSON 형식 파싱
    const jsonResult = tryParseJSON(rawContent, platform);

    // 타래 형식인 경우 (X, Threads)
    if (jsonResult.success && jsonResult.isThread) {
      const posts = jsonResult.posts.map(post => ({
        ...post,
        content: cleanContent(post.content)
      }));
      const hashtags = validateHashtags(jsonResult.hashtags, platform);

      console.log(`✅ ${platform} 타래 파싱 완료:`, {
        postCount: posts.length,
        totalWordCount: posts.reduce((sum, p) => sum + countWithoutSpace(p.content), 0),
        hashtagCount: hashtags.length
      });

      return {
        isThread: true,
        posts,
        hashtags,
        totalWordCount: posts.reduce((sum, p) => sum + countWithoutSpace(p.content), 0),
        postCount: posts.length
      };
    }

    // 단일 게시물 형식인 경우 (Facebook/Instagram)
    let content = '';
    let hashtags = [];

    if (jsonResult.success) {
      content = jsonResult.content;
      hashtags = jsonResult.hashtags;
    } else {
      // 2차 시도: 구분자 형식 파싱
      const delimiterResult = tryParseDelimiter(rawContent, platform);
      if (delimiterResult.success) {
        content = delimiterResult.content;
        hashtags = delimiterResult.hashtags;
      } else {
        // 3차 시도: 원본 텍스트 사용
        content = cleanRawContent(rawContent);
        hashtags = generateDefaultHashtags(platform);
      }
    }

    // 콘텐츠 후처리
    content = cleanContent(content);
    hashtags = validateHashtags(hashtags, platform);

    // 길이 제한 적용
    content = enforceLength(content, platform, platformConfig);

    console.log(`✅ ${platform} 단일 파싱 완료:`, {
      contentLength: countWithoutSpace(content),
      hashtagCount: hashtags.length,
      contentPreview: content.substring(0, 100) + '...'
    });

    return { isThread: false, content, hashtags };

  } catch (error) {
    console.error(`❌ ${platform} 파싱 실패:`, error);
    return {
      isThread: false,
      content: rawContent.substring(0, 200) || '',
      hashtags: generateDefaultHashtags(platform)
    };
  }
}

/**
 * JSON 파싱 시도 (타래 형식 지원)
 */
function tryParseJSON(rawContent, platform) {
  try {
    const jsonMatch = rawContent.match(/\{[\s\S]*\}/);
    if (!jsonMatch) return { success: false };

    const parsed = JSON.parse(jsonMatch[0]);
    console.log(`🔍 ${platform} JSON 구조:`, Object.keys(parsed));

    let content = '';
    let hashtags = [];
    let posts = null;

    // 타래 형식: {"posts": [...], "hashtags": [...]}
    if (Array.isArray(parsed.posts) && parsed.posts.length > 0) {
      posts = parsed.posts.map((post, idx) => ({
        order: post.order || idx + 1,
        content: (post.content || '').trim(),
        wordCount: post.wordCount || countWithoutSpace(post.content || '')
      })).filter(p => p.content.length > 0);

      hashtags = Array.isArray(parsed.hashtags) ? parsed.hashtags : [];

      if (posts.length > 0) {
        console.log(`✅ ${platform} 타래 JSON 파싱 성공: ${posts.length}개 게시물`);
        return {
          success: true,
          isThread: true,
          posts,
          hashtags,
          totalWordCount: parsed.totalWordCount || posts.reduce((sum, p) => sum + p.wordCount, 0),
          postCount: posts.length
        };
      }
    }

    // 단일 게시물 형식: {"content": "...", "hashtags": [...]}
    if (parsed.content) {
      content = parsed.content.trim();
      hashtags = Array.isArray(parsed.hashtags) ? parsed.hashtags : [];
    }
    // 중첩 형식: {"summary": {"content": "...", "hashtags": [...]}}
    else if (parsed.summary && typeof parsed.summary === 'object') {
      content = (parsed.summary.content || '').trim();
      hashtags = Array.isArray(parsed.summary.hashtags) ? parsed.summary.hashtags : [];
    }
    // 단순 형식: {"summary": "..."}
    else if (parsed.summary && typeof parsed.summary === 'string') {
      content = parsed.summary.trim();
    }
    // 대안 형식: {"text": "..."}
    else if (parsed.text) {
      content = parsed.text.trim();
      hashtags = Array.isArray(parsed.hashtags) ? parsed.hashtags : [];
    }

    if (content && content.length > 10) {
      console.log(`✅ ${platform} 단일 JSON 파싱 성공: ${content.length}자`);
      return { success: true, isThread: false, content, hashtags };
    }

    return { success: false };
  } catch (error) {
    console.log(`📝 ${platform} JSON 파싱 실패: ${error.message}`);
    return { success: false };
  }
}

/**
 * 구분자 파싱 시도
 */
function tryParseDelimiter(rawContent, platform) {
  try {
    const contentMatch = rawContent.match(/---CONTENT---([\s\S]*?)---HASHTAGS---/);
    const hashtagMatch = rawContent.match(/---HASHTAGS---([\s\S]*?)$/);

    if (contentMatch) {
      const content = contentMatch[1].trim();
      let hashtags = [];

      if (hashtagMatch) {
        hashtags = hashtagMatch[1]
          .split(/[,\s]+/)
          .map(tag => tag.trim())
          .filter(tag => tag.length > 0)
          .map(tag => tag.startsWith('#') ? tag : `#${tag}`);
      }

      if (content && content.length > 10) {
        console.log(`✅ ${platform} 구분자 파싱 성공: ${content.length}자`);
        return { success: true, content, hashtags };
      }
    }

    return { success: false };
  } catch (error) {
    console.log(`📝 ${platform} 구분자 파싱 실패: ${error.message}`);
    return { success: false };
  }
}

/**
 * 원본 텍스트 정리
 */
function cleanRawContent(rawContent) {
  return rawContent
    .replace(/---\w+---/g, '') // 구분자 제거
    .replace(/\{[\s\S]*?\}/g, '') // JSON 블록 제거
    .replace(/\n{2,}/g, '\n') // 연속된 줄바꿈 정리
    .trim();
}

/**
 * 콘텐츠 후처리
 */
function cleanContent(content) {
  return content
    // 마크다운 제거
    .replace(/```[\s\S]*?```/g, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    // HTML 태그 제거
    .replace(/<\/?(h[1-6]|p|div|br|li)[^>]*>/gi, '\n')
    .replace(/<\/?(ul|ol)[^>]*>/gi, '\n\n')
    .replace(/<[^>]*>/g, '')
    // HTML 엔티티 변환
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    // 공백 정리
    .replace(/\n{3,}/g, '\n\n')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

/**
 * 해시태그 검증 및 정리
 */
function validateHashtags(hashtags, platform) {
  if (!Array.isArray(hashtags)) hashtags = [];

  const cleaned = hashtags
    .map(tag => tag.trim())
    .filter(tag => tag.length > 1)
    .map(tag => tag.startsWith('#') ? tag : `#${tag}`)
    .slice(0, SNS_LIMITS[platform].hashtagLimit);

  return cleaned.length > 0 ? cleaned : generateDefaultHashtags(platform);
}

/**
 * 기본 해시태그 생성
 */
function generateDefaultHashtags(platform) {
  const defaults = ['#정치', '#민생', '#소통'];
  return defaults.slice(0, SNS_LIMITS[platform].hashtagLimit);
}

/**
 * 길이 제한 적용
 */
function enforceLength(content, platform, platformConfig = null) {
  const maxLength = platformConfig ? platformConfig.maxLength : SNS_LIMITS[platform].maxLength;
  const actualLength = countWithoutSpace(content);

  if (actualLength <= maxLength) return content;

  // 공백 제외 기준으로 자르기
  let trimmed = '';
  let charCount = 0;

  for (let i = 0; i < content.length && charCount < maxLength - 3; i++) {
    trimmed += content.charAt(i);
    if (!/\s/.test(content.charAt(i))) {
      charCount++;
    }
  }

  return trimmed + '...';
}
