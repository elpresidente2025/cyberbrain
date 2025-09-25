/**
 * functions/handlers/naver-login.js
 * ?�이�?로그??처리 (?�원가???�도 ?�책 반영)
 */

'use strict';

const { onCall, onRequest, HttpsError } = require('firebase-functions/v2/https');
const { admin, db } = require('../utils/firebaseAdmin');
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

// 기존 onCall ?�수 ?��?
const naverLogin = onCall({
  region: 'asia-northeast3',
  cors: [
    'https://cyberbrain.kr',
    'https://ai-secretary-6e9c8.web.app',
    'https://ai-secretary-6e9c8.firebaseapp.com'
  ],
  memory: '256MiB',
  timeoutSeconds: 60
}, async (request) => {
  // 기존 onCall 로직?� ?�순???��?
  return { success: false, message: "Use naverLoginHTTP instead" };
});

// ?�이�?로그??처리 (?�원가???�도 ?�책) - onRequest�?변경하??CORS ?�전 ?�어
const naverLoginHTTP = onRequest({
  region: 'asia-northeast3',
  cors: true, // ?�선 모든 origin ?�용?�로 ?�스??  memory: '256MiB',
  timeoutSeconds: 60
}, async (request, response) => {
  let stage = 'init'; // ?�수 최상?�에???�언
  
  // ?�동 CORS ?�더 ?�정
  response.set('Access-Control-Allow-Origin', 'https://cyberbrain.kr');
  response.set('Access-Control-Allow-Methods', 'POST, OPTIONS');
  response.set('Access-Control-Allow-Headers', 'Content-Type');
  
  // OPTIONS ?�청 처리 (?�리?�라?�트)
  if (request.method === 'OPTIONS') {
    return response.status(204).end();
  }
  try {
    console.log('?? naverLogin v2 ?�수 ?�작 (onRequest)');
    console.log('?�� ?�청 ?�보:', {
      method: request.method,
      headers: Object.keys(request.headers),
      bodyExists: !!request.body,
      bodyData: JSON.stringify(request.body),
      envVars: {
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
      console.log('???�이�??�용???�이??직접 ?�달):', {
        id: naverUserInfo.id,
        email: naverUserInfo.email,
        name: naverUserInfo.name || naverUserInfo.nickname
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
        
        const newUserData = {
          // ?�이�?계정 ?�보 (ID�??�용)
          naverUserId: naverUserData.id,
          name: naverUserData.name || naverUserData.nickname || '네이버사용자',
          profileImage: naverUserData.profile_image || null,
          gender: mapGender(naverUserData.gender) || null,
          age: naverUserData.age || null,
          
          // 기본 ?�용???�보 (?�중???�로?�에???�정 가??
          status: '?�역', // 기본�?          position: '', // ?�로?�에???�중???�정
          regionMetro: '', // ?�로?�에???�중???�정
          regionLocal: '', // ?�로?�에???�중???�정
          electoralDistrict: '', // ?�로?�에???�중???�정
          
          // 가???�보
          provider: 'naver',
          isNaverUser: true,
          createdAt: admin.firestore.FieldValue.serverTimestamp(),
          lastLoginAt: admin.firestore.FieldValue.serverTimestamp(),
          profileComplete: false // ?�로???�성 ?�요
        };
        
        // ?�용??문서 ?�??        console.log('?�� Firestore???�용???�이???�??�?..', JSON.stringify(newUserData, null, 2));
        await newUserRef.set(newUserData);
        console.log('???�이�??�용???�동 가???�료:', newUserRef.id);
        
        // 커스?� ?�큰 ?�??Firebase UID�?반환 (?�론?�엔?�에???�명 로그?????�결)
        stage = 'return_user_data_new_user';
        
        // ?�동 가??+ 로그???�공 ?�답 (?�큰 ?�이)
        return response.status(200).json({
          result: {
            success: true,
            registrationRequired: false,
            autoRegistered: true, // ?�동 가?�되?�음???�시
            user: {
              uid: newUserRef.id,
              naverUserId: naverUserData.id,
              displayName: newUserData.name,
              photoURL: newUserData.profileImage,
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
            message: '?�이�?계정?�로 ?�동 가?�되?�습?�다!'
          }
        });
        
      } catch (registrationError) {
        console.error('???�이�??�동 가???�류:', {
          stage,
          error: registrationError.message,
          stack: registrationError.stack,
          naverUserId: naverUserData.id
        });
        throw new Error(`?�동 가???�패 (${stage}): ${registrationError.message}`);
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

    // 기존 ?�용??로그???�공 ?�답 (?�큰 ?�이)
    stage = 'return_existing_user_data';
    
    return response.status(200).json({
      result: {
        success: true,
        registrationRequired: false,
        user: {
          uid: userDoc.id,
          naverUserId: userData.naverUserId,
          displayName: userData.name || userData.displayName,
          photoURL: userData.profileImage || naverUserData.profile_image,
          provider: 'naver',
          profileComplete: userData.profileComplete || false
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
    console.error('??naverLogin 최상???�류:', {
      stage: stage || 'unknown',
      errorMessage: error.message,
      errorStack: error.stack,
      requestBody: JSON.stringify(request.body),
      naverClientIdExists: !!NAVER_CLIENT_ID,
      naverClientSecretExists: !!NAVER_CLIENT_SECRET
    });
    
    return response.status(500).json({
      error: {
        code: 'internal',
        message: 'NAVER_LOGIN_INTERNAL',
        details: { 
          stage: stage || 'unknown',
          message: error.message, 
          stack: (error && error.stack) || null 
        }
      }
    });
  }
});

module.exports = {
  naverLogin, // 기존 onCall ?�수 ?��?
  naverLoginHTTP // ?�로??onRequest ?�수 추�?
};
