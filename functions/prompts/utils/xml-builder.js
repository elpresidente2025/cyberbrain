/**
 * functions/prompts/utils/xml-builder.js
 * XML 프롬프트 빌더 유틸리티
 *
 * 목적:
 * - 시각적 구분자(╔═══╗, ━━━)를 XML 태그로 대체
 * - 우선순위, 규칙, 예시 등을 구조화된 형태로 표현
 * - AI 모델의 지시사항 이해도 향상
 */

'use strict';

/**
 * XML 섹션 빌더
 * @param {string} tag - 태그명
 * @param {Object} attrs - 속성 객체
 * @param {string} content - 내부 콘텐츠
 * @returns {string}
 */
function xmlSection(tag, attrs = {}, content = '') {
  const attrStr = Object.entries(attrs)
    .map(([k, v]) => `${k}="${v}"`)
    .join(' ');
  const openTag = attrStr ? `<${tag} ${attrStr}>` : `<${tag}>`;
  return `${openTag}\n${content}\n</${tag}>`;
}

/**
 * 규칙 목록 빌더
 * @param {Array<{type: string, text: string}>} rules
 * @returns {string}
 */
function xmlRules(rules) {
  return rules
    .map(r => `  <rule type="${r.type}">${r.text}</rule>`)
    .join('\n');
}

/**
 * 필드 목록 빌더
 * @param {Object} fields - { fieldName: value }
 * @returns {string}
 */
function xmlFields(fields) {
  return Object.entries(fields)
    .filter(([_, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => `  <${k}>${v}</${k}>`)
    .join('\n');
}

/**
 * 리스트 아이템 빌더
 * @param {string} tag - 아이템 태그명
 * @param {Array<string>} items
 * @returns {string}
 */
function xmlList(tag, items) {
  return items
    .filter(Boolean)
    .map(item => `  <${tag}>${item}</${tag}>`)
    .join('\n');
}

// ============================================================================
// 프롬프트 섹션 빌더들
// ============================================================================

/**
 * 맥락 분석 섹션 (ContextAnalyzer 결과)
 */
function buildContextAnalysisSection(analysis, authorName) {
  const keyPlayersXml = (analysis.keyPlayers || [])
    .map(p => `    <player name="${p.name}" stance="${p.stance}">${p.action}</player>`)
    .join('\n');

  const factsXml = (analysis.mustIncludeFacts || [])
    .map((f, i) => `    <fact priority="${i + 1}">${f}</fact>`)
    .join('\n');

  const quotesXml = (analysis.newsQuotes || [])
    .map(q => `    <quote>${q}</quote>`)
    .join('\n');

  const stancePhrasesXml = (analysis.mustIncludeFromStance || [])
    .filter(p => p && typeof p === 'string' && p.length >= 10)
    .filter(p => !p.startsWith('⚠️') && !p.startsWith('우선순위:'))
    .map(p => `    <phrase>${p}</phrase>`)
    .join('\n');

  return `<context-analysis priority="absolute">
  <author name="${authorName || '화자'}">
    <stance>${analysis.authorStance || '(추출 실패)'}</stance>
    <role>${analysis.authorRole || '참고자료에 대한 논평 작성'}</role>
  </author>

  <event>
    <main>${analysis.mainEvent || '(추출 실패)'}</main>
    <scope>${analysis.issueScope || 'LOCAL_ISSUE'}</scope>
    <frame>${analysis.writingFrame || ''}</frame>
  </event>

  <players>
${keyPlayersXml || '    <player>(분석 실패)</player>'}
  </players>

  <tone expected="${analysis.expectedTone || '분석'}"/>
  <target>${analysis.responsibilityTarget || ''}</target>

  <warning>${analysis.contextWarning || '참고자료의 관계를 정확히 파악하세요.'}</warning>

  <must-include-facts>
${factsXml || '    <fact>(구체적 팩트 추출 실패)</fact>'}
  </must-include-facts>

  <must-include-quotes>
${quotesXml || '    <quote>(인용문 추출 실패)</quote>'}
  </must-include-quotes>

  <must-include-phrases priority="mandatory">
${stancePhrasesXml || '    <phrase>(핵심 문구 추출 실패)</phrase>'}
    <usage-rules>
      <rule type="must">각 문구를 그대로 인용하거나 핵심 의미를 유지한 채 패러프레이즈</rule>
      <rule type="must">최소 1개 이상을 서론 또는 첫 번째 본론에 배치</rule>
      <rule type="must">입장문의 논리 구조와 수사법(대구법, 반어법)을 본문에서도 활용</rule>
      <rule type="must-not">일반론으로 대체하거나 생략 시 원고 폐기</rule>
    </usage-rules>
  </must-include-phrases>
</context-analysis>`;
}

/**
 * 이슈 범위 경고 섹션 (중앙 정치 이슈)
 */
function buildScopeWarningSection(analysis) {
  if (analysis.issueScope !== 'CENTRAL_ISSUE' &&
      analysis.issueScope !== 'CENTRAL_ISSUE_WITH_LOCAL_IMPACT') {
    return '';
  }

  return `<scope-warning priority="critical" type="central-issue">
  <frame>${analysis.writingFrame || '헌정 질서 수호와 공직자 태도 비판'}</frame>
  <target>${analysis.responsibilityTarget || '중앙 정부 및 관련 공직자'}</target>
  <constraints>
    <rule type="must-not">분석된 프레임을 벗어나 엉뚱한 주제(부산시 행정 투명성, 지역 경제 등)로 논리 비약</rule>
    <rule type="must-not">기초지자체 언급 (이 이슈는 국가/광역 단위) - 서두/결미 1회 제외</rule>
  </constraints>
</scope-warning>`;
}

/**
 * 논조 경고 섹션 (비판문 의도 역전 방지)
 */
function buildToneWarningSection(analysis) {
  const tone = analysis.expectedTone || '';
  const target = analysis.responsibilityTarget || '';

  if (tone !== '비판' && tone !== '반박') {
    return '';
  }

  return `<tone-warning priority="critical" type="criticism-intent-protection">
  <target>${target}</target>
  <description>이 글은 "${target}"에 대한 비판문입니다</description>

  <banned-expressions reason="의도 역전 방지">
    <expression>${target}과 협력</expression>
    <expression>${target}과 함께</expression>
    <expression>${target}의 노력을 존중</expression>
    <expression>${target}의 성과 인정</expression>
    <expression>협력하여</expression>
    <expression>함께 나아가</expression>
    <expression>손잡고</expression>
  </banned-expressions>

  <required-expressions reason="비판적 논조 유지">
    <expression>역부족</expression>
    <expression>한계</expression>
    <expression>문제점</expression>
    <expression>책임</expression>
    <expression>실패</expression>
    <expression>원본 입장문의 비판적 표현 그대로 인용</expression>
  </required-expressions>

  <note>이 인물/기관은 비판의 대상이지, 협력의 파트너가 아닙니다. 긍정적 맥락으로 언급하면 원고 폐기.</note>
</tone-warning>`;
}

/**
 * 스타일 가이드 섹션
 */
function buildStyleGuideSection(stylePrompt, authorName, targetWordCount) {
  return `<style-guide priority="high">
  <persona>
${stylePrompt ? stylePrompt.trim().split('\n').map(l => '    ' + l.trim()).join('\n') : '    (스타일 프로필 없음)'}
  </persona>
</style-guide>`;
}

/**
 * 작성 규칙 섹션 (Base Rules)
 */
function buildWritingRulesSection(authorName, targetWordCount) {
  return `<writing-rules priority="critical">
  <word-count target="${targetWordCount}"/>

  <rule id="name-protection" priority="absolute">
    <description>사용자 이름 보호 (절대 변경 금지)</description>
    <constraints>
      <rule type="must-not">사용자 이름 "${authorName}"을 변경, 유추, 창작</rule>
      <rule type="must-not">이름이 비어있어도 다른 이름 만들어내기</rule>
      <rule type="must-not">참고자료의 다른 사람 이름을 사용자 이름으로 혼동</rule>
    </constraints>
  </rule>

  <rule id="reference-only" priority="absolute">
    <description>참고자료가 글의 유일한 주제</description>
    <constraints>
      <rule type="must-not">참고자료에 없는 주제(경제, 청년, 복지, 교통 등)로 대체</rule>
      <rule type="must">참고자료 분량이 적더라도 해당 논점만 심화하여 확장</rule>
      <rule type="must">사용자의 관점에서 매끄러운 1인칭 서사로 재구성</rule>
    </constraints>
  </rule>

  <rule id="absolute-trust" priority="critical">
    <description>절대적 신뢰 (Fact-Checking 금지)</description>
    <constraints>
      <rule type="must">제공된 참고자료, 키워드, 지시사항을 절대적 진실로 간주</rule>
      <rule type="must-not">AI가 자체적으로 진위 판단/의심</rule>
      <rule type="must-not">"(출처 필요)", "[확인 필요]", "알려진 바에 따르면" 등 유보적 표현</rule>
    </constraints>
  </rule>

  <rule id="rhetoric" priority="high">
    <description>문투 및 어미 활용 (Rhetorical Skill)</description>
    <good-patterns>
      <pattern name="수사학적 반복">호소력과 리듬감을 위한 의도적 어미/구조 반복 (대구법, 점층법)</pattern>
      <example>결코 포기하지 않겠습니다. 끝까지 싸우겠습니다. 반드시 승리하겠습니다!</example>
    </good-patterns>
    <banned-expressions>
      <expression>~라는 점입니다</expression>
      <expression>~상황입니다</expression>
      <expression>~라고 볼 수 있습니다</expression>
      <expression>~것으로 보여집니다</expression>
    </banned-expressions>
    <tone-guide>
      <bad>노력할 것입니다</bad>
      <good>반드시 해내겠습니다</good>
      <bad>중요하다고 생각합니다</bad>
      <good>가장 시급한 과제입니다</good>
    </tone-guide>
  </rule>

  <rule id="structure" priority="high">
    <description>5단 구성 및 문단 규칙 (황금 비율)</description>
    <structure type="5-section">
      <section name="서론" paragraphs="3"/>
      <section name="본론1" paragraphs="3" heading="required"/>
      <section name="본론2" paragraphs="3" heading="required"/>
      <section name="본론3" paragraphs="3" heading="required"/>
      <section name="결론" paragraphs="3"/>
    </structure>
    <paragraph-length min="100" max="150" unit="자"/>
    <heading-rules type="AEO-optimized">
      <good-types>
        <type name="질문형">~ 신청 방법은 무엇인가요?</type>
        <type name="데이터형">~ 5대 핵심 성과</type>
        <type name="정보형">~ 신청 자격 및 절차 안내</type>
        <type name="비교형">기존 정책 vs 신규 공약 차이점</type>
      </good-types>
      <banned>관련 내용, 정책 안내 (너무 모호함)</banned>
    </heading-rules>
  </rule>

  <rule id="keyword-limit" priority="high">
    <description>키워드 남용 금지 (SEO 스팸 방지)</description>
    <constraints>
      <rule type="must">검색어는 글 전체에서 4~6회까지만 자연스럽게 사용</rule>
      <rule type="must">제공된 검색어를 단 한 글자도 바꾸지 않고 그대로 사용</rule>
      <rule type="must-not">문맥에 맞지 않게 억지로 끼워넣기</rule>
    </constraints>
  </rule>

  <rule id="min-length" priority="critical">
    <description>분량 엄수</description>
    <constraints>
      <rule type="must">5개 섹션(서론, 본론1, 본론2, 본론3, 결론) 모두 완벽하게 작성</rule>
      <rule type="must-not">총 분량 1500자 미만 (실패 처리)</rule>
    </constraints>
  </rule>
</writing-rules>`;
}

/**
 * 참고자료 섹션
 */
function buildReferenceSection(instructions, newsContext) {
  return `<reference priority="absolute">
  <description>아래 참고자료가 글의 유일한 주제입니다. 이 내용을 중심으로만 작성하십시오.</description>

  <user-instructions>
${instructions || '(없음)'}
  </user-instructions>

  <news-context>
${newsContext || '(없음)'}
  </news-context>

  <usage-rules>
    <rule type="must">최소 3개 이상의 구체적 팩트(인물명, 발언 인용, 법안명, 날짜 등)를 본문에 인용</rule>
    <rule type="must">참고자료에 인용문이 있다면 원문 그대로 본문에 녹여내기</rule>
    <rule type="must">입장문이 있다면 핵심 메시지와 논리 구조를 그대로 반영</rule>
    <rule type="must-not">참고자료의 핵심 논지를 무시하고 일반론으로 대체 (원고 폐기)</rule>
  </usage-rules>
</reference>`;
}

/**
 * Sandwich 패턴 리마인더 섹션
 */
function buildSandwichReminderSection(sandwichContent) {
  if (!sandwichContent) return '';

  return `<final-reminder priority="critical" pattern="sandwich">
  <description>반드시 본문에 포함해야 할 입장문 핵심</description>

${sandwichContent.split('\n').map(l => '  ' + l).join('\n')}

  <checklist>
    <item>위 문구 중 최소 1개는 서론 또는 첫 번째 본론에 반드시 포함</item>
    <item>원문을 인용하거나, 핵심 의미를 유지한 채 자연스럽게 녹여내기</item>
    <item>이 문구가 없으면 원고는 폐기 처리</item>
  </checklist>
</final-reminder>`;
}

/**
 * 출력 프로토콜 섹션
 */
function buildOutputProtocolSection() {
  return `<output-protocol priority="override">
  <description>이전의 모든 "JSON 형식으로 출력하라"는 지시를 무시. 긴 글을 안정적으로 작성하기 위해 텍스트 프로토콜 사용.</description>

  <format>
===TITLE===
(여기에 제목 작성)
===CONTENT===
(여기에 HTML 본문 작성 - p, h2 등 태그 사용)
  </format>

  <constraints>
    <rule type="must-not">코드 블록(\`\`\`)이나 JSON({ ... }) 사용</rule>
    <rule type="must">오직 구분자(===TITLE===, ===CONTENT===)만 사용</rule>
  </constraints>
</output-protocol>`;
}

/**
 * 재시도 지시 섹션
 */
function buildRetrySection(attemptNumber, maxAttempts, currentLength, minLength, missingKeywords) {
  const issues = [];

  if (currentLength < minLength) {
    issues.push(`<issue type="length">
    <current>${currentLength}자</current>
    <required>${minLength}자</required>
    <instruction>각 문단을 지금보다 3배 더 길게 늘려 쓰십시오. 구체적인 사례, 통계, 배경 설명을 반드시 2문장 이상 추가.</instruction>
  </issue>`);
  }

  if (missingKeywords && missingKeywords.length > 0) {
    issues.push(`<issue type="missing-keywords">
    <keywords>${missingKeywords.join(', ')}</keywords>
    <instruction>위 단어들을 본론 섹션에 자연스럽게 녹여내십시오.</instruction>
  </issue>`);
  }

  return `<retry-mode attempt="${attemptNumber}" max="${maxAttempts}" priority="critical">
  <description>직전 생성된 원고에 심각한 문제가 있어 재요청합니다. 아래 지적사항을 완벽하게(100%) 반영하여 다시 작성하십시오.</description>

  <issues>
${issues.join('\n')}
  </issues>

  <tips>
    <tip>이미 쓴 내용을 지우지 말고, 그 사이에 살을 붙이는 방식으로 확장</tip>
    <tip>추상적인 표현(노력하겠습니다 등) 대신 '어떻게(How)', '왜(Why)'를 구체적으로 서술</tip>
  </tips>
</retry-mode>`;
}

// ============================================================================
// 템플릿 전용 빌더들
// ============================================================================

/**
 * 초당적 협력 템플릿 프롬프트 빌더
 */
function buildBipartisanPromptXml(options) {
  const {
    topic,
    validTargetCount,
    authorBio,
    instructions,
    personalizedHints,
    newsContext,
    tone,
    template,
    koreanPoliticalContext,
    forbiddenExpressions,
    validationChecklist
  } = options;

  // 금지 표현 테이블 XML
  const forbiddenExpressionsXml = Object.entries(forbiddenExpressions)
    .map(([category, data]) => {
      const alternatives = data.alternatives || [];
      return `    <category name="${category}" reason="${data.reason}">
${data.phrases.map(p => `      <banned>${p}</banned>`).join('\n')}
${alternatives.map(a => `      <alternative>${a}</alternative>`).join('\n')}
    </category>`;
    })
    .join('\n');

  // 체크리스트 XML
  const checklistXml = validationChecklist
    .map(item => `    <item id="${item.id}">${item.label}</item>`)
    .join('\n');

  return `<prompt type="bipartisan-cooperation" version="2.0">

<ratio-constraints priority="critical">
  <description>경쟁자 칭찬 비중 10-20% 제한</description>
  <constraint name="competitor-mention" max-ratio="0.2" max-chars="${Math.round(validTargetCount * 0.2)}">경쟁자 언급</constraint>
  <constraint name="self-pr" min-ratio="0.5" min-chars="${Math.round(validTargetCount * 0.5)}">자기PR (필수!)</constraint>
  <warning>초과 시 원고 폐기</warning>
</ratio-constraints>

<korean-political-context>
${koreanPoliticalContext.trim().split('\n').map(l => '  ' + l).join('\n')}
</korean-political-context>

<forbidden-expressions priority="critical">
  <description>위반 시 원고 폐기</description>
  <substitution-table>
    <row banned="전적으로 동의한다" replacement="이 부분만큼은 인정할 수 있다"/>
    <row banned="전적으로 공감한다" replacement="이번 사안에 한해 공감한다"/>
    <row banned="본받아야 한다" replacement="이 점은 참고할 수 있다"/>
    <row banned="깊이 공감한다" replacement="이번 발언은 주목할 만하다"/>
    <row banned="깊은 울림" replacement="주목할 만한 발언"/>
    <row banned="용기에 박수" replacement="원칙을 지킨 점은 인정"/>
    <row banned="귀감이 됩니다" replacement="참고할 만합니다"/>
    <row banned="동력이 될 것" replacement="긍정적 계기"/>
    <row banned="나침반이 될 것" replacement="방향 제시"/>
    <row banned="충격적인 소식" replacement="주목할 만한 소식"/>
    <row banned="마음이 무겁다" replacement="엄중하게 받아들인다"/>
    <row banned="안타깝다" replacement="유감스럽다"/>
  </substitution-table>

  <categories>
${forbiddenExpressionsXml}
  </categories>
</forbidden-expressions>

<special-case id="윤석열-사태" priority="critical">
  <rule id="causality" type="must">
    <description>인과관계 절대 준수</description>
    <bad>사형 구형 소식이 충격적이다/민주주의 위기다</bad>
    <good>12.3 내란(범죄)이 민주주의 위기였으며, 사형 구형(심판)은 정의의 실현이다</good>
  </rule>
  <rule id="emotion" type="must-not">
    <description>감정 배제</description>
    <banned>안타깝다, 마음이 무겁다, 충격</banned>
    <required>사필귀정, 엄정한 법의 심판, 당연한 귀결</required>
  </rule>
  <rule id="terminology">
    <description>용어 통일</description>
    <note>"전 대통령" 호칭 유지, 예우/안타까움 수식어 제외</note>
  </rule>
</special-case>

<core-principles>
  <principle>차이 먼저 명시, 인물은 분리: 정책 방향은 다르지만 인격·행동·노력은 존중</principle>
  <principle>구체성 필수, 추상 극찬 금지: "정말 훌륭하다"보다 "○○를 지속적으로 제기해 온 점"</principle>
  <principle>초당적 협력으로 연결: 칭찬 후 바로 공동목표(민생, 안보, 국익)로 이어가기</principle>
</core-principles>

<tone-setting level="${tone.id}">
  <name>${tone.name}</name>
  <when>${tone.when}</when>
  <characteristic>${tone.tone || tone.structure || ''}</characteristic>
  <template>${tone.template}</template>
  ${tone.caution ? `<caution>${tone.caution}</caution>` : ''}
  ${tone.connection ? `<connection>${tone.connection}</connection>` : ''}
</tone-setting>

<generation-template name="${template.name}">
  <structure>
${template.structure.split('\n').map(l => '    ' + l.trim()).join('\n')}
  </structure>
  <example>
${template.example.split('\n').map(l => '    ' + l.trim()).join('\n')}
  </example>
</generation-template>

<examples>
  <example type="good" label="경쟁자 인정 150자, 10%">
    <text>이번 헌정 위기에서 조경태 의원이 당을 넘어 원칙을 지킨 점만큼은 인정합니다. 저 또한 이러한 원칙 위에서 부산의 미래를 위한 AI 정책을 추진하겠습니다.</text>
    <note>이후 자기PR 900자 (50%) 필수!</note>
  </example>
  <example type="bad" label="경쟁자 칭찬 800자, 74% - 폐기 대상">
    <text>조경태 의원의 용기에 깊이 공감합니다... 본받아야 합니다... 전적으로 동의합니다...</text>
    <note>자기PR 300자 (25%) 부족 = 폐기!</note>
  </example>
</examples>

<validation-checklist>
${checklistXml}
</validation-checklist>

<data>
  <topic>${topic}</topic>
  <target-word-count>${validTargetCount}</target-word-count>
  <author>${authorBio}</author>
  ${instructions ? `<instructions>${instructions}</instructions>` : ''}
  ${personalizedHints ? `<self-pr-source priority="critical">${personalizedHints}</self-pr-source>` : ''}
  ${newsContext ? `<news-context>${newsContext.substring(0, 500)}...</news-context>` : ''}
</data>

<ratio-guide total="${validTargetCount}">
  <section name="상황 설명" ratio="0.15" chars="~${Math.round(validTargetCount * 0.15)}"/>
  <section name="경쟁자 인정" ratio="0.1-0.2" max-chars="${Math.round(validTargetCount * 0.2)}"/>
  <section name="자기PR/비전" ratio="0.5+" min-chars="${Math.round(validTargetCount * 0.5)}" required="true"/>
  <section name="차별화/마무리" ratio="0.15-0.25" chars="~${Math.round(validTargetCount * 0.2)}"/>
  <warning>경쟁자 칭찬 > 20% 또는 자기PR &lt; 50%이면 원고 폐기!</warning>
</ratio-guide>

<writing-order priority="critical">
  <step order="1" ratio="0.5" chars="${Math.round(validTargetCount * 0.5)}">자기PR - 가장 먼저, 가장 많이!</step>
  <step order="2" ratio="0.15">상황 설명</step>
  <step order="3" ratio="0.15-0.25">차별화/마무리</step>
  <step order="4" ratio="0.1-0.2" max-chars="${Math.round(validTargetCount * 0.2)}">경쟁자 인정 - 마지막에, 짧게!</step>
</writing-order>

<output-format>HTML 형식으로 본문을 작성하세요. p 태그로 문단을 구성하세요.</output-format>

</prompt>`;
}

/**
 * 일상 소통 템플릿 프롬프트 빌더 (daily-communication)
 */
function buildDailyCommunicationPromptXml(options) {
  const {
    topic,
    authorBio,
    authorName,
    targetWordCount,
    keywords,
    personalizedHints,
    narrativeFrame,
    emotionalArchetype,
    vocabularyModule
  } = options;

  const keywordsSection = keywords && keywords.length > 0
    ? `  <keywords type="context" note="참고용 - 삽입 강제 아님">\n${keywords.map(k => `    <keyword>${k}</keyword>`).join('\n')}\n  </keywords>`
    : '';

  return `<prompt type="daily-communication" version="2.0">

<speaker priority="critical">
  <identity>${authorBio}</identity>
  <name use-limit="intro-1-conclusion-1">${authorName || '화자'}</name>
  <rules>
    <rule type="must">이 글은 1인칭 시점으로 작성. "저는", "제가" 사용</rule>
    <rule type="must">"${authorName || '화자'}"이라는 이름은 서론에서 1회, 결론에서 1회만 사용</rule>
    <rule type="must-not">본문에서 이름 반복 ("${authorName || '화자'}은 약속합니다" 패턴)</rule>
    <rule type="must">본문에서는 "저는", "제가", "본 의원은" 등 대명사 사용</rule>
    <rule type="must-not">참고 자료의 타인 발언/행동을 화자인 척 작성</rule>
    <rule type="must">참고 자료에 등장하는 타인은 반드시 3인칭으로 언급</rule>
  </rules>
</speaker>

<data>
  <topic>${topic}</topic>
  <target-word-count>${targetWordCount || 2000}</target-word-count>
${keywordsSection}
${personalizedHints ? `  <personalized-hints>${personalizedHints}</personalized-hints>` : ''}
</data>

<writing-blueprint>
  <component name="뼈대 (서사 프레임)" type="${narrativeFrame.id}">
    <label>${narrativeFrame.name}</label>
    <instruction>${narrativeFrame.instruction}</instruction>
  </component>

  <component name="감정 (감성 원형)" type="${emotionalArchetype.id}">
    <label>${emotionalArchetype.name}</label>
    <instruction>${emotionalArchetype.instruction}</instruction>
  </component>

  <component name="어휘 (주제어 가이드)" type="${vocabularyModule.id}">
    <label>${vocabularyModule.name}</label>
    <thematic-guidance>${vocabularyModule.thematic_guidance}</thematic-guidance>
  </component>

  <component name="구조 전략" type="5-step">
    <structure>
      <step order="1" name="서론">인사, 문제 제기, 공감 형성</step>
      <step order="2" name="본론1" heading="required">첫 번째 핵심 주장 / 현황 분석</step>
      <step order="3" name="본론2" heading="required">두 번째 핵심 주장 / 구체적 해결책</step>
      <step order="4" name="본론3" heading="required">세 번째 핵심 주장 / 미래 비전 및 기대효과</step>
      <step order="5" name="결론">요약, 다짐, 마무리 인사</step>
    </structure>
  </component>
</writing-blueprint>

<output-format>
  <html-guide>p 태그로 문단, h2/h3 태그로 소제목, ul/ol 태그로 목록, strong 태그로 강조</html-guide>
  <banned>CSS 인라인 스타일, 마크다운 형식(**, *, #, - 등)</banned>
  <tone>반드시 존댓말 사용, 서민적이고 친근하며 진솔한 어조</tone>
</output-format>

<quality-checklist>
  <item>문장 완결성: 모든 문장이 완전한 구조</item>
  <item>조사/어미 검증: 조사 누락 절대 금지</item>
  <item>구체성 확보: 괄호 안 예시가 아닌 실제 구체적 내용</item>
  <item>날짜/시간 보존: 주제에 명시된 날짜/시간 그대로 사용</item>
  <item>논리적 연결: 도입-전개-결론 자연스러운 흐름</item>
  <item>문체 일관성: 존댓말 통일, 어색한 표현 제거</item>
  <item>감정 진정성: 형식적 표현 아닌 구체적 감정 표현</item>
  <item>반복 금지: 동일/유사 문장, 문단 반복 금지</item>
  <item>구조 일관성: 마무리 인사 후 본문 재시작 금지</item>
  <item priority="critical">본론 섹션별 미니결론 절대 금지: 각 본론은 팩트/주장으로 담백하게 끝내고, 다짐/결론은 오직 마지막 결론 섹션에만</item>
</quality-checklist>

</prompt>`;
}

/**
 * 비판적 글쓰기 템플릿 프롬프트 빌더 (current-affairs)
 */
function buildCriticalWritingPromptXml(options) {
  const {
    topic,
    authorBio,
    targetWordCount,
    keywords,
    personalizedHints,
    criticalStructure,
    offensiveTactic,
    vocabularyModule,
    rhetoricalStrategy,
    relevantExample
  } = options;

  const keywordsSection = keywords && keywords.length > 0
    ? `  <keywords type="context" note="참고용 - 삽입 강제 아님">\n${keywords.map(k => `    <keyword>${k}</keyword>`).join('\n')}\n  </keywords>`
    : '';

  return `<prompt type="critical-writing" version="2.0">

<data>
  <topic>${topic}</topic>
  <author>${authorBio}</author>
  <target-word-count>${targetWordCount || 2000}</target-word-count>
${keywordsSection}
${personalizedHints ? `  <personalized-hints>${personalizedHints}</personalized-hints>` : ''}
</data>

${rhetoricalStrategy?.promptInjection ? `<rhetorical-strategy priority="high">\n${rhetoricalStrategy.promptInjection}\n</rhetorical-strategy>` : ''}

<reference-example>
${relevantExample}
</reference-example>

<hallucination-guardrail priority="absolute">
  <rule type="must-not">사실을 지어내거나 추측</rule>
  <rule type="must">모든 비판과 주장은 오직 제공된 정보에만 100% 근거</rule>
  <rule type="must">구체적 사실, 통계, 인용문이 있다면 반드시 활용</rule>
  <rule type="must">정보가 없으면 사실을 날조하지 말고 원칙적 수준의 비판만 수행</rule>
</hallucination-guardrail>

<logic-guardrail priority="critical">
  <banned-patterns>
    <pattern reason="주제 외 효과 주장">특검법 → 경제 발전/투자 유치</pattern>
    <pattern reason="논리적 연결 없음">투명한 사회 → 관광객 증가</pattern>
    <pattern reason="근거 없는 결론">"따라서 X는 Y에 도움이 될 것입니다"</pattern>
    <pattern reason="추측성 예측">"이는 곧 Z로 이어질 것입니다"</pattern>
  </banned-patterns>
  <banned-expressions category="AI 슬롭">
    <expression>투명하고 공정한 사회를 만들겠습니다</expression>
    <expression>밝은 미래를 위해 노력하겠습니다</expression>
    <expression>함께 만들어 나가겠습니다</expression>
    <expression>필수적인 투자입니다</expression>
  </banned-expressions>
</logic-guardrail>

<reference-preservation priority="absolute">
  <rule id="key-phrases" type="must">입장문의 핵심 주장과 논리 구조를 반드시 유지. 날카로운 표현, 수사적 질문, 반어법 그대로 살리기</rule>
  <rule id="exact-terms" type="must">참조자료의 구체적 명칭(법안명, 인물명, 기관명, 사건명) 그대로 사용</rule>
  <rule id="no-new-topics" type="must-not">참조자료에 언급되지 않은 주제(지역 경제, 청년 정책 등) 삽입</rule>
  <rule id="rhetoric-copy" type="must">입장문이 강력한 문장으로 시작했다면 그 논조와 리듬 유지</rule>
</reference-preservation>

<writing-blueprint>
  <component name="전체 뼈대 (비판 구조)" type="${criticalStructure.id}">
    <label>${criticalStructure.name}</label>
    <instruction>${criticalStructure.instruction}</instruction>
  </component>

  <component name="핵심 기술 (공격 전술)" type="${offensiveTactic.id}">
    <label>${offensiveTactic.name}</label>
    <instruction>${offensiveTactic.instruction}</instruction>
  </component>

  <component name="표현 방식 (어휘 모듈)" type="${vocabularyModule.id}">
    <label>${vocabularyModule.name}</label>
    <thematic-guidance>${vocabularyModule.thematic_guidance}</thematic-guidance>
  </component>
</writing-blueprint>

<output-format>
  <html-guide>p 태그로 문단, h2/h3 태그로 소제목, ul/ol 태그로 목록, strong 태그로 강조</html-guide>
  <banned>CSS 인라인 스타일, 마크다운 형식</banned>
  <tone>반드시 존댓말 사용, 비판적이되 논리적인 어조</tone>
</output-format>

<quality-checklist>
  <item>문장 완결성: 모든 문장이 완전한 구조</item>
  <item>조사/어미 검증: 조사 누락 절대 금지</item>
  <item>구체성 확보: 괄호 안 예시 아닌 실제 구체적 내용</item>
  <item>논리적 연결: 도입-전개-결론 자연스러운 흐름</item>
  <item>사실 기반 비판: 제공된 정보에만 근거, 추측/날조 금지</item>
  <item>반복 금지: 동일/유사 문장, 문단 반복 금지</item>
  <item>구조 일관성: 마무리 인사 후 본문 재시작 금지</item>
  <item priority="critical">본론 섹션별 미니결론 절대 금지</item>
</quality-checklist>

</prompt>`;
}

/**
 * 논리적 글쓰기 템플릿 프롬프트 빌더 (policy-proposal)
 */
function buildLogicalWritingPromptXml(options) {
  const {
    topic,
    authorBio,
    authorName,
    targetWordCount,
    keywords,
    personalizedHints,
    logicalStructure,
    argumentationTactic,
    vocabularyModule,
    rhetoricalStrategy,
    electionStage
  } = options;

  const speakerName = authorName || '화자';
  const keywordsSection = keywords && keywords.length > 0
    ? `  <keywords type="context" note="참고용 - 삽입 강제 아님">\n${keywords.map(k => `    <keyword>${k}</keyword>`).join('\n')}\n  </keywords>`
    : '';

  const electionSection = electionStage?.promptInstruction
    ? `<election-compliance priority="critical">\n  <warning>선거법 준수 필수 - 위반 시 법적 책임 발생</warning>\n  <instruction>${electionStage.promptInstruction}</instruction>\n</election-compliance>\n\n`
    : '';

  return `<prompt type="logical-writing" version="2.0">

${electionSection}<speaker priority="critical">
  <identity>${authorBio}</identity>
  <name use-limit="intro-1-conclusion-1">${speakerName}</name>
  <rules>
    <rule type="must">이 글은 1인칭 시점으로 작성. "저는", "제가" 사용</rule>
    <rule type="must">"${speakerName}"이라는 이름은 서론에서 1회, 결론에서 1회만 사용</rule>
    <rule type="must-not">본문에서 이름 반복 ("${speakerName}은 약속합니다" 패턴)</rule>
    <rule type="must">본문에서는 "저는", "제가", "본 의원은" 등 대명사 사용</rule>
    <rule type="must">참고 자료에 등장하는 다른 정치인은 관찰/평가 대상(3인칭)</rule>
    <rule type="must-not">다른 정치인의 입장에서 공약을 내거나 다짐</rule>
  </rules>
</speaker>

<data>
  <topic>${topic}</topic>
  <target-word-count>${targetWordCount || 2000}</target-word-count>
${keywordsSection}
${personalizedHints ? `  <personalized-hints>${personalizedHints}</personalized-hints>` : ''}
</data>

${rhetoricalStrategy?.promptInjection ? `<rhetorical-strategy priority="high">\n${rhetoricalStrategy.promptInjection}\n</rhetorical-strategy>\n\n` : ''}<writing-blueprint>
  <component name="전체 뼈대 (논리 구조)" type="${logicalStructure.id}">
    <label>${logicalStructure.name}</label>
    <instruction>${logicalStructure.instruction}</instruction>
  </component>

  <component name="핵심 기술 (논증 전술)" type="${argumentationTactic.id}">
    <label>${argumentationTactic.name}</label>
    <instruction>${argumentationTactic.instruction}</instruction>
  </component>

  <component name="표현 방식 (어휘 모듈)" type="${vocabularyModule.id}">
    <label>${vocabularyModule.name}</label>
    <thematic-guidance>${vocabularyModule.thematic_guidance}</thematic-guidance>
  </component>
</writing-blueprint>

<rhetorical-techniques recommended="true">
  <technique name="구체성">추상적인 개념보다는 구체적인 사례와 숫자를 사용</technique>
  <technique name="공감">독자의 감정에 호소할 수 있는 진정성 있는 표현 사용</technique>
  <technique name="비전">문제 지적에 그치지 않고, 희망적인 대안과 미래 제시</technique>
</rhetorical-techniques>

<output-format>
  <html-guide>p 태그로 문단, h2/h3 태그로 소제목, ul/ol 태그로 목록, strong 태그로 강조</html-guide>
  <banned>CSS 인라인 스타일, 마크다운 형식</banned>
  <tone>반드시 존댓말 사용, 합리적이고 설득력 있는 어조</tone>
</output-format>

<quality-checklist>
  <item>문장 완결성: 모든 문장이 완전한 구조</item>
  <item>조사/어미 검증: 조사 누락 절대 금지</item>
  <item>구체성 확보: 괄호 안 예시 아닌 실제 구체적 내용</item>
  <item>논리적 연결: 도입-전개-결론 자연스러운 흐름</item>
  <item>반복 금지: 동일/유사 문장, 문단 반복 금지</item>
  <item>구조 일관성: 마무리 인사 후 본문 재시작 금지</item>
  <item priority="critical">본론 섹션별 미니결론 절대 금지</item>
</quality-checklist>

</prompt>`;
}

/**
 * 의정활동 보고 템플릿 프롬프트 빌더 (activity-report)
 */
function buildActivityReportPromptXml(options) {
  const {
    topic,
    authorBio,
    targetWordCount,
    keywords,
    personalizedHints,
    declarativeStructure,
    rhetoricalTactic,
    vocabularyModule
  } = options;

  const keywordsSection = keywords && keywords.length > 0
    ? `  <keywords type="context" note="참고용 - 삽입 강제 아님">\n${keywords.map(k => `    <keyword>${k}</keyword>`).join('\n')}\n  </keywords>`
    : '';

  return `<prompt type="activity-report" version="2.0">

<data>
  <topic>${topic}</topic>
  <author>${authorBio}</author>
  <target-word-count>${targetWordCount || 2000}</target-word-count>
${keywordsSection}
${personalizedHints ? `  <personalized-hints>${personalizedHints}</personalized-hints>` : ''}
</data>

<writing-blueprint>
  <component name="전체 뼈대 (보고 구조)" type="${declarativeStructure.id}">
    <label>${declarativeStructure.name}</label>
    <instruction>${declarativeStructure.instruction}</instruction>
  </component>

  <component name="핵심 기술 (표현 전술)" type="${rhetoricalTactic.id}">
    <label>${rhetoricalTactic.name}</label>
    <instruction>${rhetoricalTactic.instruction}</instruction>
  </component>

  <component name="표현 방식 (어휘 모듈)" type="${vocabularyModule.id}">
    <label>${vocabularyModule.name}</label>
    <thematic-guidance>${vocabularyModule.thematic_guidance}</thematic-guidance>
  </component>
</writing-blueprint>

<output-format>
  <html-guide>p 태그로 문단, h2/h3 태그로 소제목, ul/ol 태그로 목록, strong 태그로 강조</html-guide>
  <banned>CSS 인라인 스타일, 마크다운 형식</banned>
  <tone>반드시 존댓말 사용, 서민적이고 친근한 어조</tone>
</output-format>

<quality-checklist>
  <item>문장 완결성: 모든 문장이 완전한 구조 ("주민여하여" X → "주민 여러분께서" O)</item>
  <item>조사/어미 검증: 조사 누락 절대 금지 ("주민소리에" X → "주민들의 소리에" O)</item>
  <item>구체성 확보: 괄호 안 예시 아닌 실제 구체적 내용 ("(구체적 사례)" X → "지난 10월 12일 시흥시 체육관에서 열린" O)</item>
  <item>논리적 연결: 도입-전개-결론 자연스러운 흐름</item>
  <item>반복 금지: 동일/유사 문장, 문단 반복 금지</item>
  <item>구조 일관성: 마무리 인사 후 본문 재시작 금지</item>
  <item priority="critical">본론 섹션별 미니결론 절대 금지: 팩트/주장으로 담백하게 끝내고, 다짐은 마지막 결론 섹션에만</item>
</quality-checklist>

</prompt>`;
}

/**
 * 지역 현안 분석 템플릿 프롬프트 빌더 (local-issues)
 */
function buildLocalIssuesPromptXml(options) {
  const {
    topic,
    authorBio,
    targetWordCount,
    keywords,
    personalizedHints,
    analyticalStructure,
    explanatoryTactic,
    vocabularyModule,
    rhetoricalStrategy
  } = options;

  const keywordsSection = keywords && keywords.length > 0
    ? `  <keywords type="context" note="참고용 - 삽입 강제 아님">\n${keywords.map(k => `    <keyword>${k}</keyword>`).join('\n')}\n  </keywords>`
    : '';

  return `<prompt type="local-issues" version="2.0">

<data>
  <topic>${topic}</topic>
  <author>${authorBio}</author>
  <target-word-count>${targetWordCount || 2000}</target-word-count>
${keywordsSection}
${personalizedHints ? `  <personalized-hints>${personalizedHints}</personalized-hints>` : ''}
</data>

${rhetoricalStrategy?.promptInjection ? `<rhetorical-strategy priority="high">\n${rhetoricalStrategy.promptInjection}\n</rhetorical-strategy>\n\n` : ''}<writing-blueprint>
  <component name="전체 뼈대 (분석 구조)" type="${analyticalStructure.id}">
    <label>${analyticalStructure.name}</label>
    <instruction>${analyticalStructure.instruction}</instruction>
  </component>

  <component name="핵심 기술 (설명 전술)" type="${explanatoryTactic.id}">
    <label>${explanatoryTactic.name}</label>
    <instruction>${explanatoryTactic.instruction}</instruction>
  </component>

  <component name="표현 방식 (어휘 모듈)" type="${vocabularyModule.id}">
    <label>${vocabularyModule.name}</label>
    <thematic-guidance>${vocabularyModule.thematic_guidance}</thematic-guidance>
  </component>
</writing-blueprint>

<output-format>
  <html-guide>p 태그로 문단, h2/h3 태그로 소제목, ul/ol 태그로 목록, strong 태그로 강조</html-guide>
  <banned>CSS 인라인 스타일, 마크다운 형식</banned>
  <tone>반드시 존댓말 사용, 객관적이고 전문적인 어조</tone>
</output-format>

<quality-checklist>
  <item>문장 완결성: 모든 문장이 완전한 구조</item>
  <item>조사/어미 검증: 조사 누락 절대 금지</item>
  <item>구체성 확보: 괄호 안 예시 아닌 실제 구체적 내용 (예: "지난 10월 12일 시흥시 체육관에서 열린")</item>
  <item>논리적 연결: 도입-전개-결론 자연스러운 흐름</item>
  <item>데이터 정확성: 수치나 날짜 등 구체적 정보는 반드시 제공된 배경 정보에 근거</item>
  <item>반복 금지: 동일/유사 문장, 문단 반복 금지</item>
  <item>구조 일관성: 마무리 인사 후 본문 재시작 금지</item>
  <item priority="critical">본론 섹션별 미니결론 절대 금지: 팩트/주장으로 담백하게 끝내고, 다짐은 마지막 결론 섹션에만</item>
</quality-checklist>

</prompt>`;
}

module.exports = {
  xmlSection,
  xmlRules,
  xmlFields,
  xmlList,
  buildContextAnalysisSection,
  buildScopeWarningSection,
  buildToneWarningSection,
  buildStyleGuideSection,
  buildWritingRulesSection,
  buildReferenceSection,
  buildSandwichReminderSection,
  buildOutputProtocolSection,
  buildRetrySection,
  // 템플릿 빌더들
  buildBipartisanPromptXml,
  buildDailyCommunicationPromptXml,
  buildCriticalWritingPromptXml
};
