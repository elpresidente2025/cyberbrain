# Firebase Firestore 데이터 스키마

> 생성일: 2025-10-28
> CyberBrain 프로젝트의 전자두뇌비서관 Firestore 컬렉션 구조 문서

## 개요

이 문서는 CyberBrain 프로젝트에서 운영하는 전자두뇌비서관 서비스의 Firestore 데이터베이스 컬렉션 구조를 정리합니다.

---

## 1. `users` 컬렉션

사용자 프로필 및 계정 정보를 저장합니다.

### 필드 목록

#### 필수 필드
| 필드명 | 타입 | 설명 | 사용 위치 |
|--------|------|------|-----------|
| `naverUserId` | string | 네이버 사용자 ID | naver-login2.js:115, :148 |
| `name` | string | 사용자 이름 | profile.js:39, naver-login2.js:244 |
| `position` | string | 직책 (예: 국회의원, 광역자치단체장) | profile.js:41, :98 |
| `regionMetro` | string | 광역시/도 | profile.js:41, :98 |
| `regionLocal` | string | 시/군/구 | profile.js:42, :98 |
| `electoralDistrict` | string | 선거구 | profile.js:42, :98 |
| `status` | string | 재직 상태 (현역/준비) | profile.js:44, :99 |

#### 인증 관련 필드
| 필드명 | 타입 | 설명 |
|--------|------|------|
| `isAdmin` | boolean | 관리자 여부 |
| `role` | string | 역할 ('admin' 또는 null) |
| `provider` | string | 로그인 제공자 ('naver') |
| `isNaverUser` | boolean | 네이버 사용자 여부 |
| `profileImage` | string | 프로필 이미지 URL |
| `username` | string | 사용자명 (네이버 ID 기반) |

#### 개인화 정보 필드 (선택사항)
| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `ageDecade` | string | 연령대 | '40대', '50대' |
| `ageDetail` | string | 세부 연령 | '초반', '중반', '후반' |
| `age` | string | 연령 범위 | '40-49' (ageDecade에서 자동 변환) |
| `gender` | string | 성별 | '남성', '여성' |
| `familyStatus` | string | 가족 상황 | '기혼(자녀 있음)', '미혼' |
| `backgroundCareer` | string | 주요 배경 | '교육자', '사업가', '공무원' |
| `localConnection` | string | 지역 연고성 | '토박이', '오래 거주', '이주민' |
| `politicalExperience` | string | 정치 경험 | '초선', '재선', '3선 이상' |
| `committees` | array | 소속 위원회 목록 | ['교육위원회'] |
| `customCommittees` | array | 직접 입력한 위원회명 | ['특별위원회'] |
| `constituencyType` | string | 선거구 유형 | |
| `customTitle` | string | 준비 상태일 때 사용할 직위 | |

#### 구독 관련 필드
| 필드명 | 타입 | 설명 | 기본값 |
|--------|------|------|--------|
| `subscriptionStatus` | string | 구독 상태 | 'trial' (무료 체험), 'active' (유료), 'expired' |
| `trialPostsRemaining` | number | 체험판 남은 횟수 | 8 |
| `monthlyLimit` | number | 월간 생성 제한 | 8 (체험판), 플랜별 상이 |
| `postsThisMonth` | number | 이번 달 생성 횟수 | 0 |
| `planId` | string | 표준 요금제 ID | 'official-partnership' |
| `plan` | string | 표시용 요금제 이름(호환성 유지) | '공식 파트너십' |
| `billing.status` | string | 표준 청구 상태 | 'trial', 'active', 'cancelled', 'expired' |
| `billing.planId` | string | billing 스냅샷의 요금제 ID | 'official-partnership' |
| `billing.planName` | string | billing 스냅샷의 요금제 이름 | '공식 파트너십' |
| `billing.monthlyLimit` | number | 계약상 플랜 한도 스냅샷 | 90 |
| `subscription` | string | 레거시 구독명 (제거 대상) | |

#### 시스템 필드
| 필드명 | 타입 | 설명 |
|--------|------|------|
| `isActive` | boolean | 계정 활성화 여부 (bio 200자 이상 작성 시 true) |
| `districtKey` | string | 선거구 고유 키 (중복 방지용) |
| `profileComplete` | boolean | 프로필 완성 여부 |
| `createdAt` | timestamp | 생성 시각 |
| `updatedAt` | timestamp | 수정 시각 |
| `lastLoginAt` | timestamp | 마지막 로그인 시각 |

#### 글쓰기 스타일 분석 필드
| 필드명 | 타입 | 설명 |
|--------|------|------|
| `writingStyle` | object | 분석된 글쓰기 스타일 프로필 |
| `styleLastAnalyzed` | timestamp | 스타일 분석 마지막 수행 시각 |

### 주의사항
- ✅ **`bio` 필드는 users 컬렉션에 저장되지 않음** (완료)
- ✅ bio는 별도의 `bios` 컬렉션으로 완전 분리됨
- ✅ 회원가입/프로필 업데이트 시 bio는 자동으로 bios 컬렉션에만 저장됨
- ✅ getUserProfile에서는 bios 컬렉션을 조회하여 bio를 반환함 (호환성 유지)

---

## 2. `bios` 컬렉션

사용자의 자기소개 및 추가 정보를 저장합니다. (users 컬렉션에서 분리)

### 문서 ID
- 사용자 UID와 동일 (`userId`)

### 필드 목록
| 필드명 | 타입 | 설명 |
|--------|------|------|
| `userId` | string | 사용자 UID |
| `content` | string | 자기소개 내용 (단일 필드, 기존 bio) |
| `version` | number | 버전 번호 (업데이트마다 증가) |
| `entries` | array | Bio 엔트리 배열 (새로운 구조화 시스템) |
| `metadataStatus` | string | 메타데이터 추출 상태 ('pending', 'processing', 'completed') |
| `extractedMetadata` | object | AI가 추출한 메타데이터 |
| `usage` | object | 사용 통계 |
| `usage.generatedPostsCount` | number | 생성된 포스트 수 |
| `usage.avgQualityScore` | number | 평균 품질 점수 |
| `usage.lastUsedAt` | timestamp | 마지막 사용 시각 |
| `createdAt` | timestamp | 생성 시각 |
| `updatedAt` | timestamp | 수정 시각 |

### Bio Entry 구조 (entries 배열의 객체)
| 필드명 | 타입 | 설명 |
|--------|------|------|
| `id` | string | 엔트리 고유 ID |
| `type` | string | 엔트리 유형 (self_introduction, vision, policy, achievement 등) |
| `title` | string | 엔트리 제목 |
| `content` | string | 엔트리 내용 |
| `tags` | array | 태그 목록 (최대 10개) |
| `weight` | number | 가중치 (0~1) |
| `createdAt` | timestamp | 생성 시각 |
| `updatedAt` | timestamp | 수정 시각 |

---

## 3. `posts` 컬렉션

생성된 원고/포스트를 저장합니다.

### 필드 목록
| 필드명 | 타입 | 설명 |
|--------|------|------|
| `userId` | string | 작성자 UID |
| `authorId` | string | 작성자 UID (userId와 동일, 호환성용) |
| `title` | string | 포스트 제목 |
| `content` | string | 포스트 본문 |
| `wordCount` | number | 글자 수 |
| `status` | string | 상태 ('draft', 'published', 'archived') |
| `category` | string | 카테고리 |
| `options` | object | 생성 옵션 |
| `options.category` | string | 생성 시 선택한 카테고리 |
| `createdAt` | timestamp | 생성 시각 |
| `updatedAt` | timestamp | 수정 시각 |

### 인덱스
- `userId` + `createdAt` (오름차순)
- `userId` + `createdAt` (내림차순)

---

## 4. `district_claims` 컬렉션

선거구 점유 정보를 저장하여 중복 방지합니다.

### 문서 ID
- `districtKey`: position + regionMetro + regionLocal + electoralDistrict 조합

### 필드 목록
| 필드명 | 타입 | 설명 |
|--------|------|------|
| `userId` | string | 점유한 사용자 UID |
| `position` | string | 직책 |
| `regionMetro` | string | 광역시/도 |
| `regionLocal` | string | 시/군/구 |
| `electoralDistrict` | string | 선거구 |
| `claimedAt` | timestamp | 점유 시각 |
| `updatedAt` | timestamp | 수정 시각 |

### 참고
- 사용자가 삭제되면 해당 사용자의 district_claims도 자동 삭제됨 (profile.js:365-409)

---

## 5. `usernames` 컬렉션

사용자명 중복 방지를 위한 컬렉션입니다.

### 문서 ID
- 사용자명 (네이버 ID)

### 필드 목록
| 필드명 | 타입 | 설명 |
|--------|------|------|
| `uid` | string | 사용자 UID |
| `username` | string | 사용자명 |
| `createdAt` | timestamp | 생성 시각 |

---

## 6. `notices` 컬렉션

공지사항을 저장합니다.

### 접근 권한
- 읽기: 모든 사용자
- 쓰기: 관리자만

---

## 7. `system` 컬렉션

시스템 통계 및 설정을 저장합니다.

### 접근 권한
- 읽기/쓰기: 관리자만

---

## 8. `generation_progress` 컬렉션

원고 생성 진행 상황을 실시간으로 추적합니다.

### 문서 ID
- `{userId}_{timestamp}` 형식

### 접근 권한
- 읽기: 본인만 (sessionId가 자신의 UID로 시작하는 경우)
- 쓰기: Cloud Functions만 (Admin SDK)

---

## 필드명 불일치 문제 (✅ 해결 완료)

### 1. Bio 저장 위치
- ~~❌ **문제**: `users.bio` (구 방식) vs `bios.content` (신 방식) 혼재~~
- ✅ **해결 완료** (2025-10-28):
  - bios 컬렉션을 표준으로 사용
  - users 컬렉션에서 bio 필드 완전 제거
  - 회원가입 시 bios 컬렉션에만 저장 (profile.js:303-322, naver-login2.js:242-258)
  - 스타일 분석 트리거를 bios 컬렉션으로 변경 (profile.js:357-379)
  - getUserProfile에서 bios 컬렉션 조회하여 호환성 유지 (profile.js:71-79)

### 2. 사용자 ID 필드
- ~~❌ **문제**: `userId` vs `authorId` 혼용~~
- ✅ **해결 완료** (2025-10-28):
  - `userId`를 표준으로 사용
  - firestore.rules의 posts 컬렉션에서 authorId → userId로 변경 (firestore.rules:43)
  - 백엔드 코드는 이미 userId 사용 중

### 3. 구독 관련 필드
- ⚠️ **진행 중**:
  - `planId`를 표준 식별자로 사용
  - `plan`은 표시용 이름으로만 유지
  - `billing.status` / `billing.planId` / `billing.monthlyLimit`를 표준 billing 스냅샷으로 사용
  - `subscriptionStatus` / `monthlyLimit`는 기존 권한 로직과의 호환성 필드로 당분간 병행
  - `subscription` 레거시 필드는 제거 대상으로 취급

### 4. 나이 관련 필드
- ✅ **현재 구조 유지**:
  - 프론트엔드: `ageDecade` (40대) + `ageDetail` (초반/중반/후반) 사용
  - 백엔드: 자동으로 `age` 필드 생성/동기화 (40-49)
  - 동기화 로직: profile.js:49-62, :108-120
  - 정규화 스크립트로 기존 데이터 일괄 처리 가능

### 5. 성별 필드
- ✅ **현재 구조 유지**:
  - 저장 시 항상 '남성'/'여성'으로 정규화
  - 변환 함수: naver-login2.js:12-18, profile.js:64-69
  - 정규화 스크립트로 기존 데이터 일괄 처리 가능

---

## 마이그레이션 상태 (2025-10-28)

### ✅ 우선순위 1: Bio 필드 완전 분리 (완료)
- [x] users 컬렉션에서 bio 필드 완전 제거
- [x] 모든 백엔드 코드에서 users.bio 참조 제거
- [x] bios 컬렉션만 사용하도록 통일
- [x] 회원가입/프로필 업데이트 로직 수정
- [x] 스타일 분석 트리거를 bios 컬렉션으로 이동

**변경된 파일**:
- `functions/handlers/profile.js`: 303-322, 357-379
- `functions/handlers/naver-login2.js`: 242-258

### ✅ 우선순위 2: 필드명 통일 (완료)
- [x] userId/authorId 통일 (firestore.rules 수정)
- [x] plan 표준화 및 legacy subscription 제거 준비
- [x] planId + billing 스냅샷 표준 구조 추가

**변경된 파일**:
- `firestore.rules`: Line 43
- `functions/handlers/profile.js`: Line 246-247
- `functions/common/plan-catalog.js`
- `shared/plan-catalog.json`

### ✅ 우선순위 3: 데이터 정규화 (스크립트 준비 완료)
- [x] 데이터 정규화 스크립트 작성
- [ ] **프로덕션 실행 필요**: `node functions/scripts/normalize-user-data.js --dry-run`
- [ ] Dry-run 확인 후 실제 실행: `node functions/scripts/normalize-user-data.js`

**스크립트 기능**:
1. 성별 필드 일괄 정규화 (M/F → 남성/여성)
2. age ↔ ageDecade 자동 동기화
3. users.bio → bios.content 마이그레이션 (잔여 데이터 처리)
4. `planId` / `billing.*` backfill은 `functions/scripts/backfill-plan-schema.js`에서 별도 수행

**스크립트 위치**: `functions/scripts/normalize-user-data.js`

### 📋 추가 작업 필요
- [ ] 프론트엔드 코드 검토 및 필요시 수정
- [ ] Firestore 보안 규칙 배포: `firebase deploy --only firestore:rules`
- [ ] Functions 배포: `firebase deploy --only functions`
- [ ] 정규화 스크립트 실행 (Dry-run → Production)
- [ ] 배포 후 테스트

---

## 보안 규칙 요약

```javascript
// users 컬렉션
- Read: 본인 또는 Admin
- Create: 본인만 (role, isAdmin 설정 불가)
- Update: 본인 (role, isAdmin 변경 불가) 또는 Admin
- Delete: 본인 또는 Admin

// posts 컬렉션
- Read: 모두
- Write: 본인 또는 Admin

// notices 컬렉션
- Read: 모두
- Write: Admin만

// system 컬렉션
- Read/Write: Admin만

// generation_progress 컬렉션
- Read: 본인만 (sessionId 확인)
- Write: Cloud Functions만
```

---

## 참고 문서
- `firestore.rules`: 보안 규칙
- `firestore.indexes.json`: 인덱스 정의
- `functions/handlers/profile.js`: 프로필 관련 로직
- `functions/handlers/naver-login2.js`: 네이버 로그인 로직
- `functions/handlers/bio.js`: Bio 관리 로직
- `functions/handlers/dashboard.js`: 대시보드 데이터 조회

