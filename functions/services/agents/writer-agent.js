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
      userKeywords = [],  // 🔑 사용자 직접 입력 키워드 (최우선)
      previousResults = {}
    } = context;

    const ai = getGenAI();
    if (!ai) {
      throw new Error('Gemini API 키가 설정되지 않았습니다');
    }

    // 1. KeywordAgent 결과 활용 + 사용자 입력 키워드 병합
    const keywordResult = previousResults.KeywordAgent;
    const agentKeywords = keywordResult?.data?.keywords || [];
    const agentKeywordStrings = agentKeywords.slice(0, 5).map(k => k.keyword || k);

    // 🔑 사용자 입력 키워드를 최우선으로, 그 다음 KeywordAgent 결과
    const keywordStrings = [...new Set([...userKeywords, ...agentKeywordStrings])];

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

    // 🗳️ 7. 선거법 준수 지시문 자동 주입 (legal.js 구조적 통합)
    prompt = this.injectElectionLawInstruction(prompt, userProfile);

    // 8. 타 지역 주제 힌트
    if (context.regionHint) {
      prompt = context.regionHint + '\n\n' + prompt;
    }

    // 🔑 9. 사용자 입력 키워드 CRITICAL 섹션 (프롬프트 맨 앞에 추가)
    if (userKeywords && userKeywords.length > 0) {
      const userKeywordsCritical = `
╔═══════════════════════════════════════════════════════════════╗
║  🔑 [CRITICAL] 노출 희망 검색어 - 반드시 원고에 포함!          ║
╚═══════════════════════════════════════════════════════════════╝

사용자가 직접 입력한 검색어: ${userKeywords.join(', ')}

⚠️ 이 키워드는 네이버 검색 노출을 위해 사용자가 직접 입력한 것입니다.
✅ 위 키워드를 원고 본문에 **반드시 최소 2회 이상** 자연스럽게 포함하세요.
✅ 도입부(첫 문단)에 반드시 1회 포함하세요. (SEO 필수)
✅ 키워드를 그대로 사용하세요. 유사어로 대체하지 마세요.

`;
      prompt = userKeywordsCritical + prompt;
    }

    console.log(`📝 [WriterAgent] 프롬프트 생성 완료 (${prompt.length}자, 작법: ${writingMethod})`);

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
      keywordsUsed: keywordStrings
    };
  }

  /**
   * 저자 Bio 구성 (목표 선거 기준 지역 적용)
   */
  buildAuthorBio(userProfile) {
    const name = userProfile.name || '사용자';
    const targetElection = userProfile.targetElection;

    // 🎯 목표 선거가 있으면 해당 직책/지역 기준
    let effectivePosition = userProfile.position || '';
    let region = '';

    if (targetElection && targetElection.position) {
      effectivePosition = targetElection.position;
      const targetPosition = targetElection.position;

      if (targetPosition === '광역자치단체장' || targetPosition.includes('시장') || targetPosition.includes('도지사')) {
        // 광역단체장: 시/도 전체가 관할
        region = targetElection.regionMetro || userProfile.regionMetro || '';
      } else if (targetPosition === '기초자치단체장' || targetPosition.includes('구청장') || targetPosition.includes('군수')) {
        // 기초단체장: 시/군/구 전체가 관할
        const metro = targetElection.regionMetro || userProfile.regionMetro || '';
        const local = targetElection.regionLocal || userProfile.regionLocal || '';
        region = local && metro ? `${metro} ${local}` : metro || local;
      } else {
        // 의원: 선거구 기준
        const metro = targetElection.regionMetro || userProfile.regionMetro || '';
        const electoral = targetElection.electoralDistrict || userProfile.electoralDistrict || '';
        const local = targetElection.regionLocal || userProfile.regionLocal || '';
        region = electoral ? `${metro} ${electoral}` : (local && metro ? `${metro} ${local}` : metro || local);
      }
    } else {
      // 현재 직책 기준 (기존 로직)
      const regionLocal = userProfile.regionLocal || '';
      const regionMetro = userProfile.regionMetro || '';
      if (regionLocal && regionMetro) {
        region = `${regionMetro} ${regionLocal}`;
      } else if (regionMetro) {
        region = regionMetro;
      } else if (regionLocal) {
        region = regionLocal;
      }
    }

    // 신분 상태 확인 (현역/예비)
    const status = userProfile.status || '예비';
    const isIncumbent = status === '현역';

    const parts = [name];

    // 예비/준비 중인 경우 "OO 준비 중" 형태로
    if (effectivePosition) {
      if (isIncumbent) {
        parts.push(effectivePosition);
      } else {
        parts.push(`${effectivePosition} 준비 중`);
      }
    }

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

  /**
   * 🗳️ 선거법 준수 지시문 자동 주입 (legal.js 구조적 통합)
   * userProfile.status에 따라 해당 단계의 promptInstruction을 주입
   */
  injectElectionLawInstruction(prompt, userProfile) {
    const status = userProfile.status || '준비';
    const electionStage = getElectionStage(status);

    if (electionStage && electionStage.promptInstruction) {
      console.log(`🗳️ [WriterAgent] 선거법 지시문 주입: ${electionStage.name} (상태: ${status})`);
      return electionStage.promptInstruction + '\n\n' + prompt;
    }

    return prompt;
  }
}

module.exports = { WriterAgent };
