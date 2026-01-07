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
        this.modelName = 'gemini-2.5-flash-lite'; // WriterAgent와 동일 모델 사용
    }

    getRequiredContext() {
        return ['topic', 'userProfile'];
    }

    async execute(context) {
        const { topic, instructions, newsContext, userProfile } = context;

        // 1. 기획 단계 (Plan)
        const plan = await this.createPlan(topic, instructions, newsContext, userProfile);
        if (!plan) throw new Error('원고 기획에 실패했습니다.');

        // 2. 집필 단계 (Write) - 병렬 처리로 속도 개선
        console.log(`📝 [ChainWriter] 기획 완료: ${plan.sections.length}개 섹션 집필 시작`);

        // 각 섹션을 독립적으로 생성
        const sectionPromises = plan.sections.map((section, index) =>
            this.writeSection(section, index, topic, userProfile)
        );

        const sectionsContent = await Promise.all(sectionPromises);

        // 3. 조립 단계 (Assemble)
        const fullContent = sectionsContent.join('\n\n');

        // 최종 결과 반환 (WriterAgent와 호환되는 구조)
        return {
            title: plan.title, // 기획 단계에서 가제를 뽑아봄 (TitleAgent가 덮어쓸 예정)
            content: fullContent,
            structure: plan // 디버깅용 구조 정보
        };
    }

    // [Step 1] 전체 구조 설계
    async createPlan(topic, instructions, newsContext, userProfile) {
        const ai = getGenAI();
        const model = ai.getGenerativeModel({ model: this.modelName });

        const prompt = `
# Role
당신은 베테랑 정치 연설문 기획자입니다.
주어진 주제와 참고자료를 분석하여 **가장 논리적이고 설득력 있는 5단 구성**의 원고 설계도를 작성해야 합니다.

# Input Data
- **주제**: ${topic}
- **작성자**: ${userProfile.name} (${userProfile.role || '정치인'})
- **지시사항**: ${instructions || '(없음)'}
- **참고자료(뉴스)**: ${newsContext || '(없음)'}
- **사용자 정보**: ${JSON.stringify(userProfile.rhetoricalPreferences || {})}

# Critical Strategy
1. **소재 발굴**: 입력된 주제(Topic)뿐만 아니라, **참고자료(News)**나 **지시사항(Instructions)**에 숨겨진 연관 공약(예: e스포츠, 의료관광, 기업유치 등)을 적극적으로 찾아내어 배치하십시오. 주제가 "다대포 디즈니랜드"라도, 기사에 "e스포츠"나 "병원" 언급이 있다면 반드시 본론으로 가져와야 합니다.
2. **5단 구조 엄수**: 반드시 **[서론 - 본론1 - 본론2 - 본론3 - 결론]** 구조여야 합니다. 본론이 3개가 안 되면, 핵심 주제를 세부 측면(예: 경제적 효과 / 일자리 창출 / 관광 파급력)으로 나누어서라도 3개를 채우십시오.
3. **가독성**: 각 본론은 서로 다른 소제목(H2)을 가져야 하며, 내용은 독립적이어야 합니다.

# Structure (5-Step)
1. **서론**: 인사, 문제 제기, 공감 (독자에게 다가가는 톤)
2. **본론 1**: 핵심 공약 A (구체적 실행 방안)
3. **본론 2**: 핵심 공약 B (또는 A의 구체적 기대효과)
4. **본론 3**: 핵심 공약 C (또는 연관 비전/확장성)
5. **결론**: 요약, 다짐, 지지 호소 (강력한 마무리)

# Output Format (JSON)
{
  "title": "가제 (임시 제목)",
  "sections": [
    { "type": "intro", "guide": "서론 작성 가이드 (구체적으로)" },
    { "type": "body1", "keyword": "핵심키워드1", "guide": "본론1에 들어갈 구체적 내용 요약" },
    { "type": "body2", "keyword": "핵심키워드2", "guide": "본론2에 들어갈 구체적 내용 요약" },
    { "type": "body3", "keyword": "핵심키워드3", "guide": "본론3에 들어갈 구체적 내용 요약" },
    { "type": "outro", "guide": "결론 작성 가이드" }
  ]
}
`;

        try {
            const result = await model.generateContent({
                contents: [{ role: 'user', parts: [{ text: prompt }] }],
                generationConfig: { responseMimeType: 'application/json' }
            });
            return JSON.parse(result.response.text());
        } catch (e) {
            console.error('❌ [ChainWriter] 기획 실패:', e);
            return null;
        }
    }

    // [Step 2] 개별 섹션 집필
    async writeSection(sectionPlan, index, topic, userProfile) {
        const ai = getGenAI();
        const model = ai.getGenerativeModel({ model: this.modelName });

        const isBody = sectionPlan.type.startsWith('body');
        const lengthGuide = isBody ? "400~500자 (풍부하고 구체적으로)" : "250~300자 (강렬하게)";

        // 본론일 경우 소제목 태그(<h2>) 추가 요청
        const headerInstruction = isBody
            ? `가장 먼저 이 문단의 핵심을 꿰뚫는 **매력적인 소제목을 <h2>태그**로 작성하십시오.`
            : `서론이나 결론에는 소제목을 달지 마십시오. 바로 본문(<p>)으로 시작하십시오.`;

        const prompt = `
# Role
당신은 대한민국 최고의 정치 에세이스트이자 연설문 작가입니다.
딱딱하고 기계적인 보고서가 아닌, **시민의 마음을 움직이는 뜨거운 글**을 써야 합니다.
복잡한 법적 제약이나 형식은 잊으십시오. 오직 **진심과 호소력**에만 집중하십시오.

# Context
- **작성자**: ${userProfile.name}
- **주제**: ${topic}
- **현재 파트**: ${index + 1}번째 파트 (${sectionPlan.type})
- **가이드**: ${sectionPlan.guide}
- **핵심 키워드**: ${sectionPlan.keyword || '없음'}

# Instruction
1. **분량**: ${lengthGuide}
2. **어조**: "존경하는 시민 여러분"에게 말하듯 진솔하고 정중하게 (~합니다). 문장은 간결하면서도 힘이 있어야 합니다.
3. **금지 어투**: **"~라는 점입니다", "~볼 수 있습니다", "~생각합니다" 같은 번역투나 수동적인 표현을 절대 쓰지 마십시오.** 대신 "제안합니다", "확신합니다", "나아가겠습니다" 처럼 능동적으로 쓰십시오.
4. **키워드 필수**: 핵심 키워드 "${sectionPlan.keyword || ''}"가 있다면 문단 내에 자연스럽게 1회 이상 포함하십시오. (단, 억지로 넣지는 마십시오)
5. **태그**: 문단은 <p> 태그로 감싸고, 소제목은 <h2> 태그를 쓰십시오.
6. **${headerInstruction}**
7. **독립성**: 이 글은 전체 원고의 조각입니다. "안녕하세요" 같은 인사는 서론이 아니면 절대 하지 말고, 바로 본론으로 들어가십시오.

# Goal
이 파트를 읽은 시민이 "이 사람이다!"라고 무릎을 탁 치게 만드십시오.
`;

        try {
            const result = await model.generateContent({
                contents: [{ role: 'user', parts: [{ text: prompt }] }]
            });
            let text = result.response.text().trim();
            // 혹시 모를 마크다운 코드블록 제거
            text = text.replace(/```html/g, '').replace(/```/g, '');
            return text;
        } catch (e) {
            console.error(`❌ [ChainWriter] 섹션 ${index} 작성 실패:`, e);
            return `<p>(섹션 생성 실패: ${sectionPlan.keyword})</p>`;
        }
    }
}

module.exports = { ChainWriterAgent };
