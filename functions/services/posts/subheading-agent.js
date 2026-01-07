'use strict';

const { callGenerativeModel } = require('../gemini');

function stripHtml(text) {
  return String(text || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

function coerceQuestion(text) {
  if (!text) return '';
  let cleaned = String(text)
    .replace(/^["'“‘]|["'”’]$/g, '')
    .replace(/^\d+[\).]\s*/, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (!cleaned) return '';
  if (!cleaned.endsWith('?')) {
    cleaned = `${cleaned}?`;
  }
  return cleaned;
}

function parseHeadingsResponse(responseText) {
  if (!responseText) return null;
  let payload = responseText.trim();
  if (!payload) return null;

  try {
    return JSON.parse(payload);
  } catch (error) {
    const jsonMatch = payload.match(/\{[\s\S]*\}/);
    if (!jsonMatch) return null;
    try {
      return JSON.parse(jsonMatch[0]);
    } catch (parseError) {
      return null;
    }
  }
}

function buildAeoSubheadingPrompt(sections, { fullName, fullRegion }) {
  const sectionBlocks = sections.map((section, index) => {
    const trimmed = String(section || '').trim();
    return `${index + 1}) ${trimmed}`;
  }).join('\n\n');

  const entityHints = [fullName, fullRegion]
    .filter(Boolean)
    .join(', ');
  const desiredCount = sections.length;

  return `# Role Definition
당신은 'AEO(Answer Engine Optimization) Specialist'입니다.
당신의 임무는 주어진 본문 단락을 가장 잘 설명하는 질문형 소제목(H2/H3)을 만드는 것입니다.

# Logical Process (Step-by-Step)
1) Analyze: 본문 단락을 깊이 읽고 핵심 사실/해답을 파악하세요.
2) Reverse-Engineer: 이 단락이 "답변"이라면, 사용자가 던졌을 질문은 무엇인가?
3) Formulate: 그 질문을 소제목으로 만드세요.

# H2/H3 Generation Rules (Strict)
## Rule 1: Question Format (Q&A Match)
- 소제목은 반드시 질문형이어야 합니다.
- 본문 단락이 소제목의 직접적인 "답변"이 되어야 합니다.

## Rule 2: Entity First (Context Anchoring)
- 대명사 금지(그/이것/저것 등).
- 본문에 등장한 인물/지역/정책 등 구체 엔티티를 반드시 포함하세요.
- 엔티티는 가능하면 문장 앞쪽에 배치하세요.

## Rule 3: Concrete Details (No Clickbait)
- 숫자(날짜/금액/비율/건수)가 있으면 소제목에 반영하세요.
- 과장/클릭베이트 금지. 구체적으로 쓰세요.

## Rule 4: Length Limit
- ? ???? 12~25? ??(?? ??)? ?????.
- ?? ??? ??? ????? ??? ???? ????.
- ?? ?? ?? ??? ??? ????.

## Rule 5: 금지 소제목
- 아래 문구는 절대 사용 금지:
  "무엇을 나누고 싶은가", "생각의 핵심은 무엇인가", "함께 생각할 점은 무엇인가",
  "현안은 무엇인가", "핵심 쟁점은 무엇인가", "영향과 과제는 무엇인가"

# Few-Shot Example
[Input Body Text]
김교흥 의원은 서구 주민들의 주차난 해소를 위해 '공영주차장 3개소 신설' 예산 50억 원을 확보했다고 밝혔다. 특히 루원시티 상업지구와 가정동 주택가에 우선적으로 주차 타워가 건립될 예정이며, 완공 목표는 2027년 하반기다.

[Bad Output]
- 주차난 해소를 위한 노력
- 김교흥의 예산 확보 성과

[Good Output]
- 김교흥 의원이 확보한 '서구 주차장 예산' 규모와 건립 위치는?
- 루원시티·가정동 주차 타워, 2027년까지 완공 가능한가?

# Instruction
- 본문 단락 수: ${desiredCount}개
- headings 배열도 반드시 ${desiredCount}개로 출력하세요.

[엔티티 힌트]
${entityHints || '(없음)'}

[본문 단락]
${sectionBlocks}

출력은 반드시 JSON만 허용:
{"headings":["...","..."]}`;
}

async function generateAeoSubheadings({ sections, modelName, fullName, fullRegion }) {
  if (!sections || sections.length === 0) return null;
  const cleanedSections = sections
    .map((section) => stripHtml(section))
    .map((text) => text.replace(/\s+/g, ' ').trim())
    .filter(Boolean);

  if (cleanedSections.length === 0) return null;

  const prompt = buildAeoSubheadingPrompt(cleanedSections, { fullName, fullRegion });
  const response = await callGenerativeModel(prompt, 1, modelName, true);
  const parsed = parseHeadingsResponse(response);
  let headings = Array.isArray(parsed?.headings)
    ? parsed.headings.map(coerceQuestion).filter(Boolean)
    : [];

  if (headings.length === 0) return null;
  if (headings.length > cleanedSections.length) {
    headings = headings.slice(0, cleanedSections.length);
  }
  return headings;
}

module.exports = {
  generateAeoSubheadings
};
