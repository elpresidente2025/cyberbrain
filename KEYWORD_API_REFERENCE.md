# 키워드 추천 시스템 v3.0 API 레퍼런스

## 목차
1. [requestKeywordAnalysis](#requestkeywordanalysis) - 키워드 분석 요청
2. [getKeywordAnalysisResult](#getkeywordanalysisresult) - 분석 결과 조회
3. [getKeywordAnalysisHistory](#getkeywordanalysishistory) - 분석 히스토리 조회

---

## requestKeywordAnalysis

키워드 분석을 비동기로 요청합니다.

### 함수 타입
`httpsCallable`

### 요청 파라미터

```typescript
interface RequestParams {
  district: string;  // 지역구 이름 (필수)
  topic: string;     // 정책 주제 (필수)
}
```

**예시:**
```javascript
{
  district: "강남구",
  topic: "교통 개선"
}
```

### 응답

```typescript
interface Response {
  success: boolean;
  taskId: string;           // 작업 추적 ID
  status: 'processing';     // 항상 processing
  message: string;          // 안내 메시지
}
```

**성공 응답 예시:**
```javascript
{
  success: true,
  taskId: "abc123xyz",
  status: "processing",
  message: "키워드 분석이 시작되었습니다. 잠시 후 결과를 확인하세요."
}
```

### 에러

| 코드 | 메시지 | 설명 |
|------|--------|------|
| `invalid-argument` | 지역구와 주제는 필수입니다 | district 또는 topic 누락 |
| `unauthenticated` | 인증이 필요합니다 | 로그인하지 않은 상태 |
| `internal` | 분석 요청 실패: ... | 서버 내부 오류 |

### 사용 예시

```javascript
import { httpsCallable } from 'firebase/functions';
import { functions } from './firebase';

const requestKeywordAnalysis = httpsCallable(
  functions,
  'requestKeywordAnalysis'
);

async function startAnalysis() {
  try {
    const result = await requestKeywordAnalysis({
      district: '강남구',
      topic: '교통 개선'
    });

    console.log('Task ID:', result.data.taskId);
    return result.data.taskId;

  } catch (error) {
    console.error('분석 요청 실패:', error.code, error.message);
  }
}
```

---

## getKeywordAnalysisResult

특정 작업의 분석 결과를 조회합니다.

### 함수 타입
`httpsCallable`

### 요청 파라미터

```typescript
interface RequestParams {
  taskId: string;  // 작업 ID (필수)
}
```

**예시:**
```javascript
{
  taskId: "abc123xyz"
}
```

### 응답

```typescript
interface KeywordAnalysis {
  keyword: string;
  finalScore: number;       // 0-100
  grade: 'S' | 'A' | 'B' | 'C' | 'D';
  scores: {
    competitionScore: number;   // 0-10
    specificityScore: number;   // 0-10
    blogRatioScore: number;     // 0-10
    trendScore: number;         // 0-10
    relevanceScore: number;     // 0-10
    serpScore: number;          // 0-10
  };
  reasons: string[];            // 추천 이유
  metadata: {
    resultCount: number;
    blogRatio: number;
    officialRatio: number;
  };
}

interface Response {
  success: boolean;
  taskId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;             // 0-100
  keywords: KeywordAnalysis[];  // status=completed일 때만
  fromCache: boolean;
  createdAt: string;            // ISO 8601
  completedAt?: string;         // ISO 8601
}
```

**진행 중 응답 예시:**
```javascript
{
  success: true,
  taskId: "abc123xyz",
  status: "processing",
  progress: 65,
  keywords: [],
  fromCache: false,
  createdAt: "2025-01-26T10:30:00.000Z"
}
```

**완료 응답 예시:**
```javascript
{
  success: true,
  taskId: "abc123xyz",
  status: "completed",
  progress: 100,
  keywords: [
    {
      keyword: "강남구 교통 개선 주민 의견",
      finalScore: 87,
      grade: "S",
      scores: {
        competitionScore: 9,
        specificityScore: 9,
        blogRatioScore: 8,
        trendScore: 7,
        relevanceScore: 10,
        serpScore: 8
      },
      reasons: [
        "🎯 경쟁이 낮아 상위 노출 가능성이 높습니다",
        "📝 구체적인 롱테일 키워드로 타겟팅이 명확합니다",
        "🏛️ 정치/지역 관련성이 매우 높습니다",
        "⭐ 최상위 등급 키워드입니다"
      ],
      metadata: {
        resultCount: 450,
        blogRatio: 0.6,
        officialRatio: 0.2
      }
    },
    // ... 19개 더
  ],
  fromCache: false,
  createdAt: "2025-01-26T10:30:00.000Z",
  completedAt: "2025-01-26T10:32:15.000Z"
}
```

### 에러

| 코드 | 메시지 | 설명 |
|------|--------|------|
| `invalid-argument` | taskId가 필요합니다 | taskId 누락 |
| `unauthenticated` | 인증이 필요합니다 | 로그인하지 않은 상태 |
| `not-found` | 작업을 찾을 수 없습니다 | 잘못된 taskId |
| `permission-denied` | 권한이 없습니다 | 다른 사용자의 작업 조회 시도 |

### 사용 예시 (폴링)

```javascript
const getKeywordAnalysisResult = httpsCallable(
  functions,
  'getKeywordAnalysisResult'
);

async function pollResult(taskId) {
  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const result = await getKeywordAnalysisResult({ taskId });
        const { status, progress, keywords } = result.data;

        console.log(`진행률: ${progress}%`);

        if (status === 'completed') {
          clearInterval(interval);
          resolve(keywords);
        } else if (status === 'failed') {
          clearInterval(interval);
          reject(new Error('분석 실패'));
        }

      } catch (error) {
        clearInterval(interval);
        reject(error);
      }
    }, 3000); // 3초마다 확인
  });
}

// 사용
const keywords = await pollResult(taskId);
console.log('분석 완료:', keywords);
```

---

## getKeywordAnalysisHistory

사용자의 키워드 분석 히스토리를 조회합니다.

### 함수 타입
`httpsCallable`

### 요청 파라미터

```typescript
interface RequestParams {
  limit?: number;  // 조회 개수 (선택, 기본값: 10, 최대: 50)
}
```

**예시:**
```javascript
{
  limit: 20
}
```

### 응답

```typescript
interface HistoryItem {
  taskId: string;
  district: string;
  topic: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  progress: number;
  keywordCount: number;
  fromCache: boolean;
  createdAt: string;      // ISO 8601
  completedAt?: string;   // ISO 8601
}

interface Response {
  success: boolean;
  history: HistoryItem[];
  total: number;
}
```

**응답 예시:**
```javascript
{
  success: true,
  history: [
    {
      taskId: "abc123xyz",
      district: "강남구",
      topic: "교통 개선",
      status: "completed",
      progress: 100,
      keywordCount: 20,
      fromCache: false,
      createdAt: "2025-01-26T10:30:00.000Z",
      completedAt: "2025-01-26T10:32:15.000Z"
    },
    {
      taskId: "def456uvw",
      district: "서초구",
      topic: "환경 보호",
      status: "completed",
      progress: 100,
      keywordCount: 20,
      fromCache: true,
      createdAt: "2025-01-25T14:20:00.000Z",
      completedAt: "2025-01-25T14:20:05.000Z"
    }
  ],
  total: 2
}
```

### 에러

| 코드 | 메시지 | 설명 |
|------|--------|------|
| `unauthenticated` | 인증이 필요합니다 | 로그인하지 않은 상태 |
| `internal` | 히스토리 조회 실패: ... | 서버 내부 오류 |

### 사용 예시

```javascript
const getKeywordAnalysisHistory = httpsCallable(
  functions,
  'getKeywordAnalysisHistory'
);

async function loadHistory() {
  try {
    const result = await getKeywordAnalysisHistory({ limit: 10 });

    console.log('총 분석 횟수:', result.data.total);

    result.data.history.forEach(item => {
      console.log(`${item.district} - ${item.topic}`);
      console.log(`  상태: ${item.status}`);
      console.log(`  키워드: ${item.keywordCount}개`);
      console.log(`  날짜: ${new Date(item.createdAt).toLocaleString()}`);
    });

  } catch (error) {
    console.error('히스토리 조회 실패:', error);
  }
}
```

---

## 전체 워크플로우 예시

```javascript
import { httpsCallable } from 'firebase/functions';
import { functions } from './firebase';

// 1. 분석 요청
async function analyzeKeywords(district, topic) {
  const requestAnalysis = httpsCallable(functions, 'requestKeywordAnalysis');

  const result = await requestAnalysis({ district, topic });
  const taskId = result.data.taskId;

  console.log('분석 시작:', taskId);

  // 2. 결과 대기 (폴링)
  const keywords = await waitForResult(taskId);

  // 3. 결과 표시
  displayKeywords(keywords);

  return keywords;
}

// 결과 폴링
async function waitForResult(taskId) {
  const getResult = httpsCallable(functions, 'getKeywordAnalysisResult');

  return new Promise((resolve, reject) => {
    const interval = setInterval(async () => {
      try {
        const result = await getResult({ taskId });
        const { status, progress, keywords } = result.data;

        // UI 업데이트
        updateProgressBar(progress);

        if (status === 'completed') {
          clearInterval(interval);
          resolve(keywords);
        } else if (status === 'failed') {
          clearInterval(interval);
          reject(new Error('분석 실패'));
        }

      } catch (error) {
        clearInterval(interval);
        reject(error);
      }
    }, 3000);
  });
}

// 키워드 표시
function displayKeywords(keywords) {
  console.log('=== 추천 키워드 TOP 20 ===\n');

  keywords.forEach((kw, index) => {
    console.log(`${index + 1}. ${kw.keyword}`);
    console.log(`   점수: ${kw.finalScore}/100 (${kw.grade}등급)`);
    console.log(`   이유: ${kw.reasons.join(', ')}`);
    console.log('');
  });
}

// 사용
analyzeKeywords('강남구', '교통 개선')
  .then(keywords => {
    console.log('분석 완료!', keywords.length, '개 키워드');
  })
  .catch(error => {
    console.error('오류:', error);
  });
```

---

## React 컴포넌트 예시

```jsx
import React, { useState, useEffect } from 'react';
import { httpsCallable } from 'firebase/functions';
import { functions } from './firebase';

function KeywordAnalyzer() {
  const [district, setDistrict] = useState('');
  const [topic, setTopic] = useState('');
  const [taskId, setTaskId] = useState(null);
  const [progress, setProgress] = useState(0);
  const [keywords, setKeywords] = useState([]);
  const [loading, setLoading] = useState(false);

  const startAnalysis = async () => {
    setLoading(true);

    try {
      const requestAnalysis = httpsCallable(functions, 'requestKeywordAnalysis');
      const result = await requestAnalysis({ district, topic });

      setTaskId(result.data.taskId);

    } catch (error) {
      console.error('분석 요청 실패:', error);
      alert('분석 요청에 실패했습니다.');
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!taskId) return;

    const interval = setInterval(async () => {
      try {
        const getResult = httpsCallable(functions, 'getKeywordAnalysisResult');
        const result = await getResult({ taskId });

        const { status, progress: p, keywords: kw } = result.data;

        setProgress(p);

        if (status === 'completed') {
          setKeywords(kw);
          setLoading(false);
          clearInterval(interval);
        } else if (status === 'failed') {
          alert('분석에 실패했습니다.');
          setLoading(false);
          clearInterval(interval);
        }

      } catch (error) {
        console.error('결과 조회 실패:', error);
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [taskId]);

  return (
    <div>
      <h2>키워드 분석기</h2>

      <input
        value={district}
        onChange={(e) => setDistrict(e.target.value)}
        placeholder="지역구"
      />

      <input
        value={topic}
        onChange={(e) => setTopic(e.target.value)}
        placeholder="주제"
      />

      <button onClick={startAnalysis} disabled={loading}>
        {loading ? '분석 중...' : '분석 시작'}
      </button>

      {loading && (
        <div>
          <progress value={progress} max={100} />
          <span>{progress}%</span>
        </div>
      )}

      {keywords.length > 0 && (
        <div>
          <h3>추천 키워드 ({keywords.length}개)</h3>
          <ul>
            {keywords.map((kw, i) => (
              <li key={i}>
                <strong>{kw.keyword}</strong>
                <span> - {kw.finalScore}점 ({kw.grade}등급)</span>
                <ul>
                  {kw.reasons.map((reason, j) => (
                    <li key={j}>{reason}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default KeywordAnalyzer;
```

---

**버전**: 3.0
**최종 업데이트**: 2025-01-26
