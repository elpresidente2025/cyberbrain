# 알림 시스템 사용 가이드

## 개요

Firebase Email Extension을 활용한 인앱 알림 + 이메일 알림 시스템입니다.

## 1. Firebase Extension 설치

```bash
# Extension 설치
firebase ext:install firestore-send-email

# 설정 값:
# - Email 문서 컬렉션: mail
# - FROM 주소: noreply@yourdomain.com
# - SMTP URI: smtps://yourname@gmail.com:app-password@smtp.gmail.com:465
```

자세한 설치 방법은 `FIREBASE_EMAIL_SETUP.md` 참조

## 2. 알림 유형

### 2.1 우선권 획득 알림
```javascript
const { notifyPriorityGained } = require('./services/notification');

await notifyPriorityGained({
  userId: 'user123',
  districtKey: '국회의원__서울특별시__강남구__가선거구',
  previousUserId: 'user456'  // 선택사항
});
```

**발송 내용:**
- 인앱 알림: notifications 컬렉션에 문서 추가
- 이메일: mail 컬렉션에 문서 추가 → Extension이 자동 발송

### 2.2 우선권 상실 알림
```javascript
const { notifyPriorityLost } = require('./services/notification');

await notifyPriorityLost({
  userId: 'user123',
  districtKey: '국회의원__서울특별시__강남구__가선거구',
  newPrimaryUserId: 'user789'
});
```

### 2.3 구독 만료 임박 알림
```javascript
const { notifySubscriptionExpiring } = require('./services/notification');

await notifySubscriptionExpiring({
  userId: 'user123',
  daysRemaining: 3
});
```

## 3. 프론트엔드 통합

### 3.1 실시간 알림 구독 (React)

```javascript
// Dashboard.jsx 또는 App.jsx
import { useEffect, useState } from 'react';
import { db } from './firebase';
import { collection, query, where, orderBy, limit, onSnapshot } from 'firebase/firestore';

function NotificationBanner() {
  const [notifications, setNotifications] = useState([]);
  const currentUser = useAuth();

  useEffect(() => {
    if (!currentUser?.uid) return;

    const q = query(
      collection(db, 'notifications'),
      where('userId', '==', currentUser.uid),
      where('read', '==', false),
      orderBy('createdAt', 'desc'),
      limit(5)
    );

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const notifs = snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data(),
        createdAt: doc.data().createdAt?.toDate()
      }));
      setNotifications(notifs);
    });

    return unsubscribe;
  }, [currentUser]);

  if (notifications.length === 0) return null;

  return (
    <div className="notification-banner">
      {notifications.map(notif => (
        <div key={notif.id} className="notification-item">
          <span className="notification-icon">{notif.title}</span>
          <span className="notification-message">{notif.message}</span>
          <button onClick={() => handleMarkAsRead(notif.id)}>
            확인
          </button>
        </div>
      ))}
    </div>
  );
}

async function handleMarkAsRead(notificationId) {
  const markNotificationRead = httpsCallable(functions, 'markNotificationRead');
  await markNotificationRead({ notificationId });
}
```

### 3.2 알림 조회 API 호출

```javascript
import { httpsCallable } from 'firebase/functions';
import { functions } from './firebase';

// 읽지 않은 알림 조회
async function getNotifications() {
  const getNotifications = httpsCallable(functions, 'getNotifications');
  const result = await getNotifications({ limit: 10 });
  console.log(result.data.notifications);
}

// 특정 알림 읽음 처리
async function markAsRead(notificationId) {
  const markNotificationRead = httpsCallable(functions, 'markNotificationRead');
  await markNotificationRead({ notificationId });
}

// 모든 알림 읽음 처리
async function markAllAsRead() {
  const markAllNotificationsRead = httpsCallable(functions, 'markAllNotificationsRead');
  await markAllNotificationsRead();
}
```

## 4. 실제 사용 예시

### 예시 1: 결제 완료 후 우선권 부여

```javascript
// handlers/payment.js
const { notifyPriorityGained } = require('../services/notification');

async function handlePaymentSuccess({ userId, districtKey }) {
  // ... 결제 처리 로직 ...

  // 우선권 획득 알림 발송
  await notifyPriorityGained({
    userId,
    districtKey
  });

  return { success: true };
}
```

### 예시 2: 구독 취소 시 다음 순위자에게 우선권 이전

```javascript
// services/district.js (이미 구현됨)
const { notifyPriorityChange } = require('./district');

async function handleSubscriptionCancellation({ userId, districtKey }) {
  // ... 우선권 재배정 로직 ...

  // 새 우선권자에게 알림
  await notifyPriorityChange({
    newPrimaryUserId: 'user789',
    oldPrimaryUserId: userId,
    districtKey
  });
}
```

## 5. 데이터 구조

### notifications 컬렉션

```javascript
{
  id: "notif_123",
  userId: "user123",
  type: "district_priority_gained",
  title: "🎉 우선권 획득!",
  message: "선거구 우선권을 획득했습니다. 이제 서비스를 이용하실 수 있습니다.",
  districtKey: "국회의원__서울특별시__강남구__가선거구",
  read: false,
  actionUrl: "/dashboard",
  createdAt: Timestamp,
  readAt: null,  // 읽으면 Timestamp 설정
  metadata: {
    previousUserId: "user456",
    reason: "first_payment"
  }
}
```

### mail 컬렉션 (Firebase Extension이 처리)

```javascript
{
  to: "user@example.com",
  message: {
    subject: "🎉 선거구 우선권 획득 안내",
    html: "<html>...</html>"
  },
  // Extension이 자동 추가:
  delivery: {
    state: "SUCCESS",
    startTime: Timestamp,
    endTime: Timestamp,
    info: {
      messageId: "xxx",
      accepted: ["user@example.com"]
    }
  }
}
```

## 6. 이메일 템플릿 커스터마이징

템플릿 파일 위치: `functions/email-templates/priority-gained.html`

```html
<!-- 변수 치환 가능 -->
<h1>안녕하세요, {{userName}}님!</h1>
<p>{{districtName}} 선거구의 우선권을 획득하셨습니다.</p>
<a href="{{loginUrl}}">지금 시작하기</a>
```

사용 가능한 변수:
- `{{userName}}` - 사용자 이름
- `{{districtName}}` - 선거구 이름
- `{{loginUrl}}` - 로그인 URL
- `{{supportEmail}}` - 고객지원 이메일

## 7. 테스트

### 로컬 테스트

```javascript
// Firebase Console → Firestore에서 직접 추가
await db.collection('mail').add({
  to: 'your-email@example.com',
  message: {
    subject: '테스트 이메일',
    html: '<h1>테스트입니다</h1>'
  }
});

// 또는 함수 직접 호출
const { notifyPriorityGained } = require('./services/notification');
await notifyPriorityGained({
  userId: 'test-user-id',
  districtKey: '국회의원__서울특별시__강남구__가선거구'
});
```

### 발송 상태 확인

```javascript
// mail 컬렉션의 delivery 필드 확인
const mailDoc = await db.collection('mail').doc('mail_123').get();
console.log(mailDoc.data().delivery);
// {
//   state: 'SUCCESS',
//   startTime: ...,
//   endTime: ...,
//   info: { messageId: 'xxx', ... }
// }
```

## 8. 문제 해결

### 이메일이 발송되지 않는 경우

1. **Firebase Console → Functions → 로그** 확인
   ```
   Error: Invalid login: 535-5.7.8 Username and Password not accepted
   ```
   → Gmail 앱 비밀번호 재확인

2. **mail 컬렉션의 delivery.state** 확인
   - `PENDING`: 발송 대기 중
   - `SUCCESS`: 발송 성공
   - `ERROR`: 발송 실패 (delivery.error 확인)

3. **Extension 설정** 재확인
   ```bash
   firebase ext:list
   firebase ext:configure firestore-send-email
   ```

### 알림이 표시되지 않는 경우

1. Firestore 보안 규칙 확인
   ```javascript
   match /notifications/{notificationId} {
     allow read: if request.auth != null
                 && request.auth.uid == resource.data.userId;
   }
   ```

2. 프론트엔드 쿼리 확인
   ```javascript
   // orderBy와 where를 함께 사용할 경우 인덱스 필요
   // Firebase Console → Firestore → Indexes에서 복합 인덱스 생성
   ```

## 9. 비용

- **인앱 알림**: Firestore 읽기/쓰기 비용만 (거의 무료)
- **이메일**:
  - Firebase Extension: 월 5,000통 무료
  - Gmail SMTP: 무료 (일일 500통 제한)
  - SendGrid: 월 100통 무료, 이후 유료

## 10. 보안 고려사항

### Firestore 규칙

```javascript
// firestore.rules
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // 알림: 본인만 읽기 가능
    match /notifications/{notificationId} {
      allow read: if request.auth != null
                  && request.auth.uid == resource.data.userId;
      allow write: if false;  // 서버만 쓰기 가능
    }

    // mail 컬렉션: 클라이언트 접근 불가
    match /mail/{mailId} {
      allow read, write: if false;
    }
  }
}
```

### 환경 변수

```bash
# .env (로컬 개발)
APP_URL=http://localhost:3000
SUPPORT_EMAIL=support@yourdomain.com

# Firebase 환경 변수 (프로덕션)
firebase functions:config:set \
  app.url="https://yourdomain.com" \
  app.support_email="support@yourdomain.com"
```

## 요약

✅ **설치**: `firebase ext:install firestore-send-email`
✅ **알림 발송**: `notifyPriorityGained()` 함수 호출
✅ **프론트엔드**: Firestore 실시간 구독으로 알림 표시
✅ **이메일**: Extension이 자동 처리
✅ **비용**: 거의 무료 (월 5,000통까지)

문의: 추가 기능이 필요하면 `services/notification.js`에 함수 추가
