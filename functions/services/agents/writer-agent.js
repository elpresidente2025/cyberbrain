/* eslint-disable */
'use strict';

/**
 * Writer Agent - 초안 작성 (통합 리팩토링 버전)
 *
 * 역할:
 * - prompts/templates의 작법별 프롬프트 활용
 * - 개인화된 스타일 적용
 * - 구조화된 콘텐츠 생성
 *
 * 기존 prompts 시스템의 templates를 그대로 import하여 사용
 */

const { BaseAgent } = require('./base');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { getGeminiApiKey } = require('../../common/secrets');

// ✅ 선거법 규칙 import (구조적 통합)
const { getElectionStage } = require('../../prompts/guidelines/legal');

// ✅ 제목 가이드라인 import
const { getTitleGuidelineForTemplate } = require('../../prompts/builders/title-generation');

// ✅ 수사학 전략, 모범 문장, 소제목 전략 import
const { selectStrategyForAttempt, getWritingExamples, getSubheadingGuideline } = require('../../prompts/guidelines/editorial');

// ✅ 기존 templates 100% 보존하여 import
const { buildDailyCommunicationPrompt } = require('../../prompts/templates/daily-communication');
const { buildLogicalWritingPrompt } = require('../../prompts/templates/policy-proposal');
const { buildActivityReportPrompt } = require('../../prompts/templates/activity-report');
const { buildCriticalWritingPrompt, buildDiagnosisWritingPrompt } = require('../../prompts/templates/current-affairs');
const { buildLocalIssuesPrompt } = require('../../prompts/templates/local-issues');

// ✅ 기존 utils 보존하여 import
const { generateNonLawmakerWarning, generateFamilyStatusWarning } = require('../../prompts/utils/non-lawmaker-warning');

// ✅ 카테고리 매핑은 constants.js에서 import (단일 소스)
const { resolveWritingMethod } = require('../../utils/posts/constants');
const { extractStyleFromText } = require('../../utils/style-analyzer');

// 작법 → 템플릿 빌더 매핑
const TEMPLATE_BUILDERS = {
  'emotional_writing': buildDailyCommunicationPrompt,
  'logical_writing': buildLogicalWritingPrompt,
  'direct_writing': buildActivityReportPrompt,
  'critical_writing': buildCriticalWritingPrompt,
  'diagnostic_writing': buildDiagnosisWritingPrompt,
  'analytical_writing': buildLocalIssuesPrompt
};

let genAI = null;
function getGenAI() {
  if (!genAI) {
    const apiKey = getGeminiApiKey();
    if (!apiKey) return null;
    genAI = new GoogleGenerativeAI(apiKey);
  }
  return genAI;
}

class WriterAgent extends BaseAgent {
  constructor() {
    super('WriterAgent');
  }

  getRequiredContext() {
    return ['topic', 'category', 'userProfile'];
  }

  async execute(context) {
    const {
      topic,
      category,
      subCategory = '',
      userProfile = {},
      memoryContext = '',
      instructions = '',
      newsContext = '',
      targetWordCount = 1700,
      userKeywords = [],  // 🔑 사용자 직접 입력 키워드 (최우선)
      factAllowlist = null,
      previousResults = {},
      attemptNumber = 0,  // 🎯 시도 번호 (0, 1, 2) - 수사학 전략 변형용
      rhetoricalPreferences = {}  // 🎯 사용자 수사학 전략 선호도
    } = context;

    const ai = getGenAI();
    if (!ai) {
      throw new Error('Gemini API 키가 설정되지 않았습니다');
    }

    // 1. KeywordAgent 결과 = 맥락 파악용 키워드 (삽입 강제 X)
    const keywordResult = previousResults.KeywordAgent;
    const contextKeywords = keywordResult?.data?.keywords || [];
    const contextKeywordStrings = contextKeywords.slice(0, 5).map(k => k.keyword || k);

    // 🔑 검색어(userKeywords)와 키워드(contextKeywords)는 완전히 다른 용도
    // - 키워드: 글의 맥락을 잡기 위한 참고 도구 (템플릿에 전달)
    // - 검색어: SEO를 위해 반드시 삽입해야 하는 필수 요소 (CRITICAL 섹션으로 별도 주입)

    // 🔑 검색어(userKeywords)와 키워드(contextKeywords)는 완전히 다른 용도
    // - 키워드: 글의 맥락을 잡기 위한 참고 도구 (템플릿에 전달)
    // - 검색어: SEO를 위해 반드시 삽입해야 하는 필수 요소 (CRITICAL 섹션으로 별도 주입)

    // 🌟 [NEW] 문체 분석 프로필 적용 (DB 캐싱 값 우선 + 실시간 Fallback)
    let stylePrompt = '';

    // 1. 이미 저장된 스타일 프로필이 있는지 확인 (성능 최적화)
    let styleProfile = userProfile.styleProfile;

    // 2. 없으면 실시간 분석 시도 (첫 회차 Fallback)
    if (!styleProfile && userProfile.bio) {
      try {
        console.log("ℹ️ [WriterAgent] 스타일 프로필 없음 -> 실시간 분석 수행");
        styleProfile = await extractStyleFromText(userProfile.bio);
      } catch (err) {
        console.warn('❌ 문체 분석 실패:', err);
      }
    }

    if (styleProfile) {
      const { metrics, signature_keywords, tone_manner, forbidden_style } = styleProfile;
      stylePrompt = `
- **어조 및 태도**: ${tone_manner || '정보 없음'} (기계적인 문체가 아닌, 작성자의 고유한 톤을 모방하십시오.)
- **시그니처 키워드**: [${(signature_keywords || []).join(', ')}] - 이 단어들을 적재적소에 사용하여 작성자의 정체성을 드러내십시오.
- **문장 호흡**: 평균 ${metrics?.sentence_length?.avg || 40}자 내외의 ${metrics?.sentence_length?.distinct || '문장'} 사용.
- **종결 어미**: 주로 ${Object.keys(metrics?.ending_patterns?.ratios || {}).join(', ')} 사용.
- **금지 문체**: ${forbidden_style || '어색한 번역투'} 사용 금지.
`;
    }

    // 2. 작법 결정
    const writingMethod = resolveWritingMethod(category, subCategory);

    // 3. 저자 정보 구성
    const authorBio = this.buildAuthorBio(userProfile);

    // 4. 개인화 힌트 통합 (메모리 컨텍스트 포함)
    const personalizedHints = memoryContext || '';

    // 5. 템플릿 빌더 선택 및 프롬프트 생성
    const templateBuilder = TEMPLATE_BUILDERS[writingMethod] || buildDailyCommunicationPrompt;

    let prompt = templateBuilder({
      topic,
      authorBio,
      instructions,
      keywords: contextKeywordStrings,  // 맥락 파악용 (삽입 강제 X)
      targetWordCount,
      personalizedHints,
      newsContext,
      // 원외 인사 판단용
      isCurrentLawmaker: this.isCurrentLawmaker(userProfile),
      politicalExperience: userProfile.politicalExperience || '정치 신인',
      // 가족 상황 (자녀 환각 방지)
      familyStatus: userProfile.familyStatus || ''
    });

    // ═══════════════════════════════════════════════════════════════
    // 6. 프롬프트 섹션 조립 (배열 방식으로 순서 명확화)
    // 최종 순서: 수사학 → 모범문장 → 지역힌트 → 검색어 → 제목 → 선거법 → 경고문 → 본문
    // ═══════════════════════════════════════════════════════════════
    const promptSections = [];

    // 6.1 수사학 전략 (톤 설정)
    const selectedStrategy = selectStrategyForAttempt(
      attemptNumber,
      topic,
      instructions,
      userProfile,
      rhetoricalPreferences
    );

    if (selectedStrategy.promptInjection) {
      promptSections.push(`[🔥 수사학 전략 - ${selectedStrategy.strategyName}]\n${selectedStrategy.promptInjection}`);
      console.log(`🎯 [WriterAgent] 수사학 전략 적용: ${selectedStrategy.strategyName} (시도 ${attemptNumber})`);
    }

    // 6.2 모범 문장 예시 (Few-shot learning)
    const writingExamples = writingMethod === 'diagnostic_writing'
      ? null
      : getWritingExamples(category);
    if (writingExamples) {
      promptSections.push(writingExamples);
      console.log(`🎨 [WriterAgent] 모범 문장 예시 주입 (카테고리: ${category})`);
    }

    // 6.3 소제목 전략 (질문형 소제목)
    const subheadingGuideline = getSubheadingGuideline();
    if (subheadingGuideline) {
      promptSections.push(subheadingGuideline);
      console.log(`📝 [WriterAgent] 소제목 전략 주입`);
    }

    // 6.4 타 지역 주제 힌트
    if (context.regionHint) {
      promptSections.push(context.regionHint);
    }

    // 6.4 검색어 CRITICAL 섹션 (SEO 필수 삽입) - 동적 계산 적용
    if (userKeywords && userKeywords.length > 0) {
      // 🎯 동적 계산: 글자수 기반 삽입 횟수 산출
      const { calculateMinInsertions } = require('../../prompts/guidelines/seo');
      const minCount = calculateMinInsertions(targetWordCount);  // 2000자 → 5회
      const maxCount = Math.min(minCount + 2, Math.floor(minCount * 1.4));  // 스팸 방지 (5 → 7회, 최대 40% 증가)

      // 키워드별 개별 지시 (명확한 범위 제시)
      const keywordInstructions = userKeywords.map((kw, i) =>
        `  ${i + 1}. "${kw}" → **필수 ${minCount}~${maxCount}회** (부족/초과 모두 감점)`
      ).join('\n');

      // 배치 가이드 생성
      const { calculateDistribution } = require('../../prompts/guidelines/seo');
      const distribution = calculateDistribution(minCount);

      promptSections.push(`╔═══════════════════════════════════════════════════════════════╗
║  🔍 [CRITICAL] 노출 희망 검색어 - SEO 필수 삽입!               ║
╚═══════════════════════════════════════════════════════════════╝

사용자가 입력한 검색어 (네이버 검색 노출용):
${keywordInstructions}

⚠️ **중요**: 위 범위(${minCount}~${maxCount}회)를 **정확히** 지켜야 합니다.
   - ${minCount}회 미만: SEO 효과 없음 (원고 폐기)
   - ${maxCount}회 초과: 네이버 스팸 필터 차단 위험 (블로그 정지)

[삽입 규칙 - 수학적 강제]
1. **[고유명사화]**: 제공된 검색어는 **'공식 명칭'**입니다. 조사(은/는/이/가)를 제외하고 **단 한 글자도 변경 금지**

2. **[정확한 배치 계획]** (총 ${minCount}회를 아래와 같이 분산):
   - 도입부 (첫 2문단): 각 키워드 ${distribution.intro}회
   - 본론 (중간 문단들): 각 키워드 ${distribution.body}회
   - 결론 (마지막 2문단): 각 키워드 ${distribution.conclusion}회

3. **[치환 전략]**: "이 정책", "해당 사업" 대신 검색어로 치환
   - ✅ 예: "조경태 의원의 발언은" (O)
   - ❌ 예: "그의 발언은" (X)

4. **[분산 원칙]**:
   - 같은 문단 내 동일 키워드 최대 1회
   - 연속된 2문단에 같은 키워드 사용 금지

❌ **절대 금지** (위반 시 원고 자동 폐기):
- 콤마 나열: "부산, 대형병원, 순위에 대해" (X)
- 괄호 나열: "(6월 지방선거) (6월의 지방선거)" (X)
- 글 끝 스터핑: 마무리 인사 후 키워드 억지로 삽입 (X)
- 한 문장에 여러 검색어 몰아넣기 (X)

✅ 좋은 예: "조경태 의원이 윤석열 사형 구형에 대해 입장을 밝혔습니다."
❌ 나쁜 예: "조경태, 윤석열 사형 구형에 대해 이야기합니다."

📊 작성 후 자가 점검:
□ 각 검색어가 ${minCount}~${maxCount}회 범위 내에 있는가?
□ 도입-본론-결론에 고르게 분산되었는가?
□ 자연스러운 문맥 내 삽입인가? (나열이 아닌)`);

      console.log(`🔍 [WriterAgent] 검색어 삽입 규칙 주입: ${userKeywords.length}개 키워드, 각 ${minCount}~${maxCount}회`);
    }

    // 6.5 제목 가이드라인
    // 6.4-1 팩트 허용 목록 (수치 제한)
    if (factAllowlist) {
      const allowedTokens = (factAllowlist.tokens || []).slice(0, 30);
      const factSection = allowedTokens.length > 0
        ? `
[수치 근거 확인]
- 본문에 수치/비율/연도가 필요하면 제공된 근거 내 수치만 사용하세요.
- 수치는 왜 필요한지 맥락과 함께 제시하세요.
- 허용 수치: ${allowedTokens.join(', ')}
`
        : `
[수치 근거 확인]
- 수치 근거가 제공되지 않았습니다. 수치(비율/연도/순위)는 쓰지 마세요.
- 필요한 경우 수치를 빼고 일반 표현으로 작성하세요.
`;
      promptSections.push(factSection);
    }

    const titleGuideline = getTitleGuidelineForTemplate(userKeywords);
    if (titleGuideline) {
      promptSections.push(titleGuideline);
    }

    // 6.6 선거법 준수 지시문
    const electionLawInstruction = this.getElectionLawInstruction(userProfile);
    if (electionLawInstruction) {
      promptSections.push(electionLawInstruction);
    }

    // 6.7 경고문 (원외 인사, 가족 상황)
    const warnings = this.buildWarnings(userProfile, authorBio);
    if (warnings) {
      promptSections.push(warnings);
    }

    // 6.8 본문 템플릿 (기본)
    promptSections.push(prompt);

    // 6.9 [최우선 반영] 사용자 특별 지시사항 & 뉴스 기사 (Override Rule)
    // 템플릿이나 페르소나보다 이 내용이 가장 최신이고 중요함을 강조
    if (instructions || newsContext) {
      promptSections.push(`
╔═══════════════════════════════════════════════════════════════╗
║  🎭 [STYLE] 작성자 고유 페르소나 및 화법 가이드 (최우선 적용) ║
╚═══════════════════════════════════════════════════════════════╝
${stylePrompt}

╔═══════════════════════════════════════════════════════════════╗
║  🚨 [CRITICAL] 내용 구성 및 문투 교정 (Base Rules)           ║
║  (위의 STYLE 가이드가 이 Base Rules보다 더 구체적이면 우선함) ║
╚═══════════════════════════════════════════════════════════════╝

**목표 분량: ${targetWordCount}자 내외**


1. **[핵심] 참고자료 기반 재구성**:
   - 가장 중요한 것은 아래 **[뉴스/참고자료]**입니다.
   - 이 내용을 단순히 요약하지 말고, '사용자'의 관점에서 매끄러운 1인칭 서사로 재구성하세요.

2. **[CRITICAL] 절대적 신뢰 (Fact-Checking 금지)**:
   - **제공된 [뉴스/참고자료], [키워드], [사용자 지시사항]은 절대적인 진실로 간주하십시오.**
   - AI가 자체적으로 진위를 판단하거나 의심하지 마십시오.
   - 출처가 명시되지 않았더라도 사용자가 제공한 정보는 모두 사실인 것처럼 확신을 가지고 작성하십시오.
   - **절대 금지**: "(출처 필요)", "[확인 필요]", "알려진 바에 따르면" 등의 유보적인 표현이나 꼬리표를 붙이지 마십시오. 그냥 사실대로 쓰십시오.
   - 만약 정보가 틀렸다면 그 책임은 전적으로 사용자가 집니다. 당신은 충실한 대변인으로서 전달만 하십시오.

3. **[보충] 프로필(Bio) 활용으로 분량 확보**:
   - 참고자료만으로 분량이 부족하면, **사용자 프로필(Bio)**의 철학, 배경, 평소 어조를 활용하여 살을 붙이세요.
   - 단, 참고자료의 맥락을 해치지 않는 선에서 자연스럽게 녹여내야 합니다.

3. **[확장] 연계 공약/정보 활용**:
   - 만약 참고자료 내용이 사용자의 **기존 공약이나 추가 정보**와 논리적으로 연결된다면, 해당 내용을 가져와 내용을 보강하세요.
   - 예: "문화" 관련 뉴스라면 -> 사용자의 "문화 공약" 언급 가능. (관련 없으면 언급 금지)

4. **[최후] 요약 및 제언으로 분량 충족**:
   - 위 방법으로도 분량이 부족하다면, 결말부 시작에 **본론의 핵심을 요약하고 향후 포부를 구체적으로 서술**하여 분량을 채우세요.

5. **[필수] 문투 및 어미 활용 (Rhetorical Skill)**:
   - **[핵심] 기계적 반복 vs 수사학적 반복 구분**:
     - ❌ **기계적 반복(Bad)**: 별다른 의도 없이 단순 사실을 나열하며 "~했습니다. ~했습니다."를 반복하지 마세요. 지루합니다.
     - ✅ **수사학적 반복(Good)**: 호소력과 리듬감을 주기 위해 **의도적으로 같은 어미나 문장 구조를 반복(대구법, 점층법)**하는 것은 강력히 권장합니다.
     - 예시: "결코 포기하지 않겠습니다. 끝까지 싸우겠습니다. 반드시 승리하겠습니다!" (훌륭함)
   - **절대 금지 표현**:
     - "~라는 점입니다", "~상황입니다", "~라고 볼 수 있습니다", "~것으로 보여집니다"
     - 위와 같은 **제3자적/관찰자적/유보적 표현**은 절대 쓰지 마십시오. 당신은 당사자입니다.
   - **확신에 찬 어조**:
     - "노력할 것입니다" (X) -> "**반드시 해내겠습니다**" (O)
     - "중요하다고 생각합니다" (X) -> "**가장 시급한 과제입니다**" (O)

6. **[구조] 5단 구성 및 문단 규칙 (황금 비율)**:
   - 전체 구조: **[서론 - 본론1 - 본론2 - 본론3 - 결론]** (총 5개 섹션)
   - 문단 분배: **각 섹션 당 3개 문단**으로 구성 (총 15문단)
   - 문단 길이: **한 문단은 120자~150자** 내외 유지 (너무 길면 끊을 것)
   - **소제목(H2) AEO 최적화 규칙 (매우 중요)**:
     - 단순히 "서론", "본론"이라고 쓰지 마십시오. 검색자가 궁금해할 **구체적인 질문**이나 **키워드**를 포함해야 합니다.
     - **유형 1 (질문형)**: "~ 신청 방법은 무엇인가요?", "~ 혜택은?"
     - **유형 2 (데이터형)**: "~ 5대 핵심 성과", "~ 국비 100억 확보 내역"
     - **유형 3 (정보형)**: "~ 신청 자격 및 절차 안내"
     - **유형 4 (비교형)**: "기존 정책 vs 신규 공약 차이점"
     - ❌ 금지: "관련 내용", "정책 안내", "이관훈은?" (너무 짧고 모호함)
     - ✅ **본론1, 본론2, 본론3, 결론**: 위 규칙에 맞게 **매력적인 소제목(H2)**을 뽑아내십시오.

7. **[정치] 역할 및 화자 구분 (공약 주체)**:
   - **본인의 공약**: "저 이재성이 약속합니다"와 같이 본인이 주체가 되세요.
   - **타인(대통령/당)의 정책**: 반드시 출처를 밝히고, 본인은 이를 '지역에서 실현/계승'하겠다는 입장을 취하세요. (내 정책인 척 기만 금지)
   - **후원회장/지지자**: 오직 지지와 응원만 할 뿐, 공약의 주체가 될 수 없습니다. ("후원회장이 공약을 걸었다" X)
   - ✅ 올바른 예: "윤석열 정부의 의료 개혁을, 저 이재성이 부산에서 완성하겠습니다."

8. **[SEO] 키워드 남용 금지 (스팸 방지)**:
   - 검색어는 글 전체에서 **최대 5~6회**까지만 자연스럽게 사용하세요.
   - 10회 이상 과도하게 반복하면 스팸으로 간주됩니다.
   - 억지로 끼워 넣지 말고, 문맥에 맞을 때만 사용하세요.

9. **[CRITICAL] 분량 엄수**:
   - 이 글은 블로그/칼럼용 긴 글입니다.
   - 반드시 **5개 섹션(서론, 본론1, 본론2, 본론3, 결론)**을 모두 완벽하게 작성해야 합니다.
   - 총 분량이 **1500자 미만이면 실패**로 간주됩니다. 절대 중간에 멈추지 말고 끝까지 작성하십시오.

10. **[CRITICAL] 창작 허용 (Bio 확장)**:
    - 사용자 프로필(Bio)에 없는 내용이라도, **주제와 관련된 일반적인 정책이나 비전(예: 의료, 교통, 문화, 경제)**을 적극적으로 창작하여 본론 2, 3을 가득 채우십시오.
    - "Bio에 없어서 못 쓴다"는 변명은 허용되지 않습니다. 당신은 정치 전략가로서 구체적인 비전을 제시해야 합니다.

[사용자 지시사항]
${instructions || '(없음)'}

[뉴스/참고자료]
${newsContext || '(없음)'}
`);
    }

    // 최종 프롬프트 조립
    prompt = promptSections.join('\n\n');

    console.log(`📝 [WriterAgent] 프롬프트 생성 완료 (${prompt.length} 자, 작법: ${writingMethod}, 섹션: ${promptSections.length}개)`);

    // 9. Gemini 호출
    // 9. Gemini 호출 (사용자 요청: 2.5 Flash Standard 모델 사용)
    const model = ai.getGenerativeModel({ model: 'gemini-2.5-flash' });

    const result = await model.generateContent({
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
      generationConfig: {
        temperature: 0.8,
        maxOutputTokens: Math.min(targetWordCount * 3, 8000),
        responseMimeType: 'application/json'
      }
    });

    const responseText = result.response.text();

    // 10. JSON 파싱
    let parsedContent;
    try {
      parsedContent = JSON.parse(responseText);
    } catch (parseError) {
      // JSON 파싱 실패 시 텍스트 그대로 사용
      console.warn('⚠️ [WriterAgent] JSON 파싱 실패, 텍스트 모드로 전환');
      parsedContent = {
        title: `${topic} 관련`,
        content: responseText
      };
    }

    const content = parsedContent.content || responseText;
    const title = parsedContent.title || null;

    return {
      content,
      title,
      wordCount: content.replace(/<[^>]*>/g, '').length,
      writingMethod,
      contextKeywords: contextKeywordStrings,  // 맥락용 키워드
      searchTerms: userKeywords,               // SEO용 검색어
      // 🎯 수사학 전략 메타데이터 (선호도 학습용)
      appliedStrategy: {
        id: selectedStrategy.strategyId,
        name: selectedStrategy.strategyName
      }
    };
  }

  /**
   * 저자 Bio 구성
   * - 현재 직위(customTitle)만 사용
   * - "OO 준비 중" 같은 표현 금지
   * - 예: "더불어민주당 사하구 을 지역위원장 이재성"
   */
  buildAuthorBio(userProfile) {
    const name = userProfile.name || '사용자';
    const partyName = userProfile.partyName || '';

    // 현재 직위 사용 (customTitle 우선, 없으면 position)
    // ❌ targetElection.position 사용 금지 (광역자치단체장 준비 중 같은 표현 방지)
    const currentTitle = userProfile.customTitle || userProfile.position || '';

    // 정당 + 직위 + 이름 조합
    const parts = [];
    if (partyName) parts.push(partyName);
    if (currentTitle) parts.push(currentTitle);
    parts.push(name);

    // "더불어민주당 사하구 을 지역위원장 이재성" 형태
    return parts.join(' ');
  }

  /**
   * 현역 의원 여부 판단
   */
  isCurrentLawmaker(userProfile) {
    const experience = userProfile.politicalExperience || '';
    return ['초선', '재선', '3선이상'].includes(experience);
  }

  /**
   * 경고문 빌드 (원외 인사, 가족 상황) - 문자열 반환
   */
  buildWarnings(userProfile, authorBio) {
    const warnings = [];

    // 원외 인사 경고
    const nonLawmakerWarning = generateNonLawmakerWarning({
      isCurrentLawmaker: this.isCurrentLawmaker(userProfile),
      politicalExperience: userProfile.politicalExperience,
      authorBio
    });

    if (nonLawmakerWarning) {
      warnings.push(nonLawmakerWarning.trim());
    }

    // 가족 상황 경고 (자녀 환각 방지)
    const familyWarning = generateFamilyStatusWarning({
      familyStatus: userProfile.familyStatus
    });

    if (familyWarning) {
      warnings.push(familyWarning.trim());
    }

    return warnings.length > 0 ? warnings.join('\n\n') : '';
  }

  /**
   * 🗳️ 선거법 준수 지시문 가져오기 (legal.js 구조적 통합) - 문자열 반환
   * userProfile.status에 따라 해당 단계의 promptInstruction을 반환
   */
  getElectionLawInstruction(userProfile) {
    const status = userProfile.status || '준비';
    const electionStage = getElectionStage(status);

    if (electionStage && electionStage.promptInstruction) {
      console.log(`🗳️[WriterAgent] 선거법 지시문 주입: ${electionStage.name} (상태: ${status})`);
      return electionStage.promptInstruction.trim();
    }

    return '';
  }
}

module.exports = { WriterAgent };
