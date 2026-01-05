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

  return `당신은 AEO(Answer Engine Optimization) 소제목(H2/H3) 전문가입니다.
아래 본문 단락은 "답변"입니다. 각 단락에 대응하는 질문형 소제목을 만들어 주세요.

[규칙]
1) 반드시 질문형 문장으로 작성하세요.
2) 대명사는 금지입니다. 본문에 등장한 인물/지역/정책 등 구체 엔티티를 포함하세요.
3) 숫자/날짜/금액/비율이 있으면 소제목에 반영하세요.
4) 과장/클릭베이트 금지. 본문이 답이 되도록 구체적으로 작성하세요.
5) 가능하면 엔티티를 문장 앞쪽에 배치하세요.

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
  const headings = Array.isArray(parsed?.headings)
    ? parsed.headings.map(coerceQuestion).filter(Boolean)
    : [];

  if (headings.length === 0) return null;
  return headings;
}

module.exports = {
  generateAeoSubheadings
};
