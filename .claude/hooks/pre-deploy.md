# pre-deploy - 배포 전 검증 훅

배포 전에 자동으로 안정성을 검증합니다.

## 검증 항목

### 1. 빌드 테스트 (필수)

```bash
# Frontend 빌드
cd frontend && npm run build

# 빌드 실패 시 배포 차단
```

### 2. Functions 구문 검사 (필수)

```bash
# 모든 핸들러 파일 검사
node --check functions/index.js
node --check functions/handlers/*.js
node --check functions/services/**/*.js
```

### 3. 환경 변수 확인 (경고)

```bash
# 필수 환경 변수 존재 여부
- GEMINI_API_KEY
- NAVER_CLIENT_ID
- NAVER_CLIENT_SECRET

# 누락 시 경고 (배포는 허용)
```

### 4. 미커밋 변경사항 확인 (필수)

```bash
# git status로 확인
# 변경사항이 있으면 배포 차단
```

### 5. 브랜치 확인 (경고)

```bash
# main 브랜치가 아니면 경고
# 다른 브랜치에서 배포 시 확인 요청
```

## 설정 방법

### deploy.js에 통합

```javascript
// deploy.js 시작 부분에 추가
async function preDeployCheck() {
  console.log('🔍 배포 전 검증 시작...');

  // 1. 빌드 테스트
  const buildResult = await exec('npm run build');
  if (buildResult.error) {
    console.error('❌ 빌드 실패');
    process.exit(1);
  }

  // 2. 구문 검사
  const syntaxCheck = await exec('node --check functions/index.js');
  if (syntaxCheck.error) {
    console.error('❌ 구문 오류 발견');
    process.exit(1);
  }

  // 3. 미커밋 변경사항
  const status = await exec('git status --porcelain');
  if (status.stdout.trim()) {
    console.warn('⚠️ 커밋되지 않은 변경사항이 있습니다');
    // 확인 요청 또는 차단
  }

  console.log('✅ 배포 전 검증 완료');
}
```

## 실행 예시

```
$ npm run deploy

🔍 배포 전 검증 시작...

[1/5] 빌드 테스트...
  ⏳ Frontend 빌드 중...
  ✅ 빌드 성공 (48.5s)

[2/5] Functions 구문 검사...
  ✅ index.js - OK
  ✅ handlers/posts.js - OK
  ✅ services/agents/*.js - OK

[3/5] 환경 변수 확인...
  ✅ GEMINI_API_KEY - 설정됨
  ⚠️ NAVER_CLIENT_ID - 로컬 미설정 (Functions Config에는 있음)

[4/5] 미커밋 변경사항...
  ✅ 작업 디렉토리 깨끗함

[5/5] 브랜치 확인...
  ✅ main 브랜치

✅ 배포 전 검증 완료

🚀 Firebase 배포 시작...
```

## 차단 시 메시지

```
$ npm run deploy

🔍 배포 전 검증 시작...

[1/5] 빌드 테스트...
  ❌ 빌드 실패!

  Error: Module not found: 'missing-package'
  at frontend/src/pages/GeneratePage.jsx:15

❌ 배포가 차단되었습니다.
   빌드 오류를 수정한 후 다시 시도해주세요.
```

## 강제 배포 (긴급 상황)

```bash
# 검증 건너뛰기
npm run deploy -- --skip-checks

# 또는 직접 Firebase CLI
firebase deploy --only functions
```

## 관련 파일

- `deploy.js` - 배포 스크립트
- `package.json` - 배포 명령어 정의
