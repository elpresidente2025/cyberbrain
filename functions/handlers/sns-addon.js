// functions/handlers/sns-addon.js
const { HttpsError } = require('firebase-functions/v2/https');
const { wrap } = require('../common/wrap');
const { httpWrap } = require('../common/http-wrap');
const { ok, error } = require('../common/response');
const { auth } = require('../common/auth');
const { admin, db } = require('../utils/firebaseAdmin');
const { callGenerativeModel } = require('../services/gemini');
const { buildSNSPrompt, SNS_LIMITS } = require('../prompts/builders/sns-conversion');

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

// SNS 플랫폼별 제한사항은 prompts/builders/sns-conversion.js에서 import

/**
 * 사용자 프로필에 따른 X(트위터) 글자수 제한 반환
 * @param {Object} userProfile - 사용자 프로필 정보
 * @param {number} originalLength - 원본 글자수 (공백 제외)
 * @returns {Object} X 플랫폼 제한 정보
 */
function getXLimits(userProfile, originalLength = 0) {
  const isPremium = userProfile.twitterPremium === '구독';
  const premiumLimit = isPremium ? Math.min(originalLength, 25000) : 230; // 원본 글자수를 넘지 않음
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

  const { postId, modelName } = req.data || {};

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
    
    if (!isAdmin) {
      // SNS 접근 권한 확인 (오피니언 리더, 애드온 구매, 게이미피케이션)
      const hasAddonAccess = userPlan === '오피니언 리더' || userData.snsAddon?.isActive || userData.gamification?.snsUnlocked;
      
      if (!hasAddonAccess) {
        throw new HttpsError('permission-denied', 'SNS 변환 기능을 사용하려면 오피니언 리더 플랜을 이용하거나 애드온을 구매해주세요.');
      }

      // 사용량 제한 확인
      const getSNSMonthlyLimit = (plan) => {
        switch (plan) {
          case '오피니언 리더':
            return 60; // 기본 플랜 원고 생성량과 동일
          case '리전 인플루언서':
            return 20; // 기본 플랜 원고 생성량과 동일  
          case '로컬 블로거':
            return 8; // 기본 플랜 원고 생성량과 동일
          default:
            return 30; // SNS 애드온 기본값
        }
      };

      const monthlyLimit = getSNSMonthlyLimit(userPlan);
      const now = new Date();
      const currentMonthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
      const monthlyUsage = userData.snsAddon?.monthlyUsage || {};
      const currentMonthUsage = monthlyUsage[currentMonthKey] || 0;

      if (currentMonthUsage >= monthlyLimit) {
        throw new HttpsError('resource-exhausted', `이번 달 SNS 변환 한도(${monthlyLimit}회)를 모두 사용했습니다.`);
      }
    }

    // 2. 원고 조회
    const postDoc = await db.collection('posts').doc(postIdStr).get();
    if (!postDoc.exists) {
      throw new HttpsError('not-found', '원고를 찾을 수 없습니다.');
    }

    const postData = postDoc.data();
    
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
    const platforms = Object.keys(SNS_LIMITS);
    const results = {};
    
    // 사용할 모델 결정 (기본값: gemini-2.0-flash-exp)
    const selectedModel = modelName || 'gemini-2.0-flash-exp';
    console.log('🔄 모든 SNS 플랫폼 변환 시작:', { postId: postIdStr, userRole, userInfo, selectedModel });

    // 각 플랫폼별로 병렬 처리로 변환 (재시도 로직 포함)
    console.log(`🚀 ${platforms.length}개 플랫폼 병렬 변환 시작`);
    
    // 원본 글자수 계산 (공백 제외)
    const originalLength = countWithoutSpace(originalContent);
    
    const platformPromises = platforms.map(async (platform) => {
      // X(트위터)는 사용자 프리미엄 구독 여부에 따라 동적 제한 적용
      const platformConfig = platform === 'x' ? getXLimits(userData, originalLength) : SNS_LIMITS[platform];
      const targetLength = Math.floor(platformConfig.maxLength * 0.8);
      
      console.log(`🔄 ${platform} 변환 시작 - 모델: ${selectedModel}`);
      
      // 최대 2번 시도 (병렬 처리에서는 속도 우선)
      let convertedResult = null;
      const maxAttempts = 2; // 병렬 처리에서는 2번으로 줄여서 전체 시간 단축
      
      for (let attempt = 1; attempt <= maxAttempts && !convertedResult; attempt++) {
        console.log(`🔄 ${platform} 시도 ${attempt}/${maxAttempts}...`);
        
        try {
          const snsPrompt = buildSNSPrompt(originalContent, platform, platformConfig, postKeywords, userInfo);
          
          // Gemini API로 변환 실행 (타임아웃 추가)
          const convertedText = await Promise.race([
            callGenerativeModel(snsPrompt, 1, selectedModel),
            new Promise((_, reject) => 
              setTimeout(() => reject(new Error('AI 호출 타임아웃 (30초)')), 30000)
            )
          ]);
          
          console.log(`📝 ${platform} 원본 응답 (시도 ${attempt}):`, {
            length: convertedText?.length || 0,
            preview: convertedText?.substring(0, 100) + '...',
            hasJSON: /\{[\s\S]*\}/.test(convertedText || '')
          });

          if (!convertedText || convertedText.trim().length === 0) {
            console.warn(`⚠️ ${platform} 시도 ${attempt}: 빈 응답`);
            continue;
          }

          // 결과 파싱
          const parsedResult = parseConvertedContent(convertedText, platform, platformConfig);
          
          // 간소화된 검증 (속도 우선)
          const hasContent = parsedResult.content && parsedResult.content.trim().length > 20;
          const hasHashtags = Array.isArray(parsedResult.hashtags) && parsedResult.hashtags.length > 0;
          
          if (hasContent) {
            // 기본 검증만 통과하면 사용
            convertedResult = {
              content: parsedResult.content.trim(),
              hashtags: hasHashtags ? parsedResult.hashtags : generateDefaultHashtags(platform)
            };
            
            console.log(`✅ ${platform} 시도 ${attempt} 성공:`, {
              contentLength: countWithoutSpace(convertedResult.content),
              hashtagCount: convertedResult.hashtags.length
            });
          } else {
            console.warn(`⚠️ ${platform} 시도 ${attempt}: 콘텐츠가 너무 짧음`);
            if (attempt === maxAttempts) {
              // 최종 시도에서도 실패하면 기본 콘텐츠 생성
              convertedResult = {
                content: `${userInfo.name}입니다. ${originalContent.substring(0, Math.min(200, platformConfig.maxLength))}`,
                hashtags: generateDefaultHashtags(platform)
              };
            }
          }
          
        } catch (error) {
          console.error(`❌ ${platform} 시도 ${attempt} 오류:`, error.message);
          if (attempt === maxAttempts) {
            // 최종적으로 실패하면 기본 콘텐츠 반환
            convertedResult = {
              content: `${userInfo.name}입니다. 원고 내용을 공유드립니다.`,
              hashtags: generateDefaultHashtags(platform)
            };
          }
        }
      }

      console.log(`✅ ${platform} 변환 완료`);
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

    const userData = userDoc.data();
    const isAdmin = userData.role === 'admin' || userData.isAdmin === true;
    const userPlan = userData.plan || userData.subscription;
    
    // 플랜별 SNS 월 제한량 결정
    const getSNSMonthlyLimit = (plan) => {
      switch (plan) {
        case '오피니언 리더':
          return 60; // 기본 플랜 원고 생성량과 동일
        case '리전 인플루언서':
          return 20; // 기본 플랜 원고 생성량과 동일  
        case '로컬 블로거':
          return 8; // 기본 플랜 원고 생성량과 동일
        default:
          return 30; // SNS 애드온 기본값 (애드온 구매 시)
      }
    };

    // SNS 접근 권한 확인
    const hasAddonAccess = isAdmin || userData.snsAddon?.isActive || userData.gamification?.snsUnlocked || userPlan === '오피니언 리더';

    // 관리자는 무제한 사용
    if (isAdmin) {
      return ok({
        isActive: true,
        monthlyLimit: 999999, // 관리자 무제한
        currentMonthUsage: 0,
        remaining: 999999,
        accessMethod: 'admin'
      });
    }

    const monthlyLimit = getSNSMonthlyLimit(userPlan);

    // 현재 월 사용량 계산
    const now = new Date();
    const currentMonthKey = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
    const monthlyUsage = userData.snsAddon?.monthlyUsage || {};
    const currentMonthUsage = monthlyUsage[currentMonthKey] || 0;

    return ok({
      isActive: hasAddonAccess,
      monthlyLimit: monthlyLimit,
      currentMonthUsage: currentMonthUsage,
      remaining: Math.max(0, monthlyLimit - currentMonthUsage),
      accessMethod: userPlan === '오피니언 리더' ? 'plan_included' :
                   userData.snsAddon?.isActive ? 'paid' :
                   userData.gamification?.snsUnlocked ? 'gamification' : 'none'
    });

  } catch (error) {
    console.error('❌ SNS 사용량 조회 실패:', error);
    throw new HttpsError('internal', 'SNS 사용량 조회 중 오류가 발생했습니다.');
  }
});

/**
 * SNS 애드온 구매/활성화
 */
exports.purchaseSNSAddon = wrap(async (req) => {
  const { uid } = await auth(req);

  // auth 함수에서 이미 인증 검증이 완료됨

  try {
    // 사용자 정보 조회하여 플랜 확인
    const userDoc = await db.collection('users').doc(uid).get();
    const userData = userDoc.data();
    
    if (!userData) {
      throw new HttpsError('not-found', '사용자 정보를 찾을 수 없습니다.');
    }
    
    const userPlan = userData.plan || userData.subscription;
    
    // 오피니언 리더 플랜은 SNS 원고가 이미 포함되어 있으므로 구매 불가
    if (userPlan === '오피니언 리더') {
      throw new HttpsError('failed-precondition', '오피니언 리더 플랜은 이미 SNS 원고 무료 생성이 포함되어 있습니다. 추가 구매가 불필요합니다.');
    }
    const now = new Date();
    const nextMonth = new Date(now.getFullYear(), now.getMonth() + 1, now.getDate());

    await db.collection('users').doc(uid).update({
      'snsAddon.isActive': true,
      'snsAddon.purchaseDate': admin.firestore.FieldValue.serverTimestamp(),
      'snsAddon.expiryDate': admin.firestore.Timestamp.fromDate(nextMonth),
      'snsAddon.monthlyUsage': {},
      'snsAddon.totalUsed': 0
    });

    console.log('✅ SNS 애드온 구매 완료:', uid);

    return ok({
      message: 'SNS 애드온이 성공적으로 활성화되었습니다.',
      expiryDate: nextMonth.toISOString(),
      price: 22000
    });

  } catch (error) {
    console.error('❌ SNS 애드온 구매 실패:', error);
    throw new HttpsError('internal', 'SNS 애드온 구매 중 오류가 발생했습니다.');
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
 * 변환된 내용 파싱 (완전히 새로 작성)
 */
function parseConvertedContent(rawContent, platform, platformConfig = null) {
  try {
    console.log(`🔍 ${platform} 파싱 시작:`, {
      rawContentLength: rawContent?.length || 0,
      rawContentPreview: rawContent?.substring(0, 200) + '...'
    });

    let content = '';
    let hashtags = [];

    // 1차 시도: JSON 형식 파싱
    const jsonResult = tryParseJSON(rawContent, platform);
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

    console.log(`✅ ${platform} 파싱 완료:`, {
      contentLength: countWithoutSpace(content),
      hashtagCount: hashtags.length,
      contentPreview: content.substring(0, 100) + '...'
    });

    return { content, hashtags };

  } catch (error) {
    console.error(`❌ ${platform} 파싱 실패:`, error);
    return {
      content: rawContent.substring(0, 200) || '',
      hashtags: generateDefaultHashtags(platform)
    };
  }
}

/**
 * JSON 파싱 시도
 */
function tryParseJSON(rawContent, platform) {
  try {
    const jsonMatch = rawContent.match(/\{[\s\S]*\}/);
    if (!jsonMatch) return { success: false };

    const parsed = JSON.parse(jsonMatch[0]);
    console.log(`🔍 ${platform} JSON 구조:`, Object.keys(parsed));

    let content = '';
    let hashtags = [];

    // 표준 형식: {"content": "...", "hashtags": [...]}
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
      console.log(`✅ ${platform} JSON 파싱 성공: ${content.length}자`);
      return { success: true, content, hashtags };
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