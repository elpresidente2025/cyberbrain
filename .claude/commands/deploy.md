# /deploy - 배포 자동화

배포 프로세스를 자동화합니다.

## 사용법

```
/deploy                    # 전체 배포 (functions + hosting)
/deploy functions          # Functions만 배포
/deploy hosting            # Hosting만 배포
/deploy --no-commit        # 커밋 없이 배포만
```

## 실행 절차

### 1단계: 변경사항 확인
```bash
git status
git diff --stat
```

변경사항이 없으면 "변경사항이 없습니다" 출력 후 종료.

### 2단계: 커밋 (--no-commit 옵션이 없을 때)

1. `git log --oneline -3`으로 최근 커밋 스타일 확인
2. 변경사항 분석하여 커밋 메시지 작성
3. 커밋 메시지 형식:
   ```
   <type>: <subject>

   <body>

   🤖 Generated with [Claude Code](https://claude.com/claude-code)

   Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
   ```
4. `git add` 후 `git commit`
5. `git push origin main`

### 3단계: 배포

**전체 배포 (기본)**:
```bash
npm run deploy:functions
npm run deploy:hosting
```

**functions만**:
```bash
npm run deploy:functions
```

**hosting만**:
```bash
npm run deploy:hosting
```

### 4단계: 결과 보고

배포 완료 후 다음 정보 출력:
- 커밋 해시
- 배포된 항목 (Functions/Hosting)
- 확인 링크: https://ai-secretary-6e9c8.web.app

## 주의사항

- settings.local.json은 커밋에서 제외
- 배포 실패 시 에러 메시지와 함께 중단
- Functions 배포는 약 2-3분 소요
