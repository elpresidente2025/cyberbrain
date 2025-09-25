/**
 * functions/handlers/naver-disconnect.js
 * 네이버 연결 끊기 콜백 처리 핸들러
 */

'use strict';

const { onRequest, HttpsError } = require('firebase-functions/v2/https');
const { admin, db } = require('../utils/firebaseAdmin');

// 네이버 연결 끊기 콜백 처리
const naverDisconnect = onRequest({
  cors: [
    'https://cyberbrain.kr',
    'https://ai-secretary-6e9c8.web.app',
    'https://ai-secretary-6e9c8.firebaseapp.com'
  ],
  memory: '256MiB',
  timeoutSeconds: 60
}, async (request, response) => {
  console.log('🔗 naverDisconnect 콜백 수신');
  
  try {
    // POST 요청만 허용
    if (request.method !== 'POST') {
      console.log('❌ 잘못된 HTTP 메소드:', request.method);
      return response.status(405).json({ 
        success: false, 
        error: 'METHOD_NOT_ALLOWED',
        message: 'POST 메소드만 허용됩니다.' 
      });
    }

    // 네이버에서 보내는 파라미터 추출
    const { 
      user_id,      // 네이버 사용자 ID
      service_id,   // 서비스 ID
      reason        // 연결 해제 사유 ('user_delete' | 'user_unlink')
    } = request.body;

    console.log('📋 네이버 연결 끊기 파라미터:', {
      user_id,
      service_id,
      reason,
      timestamp: new Date().toISOString()
    });

    // 필수 파라미터 검증
    if (!user_id) {
      console.log('❌ user_id 누락');
      return response.status(400).json({
        success: false,
        error: 'MISSING_USER_ID',
        message: 'user_id가 필요합니다.'
      });
    }

    // Firestore에서 해당 네이버 사용자 찾기
    const userQuery = await db.collection('users')
      .where('naverUserId', '==', user_id)
      .limit(1)
      .get();

    if (userQuery.empty) {
      console.log('⚠️ 해당 네이버 사용자를 찾을 수 없음:', user_id);
      // 네이버에는 성공 응답 (이미 삭제된 사용자일 수 있음)
      return response.status(200).json({
        success: true,
        message: '사용자가 이미 삭제되었거나 존재하지 않습니다.'
      });
    }

    const userDoc = userQuery.docs[0];
    const userData = userDoc.data();
    const userId = userDoc.id;

    console.log('👤 연결 해제 대상 사용자:', userData.name || userData.email);

    // 연결 해제 사유별 처리
    if (reason === 'user_delete') {
      // 네이버 회원 탈퇴 - 사용자 계정 완전 삭제
      console.log('🗑️ 네이버 회원 탈퇴로 인한 계정 삭제 처리');
      
      // Firebase Auth 사용자 삭제
      try {
        await admin.auth().deleteUser(userId);
        console.log('✅ Firebase Auth 사용자 삭제 완료');
      } catch (authError) {
        console.log('⚠️ Firebase Auth 사용자 삭제 실패 (이미 삭제됨):', authError.message);
      }
      
      // Firestore 사용자 문서 삭제
      await userDoc.ref.delete();
      console.log('✅ Firestore 사용자 문서 삭제 완료');
      
      // 사용자 관련 데이터 삭제 (게시물, 프로필 등)
      await deleteUserRelatedData(userId);
      
    } else if (reason === 'user_unlink') {
      // 사용자가 직접 연결 해제 - 네이버 연결 정보만 삭제
      console.log('🔗 사용자 연결 해제 처리 (계정 유지)');
      
      // 네이버 연결 정보 제거
      await userDoc.ref.update({
        naverUserId: admin.firestore.FieldValue.delete(),
        naverConnected: false,
        naverDisconnectedAt: admin.firestore.FieldValue.serverTimestamp(),
        updatedAt: admin.firestore.FieldValue.serverTimestamp()
      });
      
      console.log('✅ 네이버 연결 정보 제거 완료');
    }

    // 연결 해제 로그 기록
    await db.collection('admin_logs').add({
      type: 'naver_disconnect',
      userId: userId,
      userEmail: userData.email,
      userName: userData.name,
      naverUserId: user_id,
      reason: reason,
      timestamp: admin.firestore.FieldValue.serverTimestamp(),
      details: {
        service_id,
        user_agent: request.get('User-Agent'),
        ip: request.ip
      }
    });

    console.log('✅ 네이버 연결 끊기 처리 완료');

    // 네이버에 성공 응답
    return response.status(200).json({
      success: true,
      message: '연결 해제 처리가 완료되었습니다.',
      processed_at: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ naverDisconnect 처리 중 오류:', error);
    
    // 오류 로그 기록
    try {
      await db.collection('error_logs').add({
        type: 'naver_disconnect_error',
        error: error.message,
        stack: error.stack,
        requestBody: request.body,
        timestamp: admin.firestore.FieldValue.serverTimestamp()
      });
    } catch (logError) {
      console.error('로그 기록 실패:', logError);
    }
    
    // 네이버에는 항상 200 응답 (재시도 방지)
    return response.status(200).json({
      success: false,
      error: 'INTERNAL_ERROR',
      message: '서버 처리 중 오류가 발생했습니다.'
    });
  }
});

/**
 * 사용자 관련 데이터 삭제 함수
 */
async function deleteUserRelatedData(userId) {
  console.log('🧹 사용자 관련 데이터 삭제 시작:', userId);
  
  try {
    const batch = db.batch();
    
    // 사용자 게시물 삭제
    const postsQuery = await db.collection('posts')
      .where('userId', '==', userId)
      .get();
    
    postsQuery.forEach(doc => {
      batch.delete(doc.ref);
    });
    
    // 사용자 프로필 삭제
    const profileQuery = await db.collection('user_profiles')
      .where('userId', '==', userId)
      .get();
    
    profileQuery.forEach(doc => {
      batch.delete(doc.ref);
    });
    
    // 사용자 바이오 삭제
    const bioQuery = await db.collection('user_bios')
      .where('userId', '==', userId)
      .get();
    
    bioQuery.forEach(doc => {
      batch.delete(doc.ref);
    });
    
    // 사용자 결제 기록 (민감정보 제거하고 익명화)
    const paymentsQuery = await db.collection('payments')
      .where('userId', '==', userId)
      .get();
    
    paymentsQuery.forEach(doc => {
      batch.update(doc.ref, {
        userId: 'deleted_user',
        userEmail: 'deleted@deleted.com',
        userName: '탈퇴한 사용자',
        deletedAt: admin.firestore.FieldValue.serverTimestamp()
      });
    });
    
    await batch.commit();
    console.log('✅ 사용자 관련 데이터 삭제 완료');
    
  } catch (error) {
    console.error('❌ 사용자 관련 데이터 삭제 실패:', error);
    throw error;
  }
}

module.exports = {
  naverDisconnect
};