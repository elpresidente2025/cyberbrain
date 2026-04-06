# Python Backend Migration Inventory

작성일: 2026-03-25

## 목표

최종 목표는 Firebase Functions 백엔드를 완전히 Python으로 전환하고, `functions/` Node.js 코드베이스를 제거하는 것이다.

이 문서는 현재 저장소 기준으로 다음을 정리한다.

- 현재 배포 런타임 구조
- Python 이관 완료 함수
- Node 전용 함수와 도메인별 잔여 범위
- 프런트가 실제로 호출하는 함수 기준 우선순위
- 즉시 정리 가능한 stale/dead 후보

## 현재 구조 요약

- 배포는 아직 이중 코드베이스다.
  - Node: `functions` / codebase `default`
  - Python: `functions/python` / codebase `python-rag`
- 기준 파일
  - `firebase.json`
  - `functions/index.js`
  - `functions/python/main.py`
  - Node export 수치는 `functions/index.js` 실제 로드 결과 기준으로 계산했다.

### 수치 스냅샷

- Python export 수: 23
- Node export 수: 88
- 이름 기준 Python/Node 중복 수: 0
- Node 전용 export 수: 88

### 프런트 참조 스냅샷

프런트에서 실제 호출 경로 기준으로 확인한 백엔드 함수 참조는 다음 상태로 나뉜다.

- Python 연결: 6
- Node 연결: 28
- stale 또는 unexported: 0

즉, 핵심 생성/게시 경로는 Python으로 넘어왔지만 운영 표면 대부분은 아직 Node에 남아 있다. Wave 0 기준선 정리로 broken export 3개와 stale/dead 파일 2개는 이미 처리했다.

## Python 활성 표면

현재 `functions/python/main.py` 기준 Python export:

- `pipeline_start`
- `pipeline_step`
- `pipeline_status`
- `pipeline_retry`
- `py_saveSelectedPost`
- `saveSelectedPost`
- `generatePosts`
- `getUserPosts`
- `getPost`
- `updatePost`
- `deletePost`
- `checkUsageLimit`
- `indexPastPosts`
- `index_bio_to_rag`
- `batch_index_bios`
- `save_selected_post`
- `py_convertToSNS`
- `py_getSNSUsage`
- `py_testSNS`
- `convert_to_sns`
- `get_sns_usage`
- `test_sns`
- `generate_post`

## Python 단독 운영 중인 핵심 게시 경로

아래 함수는 현재 Python 쪽에서만 운영되고 있다.

- `generatePosts`
- `saveSelectedPost`
- `getUserPosts`
- `getPost`
- `updatePost`
- `deletePost`
- `checkUsageLimit`
- `indexPastPosts`

이 영역은 사실상 1차 컷오버가 끝난 상태로 봐도 된다. 남은 일은 관련 stale 문서와 옛 흔적 정리다.

## 도메인별 Node 잔여 범위

### 1. 프로필 / 계정

- 핸들러
  - `functions/handlers/profile.js`
- 주요 export
  - `getUserProfile`
  - `updateProfile`
  - `updateUserPlan`
  - `checkDistrictAvailability`
  - `registerWithDistrictCheck`
  - `analyzeBioOnUpdate`
  - `cleanupDistrictClaimsOnUserDelete`
- 프런트 사용
  - `getUserProfile`
  - `updateProfile`
  - `checkDistrictAvailability`
- 우선순위
  - 매우 높음
- 메모
  - 생성 UX와 회원 관리 UX의 핵심 진입점이다.

### 2. 게시 후속 처리 / 발행 / 보너스

- 핸들러
  - `functions/handlers/publishing.js`
  - `functions/handlers/session.js`
- 주요 export
  - `publishPost`
  - `getPublishingStats`
  - `checkBonusEligibility`
  - `useBonusGeneration`
  - `getMonthlyTarget`
  - `resetUserUsage`
  - `toggleTester`
  - `toggleFaceVerified`
  - `resetGenerationSession`
  - `getGenerationSession`
  - `adminResetSession`
- 프런트 사용
  - `publishPost`
  - `getPublishingStats`
  - `checkBonusEligibility`
  - `useBonusGeneration`
- 우선순위
  - 매우 높음
- 메모
  - 생성 완료 후 실제 발행/사용량/보너스 흐름이 아직 Node에 남아 있다.

### 3. 대시보드 / 시스템 / 공지 / 알림

- 핸들러
  - `functions/handlers/dashboard.js`
  - `functions/handlers/system.js`
  - `functions/handlers/system-config.js`
  - `functions/handlers/notices.js`
  - `functions/handlers/notifications.js`
- 주요 export
  - `getDashboardData`
  - `healthCheck`
  - `testPrompt`
  - `checkGeminiStatus`
  - `getPolicyTemplate`
  - `testPolicy`
  - `logUserActivity`
  - `getSystemStatus`
  - `updateGeminiStatus`
  - `updateSystemStatus`
  - `getSystemConfig`
  - `updateSystemConfig`
  - `createNotice`
  - `updateNotice`
  - `deleteNotice`
  - `getNotices`
  - `getActiveNotices`
  - `getAdminStats`
  - `getErrorLogs`
  - `getNotifications`
  - `markNotificationRead`
  - `markAllNotificationsRead`
- 프런트 사용
  - `getDashboardData`
  - `getSystemConfig`
  - `getActiveNotices`
- 우선순위
  - 높음
- 메모
  - 관리자/대시보드 UI가 Node 의존이다.

### 4. SNS 변환

- 핸들러
  - `functions/handlers/sns-addon.js`
- 주요 export
  - `convertToSNS`
  - `getSNSUsage`
  - `testSNS`
- 프런트 사용
  - `convertToSNS`
  - `getSNSUsage`
- Python 상태
  - Python 유사 기능 존재 (`py_convertToSNS`, `py_getSNSUsage`, `py_testSNS`)
  - 동명 컷오버는 아직 미완료
- 우선순위
  - 중상
- 메모
  - 이미 Python 로직이 있으므로 함수명 컷오버가 빠를 가능성이 높다.

### 5. 키워드 분석

- 핸들러
  - `functions/handlers/keyword-analysis.js`
- 주요 export
  - `requestKeywordAnalysis`
  - `keywordAnalysisWorker`
  - `getKeywordAnalysisResult`
  - `getKeywordAnalysisHistory`
- 프런트 사용
  - `requestKeywordAnalysis`
  - `getKeywordAnalysisResult`
- 우선순위
  - 높음
- 메모
  - 생성 보조 UX와 연결된다.

### 6. 인증 / 네이버 로그인

- 핸들러
  - `functions/handlers/naver-login.js`
- 주요 export
  - `naverLogin`
  - `naverLoginHTTP`
- 프런트 사용
  - `naverLoginHTTP`
- 우선순위
  - 높음
- 메모
  - 가입/로그인 실패는 전체 서비스 이용 차단으로 이어진다.

### 7. 결제 / 검증

- 핸들러
  - `functions/handlers/payment.js`
  - `functions/handlers/naver-payments.js`
  - `functions/handlers/party-verification.js`
- 주요 export
  - `processPayment`
  - `cancelSubscription`
  - `getPaymentStatus`
  - `initiateNaverPayment`
  - `confirmNaverPayment`
  - `getUserPayments`
  - `verifyPartyCertificate`
  - `verifyPaymentReceipt`
  - `getVerificationHistory`
- 프런트 사용
  - `initiateNaverPayment`
  - `confirmNaverPayment`
  - `verifyPartyCertificate`
  - `verifyPaymentReceipt`
- 우선순위
  - 높음
- 메모
  - 외부 연동과 금전 흐름이므로 도메인 안정화 후 이관 권장.

### 8. 관리자 / 운영 도구

- 핸들러
  - `functions/handlers/admin.js`
  - `functions/handlers/admin-users.js`
  - `functions/handlers/emergency-admin.js`
  - `functions/handlers/merge-user.js`
  - `functions/handlers/cleanup-legacy-fields.js`
- 주요 export
  - `syncDistrictKey`
  - `checkAdminStatus`
  - `setAdminStatus`
  - `getAllUsers`
  - `deactivateUser`
  - `reactivateUser`
  - `deleteUser`
  - `emergencyRestoreAdmin`
  - `mergeDuplicateUser`
  - `removeLegacyDistrictField`
  - `removeLegacyProfileImage`
  - `removeLegacyIsAdmin`
- 프런트 사용
  - `emergencyRestoreAdmin`
  - `mergeDuplicateUser`
  - `removeLegacyDistrictField`
  - `removeLegacyProfileImage`
  - `removeLegacyIsAdmin`
- 우선순위
  - 중간
- 메모
  - 사용자 핵심 경로보다 뒤로 미뤄도 된다.

### 9. URL 단축 / 동기화 배치

- 핸들러
  - `functions/handlers/url-shortener.js`
  - `functions/handlers/district-sync-handler.js`
  - `functions/handlers/politician-sync-handler.js`
- 주요 export
  - `createShortUrl`
  - `redirectShortUrl`
  - `scheduledDistrictSync`
  - `syncElectoralDistricts`
  - `getElectionList`
  - `scheduledPoliticianSync`
  - `syncPoliticiansManual`
- 프런트 사용
  - `createShortUrl`
- 우선순위
  - 중간
- 메모
  - 배치와 온디맨드가 섞여 있어 컷오버 전에 스케줄링 전략을 정리해야 한다.

## 프런트 기준 함수 상태

### Python 연결

- `generatePosts`
- `getUserPosts`
- `getPost`
- `deletePost`
- `indexPastPosts`
- `batch_index_bios`

### Node 연결

- `deleteUserAccount`
- `getUserProfile`
- `updateProfile`
- `checkDistrictAvailability`
- `getDashboardData`
- `getPerformanceMetrics`
- `getSystemConfig`
- `getActiveNotices`
- `getPublishingStats`
- `publishPost`
- `checkBonusEligibility`
- `useBonusGeneration`
- `convertToSNS`
- `getSNSUsage`
- `createShortUrl`
- `requestKeywordAnalysis`
- `getKeywordAnalysisResult`
- `naverLoginHTTP`
- `naverCompleteRegistration`
- `initiateNaverPayment`
- `confirmNaverPayment`
- `verifyPartyCertificate`
- `verifyPaymentReceipt`
- `emergencyRestoreAdmin`
- `mergeDuplicateUser`
- `removeLegacyDistrictField`
- `removeLegacyProfileImage`
- `removeLegacyIsAdmin`

### stale 또는 unexported

- 없음

## 즉시 정리 후보

### A. index.js에 직접 연결되지 않은 handler 파일

아래 파일은 현재 `functions/index.js`에서 직접 mount되지 않는다.

- `bio.js`
- `debug-election.js`
- `diag.js`
- `naver-disconnect.js`
- `system.clean.js`
- `test-scraper.js`
- `username.js`

이 중 일부는 dead code일 가능성이 높고, 일부는 예전 실험/대체 구현일 수 있다.

### B. Wave 0에서 정리한 broken/stale 항목

- `deleteUserAccount`
  - `user-management.js` 구현을 `functions/index.js`에 재연결
- `getPerformanceMetrics`
  - `performance.js` 구현을 `functions/index.js`에 재연결
- `naverCompleteRegistration`
  - `naver-login2.js` 구현을 이름 충돌 없이 `functions/index.js`에 재연결
- `frontend/src/services/api.js`
  - import 흔적 없는 dead legacy 파일로 확인되어 제거
- `functions/exports_list.json`
  - 실제 export 표면과 어긋나는 stale 메타데이터로 확인되어 제거

## 권장 이관 웨이브

### Wave 0. 죽은 참조 정리

- 완료
- broken export 복구
  - `deleteUserAccount`
  - `getPerformanceMetrics`
  - `naverCompleteRegistration`
- dead legacy 제거
  - `frontend/src/services/api.js`
  - `functions/exports_list.json`

이제 프런트 기준 stale/unexported 함수명은 0개다.

### Wave 1. 사용자 핵심 경로

- `getUserProfile`
- `updateProfile`
- `checkDistrictAvailability`
- `getDashboardData`
- `getSystemConfig`
- `getActiveNotices`
- `publishPost`
- `getPublishingStats`
- `checkBonusEligibility`
- `useBonusGeneration`

이 웨이브를 끝내면 주요 UI는 대부분 Python 기반으로 전환된다.

### Wave 2. 인증 / 결제 / 검증

- `naverLogin`
- `naverLoginHTTP`
- `initiateNaverPayment`
- `confirmNaverPayment`
- `getUserPayments`
- `verifyPartyCertificate`
- `verifyPaymentReceipt`
- `getVerificationHistory`
- `processPayment`
- `cancelSubscription`
- `getPaymentStatus`

### Wave 3. 부가 생성 기능

- `convertToSNS`
- `getSNSUsage`
- `testSNS`
- `requestKeywordAnalysis`
- `keywordAnalysisWorker`
- `getKeywordAnalysisResult`
- `getKeywordAnalysisHistory`

### Wave 4. 관리자 / 배치 / 유틸리티

- `admin.js`
- `admin-users.js`
- `emergency-admin.js`
- `merge-user.js`
- `cleanup-legacy-fields.js`
- `district-sync-handler.js`
- `politician-sync-handler.js`
- `url-shortener.js`

### Wave 5. Node 코드베이스 절단

완료 조건:

- 프런트 문자열 참조 기준 Node 함수명 0개
- `functions/index.js` export 0개 또는 제거
- `firebase.json`에서 Node codebase 제거
- `functions/package.json` 제거
- Node 전용 handler 제거

## 실무 원칙

- 신규 백엔드 기능은 Python에만 추가한다.
- Python 이관 시 가능하면 기존 함수명을 유지한다.
- 동일 기능이 Python에 자리잡으면 Node 구현과 stale 문서를 즉시 제거한다.
- Python 코드 안의 `Node 포팅` 설명은 이관 완료 시점에 모두 걷어낸다.

## 바로 다음 액션

1. Wave 1 함수별 Python owner 문서화
2. Wave 1부터 함수 단위로 Node -> Python 컷오버
3. 각 컷오버 직후 Node 구현 삭제
4. Node 미마운트 handler의 실제 사용 여부 재검증 후 정리
