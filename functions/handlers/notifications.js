/**
 * functions/handlers/notifications.js
 * 알림 관련 HTTP 핸들러
 */

'use strict';

const { wrap } = require('../common/wrap');
const { ok } = require('../common/response');
const { auth } = require('../common/auth');
const {
  getUnreadNotifications,
  markNotificationAsRead,
  markAllNotificationsAsRead
} = require('../services/notification');

/**
 * 읽지 않은 알림 조회
 */
exports.getNotifications = wrap(async (req) => {
  const { uid } = await auth(req);
  const { limit = 10 } = req.data || {};

  const notifications = await getUnreadNotifications(uid, limit);

  return ok({
    notifications,
    count: notifications.length,
    hasUnread: notifications.length > 0
  });
});

/**
 * 특정 알림 읽음 처리
 */
exports.markNotificationRead = wrap(async (req) => {
  const { uid } = await auth(req);
  const { notificationId } = req.data || {};

  if (!notificationId) {
    throw new Error('notificationId가 필요합니다.');
  }

  await markNotificationAsRead(notificationId);

  return ok({ message: '알림을 읽음 처리했습니다.' });
});

/**
 * 모든 알림 읽음 처리
 */
exports.markAllNotificationsRead = wrap(async (req) => {
  const { uid } = await auth(req);

  const result = await markAllNotificationsAsRead(uid);

  return ok({
    message: '모든 알림을 읽음 처리했습니다.',
    updated: result.updated
  });
});
