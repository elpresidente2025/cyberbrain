# CyberBrain

전자두뇌비서관 서비스 운영 저장소입니다.

Naver login integration is documented in `docs/NAVER_LOGIN.md`.
UTF-8 console handling for Windows PowerShell is documented in `docs/UTF8_CONSOLE.md`.

## 문서 구조

- 사업 문서: `docs/business/`
- 데이터 스키마: `docs/data/FIREBASE_SCHEMA.md`
- 운영 문서: `docs/ops/`
- 아키텍처 변경 요약: `docs/architecture/MIGRATION_SUMMARY.md`

## 루트 스크립트

- `npm run dev`: 프론트엔드와 Functions 에뮬레이터 동시 실행
- `npm run build`: 프론트엔드 빌드
- `npm run lint`: Functions lint 실행
