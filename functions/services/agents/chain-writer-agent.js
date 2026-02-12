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

class ChainWriterAgent extends BaseAgent {
    constructor() {
        super('ChainWriterAgent');
        this.modelName = 'gemini-2.5-flash'; // 품질 최적화 (Lite 제외)
    }

    getRequiredContext() {
        return ['topic', 'userProfile'];
    }

    async execute(context) {
        const { topic, instructions, ragContext, newsContext, userProfile } = context;

        if (!getGenAI()) {
            throw new Error('Gemini API 키가 설정되지 않았습니다.');
        }

        const plan = await this.createPlan(topic, instructions, ragContext, newsContext, userProfile);
        if (!plan) throw new Error('원고 기획에 실패했습니다.');

        console.log(`📝 [ChainWriter] 기획 완료: ${plan.sections.length}개 섹션 집필 시작`);

        const sectionPromises = plan.sections.map((section, index) =>
            this.writeSection(section, index, topic, userProfile)
        );

        const sectionsContent = await Promise.all(sectionPromises);
        const fullContent = sectionsContent.join('\n\n');

        return {
            title: plan.title,
            content: fullContent,
            structure: plan
        };
    }

    async createPlan(topic, instructions, ragContext, newsContext, userProfile) {
        // [NEW] 5개 섹션 구조 고정 - LLM 변동성으로 인한 섹션 누락 방지
        const ai = getGenAI();
        const model = ai.getGenerativeModel({ model: this.modelName });

        // 키워드 추출만 LLM에게 맡김 (구조는 고정)
        let keywords = { keyword1: topic, keyword2: topic, keyword3: topic };
        try {
            const keywordPrompt = `
주제: "${topic}"
참고자료: ${newsContext || '(없음)'}
지시사항: ${instructions || '(없음)'}

위 내용에서 블로그 글의 3개 본론에 사용할 핵심 키워드를 추출하세요.
JSON 형식으로만 응답: {"keyword1": "첫번째 핵심 주제", "keyword2": "두번째 핵심 주제", "keyword3": "세번째 핵심 주제"}
`;
            const result = await model.generateContent({
                contents: [{ role: 'user', parts: [{ text: keywordPrompt }] }],
                generationConfig: { responseMimeType: 'application/json' }
            });
            let responseText = result.response.text().trim();
            if (responseText.startsWith('\`\`\`')) {
                responseText = responseText.replace(/^\`\`\`(?:json)?\\s*/i, '').replace(/\\s*\`\`\`$/, '');
            }
            keywords = JSON.parse(responseText);
            console.log('🔑 [ChainWriter] 추출된 키워드:', keywords);
        } catch (e) {
            console.warn('⚠️ [ChainWriter] 키워드 추출 실패, 기본값 사용:', e.message);
        }

        // 고정된 5개 섹션 구조 반환 (절대 누락되지 않음)
        const fixedPlan = {
            title: topic,
            sections: [
                {
                    type: 'intro',
                    guide: `서론 작성: 1) "${userProfile.name}"의 인사/자기소개(100자), 2) 현 상황의 문제점/공감대 형성(150자), 3) 해결 의지 표명(100자). 총 350자 목표.`
                },
                {
                    type: 'body1',
                    keyword: keywords.keyword1 || topic,
                    guide: `본론1 "${keywords.keyword1 || topic}": 1) 현황/배경 설명(150자), 2) 구체적 실행방안/공약(150자), 3) 기대효과(150자). 총 450자 목표.`
                },
                {
                    type: 'body2',
                    keyword: keywords.keyword2 || topic,
                    guide: `본론2 "${keywords.keyword2 || topic}": 1) 현황/배경 설명(150자), 2) 구체적 실행방안/공약(150자), 3) 기대효과(150자). 총 450자 목표.`
                },
                {
                    type: 'body3',
                    keyword: keywords.keyword3 || topic,
                    guide: `본론3 "${keywords.keyword3 || topic}": 1) 현황/배경 설명(150자), 2) 구체적 실행방안/공약(150자), 3) 기대효과(150자). 총 450자 목표.`
                },
                {
                    type: 'outro',
                    guide: `결론 작성: 1) 핵심 내용 요약(100자), 2) 미래 비전 제시(150자), 3) 지지 호소/마무리 인사(100자). 총 350자 목표.`
                }
            ]
        };

        console.log('📋 [ChainWriter] 고정 구조 기획 완료:', fixedPlan.sections.length, '개 섹션');
        return fixedPlan;
    }

    async writeSection(sectionPlan, index, topic, userProfile) {
        const ai = getGenAI();
        const model = ai.getGenerativeModel({ model: this.modelName });

        const isBody = sectionPlan.type.startsWith('body');
        // 2000자 ±10% 목표 (1800~2200자): 본론 400~500자×3 + 서론/결론 350~400자×2 = 1900~2300자
        const minChars = isBody ? 400 : 350;
        const maxChars = isBody ? 500 : 400;

        let headerInstruction = '';
        if (sectionPlan.type === 'intro') {
            headerInstruction = '서론에는 절대 소제목을 달지 마십시오. "존경하는..." 같은 인사말로 바로 시작하십시오.';
        } else if (sectionPlan.type === 'outro') {
            headerInstruction = '결론의 시작에는 "기대하는 변화" 또는 "맺음말" 같은 소제목을 <h2>태그로 작성하십시오.';
        } else {
            headerInstruction = '가장 먼저 이 문단의 핵심을 꿰뚫는 매력적인 소제목을 <h2>태그로 작성하십시오.';
        }

        const prompt = `당신은 대한민국 최고의 정치 에세이스트입니다.

[Task]
지시된 [가이드]에 따라 **정확히 3개의 문단**을 작성하십시오.

[Context]
- 작성자: ${userProfile.name}
- 주제: ${topic}
- 가이드: ${sectionPlan.guide}
- 목표 분량: **${minChars}~${maxChars}자**

[CRITICAL] 3-Step Paragraph Template (반드시 준수)
1. **첫 번째 문단 (<p>)**: 배경, 현황, 또는 공감 유도 (120~150자)
2. **두 번째 문단 (<p>)**: 핵심 주장, 대안 제시, 또는 구체적 액션 (120~150자)
3. **세 번째 문단 (<p>)**: 기대 효과, 미래 비전, 또는 강력한 호소 (120~150자)

[Absolute Rules]
1. **분량**: **공백 포함 ${minChars}자 미만은 실패**입니다. 쓸 말이 없으면 구체적 예시를 들어 채우십시오.
2. **태그**: 문단마다 <p> 태그 사용. 소제목은 <h2> 사용.
3. **말투**: "~합니다", "~하겠습니다" (자신감 있고 정중하게).
4. ${headerInstruction}`;

        try {
            const result = await model.generateContent({
                contents: [{ role: 'user', parts: [{ text: prompt }] }],
                generationConfig: {
                    temperature: 0.7,
                    maxOutputTokens: 4000
                }
            });
            let text = result.response.text().trim();
            text = text.replace(/```html/g, '').replace(/```/g, '');

            const charCount = text.replace(/<[^>]*>/g, '').length;
            console.log(`✅ [ChainWriter] 섹션 ${index} (${sectionPlan.type}) 생성: ${charCount}자`);

            return text;
        } catch (e) {
            console.error(`❌ [ChainWriter] 섹션 ${index} 작성 실패:`, e);
            return `<p>(섹션 생성 실패: ${sectionPlan.keyword})</p>`;
        }
    }
}

module.exports = { ChainWriterAgent };
