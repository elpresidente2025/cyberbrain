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

// 🔑 [방안 3] 카테고리별 소제목 스타일 정의
const SUBHEADING_STYLES = {
  // 논평/시사: 주장형 소제목 (질문형 금지)
  'current-affairs': {
    style: 'assertive',
    description: '논평/시사 카테고리는 주장형 소제목을 사용합니다.',
    preferredTypes: ['주장형', '명사형'],
    forbiddenPatterns: ['~인가요?', '~일까요?', '~는?', '~할까?', '~인가?'],
    examples: [
      '"신공안 프레임"은 책임 회피에 불과하다',
      '특검은 정치 보복이 아니다',
      '당당하면 피할 이유 없다',
      '민주주의의 기본 질서를 지켜야'
    ]
  },
  // 정책 제안: 정보형/데이터형 소제목
  'policy-proposal': {
    style: 'informative',
    description: '정책 제안 카테고리는 구체적인 정보형 소제목을 사용합니다.',
    preferredTypes: ['데이터형', '명사형', '절차형'],
    forbiddenPatterns: [],
    examples: [
      '청년 일자리 3대 핵심 전략',
      '국비 100억 확보 내역',
      '교통 체계 개편 5단계 로드맵'
    ]
  },
  // 의정활동: 실적/성과 중심
  'activity-report': {
    style: 'achievement',
    description: '의정활동 보고는 성과 중심 소제목을 사용합니다.',
    preferredTypes: ['데이터형', '명사형'],
    forbiddenPatterns: [],
    examples: [
      '국정감사 5대 핵심 성과',
      '지역 현안 해결 실적',
      '국회 발의 법안 현황'
    ]
  },
  // 일상 소통: 친근한 질문형 허용
  'daily-communication': {
    style: 'friendly',
    description: '일상 소통은 친근한 질문형도 허용됩니다.',
    preferredTypes: ['질문형', '명사형'],
    forbiddenPatterns: [],
    examples: [
      '요즘 어떻게 지내시나요?',
      '함께 나눈 이야기들',
      '시민 여러분께 전하는 말씀'
    ]
  },
  // 기본값: 기존 AEO 최적화 유지
  'default': {
    style: 'aeo-optimized',
    description: '기본 AEO 최적화 스타일을 사용합니다.',
    preferredTypes: ['질문형', '명사형', '데이터형'],
    forbiddenPatterns: [],
    examples: []
  }
};

/**
 * 카테고리에 맞는 소제목 스타일 가져오기
 */
function getSubheadingStyle(category, subCategory = '') {
  // 논평 하위 카테고리 감지
  if (category === 'current-affairs') {
    return SUBHEADING_STYLES['current-affairs'];
  }

  // 그 외 카테고리
  if (SUBHEADING_STYLES[category]) {
    return SUBHEADING_STYLES[category];
  }

  return SUBHEADING_STYLES['default'];
}

/**
 * AEO 전문가로서 본문 단락을 분석하여 최적의 소제목(H2) 생성
 * 사용자 제공 가이드라인(유형 1~5) 완벽 준수
 * 🔑 [방안 3] 카테고리별 스타일 분기 추가
 */
async function generateAeoSubheadings({ sections, modelName = 'gemini-2.5-flash', fullName, fullRegion, category = '', subCategory = '' }) {
  if (!sections || sections.length === 0) return null;

  // 1. 단락 전처리
  const cleanedSections = sections
    .map((section) => stripHtml(section))
    .map((text) => text.replace(/\s+/g, ' ').trim())
    .filter(Boolean);

  if (cleanedSections.length === 0) return null;

  const entityHints = [fullName, fullRegion].filter(Boolean).join(', ');

  // 🔑 [방안 3] 카테고리별 스타일 가져오기
  const styleConfig = getSubheadingStyle(category, subCategory);
  const isAssertiveStyle = styleConfig.style === 'assertive';

  // 2. 프롬프트: 카테고리별 분기
  let prompt;

  if (isAssertiveStyle) {
    // 🔑 논평/시사 카테고리: 주장형 소제목 (질문형 금지)
    prompt = `
# Role Definition
당신은 대한민국 최고의 **정치 논평 전문 에디터**입니다.
주어진 논평/입장문 단락들을 분석하여, **날카롭고 주장이 담긴 소제목(H2)**을 생성해야 합니다.

# Input Data
- **Context**: ${entityHints || '(없음)'}
- **Target Count**: ${cleanedSections.length} Headings
- **글 유형**: 논평/입장문 (주장형 소제목 필수)

# [CRITICAL] 논평용 H2 작성 가이드라인
⚠️ 이 글은 논평/입장문입니다. 질문형 소제목은 절대 금지됩니다.

## 1. 필수 요소
- **길이**: **12~25자** (네이버 최적: 15~22자)
- **형식**: **주장형** 또는 **명사형** (질문형 절대 금지)
- **어조**: 단정적, 비판적, 명확한 입장 표명

## 2. ✅ 권장 유형 (주장형)
- **유형 A (단정형)**: "~이다", "~해야 한다"
  - ✅ "특검은 정치 보복이 아니다" (12자)
  - ✅ "당당하면 피할 이유 없다" (12자)
  - ✅ "'신공안 프레임'은 책임 회피다" (15자)
  - ✅ "민주주의는 권력자에게 편하지 않다" (17자)

- **유형 B (비판형)**: 대상을 명시한 비판
  - ✅ "진실 규명을 거부하는 태도" (13자)
  - ✅ "특검 전에 프레임부터 씌우는 이유" (16자)
  - ✅ "책임 회피로 일관하는 자세" (13자)

- **유형 C (명사형)**: 핵심 쟁점 명시
  - ✅ "특검법의 정당성과 의의" (12자)
  - ✅ "민주주의 수호의 당위성" (12자)
  - ✅ "투명한 검증을 위한 제도적 장치" (16자)

## 3. ❌ 절대 금지 (질문형)
- ❌ "~인가요?", "~일까요?", "~는?", "~할까?"
- ❌ "어떻게 해소해야 하나?" (질문형)
- ❌ "정말 답인가?" (질문형)
- ❌ "왜 피하는가?" (질문형, 수사적 질문도 금지)

## 4. ❌ 나쁜 예시 (절대 금지)
- "부산광역시의 주요 비전과 과제" → 본문 내용과 무관한 일반적 표현
- "앞으로의 과제" → 구체성 없음
- "투명한 사회를 위한 노력" → AI 슬롭 표현

# Input Paragraphs
${cleanedSections.map((sec, i) => `[Paragraph ${i + 1}]\n${sec.substring(0, 400)}...`).join('\n\n')}

# Output Format (JSON Only)
반드시 아래 JSON 포맷으로 출력하세요. 순서는 단락 순서와 일치해야 합니다.
{
  "headings": [
    "주장형 소제목1",
    "주장형 소제목2"
  ]
}`;
  } else {
    // 기본: 기존 AEO 최적화 프롬프트
    prompt = `
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
  }

  // 🔑 [방안 3] 카테고리별 스타일 로깅
  console.log(`📝 [SubheadingAgent] 소제목 생성 시작 (category=${category}, style=${styleConfig.style}, sections=${cleanedSections.length})`);

  const ai = getGenAI();
  if (!ai) {
    throw new Error('[SubheadingAgent] Gemini API 키가 설정되지 않았습니다. 소제목 생성 불가.');
  }

  const model = ai.getGenerativeModel({ model: modelName }); // gemini-2.5-flash 사용

  // 재시도 로직 (최대 3회)
  const MAX_RETRIES = 3;
  let lastError = null;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      const result = await model.generateContent({
        contents: [{ role: 'user', parts: [{ text: prompt }] }],
        generationConfig: {
          responseMimeType: 'application/json'
        }
      });

      const parsed = JSON.parse(result.response.text());

      if (Array.isArray(parsed?.headings)) {
        const processedHeadings = parsed.headings.map((h) => {
          let heading = String(h).trim().replace(/^["']|["']$/g, '');
          // 혹시라도 너무 길면 자르기 (28자)
          if (heading.length > 28) heading = heading.substring(0, 27) + '...';
          return heading;
        });
        console.log(`✅ [SubheadingAgent] 소제목 생성 완료 (model=${modelName}, style=${styleConfig.style}, attempt=${attempt}):`, processedHeadings);
        return processedHeadings;
      } else {
        throw new Error('응답에 headings 배열이 없습니다.');
      }

    } catch (error) {
      lastError = error;
      // [상세 로그] 에러 객체 전체와 메시지 출력
      console.error(`⚠️ [SubheadingAgent] LLM 시도 ${attempt}/${MAX_RETRIES} 실패 (model=${modelName}):`, error);
      console.error(`   - Error Message: ${error.message}`);
      if (error.response) console.error(`   - Response: ${JSON.stringify(error.response)}`);

      // 마지막 시도가 아니면 잠시 대기 후 재시도
      if (attempt < MAX_RETRIES) {
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }
  }

  throw new Error(`[SubheadingAgent] LLM ${MAX_RETRIES}회 시도 후 최종 실패 (category=${category}). 마지막 에러: ${lastError?.message || 'unknown'}`);
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
  const parts = [];
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
