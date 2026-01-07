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
            extractedKeywords = []
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

        // 프롬프트 구성
        const prompt = this.buildPrompt(content, status, allKeywords);

        // LLM 호출
        const ai = getGenAI();
        if (!ai) {
            throw new Error('Gemini API 키가 설정되지 않았습니다');
        }

        // WriterAgent와 동일한 모델 사용
        const model = ai.getGenerativeModel({ model: 'gemini-2.5-flash-lite' });

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

    buildPrompt(content, status, keywords) {
        const isPreCandidate = status === '예비후보';

        // 선거법 가이드 (최소한의 가이드만 제공하여 창의성 저해 방지)
        const electionLawGuide = isPreCandidate
            ? `✅ "약속", "공약" 사용 가능.`
            : `⚠️ 주의: "약속", "공약" 표현은 피하고 "방향", "구상", "제안" 사용.`;

        return `
# Role Definition
당신은 **SEO/AEO(검색 엔진 최적화/답변 엔진 최적화) 블로그 제목 전문가**입니다.
제공된 본문을 분석하여 유권자의 검색 의도에 부합하고 높은 신뢰성을 주는 전문적인 제목을 생성해야 합니다.

# Input Data
- **Status**: ${status}
- **Keywords**: ${keywords.join(', ')}
- **Context**: 
${content.substring(0, 3000)}...

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

6. **시간 중심 신뢰성형**
   - 전략: 정기성과 최신성을 강조하여 신뢰 구축
   - 예시: "2025년 6월 의정 보고서: 5대 핵심 성과"
   - 핵심: 연도/월 명시, "보고서", "리포트", "소식지" 키워드

# 🔴 Critical Checklist (Must Follow)
1. **지역명 포함**: 가능하면 구/동 단위 지역명 포함 (예: 부산, 다대포, 강서구 등)
2. **구체적 수치**: 막연한 "많은", "대폭" 금지. "127건", "34억" 등 숫자 사용
3. **길이 제한**: 공백 포함 **15자 ~ 25자** 이내 (네이버 모바일 최적화)
4. **키워드 배치**: 핵심 키워드는 제목 **앞쪽 1/3** 지점에 배치
5. **금지어**: "최고", "혁명적" 같은 과장 광고성 어휘 금지. 밋밋하고 추상적인 제목 금지.

# Tasks
1. 본문의 핵심 내용(Fact)을 추출하세요. (숫자, 지역명, 정책명 등)
2. 위 6가지 유형 중 가장 적합한 유형 1~2개를 고르세요.
3. **후보 제목 5개**를 작성하세요.
4. 그 중 **가장 클릭률(CTR)과 신뢰도가 높을 1개(Best Title)**를 최종 선택하세요.

# Output Format (JSON Only)
{
  "type": "유형 번호 및 이름 (예: 1. 구체적 데이터 기반형)",
  "candidates": ["후보1", "후보2", "후보3", "후보4", "후보5"],
  "title": "최종 선택된 최고의 제목 (15-25자)",
  "reasoning": "선택 이유 (키워드 배치, 구체성, AEO 적합성 등)"
}
`;
    }
}

module.exports = { TitleAgent };
