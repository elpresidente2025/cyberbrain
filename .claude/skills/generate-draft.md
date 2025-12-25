# generate-draft - 원고 생성 테스트 스킬

원고 생성 기능을 E2E로 테스트합니다.

## 트리거

- 원고 생성 관련 코드 변경 시
- Multi-Agent 시스템 변경 시
- 프롬프트 템플릿 변경 시

## 테스트 시나리오

### 시나리오 1: 기본 원고 생성

```javascript
// 테스트 입력
{
  topic: "지역 경제 활성화",
  category: "policy",
  userProfile: { /* 표준 프로필 */ },
  targetWordCount: 1700
}

// 기대 결과
- 글자수: 1500-2300자
- 구조: 도입-본론-결론
- 선거법: 위반 없음
```

### 시나리오 2: 원외 인사 (준비 상태)

```javascript
// 테스트 입력
{
  userProfile: {
    status: "준비",
    politicalExperience: "정치 신인",
    position: "예비후보"
  }
}

// 기대 결과
- "의원" 호칭 사용 안 함
- 공약/투표 관련 표현 없음
- 경고 문구 포함
```

### 시나리오 3: 타 지역 주제

```javascript
// 테스트 입력
{
  topic: "부산 북항 재개발",
  userProfile: {
    regionMetro: "서울특별시",
    regionLocal: "강남구"
  }
}

// 기대 결과
- regionHint 프롬프트 포함
- 외부 관점으로 작성
```

### 시나리오 4: 자녀 없는 사용자

```javascript
// 테스트 입력
{
  topic: "교육 정책",
  userProfile: {
    familyStatus: "미혼"
  }
}

// 기대 결과
- "우리 아이", "자녀" 언급 없음
- 환각 검출 시 자동 제거
```

## 검증 체크리스트

- [ ] API 응답 200 OK
- [ ] drafts.content 존재
- [ ] drafts.title 존재
- [ ] wordCount 1500-2300 범위
- [ ] 선거법 위반 표현 없음
- [ ] 프로필과 일치하는 호칭/표현

## 실행 방법

```bash
# Firebase 에뮬레이터로 로컬 테스트
cd E:/ai-secretary/functions
firebase emulators:start --only functions

# 별도 터미널에서 테스트 호출
curl -X POST http://localhost:5001/ai-secretary-6e9c8/asia-northeast3/generatePosts \
  -H "Content-Type: application/json" \
  -d '{"data": {...}}'
```

## 관련 파일

- `functions/handlers/posts.js`
- `functions/services/agents/pipeline-helper.js`
- `functions/prompts/templates/*.js`
