/**
 * functions/handlers/naver-login.js
 * ?�이�?로그??처리 (?�원가???�도 ?�책 반영)
 */

'use strict';

const { onCall, onRequest, HttpsError } = require('firebase-functions/v2/https');
const { admin, db } = require('../utils/firebaseAdmin');
const { ALLOWED_ORIGINS } = require('../common/config');
const fetch = require('node-fetch');

// ?�이�?OAuth ?�정 (?�경변???�수)
const NAVER_CLIENT_ID = process.env.NAVER_CLIENT_ID;
const NAVER_CLIENT_SECRET = process.env.NAVER_CLIENT_SECRET;

function mapGender(g) {
  if (!g) return '';
  const s = String(g).trim().toUpperCase();
  if (s === 'M' || s === 'MALE' || s === '남' || s === '남자') return '남성';
  if (s === 'F' || s === 'FEMALE' || s === '여' || s === '여자') return '여성';
  return String(g).trim();
}
// ?�이�??�용???�보 조회
async function getNaverUserInfo(accessToken) {
  try {
    console.log('?�� ?�이�?API ?�출 ?�작 - ?�큰 길이:', accessToken?.length || 0);
    
    const response = await fetch('https://openapi.naver.com/v1/nid/me', {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${accessToken}`
      }
    });

    console.log('?�� ?�이�?API ?�답 ?�태:', response.status, response.statusText);

    if (!response.ok) {
      const errorText = await response.text();
      console.error('???�이�?API ?�출 ?�패:', {
        status: response.status,
        statusText: response.statusText,
        errorText: errorText
      });
      throw new Error(`?�이�?API ?�출 ?�패: ${response.status} - ${errorText}`);
    }

    const data = await response.json();
    console.log('?�� ?�이�?API ?�답 ?�이??', {
      resultcode: data.resultcode,
      message: data.message,
      hasResponse: !!data.response,
      responseKeys: data.response ? Object.keys(data.response) : []
    });

    if (data.resultcode !== '00') {
      throw new Error(`?�이�??�용???�보 조회 ?�패: ${data.message}`);
    }

    return data.response;
  } catch (error) {
    console.error('???�이�??�용???�보 조회 ?�류:', {
      message: error.message,
      stack: error.stack,
      accessTokenProvided: !!accessToken
    });
    throw error;
  }
}

// 기존 onCall 함수 (deprecated)
const naverLogin = onCall({
  region: 'asia-northeast3',
  cors: ALLOWED_ORIGINS,
  memory: '256MiB',
  timeoutSeconds: 60
}, async (request) => {
  // 기존 onCall 로직은 더 이상 사용되지 않음
  return { success: false, message: "Use naverLoginHTTP instead" };
});

// ?�이�?로그??처리 (?�원가???�도 ?�책) - onRequest�?변경하??CORS ?�전 ?�어
const naverLoginHTTP = onRequest({
  region: 'asia-northeast3',
  cors: true,
  memory: '256MiB',
  timeoutSeconds: 60
}, async (request, response) => {
  // CORS 헤더 명시적 설정
  response.set('Access-Control-Allow-Origin', request.headers.origin || '*');
  response.set('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  response.set('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  response.set('Access-Control-Max-Age', '3600');

  // OPTIONS preflight 요청 처리
  if (request.method === 'OPTIONS') {
    return response.status(204).send('');
  }

  let stage = 'init';
  try {
    console.log('✅ naverLogin v2 시작 (onRequest)');
    console.log('📋 요청 정보:', {
      method: request.method,
      hasBody: !!request.body,
      envVarsConfigured: {
        naverClientId: !!NAVER_CLIENT_ID,
        naverClientSecret: !!NAVER_CLIENT_SECRET
      }
    });
    stage = 'parsing_request';

    // POST ?�청 ?�이???�싱
    const requestData = request.body?.data || request.body || {};
    const { accessToken, naverUserInfo, code, state } = requestData;
    let naverUserData;

    if (naverUserInfo) {
      stage = 'use_client_userinfo';
      console.log('ℹ️ 네이버 사용자 데이터 (클라이언트 제공):', {
        hasId: !!naverUserInfo.id,
        hasEmail: !!naverUserInfo.email,
        hasName: !!(naverUserInfo.name || naverUserInfo.nickname)
      });
      naverUserData = naverUserInfo;
    } else if (accessToken) {
      stage = 'fetch_userinfo_with_token';
      console.log('???�세???�큰?�로 ?�용???�보 조회');
      naverUserData = await getNaverUserInfo(accessToken);
    } else if (code) {
      // Authorization Code ?�로??지?? code -> access_token 교환
      stage = 'exchange_code_for_token';
      console.log('??Authorization Code ?�로?? ?�큰 교환 ?�도');
      try {
        if (!NAVER_CLIENT_ID || !NAVER_CLIENT_SECRET) {
          throw new Error('NAVER 환경변수(NAVER_CLIENT_ID/SECRET) 미설정');
        }
        const params = new URLSearchParams();
        params.append('grant_type', 'authorization_code');
        params.append('client_id', NAVER_CLIENT_ID);
        params.append('client_secret', NAVER_CLIENT_SECRET);
        params.append('code', code);
        if (state) params.append('state', state);

        const tokenResp = await fetch('https://nid.naver.com/oauth2.0/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: params.toString()
        });

        if (!tokenResp.ok) {
          const txt = await tokenResp.text();
          throw new Error(`?�큰 교환 ?�패: ${tokenResp.status} ${txt}`);
        }

        const tokenJson = await tokenResp.json();
        if (!tokenJson.access_token) {
          throw new Error('?�큰 교환 ?�답??access_token ?�음');
        }

        console.log('???�큰 교환 ?�공, ?�용???�보 조회');
        stage = 'fetch_userinfo_after_exchange';
        naverUserData = await getNaverUserInfo(tokenJson.access_token);
      } catch (ex) {
        console.error('?�이�??�큰 교환 ?�류:', ex);
        throw new HttpsError('unauthenticated', '?�이�??�큰 교환 ?�패', { stage, message: ex.message });
      }
    } else {
      throw new HttpsError('invalid-argument', '?�이�??�용???�보 ?�는 ?�세???�큰???�요?�니??');
    }

    // ?�이�?ID ?�인 (?�수)
    if (!naverUserData.id) {
      return response.status(400).json({
        error: {
          code: 'invalid-argument',
          message: '?�이�??�용??ID�?가?�올 ???�습?�다.',
          details: { stage: 'validate_naver_id' }
        }
      });
    }

    // 기존 가???��? ?�인 (?�이�?ID�?조회)
    stage = 'query_user';
    const userQuery = await db.collection('users')
      .where('naverUserId', '==', naverUserData.id)
      .limit(1)
      .get();

    // 미�??? ?�동 ?�원가??진행
    if (userQuery.empty) {
      stage = 'auto_registration';
      console.log('?�� ?�이�??�용???�동 가???�작:', naverUserData.id);
      
      try {
        // ???�용??문서 ?�성
        console.log('?�� ???�용??문서 ?�성 ?�작...');
        const newUserRef = db.collection('users').doc();
        console.log('?�� ?�성???�용??ID:', newUserRef.id);
        
        // 월말 계산 (무료 체험 만료일)
        const now = new Date();
        const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59);

        const newUserData = {
          // 네이버 계정 정보
          naverUserId: naverUserData.id,
          name: naverUserData.name || naverUserData.nickname || '네이버사용자',
          gender: mapGender(naverUserData.gender) || null,
          age: naverUserData.age || null,

          // 기본 사용자 정보 (추후 프로필에서 설정)
          status: '현역',
          position: '',
          regionMetro: '',
          regionLocal: '',
          electoralDistrict: '',

          // 가입 정보
          provider: 'naver',
          isNaverUser: true,
          createdAt: admin.firestore.FieldValue.serverTimestamp(),
          lastLoginAt: admin.firestore.FieldValue.serverTimestamp(),
          profileComplete: false,

          // 우선권 시스템 필드
          districtPriority: null,
          isPrimaryInDistrict: false,
          districtStatus: 'trial',

          // 구독/무료 체험 관련 필드
          subscriptionStatus: 'trial',
          paidAt: null,
          trialPostsRemaining: 8,
          generationsRemaining: 8,
          trialExpiresAt: admin.firestore.Timestamp.fromDate(endOfMonth),
          monthlyLimit: 8,
          monthlyUsage: {},
          activeGenerationSession: null
        };
        
        // 사용자 문서 저장
        console.log('💾 Firestore에 사용자 데이터 저장 중...');
        await newUserRef.set(newUserData);
        console.log('✅ 네이버 사용자 자동 가입 완료:', newUserRef.id);

        // Firebase Custom Token 생성 (보안 강화)
        stage = 'create_custom_token_new_user';
        console.log('🔐 Firebase Custom Token 생성 중...');
        const customToken = await admin.auth().createCustomToken(newUserRef.id, {
          provider: 'naver',
          naverUserId: naverUserData.id
        });
        console.log('✅ Custom Token 생성 완료');

        // 자동 가입 + 로그인 성공 응답 (Custom Token 포함)
        return response.status(200).json({
          result: {
            success: true,
            registrationRequired: false,
            autoRegistered: true, // 자동 가입되었음을 표시
            customToken, // Firebase 인증용 Custom Token
            user: {
              uid: newUserRef.id,
              naverUserId: naverUserData.id,
              displayName: newUserData.name,
              photoURL: naverUserData.profile_image,
              provider: 'naver',
              profileComplete: false
            },
            naver: {
              id: naverUserData.id,
              name: naverUserData.name || naverUserData.nickname || null,
              gender: naverUserData.gender || null,
              age: naverUserData.age || null,
              profile_image: naverUserData.profile_image || null
            },
            message: '네이버 계정으로 자동 가입되었습니다!'
          }
        });
        
      } catch (registrationError) {
        console.error('❌ 네이버 자동 가입 오류:', {
          stage,
          error: registrationError.message
        });
        throw new Error(`자동 가입 실패 (${stage}): ${registrationError.message}`);
      }
    }

    // 기�??? 로그??처리
    stage = 'prepare_login_existing_user';
    const userDoc = userQuery.docs[0];
    const userData = userDoc.data();

    stage = 'update_last_login';
    const updateExisting = {
      lastLoginAt: admin.firestore.FieldValue.serverTimestamp(),
      naverUserId: naverUserData.id
    };
    if (!userData.gender && naverUserData.gender) {
      updateExisting.gender = mapGender(naverUserData.gender);
    }
    await userDoc.ref.update(updateExisting);

    // Firebase Custom Token 생성 (보안 강화)
    stage = 'create_custom_token_existing_user';
    console.log('🔐 Firebase Custom Token 생성 중...');
    const customToken = await admin.auth().createCustomToken(userDoc.id, {
      provider: 'naver',
      naverUserId: naverUserData.id
    });
    console.log('✅ Custom Token 생성 완료');

    // 기존 사용자 로그인 성공 응답 (Custom Token 포함)
    stage = 'return_existing_user_data';

    // Timestamp를 ISO 문자열로 변환하는 헬퍼 함수
    const convertTimestamp = (timestamp) => {
      if (!timestamp) return null;
      if (timestamp.toDate) return timestamp.toDate().toISOString();
      if (timestamp instanceof Date) return timestamp.toISOString();
      return timestamp;
    };

    return response.status(200).json({
      result: {
        success: true,
        registrationRequired: false,
        customToken, // Firebase 인증용 Custom Token
        user: {
          uid: userDoc.id,
          naverUserId: userData.naverUserId,
          displayName: userData.name || userData.displayName,
          photoURL: naverUserData.profile_image,
          provider: 'naver',
          profileComplete: userData.profileComplete || false,
          // 전체 사용자 정보 포함
          role: userData.role || null,
          isAdmin: userData.isAdmin || false,
          status: userData.status || null,
          position: userData.position || null,
          regionMetro: userData.regionMetro || null,
          regionLocal: userData.regionLocal || null,
          electoralDistrict: userData.electoralDistrict || null,
          bio: userData.bio || null,
          userPlan: userData.userPlan || null,
          userSubscription: userData.userSubscription || null,
          finalPlan: userData.finalPlan || null,
          verificationStatus: userData.verificationStatus || null,
          lastVerification: userData.lastVerification ? {
            quarter: userData.lastVerification.quarter,
            date: convertTimestamp(userData.lastVerification.date)
          } : null,
          createdAt: convertTimestamp(userData.createdAt),
          lastLoginAt: convertTimestamp(userData.lastLoginAt)
        },
        naver: {
          id: naverUserData.id,
          name: naverUserData.name || naverUserData.nickname || null,
          gender: naverUserData.gender || null,
          age: naverUserData.age || null,
          profile_image: naverUserData.profile_image || null
        }
      }
    });

  } catch (error) {
    // 서버 로그에만 상세 정보 기록
    console.error('❌ naverLogin 최상위 오류:', {
      stage: stage || 'unknown',
      errorMessage: error.message,
      errorStack: error.stack,
      envVarsConfigured: {
        naverClientId: !!NAVER_CLIENT_ID,
        naverClientSecret: !!NAVER_CLIENT_SECRET
      }
    });

    // 클라이언트에는 일반적인 오류 메시지만 반환 (보안)
    return response.status(500).json({
      error: {
        code: 'internal',
        message: '네이버 로그인 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.'
      }
    });
  }
});

module.exports = {
  naverLogin, // 기존 onCall ?�수 ?��?
  naverLoginHTTP // ?�로??onRequest ?�수 추�?
};
