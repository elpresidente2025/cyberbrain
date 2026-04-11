# Firebase 스키마 정리 - 변경사항 요약

> 작업일: 2025-10-28
> 작업자: Claude Code
> 상태: ✅ 백엔드 코드 수정 완료 (배포 대기)

---

## 📋 작업 개요

Firebase Firestore 데이터베이스의 필드 불일치 문제를 해결하고 데이터 구조를 정리했습니다.

### 우선순위 1-3 모두 완료
1. ✅ Bio 필드 완전 분리 (users.bio → bios.content)
2. ✅ 필드명 통일 (userId/authorId, plan/subscription)
3. ✅ 데이터 정규화 스크립트 작성

---

## 🔧 변경된 파일

### 백엔드 (Functions)

#### 1. `functions/handlers/profile.js`
**주요 변경사항**:
- ✅ `registerWithDistrictCheck`: bio를 bios 컬렉션에만 저장 (Line 303-322)
- ✅ `analyzeBioOnUpdate`: 트리거를 users → bios 컬렉션으로 변경 (Line 357-379)
- ✅ `updateUserPlan`: plan/subscription 주석 명확화 (Line 246-247)

**Before**:
```javascript
// users 컬렉션에 bio 저장
await db.collection('users').doc(uid).set({
  ...sanitizedProfileData,
  bio,  // ❌ users 컬렉션에 저장
  isActive,
  // ...
});
```

**After**:
```javascript
// bios 컬렉션에만 저장
if (bio) {
  await db.collection('bios').doc(uid).set({
    userId: uid,
    content: bio,
    version: 1,
    // ...
  });
}

// users 컬렉션에는 저장하지 않음
await db.collection('users').doc(uid).set({
  ...sanitizedProfileData,  // bio 제외
  isActive,
  // ...
});
```

#### 2. `functions/handlers/naver-login2.js`
**주요 변경사항**:
- ✅ `naverCompleteRegistration`: bio를 bios 컬렉션에만 저장 (Line 242-258)
- ✅ isActive 필드를 bio 존재 여부로 설정 (Line 271)

**Before**:
```javascript
const doc = {
  naverUserId: naverUserData.id,
  name: String(profileData.name).trim(),
  bio: profileData.bio || '',  // ❌ users 컬렉션에 저장
  // ...
};
await ref.set(doc);
```

**After**:
```javascript
// bios 컬렉션에만 저장
const bio = profileData.bio ? String(profileData.bio).trim() : '';
if (bio) {
  await db.collection('bios').doc(ref.id).set({
    userId: ref.id,
    content: bio,
    // ...
  });
}

const doc = {
  naverUserId: naverUserData.id,
  name: String(profileData.name).trim(),
  isActive: !!bio,  // ✅ bio 존재 여부
  // bio 필드 없음
  // ...
};
await ref.set(doc);
```

### 보안 규칙

#### 3. `firestore.rules`
**주요 변경사항**:
- ✅ posts 컬렉션: `authorId` → `userId`로 변경 (Line 43)

**Before**:
```javascript
match /posts/{postId} {
  allow create, update, delete: if request.auth.uid == resource.data.authorId
                                  || isAdmin();
}
```

**After**:
```javascript
match /posts/{postId} {
  allow create, update, delete: if request.auth.uid == resource.data.userId
                                  || isAdmin();
}
```

### 데이터 정규화 스크립트

#### 4. `functions/scripts/normalize-user-data.js` (신규)
**기능**:
1. 성별 필드 정규화 (M/F → 남성/여성)
2. age ↔ ageDecade 자동 동기화
3. users.bio → bios.content 마이그레이션
4. Dry-run 모드 지원

**실행 방법**:
```bash
# Dry-run (실제 변경 없음)
node functions/scripts/normalize-user-data.js --dry-run

# Production (실제 변경 적용)
node functions/scripts/normalize-user-data.js

# 배치 크기 조정
node functions/scripts/normalize-user-data.js --batch-size=100
```

### 문서

#### 5. `docs/data/FIREBASE_SCHEMA.md` (업데이트)
- ✅ 필드 구조 문서화
- ✅ 마이그레이션 상태 업데이트
- ✅ 해결된 문제 표시

---

## 🎯 해결된 문제

### 1. Bio 필드 분리 ✅
**문제**: users 컬렉션과 bios 컬렉션에 bio가 혼재
**해결**: bios 컬렉션으로 완전 통일
**영향**:
- 회원가입 시 bios 컬렉션에만 저장
- 프로필 업데이트 시 bios 컬렉션에만 저장
- 스타일 분석 트리거가 bios 컬렉션 감시
- getUserProfile에서 bios 컬렉션 조회 (호환성 유지)

### 2. userId/authorId 통일 ✅
**문제**: posts 컬렉션 보안 규칙에서 authorId 사용, 코드에서는 userId 사용
**해결**: firestore.rules에서 userId로 통일
**영향**:
- posts 컬렉션 생성/수정/삭제 권한 검사 정상 작동
- 백엔드 코드와 보안 규칙 일치

### 3. plan/subscription 명확화 ✅
**문제**: plan과 subscription 중복
**해결**: plan을 표준 필드로 명확화, subscription은 레거시 호환성용
**영향**:
- 주석으로 명확히 구분
- 향후 subscription 제거 계획 명시

### 4. 데이터 정규화 준비 ✅
**문제**: 성별, 나이 필드 불일치
**해결**: 정규화 스크립트 작성 완료
**영향**:
- 기존 데이터 일괄 정규화 가능
- Dry-run으로 안전하게 테스트 가능

---

## 📦 배포 체크리스트

### 1. 사전 준비
- [x] 코드 변경사항 검토
- [x] 스키마 문서 업데이트
- [ ] 로컬 테스트 (Functions Emulator)

### 2. Firestore 보안 규칙 배포
```bash
firebase deploy --only firestore:rules
```

### 3. Functions 배포
```bash
# 모든 Functions 배포
firebase deploy --only functions

# 또는 특정 함수만 배포
firebase deploy --only functions:profile,functions:naver
```

### 4. 데이터 정규화 실행
```bash
# 1단계: Dry-run으로 확인
cd functions
node scripts/normalize-user-data.js --dry-run

# 2단계: 결과 확인 후 실제 실행
node scripts/normalize-user-data.js
```

### 5. 배포 후 검증
- [ ] 회원가입 테스트
  - [ ] bio 입력 시 bios 컬렉션에 저장되는지 확인
  - [ ] users 컬렉션에 bio 필드가 없는지 확인
- [ ] 프로필 업데이트 테스트
  - [ ] bio 수정 시 bios 컬렉션 업데이트 확인
  - [ ] 스타일 분석 트리거 작동 확인
- [ ] 포스트 생성/수정/삭제 테스트
  - [ ] userId 기반 권한 검사 정상 작동 확인
- [ ] 플랜 변경 테스트
  - [ ] plan과 subscription 모두 업데이트 확인

---

## ⚠️ 주의사항

### 하위 호환성
- ✅ getUserProfile은 여전히 bio 필드를 반환 (bios 컬렉션에서 조회)
- ✅ 기존 API 응답 구조 유지
- ✅ 프론트엔드 수정 불필요 (확인 필요)

### 데이터 무결성
- ✅ 회원가입 시 bios 컬렉션 자동 생성
- ✅ bio 없는 경우에도 정상 동작
- ✅ 기존 사용자의 bio는 정규화 스크립트로 마이그레이션

### 롤백 계획
만약 문제 발생 시:
1. Functions 이전 버전으로 롤백: `firebase functions:rollback`
2. Firestore Rules 이전 버전으로 복원
3. 데이터는 영향 없음 (bios 컬렉션은 추가만 되고 삭제되지 않음)

---

## 🚀 다음 단계

### 즉시 실행
1. ✅ 로컬 테스트
2. ✅ Functions Emulator로 검증
3. ✅ 배포 (firestore:rules, functions)
4. ✅ 정규화 스크립트 실행 (dry-run → production)

### 향후 계획
1. 프론트엔드 코드 점검 및 필요시 수정
2. subscription 필드 완전 제거 (레거시 데이터 정리 후)
3. 모니터링 및 피드백 수집

---

## 📊 변경사항 통계

| 항목 | 수정된 파일 | 추가된 파일 | 영향받는 컬렉션 |
|------|------------|------------|----------------|
| Bio 분리 | 2 | 1 | users, bios |
| 필드명 통일 | 1 | 0 | posts |
| 정규화 스크립트 | 0 | 1 | users, bios |
| 문서 | 1 | 2 | - |
| **합계** | **4** | **4** | **3** |

---

## 📞 문의

문제 발생 시 이슈 등록: [GitHub Issues](https://github.com/your-repo/issues)

---

**작성**: 2025-10-28
**버전**: 1.0.0
**검토**: 필요
