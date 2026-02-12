'use strict';

const { generateAndValidateTitle } = require('../../prompts/builders/title-generation');
const { callGenerativeModel } = require('../gemini');

const NAVER_CHAR_LIMIT = 25;

function normalizeTitleRegion(title, titleScope = {}) {
  if (!title) return title;
  if (!titleScope || !titleScope.avoidLocalInTitle) return title;

  const regionLocal = String(titleScope.regionLocal || '').trim();
  const regionMetro = String(titleScope.regionMetro || '').trim();
  const metroLabel = regionMetro
    ? regionMetro.replace(/광역시|특별시|특별자치시|자치시|자치도|도$/g, '').trim()
    : '';
  const finalMetro = metroLabel || regionMetro;

  let updated = title;
  if (regionLocal) {
    updated = finalMetro
      ? updated.split(regionLocal).join(finalMetro)
      : updated.split(regionLocal).join('');
  }

  return updated.replace(/\s{2,}/g, ' ').trim();
}

/**
 * 본문 내용을 기반으로 제목을 생성하는 함수 (통합된 Builder 로직 사용)
 */
async function generateTitleFromContent({ content, backgroundInfo, keywords, userKeywords, topic, fullName, modelName, category, subCategory, status, factAllowlist = null, titleScope = null }) {
  console.log('📝 [Unified] 본문 기반 제목 생성 시작');

  // 1. 파라미터 준비
  const contentPreview = String(content || '').substring(0, 3000).replace(/<[^>]*>/g, '');
  const backgroundText = Array.isArray(backgroundInfo)
    ? backgroundInfo.filter(item => item && item.trim()).join('\n')
    : backgroundInfo || '';

  const params = {
    contentPreview,
    backgroundText,
    topic,
    fullName,
    keywords,
    userKeywords,
    category,
    subCategory,
    status,
    titleScope
  };

  // 2. 생성 함수 어댑터 (Gemini 호출)
  const generateFn = async (prompt) => {
    try {
      const resp = await callGenerativeModel(prompt, 0.8, modelName, false);

      // 간단한 후처리 (JSON이나 마크다운 제거)
      let cleanText = resp.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();

      // JSON 파싱 시도 (TitleAgent와 동일하게)
      try {
        if (cleanText.startsWith('{')) {
          const parsed = JSON.parse(cleanText);
          return parsed.title || cleanText;
        }
      } catch (e) {
        // parsing failed, use raw text
      }

      // 정규식으로 title 추출 시도
      const match = cleanText.match(/제목:\s*"([^"]+)"/);
      if (match) return match[1];

      return cleanText.replace(/^["']|["']$/g, '');
    } catch (error) {
      console.error('Gemini Call Failed:', error.message);
      return '';
    }
  };

  // 3. 통합 생성/검증 로직 실행
  const result = await generateAndValidateTitle(generateFn, params, {
    minScore: 70,
    maxAttempts: 3,
    onProgress: ({ attempt, score }) => {
      console.log(`🔄 [Legacy-Adapter] 제목 생성 시도 ${attempt} (점수: ${score})`);
    }
  });

  let finalTitle = result.title;

  // 4. 최종 후처리 (지역명 정규화 등)
  if (finalTitle) {
    finalTitle = normalizeTitleRegion(finalTitle, titleScope);
  }

  // 5. 실패 시 폴백
  if (!finalTitle || (result.score < 30 && !result.passed)) {
    console.warn(`⚠️ 제목 생성 실패 또는 저품질 (점수: ${result.score}). 폴백 사용.`);
    return topic ? `${topic.substring(0, 20)} 관련 글` : '새 원고';
  }

  return finalTitle;
}

module.exports = {
  generateTitleFromContent
};
