'use strict';

const { HttpsError } = require('firebase-functions/v2/https');
const { httpWrap } = require('../common/http-wrap');
const { admin, db } = require('../utils/firebaseAdmin');
const { callGenerativeModel } = require('../services/gemini');

/**
 * 원고 생성 (HTTP 함수)
 */
exports.generatePosts = httpWrap(async (req) => {
  console.log('🔥 generatePosts HTTP 시작');

  let uid;

  // 데이터 추출 - Firebase SDK와 HTTP 요청 모두 처리
  let requestData = req.data || req.rawRequest?.body || {};

  // 중첩된 data 구조 처리
  if (requestData.data && typeof requestData.data === 'object') {
    requestData = requestData.data;
  }

  // 사용자 인증 데이터 확인 (모든 사용자는 네이버 로그인)
  if (requestData.__naverAuth && requestData.__naverAuth.uid && requestData.__naverAuth.provider === 'naver') {
    console.log('📱 사용자 인증 처리:', requestData.__naverAuth.uid);
    uid = requestData.__naverAuth.uid;
    // 인증 정보 제거 (처리 완료)
    delete requestData.__naverAuth;
  } else {
    console.error('❌ 유효하지 않은 인증 데이터:', requestData);
    throw new HttpsError('unauthenticated', '인증이 필요합니다.');
  }

  const { topic, prompt, tone, keywords, category, length } = requestData;
  // topic 또는 prompt 중 하나라도 있으면 사용 (호환성)
  const actualTopic = topic || prompt;

  console.log('📝 입력 데이터:', { uid, topic, prompt, actualTopic, tone, keywords, category, length });

  if (!uid) {
    console.log('❌ 인증되지 않은 요청');
    throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
  }

  if (!actualTopic) {
    throw new HttpsError('invalid-argument', '주제 또는 프롬프트가 필요합니다.');
  }

  try {
    // 사용자 정보 조회
    const userDoc = await db.collection('users').doc(uid).get();
    if (!userDoc.exists) {
      throw new HttpsError('not-found', '사용자를 찾을 수 없습니다.');
    }

    const userData = userDoc.data();
    const userProfile = userData.profile || {};

    // 기본 원고 생성 프롬프트
    const generationPrompt = `정치인을 위한 원고를 작성해주세요.

주제: ${actualTopic}
톤: ${tone || '전문적'}
키워드: ${keywords || ''}
카테고리: ${category || '일반'}
길이: ${length || '중간'}

정치인 정보:
- 이름: ${userProfile.name || '정치인'}
- 직책: ${userProfile.position || '의원'}
- 지역: ${userProfile.region || '지역'}

요구사항:
1. 정치인다운 품격 있는 문체로 작성
2. 주제에 맞는 구체적이고 실용적인 내용
3. 지역 주민들과의 소통을 중시하는 내용
4. 완성도 높은 원고로 작성

**중요: JSON 형식이 아닌 완성된 원고 텍스트만 반환해주세요.**

원고를 작성해주세요.`;

    // AI 모델 호출
    const rawResponse = await callGenerativeModel(generationPrompt, 1, 'gemini-2.5-flash-lite');

    if (!rawResponse) {
      throw new HttpsError('internal', '원고 생성에 실패했습니다.');
    }

    console.log('🤖 AI 원본 응답:', rawResponse.substring(0, 200) + '...');

    // AI 응답이 JSON 형태인 경우 파싱
    let generatedContent = rawResponse;
    try {
      // JSON 형태 응답인지 확인 (객체 또는 배열)
      if (rawResponse.trim().startsWith('{') || rawResponse.trim().startsWith('[')) {
        const parsed = JSON.parse(rawResponse);

        // 다양한 JSON 구조에서 content 추출
        if (parsed.activityReport?.content) {
          generatedContent = parsed.activityReport.content;
        } else if (parsed.content) {
          generatedContent = parsed.content;
        } else if (parsed.text) {
          generatedContent = parsed.text;
        } else if (parsed.response) {
          generatedContent = parsed.response;
        } else if (Array.isArray(parsed)) {
          // 배열인 경우 첫 번째 요소 사용
          generatedContent = parsed[0] || rawResponse;
        } else {
          // JSON이지만 알려진 필드가 없는 경우 원본 사용
          console.warn('⚠️ JSON 응답이지만 알려진 content 필드가 없음');
          generatedContent = rawResponse;
        }

        // 추출된 content가 배열인 경우 처리
        if (Array.isArray(generatedContent)) {
          if (generatedContent.length === 1 && typeof generatedContent[0] === 'string') {
            generatedContent = generatedContent[0];
          } else {
            generatedContent = generatedContent.join('\n\n');
          }
        }
      }
    } catch (parseError) {
      console.log('📝 JSON 파싱 실패, 원본 텍스트 사용:', parseError.message);
      // JSON 파싱 실패시 원본 사용
      generatedContent = rawResponse;
    }

    console.log('✅ 최종 추출된 콘텐츠:',
      typeof generatedContent === 'string'
        ? generatedContent.substring(0, 100) + '...'
        : JSON.stringify(generatedContent).substring(0, 100) + '...'
    );

    if (!generatedContent ||
        (typeof generatedContent === 'string' && generatedContent.trim().length < 10) ||
        (typeof generatedContent !== 'string' && !generatedContent)) {
      throw new HttpsError('internal', '유효한 원고 콘텐츠를 생성하지 못했습니다.');
    }

    // 문자열이 아닌 경우 JSON 문자열로 변환
    if (typeof generatedContent !== 'string') {
      generatedContent = JSON.stringify(generatedContent, null, 2);
    }

    // DB에 저장하지 않고 생성된 콘텐츠만 반환
    console.log('✅ 원고 생성 완료 (임시)');

    return {
      success: true,
      content: generatedContent,
      topic: actualTopic,
      tone: tone || '전문적',
      keywords: keywords || '',
      category: category || '일반',
      length: length || '중간',
      message: '원고가 성공적으로 생성되었습니다.'
    };

  } catch (error) {
    console.error('❌ 원고 생성 실패:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '원고 생성 중 오류가 발생했습니다.');
  }
});