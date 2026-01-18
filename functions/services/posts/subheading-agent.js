'use strict';

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

function stripHtml(text) {
  return String(text || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

/**
 * AEO 전문가로서 본문 단락을 분석하여 최적의 소제목(H2) 생성
 * 사용자 제공 가이드라인(유형 1~5) 완벽 준수
 */
async function generateAeoSubheadings({ sections, modelName = 'gemini-2.0-flash', fullName, fullRegion }) {
  if (!sections || sections.length === 0) return null;

  // 1. 단락 전처리
  const cleanedSections = sections
    .map((section) => stripHtml(section))
    .map((text) => text.replace(/\s+/g, ' ').trim())
    .filter(Boolean);

  if (cleanedSections.length === 0) return null;

  const entityHints = [fullName, fullRegion].filter(Boolean).join(', ');

  // 2. 프롬프트: 사용자 AEO 가이드라인 반영
  const prompt = `
# Role Definition
당신은 대한민국 최고의 **AEO(Answer Engine Optimization) & SEO 전문 카피라이터**입니다.
주어진 본문 단락들을 분석하여, 검색 엔진과 사용자 모두에게 매력적인 **최적의 소제목(H2)**을 생성해야 합니다.

# Input Data
- **Context**: ${entityHints || '(없음)'}
- **Target Count**: ${cleanedSections.length} Headings

# [CRITICAL] AEO H2 작성 가이드라인
아래 규칙을 위반할 경우 해고될 수 있습니다. 반드시 준수하세요.

## 1. 필수 요소
- **길이**: **12~25자** (네이버 최적: 15~22자)
- **키워드**: 핵심 키워드를 **문장 앞쪽 1/3**에 배치할 것.
- **형식**: 구체적인 **질문형** 또는 **명확한 명사형**.
- **금지**: "~에 대한", "~관련", "좋은 성과", "이관훈은?" 같은 모호한 표현.

## 2. AEO 최적화 유형 (상황에 맞춰 사용)

- **유형 1 (질문형 - AEO 최강)**: 검색자의 의도를 저격.
  - ✅ "청년 일자리 부족, 원인은 무엇인가요?" (19자)
  - ✅ "지역 의료 붕괴, 어떻게 막을 수 있나요?" (20자)
  - ✅ "출퇴근 지옥, 해결책은 정말 있나요?" (18자)
  - ✅ "미세먼지 문제, 어떻게 줄일 수 있나요?" (20자)
  - ✅ "전세 사기 피해, 어떻게 예방하나요?" (18자)

- **유형 2 (명사형 - 구체적)**: 핵심 정보 제공.
  - ✅ "청년이 돌아오는 도시를 만드는 방법" (18자)
  - ✅ "지역 경제 활성화를 위한 5대 과제" (17자)
  - ✅ "노인 돌봄 서비스 확대 핵심 정책" (17자)
  - ✅ "환경 오염 방지를 위한 구체적 대책" (18자)
  - ✅ "교육 격차 해소를 위한 실천 방안" (17자)

- **유형 3 (데이터형 - 신뢰성)**: 숫자 포함.
  - ✅ "공공 임대 5만 호 공급 세부 계획" (17자)
  - ✅ "탄소 배출 40% 감축 달성 3대 과제" (19자)
  - ✅ "청년 일자리 1만 개 창출 로드맵" (17자)
  - ✅ "교통비 부담 30% 완화 지원 정책" (17자)
  - ✅ "어린이집 200개소 확충 추진 계획" (18자)

- **유형 4 (절차형 - 실용성)**: 단계별 가이드.
  - ✅ "전세 사기 예방을 위한 3단계 가이드" (19자)
  - ✅ "청년 취업 지원금 신청 3단계 절차" (18자)
  - ✅ "보육료 지원금 수령까지 소요 기간" (17자)
  - ✅ "창업 지원 프로그램 참여 신청 방법" (18자)
  - ✅ "노후 주택 정비 사업 참여 절차 안내" (19자)

- **유형 5 (비교형 - 차별화)**: 대조 분석.
  - ✅ "타 지역 대비 우리 지역만의 특징" (17자)
  - ✅ "기존 정책 vs 새 정책, 무엇이 다른가" (19자)
  - ✅ "임대료 지원 vs 직접 공급, 차이점" (18자)
  - ✅ "공교육 vs 사교육, 격차 줄이는 법" (18자)
  - ✅ "민간 vs 공공 의료, 접근성 비교 분석" (20자)

## ❌ 나쁜 예시 (절대 금지)
- "청년 지원 정책에 관한 모든 것을 알려드립니다" (22자) → 핵심 없음, 과장
- "좋은 성과를 냈습니다" (10자) → 추상적
- "부산광역시 부산은 K은?" (12자) → 비문
- "관련 내용", "정책 안내" (너무 짧고 모호함)

# Input Paragraphs
${cleanedSections.map((sec, i) => `[Paragraph ${i + 1}]\n${sec.substring(0, 400)}...`).join('\n\n')}

# Output Format (JSON Only)
반드시 아래 JSON 포맷으로 출력하세요. 순서는 단락 순서와 일치해야 합니다.
{
  "headings": [
    "AEO 최적화 소제목1",
    "AEO 최적화 소제목2"
  ]
}
`;

  const ai = getGenAI();
  if (!ai) return fallbacks(cleanedSections, fullRegion);

  const model = ai.getGenerativeModel({ model: modelName }); // gemini-2.0-flash 권장

  try {
    const result = await model.generateContent({
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
      generationConfig: {
        responseMimeType: 'application/json'
      }
    });

    const parsed = JSON.parse(result.response.text());

    if (Array.isArray(parsed?.headings)) {
      return parsed.headings.map((h) => {
        let heading = String(h).trim().replace(/^["']|["']$/g, '');
        // 혹시라도 너무 길면 자르기 (28자)
        if (heading.length > 28) heading = heading.substring(0, 27) + '...';
        return heading;
      });
    }

  } catch (error) {
    console.error('⚠️ [SubheadingAgent] LLM Error:', error.message);
  }

  return fallbacks(cleanedSections, fullRegion);
}

function fallbacks(sections, region) {
  const safeRegion = region || '지역';
  return sections.map(() => `${safeRegion}의 주요 비전과 과제`); // 안전한 기본값
}

/**
 * [Main Entry] HTML 컨텐츠 통째로 받아서 H2 태그만 AEO 스타일로 교체
 */
async function optimizeHeadingsInContent({ content, fullName, fullRegion }) {
  if (!content) return content;

  // 1. 기존 H2 추출
  const h2Regex = /<h2>(.*?)<\/h2>/gi;
  const matches = [...content.matchAll(h2Regex)];

  if (matches.length === 0) return content; // 교체할 대상이 없음

  console.log(`✨ [SubheadingAgent] 발견된 소제목 ${matches.length}개 최적화 시작...`);

  // 2. 각 H2에 대응하는 본문 텍스트 추출 (맥락 파악용)
  const sectionsForPrompt = matches.map(match => {
    const h2Index = match.index;
    const headerLength = match[0].length;
    const nextText = content.substring(h2Index + headerLength, h2Index + headerLength + 600);
    return stripHtml(nextText).trim();
  });

  // 3. AEO 에이전트 호출 (배열 반환)
  const aeoHeadings = await generateAeoSubheadings({
    sections: sectionsForPrompt,
    fullName,
    fullRegion
  });

  if (!aeoHeadings || aeoHeadings.length !== matches.length) {
    console.warn('⚠️ [SubheadingAgent] 생성된 소제목 개수 불일치. 원본 유지.');
    return content;
  }

  // 4. 교체 (String Reconstruction)
  let parts = [];
  let lastIndex = 0;

  matches.forEach((match, i) => {
    parts.push(content.substring(lastIndex, match.index)); // 태그 앞부분
    parts.push(`<h2>${aeoHeadings[i]}</h2>`);             // 교체된 태그
    lastIndex = match.index + match[0].length;             // 태그 뒷부분 시작점 갱신
  });
  parts.push(content.substring(lastIndex)); // 남은 뒷부분

  console.log('✅ [SubheadingAgent] 소제목 전면 교체 완료');
  return parts.join('');
}

module.exports = {
  generateAeoSubheadings,
  optimizeHeadingsInContent
};
