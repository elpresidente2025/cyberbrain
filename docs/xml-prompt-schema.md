# XML Prompt Schema v1.0

전뇌비서관 프롬프트 시스템을 위한 XML 스키마 설계 문서입니다.

## 설계 원칙

1. **의미적 명확성**: 태그명이 곧 역할을 설명
2. **우선순위 속성화**: `priority="critical|high|medium|low"`로 중요도 표현
3. **중첩 가능 구조**: 복합 지시사항 표현 가능
4. **간결성**: 불필요한 중첩 최소화

---

## 1. 루트 요소

```xml
<prompt type="writer|editor|title|sns" version="1.0">
  <!-- 모든 섹션이 여기에 포함 -->
</prompt>
```

---

## 2. 핵심 섹션 태그

### 2.1 지시사항 섹션 (`<instructions>`)

```xml
<instructions priority="critical|high|medium">
  <rule>규칙 내용</rule>
  <rule type="must">필수 규칙</rule>
  <rule type="must-not">금지 규칙</rule>
</instructions>
```

**변환 예시**:

Before (현재):
```
╔═══════════════════════════════════════════════════════════════╗
║  🔍 [CRITICAL] 노출 희망 검색어 - SEO 필수 삽입                ║
╚═══════════════════════════════════════════════════════════════╝

[필수 규칙]
✅ 각 검색어 최소 2회 포함
❌ 검색어 나열 금지
```

After (XML):
```xml
<instructions priority="critical" label="노출 희망 검색어 - SEO 필수 삽입">
  <rule type="must">각 검색어 최소 2회 포함</rule>
  <rule type="must">도입부(첫 문단)에 1회 포함</rule>
  <rule type="must">문맥에 자연스럽게 녹일 것</rule>
  <rule type="must-not">검색어 나열 금지</rule>
  <rule type="must-not">한 문장에 여러 검색어 몰아넣기 금지</rule>
</instructions>
```

---

### 2.2 컨텍스트 오버라이드 (`<context-override>`)

AI 모델의 기존 지식을 덮어쓰는 사실 정보

```xml
<context-override priority="critical">
  <fact key="현직 대통령">이재명 (2025년 취임)</fact>
  <fact key="여당">더불어민주당 (국회 과반)</fact>
  <fact key="야당">국민의힘, 조국혁신당 등</fact>
  <fact key="윤석열 상태">2024년 12월 계엄 선포로 탄핵, 현재 재판 중</fact>
</context-override>
```

---

### 2.3 화자 정체성 (`<speaker>`)

```xml
<speaker>
  <identity>{authorBio}</identity>
  <party>더불어민주당</party>
  <role>여당</role>

  <rules>
    <rule>"저는", "제가"는 오직 화자 자신만 지칭</rule>
    <rule>타인은 관찰/평가 대상(3인칭)</rule>
  </rules>
</speaker>
```

---

### 2.4 톤 매트릭스 (`<tone-matrix>`)

```xml
<tone-matrix>
  <case id="type-a" trigger="헌정 파괴, 중범죄, 사법 리스크">
    <stance>범죄(원인)는 비판하되, 처벌(결과)은 환영</stance>
    <tone>냉철, 엄중, 정의로움</tone>
    <keywords>사필귀정, 엄중한 심판, 법치주의 실현</keywords>
  </case>

  <case id="type-b" trigger="소신 발언, 내부 비판, 원칙 준수">
    <stance>1~2문장만 인정 후, 즉시 자기PR로 복귀</stance>
    <tone>절제된 인정</tone>
    <keywords>높이 평가한다, 주목할 만하다</keywords>
  </case>

  <case id="type-c" trigger="정쟁, 정책 차이, 단순 행보">
    <stance>정중하지만 날선 비판과 대안 제시</stance>
    <tone>논리적 비판, 견제</tone>
    <keywords>유감입니다, 재고해야 합니다</keywords>
  </case>

  <case id="type-d" trigger="재난, 사고, 사망, 국가적 비극">
    <stance>정쟁 중단, 무조건적 위로</stance>
    <tone>애도, 슬픔, 위로</tone>
    <keywords>참담한 심정, 깊은 애도</keywords>
  </case>
</tone-matrix>
```

---

### 2.5 글쓰기 가이드 (`<writing-guide>`)

```xml
<writing-guide>
  <structure type="5-step">
    <step order="1" name="서론">인사, 문제 제기, 공감 형성</step>
    <step order="2" name="본론1" heading="required">첫 번째 핵심 주장</step>
    <step order="3" name="본론2" heading="required">두 번째 핵심 주장</step>
    <step order="4" name="본론3" heading="required">세 번째 핵심 주장</step>
    <step order="5" name="결론">요약, 다짐, 마무리 인사</step>
  </structure>

  <style>
    <format>HTML (p, h2, h3, ul, ol, strong)</format>
    <tone>합쇼체 존댓말</tone>
    <word-count target="2000" min="1700" max="2300"/>
  </style>
</writing-guide>
```

---

### 2.6 블랙리스트 (`<blacklist>`)

```xml
<blacklist category="LLM 특유 표현">
  <group name="결론 클리셰">
    <banned>결론적으로</banned>
    <banned>요약하자면</banned>
    <banned>정리하면</banned>
  </group>

  <group name="과도한 접속어">
    <banned>또한</banned>
    <banned>한편</banned>
    <banned>더 나아가</banned>
  </group>

  <group name="완곡 표현">
    <banned>~것 같습니다</banned>
    <banned>~로 보입니다</banned>
    <banned>~라고 볼 수 있습니다</banned>
  </group>
</blacklist>
```

---

### 2.7 화이트리스트 / 권장 표현 (`<whitelist>`)

```xml
<whitelist category="권장 표현">
  <group name="단정형 종결">
    <allowed>~입니다</allowed>
    <allowed>~합니다</allowed>
    <allowed>~했습니다</allowed>
  </group>

  <group name="약속형 공약">
    <allowed>~하겠습니다</allowed>
    <allowed>추진합니다</allowed>
    <allowed>실현합니다</allowed>
  </group>
</whitelist>
```

---

### 2.8 예시 (`<examples>`)

```xml
<examples>
  <example type="good" label="올바른 결론 구조">
    <text>이 정책으로 지역 경제가 살아납니다. 청년 일자리 1,200개를 만들겠습니다.</text>
  </example>

  <example type="bad" label="금지된 구조">
    <text>결론적으로, 이 정책은 중요한 것 같습니다.</text>
    <reason>결론 클리셰 + 완곡 표현 사용</reason>
  </example>
</examples>
```

---

### 2.9 데이터 섹션 (`<data>`)

동적으로 주입되는 값들

```xml
<data>
  <field name="topic">{topic}</field>
  <field name="author-bio">{authorBio}</field>
  <field name="target-word-count">{targetWordCount}</field>

  <keywords type="search" priority="must-include">
    <keyword>검색어1</keyword>
    <keyword>검색어2</keyword>
  </keywords>

  <keywords type="context" priority="reference-only">
    <keyword>맥락 키워드1</keyword>
    <keyword>맥락 키워드2</keyword>
  </keywords>
</data>
```

---

### 2.10 체크리스트 (`<checklist>`)

```xml
<checklist priority="final">
  <item>"결론적으로" 같은 결론 접속어 0회</item>
  <item>문장 시작 "또한", "한편" 최소화 (0-1회)</item>
  <item>"~것 같습니다" → "~입니다" 전환</item>
  <item>본론 섹션별 미니결론 절대 금지</item>
</checklist>
```

---

## 3. 출력 형식 (`<output-format>`)

### 현재 (텍스트 프로토콜)
```
===TITLE===
제목 내용
===CONTENT===
<p>본문 HTML...</p>
```

### XML 출력
```xml
<output>
  <title>제목 내용</title>
  <content><![CDATA[
    <p>본문 HTML...</p>
  ]]></content>
</output>
```

---

## 4. 전체 프롬프트 예시

```xml
<prompt type="writer" version="1.0">

  <context-override priority="critical">
    <fact key="현직 대통령">이재명 (2025년 취임)</fact>
    <fact key="여당">더불어민주당</fact>
  </context-override>

  <speaker>
    <identity>부산 사하을 이재성 예비후보</identity>
    <party>더불어민주당</party>
  </speaker>

  <instructions priority="critical" label="검색어 SEO">
    <rule type="must">각 검색어 최소 2회 포함</rule>
    <rule type="must-not">검색어 나열 금지</rule>
  </instructions>

  <data>
    <field name="topic">청년 일자리 정책</field>
    <keywords type="search">
      <keyword>청년 일자리</keyword>
      <keyword>부산 취업</keyword>
    </keywords>
  </data>

  <writing-guide>
    <structure type="5-step">
      <step order="1" name="서론">인사, 문제 제기</step>
      <step order="2" name="본론1" heading="required">현황 분석</step>
      <step order="3" name="본론2" heading="required">해결책 제시</step>
      <step order="4" name="본론3" heading="required">기대효과</step>
      <step order="5" name="결론">다짐, 마무리</step>
    </structure>
  </writing-guide>

  <tone-matrix>
    <!-- 상황별 톤 가이드 -->
  </tone-matrix>

  <blacklist category="LLM 특유 표현">
    <banned>결론적으로</banned>
    <banned>또한</banned>
  </blacklist>

  <checklist priority="final">
    <item>결론 클리셰 0회</item>
    <item>5단 구조 준수</item>
  </checklist>

</prompt>
```

---

## 5. 태그 요약표

| 현재 패턴 | XML 태그 | 용도 |
|-----------|----------|------|
| `╔═══════════════╗` 박스 | `<instructions priority="critical">` | 중요 지시사항 |
| `╭───────────────╮` 둥근 박스 | `<context-override>` | 지식 오버라이드 |
| `[CRITICAL]`, `[HIGH]` | `priority` 속성 | 우선순위 |
| `[필수 규칙]` | `<rule type="must">` | 필수 규칙 |
| `✅`, `❌` | `type="must"`, `type="must-not"` | 해야 할 것/금지 |
| `| Case | 상황 |` 테이블 | `<tone-matrix><case>` | 톤 매트릭스 |
| Before/After 예시 | `<examples><example type="good|bad">` | 예시 |
| `- [ ]` 체크리스트 | `<checklist><item>` | 최종 검증 |
| `===TITLE===` 구분자 | `<output><title>` | 출력 파싱 |

---

## 6. 파싱 전략

### JavaScript 파서 예시

```javascript
function parseXMLOutput(xmlString) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(xmlString, 'text/xml');

  return {
    title: doc.querySelector('output > title')?.textContent?.trim(),
    content: doc.querySelector('output > content')?.textContent?.trim()
  };
}
```

### 에러 핸들링

```javascript
function safeParseOutput(rawOutput) {
  // 1차: XML 파싱 시도
  if (rawOutput.includes('<output>')) {
    try {
      return parseXMLOutput(rawOutput);
    } catch (e) {
      console.warn('XML 파싱 실패, 폴백 사용');
    }
  }

  // 2차: 기존 텍스트 프로토콜 폴백
  if (rawOutput.includes('===TITLE===')) {
    return parseTextProtocol(rawOutput);
  }

  // 3차: 전체를 content로 반환
  return { title: '', content: rawOutput };
}
```

---

## 7. 마이그레이션 전략

### Phase 1: 스키마 확정 (현재)
- [x] 태그 구조 설계
- [x] 변환 규칙 정의

### Phase 2: 부분 적용
- [ ] `editor-prompts.js` (239줄) - 가장 독립적
- [ ] `daily-communication.js` (147줄) - 템플릿 예시

### Phase 3: 전체 확장
- [ ] 나머지 템플릿 6개
- [ ] 가이드라인 8개
- [ ] 빌더 2개 (title, sns)

### Phase 4: 파싱 로직 교체
- [ ] writer-agent.js 출력 파싱
- [ ] 폴백 로직 유지

---

## 8. 기대 효과

1. **구조적 명확성**: AI가 섹션 역할을 명확히 인지
2. **우선순위 인식**: `priority` 속성으로 중요도 전달
3. **파싱 안정성**: XML 표준 파서 활용 가능
4. **유지보수성**: 태그 기반으로 수정 용이
5. **토큰 효율**: 시각적 구분자 제거로 토큰 절감
