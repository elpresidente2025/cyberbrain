# 🎯 우선권 시스템 구현 완료

## ✅ 구현 완료 항목

### 1. 핵심 서비스 (`functions/services/district-priority.js`)
- ✅ `addUserToDistrict()` - 선거구에 사용자 추가 (중복 허용)
- ✅ `handlePaymentSuccess()` - 결제 완료 시 우선권 처리
- ✅ `handleSubscriptionCancellation()` - 구독 취소 시 우선권 재배정
- ✅ `changeUserDistrict()` - 선거구 변경 처리
- ✅ `getDistrictStatus()` - 선거구 상태 조회 (정보 최소화)
- ✅ `checkGenerationPermission()` - 콘텐츠 생성 권한 확인

### 2. 결제 핸들러 (`functions/handlers/payment.js`)
- ✅ `processPayment` - 결제 처리 + 우선권 부여
- ✅ `cancelSubscription` - 구독 취소 + 우선권 재배정
- ✅ `getPaymentStatus` - 결제/우선권 상태 조회

### 3. 프로필 핸들러 수정 (`functions/handlers/profile.js`)
- ✅ `registerWithDistrictCheck` - 가입 시 중복 허용, 경고만 표시
- ✅ `updateProfile` - 선거구 변경 시 우선권 처리

### 4. 콘텐츠 생성 권한 체크 (`functions/handlers/posts.js`)
- ✅ `generatePosts` 함수에 우선권 체크 추가
- ✅ 비우선권자는 생성 차단

### 5. 알림 시스템 (`functions/services/notification.js`)
- ✅ 우선권 획득 알림 (인앱 + 이메일)
- ✅ 우선권 상실 알림
- ✅ 구독 만료 임박 알림

### 6. 마이그레이션 스크립트 (`functions/scripts/migrate-to-priority-system.js`)
- ✅ district_claims 컬렉션 구조 변경
- ✅ users 컬렉션 필드 추가
- ✅ DRY-RUN 모드 지원

---

## 🔄 시스템 동작 흐름

### 1️⃣ 회원가입
```
사용자 가입
  ↓
선거구 입력 (position, regionMetro, regionLocal, electoralDistrict)
  ↓
addUserToDistrict() 호출
  ├─ 첫 가입자: district_claims 문서 생성
  └─ 추가 가입자: members 배열에 추가
  ↓
users 문서 생성
  - districtStatus: 'trial'
  - isPrimaryInDistrict: false
  - districtPriority: null
```

### 2️⃣ 결제 완료
```
processPayment() 호출
  ↓
handlePaymentSuccess()
  ├─ 첫 결제자?
  │   ├─ YES → isPrimary: true, priority: 1
  │   │         primaryUserId 설정
  │   └─ NO  → isPrimary: false, priority: 2, 3, ...
  ↓
users 문서 업데이트
  - isPrimaryInDistrict: true/false
  - districtStatus: 'primary' or 'waiting'
  - monthlyLimit: 90 (우선권자) or 0 (대기자)
  ↓
우선권 획득 시 알림 발송 📧
```

### 3️⃣ 콘텐츠 생성
```
generatePosts() 호출
  ↓
checkGenerationPermission()
  ├─ trial → generationsRemaining 확인
  ├─ cancelled/expired → 차단
  ├─ active + !isPrimary → 차단 (비우선권자)
  └─ active + isPrimary → 월 사용량 확인
  ↓
허용되면 생성 진행
차단되면 HttpsError 발생
```

### 4️⃣ 구독 취소
```
cancelSubscription() 호출
  ↓
handleSubscriptionCancellation()
  ├─ 우선권자가 취소?
  │   ├─ YES → 다음 순위자 찾기
  │   │         (priority 기준 정렬)
  │   │         ↓
  │   │         새 primaryUserId 설정
  │   │         ↓
  │   │         알림 발송 📧
  │   └─ NO  → members 배열에서만 상태 변경
  ↓
취소한 사용자
  - districtStatus: 'cancelled'
  - monthlyLimit: 0
```

### 5️⃣ 선거구 변경
```
updateProfile() - 선거구 변경 시
  ↓
changeUserDistrict()
  ├─ 1. 기존 선거구에서 제거
  │      handleSubscriptionCancellation()
  │      ↓
  │      우선권자였다면 다음 순위자에게 이전 📧
  ├─ 2. 새 선거구에 추가
  │      addUserToDistrict()
  └─ 3. 유료 사용자면 새 선거구에서 결제 처리
         handlePaymentSuccess()
         ↓
         새 선거구에서 우선권 획득 시 알림 📧
```

---

## 📊 데이터 구조

### district_claims/{districtKey}

```javascript
{
  members: [
    {
      userId: "user1",
      registeredAt: Timestamp,
      paidAt: Timestamp,
      subscriptionStatus: "active",
      priority: 1,
      isPrimary: true
    },
    {
      userId: "user2",
      registeredAt: Timestamp,
      paidAt: Timestamp,
      subscriptionStatus: "active",
      priority: 2,
      isPrimary: false
    },
    {
      userId: "user3",
      registeredAt: Timestamp,
      paidAt: null,
      subscriptionStatus: "trial",
      priority: null,
      isPrimary: false
    }
  ],
  primaryUserId: "user1",
  totalMembers: 3,
  paidMembers: 2,
  waitlistCount: 1,
  createdAt: Timestamp,
  lastUpdated: Timestamp,
  priorityHistory: [
    {
      userId: "user1",
      becamePrimaryAt: Timestamp,
      reason: "first_payment"
    }
  ]
}
```

### users/{uid} (추가 필드)

```javascript
{
  // 기존 필드들...
  districtKey: "국회의원__서울특별시__강남구__가선거구",

  // 우선권 시스템 필드
  districtPriority: 1,              // 우선순위 (1순위, 2순위, ...)
  isPrimaryInDistrict: true,         // 우선권자 여부
  districtStatus: "primary",         // trial | primary | waiting | cancelled

  // 결제 정보
  subscriptionStatus: "active",      // trial | active | cancelled | expired
  paidAt: Timestamp,                 // 결제 시점
  monthlyLimit: 90                   // 월 사용 한도
}
```

---

## 🚀 배포 순서

### 1️⃣ 코드 배포

```bash
# Functions 배포
firebase deploy --only functions
```

### 2️⃣ 마이그레이션 (DRY-RUN 먼저!)

```bash
# 시뮬레이션 (변경 안 함)
cd functions
node scripts/migrate-to-priority-system.js --dry-run

# 실제 마이그레이션
node scripts/migrate-to-priority-system.js
```

### 3️⃣ Firebase Email Extension 설치

```bash
firebase ext:install firestore-send-email
```

설정:
- Email 컬렉션: `mail`
- FROM 주소: `noreply@yourdomain.com`
- SMTP URI: Gmail 앱 비밀번호 (docs/FIREBASE_EMAIL_SETUP.md 참조)

### 4️⃣ 환경 변수 설정

```bash
firebase functions:config:set \
  app.url="https://your-domain.com" \
  app.support_email="support@your-domain.com"
```

---

## 🧪 테스트 시나리오

### 시나리오 1: 첫 가입자 → 결제
1. 사용자 A 가입 → districtStatus: 'trial'
2. 사용자 A 결제 → isPrimary: true, priority: 1
3. 콘텐츠 생성 → 성공 ✅
4. 이메일 확인 → "우선권 획득" 알림 수신 📧

### 시나리오 2: 두 번째 가입자 → 결제
1. 사용자 B 동일 선거구 가입 → districtStatus: 'trial'
2. 사용자 B 결제 → isPrimary: false, priority: 2
3. 콘텐츠 생성 시도 → 차단 ❌ ("다른 사용자가 우선권 보유 중")

### 시나리오 3: 우선권자 구독 취소
1. 사용자 A 구독 취소
2. 우선권 자동 이전 → 사용자 B가 isPrimary: true
3. 사용자 B 이메일 수신 → "우선권 획득" 📧
4. 사용자 B 콘텐츠 생성 → 성공 ✅

### 시나리오 4: 선거구 변경
1. 사용자 A(우선권자) 선거구 변경
2. 기존 선거구 → 사용자 B에게 우선권 이전 📧
3. 새 선거구 → 사용자 A가 첫 가입자면 즉시 우선권 획득

---

## 📝 API 엔드포인트

### 결제
```javascript
// 결제 처리
const processPayment = httpsCallable(functions, 'processPayment');
const result = await processPayment({ plan: '스탠다드 플랜' });

// 구독 취소
const cancelSubscription = httpsCallable(functions, 'cancelSubscription');
await cancelSubscription({ reason: '사용자 요청' });

// 상태 조회
const getPaymentStatus = httpsCallable(functions, 'getPaymentStatus');
const status = await getPaymentStatus();
```

### 알림
```javascript
// 알림 조회
const getNotifications = httpsCallable(functions, 'getNotifications');
const notifs = await getNotifications({ limit: 10 });

// 알림 읽음 처리
const markNotificationRead = httpsCallable(functions, 'markNotificationRead');
await markNotificationRead({ notificationId: 'xxx' });
```

---

## ⚠️ 주의사항

### 1. 정보 비공개
- ❌ 선거구 내 가입자 수 표시하지 않음
- ❌ 대기 순번 표시하지 않음
- ✅ "다른 사용자가 이용 중" 정도만 표시

### 2. 트랜잭션 사용
- 모든 우선권 변경은 Firestore 트랜잭션 사용
- 동시성 문제 자동 해결

### 3. 알림 실패
- 알림 발송 실패는 메인 프로세스에 영향 없음
- 로그만 남기고 계속 진행

### 4. 마이그레이션
- 반드시 DRY-RUN 먼저 실행
- 기존 사용자는 자동으로 우선권자로 전환
- 롤백 불가하므로 백업 권장

---

## 🎉 완료!

모든 우선권 시스템 구현이 완료되었습니다.

**다음 단계:**
1. ✅ 코드 배포 (`firebase deploy --only functions`)
2. ✅ 마이그레이션 실행 (`node scripts/migrate-to-priority-system.js`)
3. ✅ Email Extension 설치
4. ✅ 프론트엔드 UI 업데이트 (선택사항)
5. ✅ 테스트 및 모니터링

**문서:**
- `FIREBASE_EMAIL_SETUP.md` - Email Extension 설치
- `NOTIFICATION_USAGE.md` - 알림 시스템 사용법
- `PRIORITY_SYSTEM_COMPLETE.md` - 이 문서

Happy Coding! 🚀
