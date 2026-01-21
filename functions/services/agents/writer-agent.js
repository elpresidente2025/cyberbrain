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
            const keyPlayersText = (contextAnalysis.keyPlayers || [])
              .map(p => `- ${p.name}: ${p.action} (${p.stance})`)
              .join('\n');

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

            // 🚨 중앙 이슈 혼동 방지 경고 생성
            let scopeWarning = '';
            // 중앙 이슈이거나 중앙 이슈가 지역에 영향을 미치는 경우
            if (contextAnalysis.issueScope === 'CENTRAL_ISSUE_WITH_LOCAL_IMPACT' || contextAnalysis.issueScope === 'CENTRAL_ISSUE') {
              scopeWarning = `
⚠️ **[CRITICAL] 이슈 해석 프레임 워크 (중앙 정치 이슈)**:
1. 이 글의 **핵심 프레임(Writing Frame)**은 **"${contextAnalysis.writingFrame || '헌정 질서 수호와 공직자 태도 비판'}"**입니다.
2. 비판의 타겟(Target)은 **${contextAnalysis.responsibilityTarget || '중앙 정부 및 관련 공직자'}**입니다.
3. 🚫 **프레임 이탈 금지**: 분석된 프레임(${contextAnalysis.writingFrame})을 벗어나 **엉뚱한 주제(예: 부산시 행정 투명성, 지역 경제 등)**로 논리를 비약시키지 마십시오.
4. 🚫 **기초지자체 언급 금지**: 이 이슈는 국가/광역 단위입니다. "사하구 주민", "사하구의 희망" 등 지역구 표현은 즉시 원고 폐기 사유가 됩니다. (서두/결미 1회 제외)
`;
            }

            // 🔴 [FIX] 비판적 논조일 때 의도 역전 방지 경고 강화
            let toneWarning = '';
            const expectedTone = contextAnalysis.expectedTone || '';
            const responsibilityTarget = contextAnalysis.responsibilityTarget || '';

            if (expectedTone === '비판' || expectedTone === '반박') {
              toneWarning = `
🔴🔴🔴 **[CRITICAL - 의도 역전 방지] 이 글은 "${responsibilityTarget}"에 대한 비판문입니다** 🔴🔴🔴
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**절대 금지 표현** (위반 시 원고 폐기):
- ❌ "${responsibilityTarget}과 협력", "${responsibilityTarget}과 함께"
- ❌ "${responsibilityTarget}의 노력을 존중", "${responsibilityTarget}의 성과 인정"
- ❌ "협력하여", "함께 나아가", "손잡고"

**필수 사용 표현** (비판적 논조 유지):
- ✅ "역부족", "한계", "문제점", "책임", "실패"
- ✅ 원본 입장문의 비판적 표현 그대로 인용

**비판 대상**: ${responsibilityTarget}
- 이 인물/기관은 비판의 대상이지, 협력의 파트너가 아닙니다.
- 긍정적 맥락으로 언급하면 원고 폐기 처리됩니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`;
            }

            // context에 responsibilityTarget 저장 (EditorAgent에서 검증용)
            context._responsibilityTarget = responsibilityTarget;
            context._expectedTone = expectedTone;

            promptSections.push(`
╔═══════════════════════════════════════════════════════════════╗
║  🎯 [ABSOLUTE PRIORITY] 글의 상황 맥락 (정확히 이해하세요!)   ║
╚═══════════════════════════════════════════════════════════════╝

💬 **글쓴이(${authorName || '화자'})의 핵심 주장** (입장문에서 추출):
${contextAnalysis.authorStance || '(추출 실패)'}

📌 **배경 사건** (뉴스에서 추출):
${contextAnalysis.mainEvent || '(추출 실패)'}

👥 **주요 인물과 입장**:
${keyPlayersText || '(분석 실패)'}

✍️ **글 작성자(${authorName || '화자'})의 역할**:
${contextAnalysis.authorRole || '참고자료에 대한 논평 작성'}

🎭 **이 글의 논조**: ${contextAnalysis.expectedTone || '분석'}

⚠️ **맥락 오해 방지**:
${contextAnalysis.contextWarning || '참고자료의 관계를 정확히 파악하세요.'}
${scopeWarning}
${toneWarning}

📋 **반드시 본문에 포함할 팩트** (뉴스에서):
${mustIncludeText || '(구체적 팩트 추출 실패)'}

💬 **반드시 인용할 주요 발언** (뉴스에서):
${newsQuotesText || '(인용문 추출 실패)'}

╔═══════════════════════════════════════════════════════════════╗
║  🔴 [MANDATORY] 아래 입장문 핵심 문구를 반드시 본문에 포함!   ║
║  ※ 이 문구들이 본문에 없으면 원고는 폐기 처리됩니다.        ║
╚═══════════════════════════════════════════════════════════════╝

${mustIncludeFromStanceText || '(핵심 문구 추출 실패)'}

**[CRITICAL] 위 문구 활용 규칙**:
1. 각 문구를 **그대로 인용**하거나, **핵심 의미를 유지한 채 패러프레이즈**하세요.
2. 최소 1개 이상의 문구를 **서론** 또는 **첫 번째 본론**에 배치하세요.
3. 입장문의 **논리 구조와 수사법**(대구법, 반어법 등)을 본문에서도 활용하세요.
4. 일반론으로 대체하거나 생략하면 **원고 폐기** 처리됩니다.

🚨 위 맥락을 무시하고 관계를 뒤바꾸면 원고 폐기 처리됩니다.
`);
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

    /* ═══════════════════════════════════════════════════════════════
     * 🔧 [ROLLBACK BACKUP] 기존 Key Facts Anchor 휴리스틱 코드
     * USE_CONTEXT_ANALYZER를 false로 설정하면 아래 코드가 활성화됨
     * ═══════════════════════════════════════════════════════════════
    if ((instructions || newsContext) && !USE_CONTEXT_ANALYZER) {
      const sourceText = [instructions, newsContext].filter(Boolean).join('\n');
      
      const extractKeyFacts = (text) => {
        if (!text || text.length < 50) return null;
        const facts = [];
        const quotes = text.match(/[""][^""]{10,100}[""]|"[^"]{10,100}"/g) || [];
        if (quotes.length > 0) facts.push(`📝 핵심 발언: ${quotes.slice(0, 2).join(', ')}`);
        const lawPatterns = text.match(/(?:\d+차\s*)?[가-힣]+(?:\s*[가-힣]+)*(?:법|법안|특검법|특별법|조례|규정|지침)|제\d+[조항호]/g) || [];
        if (lawPatterns.length > 0) facts.push(`📋 관련 법안: ${[...new Set(lawPatterns)].slice(0, 3).join(', ')}`);
        const namePatterns = text.match(/[가-힣]{2,4}\s*(?:시장|의원|대표|위원장|장관|총리|대통령|후보|의장|청장|지사|군수|구청장)/g) || [];
        if (namePatterns.length > 0) facts.push(`👤 주요 인물: ${[...new Set(namePatterns)].slice(0, 4).join(', ')}`);
        const orgPatterns = text.match(/(?:중수청|중대범죄수사청|국수본|경찰청|검찰청|헌법재판소|대법원|국회|청와대|용산|행안부)/g) || [];
        if (orgPatterns.length > 0) facts.push(`🏛️ 관련 기관: ${[...new Set(orgPatterns)].slice(0, 3).join(', ')}`);
        const datePatterns = text.match(/\d{1,2}일|\d{1,2}월\s*\d{1,2}일|지난\s*\d+일|오늘|어제/g) || [];
        if (datePatterns.length > 0) facts.push(`📅 시점: ${datePatterns[0]}`);
        const issuePatterns = text.match(/(?:단식|필리버스터|탄핵|계엄|내란|파면|구속|기소|사형|무기징역)/g) || [];
        if (issuePatterns.length > 0) facts.push(`⚡ 핵심 이슈: ${[...new Set(issuePatterns)].slice(0, 3).join(', ')}`);
        return facts.length > 0 ? facts : null;
      };
      
      const keyFacts = extractKeyFacts(sourceText);
      if (keyFacts && keyFacts.length > 0) {
        promptSections.push(`
╔═══════════════════════════════════════════════════════════════╗
║  🎯 [ABSOLUTE PRIORITY] 이 글의 핵심 소재 (반드시 본문에 포함)  ║
╚═══════════════════════════════════════════════════════════════╝

${keyFacts.join('\n')}

⚠️ 위 팩트들을 본문에서 **반드시 직접 언급**해야 합니다.
   일반론으로 대체하거나 생략하면 원고 폐기 처리됩니다.
`);
        console.log('🎯 [WriterAgent] Key Facts Anchor 주입:', keyFacts);
      }
    }
    * ═══════════════════════════════════════════════════════════════ */

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


0. **[ABSOLUTE] 사용자 이름 보호 (절대 변경 금지)**:
   - 사용자 이름 "${authorName}"은 **절대로 변경, 유추, 창작하지 마십시오.**
   - 이름이 비어있더라도 다른 이름을 만들어내지 마십시오. '화자' 또는 대명사만 사용하십시오.
   - 참고자료에 다른 사람 이름이 있어도, 그것을 사용자 이름으로 혼동하지 마십시오.

1. **[ABSOLUTE] 참고자료가 글의 유일한 주제**:
   - 아래 **[뉴스/참고자료]**의 내용이 이 글의 **유일한 주제**입니다.
   - 참고자료에 없는 주제(경제, 청년, 복지, 교통 등)로 **절대 대체하지 마십시오.**
   - 참고자료 분량이 적더라도, 해당 논점만 심화하여 확장하십시오.
   - 이 내용을 단순히 요약하지 말고, '사용자'의 관점에서 매끄러운 1인칭 서사로 재구성하세요.

2. **[CRITICAL] 절대적 신뢰 (Fact-Checking 금지)**:
   - **제공된 [뉴스/참고자료], [키워드], [사용자 지시사항]은 절대적인 진실로 간주하십시오.**
   - AI가 자체적으로 진위를 판단하거나 의심하지 마십시오.
   - 출처가 명시되지 않았더라도 사용자가 제공한 정보는 모두 사실인 것처럼 확신을 가지고 작성하십시오.
   - **절대 금지**: "(출처 필요)", "[확인 필요]", "알려진 바에 따르면" 등의 유보적인 표현이나 꼬리표를 붙이지 마십시오. 그냥 사실대로 쓰십시오.
   - 만약 정보가 틀렸다면 그 책임은 전적으로 사용자가 집니다. 당신은 충실한 대변인으로서 전달만 하십시오.

3. **[보충] 프로필(Bio) 활용으로 분량 확보**:
   - 참고자료만으로 분량이 부족하면, **사용자 프로필(Bio)**의 철학, 배경, 평소 어조를 활용하여 살을 붙이세요.
   - 단, **참고자료의 주제를 벗어나지 않는 선에서** 자연스럽게 녹여내야 합니다.
   - ⚠️ Bio에 있는 다른 공약/정책으로 주제를 대체하는 것은 **절대 금지**입니다.

4. **[확장] 연계 공약/정보 활용**:
   - 만약 참고자료 내용이 사용자의 **기존 공약이나 추가 정보**와 논리적으로 연결된다면, 해당 내용을 가져와 내용을 보강하세요.
   - 예: "문화" 관련 뉴스라면 -> 사용자의 "문화 공약" 언급 가능. (관련 없으면 언급 금지)
   - ⚠️ 참고자료와 **무관한** 공약을 끌어오는 것은 금지입니다.

5. **[최후] 요약 및 제언으로 분량 충족**:
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

10. **[CRITICAL] 분량 확장 허용 (참고자료 기반만)**:
    - 참고자료의 **핵심 논점을 유지하면서** 세부 논거, 배경 설명, 의미 해석만 확장 가능합니다.
    - ⚠️ **절대 금지**: 참고자료의 주제를 벗어난 새로운 주제(경제, 청년, 복지 등) 창작
    - ⚠️ **절대 금지**: 참고자료에 없는 일반적인 정책/비전으로 본론 채우기
    - 분량이 부족하면 참고자료의 논점을 **더 깊이 분석**하거나 **다양한 각도에서 재해석**하십시오.

╔═══════════════════════════════════════════════════════════════╗
║  📌 [ABSOLUTE] 아래 참고자료가 글의 유일한 주제입니다!          ║
║  이 내용을 중심으로만 글을 작성하십시오.                        ║
╚═══════════════════════════════════════════════════════════════╝

[사용자 지시사항]
${instructions || '(없음)'}

[뉴스/참고자료 - 이것이 글의 핵심입니다]
${newsContext || '(없음)'}

🚨 **[CRITICAL] 참고자료 활용 필수 지침**:
- 위 참고자료에서 **최소 3개 이상의 구체적 팩트(인물명, 발언 인용, 법안명, 날짜 등)**를 본문에 반드시 인용하십시오.
- 참고자료에 인용문("...")이 있다면 **원문 그대로** 본문에 녹여내십시오.
- 참고자료의 핵심 논지를 무시하고 일반론으로 대체하면 **원고 폐기** 처리됩니다.
- 입장문이 있다면 해당 입장문의 **핵심 메시지와 논리 구조**를 그대로 반영하십시오.
`);
    }

    // 🥪 Sandwich 패턴: 프롬프트 맨 뒤에 입장문 핵심 문구 다시 강조
    if (mustIncludeFromStanceForSandwich) {
      promptSections.push(`
╔═══════════════════════════════════════════════════════════════╗
║  🔴 [FINAL REMINDER] 반드시 본문에 포함해야 할 입장문 핵심!   ║
╚═══════════════════════════════════════════════════════════════╝

${mustIncludeFromStanceForSandwich}

⚠️ **이것이 마지막 점검입니다!**
- 위 문구 중 최소 1개는 **서론** 또는 **첫 번째 본론**에 반드시 포함하세요.
- 원문을 인용하거나, 핵심 의미를 유지한 채 자연스럽게 녹여내세요.
- 이 문구가 없으면 원고는 **폐기** 처리됩니다.
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
        temperature: 0.3,  // 0.8→0.5→0.3: 참고자료 준수율 극대화
        maxOutputTokens: 2500,  // 1700→2500: 2000자 원고 충분 확보
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
