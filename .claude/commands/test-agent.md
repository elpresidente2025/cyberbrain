# /test-agent - Multi-Agent 시스템 테스트

Multi-Agent 파이프라인을 로컬에서 테스트합니다.

## 사용법

```
/test-agent                     # 전체 파이프라인 테스트
/test-agent keyword             # KeywordAgent만 테스트
/test-agent writer              # WriterAgent만 테스트
/test-agent compliance          # ComplianceAgent만 테스트
/test-agent seo                 # SEOAgent만 테스트
```

## 테스트 시나리오

### 기본 테스트 데이터

```javascript
const testContext = {
  topic: "청년 일자리 정책",
  category: "policy",
  userProfile: {
    name: "테스트 의원",
    regionMetro: "서울특별시",
    regionLocal: "강남구",
    position: "국회의원",
    party: "더불어민주당",
    status: "현역",
    politicalExperience: "초선",
    familyStatus: "기혼(자녀 있음)"
  },
  memoryContext: "",
  instructions: "MZ세대 청년들의 취업난 해결 방안",
  newsContext: "",
  keywords: ["청년 일자리", "취업 지원"],
  targetWordCount: 1700
};
```

### 테스트 실행 방법

```bash
cd E:/ai-secretary/functions
node -e "
const { generateWithMultiAgent } = require('./services/agents/pipeline-helper');
// ... 테스트 코드
"
```

## 검증 항목

### KeywordAgent
- [ ] 키워드 3-5개 추출
- [ ] primary 키워드 선정
- [ ] 관련성 점수 포함

### WriterAgent
- [ ] 글자수 1500-2300자
- [ ] 도입-본론-결론 구조
- [ ] 키워드 자연스럽게 포함
- [ ] 원외 인사 경고 문구 (해당 시)

### ComplianceAgent
- [ ] 선거법 위반 표현 검출
- [ ] 자동 치환 수행
- [ ] 환각(자녀 언급 등) 검출
- [ ] passed/issues/replacements 반환

### SEOAgent
- [ ] 제목 60자 이내
- [ ] 키워드 밀도 1.5-2.5%
- [ ] SEO 점수 계산
- [ ] 개선 제안 생성

## 예상 출력

```
🤖 [MultiAgent] 전체 파이프라인 시작
▶️ [Orchestrator] KeywordAgent 실행 시작
✅ [Orchestrator] KeywordAgent 완료 (1200ms)
▶️ [Orchestrator] WriterAgent 실행 시작
✅ [Orchestrator] WriterAgent 완료 (45000ms)
▶️ [Orchestrator] ComplianceAgent 실행 시작
✅ [Orchestrator] ComplianceAgent 완료 (800ms)
▶️ [Orchestrator] SEOAgent 실행 시작
✅ [Orchestrator] SEOAgent 완료 (500ms)
🎭 [Orchestrator] 파이프라인 완료 (47500ms)

결과:
- 글자수: 1850자
- SEO 점수: 78점
- 검수 통과: true
- 키워드: ["청년 일자리", "취업 지원", "MZ세대"]
```

## 에러 디버깅

테스트 실패 시 확인할 사항:
1. Firestore 연결 (에뮬레이터 또는 실제)
2. Gemini API 키 설정
3. templates import 경로
4. guidelines import 경로
