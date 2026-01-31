'use strict';

/**
 * TopicClassifier - 주제 기반 writingMethod 자동 분류
 * 
 * 사용자가 카테고리를 선택하지 않아도, 주제(topic)를 분석하여
 * 적합한 writingMethod를 자동으로 결정합니다.
 */

const { GoogleGenerativeAI } = require('@google/generative-ai');
const { getGeminiApiKey } = require('../../common/secrets');

// writingMethod 정의 (프롬프트 내 설명용)
const WRITING_METHODS = {
    emotional_writing: '감사, 축하, 격려, 일상 공유 등 따뜻하고 감성적인 글',
    logical_writing: '정책 제안, 공약 발표, 성과 보고 등 논리적이고 설득력 있는 글',
    critical_writing: '비판적 논평, 가짜뉴스 반박, 시사 논평 등 날카로운 비판이 필요한 글',
    diagnostic_writing: '현안 진단, 문제 분석, 원인 규명 등 심층 분석이 필요한 글',
    analytical_writing: '지역 현안 분석, 해결책 제시, 민원 처리 보고 등 분석적인 글',
    direct_writing: '의정활동 보고, 국정감사 활동, 법안 발의 등 직접적인 활동 보고'
};

// 키워드 기반 빠른 분류 (LLM 호출 전 사전 필터링)
const KEYWORD_PATTERNS = {
    critical_writing: [
        /비판|논평|반박|규탄|성토|심판|퇴진|탄핵|사퇴|구속|기소|수사|부패|비리|의혹/,
        /사형|구형|판결|재판|검찰|수사|기소|공소/
    ],
    emotional_writing: [
        /감사|축하|격려|응원|위로|추모|기념|명절|새해|설날|추석|어버이|스승/,
        /생일|결혼|출산|졸업|입학|취업/
    ],
    logical_writing: [
        /예산|확보|공약|정책|제안|발표|계획|추진|성과|달성|이행/
    ],
    analytical_writing: [
        /지역|현안|민원|교통|주거|환경|시설|개선|해결책/
    ],
    direct_writing: [
        /국정감사|국감|의정활동|법안|조례|위원회|회의|본회의/
    ]
};

/**
 * 키워드 기반 빠른 분류 (LLM 호출 없이)
 * @param {string} topic - 주제
 * @returns {string|null} - 매칭된 writingMethod 또는 null
 */
function quickClassify(topic) {
    for (const [method, patterns] of Object.entries(KEYWORD_PATTERNS)) {
        for (const pattern of patterns) {
            if (pattern.test(topic)) {
                return method;
            }
        }
    }
    return null;
}

/**
 * LLM 기반 주제 분류
 * @param {string} topic - 주제
 * @returns {Promise<{writingMethod: string, confidence: number}>}
 */
async function classifyWithLLM(topic) {
    const apiKey = getGeminiApiKey();
    if (!apiKey) {
        console.warn('⚠️ [TopicClassifier] API 키 없음, 기본값 반환');
        return { writingMethod: 'emotional_writing', confidence: 0.5 };
    }

    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({ model: 'gemini-2.0-flash' });

    const methodDescriptions = Object.entries(WRITING_METHODS)
        .map(([key, desc]) => `- ${key}: ${desc}`)
        .join('\n');

    const prompt = `당신은 정치인 블로그 글의 작법(writing style)을 분류하는 전문가입니다.

아래 주제에 가장 적합한 작법을 **하나만** 선택하세요.

[주제]
"${topic}"

[작법 목록]
${methodDescriptions}

[판단 기준]
- 비판, 논평, 반박, 규탄 → critical_writing
- 감사, 축하, 격려, 일상 → emotional_writing  
- 정책, 공약, 성과, 예산 → logical_writing
- 현안 진단, 문제 분석 → diagnostic_writing
- 지역 현안, 민원, 해결책 → analytical_writing
- 의정활동, 국감, 법안 → direct_writing

반드시 아래 JSON 형식으로만 응답하세요:
{"writingMethod": "선택한_작법", "confidence": 0.0~1.0}`;

    try {
        const result = await model.generateContent({
            contents: [{ role: 'user', parts: [{ text: prompt }] }],
            generationConfig: {
                responseMimeType: 'application/json',
                temperature: 0.1,
                maxOutputTokens: 100
            }
        });

        const text = result.response.text();
        const parsed = JSON.parse(text);

        // 유효성 검사
        if (!WRITING_METHODS[parsed.writingMethod]) {
            console.warn(`⚠️ [TopicClassifier] 알 수 없는 작법: ${parsed.writingMethod}`);
            return { writingMethod: 'emotional_writing', confidence: 0.5 };
        }

        return {
            writingMethod: parsed.writingMethod,
            confidence: parsed.confidence || 0.8
        };
    } catch (error) {
        console.error('❌ [TopicClassifier] LLM 분류 실패:', error.message);
        return { writingMethod: 'emotional_writing', confidence: 0.5 };
    }
}

/**
 * 주제 분류 메인 함수
 * 1. 키워드 매칭으로 빠른 분류 시도
 * 2. 실패 시 LLM 호출
 * 
 * @param {string} topic - 주제
 * @returns {Promise<{writingMethod: string, confidence: number, source: string}>}
 */
async function classifyTopic(topic) {
    if (!topic || topic.trim().length < 3) {
        return { writingMethod: 'emotional_writing', confidence: 0.5, source: 'default' };
    }

    // 1. 키워드 기반 빠른 분류
    const quickResult = quickClassify(topic);
    if (quickResult) {
        console.log(`⚡ [TopicClassifier] 키워드 매칭: ${quickResult}`);
        return { writingMethod: quickResult, confidence: 0.9, source: 'keyword' };
    }

    // 2. LLM 분류
    console.log(`🤖 [TopicClassifier] LLM 분류 시작: "${topic.substring(0, 50)}..."`);
    const llmResult = await classifyWithLLM(topic);
    console.log(`🤖 [TopicClassifier] LLM 결과: ${llmResult.writingMethod} (${llmResult.confidence})`);

    return { ...llmResult, source: 'llm' };
}

module.exports = {
    classifyTopic,
    quickClassify,
    WRITING_METHODS
};
