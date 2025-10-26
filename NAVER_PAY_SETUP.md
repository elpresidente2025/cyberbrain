# 네이버페이 결제 연동 설정 가이드

## 개요
토스페이먼츠에서 네이버페이로 결제 시스템을 전환하는 설정 가이드입니다.

## 1. 네이버페이 파트너 가입

1. [네이버페이 파트너센터](https://partner.pay.naver.com/) 접속
2. 파트너 가입 신청
3. 사업자 정보 등록 및 심사 대기
4. 승인 완료 후 API 키 발급

## 2. API 키 발급

네이버페이 파트너센터에서 다음 정보를 발급받습니다:

- **Client ID**: 네이버페이 API 클라이언트 ID
- **Client Secret**: 네이버페이 API 클라이언트 시크릿
- **Partner ID**: 네이버페이 파트너 ID

## 3. Firebase Functions 환경변수 설정

### 3.1 로컬 개발 환경 (.env 파일)

`functions/.env` 파일에 다음 환경변수를 추가합니다:

```bash
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret
NAVER_PARTNER_ID=your_naver_partner_id
```

### 3.2 Firebase 프로덕션 환경

Firebase Functions 환경변수로 설정합니다:

```bash
# Firebase CLI를 사용한 환경변수 설정
firebase functions:secrets:set NAVER_CLIENT_ID
firebase functions:secrets:set NAVER_CLIENT_SECRET
firebase functions:secrets:set NAVER_PARTNER_ID
```

또는 Firebase Console에서 직접 설정:
1. Firebase Console 접속
2. Functions > 설정 > 환경 구성
3. 환경변수 추가

## 4. 프론트엔드 환경변수 설정 (선택사항)

`frontend/.env` 파일에 다음을 추가합니다 (필요시):

```bash
VITE_NAVER_PAY_ENABLED=true
```

## 5. 네이버페이 결제 URL 설정

네이버페이 파트너센터에서 결제 성공/실패 URL을 설정합니다:

- **성공 URL**: `https://your-domain.com/payment/success`
- **실패 URL**: `https://your-domain.com/payment/fail`

프로덕션 도메인 예시:
- 성공: `https://ai-secretary-6e9c8.web.app/payment/success`
- 실패: `https://ai-secretary-6e9c8.web.app/payment/fail`

## 6. 테스트 환경 설정

### 6.1 네이버페이 테스트 모드

네이버페이는 별도의 테스트 환경을 제공합니다.
- 테스트 API 엔드포인트: `https://dev.apis.naver.com/naverpay-partner/naverpay/payments/v2.2/`
- 프로덕션 API 엔드포인트: `https://apis.naver.com/naverpay-partner/naverpay/payments/v2.2/`

### 6.2 테스트 결제

테스트 환경에서는 실제 결제가 발생하지 않으므로 안전하게 테스트할 수 있습니다.

## 7. 배포

### 7.1 Functions 배포

```bash
npm run deploy:functions
```

또는

```bash
firebase deploy --only functions
```

### 7.2 Frontend 배포

```bash
npm run build
firebase deploy --only hosting
```

## 8. 검증

### 8.1 결제 흐름 테스트

1. 로그인
2. Billing 페이지 접속
3. "결제하기" 버튼 클릭
4. 네이버페이 결제 페이지 확인
5. 테스트 결제 진행
6. 결제 성공 페이지 리다이렉트 확인
7. Firestore에 결제 데이터 저장 확인

### 8.2 로그 확인

Firebase Console에서 Functions 로그를 확인합니다:

```bash
firebase functions:log
```

필요한 로그:
- ✅ 네이버페이 결제 준비 성공
- ✅ 네이버페이 승인 성공
- ✅ 사용자 구독 정보 업데이트 완료

## 9. 주의사항

### 9.1 보안
- API 키는 절대 소스코드에 하드코딩하지 않습니다
- 환경변수로만 관리합니다
- `.env` 파일은 `.gitignore`에 포함되어야 합니다

### 9.2 에러 처리
- 네이버페이 API 에러는 `payment_failures` 컬렉션에 자동 기록됩니다
- 결제 실패 시 사용자에게 명확한 에러 메시지를 표시합니다

### 9.3 데이터베이스
- 결제 성공: `payments` 컬렉션에 저장
- 결제 실패: `payment_failures` 컬렉션에 저장
- 결제 준비: `payment_reserves` 컬렉션에 저장

## 10. 문제 해결

### 결제 준비 실패
- NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 환경변수 확인
- 네이버페이 파트너 계정 상태 확인
- API 엔드포인트 URL 확인

### 결제 승인 실패
- 결제 금액 확인
- 주문번호 중복 확인
- 네이버페이 잔액/한도 확인

### 리다이렉트 실패
- successUrl, failUrl 설정 확인
- CORS 설정 확인
- 네이버페이 파트너센터의 허용 도메인 확인

## 11. 참고 문서

- [네이버페이 개발 가이드](https://developer.pay.naver.com/)
- [네이버페이 API 레퍼런스](https://developer.pay.naver.com/docs/api)
- [Firebase Functions 환경변수 가이드](https://firebase.google.com/docs/functions/config-env)

## 12. 기존 토스페이먼츠 제거 (선택사항)

네이버페이로 완전 전환 후, 토스페이먼츠 관련 코드를 제거할 수 있습니다:

1. `frontend/src/components/TossPayment.jsx` 삭제 (또는 백업)
2. `functions/handlers/toss-payments.js` 비활성화 (또는 백업)
3. 환경변수에서 TOSS_CLIENT_KEY, TOSS_SECRET_KEY 제거

## 변경 사항 요약

### 프론트엔드
- ✅ Billing.jsx: 단일 요금제로 변경 (55,000원, 90회)
- ✅ PaymentDialog.jsx: 네이버페이 컴포넌트 사용
- ✅ NaverPayment.jsx: 신규 생성
- ✅ Dashboard.jsx: 플랜명/색상 함수 수정
- ✅ AboutPage.jsx: 가격 안내 업데이트
- ✅ PublishingProgress.jsx: 플랜별 한도 수정
- ✅ UsageGuide.jsx: 플랜 정보 업데이트

### 백엔드
- ✅ functions/handlers/naver-payments.js: 신규 생성
- ✅ functions/index.js: 네이버페이 핸들러 추가

### 데이터베이스 구조
```
payments/
  {orderId}/
    - userId
    - orderId
    - amount: 55000
    - orderName: "전자두뇌비서관 - 스탠다드 플랜 (1개월)"
    - status: "completed"
    - method: "naverpay"
    - approvedAt
    - createdAt

users/
  {uid}/
    - plan: "스탠다드 플랜"
    - monthlyLimit: 90
    - subscriptionStatus: "active"
    - nextBillingDate
    - lastPaymentAt
    - lastPaymentAmount: 55000
```
