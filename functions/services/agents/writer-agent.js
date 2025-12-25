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

// ✅ 기존 templates 100% 보존하여 import
const { buildDailyCommunicationPrompt } = require('../../prompts/templates/daily-communication');
const { buildLogicalWritingPrompt } = require('../../prompts/templates/policy-proposal');
const { buildActivityReportPrompt } = require('../../prompts/templates/activity-report');
const { buildCriticalWritingPrompt } = require('../../prompts/templates/current-affairs');
const { buildLocalIssuesPrompt } = require('../../prompts/templates/local-issues');

// ✅ 기존 utils 보존하여 import
const { generateNonLawmakerWarning, generateFamilyStatusWarning } = require('../../prompts/utils/non-lawmaker-warning');

// 카테고리 → 작법 매핑
const CATEGORY_TO_WRITING_METHOD = {
  'daily': 'emotional_writing',
  'activity': 'direct_writing',
  'policy': 'logical_writing',
  'current': 'critical_writing',
  'local': 'analytical_writing'
};

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
      previousResults = {}
    } = context;

    const ai = getGenAI();
    if (!ai) {
      throw new Error('Gemini API 키가 설정되지 않았습니다');
    }

    // 1. KeywordAgent 결과 활용
    const keywordResult = previousResults.KeywordAgent;
    const keywords = keywordResult?.data?.keywords || [];
    const keywordStrings = keywords.slice(0, 5).map(k => k.keyword || k);

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
      keywords: keywordStrings,
      targetWordCount,
      personalizedHints,
      newsContext,
      // 원외 인사 판단용
      isCurrentLawmaker: this.isCurrentLawmaker(userProfile),
      politicalExperience: userProfile.politicalExperience || '정치 신인',
      // 가족 상황 (자녀 환각 방지)
      familyStatus: userProfile.familyStatus || ''
    });

    // 6. 경고문 주입
    prompt = this.injectWarnings(prompt, userProfile, authorBio);

    // 7. 타 지역 주제 힌트
    if (context.regionHint) {
      prompt = context.regionHint + '\n\n' + prompt;
    }

    console.log(`📝 [WriterAgent] 프롬프트 생성 완료 (${prompt.length}자, 작법: ${writingMethod})`);

    // 8. Gemini 호출
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

    // 9. JSON 파싱
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
      keywordsUsed: keywordStrings
    };
  }

  /**
   * 저자 Bio 구성
   */
  buildAuthorBio(userProfile) {
    const name = userProfile.name || '사용자';
    const position = userProfile.position || '';
    const regionLocal = userProfile.regionLocal || '';
    const regionMetro = userProfile.regionMetro || '';

    let region = '';
    if (regionLocal && regionMetro) {
      region = `${regionMetro} ${regionLocal}`;
    } else if (regionMetro) {
      region = regionMetro;
    } else if (regionLocal) {
      region = regionLocal;
    }

    const parts = [name];
    if (position) parts.push(position);
    if (region) parts.push(region);

    return parts.join(', ');
  }

  /**
   * 현역 의원 여부 판단
   */
  isCurrentLawmaker(userProfile) {
    const experience = userProfile.politicalExperience || '';
    return ['초선', '재선', '3선이상'].includes(experience);
  }

  /**
   * 경고문 주입 (원외 인사, 가족 상황)
   */
  injectWarnings(prompt, userProfile, authorBio) {
    // 원외 인사 경고
    const nonLawmakerWarning = generateNonLawmakerWarning({
      isCurrentLawmaker: this.isCurrentLawmaker(userProfile),
      politicalExperience: userProfile.politicalExperience,
      authorBio
    });

    if (nonLawmakerWarning) {
      prompt = nonLawmakerWarning + '\n\n' + prompt;
    }

    // 가족 상황 경고 (자녀 환각 방지)
    const familyWarning = generateFamilyStatusWarning({
      familyStatus: userProfile.familyStatus
    });

    if (familyWarning) {
      prompt = familyWarning + '\n\n' + prompt;
    }

    return prompt;
  }
}

module.exports = { WriterAgent };
