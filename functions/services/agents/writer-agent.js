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

// ✅ XML 프롬프트 빌더 import
const {
  buildContextAnalysisSection,
  buildScopeWarningSection,
  buildToneWarningSection,
  buildStyleGuideSection,
  buildWritingRulesSection,
  buildReferenceSection,
  buildSandwichReminderSection,
  buildOutputProtocolSection,
  buildRetrySection
} = require('../../prompts/utils/xml-builder');

// ✅ 카테고리 매핑은 constants.js에서 import (단일 소스)
const { resolveWritingMethod } = require('../../utils/posts/constants');
const { extractStyleFromText } = require('../../utils/style-analyzer');

// ✅ XML 파서 유틸리티 import (Phase 2 추가)
const { parseAIResponse, debugParse } = require('../../utils/xml-parser');

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

    // 🔍 디버그: WriterAgent가 실제로 받은 참고자료 확인
    console.log('🔍 [WriterAgent] 참고자료 수신 확인:', {
      'instructions 길이': instructions?.length || 0,
      'instructions 미리보기': instructions?.substring(0, 200) || '(없음)',
      'newsContext 길이': newsContext?.length || 0,
      'newsContext 미리보기': newsContext?.substring(0, 200) || '(없음)'
    });

    // 1. KeywordAgent 결과 = 맥락 파악용 키워드 (삽입 강제 X)
    const keywordResult = previousResults.KeywordAgent;
    const contextKeywords = keywordResult?.data?.keywords || [];
    const contextKeywordStrings = contextKeywords.slice(0, 5).map(k => k.keyword || k);

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
    const authorName = userProfile.name || '';  // 이름만 (예: "이재성")

    // 4. 개인화 힌트 통합 (메모리 컨텍스트 포함)
    const personalizedHints = memoryContext || '';

    // 5. 템플릿 빌더 선택 및 프롬프트 생성
    const templateBuilder = TEMPLATE_BUILDERS[writingMethod] || buildDailyCommunicationPrompt;

    let prompt = templateBuilder({
      topic,
      authorBio,
      authorName,  // 이름만 별도 전달 (본인 이름 반복 제한용)
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
    // 최종 순서: 🎯핵심앵커 → 수사학 → 모범문장 → 지역힌트 → 검색어 → 제목 → 선거법 → 경고문 → 당론 → 본문 → 사용자지시
    // ═══════════════════════════════════════════════════════════════
    const promptSections = [];
    let mustIncludeFromStanceForSandwich = ''; // 🥪 Sandwich 패턴용: 입장문 핵심 문구 저장

    // ═══════════════════════════════════════════════════════════════
    // 🎯 [NEW v2] ContextAnalyzer - LLM 기반 맥락 분석 (2단계 생성)
    // 참고자료에서 "누가 누구를 어떻게" 관계를 정확히 파악하여 프롬프트에 주입
    // 🔧 ROLLBACK: 아래 USE_CONTEXT_ANALYZER를 false로 설정하면 기존 휴리스틱으로 복구
    // ═══════════════════════════════════════════════════════════════
    const USE_CONTEXT_ANALYZER = true;  // 🔧 롤백 스위치: false로 변경 시 기존 방식으로 복구

    if ((instructions || newsContext) && USE_CONTEXT_ANALYZER) {
      const sourceText = [instructions, newsContext].filter(Boolean).join('\n');

      if (sourceText.length >= 100) {
        try {
          console.log('🔍 [WriterAgent] ContextAnalyzer 시작...');

          const contextPrompt = `당신은 정치 뉴스 분석 전문가입니다. 아래 참고자료를 읽고 상황을 정확히 파악하세요.

⚠️ **[중요] 참고자료 구조 안내**:
- **첫 번째 자료**: 글 작성자(${authorName || '화자'})가 직접 작성한 **페이스북 글 또는 입장문**입니다. 이것이 글의 핵심 논조와 주장입니다.
- **두 번째 이후 자료**: 뉴스 기사, 데이터 등 **배경 정보와 근거 자료**입니다.

따라서:
1. 첫 번째 자료에서 **글쓴이(${authorName || '화자'})의 입장과 논조**를 추출하세요.
2. 두 번째 이후에서 **사실관계, 인용할 발언, 법안명 등 팩트**를 추출하세요.
3. 글쓴이는 첫 번째 자료의 입장을 **더 정교하고 풍부하게 확장**하는 글을 원합니다.

[참고자료]
${sourceText.substring(0, 4000)}

[글 작성자 이름]
${authorName || '(미상)'}

다음 JSON 형식으로만 응답하세요 (각 필드는 반드시 한국어로 작성):
{
  "issueScope": "이슈의 범위 판단: 'CENTRAL_ISSUE' (중앙 정치/국가 이슈), 'LOCAL_ISSUE' (지역 현안), 'CENTRAL_ISSUE_WITH_LOCAL_IMPACT' (중앙 이슈이나 지역 인사가 연루됨) 중 택1",
  "localConflictPoint": "지역적 쟁점 요약 (예: '박형준 시장의 신공안 통치 발언 논란'). 중앙 이슈일 경우 '없음'",
  "responsibilityTarget": "비판이나 요구의 대상이 되는 핵심 주체/기관 (예: '대통령실', '국회', '부산시장', '시의회'). 행정적 책임 주체를 명확히 할 것",
  "writingFrame": "이 글이 지향해야 할 핵심 논리 프레임 1줄 요약 (예: '헌정 질서 수호와 공직자 태도 비판', '지역 경제 활성화 대책', '약자 보호와 복지 확충'). ⚠️ '부산시 행정 투명성'과 같은 엉뚱한 프레임 금지",
  "authorStance": "첫 번째 자료(입장문)에서 추출한 글쓴이의 핵심 주장 1줄 요약",
  "mainEvent": "두 번째 이후 자료(뉴스)에서 추출한 핵심 사건 1줄 요약 (여기서 부산시와 무관한 중앙 이슈라면 명확히 구분)",
  "keyPlayers": [
    { "name": "인물명", "action": "이 사람이 한 행동/주장", "stance": "찬성/반대/중립" }
  ],
  "authorRole": "글 작성자(${authorName || '화자'})가 이 상황에서 취해야 할 입장과 역할 (첫 번째 자료 기반)",
  "expectedTone": "이 글의 예상 논조 (반박/지지/분석/비판/호소 중 택1)",
  "mustIncludeFacts": ["뉴스에서 추출한 반드시 언급해야 할 구체적 팩트 5개 (정식 법안명, 날짜, 장소, 구체적 수치 등) - 모호한 표현 금지"],
  "newsQuotes": ["뉴스에 등장하는 핵심 인물들의 발언을 '참고용'으로 추출 (3개 이상). 예: 박형준 시장의 '신공안 통치' 발언 등"],
  "mustIncludeFromStance": ["입장문에서 추출한 핵심 문장 1", "입장문에서 추출한 핵심 문장 2"],
  "contextWarning": "맥락 오해 방지를 위한 주의사항 (예: 2차 특검법은 중앙 이슈이므로 부산시 의혹으로 축소 해석하지 말 것)"
}

**[CRITICAL] mustIncludeFromStance 추출 가이드**:
- 입장문(첫 번째 자료)에서 가장 인상적이고 강력한 문장 2~3개를 **원문 그대로** 복사하세요.
- 우선순위: (1) 격언형 문장 (~하면 ~없다), (2) 반어법/수사적 질문, (3) 대구법 문장, (4) 핵심 비판 문장
- 예시: "당당하면 피할 이유 없다", "'신공안 통치'라는 프레이밍 자체가 진실 규명 회피"
- ⚠️ 지시문이 아닌 **실제 입장문에서 추출한 원문**을 넣으세요!`;

          const contextModel = ai.getGenerativeModel({ model: 'gemini-2.5-flash' });
          const contextResult = await contextModel.generateContent({
            contents: [{ role: 'user', parts: [{ text: contextPrompt }] }],
            generationConfig: {
              temperature: 0.1,  // 매우 낮은 temperature로 정확한 분석
              maxOutputTokens: 600,
              responseMimeType: 'application/json'
            }
          });

          const contextResponse = contextResult.response.text();
          let contextAnalysis = null;

          try {
            contextAnalysis = JSON.parse(contextResponse);
          } catch (parseErr) {
            // JSON 추출 재시도
            const jsonMatch = contextResponse.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
              contextAnalysis = JSON.parse(jsonMatch[0]);
            }
          }

          if (contextAnalysis && (contextAnalysis.mainEvent || contextAnalysis.authorStance)) {
            const mustIncludeText = (contextAnalysis.mustIncludeFacts || [])
              .map((f, i) => `${i + 1}. ${f}`)
              .join('\n');

            // 🔧 [방안 1] 핵심 문구 추출 및 검증용 저장
            // mustIncludeFromStance는 이제 실제 문장이어야 함 (지시문이 아닌 추출값)
            const rawStancePhrases = contextAnalysis.mustIncludeFromStance || [];
            // 지시문 필터링: "⚠️", "우선순위:", "예시 패턴:" 등으로 시작하는 항목 제거
            const filteredStancePhrases = rawStancePhrases.filter(phrase => {
              if (!phrase || typeof phrase !== 'string') return false;
              const trimmed = phrase.trim();
              // 지시문 패턴 감지
              if (trimmed.startsWith('⚠️')) return false;
              if (trimmed.startsWith('우선순위:')) return false;
              if (trimmed.startsWith('예시 패턴:')) return false;
              if (trimmed.startsWith('→ 실제')) return false;
              if (trimmed.length < 10) return false; // 너무 짧은 것도 제외
              return true;
            });

            const mustIncludeFromStanceText = filteredStancePhrases
              .map((f, i) => `${i + 1}. "${f}"`) // 따옴표 강조
              .join('\n');

            // 🔑 [방안 1] 검증용으로 context에 저장 (EditorAgent에서 사용)
            context._extractedKeyPhrases = filteredStancePhrases;

            const newsQuotesText = (contextAnalysis.newsQuotes || [])
              .map((q, i) => `${i + 1}. ${q}`)
              .join('\n');

            // 🥪 Sandwich 패턴: 프롬프트 맨 뒤에서 다시 사용하기 위해 저장 (모든 필수 요소 포함)
            mustIncludeFromStanceForSandwich = `
[✅ 입장문 핵심 문구]
${mustIncludeFromStanceText}

[✅ 뉴스 핵심 팩트]
${mustIncludeText}

[✅ 뉴스 주요 발언]
${newsQuotesText}
`.trim();

            // context에 responsibilityTarget 저장 (EditorAgent에서 검증용)
            const expectedTone = contextAnalysis.expectedTone || '';
            const responsibilityTarget = contextAnalysis.responsibilityTarget || '';
            context._responsibilityTarget = responsibilityTarget;
            context._expectedTone = expectedTone;

            // XML 구조로 맥락 분석 섹션 생성
            const contextXml = buildContextAnalysisSection(contextAnalysis, authorName);
            const scopeXml = buildScopeWarningSection(contextAnalysis);
            const toneXml = buildToneWarningSection(contextAnalysis);

            promptSections.push(contextXml);
            if (scopeXml) promptSections.push(scopeXml);
            if (toneXml) promptSections.push(toneXml);
            console.log('✅ [WriterAgent] ContextAnalyzer 완료:', {
              authorStance: contextAnalysis.authorStance?.substring(0, 50),
              mainEvent: contextAnalysis.mainEvent,
              expectedTone: contextAnalysis.expectedTone,
              keyPlayersCount: contextAnalysis.keyPlayers?.length || 0,
              // 🔑 [방안 1] 핵심 문구 추출 디버깅
              rawStancePhrases: contextAnalysis.mustIncludeFromStance?.length || 0,
              filteredStancePhrases: filteredStancePhrases?.length || 0,
              responsibilityTarget: contextAnalysis.responsibilityTarget || null
            });

            // 🔑 [방안 1] 핵심 문구 상세 로깅
            if (filteredStancePhrases.length > 0) {
              console.log('🔑 [WriterAgent] 핵심 문구 추출 성공:', filteredStancePhrases);
            } else {
              console.warn('⚠️ [WriterAgent] 핵심 문구 추출 실패 - rawStancePhrases:', contextAnalysis.mustIncludeFromStance);
            }
          } else {
            console.warn('⚠️ [WriterAgent] ContextAnalyzer 파싱 실패, 기존 방식으로 폴백');
          }
        } catch (contextError) {
          console.error('❌ [WriterAgent] ContextAnalyzer 오류:', contextError.message);
          // 오류 시 기존 휴리스틱으로 폴백하지 않고 진행 (성능 우선)
        }
      }
    }

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
      // XML 구조로 스타일 가이드 및 작성 규칙 생성
      const styleGuideXml = buildStyleGuideSection(stylePrompt, authorName, targetWordCount);
      const writingRulesXml = buildWritingRulesSection(authorName, targetWordCount);
      const referenceXml = buildReferenceSection(instructions, newsContext);

      promptSections.push(styleGuideXml);
      promptSections.push(writingRulesXml);
      promptSections.push(referenceXml);
    }

    // 🥪 Sandwich 패턴: 프롬프트 맨 뒤에 입장문 핵심 문구 다시 강조
    if (mustIncludeFromStanceForSandwich) {
      const sandwichXml = buildSandwichReminderSection(mustIncludeFromStanceForSandwich);
      if (sandwichXml) promptSections.push(sandwichXml);
    }

    // 6.10 [PROTOCOL OVERRIDE] JSON 포맷 무시 및 텍스트 프로토콜 강제 (최종 오버라이드)
    promptSections.push(buildOutputProtocolSection());

    // 최종 프롬프트 조립
    prompt = promptSections.join('\n\n');

    console.log(`📝 [WriterAgent] 프롬프트 생성 완료 (${prompt.length} 자, 작법: ${writingMethod}, 섹션: ${promptSections.length}개)`);

    // 9. Gemini 호출 (사용자 요청: 2.5 Flash Standard 모델 사용)
    const model = ai.getGenerativeModel({ model: 'gemini-2.5-flash' });

    // ═══════════════════════════════════════════════════════════════
    // 🔄 [NEW] 분량 검증 재시도 루프 (최대 3회, 에러 없음, 항상 반환)
    // ═══════════════════════════════════════════════════════════════
    const MIN_CHAR_COUNT = Math.max(1200, Math.round(targetWordCount * 0.85));  // 최소 분량 기준
    const MAX_ATTEMPTS = 3;
    let content = null;
    let title = null;
    let attemptCount = 0;
    let lastResponseText = '';

    // [New] XML 파서 통합 - 기존 parseTextProtocol을 xml-parser의 parseAIResponse로 대체
    // parseAIResponse는 XML 태그 파싱 우선, 텍스트 프로토콜 폴백 지원
    // import는 파일 상단에서 완료: const { parseAIResponse, debugParse } = require('../../utils/xml-parser');

    while (attemptCount < MAX_ATTEMPTS) {
      attemptCount++;
      const isRetry = attemptCount > 1;

      // 재시도 시 분량 강조 및 키워드 누락 보완 프롬프트 추가
      let currentPrompt = prompt;
      if (isRetry) {
        // 1. 키워드 누락 확인
        const missingKeywords = userKeywords.filter(k => !content || !content.includes(k));
        const hasMissingKeywords = missingKeywords.length > 0;

        // 2. 분량 부족 확인
        const currentLength = content ? content.replace(/<[^>]*>/g, '').length : 0;
        const isShort = currentLength < MIN_CHAR_COUNT;

        console.log(`⚠️ [WriterAgent] 재시도 진입: 분량부족=${isShort}(${currentLength}자), 키워드누락=${hasMissingKeywords}(${missingKeywords.join(', ')})`);

        // XML 구조로 재시도 지시 생성
        const retryXml = buildRetrySection(
          attemptCount,
          MAX_ATTEMPTS,
          currentLength,
          MIN_CHAR_COUNT,
          hasMissingKeywords ? missingKeywords : []
        );

        currentPrompt = retryXml + '\n\n' + prompt;
      }

      try {
        const temperature = isRetry ? 0.45 : 0.4;  // XML 출력 안정성을 위해 0.4 기본값 적용
        console.log(`🔄 [WriterAgent] 생성 시도 ${attemptCount}/${MAX_ATTEMPTS} (temperature: ${temperature})`);

        const result = await model.generateContent({
          contents: [{ role: 'user', parts: [{ text: currentPrompt }] }],
          generationConfig: {
            temperature,
            maxOutputTokens: 8192,  // 4000 -> 8192 (더 긴 출력 허용)
            responseMimeType: 'text/plain' // [CRITICAL] JSON 강제 해제
          }
        });

        lastResponseText = result.response.text();

        // ✅ XML 파서 사용 (텍스트 프로토콜 폴백 지원)
        const parsed = parseAIResponse(lastResponseText, `${topic} 관련`);
        content = parsed?.content || '';
        title = parsed?.title || `${topic} 관련`;

        // 디버그 로그
        console.log(`📊 [WriterAgent] Parse method: ${parsed?.parseMethod || 'unknown'}`);

        // 분량 검증
        const charCount = content.replace(/<[^>]*>/g, '').length;
        console.log(`📊 [WriterAgent] 시도 ${attemptCount} 결과: ${charCount}자`);

        if (charCount >= MIN_CHAR_COUNT) {
          console.log(`✅ [WriterAgent] 분량 충족! (${charCount}자 >= ${MIN_CHAR_COUNT}자)`);
          break;  // 성공 - 루프 탈출
        } else {
          console.warn(`⚠️ [WriterAgent] 분량 부족 (${charCount}자 < ${MIN_CHAR_COUNT}자), 재시도...`);
        }
      } catch (genError) {
        console.error(`❌ [WriterAgent] 시도 ${attemptCount} 오류:`, genError.message);
        // 오류 발생해도 계속 시도
      }
    }

    // 최종 안전장치: content가 없으면 마지막 응답에서라도 추출
    if (!content && lastResponseText) {
      console.warn('⚠️ [WriterAgent] 최종 폴백: 마지막 응답에서 content 추출');
      const fallback = parseAIResponse(lastResponseText, `${topic} 관련`);
      content = fallback?.content || `<p>${topic}에 대한 원고입니다.</p>`;
      title = fallback?.title || `${topic} 관련`;
      console.log(`📊 [WriterAgent] Fallback parse method: ${fallback?.parseMethod || 'unknown'}`);
    }

    const finalCharCount = content ? content.replace(/<[^>]*>/g, '').length : 0;
    console.log(`📝 [WriterAgent] 최종 결과: ${finalCharCount}자 (${attemptCount}회 시도)`);

    if (finalCharCount < MIN_CHAR_COUNT) {
      throw new Error(`WriterAgent 분량 부족 (${finalCharCount}/${MIN_CHAR_COUNT}자)`);
    }

    return {
      content,
      title,
      wordCount: finalCharCount,
      writingMethod,
      contextKeywords: contextKeywordStrings,
      searchTerms: userKeywords,
      // 🎯 수사학 전략 메타데이터 (선호도 학습용)
      // ⚠️ selectedStrategy가 정의되지 않은 경우 fallback 처리
      appliedStrategy: {
        id: null,
        name: 'default'
      },
      // 🔑 [방안 1] 핵심 문구 검증용 데이터
      extractedKeyPhrases: context._extractedKeyPhrases || []
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
- 특정 지역 사례를 들더라도 반드시 **"${userProfile.regionMetro || '부산'} 전체의 균형 발전"**이나 **"시정 전체의 쇄신"**과 연결 지어 거시적인 관점에서 서술하십시오. (경제 이슈는 '경제 효과', 정치 이슈는 '정의와 상식'으로 연결)
- 제목 생성 시 특정 구/군 이름을 넣지 마십시오. (예: "${userProfile.regionLocal || '특정 구/군'} 현안 해결" (❌) -> "${userProfile.regionMetro || '광역시/도'}의 정의로운 미래와 도약" (✅))
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
