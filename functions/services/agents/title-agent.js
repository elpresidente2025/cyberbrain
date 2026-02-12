'use strict';

/**
 * functions/services/agents/title-agent.js
 *
 * 통합된 TitleAgent - 제목 생성 + 검증 + SEO 최적화
 * (prompts/builders/title-generation.js 활용)
 *
 * 핵심 원칙:
 * - 25자 이내 (네이버 검색결과 최적화)
 * - 콘텐츠 구조(유형) 기반 분류
 * - AEO(AI 검색) 최적화
 * - 선거법 준수
 */

const { BaseAgent } = require('./base');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { getGeminiApiKey } = require('../../common/secrets');

// ✅ Shared Logic Import
const {
    generateAndValidateTitle,
    // Exports for backward compatibility if needed
    buildTitlePrompt,
    buildTitlePromptWithType,
    detectContentType,
    TITLE_TYPES,
    KEYWORD_POSITION_GUIDE,
    getElectionComplianceInstruction,
    getKeywordStrategyInstruction,
    getTitleGuidelineForTemplate,
    extractNumbersFromContent,
    validateThemeAndContent,
    calculateTitleQualityScore
} = require('../../prompts/builders/title-generation');

let genAI = null;
function getGenAI() {
    if (!genAI) {
        const apiKey = getGeminiApiKey();
        if (!apiKey) return null;
        genAI = new GoogleGenerativeAI(apiKey);
    }
    return genAI;
}

// ============================================================================
// TitleAgent Class
// ============================================================================

class TitleAgent extends BaseAgent {
    constructor() {
        super('TitleAgent');
    }

    getRequiredContext() {
        return ['previousResults', 'userProfile'];
    }

    async execute(context) {
        const {
            previousResults,
            userProfile,
            userKeywords = [],
            extractedKeywords = [],
            topic = '',
            category = '',
            subCategory = ''
        } = context;

        // 본문 가져오기 (WriterAgent 또는 StyleAgent - modular 파이프라인 지원)
        const writerResult = previousResults?.WriterAgent?.data;
        const styleResult = previousResults?.StyleAgent?.data;
        const structureResult = previousResults?.StructureAgent?.data;

        // 우선순위: WriterAgent → StyleAgent → StructureAgent
        const contentSource = writerResult?.content || styleResult?.content || structureResult?.content;
        const titleSource = writerResult?.title || styleResult?.title || structureResult?.title;

        if (!contentSource) {
            throw new Error('본문 내용이 없습니다. WriterAgent 또는 StyleAgent가 먼저 실행되어야 합니다.');
        }

        const content = contentSource;
        const status = userProfile?.status || '준비';
        const authorName = userProfile?.name || '이재성';

        // 사용자 키워드와 추출된 키워드 병합
        const allKeywords = [
            ...userKeywords,
            ...(extractedKeywords || []).map(k => k.keyword || k)
        ].filter(Boolean);

        // 배경 정보 추출
        const backgroundText = [
            context.instructions,
            context.newsContext
        ].filter(Boolean).join('\n').substring(0, 500);

        console.log(`🏷️ [TitleAgent] 주제: "${topic}", 키워드: [${allKeywords.join(', ')}]`);
        if (titleSource) {
            console.log(`🏷️ [TitleAgent] 기존 제목 참고 (미사용): "${titleSource}"`);
        }

        // LLM 호출 함수
        const generateFn = async (prompt) => {
            const ai = getGenAI();
            if (!ai) throw new Error('Gemini API 키가 설정되지 않았습니다');

            const model = ai.getGenerativeModel({ model: 'gemini-2.5-flash' });
            const result = await model.generateContent({
                contents: [{ role: 'user', parts: [{ text: prompt }] }],
                generationConfig: {
                    temperature: 0.8,
                    maxOutputTokens: 1000
                }
            });
            const text = result.response.text();

            try {
                const cleanText = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
                const parsed = JSON.parse(cleanText);
                return parsed.title || cleanText;
            } catch (e) {
                const match = text.match(/제목:\s*"([^"]+)"/);
                if (match) return match[1];
                return text.trim();
            }
        };

        // 파라미터 구성
        const params = {
            contentPreview: content.substring(0, 3000),
            backgroundText,
            topic,
            fullName: authorName,
            keywords: allKeywords,
            userKeywords,
            category,
            subCategory,
            status,
            titleScope: context.titleScope || null,
            _forcedType: null
        };

        // 제목 생성 및 검증 실행 (Builder의 generateAndValidateTitle 사용)
        const result = await generateAndValidateTitle(generateFn, params, {
            minScore: 70,
            maxAttempts: 3,
            onProgress: ({ attempt, score }) => {
                console.log(`🔄 [TitleAgent] 생성 시도 ${attempt} (현재 점수: ${score || 0})`);
            }
        });

        console.log(`✅ [TitleAgent] 최종 제목 확정: "${result.title}" (점수: ${result.score})`);

        return {
            title: result.title,
            score: result.score,
            attempts: result.attempts,
            history: result.history,
            passed: result.passed
        };
    }
}

// ============================================================================
// Exports
// ============================================================================

module.exports = {
    TitleAgent,
    // 외부에서 사용하는 함수들 (하위 호환성 유지)
    buildTitlePrompt,
    buildTitlePromptWithType,
    detectContentType,
    TITLE_TYPES,
    KEYWORD_POSITION_GUIDE,
    getElectionComplianceInstruction,
    getKeywordStrategyInstruction,
    getTitleGuidelineForTemplate,
    extractNumbersFromContent,
    validateThemeAndContent,
    calculateTitleQualityScore,
    generateAndValidateTitle
};
