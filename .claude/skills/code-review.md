# code-review - 코드 리뷰 스킬

변경된 코드의 품질을 자동으로 점검합니다.

## 트리거

- PR 생성 시
- 주요 기능 구현 완료 시
- 커밋 전 검토 요청 시

## 리뷰 체크리스트

### 1. 보안

- [ ] SQL Injection 위험 없음
- [ ] XSS 취약점 없음
- [ ] 민감 정보 하드코딩 없음 (API 키, 비밀번호)
- [ ] 인증/권한 검사 적절함

### 2. 에러 처리

- [ ] try-catch 적절히 사용
- [ ] 에러 메시지가 사용자 친화적
- [ ] 에러 로깅 포함
- [ ] 폴백 처리 존재

### 3. 성능

- [ ] N+1 쿼리 없음
- [ ] 불필요한 반복문 없음
- [ ] 메모리 누수 위험 없음
- [ ] 적절한 캐싱 사용

### 4. 가독성

- [ ] 함수/변수명이 명확함
- [ ] 복잡한 로직에 주석 있음
- [ ] 함수가 단일 책임 원칙 준수
- [ ] 코드 중복 없음

### 5. 프로젝트 특화

- [ ] 선거법 관련 코드 → ComplianceAgent 연동 확인
- [ ] 원고 생성 → 글자수/키워드 규칙 준수
- [ ] Firestore 쿼리 → 인덱스 필요 여부 확인
- [ ] Cloud Functions → 타임아웃 설정 확인

## 리뷰 실행 방법

```bash
# 변경된 파일 확인
git diff --name-only HEAD~1

# 각 파일별 diff 확인
git diff HEAD~1 -- <파일경로>
```

## 자동 점검 항목

### JavaScript/Node.js

```javascript
// ❌ 나쁜 예: 동기 파일 읽기
const data = fs.readFileSync(path);

// ✅ 좋은 예: 비동기 파일 읽기
const data = await fs.promises.readFile(path);
```

```javascript
// ❌ 나쁜 예: console.log 남김
console.log('debug:', data);

// ✅ 좋은 예: 구조화된 로깅
console.log('📊 [ModuleName] 처리 완료:', { count: data.length });
```

### React/Frontend

```javascript
// ❌ 나쁜 예: 의존성 배열 누락
useEffect(() => {
  fetchData();
});

// ✅ 좋은 예: 의존성 명시
useEffect(() => {
  fetchData();
}, [userId]);
```

## 출력 형식

```markdown
## 코드 리뷰 결과

**변경 파일**: 5개
**총 라인**: +245 / -120

### 이슈 발견 (3건)

1. **[보안]** `posts.js:125`
   - 사용자 입력 검증 누락
   - 권장: sanitizeInput() 추가

2. **[성능]** `profile-loader.js:45`
   - Firestore 쿼리가 루프 안에서 실행됨
   - 권장: 배치 쿼리로 변경

3. **[가독성]** `seo-agent.js:200`
   - 매직 넘버 사용 (400)
   - 권장: 상수로 추출

### 좋은 점
- 에러 처리가 일관됨
- 로깅이 잘 구조화됨
- 테스트 커버리지 유지됨
```

## 관련 도구

- ESLint: `npm run lint`
- 타입 체크: 해당 없음 (순수 JS)
- 테스트: `npm test` (있는 경우)
