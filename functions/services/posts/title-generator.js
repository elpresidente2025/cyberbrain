'use strict';

const { buildTitlePrompt } = require('../../prompts/builders/title-generation');
const { callGenerativeModel } = require('../gemini');
const { findUnsupportedNumericTokens } = require('../../utils/fact-guard');

const NAVER_CHAR_LIMIT = 25;

function normalizeSpaces(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

function cleanTitleResponse(text) {
  return String(text || '')
    .replace(/```json/g, '')
    .replace(/```/g, '')
    .split('\n')[0]
    .trim()
    .replace(/^["']|["']$/g, '');
}

function pickShortFallback(primaryKeyword, limit = NAVER_CHAR_LIMIT) {
  const candidates = [];
  if (primaryKeyword) {
    candidates.push(`${primaryKeyword} 현안 진단`);
    candidates.push(`${primaryKeyword} 현안`);
    candidates.push(`${primaryKeyword} 진단`);
    candidates.push(primaryKeyword);
  }
  candidates.push('현안 진단');
  candidates.push('현안 점검');
  return candidates.find((candidate) => candidate && candidate.length <= limit) || '현안 진단';
}

function shrinkTitleByRules(title, { primaryKeyword, limit = NAVER_CHAR_LIMIT } = {}) {
  let normalized = normalizeSpaces(title);
  if (normalized.length <= limit) return normalized;

  normalized = normalized.replace(/[-–—:|·,]+$/g, '').trim();
  if (normalized.length <= limit) return normalized;

  const separatorRegex = /\s*[-–—:|·,]\s*/;
  if (separatorRegex.test(normalized)) {
    const parts = normalized.split(separatorRegex).map((part) => part.trim()).filter(Boolean);
    if (parts.length > 0) {
      const head = parts[0];
      if (head.length <= limit) return head;
      normalized = head;
    }
  }

  const words = normalized.split(' ').filter(Boolean);
  while (words.length > 1 && words.join(' ').length > limit) {
    words.pop();
  }
  const compact = normalizeSpaces(words.join(' '));
  if (compact.length <= limit) return compact;

  return pickShortFallback(primaryKeyword, limit);
}

async function rewriteTitleToLimit({ title, modelName, userKeywords, topic, limit = NAVER_CHAR_LIMIT }) {
  const primaryKeyword = userKeywords?.[0] || '';
  const prompt = `다음 제목을 ${limit}자 이내로 다시 작성하세요.
- 의미 유지, 과장 금지
- 기존 숫자/고유명사만 사용 (새 숫자 금지)
- 키워드는 가능하면 제목 앞쪽에 배치
- 부제목(:,-) 금지, 문장 중간 끊기 금지
- 출력은 제목 한 줄만

원본 제목: ${title}
주제: ${topic || ''}
키워드: ${primaryKeyword || ''}`;

  try {
    const response = await callGenerativeModel(prompt, 1, modelName, false);
    const rewritten = normalizeSpaces(cleanTitleResponse(response));
    if (rewritten && rewritten.length <= limit) return rewritten;
    return '';
  } catch (error) {
    console.warn('⚠️ 제목 재작성 실패:', error.message);
    return '';
  }
}

/**
 * 본문 내용을 기반으로 제목을 생성하는 함수
 * @param {Object} params - 제목 생성에 필요한 파라미터
 * @param {string} params.content - 생성된 본문 내용
 * @param {string|Array} params.backgroundInfo - 배경정보
 * @param {Array} params.keywords - 키워드 목록
 * @param {Array} params.userKeywords - 사용자가 직접 입력한 노출 희망 검색어
 * @param {string} params.topic - 주제
 * @param {string} params.fullName - 작성자 이름
 * @param {string} params.modelName - 사용할 AI 모델명
 * @param {string} params.category - 카테고리
 * @param {string} params.subCategory - 하위 카테고리
 * @param {string} params.status - 사용자 상태 (준비/현역/예비/후보)
 * @returns {Promise<string>} - 생성된 제목
 */
async function generateTitleFromContent({ content, backgroundInfo, keywords, userKeywords, topic, fullName, modelName, category, subCategory, status, factAllowlist = null }) {
  console.log('📝 2단계: 본문 기반 제목 생성 시작');

  // 본문에서 HTML 태그 제거하고 미리보기 추출
  const contentPreview = content.substring(0, 1000).replace(/<[^>]*>/g, '');

  // 배경정보 텍스트 추출
  const backgroundText = Array.isArray(backgroundInfo)
    ? backgroundInfo.filter(item => item && item.trim()).join('\n')
    : backgroundInfo || '';

  // 분리된 프롬프트 빌더 사용 (선거법 준수를 위해 status 전달)
  const titlePrompt = buildTitlePrompt({
    contentPreview,
    backgroundText,
    topic,
    fullName,
    keywords,
    userKeywords,
    category,
    subCategory,
    status
  });

  try {
    const titleResponse = await callGenerativeModel(titlePrompt, 1, modelName, false);
    let cleanTitle = normalizeSpaces(cleanTitleResponse(titleResponse));
    const primaryKeyword = userKeywords?.[0] || '';

    if (cleanTitle.length > NAVER_CHAR_LIMIT) {
      console.warn(`⚠️ 제목 길이 초과 (${cleanTitle.length}자): "${cleanTitle}"`);
      const rewritten = await rewriteTitleToLimit({
        title: cleanTitle,
        modelName,
        userKeywords,
        topic,
        limit: NAVER_CHAR_LIMIT
      });
      if (rewritten) {
        cleanTitle = rewritten;
      } else {
        cleanTitle = shrinkTitleByRules(cleanTitle, { primaryKeyword, limit: NAVER_CHAR_LIMIT });
      }
    }

    if (factAllowlist) {
      const titleCheck = findUnsupportedNumericTokens(cleanTitle, factAllowlist);
      if (!titleCheck.passed) {
        let sanitizedTitle = cleanTitle;
        titleCheck.unsupported.forEach((token) => {
          sanitizedTitle = sanitizedTitle.split(token).join(' ');
        });
        sanitizedTitle = normalizeSpaces(sanitizedTitle).replace(/[-–—:,]+$/g, '').trim();
        cleanTitle = sanitizedTitle || pickShortFallback(primaryKeyword, NAVER_CHAR_LIMIT);
      }
    }

    if (cleanTitle.length > NAVER_CHAR_LIMIT) {
      cleanTitle = shrinkTitleByRules(cleanTitle, { primaryKeyword, limit: NAVER_CHAR_LIMIT });
    }

    console.log('✅ 제목 생성 완료:', cleanTitle);
    return cleanTitle;
  } catch (error) {
    console.error('❌ 제목 생성 실패:', error.message);
    // 실패 시 기본 제목 반환
    return `${topic} 관련 원고`;
  }
}

module.exports = {
  generateTitleFromContent
};
