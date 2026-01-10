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
        const { topic, instructions, newsContext, userProfile } = context;

        const plan = await this.createPlan(topic, instructions, newsContext, userProfile);
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

    async createPlan(topic, instructions, newsContext, userProfile) {
        const ai = getGenAI();
        const model = ai.getGenerativeModel({ model: this.modelName });

        const prompt = `
# Role
당신은 베테랑 정치 연설문 기획자입니다.
주어진 주제와 참고자료를 분석하여 **가장 논리적이고 설득력 있는 5단 구성**의 원고 설계도를 작성해야 합니다.

╔═══════════════════════════════════════════════════════════════════════╗
║ 🎭 [CRITICAL] 화자 정체성 - 절대 혼동 금지!                              ║
╚═══════════════════════════════════════════════════════════════════════╝

**이 원고의 화자는 "${userProfile.name}"입니다.**
- 참고 자료에 다른 인물(예: 후원회장, 지지자)의 발언이 있더라도, 그 사람이 글을 쓰는 것이 아닙니다.
- 원고의 1인칭 주체는 오직 "${userProfile.name}"입니다.
- 타인의 행동/발언은 3인칭으로 인용하세요 (예: "OOO님께서 ~해주셨습니다").

# Input Data
- **주제**: ${topic}
- **작성자**: ${userProfile.name} (${userProfile.role || '정치인'})
- **지시사항**: ${instructions || '(없음)'}
- **참고자료(뉴스)**: ${newsContext || '(없음)'}
- **사용자 정보**: ${JSON.stringify(userProfile.rhetoricalPreferences || {})}

# Critical Strategy
1. **소재 발굴**: 입력된 주제(Topic)뿐만 아니라, **참고자료(News)**나 **지시사항(Instructions)**에 숨겨진 연관 공약(예: e스포츠, 의료관광, 기업유치 등)을 적극적으로 찾아내어 배치하십시오. 주제가 "다대포 디즈니랜드"라도, 기사에 "e스포츠"나 "병원" 언급이 있다면 반드시 본론으로 가져와야 합니다.
2. **5단 구조 엄수**: 반드시 **[서론 - 본론1 - 본론2 - 본론3 - 결론]** 구조여야 합니다. 본론이 3개가 안 되면, 핵심 주제를 세부 측면(예: 경제적 효과 / 일자리 창출 / 관광 파급력)으로 나누어서라도 3개를 채우십시오.
3. **소제목(H2) AEO 최적화 (핵심)**:
   - 검색자가 궁금해할 **구체적인 질문**이나 **키워드**를 포함해야 합니다.
   - **유형 1 (질문형)**: "~란 무엇인가요?", "~ 신청 방법은?" (가장 권장)
   - **유형 2 (데이터형)**: "~ 5대 핵심 성과", "~ 예산 100억 확보 내역"
   - **유형 3 (정보형)**: "~ 신청 자격 및 필수 서류"
   - ❌ "관련 내용", "정책 안내", "이관훈은?" 같은 모호한 제목 절대 금지.
   - 각 본론의 소제목은 위 규칙을 따라 매력적으로 작성하십시오.

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
    { "type": "intro", "guide": "서론 작성 가이드 (3문단으로 구성, 구체적인 작성 포인트 나열)" },
    { "type": "body1", "keyword": "핵심키워드1", "guide": "본론1 상세 가이드 (반드시 다뤄야 할 구체적 내용, 3문단 분량 확보를 위한 세부 지시)" },
    { "type": "body2", "keyword": "핵심키워드2", "guide": "본론2 상세 가이드 (3문단 분량 확보를 위한 세부 지시)" },
    { "type": "body3", "keyword": "핵심키워드3", "guide": "본론3 상세 가이드 (3문단 분량 확보를 위한 세부 지시)" },
    { "type": "outro", "guide": "결론 작성 가이드 (3문단으로 구성, 구체적인 마무리 포인트)" }
  ]
}
`;

        try {
            const result = await model.generateContent({
                contents: [{ role: 'user', parts: [{ text: prompt }] }],
                generationConfig: { responseMimeType: 'application/json' }
            });
            const parsedPlan = JSON.parse(result.response.text());
            console.log('📋 [ChainWriter] 생성된 기획:', JSON.stringify(parsedPlan, null, 2));
            return parsedPlan;
        } catch (e) {
            console.error('❌ [ChainWriter] 기획 실패:', e);
            return null;
        }
    }

    async writeSection(sectionPlan, index, topic, userProfile) {
        const ai = getGenAI();
        const model = ai.getGenerativeModel({ model: this.modelName });

        const isBody = sectionPlan.type.startsWith('body');
        // 분량 목표 강화: 본론은 최소 400자 이상, 서론/결론은 250자 이상
        const minChars = isBody ? 400 : 250;
        const lengthTarget = isBody ? "500자 이상 (아무리 짧아도 400자는 넘길 것)" : "300자 내외";

        let headerInstruction = '';
        if (sectionPlan.type === 'intro') {
            headerInstruction = '서론에는 절대 소제목을 달지 마십시오. "존경하는..." 같은 인사말로 바로 시작하십시오. (<p> 태그)';
        } else if (sectionPlan.type === 'outro') {
            headerInstruction = '결론의 시작에는 반드시 **"마무리 인사"** 또는 **"맺음말"** 같은 소제목을 <h2>태그로 작성하십시오.';
        } else {
            // 본론 (body)
            headerInstruction = '가장 먼저 이 문단의 핵심을 꿰뚫는 **매력적인 소제목을 <h2>태그**로 작성하십시오.';
        }

        const prompt = `
# Role
당신은 대한민국 최고의 정치 에세이스트이자 파워 블로거입니다.
단순한 요약가가 아닙니다. 주어진 주제를 **풍부하게 풀어서 설명하고, 살을 붙여 확장하는** 능력이 탁월합니다.
짧게 쓰는 것은 당신의 자존심이 허락하지 않습니다. **최대한 길고 상세하게** 쓰십시오.

╔═══════════════════════════════════════════════════════════════════════╗
║ 🎭 [CRITICAL] 화자 정체성 - 절대 혼동 금지!                              ║
╚═══════════════════════════════════════════════════════════════════════╝

**당신은 "${userProfile.name}"입니다. 이 글의 유일한 1인칭 화자입니다.**
- "저는", "제가"를 사용하여 1인칭으로 작성하세요.
- 참고 자료에 등장하는 타인(후원회장, 지지자 등)은 3인칭으로 언급하세요.
- ❌ "후원회장을 맡게 되었습니다" (당신은 후원회장이 아닙니다!)
- ✅ "OOO님께서 후원회장을 맡아주셨습니다"

# Context
- **작성자**: ${userProfile.name}
- **주제**: ${topic}
- **현재 파트**: ${index + 1}번째 파트 (${sectionPlan.type})
- **가이드**: ${sectionPlan.guide}
- **핵심 키워드**: ${sectionPlan.keyword || '없음'}

# Critical Instructions (Absolute Rules)
1. **[CRITICAL] 분량 강제 (Length Enforcement)**:
   - 목표 분량: **${lengthTarget}**
   - **${minChars}자 미만으로 작성하면 실패로 간주됩니다.**
   - 할 말이 없으면 사례를 들거나, 감정을 묘사하거나, 미래 비전을 구체적으로 서술하여 **무조건 분량을 채우십시오.**
   - 절대 요약하지 마십시오. 구구절절하게 늘려 쓰십시오.

2. **구조 (Paragraph Structure)**:
   - 반드시 **3개의 문단(<p> 태그 3개)**으로 나누십시오. 2개도 안 됩니다. 무조건 3개입니다.
   - 각 문단은 **150자 이상** 꽉 채워 쓰십시오. (단문 나열 금지)

3. **어조**: "존경하는 시민 여러분"에게 말하듯 진솔하고 정중하게 (~합니다). 문장은 간결하면서도 힘이 있어야 합니다.

4. **[CRITICAL] 문투 교정 (자연스러움)**:
   - **"~하고 있습니다", "~하고자 하고 있습니다" 절대 금지.** (비문 주의)
   - "~라는 점입니다", "~라고 볼 수 있습니다" 절대 금지.
   - ❌ "극복해야 하고 있습니다." → ✅ "극복하겠습니다."
   - ❌ "예상되는 상황입니다." → ✅ "예상됩니다."

5. **키워드 제한 (스팸 방지)**: 핵심 키워드 "${sectionPlan.keyword || ''}"가 있다면 문맥에 맞는 곳에 **딱 1번만** 사용하십시오. 절대 2회 이상 반복하지 마십시오.

6. **태그**: 각 문단은 <p> 태그로 감싸고, 소제목은 <h2> 태그를 쓰십시오. (마크다운 ## 금지)
7. **${headerInstruction}**
8. **독립성**: 이 글은 전체 원고의 조각입니다. 인사는 서론이 아니면 절대 하지 말고, 바로 본론으로 들어가십시오.

9. **[CRITICAL] 절대 주석 금지 (No Meta-Commentary)**:
   - 본문에 '출처 확인이 필요합니다', '정확한 수치는 확인 바랍니다', '참고로', '관련 데이터 출처 확보가 필요합니다'와 같은 **에디터의 주석(Note)이나 메타 발언**을 절대 포함하지 마십시오.
   - 확신이 없으면 해당 문장을 아예 쓰지 마십시오. 오직 **블로그/칼럼 본문**만 출력하십시오.

# Goal
이 파트 하나만 읽어도 배가 부를 정도로 **풍성하고 구체적인 내용**을 담으십시오.
빈약한 문장은 용납되지 않습니다.
`;

        try {
            const result = await model.generateContent({
                contents: [{ role: 'user', parts: [{ text: prompt }] }],
                generationConfig: {
                    temperature: 0.9,
                    maxOutputTokens: 2000
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
