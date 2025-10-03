# 전뇌비서관 Frontend

정치인 SNS 원고 자동 생성 시스템의 프론트엔드 애플리케이션입니다.

## 🔧 개발 시작하기

### 1. 환경 변수 설정

```bash
# .env.example을 복사하여 .env 파일 생성
cp .env.example .env

# .env 파일을 열어서 Firebase 설정 입력
# Firebase Console에서 프로젝트 설정을 복사하세요
```

### 2. 의존성 설치

```bash
npm install
```

### 3. 개발 서버 실행

```bash
npm run dev
```

개발 서버가 `http://localhost:5173`에서 실행됩니다.

## 📁 프로젝트 구조

```
frontend/
├── src/
│   ├── components/       # React 컴포넌트
│   │   ├── admin/       # 관리자 전용 컴포넌트
│   │   ├── auth/        # 인증 관련 컴포넌트
│   │   ├── common/      # 공통 컴포넌트
│   │   ├── guides/      # 가이드 컴포넌트
│   │   └── loading/     # 로딩 UI 컴포넌트
│   ├── config/          # 설정 파일 (템플릿)
│   ├── hooks/           # Custom React Hooks
│   ├── pages/           # 페이지 컴포넌트
│   ├── services/        # Firebase 서비스 (실제 사용)
│   ├── utils/           # 유틸리티 함수
│   └── App.jsx          # 메인 앱 컴포넌트
├── public/              # 정적 파일
└── vite.config.js       # Vite 설정
```

## ⚠️ 중요: Firebase 설정

### 올바른 파일 수정하기

- ✅ **실제 사용**: `src/services/firebase.js` (환경 변수 사용)
- ❌ **템플릿**: `src/config/firebase.js` (참고용, 수정 불필요)

### 환경 변수 설정 방법

1. **Firebase Console 접속**
   - https://console.firebase.google.com/
   - ai-secretary-6e9c8 프로젝트 선택

2. **설정 복사**
   - 프로젝트 설정 → 일반 → 웹 앱
   - "SDK 설정 및 구성" 클릭
   - Config 값 복사

3. **`.env` 파일에 추가**
   ```env
   VITE_FIREBASE_API_KEY=AIza...
   VITE_FIREBASE_AUTH_DOMAIN=ai-secretary-6e9c8.firebaseapp.com
   VITE_FIREBASE_PROJECT_ID=ai-secretary-6e9c8
   VITE_FIREBASE_STORAGE_BUCKET=ai-secretary-6e9c8.firebasestorage.app
   VITE_FIREBASE_MESSAGING_SENDER_ID=1234567890
   VITE_FIREBASE_APP_ID=1:1234567890:web:abcdef123456
   VITE_USE_EMULATORS=false
   ```

## 🚀 빌드 및 배포

### 프로덕션 빌드

```bash
npm run build
```

빌드된 파일은 `dist/` 디렉토리에 생성됩니다.

### Firebase Hosting 배포

```bash
# Firebase CLI 설치 (한 번만)
npm install -g firebase-tools

# Firebase 로그인
firebase login

# 배포
firebase deploy --only hosting
```

## 🛠️ 주요 기능

### 1. 원고 생성
- 5가지 작법 지원 (감성적/논리적/직설적/비판적/분석적)
- 실시간 뉴스 컨텍스트 자동 조회
- Gemini AI 기반 원고 자동 생성

### 2. 사용자 관리
- Firebase Authentication
- 프로필 관리 (Bio, 페르소나)
- 크레딧 시스템

### 3. 원고 관리
- 생성된 원고 목록 조회
- 원고 수정 및 삭제
- 카테고리별 필터링

## 📦 주요 라이브러리

- **React 18** - UI 프레임워크
- **Vite** - 빌드 도구
- **Firebase** - 백엔드 서비스
- **Material-UI** - UI 컴포넌트
- **React Router** - 라우팅

## 🐛 문제 해결

### Firebase 연결 오류

```bash
# 환경 변수가 올바르게 설정되었는지 확인
cat .env

# 개발 서버 재시작
npm run dev
```

### 빌드 오류

```bash
# node_modules 삭제 후 재설치
rm -rf node_modules
npm install

# 캐시 삭제
npm run build -- --clean
```

## 📝 개발 가이드

### 새 페이지 추가

1. `src/pages/` 에 컴포넌트 생성
2. `src/App.jsx`에 라우트 추가

### 새 컴포넌트 추가

1. 적절한 디렉토리에 컴포넌트 생성
2. `index.js`에서 export (있는 경우)

### API 호출

```javascript
import { functions } from '../services/firebase';
import { httpsCallable } from 'firebase/functions';

const generatePosts = httpsCallable(functions, 'generatePosts');
const result = await generatePosts({ topic: '주제' });
```

## 🔒 보안

- API 키는 `.env` 파일에 저장 (Git에 커밋 금지)
- `.env` 파일은 `.gitignore`에 포함됨
- Firebase Rules로 데이터 접근 제어

## 📄 라이선스

Copyright © 2025 전뇌비서관 팀
