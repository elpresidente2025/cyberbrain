/**
 * functions/services/notification.js
 * 알림 서비스 (인앱 + 이메일)
 */

'use strict';

const { admin, db } = require('../utils/firebaseAdmin');
const fs = require('fs');
const path = require('path');

/**
 * 알림 유형 정의
 */
const NOTIFICATION_TYPES = {
  PRIORITY_GAINED: 'district_priority_gained',
  PRIORITY_LOST: 'district_priority_lost',
  SUBSCRIPTION_EXPIRING: 'subscription_expiring',
  SUBSCRIPTION_EXPIRED: 'subscription_expired',
};

/**
 * 우선권 획득 알림 (인앱 + 이메일)
 */
async function notifyPriorityGained({ userId, districtKey, previousUserId = null }) {
  console.log('📧 [notifyPriorityGained] 시작:', { userId, districtKey });

  try {
    // 1. 사용자 정보 조회
    const [userDoc, userRecord] = await Promise.all([
      db.collection('users').doc(userId).get(),
      admin.auth().getUser(userId)
    ]);

    if (!userDoc.exists) {
      console.error('❌ 사용자 문서 없음:', userId);
      return;
    }

    const userData = userDoc.data();
    const userName = userData.name || '사용자';
    const userEmail = userRecord.email;

    if (!userEmail) {
      console.warn('⚠️ 이메일 주소 없음:', userId);
    }

    // 2. 인앱 알림 생성
    await db.collection('notifications').add({
      userId,
      type: NOTIFICATION_TYPES.PRIORITY_GAINED,
      title: '🎉 우선권 획득!',
      message: '선거구 우선권을 획득했습니다. 이제 서비스를 이용하실 수 있습니다.',
      districtKey,
      read: false,
      actionUrl: '/dashboard',
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      metadata: {
        previousUserId,
        reason: previousUserId ? 'previous_cancelled' : 'first_payment'
      }
    });

    console.log('✅ 인앱 알림 생성 완료:', userId);

    // 3. 이메일 발송 (Firebase Extension 사용)
    if (userEmail) {
      const emailData = {
        to: userEmail,
        message: {
          subject: '🎉 선거구 우선권 획득 안내',
          html: await renderEmailTemplate('priority-gained', {
            userName,
            districtName: formatDistrictName(districtKey),
            loginUrl: process.env.APP_URL || 'https://ai-secretary.web.app',
            supportEmail: process.env.SUPPORT_EMAIL || 'support@ai-secretary.com'
          })
        }
      };

      await db.collection('mail').add(emailData);
      console.log('✅ 이메일 발송 요청 완료:', userEmail);
    }

    return { success: true };

  } catch (error) {
    console.error('❌ [notifyPriorityGained] 실패:', error);
    // 알림 실패는 메인 프로세스에 영향을 주지 않음
    return { success: false, error: error.message };
  }
}

/**
 * 우선권 상실 알림
 */
async function notifyPriorityLost({ userId, districtKey, newPrimaryUserId }) {
  console.log('📧 [notifyPriorityLost] 시작:', { userId, districtKey });

  try {
    const userDoc = await db.collection('users').doc(userId).get();
    if (!userDoc.exists) return;

    const userData = userDoc.data();

    // 인앱 알림만 생성 (이메일은 선택사항)
    await db.collection('notifications').add({
      userId,
      type: NOTIFICATION_TYPES.PRIORITY_LOST,
      title: 'ℹ️ 우선권 변경 안내',
      message: '다른 사용자가 먼저 결제하여 우선권이 변경되었습니다.',
      districtKey,
      read: false,
      actionUrl: '/settings',
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      metadata: {
        newPrimaryUserId
      }
    });

    console.log('✅ 우선권 상실 알림 생성 완료:', userId);
    return { success: true };

  } catch (error) {
    console.error('❌ [notifyPriorityLost] 실패:', error);
    return { success: false, error: error.message };
  }
}

/**
 * 구독 만료 임박 알림
 */
async function notifySubscriptionExpiring({ userId, daysRemaining }) {
  console.log('📧 [notifySubscriptionExpiring] 시작:', { userId, daysRemaining });

  try {
    const [userDoc, userRecord] = await Promise.all([
      db.collection('users').doc(userId).get(),
      admin.auth().getUser(userId)
    ]);

    if (!userDoc.exists) return;

    const userData = userDoc.data();
    const userName = userData.name || '사용자';
    const userEmail = userRecord.email;

    // 인앱 알림
    await db.collection('notifications').add({
      userId,
      type: NOTIFICATION_TYPES.SUBSCRIPTION_EXPIRING,
      title: '⚠️ 구독 만료 임박',
      message: `구독이 ${daysRemaining}일 후 만료됩니다. 갱신해주세요.`,
      read: false,
      actionUrl: '/subscription',
      createdAt: admin.firestore.FieldValue.serverTimestamp(),
      metadata: { daysRemaining }
    });

    // 이메일 발송
    if (userEmail) {
      await db.collection('mail').add({
        to: userEmail,
        message: {
          subject: `⚠️ 구독이 ${daysRemaining}일 후 만료됩니다`,
          text: `안녕하세요, ${userName}님. 구독이 ${daysRemaining}일 후 만료됩니다. 계속 이용하시려면 구독을 갱신해주세요.`,
          html: `
            <h2>안녕하세요, ${userName}님</h2>
            <p>구독이 <strong>${daysRemaining}일 후</strong> 만료됩니다.</p>
            <p>계속 이용하시려면 구독을 갱신해주세요.</p>
            <a href="${process.env.APP_URL}/subscription">구독 갱신하기</a>
          `
        }
      });
    }

    console.log('✅ 구독 만료 알림 완료:', userId);
    return { success: true };

  } catch (error) {
    console.error('❌ [notifySubscriptionExpiring] 실패:', error);
    return { success: false, error: error.message };
  }
}

/**
 * 이메일 템플릿 렌더링
 */
async function renderEmailTemplate(templateName, data) {
  try {
    const templatePath = path.join(__dirname, '..', 'email-templates', `${templateName}.html`);

    if (!fs.existsSync(templatePath)) {
      console.warn(`⚠️ 템플릿 파일 없음: ${templatePath}, 기본 HTML 사용`);
      return generateDefaultHtml(data);
    }

    let html = fs.readFileSync(templatePath, 'utf-8');

    // 템플릿 변수 치환
    Object.keys(data).forEach(key => {
      const regex = new RegExp(`{{${key}}}`, 'g');
      html = html.replace(regex, data[key] || '');
    });

    return html;

  } catch (error) {
    console.error('❌ 템플릿 렌더링 실패:', error);
    return generateDefaultHtml(data);
  }
}

/**
 * 기본 HTML 생성 (템플릿 없을 경우)
 */
function generateDefaultHtml(data) {
  return `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body { font-family: sans-serif; padding: 20px; }
        .container { max-width: 600px; margin: 0 auto; background: #f9f9f9; padding: 30px; border-radius: 8px; }
        .button { background: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 4px; display: inline-block; margin-top: 20px; }
      </style>
    </head>
    <body>
      <div class="container">
        <h1>🎉 우선권 획득 안내</h1>
        <p>안녕하세요, <strong>${data.userName}</strong>님!</p>
        <p><strong>${data.districtName}</strong> 선거구의 우선권을 획득하셨습니다.</p>
        <p>이제 월 90회 콘텐츠 생성 서비스를 이용하실 수 있습니다.</p>
        <a href="${data.loginUrl}/dashboard" class="button">지금 시작하기</a>
      </div>
    </body>
    </html>
  `;
}

/**
 * 선거구 키를 읽기 쉬운 이름으로 변환
 */
function formatDistrictName(districtKey) {
  if (!districtKey) return '선거구';

  // 예: "국회의원__서울특별시__강남구__가선거구" → "서울특별시 강남구 가선거구"
  const parts = districtKey.split('__');
  if (parts.length >= 3) {
    return parts.slice(1).join(' ');
  }

  return districtKey;
}

/**
 * 사용자의 읽지 않은 알림 조회
 */
async function getUnreadNotifications(userId, limit = 10) {
  const snapshot = await db
    .collection('notifications')
    .where('userId', '==', userId)
    .where('read', '==', false)
    .orderBy('createdAt', 'desc')
    .limit(limit)
    .get();

  return snapshot.docs.map(doc => ({
    id: doc.id,
    ...doc.data(),
    createdAt: doc.data().createdAt?.toDate()
  }));
}

/**
 * 알림 읽음 처리
 */
async function markNotificationAsRead(notificationId) {
  await db.collection('notifications').doc(notificationId).update({
    read: true,
    readAt: admin.firestore.FieldValue.serverTimestamp()
  });
}

/**
 * 모든 알림 읽음 처리
 */
async function markAllNotificationsAsRead(userId) {
  const snapshot = await db
    .collection('notifications')
    .where('userId', '==', userId)
    .where('read', '==', false)
    .get();

  const batch = db.batch();
  snapshot.docs.forEach(doc => {
    batch.update(doc.ref, {
      read: true,
      readAt: admin.firestore.FieldValue.serverTimestamp()
    });
  });

  await batch.commit();
  return { updated: snapshot.size };
}

module.exports = {
  NOTIFICATION_TYPES,
  notifyPriorityGained,
  notifyPriorityLost,
  notifySubscriptionExpiring,
  getUnreadNotifications,
  markNotificationAsRead,
  markAllNotificationsAsRead
};
