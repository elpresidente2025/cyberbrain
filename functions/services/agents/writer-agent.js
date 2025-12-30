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
const { buildCriticalWritingPrompt } = require('../../prompts/templates/current-affairs');
const { buildLocalIssuesPrompt } = require('../../prompts/templates/local-issues');

// ✅ 기존 utils 보존하여 import
const { generateNonLawmakerWarning, generateFamilyStatusWarning } = require('../../prompts/utils/non-lawmaker-warning');

// ✅ 카테고리 매핑은 constants.js에서 import (단일 소스)
const { CATEGORY_TO_WRITING_METHOD } = require('../../utils/posts/constants');

// 작법 → 템플릿 빌더 매핑
const TEMPLATE_BUILDERS = {
  'emotional_writing': buildDailyCommunicationPrompt,
  'logical_writing': buildLogicalWritingPrompt,
  'direct_writing': buildActivityReportPrompt,
  'critical_writing': buildCriticalWritingPrompt,
  'analytical_writing': buildLocalIssuesPrompt
};

let genAI = null;
function getGenAI() {
  if (!genAI) {
    const apiKey = process.env.GEMINI_API_KEY;
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
      userProfile = {},
      memoryContext = '',
      instructions = '',
      newsContext = '',
      targetWordCount = 1700,
      userKeywords = [],  // 🔑 사용자 직접 입력 키워드 (최우선)
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

    // 2. 작법 결정
    const writingMethod = CATEGORY_TO_WRITING_METHOD[category] || 'emotional_writing';

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
    const writingExamples = getWritingExamples(category);
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

    // 6.4 검색어 CRITICAL 섹션 (SEO 필수 삽입)
    if (userKeywords && userKeywords.length > 0) {
      const searchTermList = userKeywords.map((kw, i) => `  ${i + 1}. "${kw}"`).join('\n');
      promptSections.push(`╔═══════════════════════════════════════════════════════════════╗
║  🔍 [CRITICAL] 노출 희망 검색어 - SEO 필수 삽입!               ║
╚═══════════════════════════════════════════════════════════════╝

사용자가 입력한 검색어 (네이버 검색 노출용):
${searchTermList}

[삽입 규칙]
✅ 각 검색어를 본문에 **최소 2회 이상** 자연스럽게 포함하세요.
✅ 도입부(첫 문단)에 반드시 1회 포함하세요.
✅ 검색어는 문맥에 녹여서 자연스럽게 사용하세요.

❌ 절대 금지:
- 검색어를 콤마로 나열 금지. 예: "부산, 대형병원, 순위에 대해" (X)
- 한 문장에 여러 검색어 몰아넣기 금지.

✅ 좋은 예: "부산 대형병원 순위가 해마다 하락하고 있습니다."
❌ 나쁜 예: "부산, 대형병원, 순위에 대한 이야기입니다."`);
    }

    // 6.5 제목 가이드라인
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

    // 6.8 본문 템플릿 (맨 마지막)
    promptSections.push(prompt);

    // 최종 프롬프트 조립
    prompt = promptSections.join('\n\n');

    console.log(`📝 [WriterAgent] 프롬프트 생성 완료 (${prompt.length}자, 작법: ${writingMethod}, 섹션: ${promptSections.length}개)`);

    // 9. Gemini 호출
    const model = ai.getGenerativeModel({ model: 'gemini-2.0-flash-exp' });

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
      console.log(`🗳️ [WriterAgent] 선거법 지시문 주입: ${electionStage.name} (상태: ${status})`);
      return electionStage.promptInstruction.trim();
    }

    return '';
  }
}

module.exports = { WriterAgent };
