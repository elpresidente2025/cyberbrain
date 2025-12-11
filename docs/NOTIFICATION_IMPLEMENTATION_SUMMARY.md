# 알림 시스템 구현 완료 요약

## ✅ 구현된 항목

### 1. 백엔드 서비스

#### 📁 `functions/services/notification.js`
- `notifyPriorityGained()` - 우선권 획득 알림
- `notifyPriorityLost()` - 우선권 상실 알림
- `notifySubscriptionExpiring()` - 구독 만료 임박 알림
- `getUnreadNotifications()` - 읽지 않은 알림 조회
- `markNotificationAsRead()` - 알림 읽음 처리
- `markAllNotificationsAsRead()` - 모든 알림 읽음 처리

#### 📁 `functions/services/district.js`
- `notifyPriorityChange()` - 우선권 변경 시 자동 알림 발송

#### 📁 `functions/handlers/notifications.js`
- `getNotifications` - HTTP Callable 함수
- `markNotificationRead` - HTTP Callable 함수
- `markAllNotificationsRead` - HTTP Callable 함수

#### 📁 `functions/index.js`
- 알림 핸들러 exports 추가

### 2. 이메일 템플릿

#### 📁 `functions/email-templates/priority-gained.html`
- 우선권 획득 안내 이메일 템플릿
- 반응형 디자인
- 변수 치환 지원 (userName, districtName, loginUrl, supportEmail)

### 3. 문서

#### 📁 `docs/FIREBASE_EMAIL_SETUP.md`
- Firebase Email Extension 설치 가이드
- Gmail/SendGrid SMTP 설정 방법
- 문제 해결 가이드

#### 📁 `docs/NOTIFICATION_USAGE.md`
- 알림 시스템 사용 방법
- 프론트엔드 통합 가이드
- API 호출 예시
- 데이터 구조 설명

#### 📁 `docs/NOTIFICATION_IMPLEMENTATION_SUMMARY.md` (현재 파일)
- 구현 완료 항목 정리
- 다음 단계 안내

### 4. 테스트 도구

#### 📁 `functions/scripts/test-notification.js`
- 알림 발송 테스트 스크립트
- 사용법: `node functions/scripts/test-notification.js <userId>`

---

## 🚀 다음 단계

### 1. Firebase Extension 설치 (필수)

```bash
firebase ext:install firestore-send-email
```

**설정 값:**
- Email 문서 컬렉션: `mail`
- FROM 주소: `noreply@yourdomain.com`
- SMTP URI: Gmail 앱 비밀번호 사용 (FIREBASE_EMAIL_SETUP.md 참조)

### 2. 환경 변수 설정

```bash
firebase functions:config:set \
  app.url="https://yourdomain.com" \
  app.support_email="support@yourdomain.com"
```

### 3. 배포

```bash
# Functions 배포
firebase deploy --only functions

# Firestore 보안 규칙 업데이트 (필요시)
firebase deploy --only firestore:rules
```

### 4. Firestore 보안 규칙 추가

```javascript
// firestore.rules
match /notifications/{notificationId} {
  allow read: if request.auth != null
              && request.auth.uid == resource.data.userId;
  allow write: if false;  // 서버만 쓰기
}

match /mail/{mailId} {
  allow read, write: if false;  // 클라이언트 접근 불가
}
```

### 5. 프론트엔드 통합

#### A. 알림 배너 컴포넌트 추가

```javascript
// components/NotificationBanner.jsx
import { useEffect, useState } from 'react';
import { db } from '../firebase';
import { collection, query, where, orderBy, limit, onSnapshot } from 'firebase/firestore';
import { httpsCallable } from 'firebase/functions';
import { functions } from '../firebase';

export function NotificationBanner({ userId }) {
  const [notifications, setNotifications] = useState([]);

  useEffect(() => {
    if (!userId) return;

    const q = query(
      collection(db, 'notifications'),
      where('userId', '==', userId),
      where('read', '==', false),
      orderBy('createdAt', 'desc'),
      limit(5)
    );

    const unsubscribe = onSnapshot(q, (snapshot) => {
      const notifs = snapshot.docs.map(doc => ({
        id: doc.id,
        ...doc.data()
      }));
      setNotifications(notifs);
    });

    return unsubscribe;
  }, [userId]);

  const handleMarkAsRead = async (notificationId) => {
    const markRead = httpsCallable(functions, 'markNotificationRead');
    await markRead({ notificationId });
  };

  if (notifications.length === 0) return null;

  return (
    <div className="notification-banner">
      {notifications.map(notif => (
        <div key={notif.id} className="notification-item">
          <span className="title">{notif.title}</span>
          <span className="message">{notif.message}</span>
          <button onClick={() => handleMarkAsRead(notif.id)}>확인</button>
        </div>
      ))}
    </div>
  );
}
```

#### B. Dashboard에 추가

```javascript
// pages/Dashboard.jsx
import { NotificationBanner } from '../components/NotificationBanner';

function Dashboard() {
  const { currentUser } = useAuth();

  return (
    <div>
      <NotificationBanner userId={currentUser?.uid} />
      {/* 기존 대시보드 내용 */}
    </div>
  );
}
```

#### C. Firestore 인덱스 생성

Firebase Console → Firestore → Indexes에서 복합 인덱스 생성:
- 컬렉션: `notifications`
- 필드: `userId` (Ascending), `read` (Ascending), `createdAt` (Descending)

---

## 🧪 테스트

### 1. 로컬 테스트

```bash
# 테스트 스크립트 실행
cd functions
node scripts/test-notification.js <실제-사용자-ID>
```

### 2. 확인 사항

1. **Firestore Console 확인**
   - `notifications` 컬렉션에 새 문서 생성됨
   - `mail` 컬렉션에 새 문서 생성됨

2. **이메일 수신 확인**
   - 받은편지함 확인
   - 스팸함도 확인

3. **발송 상태 확인**
   - `mail` 컬렉션 문서의 `delivery.state` 필드 확인
   - `SUCCESS`: 발송 성공
   - `ERROR`: 발송 실패 (delivery.error 확인)

### 3. 프론트엔드 테스트

1. 로그인 후 대시보드 접속
2. 알림 배너가 표시되는지 확인
3. "확인" 버튼 클릭 시 알림 사라지는지 확인
4. Firestore에서 `read: true`로 업데이트되었는지 확인

---

## 📊 데이터 흐름

```
우선권 변경 발생
    ↓
notifyPriorityChange() 호출
    ↓
    ├─→ notifyPriorityGained()
    │       ├─→ notifications 컬렉션에 문서 추가 (인앱 알림)
    │       └─→ mail 컬렉션에 문서 추가
    │               ↓
    │           Firebase Extension이 감지
    │               ↓
    │           SMTP로 이메일 발송
    │               ↓
    │           delivery 필드 업데이트
    │
    └─→ notifyPriorityLost() (선택사항)
            └─→ notifications 컬렉션에 문서 추가
```

---

## 🔍 트러블슈팅

### 이메일이 발송되지 않는 경우

1. Firebase Console → Functions → 로그 확인
2. `mail` 컬렉션의 `delivery.error` 확인
3. SMTP 설정 재확인 (Gmail 앱 비밀번호)

### 알림이 표시되지 않는 경우

1. Firestore 보안 규칙 확인
2. 복합 인덱스 생성 확인
3. 브라우저 콘솔에서 에러 확인

### 이메일이 스팸으로 분류되는 경우

1. SPF/DKIM 설정 (도메인 이메일 사용 시)
2. SendGrid 등 전문 SMTP 서비스 사용 권장

---

## 💰 예상 비용

### 무료 범위
- Firestore 읽기/쓰기: 일 50,000건 무료
- Firebase Email Extension: 월 5,000통 무료
- Gmail SMTP: 무료 (일일 500통 제한)

### 유료 전환 시점
- 월 5,000통 초과 시: SendGrid 유료 플랜 고려 ($19.95/월)
- Firestore 무료 할당량 초과 시: 약 $0.06/10만 읽기

**예상**: 사용자 100명 기준 → 월 $0~5 정도

---

## 📝 추가 개선 사항 (선택)

### 1. 푸시 알림 (FCM)
- 브라우저가 닫혀있어도 알림 수신
- 구현 복잡도: 중간
- NOTIFICATION_USAGE.md 참조

### 2. 알림 설정 UI
- 사용자가 알림 유형별 on/off 설정
- `users` 컬렉션에 `notificationPreferences` 필드 추가

### 3. 알림 히스토리
- 읽은 알림도 30일간 보관
- "모든 알림 보기" 페이지

### 4. 배치 알림
- 하루 한 번 요약 이메일
- 여러 알림을 하나로 묶어 발송

---

## ✅ 체크리스트

구현 완료 후 다음 항목을 체크하세요:

- [ ] Firebase Email Extension 설치 완료
- [ ] SMTP 설정 및 테스트 이메일 발송 성공
- [ ] Functions 배포 완료
- [ ] Firestore 보안 규칙 업데이트
- [ ] Firestore 복합 인덱스 생성
- [ ] 프론트엔드 NotificationBanner 컴포넌트 추가
- [ ] 실제 사용자로 end-to-end 테스트 완료
- [ ] 이메일이 스팸으로 분류되지 않는지 확인
- [ ] 프로덕션 환경 변수 설정 (APP_URL, SUPPORT_EMAIL)
- [ ] 모니터링 설정 (Firebase Console → Functions → 로그)

---

## 🎉 완료!

모든 항목이 체크되면 알림 시스템이 정상 작동합니다.

질문이나 문제가 있으면:
1. `docs/NOTIFICATION_USAGE.md` 참조
2. Firebase Functions 로그 확인
3. `mail` 컬렉션의 delivery 필드 확인

**Happy Coding! 🚀**
