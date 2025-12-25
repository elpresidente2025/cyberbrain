# pre-commit - 커밋 전 검증 훅

커밋 전에 자동으로 코드 품질을 검증합니다.

## 검증 항목

### 1. 구문 검사 (필수)

```bash
# Functions 구문 체크
node --check functions/handlers/posts.js
node --check functions/services/agents/*.js

# 에러 시 커밋 차단
```

### 2. 민감 정보 검사 (필수)

```bash
# 검색 패턴
- API_KEY=
- SECRET=
- PASSWORD=
- .env 파일 변경

# 발견 시 경고 및 확인 요청
```

### 3. 콘솔 로그 검사 (경고)

```bash
# 패턴
- console.log('debug
- console.log("debug
- // TODO:
- // FIXME:

# 발견 시 경고 (커밋은 허용)
```

### 4. 대용량 파일 검사 (필수)

```bash
# 1MB 이상 파일 검사
# node_modules, dist 제외

# 발견 시 커밋 차단
```

## 설정 방법

### settings.json에 추가

```json
{
  "hooks": {
    "pre-commit": {
      "enabled": true,
      "checks": ["syntax", "secrets", "console-logs", "large-files"],
      "blockOnError": true
    }
  }
}
```

### 또는 Git Hooks 사용

```bash
# .git/hooks/pre-commit
#!/bin/sh

# 구문 검사
node --check functions/handlers/posts.js || exit 1

# 민감 정보 검사
if git diff --cached --name-only | xargs grep -l "API_KEY=\|SECRET=" 2>/dev/null; then
  echo "⚠️ 민감 정보가 포함된 것 같습니다. 확인해주세요."
  exit 1
fi

echo "✅ pre-commit 검사 통과"
```

## 예외 처리

```bash
# 검사 건너뛰기 (긴급 상황에만)
git commit --no-verify -m "hotfix: 긴급 수정"
```

## 실행 예시

```
$ git commit -m "feat: 새 기능"

🔍 pre-commit 검사 시작...

[1/4] 구문 검사...
  ✅ functions/handlers/posts.js - OK
  ✅ functions/services/agents/writer-agent.js - OK

[2/4] 민감 정보 검사...
  ✅ 민감 정보 없음

[3/4] 콘솔 로그 검사...
  ⚠️ functions/handlers/posts.js:125 - console.log 발견
  (경고만, 계속 진행)

[4/4] 대용량 파일 검사...
  ✅ 대용량 파일 없음

✅ pre-commit 검사 완료

[main abc1234] feat: 새 기능
 3 files changed, 45 insertions(+)
```

## 차단 시 메시지

```
$ git commit -m "feat: 새 기능"

🔍 pre-commit 검사 시작...

[1/4] 구문 검사...
  ❌ functions/handlers/posts.js - 구문 오류!
     SyntaxError: Unexpected token at line 125

❌ 커밋이 차단되었습니다.
   위 오류를 수정한 후 다시 시도해주세요.

   검사를 건너뛰려면: git commit --no-verify
```
