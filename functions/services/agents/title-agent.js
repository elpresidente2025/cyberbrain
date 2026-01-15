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
            topic = ''  // 🆕 사용자가 입력한 주제
        } = context;

        // WriterAgent가 생성한 본문 가져오기
        const writerResult = previousResults?.WriterAgent?.data;
        if (!writerResult || !writerResult.content) {
            throw new Error('본문 내용이 없습니다. WriterAgent가 먼저 실행되어야 합니다.');
        }

        const content = writerResult.content;
        const status = userProfile?.status || '준비'; // 준비/현역/예비후보

        // 사용자 키워드와 추출된 키워드 병합
        const allKeywords = [
            ...userKeywords,
            ...(extractedKeywords || []).map(k => k.keyword || k)
        ].filter(Boolean);

        // 프롬프트 구성 (🆕 topic 추가)
        const prompt = this.buildPrompt(content, status, allKeywords, topic);
        console.log(`🏷️ [TitleAgent] 주제: "${topic}", 키워드: [${allKeywords.join(', ')}]`);

        // LLM 호출
        const ai = getGenAI();
        if (!ai) {
            throw new Error('Gemini API 키가 설정되지 않았습니다');
        }

        // WriterAgent와 동일한 모델 사용
        const model = ai.getGenerativeModel({ model: 'gemini-2.5-flash' });

        const result = await model.generateContent({
            contents: [{ role: 'user', parts: [{ text: prompt }] }],
            generationConfig: {
                temperature: 0.7,
                maxOutputTokens: 1000,
                responseMimeType: 'application/json'
            }
        });

        const responseText = result.response.text();
        let parsed;
        try {
            parsed = JSON.parse(responseText);
        } catch (e) {
            console.warn('⚠️ [TitleAgent] JSON 파싱 실패:', e.message);
            return {
                title: null,
                error: 'JSON Parsing Failed'
            };
        }

        return {
            title: parsed.title,
            type: parsed.type,
            reasoning: parsed.reasoning,
            candidates: parsed.candidates
        };
    }

    buildPrompt(content, status, keywords, topic = '') {
        const isPreCandidate = status === '예비후보';

        // 선거법 가이드 (최소한의 가이드만 제공하여 창의성 저해 방지)
        const electionLawGuide = isPreCandidate
            ? `✅ "약속", "공약" 사용 가능.`
            : `⚠️ 주의: "약속", "공약" 표현은 피하고 "방향", "구상", "제안" 사용.`;

        // 주제 섹션 (topic이 있으면 강조)
        const topicSection = topic ? `
╔═══════════════════════════════════════════════════════════════════════╗
║ 🎯 [CRITICAL] 사용자가 입력한 주제 - 반드시 제목에 반영!              ║
╚═══════════════════════════════════════════════════════════════════════╝

**사용자가 입력한 주제**: "${topic}"

[필수 규칙]
1. 제목은 반드시 위 주제의 핵심 내용을 반영해야 합니다.
2. 주제에 언급된 인물/사건이 제목에 포함되어야 합니다.
3. 본문에 다른 내용(정책, 공약 등)이 있더라도, **주제가 우선**입니다.

예시:
- 주제: "배우 이관훈, 이재성의 후원회장이 되다"
- ✅ 좋은 제목: "6월 지방선거, 이관훈 배우 이재성 후원회장 맡다"
- ❌ 나쁜 제목: "다대포 디즈니랜드 조성" (주제와 무관)

` : '';

        return `
# Role Definition
당신은 **SEO/AEO(검색 엔진 최적화/답변 엔진 최적화) 블로그 제목 전문가**입니다.
제공된 본문을 분석하여 유권자의 검색 의도에 부합하고 높은 신뢰성을 주는 전문적인 제목을 생성해야 합니다.

${topicSection}
# Input Data
- **Status**: ${status}
- **Topic**: ${topic || '(없음)'}
- **Keywords**: ${keywords.join(', ')}
- **Context**: 
${content.substring(0, 3000)}...

╔═══════════════════════════════════════════════════════════════════════╗
║ 🎯 [CRITICAL] 키워드 + 본문 핵심 조합 원칙                              ║
╚═══════════════════════════════════════════════════════════════════════╝

**키워드를 억지로 제목에 끼워넣지 마세요.** 대신:

1. **본문의 핵심 내용(인물, 사건, 정책)을 먼저 파악**하세요.
   - 예: 본문이 "이관훈 배우가 후원회장을 맡았다"라면, 핵심은 "이관훈", "후원회장"
   
2. **키워드를 핵심 내용과 자연스럽게 조합**하세요.
   - ❌ 억지 삽입: "6월 지방선거 핵심 점검" (내용과 무관)
   - ✅ 자연 조합: "6월 지방선거, 이재성과 함께하는 이관훈 후원회장"

3. **상투적/맥락 없는 표현 절대 금지**:
   - ❌ "핵심 점검", "현안 진단", "주요 이슈", "중요 사안", "심층 분석"
   - ❌ 본문에 없는 내용을 제목에 넣지 마세요

# 🔴 SEO/AEO Strategy (6 Types)
다음 6가지 유형 중 본문 내용에 가장 적합한 전략을 선택하여 제목을 작성하세요.

1. **구체적 데이터 기반형**
   - 전략: 성과를 숫자와 증빙 자료로 제시하여 신뢰성 확보
   - 예시: "2025년 시민청원 127건 해결, 34억 예산 절감"
   - 핵심: 연도, 구체적 수치(금액, 인원), "~건", "~%" 포함

2. **질문-해답 구조형 (AEO 최적화)**
   - 전략: 유권자의 실제 검색 질문을 그대로 제목화
   - 예시: "분당구 청년 주거 지원, 어떤 게 있을까요?"
   - 핵심: "어떻게", "무엇을", "왜" 질문 포함, 지역명 결합

3. **비교·대조 전략형**
   - 전략: 전후 변화와 개선점을 명확히 비교
   - 예시: "기존 청년 지원 vs 2025년 개선안, 무엇이 달라졌나요?"
   - 핵심: "전 vs 후", "기존 vs 개선", "문제 vs 해결" 구조

4. **전문 지식 공유형**
   - 전략: 입법/행정 전문성을 부각하는 정보 제공
   - 예시: "주차장 부족 해결 조례, 입법 과정 전격 공개"
   - 핵심: "법안", "예산안", "조례", "가이드", "설명" 키워드

5. **지역 맞춤형 정보형 (초지역화)**
   - 전략: 동/면/읍 단위 지역민 타겟팅
   - 예시: "분당구 정자동 주민들께 드리는 2025년 상반기 성과"
   - 핵심: 행정구역명(동/읍/면) 필수, "주민", "구민" 호명

6. **인물/사건 중심형 (뉴스형)**
   - 전략: 본문에 등장하는 핵심 인물이나 사건을 제목에 부각
   - 예시: "계엄군 막은 이관훈 배우, 부산시장 후원회장 맡다"
   - 핵심: 인물명, 직함, 사건/행동을 구체적으로 명시

# 🔴 Critical Checklist (Must Follow)
1. **내용 반영 필수**: 본문의 핵심 내용(인물, 사건, 정책)이 제목에 반영되어야 함
2. **키워드 자연 삽입**: 키워드를 제목에 자연스럽게 녹여야 함 (억지 삽입 금지)
3. **길이 제한**: 공백 포함 **15자 ~ 30자** 이내 (조금 더 여유 있게)
4. **키워드 배치**: 핵심 키워드는 제목 **앞쪽 1/2** 지점 내에 배치
5. **금지어**: "핵심 점검", "현안 진단", "주요 이슈" 같은 상투적 표현 절대 금지

# Tasks
1. 본문의 핵심 내용(Fact)을 추출하세요. **(인물명, 직함, 사건, 숫자, 지역명, 정책명 등)**
2. 위 6가지 유형 중 가장 적합한 유형 1~2개를 고르세요.
3. **후보 제목 5개**를 작성하세요. (키워드 + 본문 핵심 조합)
4. 그 중 **가장 클릭률(CTR)과 내용 반영도가 높은 1개(Best Title)**를 최종 선택하세요.

# Output Format (JSON Only)
{
  "type": "유형 번호 및 이름 (예: 6. 인물/사건 중심형)",
  "candidates": ["후보1", "후보2", "후보3", "후보4", "후보5"],
  "title": "최종 선택된 최고의 제목 (15-30자)",
  "reasoning": "선택 이유 (키워드 배치, 내용 반영도, 구체성 등)"
}
`;
    }
}

module.exports = { TitleAgent };
