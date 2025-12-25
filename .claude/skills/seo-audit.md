# seo-audit - SEO 점검 스킬

원고의 네이버 SEO 최적화 상태를 점검합니다.

## 트리거

- SEO 관련 코드 변경 시
- editorial.js 또는 seo.js 변경 시
- SEOAgent 변경 시

## 점검 항목

### 1. 글자수

```javascript
SEO_RULES.wordCount = {
  min: 1500,
  max: 2300,
  target: 1700
};
```

| 상태 | 점수 |
|------|------|
| 1500-2300자 | +20점 |
| 1200-1500 또는 2300-2760자 | +12점 |
| 500자 이상 | +5점 |
| 500자 미만 | 0점 |

### 2. 제목

```javascript
SEO_RULES.title = {
  maxLength: 60,
  minLength: 15
};
```

| 상태 | 점수 |
|------|------|
| 30-60자 + 키워드 포함 | +25점 |
| 20-70자 | +8점 |
| 그 외 | 0점 |

### 3. 키워드 밀도

```javascript
SEO_RULES.keywordPlacement.density = {
  optimal: '1.5-2.5%',
  maximum: '3%'
};
```

| 상태 | 판정 |
|------|------|
| 1.5-3% | optimal |
| 0.3-1.5% | acceptable |
| 0.3% 미만 | too_low |
| 3% 초과 | too_high (스팸 위험) |

### 4. 구조

```javascript
SEO_RULES.structure = {
  headings: {
    h2: { count: '1-2개' },
    h3: { count: '2-4개' }
  },
  paragraphs: { count: '6-10개' }
};
```

## 점검 실행

```javascript
const { SEOAgent } = require('./services/agents/seo-agent');

const agent = new SEOAgent();
const result = await agent.run({
  previousResults: {
    ComplianceAgent: { success: true, data: { content } },
    KeywordAgent: { success: true, data: { keywords } }
  },
  userProfile
});

console.log('SEO 점수:', result.data.seoScore);
console.log('개선 제안:', result.data.suggestions);
```

## 출력 예시

```markdown
## SEO 점검 결과

**총점**: 78/100

### 세부 점수
- 글자수 (1850자): 20/20 ✅
- 제목 (45자, 키워드 포함): 25/25 ✅
- 키워드 밀도: 18/25 ⚠️
- 구조: 15/15 ✅
- 메타 설명: 0/15 ❌

### 개선 제안
1. [medium] "청년 일자리" 키워드 사용 빈도가 낮습니다. (2회)
2. [low] 메타 설명이 없습니다.

### 키워드 밀도 상세
| 키워드 | 횟수 | 밀도 | 상태 |
|--------|------|------|------|
| 청년 일자리 | 2회 | 0.8% | too_low |
| 취업 지원 | 4회 | 1.6% | optimal |
```

## 관련 파일

- `functions/services/agents/seo-agent.js`
- `functions/prompts/guidelines/editorial.js`
- `functions/prompts/guidelines/seo.js`
