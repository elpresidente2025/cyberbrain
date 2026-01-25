'use strict';

const { buildTitlePrompt } = require('../../prompts/builders/title-generation');
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

function normalizeSpaces(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

function cleanTitleResponse(text) {
  const raw = String(text || '').trim();

  // JSON 응답이면 title 키 추출
  try {
    const cleaned = raw.replace(/```json\s*/g, '').replace(/```/g, '').trim();
    if (cleaned.startsWith('{')) {
      const parsed = JSON.parse(cleaned);
      if (parsed.title && typeof parsed.title === 'string') {
        return parsed.title.trim();
      }
    }
  } catch {
    // JSON 파싱 실패 - 아래 로직으로 진행
  }

  // 텍스트에서 title 키 추출 시도
  const titleMatch = raw.match(/"title"\s*:\s*"([^"]+)"/);
  if (titleMatch) {
    return titleMatch[1].trim();
  }

  // 기존 로직: 첫 줄 추출
  return raw
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

/**
 * 제목 검증 함수 - Hallucination 및 규칙 위반 체크
 * @param {string} title - 생성된 제목
 * @param {string} content - 본문 내용
 * @returns {{ valid: boolean, reason?: string, value?: string }}
 */
function validateTitle(title, content) {
  if (!title) {
    return { valid: false, reason: 'empty', message: '제목이 비어있음' };
  }

  // 1. 본문에 없는 숫자 사용 체크 (Hallucination 감지)
  const titleNumbers = (title.match(/\d+/g) || []).filter(n => n.length <= 6); // 6자리 이하 숫자만
  const contentText = String(content || '').replace(/<[^>]*>/g, ''); // HTML 태그 제거
  const contentNumbers = contentText.match(/\d+/g) || [];

  for (const num of titleNumbers) {
    // 연도(2024, 2025, 2026)는 허용
    if (/^20\d{2}$/.test(num)) continue;

    // 본문에 없는 숫자면 Hallucination
    if (!contentNumbers.includes(num)) {
      return {
        valid: false,
        reason: 'hallucinated_number',
        value: num,
        message: `제목에 "${num}"이 있지만 본문에 없음 - 날조 의심`
      };
    }
  }

  // 1.5. 필수 키워드 누락 체크 (NEW)
// 사용자가 지정한 키워드가 제목에 포함되지 않으면 무조건 실패 처리
// (단, '윤석열', '조경태' 등 고유명사가 키워드인 경우 필수)
if (content.userKeywords && content.userKeywords.length > 0) {
  const requiredKeyword = content.userKeywords[0]; // 1순위 키워드
  if (requiredKeyword && !title.includes(requiredKeyword)) {
    return {
      valid: false,
      reason: 'keyword_missing',
      value: requiredKeyword,
      message: `제목에 필수 키워드("${requiredKeyword}")가 포함되지 않음`
    };
  }
}

// 2. 과도하게 긴 제목 체크 (40자 이상이면 경고)
if (title.length > 40) {
  return {
    valid: false,
    reason: 'too_long',
    value: String(title.length),
    message: `제목이 ${title.length}자로 너무 김 (40자 초과)`
  };
}

return { valid: true };
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
async function generateTitleFromContent({ content, backgroundInfo, keywords, userKeywords, topic, fullName, modelName, category, subCategory, status, factAllowlist = null, titleScope = null }) {
  console.log('📝 2단계: 본문 기반 제목 생성 시작');

  // 본문에서 HTML 태그 제거하고 미리보기 추출
  const contentPreview = String(content || '').substring(0, 1000).replace(/<[^>]*>/g, '');
  const fullContent = String(content || '').replace(/<[^>]*>/g, ''); // 검증용 전체 본문

  // 배경정보 텍스트 추출
  const backgroundText = Array.isArray(backgroundInfo)
    ? backgroundInfo.filter(item => item && item.trim()).join('\n')
    : backgroundInfo || '';

  const primaryKeyword = userKeywords?.[0] || '';
  const MAX_RETRIES = 3;
  let lastValidationError = null;

  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    console.log(`🔄 제목 생성 시도 ${attempt}/${MAX_RETRIES}`);

    // 재시도 시 이전 오류 피드백 추가
    let retryFeedback = '';
    if (attempt > 1 && lastValidationError) {
      retryFeedback = `
⚠️ [이전 시도 오류 - 반드시 수정하세요]
${lastValidationError.message}
${lastValidationError.reason === 'hallucinated_number'
          ? `❌ 숫자 "${lastValidationError.value}"는 본문에 없습니다. 이 숫자를 사용하지 마세요!`
          : ''}
`;
    }

    // 분리된 프롬프트 빌더 사용 (선거법 준수를 위해 status 전달)
    const titlePrompt = buildTitlePrompt({
      contentPreview: retryFeedback + contentPreview,
      backgroundText,
      topic,
      fullName,
      keywords,
      userKeywords,
      category,
      subCategory,
      status,
      titleScope
    });

    try {
      const titleResponse = await callGenerativeModel(titlePrompt, 1, modelName, false);
      let cleanTitle = normalizeSpaces(cleanTitleResponse(titleResponse));
      cleanTitle = normalizeTitleRegion(cleanTitle, titleScope);

      // 🔒 응답이 콘텐츠처럼 보이면 재시도 (HTML 태그, "여러분", "입니다" 포함 등)
      const looksLikeContent = cleanTitle.includes('<') ||
        cleanTitle.includes('여러분') ||
        cleanTitle.endsWith('입니다') ||
        cleanTitle.endsWith('습니다') ||
        cleanTitle.length > 50;
      if (looksLikeContent) {
        console.warn(`⚠️ 제목이 콘텐츠처럼 보임 (시도 ${attempt}): "${cleanTitle.substring(0, 50)}..."`);
        lastValidationError = { reason: 'looks_like_content', message: '제목이 본문처럼 보임' };
        if (attempt < MAX_RETRIES) continue;
        // 마지막 시도면 topic 기반 폴백
        cleanTitle = topic ? `${topic.substring(0, 20)}` : '새 원고';
      }

      // ✅ 검증 단계
      const validation = validateTitle(cleanTitle, fullContent);

      if (!validation.valid) {
        console.warn(`⚠️ 제목 검증 실패 (시도 ${attempt}): ${validation.message}`);
        lastValidationError = validation;

        // 마지막 시도면 검증 실패해도 사용 (단, 경고 로그)
        if (attempt === MAX_RETRIES) {
          console.warn(`⚠️ 최대 재시도 도달, 검증 실패한 제목 사용: "${cleanTitle}"`);
          // 길이 초과만 처리하고 반환
          if (cleanTitle.length > NAVER_CHAR_LIMIT) {
            cleanTitle = shrinkTitleByRules(cleanTitle, { primaryKeyword, limit: NAVER_CHAR_LIMIT });
          }
          return cleanTitle;
        }

        continue; // 재시도
      }

      // 검증 통과 - 길이 최적화
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

      if (cleanTitle.length > NAVER_CHAR_LIMIT) {
        cleanTitle = shrinkTitleByRules(cleanTitle, { primaryKeyword, limit: NAVER_CHAR_LIMIT });
      }

      console.log(`✅ 제목 생성 완료 (시도 ${attempt}):`, cleanTitle);
      return cleanTitle;

    } catch (error) {
      console.error(`❌ 제목 생성 실패 (시도 ${attempt}):`, error.message);
      if (attempt === MAX_RETRIES) {
        return `${topic} 관련 원고`;
      }
    }
  }

  // 폴백
  return `${topic} 관련 원고`;
}

module.exports = {
  generateTitleFromContent
};
