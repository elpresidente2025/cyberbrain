const { GoogleGenerativeAI } = require('@google/generative-ai');
const { getGeminiApiKey } = require('../common/secrets');

// 정량적 분석 유틸리티
const METRICS_ANALYZER = {
    // 1. 문장 길이 및 호흡 분석
    analyzeSentenceLength: (text) => {
        // 문장 분리 (마침표, 물음표, 느낌표 기준)
        const sentences = text.match(/[^.!?]+[.!?]+/g) || [];
        if (sentences.length === 0) return { avg: 0, distinct: 'N/A' };

        const lengths = sentences.map((s) => s.trim().length);
        const total = lengths.reduce((a, b) => a + b, 0);
        const avg = Math.round(total / lengths.length);

        // 호흡 판단
        let distinct = '중간 호흡 (40~60자)';
        if (avg < 40) distinct = '짧고 간결한 호흡 (단문 위주)';
        else if (avg > 70) distinct = '길고 논리적인 호흡 (만연체 경향)';

        return { avg, distinct, count: sentences.length };
    },

    // 2. 종결 어미 패턴 분석 (규칙 기반)
    analyzeEndingPatterns: (text) => {
        const patterns = {
            '합쇼체(격식)': /합니다|습니다|입니다|습니까|십시요/g,
            '해요체(비격식)': /해요|데요|나요|가요/g,
            '해라체(권위/선언)': /한다|했다|이다|겠다/g,
            '청유형(제안)': /합시다|자|시죠/g,
        };

        const counts = {};
        let totalMatches = 0;

        for (const [key, regex] of Object.entries(patterns)) {
            const matches = text.match(regex);
            const count = matches ? matches.length : 0;
            counts[key] = count;
            totalMatches += count;
        }

        // 비율 계산
        const ratios = {};
        if (totalMatches > 0) {
            for (const [key, count] of Object.entries(counts)) {
                if (count > 0) {
                    ratios[key] = `${Math.round((count / totalMatches) * 100)}%`;
                }
            }
        }

        return { counts, ratios };
    },
};

/**
 * 텍스트(Bio, 연설문 등)를 분석하여 스타일 프로필을 생성하는 함수
 * @param {string} text - 분석할 텍스트
 * @return {Promise<Object|null>} 스타일 프로필 JSON 객체
 */
async function extractStyleFromText(text) {
    if (!text || text.length < 50) {
        return null; // 텍스트가 너무 짧으면 분석 불가
    }

    // 1. 정량 분석 실행
    const sentenceMetrics = METRICS_ANALYZER.analyzeSentenceLength(text);
    const endingMetrics = METRICS_ANALYZER.analyzeEndingPatterns(text);

    // 2. 정성 분석 (LLM 호출)
    const apiKey = getGeminiApiKey();
    if (!apiKey) {
        console.error('Gemini API 키가 없습니다.');
        return {
            metrics: {
                sentence_length: sentenceMetrics,
                ending_patterns: endingMetrics,
            },
            persona_summary: 'API 키 누락으로 분석 불가',
            signature_keywords: [],
            tone_manner: '알 수 없음',
        };
    }

    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({
        model: 'gemini-2.0-flash',
        generationConfig: { responseMimeType: 'application/json' },
    });

    const prompt = `
당신은 문체 분석 전문가(Stylometry Expert)입니다. 
아래 텍스트는 한 정치인의 프로필(Bio) 또는 과거 글입니다.
이 텍스트를 심층 분석하여, 이 사람의 '글쓰기 스타일(Persona)'을 정의하는 JSON을 생성하십시오.

[분석 대상 텍스트]
"""
${text.substring(0, 3000)}
"""

[지시사항]
다음 구조의 JSON 객체만 출력하십시오. (부연 설명 금지)
{
  "persona_summary": "이 사람의 캐릭터를 한 문장으로 요약",
  "signature_keywords": ["정체성 키워드 3~5개"],
  "tone_manner": "말투 특징",
  "narrative_strategy": "서사 전략",
  "forbidden_style": "절대 쓰지 않는 어색한 문체"
}
`;

    try {
        const result = await model.generateContent(prompt);
        const response = await result.response;
        const jsonStr = response.text().trim();

        // JSON 파싱
        let qualitativeData = {};
        try {
            qualitativeData = JSON.parse(jsonStr);
        } catch (e) {
            const cleanJson = jsonStr.replace(/```json|```/g, '').trim();
            try {
                qualitativeData = JSON.parse(cleanJson);
            } catch (e2) {
                console.warn('스타일 분석 JSON 파싱 최종 실패', jsonStr);
                qualitativeData = { raw_analysis: jsonStr };
            }
        }

        return {
            metrics: {
                sentence_length: sentenceMetrics,
                ending_patterns: endingMetrics,
            },
            ...qualitativeData,
        };
    } catch (error) {
        console.error('스타일 추출 중 오류 발생:', error);
        return {
            metrics: {
                sentence_length: sentenceMetrics,
                ending_patterns: endingMetrics,
            },
            persona_summary: '분석 실패 (기본값 사용)',
            signature_keywords: [],
            tone_manner: '정중하고 차분한',
        };
    }
}

module.exports = { extractStyleFromText };
