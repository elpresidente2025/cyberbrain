const admin = require('firebase-admin');
const { onCall, HttpsError } = require('firebase-functions/v2/https');
const wrap = require('../common/wrap').wrap;
const { auth } = require('../common/auth');

// 모든 사용자 조회 (관리자 전용)
const getAllUsers = wrap(async (request) => {
  const { uid, token } = await auth(request);

  try {
    const db = admin.firestore();
    
    // 요청자가 관리자인지 확인
    const requesterDoc = await db.collection('users').doc(uid).get();
    const userData = requesterDoc.data() || {};
    const isAdmin = userData.role === 'admin' || userData.isAdmin === true; // 이전 버전과 호환성
    
    if (!requesterDoc.exists || !isAdmin) {
      throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
    }

    // 모든 사용자 조회
    const usersSnapshot = await db.collection('users').orderBy('createdAt', 'desc').get();
    const users = [];
    
    usersSnapshot.forEach(doc => {
      const data = doc.data();
      
      // Timestamp 필드들을 ISO 문자열로 변환
      const convertedData = { ...data };
      if (data.createdAt && data.createdAt.toDate) {
        convertedData.createdAt = data.createdAt.toDate().toISOString();
      }
      if (data.updatedAt && data.updatedAt.toDate) {
        convertedData.updatedAt = data.updatedAt.toDate().toISOString();
      }
      if (data.deactivatedAt && data.deactivatedAt.toDate) {
        convertedData.deactivatedAt = data.deactivatedAt.toDate().toISOString();
      }
      if (data.reactivatedAt && data.reactivatedAt.toDate) {
        convertedData.reactivatedAt = data.reactivatedAt.toDate().toISOString();
      }
      
      users.push({
        uid: doc.id,
        ...convertedData
      });
    });

    return {
      success: true,
      users: users
    };

  } catch (error) {
    console.error('Get all users error:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '사용자 목록 조회 중 오류가 발생했습니다.');
  }
});

// 사용자 계정 비활성화 (관리자 전용)
const deactivateUser = wrap(async (request) => {
  const { uid, token } = await auth(request);
  const { userId } = request.data;

  if (!userId) {
    throw new HttpsError('invalid-argument', '사용자 ID가 필요합니다.');
  }

  try {
    const db = admin.firestore();
    
    // 요청자가 관리자인지 확인
    const requesterDoc = await db.collection('users').doc(uid).get();
    const userData = requesterDoc.data() || {};
    const isAdmin = userData.role === 'admin' || userData.isAdmin === true; // 이전 버전과 호환성
    
    if (!requesterDoc.exists || !isAdmin) {
      throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
    }

    // 자기 자신은 비활성화할 수 없음
    if (uid === userId) {
      throw new HttpsError('failed-precondition', '자신의 계정은 비활성화할 수 없습니다.');
    }

    // Firestore에서 사용자 비활성화
    await db.collection('users').doc(userId).update({
      isActive: false,
      deactivatedAt: admin.firestore.FieldValue.serverTimestamp(),
      deactivatedBy: uid
    });

    // Firebase Auth에서 사용자 비활성화
    await admin.auth().updateUser(userId, {
      disabled: true
    });

    console.log(`User ${userId} deactivated by admin ${uid}`);

    return {
      success: true,
      message: '사용자 계정이 비활성화되었습니다.'
    };

  } catch (error) {
    console.error('Deactivate user error:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '계정 비활성화 중 오류가 발생했습니다.');
  }
});

// 사용자 계정 재활성화 (관리자 전용)
const reactivateUser = wrap(async (request) => {
  const { uid, token } = await auth(request);
  const { userId } = request.data;

  if (!userId) {
    throw new HttpsError('invalid-argument', '사용자 ID가 필요합니다.');
  }

  try {
    const db = admin.firestore();
    
    // 요청자가 관리자인지 확인
    const requesterDoc = await db.collection('users').doc(uid).get();
    const userData = requesterDoc.data() || {};
    const isAdmin = userData.role === 'admin' || userData.isAdmin === true; // 이전 버전과 호환성
    
    if (!requesterDoc.exists || !isAdmin) {
      throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
    }

    // Firestore에서 사용자 재활성화
    await db.collection('users').doc(userId).update({
      isActive: true,
      reactivatedAt: admin.firestore.FieldValue.serverTimestamp(),
      reactivatedBy: uid
    });

    // Firebase Auth에서 사용자 재활성화
    await admin.auth().updateUser(userId, {
      disabled: false
    });

    console.log(`User ${userId} reactivated by admin ${uid}`);

    return {
      success: true,
      message: '사용자 계정이 재활성화되었습니다.'
    };

  } catch (error) {
    console.error('Reactivate user error:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '계정 재활성화 중 오류가 발생했습니다.');
  }
});

// 사용자 계정 완전 삭제 (관리자 전용)
const deleteUser = wrap(async (request) => {
  const { uid, token } = await auth(request);
  const { userId } = request.data;

  if (!userId) {
    throw new HttpsError('invalid-argument', '사용자 ID가 필요합니다.');
  }

  try {
    const db = admin.firestore();
    
    // 요청자가 관리자인지 확인
    const requesterDoc = await db.collection('users').doc(uid).get();
    const userData = requesterDoc.data() || {};
    const isAdmin = userData.role === 'admin' || userData.isAdmin === true; // 이전 버전과 호환성
    
    if (!requesterDoc.exists || !isAdmin) {
      throw new HttpsError('permission-denied', '관리자 권한이 필요합니다.');
    }

    // 자기 자신은 삭제할 수 없음
    if (uid === userId) {
      throw new HttpsError('failed-precondition', '자신의 계정은 삭제할 수 없습니다.');
    }

    // 삭제 로그를 위해 사용자 정보 백업
    const userDoc = await db.collection('users').doc(userId).get();
    const userDataToDelete = userDoc.data();

    // 관련된 모든 데이터 삭제
    const batch = db.batch();

    // 사용자 프로필 삭제
    batch.delete(db.collection('users').doc(userId));

    // 사용자의 게시물 삭제
    const postsSnapshot = await db.collection('posts').where('userId', '==', userId).get();
    postsSnapshot.forEach(doc => {
      batch.delete(doc.ref);
    });

    // 사용자의 발행 기록 삭제
    const publishingDoc = db.collection('user_publishing').doc(userId);
    if ((await publishingDoc.get()).exists) {
      batch.delete(publishingDoc);
    }

    // 사용자의 바이오 삭제
    const bioDoc = db.collection('bios').doc(userId);
    if ((await bioDoc.get()).exists) {
      batch.delete(bioDoc);
    }

    // 삭제 로그 추가
    batch.set(db.collection('admin_logs').doc(), {
      action: 'USER_DELETED',
      adminId: uid,
      deletedUserId: userId,
      deletedUserData: userDataToDelete,
      timestamp: admin.firestore.FieldValue.serverTimestamp()
    });

    // Firestore 일괄 삭제 실행
    await batch.commit();

    // Firebase Auth에서 사용자 삭제
    await admin.auth().deleteUser(userId);

    console.log(`User ${userId} completely deleted by admin ${uid}`);

    return {
      success: true,
      message: '사용자 계정과 모든 관련 데이터가 삭제되었습니다.'
    };

  } catch (error) {
    console.error('Delete user error:', error);
    if (error instanceof HttpsError) {
      throw error;
    }
    throw new HttpsError('internal', '계정 삭제 중 오류가 발생했습니다.');
  }
});

module.exports = {
  getAllUsers,
  deactivateUser,
  reactivateUser,
  deleteUser
};