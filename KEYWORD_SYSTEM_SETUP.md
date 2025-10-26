# 키워드 추천 시스템 v3.0 설정 가이드

## 개요
정치인을 위한 롱테일 SEO 키워드 추천 시스템입니다.
Google Cloud Tasks, Gemini API, Google Trends를 활용한 고품질 키워드 분석을 제공합니다.

## 시스템 아키텍처

### Phase 1: 비동기 처리 (Cloud Tasks)
```
Client
  ↓ requestKeywordAnalysis()
Firebase Function
  ↓ Create Task
Cloud Tasks Queue
  ↓ Trigger
keywordAnalysisWorker()
  ↓ Process
Firestore (결과 저장)
```

### Phase 2: 키워드 분석 파이프라인
```
1. 기본 키워드 수집 (Naver 스크래핑)
   ↓
2. Gemini AI 확장 (30개)
   ↓
3. 각 키워드별 상세 분석
   - SERP 분석 (검색 결과 페이지)
   - 경쟁도 분석
   - Google Trends 트렌드 점수
   - 구체성 점수
   - 정치 관련성 점수
   ↓
4. 최종 점수 계산 (가중 평균)
   ↓
5. 상위 20개 선정
```

### Phase 3: 캐싱 전략
- **전체 분석 캐시**: 12시간 (district + topic)
- **개별 키워드 캐시**: 24시간
- **트렌드 데이터 캐시**: 12시간

## 1. 환경 설정

### 1.1 필수 패키지 설치

```bash
cd functions
npm install @google-cloud/tasks@^5.7.0
npm install google-trends-api@^5.1.0
```

선택적 패키지 (Puppeteer - 폴백용):
```bash
npm install --save-optional puppeteer@^23.0.0
```

### 1.2 Gemini API 키 설정

Firebase Functions 환경변수로 설정:

```bash
firebase functions:secrets:set GEMINI_API_KEY
```

또는 `.env` 파일 (로컬 개발):
```bash
GEMINI_API_KEY=your_gemini_api_key
```

### 1.3 Cloud Tasks 큐 생성

Google Cloud Console에서 Cloud Tasks 큐를 생성합니다:

```bash
gcloud tasks queues create keyword-analysis-queue \
  --location=asia-northeast3 \
  --max-dispatches-per-second=1 \
  --max-concurrent-dispatches=10
```

또는 Firebase Console > Cloud Tasks에서 GUI로 생성 가능합니다.

## 2. Firestore 데이터베이스 구조

### 2.1 Collections

**keyword_tasks** (분석 작업 추적)
```javascript
{
  userId: string,
  district: string,        // 지역구 (예: "강남구")
  topic: string,           // 주제 (예: "교통 개선")
  status: string,          // pending | processing | completed | failed
  progress: number,        // 0-100
  stage: string,           // 현재 작업 단계 설명
  keywords: Array,         // 최종 결과 키워드 배열
  fromCache: boolean,      // 캐시 사용 여부
  createdAt: Timestamp,
  updatedAt: Timestamp,
  completedAt: string
}
```

**keyword_cache** (전체 분석 결과 캐시)
```javascript
{
  keywords: Array,         // 분석 결과
  timestamp: Timestamp,
  cachedAt: string
}
```

**keyword_analysis_cache** (개별 키워드 분석 캐시)
```javascript
{
  analysis: Object,        // 키워드 분석 결과
  timestamp: Timestamp,
  cachedAt: string
}
```

**trend_cache** (Google Trends 캐시)
```javascript
{
  trendScore: number,      // 0-10
  trend: string,           // rising | falling | stable
  data: Array,
  average: number,
  change: number,
  timestamp: Timestamp
}
```

### 2.2 인덱스 생성

Firestore Console에서 다음 인덱스를 생성하세요:

```
Collection: keyword_tasks
Fields: userId (Ascending), createdAt (Descending)
```

## 3. Functions 배포

### 3.1 배포 전 확인사항

- ✅ Gemini API 키 설정 완료
- ✅ Cloud Tasks 큐 생성 완료
- ✅ Firestore 인덱스 생성 완료
- ✅ package.json 의존성 설치 완료

### 3.2 배포 명령어

```bash
# Functions 배포
firebase deploy --only functions:requestKeywordAnalysis,functions:keywordAnalysisWorker,functions:getKeywordAnalysisResult,functions:getKeywordAnalysisHistory
```

전체 Functions 배포:
```bash
firebase deploy --only functions
```

### 3.3 배포 확인

```bash
# Functions 목록 확인
firebase functions:list

# 로그 확인
firebase functions:log --only requestKeywordAnalysis
```

## 4. 클라이언트 사용법

### 4.1 키워드 분석 요청

```javascript
import { httpsCallable } from 'firebase/functions';
import { functions } from './firebase';

const requestKeywordAnalysis = httpsCallable(functions, 'requestKeywordAnalysis');

async function analyzeKeywords(district, topic) {
  try {
    const result = await requestKeywordAnalysis({
      district: '강남구',
      topic: '교통 개선'
    });

    console.log('분석 시작:', result.data);
    // { success: true, taskId: "abc123", status: "processing" }

    const taskId = result.data.taskId;

    // 결과 확인 (폴링)
    checkResult(taskId);

  } catch (error) {
    console.error('분석 요청 실패:', error);
  }
}
```

### 4.2 결과 조회 (폴링)

```javascript
const getKeywordAnalysisResult = httpsCallable(functions, 'getKeywordAnalysisResult');

async function checkResult(taskId) {
  const interval = setInterval(async () => {
    try {
      const result = await getKeywordAnalysisResult({ taskId });

      console.log('진행률:', result.data.progress + '%');

      if (result.data.status === 'completed') {
        clearInterval(interval);
        console.log('분석 완료!');
        console.log('키워드:', result.data.keywords);

        // 상위 20개 키워드 표시
        displayKeywords(result.data.keywords);

      } else if (result.data.status === 'failed') {
        clearInterval(interval);
        console.error('분석 실패');
      }

    } catch (error) {
      console.error('결과 조회 실패:', error);
    }
  }, 3000); // 3초마다 확인
}
```

### 4.3 히스토리 조회

```javascript
const getKeywordAnalysisHistory = httpsCallable(functions, 'getKeywordAnalysisHistory');

async function loadHistory() {
  try {
    const result = await getKeywordAnalysisHistory({ limit: 10 });

    console.log('분석 히스토리:', result.data.history);
    // [{ taskId, district, topic, status, keywordCount, createdAt }, ...]

  } catch (error) {
    console.error('히스토리 조회 실패:', error);
  }
}
```

## 5. 점수 계산 방식

### 5.1 최종 점수 (0-100)

가중 평균으로 계산됩니다:

| 항목 | 가중치 | 설명 |
|-----|--------|------|
| 경쟁도 점수 | 35% | 검색 결과 수가 적을수록 높은 점수 |
| 구체성 점수 | 25% | 단어 수가 많을수록 높은 점수 (롱테일) |
| 블로그 비율 점수 | 20% | 상위 결과 중 블로그 비율이 높을수록 |
| 트렌드 점수 | 10% | Google Trends 상승세 반영 |
| 관련성 점수 | 10% | 지역구/주제 포함 여부 |

### 5.2 등급 시스템

- **S등급**: 85점 이상 (최상급, 적극 추천)
- **A등급**: 70-84점 (상급, 추천)
- **B등급**: 55-69점 (중상급, 고려)
- **C등급**: 40-54점 (중급)
- **D등급**: 39점 이하 (하급)

## 6. 비용 최적화

### 6.1 캐싱 전략

시스템은 3단계 캐싱을 사용합니다:

1. **전체 분석 캐시** (12시간)
   - 같은 district + topic 조합은 12시간 내 재분석하지 않음

2. **개별 키워드 캐시** (24시간)
   - 각 키워드의 SERP, 경쟁도 등은 24시간 재사용

3. **트렌드 캐시** (12시간)
   - Google Trends API 호출 최소화

### 6.2 예상 비용

**무료 할당량 내 처리 가능:**
- Cloud Functions: 200만 호출/월 무료
- Cloud Tasks: 100만 태스크/월 무료
- Firestore: 읽기 5만/일 무료

**외부 API:**
- Google Trends API: 무료 (Rate Limit 있음)
- Gemini API: 분당 15회 무료 (Flash 모델)

**1회 분석 시:**
- Gemini API: 1회 호출
- Google Trends API: 최대 30회 (캐시 미적중 시)
- Naver 스크래핑: 30-60회 (무료)

## 7. 문제 해결

### 7.1 Cloud Tasks 오류

```bash
Error: Queue not found
```

**해결:**
```bash
# 큐 생성 확인
gcloud tasks queues describe keyword-analysis-queue --location=asia-northeast3

# 없으면 생성
gcloud tasks queues create keyword-analysis-queue --location=asia-northeast3
```

### 7.2 Gemini API 오류

```bash
Error: GEMINI_API_KEY not found
```

**해결:**
```bash
firebase functions:secrets:set GEMINI_API_KEY
# API 키 입력 후 Enter
firebase deploy --only functions
```

### 7.3 Google Trends Rate Limit

```bash
Error: Too many requests
```

**해결:**
- 자동으로 2초 간격으로 요청을 분산시킵니다
- 캐시를 활용하여 중복 요청을 방지합니다
- 필요시 `trends-analyzer.js`의 `sleep` 시간을 늘립니다

### 7.4 스크래핑 실패

**현상:**
- 네이버에서 데이터를 가져오지 못함

**해결:**
1. axios/cheerio가 먼저 시도됩니다
2. 실패 시 자동으로 Puppeteer로 폴백됩니다
3. Puppeteer도 실패하면 기본 키워드를 반환합니다

Puppeteer 설치 (옵션):
```bash
cd functions
npm install --save-optional puppeteer
```

## 8. 모니터링

### 8.1 로그 확인

```bash
# 실시간 로그
firebase functions:log --only keywordAnalysisWorker

# 특정 시간대 로그
firebase functions:log --since 1h
```

### 8.2 주요 로그 메시지

- `✅ [Worker] 작업 완료` - 분석 성공
- `❌ [Worker] 작업 실패` - 분석 실패
- `📋 [Worker] 기본 키워드 N개 수집 완료` - 스크래핑 성공
- `🤖 [Worker] 확장 키워드 N개 생성 완료` - Gemini 확장 성공
- `💾 [Cache] 캐시 저장` - 캐싱 동작

### 8.3 성능 메트릭

Firestore Console에서 확인:
- `keyword_tasks` 문서 수 = 총 분석 요청 수
- status=completed 비율 = 성공률
- fromCache=true 비율 = 캐시 적중률

## 9. 확장 가능성

### 9.1 추가 기능 아이디어

- ✅ 키워드 즐겨찾기
- ✅ 키워드 그룹화/카테고리
- ✅ 주간/월간 트렌드 리포트
- ✅ 경쟁자 키워드 분석
- ✅ 블로그 포스트 자동 작성 연동

### 9.2 성능 개선

- **병렬 처리**: 30개 키워드를 배치로 나눠서 병렬 분석
- **증분 업데이트**: 새로운 키워드만 분석
- **ML 모델**: 키워드 품질 예측 모델 학습

## 10. 보안

### 10.1 인증/권한

- 모든 Functions는 Firebase Authentication 필수
- userId 기반 접근 제어
- taskId 소유권 검증

### 10.2 Rate Limiting

- Cloud Tasks를 통한 자연스러운 속도 제한
- 사용자당 1일 N회 제한 (선택적 구현)

## 참고 문서

- [Google Cloud Tasks 문서](https://cloud.google.com/tasks/docs)
- [Gemini API 문서](https://ai.google.dev/docs)
- [Google Trends API](https://www.npmjs.com/package/google-trends-api)
- [Firebase Functions 가이드](https://firebase.google.com/docs/functions)

---

**버전**: 3.0
**최종 업데이트**: 2025-01-26
