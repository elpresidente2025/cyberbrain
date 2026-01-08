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

class SubheadingAgent extends BaseAgent {
    constructor() {
        super('SubheadingAgent');
        this.modelName = 'gemini-2.0-flash'; // 빠르고 똑똑한 2.0 Flash 사용
    }

    getRequiredContext() {
        return ['content', 'userKeywords'];
    }

    async execute(context) {
        const { content, userKeywords = [] } = context;
        const ai = getGenAI();
        const model = ai.getGenerativeModel({
            model: this.modelName,
            generationConfig: { responseMimeType: "application/json" }
        });

        const prompt = `
# Role
당신은 대한민국 최고의 **AEO(Answer Engine Optimization) & SEO 전문 카피라이터**입니다.
주어진 글의 문단을 분석하여, 검색 엔진과 사용자 모두에게 매력적인 **최적의 소제목(H2)**을 작성해야 합니다.

# Input Data
- **키워드**: ${userKeywords.join(', ')}
- **본문**: 
${content}

# Task
1. 본문 내용 중 **소제목이 필요한 문단 그룹**을 찾으세요. (기존에 소제목이 있다면 그것을 대체합니다.)
2. 각 문단의 핵심 내용을 꿰뚫는 **AEO 최적화 소제목(H2)**을 생성하세요.
3. 생성된 소제목을 적용하여 **전체 HTML을 재구성**하세요.

# [CRITICAL] AEO 소제목(H2) 작성 가이드라인
아래 규칙을 위반할 경우 해고될 수 있습니다. 반드시 준수하세요.

## 1. 필수 요소
- **길이**: **12~25자** (네이버 최적: 15~22자)
- **키워드**: 핵심 키워드를 **문장 앞쪽 1/3**에 배치할 것.
- **형식**: 구체적인 **질문형** 또는 **명확한 명사형**.

## 2. AEO 최적화 유형 (상황에 맞춰 사용)
- **유형 1 (질문형 - AEO 최강)**: 검색자의 의도를 저격.
  - ✅ "청년 기본소득, **신청 방법은 무엇인가요?**"
  - ✅ "분당구 주차장, **어디에 새로 생기나요?**"
- **유형 2 (명사형 - 구체적)**: 핵심 정보 제공.
  - ✅ "청년 기본소득 **신청 자격 조건**"
  - ✅ "분당구 정자동 주차장 **신설 위치**"
- **유형 3 (데이터형 - 신뢰성)**: 숫자 포함.
  - ✅ "2025년 상반기 **5대 주요 성과**"
  - ✅ "청년 일자리 **274명 창출 방법**"
- **유형 4 (절차형 - 실용성)**: 단계별 가이드.
  - ✅ "청년 기본소득 **신청 3단계 절차**"
  - ✅ "보육료 지원금 **수령까지 소요 기간**"
- **유형 5 (비교형 - 차별화)**: 대조 분석.
  - ✅ "청년 기본소득 **vs 청년 수당 차이점**"
  - ✅ "타 지역 대비 **분당구만의 특징**"

## 3. ❌ 절대 금지 (나쁜 예시)
- 모호한 표현: "관련 내용", "정책 안내", "이관훈은?", "부산은?"
- 너무 짧음: "정책", "성과", "방법" (8자 미만 금지)
- 키워드 없음: "우리 지역의 발전을 위한 노력" (핵심어 부재)
- 과장/추상적: "최고의 결과를 얻었습니다", "열심히 노력하겠습니다"

# Output Format (JSON)
{
  "beforeTitles": ["기존 소제목1", "기존 소제목2"],
  "afterTitles": ["수정된 AEO 소제목1", "수정된 AEO 소제목2"],
  "content": "<h1>...</h1>...<h2>수정된 소제목</h2><p>...</p>..." 
}
(content 필드에는 <body> 내부의 HTML만 포함하세요. <html>, <head> 태그 제외)
`;

        try {
            const result = await model.generateContent({
                contents: [{ role: 'user', parts: [{ text: prompt }] }]
            });
            const response = JSON.parse(result.response.text());

            console.log(`✨ [SubheadingAgent] 소제목 교체 완료: ${response.beforeTitles.length}개 -> ${response.afterTitles.length}개`);

            return {
                content: response.content || content, // 실패 시 원본 반환
                log: response.afterTitles
            };

        } catch (e) {
            console.error('❌ [SubheadingAgent] 소제목 최적화 실패:', e);
            return { content }; // 에러 시 원본 그대로 반환 (안전장치)
        }
    }
}

module.exports = { SubheadingAgent };
