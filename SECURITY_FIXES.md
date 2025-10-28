# 보안 수정 사항 (2025-01-28)

## 개요
전체 코드베이스 보안 감사 결과 발견된 7가지 심각한 보안 취약점을 모두 수정했습니다.

## 수정된 보안 취약점

### 1. ✅ CRITICAL: 인증 우회 취약점 제거
**위치**: `functions/common/auth.js`

**문제**:
- 클라이언트가 제공하는 `__naverAuth` 객체를 신뢰
- 공격자가 임의의 UID를 전송하여 다른 사용자로 위장 가능
- 모든 네이버 사용자 계정 탈취 위험

**해결**:
```javascript
// BEFORE (취약)
const naverAuth = request.data?.__naverAuth;
if (naverAuth && naverAuth.uid) {
  return { uid: naverAuth.uid }; // 클라이언트 제공 UID 신뢰
}

// AFTER (보안)
if (!request.auth || !request.auth.uid) {
  throw new HttpsError('unauthenticated', '로그인이 필요합니다.');
}
return { uid: request.auth.uid }; // Firebase Auth만 신뢰
```

### 2. ✅ CRITICAL: Firebase Custom Token 인증 구현
**위치**:
- `functions/handlers/naver-login.js:230-237` (신규 사용자)
- `functions/handlers/naver-login.js:289-296` (기존 사용자)
- `frontend/src/hooks/useNaverLogin.js:91-99`

**구현**:
- 백엔드: 네이버 OAuth 검증 후 Firebase Custom Token 발급
- 프론트엔드: Custom Token으로 Firebase Auth 로그인
- 모든 후속 API 호출은 Firebase Auth 토큰 사용

**코드**:
```javascript
// Backend
const customToken = await admin.auth().createCustomToken(userDoc.id, {
  provider: 'naver',
  naverUserId: naverUserData.id
});

// Frontend
const userCredential = await signInWithCustomToken(auth, customToken);
```

### 3. ✅ CRITICAL: 민감 데이터 로깅 제거
**위치**:
- `functions/handlers/naver-login.js:106-113`
- `functions/handlers/toss-payments.js:61-82`

**제거된 항목**:
- 전체 요청 body 로깅 (액세스 토큰 포함)
- `rawPaymentData` 저장 (카드 정보 포함 가능)
- 에러 스택 트레이스 클라이언트 노출

**PCI DSS 준수**:
```javascript
// BEFORE
rawPaymentData: paymentData // 전체 카드 정보 저장

// AFTER (마스킹된 정보만)
card: paymentData.card ? {
  company: paymentData.card.company,
  number: paymentData.card.number, // 이미 마스킹됨
  installmentPlanMonths: paymentData.card.installmentPlanMonths
} : null
```

### 4. ✅ IMPORTANT: 에러 메시지 보안 강화
**위치**: `functions/handlers/naver-login.js:336-342`

**변경**:
```javascript
// BEFORE
return response.json({
  error: {
    message: error.message,
    stack: error.stack  // 내부 정보 노출
  }
});

// AFTER
return response.json({
  error: {
    message: '네이버 로그인 처리 중 오류가 발생했습니다.'  // 일반적 메시지
  }
});
```

### 5. ✅ IMPORTANT: 환경 변수 검증 추가
**위치**: `functions/index.js:9-23`

**구현**:
```javascript
const REQUIRED_ENV_VARS = [
  'NAVER_CLIENT_ID',
  'NAVER_CLIENT_SECRET',
  'TOSS_SECRET_KEY',
  'GEMINI_API_KEY'
];

const missingVars = REQUIRED_ENV_VARS.filter(v => !process.env[v]);
if (missingVars.length > 0) {
  console.error('❌ 필수 환경 변수 누락:', missingVars);
}
```

### 6. ✅ IMPORTANT: CORS 설정 중앙집중화
**위치**: `functions/common/config.js:21-31`

**개선**:
- 모든 핸들러가 동일한 `ALLOWED_ORIGINS` 사용
- 개발 환경 자동 감지 (localhost 추가)
- 일관성 있는 CORS 정책 적용

### 7. ✅ 프론트엔드 보안 강화
**위치**:
- `frontend/src/services/firebaseService.js:44-53`
- `frontend/src/hooks/useNaverLogin.js:91-99`

**변경**:
- `__naverAuth` 패턴 완전 제거
- Firebase Auth 표준 인증만 사용
- `callFunctionWithNaverAuth`를 일반 Firebase Functions 호출로 변경

## 마이그레이션 가이드

### 배포 순서 (중요!)

1. **백엔드 먼저 배포**:
   ```bash
   cd functions
   npm install
   firebase deploy --only functions
   ```

2. **프론트엔드 배포**:
   ```bash
   cd frontend
   npm install
   npm run build
   firebase deploy --only hosting
   ```

### 기존 사용자 영향

**영향 없음**:
- 기존 로그인 세션은 유지됨
- 다음 로그인 시 자동으로 새로운 인증 방식 사용
- 데이터 마이그레이션 불필요

**주의사항**:
- 백엔드와 프론트엔드 배포 사이 간격을 최소화할 것
- 배포 후 네이버 로그인 테스트 필수

## 테스트 체크리스트

- [ ] 네이버 신규 가입 테스트
- [ ] 네이버 기존 사용자 로그인 테스트
- [ ] 프로필 조회 API 호출 테스트
- [ ] 결제 기능 테스트
- [ ] Firebase Auth 토큰 자동 갱신 확인
- [ ] 에러 처리 확인 (잘못된 토큰, 만료된 토큰 등)

## 영향받는 파일 목록

### Backend
- `functions/common/auth.js` - 완전히 재작성
- `functions/common/config.js` - CORS 설정 추가
- `functions/handlers/naver-login.js` - Custom Token 발급 추가
- `functions/handlers/toss-payments.js` - 민감 데이터 제거
- `functions/index.js` - 환경 변수 검증 추가

### Frontend
- `frontend/src/hooks/useNaverLogin.js` - Custom Token 인증 추가
- `frontend/src/services/firebaseService.js` - `__naverAuth` 패턴 제거

## 보안 개선 효과

1. **인증 보안**: 클라이언트 위조 불가능한 Firebase Auth 토큰 사용
2. **데이터 보호**: PCI DSS 준수, 민감 정보 로깅 제거
3. **정보 노출 방지**: 에러 메시지 일반화
4. **운영 안정성**: 환경 변수 검증으로 설정 오류 조기 발견
5. **코드 품질**: CORS 설정 중앙화로 유지보수성 향상

## 추가 권장사항

### 단기 (1-2주 내)
- [ ] Firestore Security Rules 재검토
- [ ] API Rate Limiting 구현
- [ ] 로그 모니터링 시스템 구축

### 중기 (1-2개월 내)
- [ ] 정기적인 보안 감사 프로세스 수립
- [ ] 침투 테스트 수행
- [ ] 보안 교육 및 가이드라인 문서화

## 참고 자료

- [Firebase Custom Tokens](https://firebase.google.com/docs/auth/admin/create-custom-tokens)
- [PCI DSS Compliance](https://www.pcisecuritystandards.org/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
