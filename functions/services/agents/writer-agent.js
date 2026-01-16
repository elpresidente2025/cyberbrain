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

// ✅ 당론 가이드 import
const { getPartyStance } = require('../../prompts/guidelines/theminjoo');

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
      targetWordCount = 2000,
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

    // 5.5 당론 가이드 조회 (비동기)
    // 주제와 관련된 공식 당론이 있는지 확인하여 프롬프트에 강력하게 주입
    let partyStanceGuide = null;
    try {
      partyStanceGuide = await getPartyStance(topic);
    } catch (stanceError) {
      console.warn('⚠️ [WriterAgent] 당론 조회 실패 (무시하고 진행):', stanceError);
    }

    // ═══════════════════════════════════════════════════════════════
    // 6. 프롬프트 섹션 조립 (배열 방식으로 순서 명확화)
    // 최종 순서: 수사학 → 모범문장 → 지역힌트 → 검색어 → 제목 → 선거법 → 경고문 → 당론 → 본문 → 사용자지시
    // ═══════════════════════════════════════════════════════════════
    const promptSections = [];

    // ... (중략) ...

    // 6.7 경고문 (원외 인사, 가족 상황)
    const warnings = this.buildWarnings(userProfile, authorBio);
    if (warnings) {
      promptSections.push(warnings);
    }

    // 6.7.5 [CRITICAL] 당론 가이드 (본문 템플릿보다 우선 적용)
    if (partyStanceGuide) {
      promptSections.push(partyStanceGuide);
      console.log(`🏛️ [WriterAgent] 당론 가이드 주입 완료`);
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
   - 문단 길이: **한 문단은 100자~150자** 내외 유지 (유연하게 조절)
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
   - 검색어는 글 전체에서 **4~6회**까지만 자연스럽게 사용하세요.
   - **[CRITICAL]** 제공된 검색어를 단 한 글자도 바꾸지 말고 그대로 사용해야 합니다 (패러프레이즈 금지).
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
        maxOutputTokens: 1700,
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
      // ⚠️ selectedStrategy가 정의되지 않은 경우 fallback 처리
      appliedStrategy: {
        id: null,
        name: 'default'
      }
    };
  }

  /**
   * 저자 Bio 구성
   * - 현재 직위(customTitle)만 사용
   * - "OO 준비 중" 같은 표현 금지
   * - 예: "더불어민주당 사하구 을 지역위원장 이재성"
   */
  /**
   * 저자 Bio 구성 (강화된 버전)
   * - 기본 직위 외에 주요 경력, 슬로건, 핵심 가치 등을 포함하여
   * - LLM이 자기PR 섹션을 작성할 때 활용할 수 있는 풍부한 맥락 제공
   */
  buildAuthorBio(userProfile) {
    const name = userProfile.name || '사용자';
    const partyName = userProfile.partyName || '';

    // 현재 직위 (customTitle 우선)
    const currentTitle = userProfile.customTitle || userProfile.position || '';

    // 기본 Bio (예: "더불어민주당 사하구 을 지역위원장 이재성")
    const basicBio = [partyName, currentTitle, name].filter(Boolean).join(' ');

    // 추가 정보 구성
    const additionalInfo = [];

    // 1. 주요 경력 (Bio 또는 CareerSummary)
    // userProfile.careerSummary가 배열이면 상위 3개만, 문자열이면 그대로 사용
    const career = userProfile.careerSummary || userProfile.bio || '';
    if (career) {
      if (Array.isArray(career)) {
        additionalInfo.push(`[주요 경력] ${career.slice(0, 3).join(', ')}`);
      } else {
        // 문자열인 경우 너무 길면 자르기 (150자)
        const truncatedCareer = career.length > 150 ? career.substring(0, 150) + '...' : career;
        additionalInfo.push(`[주요 경력] ${truncatedCareer}`);
      }
    }

    // 2. 슬로건
    if (userProfile.slogan) {
      additionalInfo.push(`[슬로건] "${userProfile.slogan}"`);
    }

    // 3. 핵심 가치
    if (userProfile.coreValues) {
      const values = Array.isArray(userProfile.coreValues)
        ? userProfile.coreValues.join(', ')
        : userProfile.coreValues;
      additionalInfo.push(`[핵심 가치] ${values}`);
    }

    // 최종 조합
    if (additionalInfo.length > 0) {
      return `${basicBio}\n${additionalInfo.join('\n')}`;
    }

    return basicBio;
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

    // 3. 사실 관계 경고 (가족 이력 혼동 방지)
    warnings.push(`
🚨 [CRITICAL] 사실 관계 왜곡 금지 (본인 vs 가족 구분):
- 작성자 프로필(Bio)에 언급된 "가족의 직업/이력"을 "나(화자)의 직업/이력"으로 쓰지 마십시오.
- 예: "아버지가 부두 노동자" -> "저는 부두 노동자 출신입니다" (❌ 절대 금지: 아버지가 노동자이지 내가 아님)
- 예: "아버지가 부두 노동자" -> "부두 노동자였던 아버지의 등을 보며 자랐습니다" (✅ 올바른 표현)
`.trim());

    // 4. 지역 범위 경고 (광역 단체장 출마 시)
    const targetElection = userProfile.targetElection || {};
    const position = targetElection.position || userProfile.position || '';
    // 광역단체장 또는 교육감 등 넓은 범위
    const isMetro = position.includes('시장') || position.includes('도지사') || position.includes('교육감');
    // 단, 기초단체장(구청장/군수)은 제외해야 하므로 '시장' 체크 시 주의 (부산광역시장 vs 김해시장)
    // userProfile.regionLocal이 없고 regionMetro만 있으면 광역으로 간주하는 로직 활용 가능하나,
    // 여기서는 직책명으로 1차 필터링. "부산광역시장" 등.

    // 더 정확한 판단: targetElection.position이 명확하지 않을 수 있으므로
    // "시장"이 포함되면서 "구청장", "군수", "의원"이 아닌 경우로 좁힘, 혹은 userProfile.regionLocal이 비어있는지 확인.
    const isGuGun = position.includes('구청장') || position.includes('군수') || position.includes('기초의원');

    if (isMetro && !isGuGun) {
      warnings.push(`
🚨 [CRITICAL] 지역 범위 설정 (광역 자치단체장급):
- 당신은 지금 기초지자체(구/군)가 아닌 **"광역 자치단체(${userProfile.regionMetro || '시/도'}) 전체"**를 대표하는 후보자입니다.
- 특정 구/군(예: ${userProfile.regionLocal || '특정 지역'})에만 국한된 공약이나 비전을 메인으로 내세우지 마십시오. "구청장" 후보처럼 보입니다.
- 특정 지역 사례를 들더라도 반드시 **"${userProfile.regionMetro || '부산'} 전체의 균형 발전 및 경제적 파급 효과"**와 연결 지어 거시적인 관점에서 서술하십시오.
- 제목 생성 시 특정 구/군 이름을 넣지 마십시오. (예: "[부산] 사하구 경제 활성화" (❌) -> "[부산] 서부산권 균형 발전 전략" (✅))
`.trim());
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
