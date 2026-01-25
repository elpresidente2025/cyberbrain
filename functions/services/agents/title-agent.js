'use strict';

const { BaseAgent } = require('./base');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { getGeminiApiKey } = require('../../common/secrets');

let genAI = null;
function getGenAI() {
    if (!genAI) {
        const apiKey = getGeminiApiKey();
        if (!apiKey) return null;
        genAI = new GoogleGenerativeAI(apiKey);
    }
    return genAI;
}

// 🆕 title-generation.js의 고급 로직 사용
const { generateAndValidateTitle } = require('../../prompts/builders/title-generation');

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
            topic = '',  // 🆕 사용자가 입력한 주제
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
        const status = userProfile?.status || '준비'; // 준비/현역/예비후보
        const authorName = userProfile.name || '이재성';

        // 사용자 키워드와 추출된 키워드 병합
        const allKeywords = [
            ...userKeywords,
            ...(extractedKeywords || []).map(k => k.keyword || k)
        ].filter(Boolean);

        // 배경 정보 추출 (뉴스, 지시사항 등)
        const backgroundText = [
            context.instructions,
            context.newsContext
        ].filter(Boolean).join('\n').substring(0, 500);

        console.log(`🏷️ [TitleAgent] 주제: "${topic}", 키워드: [${allKeywords.join(', ')}]`);
        if (titleSource) {
            console.log(`🏷️ [TitleAgent] 기존 제목 참고 (미사용): "${titleSource}"`);
        }

        // 🟢 [Refactored] generateAndValidateTitle 사용
        // LLM 호출 함수 (generateAndValidateTitle 내부에서 사용)
        const generateFn = async (prompt) => {
            const ai = getGenAI();
            if (!ai) throw new Error('Gemini API 키가 설정되지 않았습니다');

            const model = ai.getGenerativeModel({ model: 'gemini-2.5-flash' });
            const result = await model.generateContent({
                contents: [{ role: 'user', parts: [{ text: prompt }] }],
                generationConfig: {
                    temperature: 0.8, // 창의성 위해 약간 높임
                    maxOutputTokens: 1000
                    // JSON 모드 사용 안 함 (generateAndValidateTitle이 텍스트 파싱 처리)
                }
            });
            const text = result.response.text();

            // JSON 파싱 (title-generation.js는 순수 제목 텍스트 반환을 기대하므로 파싱 필요)
            try {
                // 마크다운 코드 블록 제거
                const cleanText = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
                const parsed = JSON.parse(cleanText);
                return parsed.title || cleanText;
            } catch (e) {
                // JSON이 아니면 텍스트에서 제목 추출 시도 (Title: "...")
                const match = text.match(/제목:\s*"([^"]+)"/);
                if (match) return match[1];
                return text.trim(); // 최후의 수단: 전체 텍스트
            }
        };

        // 파라미터 구성
        const params = {
            contentPreview: content.substring(0, 3000), // 본문 미리보기
            backgroundText, // 뉴스/지시사항 배경 정보
            topic,
            fullName: authorName,
            keywords: allKeywords, // 병합된 전체 키워드
            userKeywords,
            category,
            subCategory,
            status,
            titleScope: context.titleScope || null, // 지역 스코프 (광역/기초)
            _forcedType: null
        };

        // 제목 생성 및 검증 실행 (자동 재시도 포함)
        const result = await generateAndValidateTitle(generateFn, params, {
            minScore: 70,    // 70점 이상 통과
            maxAttempts: 3,  // 최대 3회 시도
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

module.exports = { TitleAgent };
