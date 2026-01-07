'use strict';

const { GoogleGenerativeAI } = require('@google/generative-ai');
const { getGeminiApiKey } = require('../../common/secrets');

// LLM 인스턴스 (WriterAgent와 동일한 모델 사용)
let genAI = null;
function getGenAI() {
  if (!genAI) {
    const apiKey = getGeminiApiKey();
    if (!apiKey) return null;
    genAI = new GoogleGenerativeAI(apiKey);
  }
  return genAI;
}

function stripHtml(text) {
  return String(text || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

/**
 * AEO 전문가로서 본문 단락을 분석하여 질문형 소제목(H2) 생성
 * - 복잡한 정규식 후처리 없이 LLM의 지능을 전적으로 활용
 */
async function generateAeoSubheadings({ sections, modelName, fullName, fullRegion }) {
  if (!sections || sections.length === 0) return null;

  // 1. 단락 전처리 (HTML 제거 및 공백 정리)
  const cleanedSections = sections
    .map((section) => stripHtml(section))
    .map((text) => text.replace(/\s+/g, ' ').trim())
    .filter(Boolean);

  if (cleanedSections.length === 0) return null;

  // 2. 입력 데이터 요약 (Entity Hint 추출)
  const entityHints = [fullName, fullRegion].filter(Boolean).join(', ');

  // 3. 프롬프트 구성 (사용자가 제공한 AEO 가이드 완전 통합)
  const prompt = `
# Role Definition
당신은 **AEO(Answer Engine Optimization) 전문가**입니다.
주어진 본문 단락들을 분석하여, **검색 의도(Search Intent)**에 부합하는 질문형 또는 명확한 명사형 소제목(H2)을 생성해야 합니다.

# Input Settings
- **Region/Name**: ${entityHints || '(없음)'}
- **Number of Headings**: ${cleanedSections.length}개 (각 단락마다 1개씩)

# 🔴 Critical Rules (AEO Checklist)
1. **길이**: 공백 포함 **15자 ~ 22자** (최적), 최대 25자 절대 넘지 말 것.
2. **구조**: **"핵심 키워드 + 구체적 질문/정보"** 형태. 키워드를 무조건 앞쪽에 배치.
3. **일치성**: 반드시 **해당 문단(Paragraph)에 실제로 있는 내용**으로만 소제목을 지을 것. (배경지식이나 힌트 사용 금지)
4. **금지**: "~에 대한", "~관련", "좋은 성과", "열심히" 같은 **추상적 표현 절대 금지**.
5. **필수**: 구체적인 **숫자(금액, 인원, 날짜)**나 **고유명사(지역명, 정책명)** 포함.

# H2 Generation Strategy (5 Types)
상황에 맞는 유형을 선택하여 생성하세요:

1. **질문형 (AEO 최강)**: "청년 기본소득, 신청 방법은 무엇인가?" (19자)
2. **명사형 (SEO 기본)**: "분당구 정자동 주차장 신설 위치" (16자)
3. **데이터형 (신뢰성)**: "2025년 상반기 5대 주요 성과" (15자)
4. **절차형 (실용성)**: "청년 기본소득 신청 3단계 절차" (16자)
5. **비교형 (차별화)**: "기존 정책 vs 개선안 3가지 비교" (16자)

# Bad vs Good Examples
❌ "청년 지원 정책에 관한 모든 것을 알려드립니다" (22자) → 핵심 없음, 과장
✅ "청년 기본소득, 어떻게 신청하나요?" (17자)

❌ "좋은 성과를 냈습니다" (10자) → 추상적
✅ "청년 일자리 274명 창출 성과" (15자)

❌ "부산광역시 부산은 K은?" (12자) → 비문, 오류
✅ "부산 K-콘텐츠 산업, 육성 전략은?" (17자)

# Input Paragraphs
${cleanedSections.map((sec, i) => `[Paragraph ${i + 1}]\n${sec.substring(0, 300)}...`).join('\n\n')}

# Output Format (JSON Only)
반드시 아래 JSON 포맷으로 출력하세요. 순서는 단락 순서와 일치해야 합니다.
{
  "headings": [
    "소제목1 (15-22자)",
    "소제목2 (15-22자)"
  ]
}
`;

  // 4. LLM 호출 (WriterAgent와 동일한 모델 사용 - 404 방지)
  const ai = getGenAI();
  if (!ai) {
    console.error('Gemini API Key missing');
    return fallbacks(cleanedSections, fullRegion);
  }

  // WriterAgent.js와 동일한 모델명 사용
  const model = ai.getGenerativeModel({ model: 'gemini-2.5-flash-lite' });

  try {
    const result = await model.generateContent({
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
      generationConfig: {
        temperature: 0.7, // 창의성보다 정확성 중요
        maxOutputTokens: 1000,
        responseMimeType: 'application/json'
      }
    });

    const responseText = result.response.text();
    const parsed = JSON.parse(responseText);

    if (Array.isArray(parsed?.headings)) {
      // 5. 안전 장치 로직 (25자 초과 시에만 단순 축약, 조사 검사 X)
      return parsed.headings.map((h, i) => {
        let heading = String(h).trim();
        // 혹시 모를 따옴표 제거
        heading = heading.replace(/^["']|["']$/g, '');
        // 길이 강제 (뒤에 자르기)
        if (heading.length > 28) {
          heading = heading.substring(0, 27) + '...';
        }
        return heading;
      });
    }

  } catch (error) {
    console.error('⚠️ [SubheadingAgent] LLM Error:', error.message);
  }

  // 6. 실패 시 안전한 Fallback (조잡한 문장 분석 X)
  return fallbacks(cleanedSections, fullRegion);
}

// 7. 아주 단순하고 안전한 Fallback (버그 원천 차단)
function fallbacks(sections, region) {
  const safeRegion = region || '지역';
  return sections.map(() => `${safeRegion}의 주요 정책과 비전`);
}

module.exports = {
  generateAeoSubheadings
};
