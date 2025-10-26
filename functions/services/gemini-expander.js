/**
 * services/gemini-expander.js
 * Google Gemini API를 이용한 키워드 확장
 */

'use strict';

const { GoogleGenerativeAI } = require('@google/generative-ai');

/**
 * Gemini API를 이용하여 롱테일 키워드 생성
 * @param {Object} params - 확장 파라미터
 * @returns {Promise<Array<string>>} 확장된 키워드 배열
 */
async function expandKeywordsWithGemini(params) {
  const {
    district,
    topic,
    baseKeywords = [],
    targetCount = 30
  } = params;

  try {
    console.log(`🤖 [Gemini] 키워드 확장 시작: ${district} - ${topic}`);

    // Gemini API 초기화
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      throw new Error('GEMINI_API_KEY 환경변수가 설정되지 않았습니다');
    }

    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({ model: 'gemini-1.5-flash' });

    // 프롬프트 생성
    const prompt = generateExpansionPrompt(district, topic, baseKeywords, targetCount);

    console.log(`📤 [Gemini] 프롬프트 전송 중...`);

    // Gemini API 호출
    const result = await model.generateContent(prompt);
    const response = await result.response;
    const text = response.text();

    console.log(`📥 [Gemini] 응답 수신 완료`);

    // JSON 파싱
    const expandedKeywords = parseGeminiResponse(text);

    if (expandedKeywords.length === 0) {
      console.warn(`⚠️ [Gemini] 확장된 키워드가 없습니다. 기본 키워드 사용`);
      return generateFallbackKeywords(district, topic, baseKeywords, targetCount);
    }

    console.log(`✅ [Gemini] ${expandedKeywords.length}개 키워드 생성 완료`);

    return expandedKeywords.slice(0, targetCount);

  } catch (error) {
    console.error(`❌ [Gemini] 키워드 확장 실패:`, error.message);

    // 폴백: 기본 키워드 조합 생성
    console.log(`🔄 [Gemini] 폴백 모드: 기본 키워드 생성`);
    return generateFallbackKeywords(district, topic, baseKeywords, targetCount);
  }
}

/**
 * Gemini용 프롬프트 생성
 * @param {string} district - 지역구
 * @param {string} topic - 주제
 * @param {Array<string>} baseKeywords - 기본 키워드
 * @param {number} targetCount - 목표 개수
 * @returns {string} 프롬프트
 */
function generateExpansionPrompt(district, topic, baseKeywords, targetCount) {
  const baseKeywordList = baseKeywords.length > 0
    ? `\n참고할 기본 키워드: ${baseKeywords.join(', ')}`
    : '';

  return `당신은 정치인을 위한 SEO 전문가입니다.
지역구 의원이 블로그 콘텐츠를 작성할 때 사용할 롱테일 키워드를 생성해주세요.

**지역구:** ${district}
**정책 주제:** ${topic}${baseKeywordList}

**요구사항:**
1. 총 ${targetCount}개의 롱테일 키워드를 생성하세요
2. 각 키워드는 3-6개 단어로 구성되어야 합니다
3. 지역구 이름(${district})과 주제(${topic})를 자연스럽게 포함하세요
4. 주민들이 실제로 검색할 법한 구체적인 표현을 사용하세요
5. 검색 의도가 명확한 키워드를 우선하세요

**좋은 예시:**
- "${district} ${topic} 주민 의견"
- "${district} ${topic} 현황 및 문제점"
- "${district} 지역 ${topic} 개선 방안"
- "${district} ${topic} 예산 사용처"

**피해야 할 예시:**
- 너무 짧은 키워드 (예: "${topic}")
- 추상적인 표현 (예: "${topic} 중요성")
- 지역과 무관한 표현

**출력 형식:**
반드시 JSON 배열 형식으로만 응답하세요. 다른 설명이나 텍스트는 포함하지 마세요.

["키워드1", "키워드2", "키워드3", ...]

JSON 배열로 ${targetCount}개의 키워드를 생성해주세요:`;
}

/**
 * Gemini 응답 파싱
 * @param {string} text - Gemini 응답 텍스트
 * @returns {Array<string>} 파싱된 키워드 배열
 */
function parseGeminiResponse(text) {
  try {
    // JSON 블록 추출 시도
    const jsonMatch = text.match(/\[[\s\S]*\]/);

    if (!jsonMatch) {
      console.warn(`⚠️ [Gemini] JSON 형식을 찾을 수 없습니다`);
      return [];
    }

    const jsonText = jsonMatch[0];
    const keywords = JSON.parse(jsonText);

    if (!Array.isArray(keywords)) {
      console.warn(`⚠️ [Gemini] 배열 형식이 아닙니다`);
      return [];
    }

    // 문자열만 필터링하고 중복 제거
    const validKeywords = keywords
      .filter(k => typeof k === 'string' && k.trim().length > 0)
      .map(k => k.trim());

    return [...new Set(validKeywords)];

  } catch (error) {
    console.error(`❌ [Gemini] 응답 파싱 실패:`, error.message);
    return [];
  }
}

/**
 * 폴백 키워드 생성 (Gemini 실패 시)
 * @param {string} district - 지역구
 * @param {string} topic - 주제
 * @param {Array<string>} baseKeywords - 기본 키워드
 * @param {number} targetCount - 목표 개수
 * @returns {Array<string>} 생성된 키워드 배열
 */
function generateFallbackKeywords(district, topic, baseKeywords, targetCount) {
  const keywords = [];

  // 기본 템플릿
  const templates = [
    `${district} ${topic}`,
    `${district} ${topic} 현황`,
    `${district} ${topic} 문제점`,
    `${district} ${topic} 개선`,
    `${district} ${topic} 정책`,
    `${district} ${topic} 주민 의견`,
    `${district} ${topic} 예산`,
    `${district} ${topic} 사업`,
    `${district} ${topic} 계획`,
    `${district} 지역 ${topic}`,
    `${district} ${topic} 민원`,
    `${district} ${topic} 해결 방안`,
    `${district} ${topic} 지원`,
    `${district} ${topic} 현실`,
    `${district} ${topic} 의원`,
    `${district} ${topic} 활동`,
    `${district} ${topic} 필요성`,
    `${district} ${topic} 변화`,
    `${district} ${topic} 주민`,
    `${district} ${topic} 개발`
  ];

  // 기본 템플릿 추가
  keywords.push(...templates);

  // 기본 키워드 조합 추가
  if (baseKeywords.length > 0) {
    baseKeywords.forEach(base => {
      keywords.push(`${district} ${base}`);
      keywords.push(`${base} ${district}`);
      keywords.push(`${district} ${base} 현황`);
      keywords.push(`${district} ${base} 개선`);
    });
  }

  // 추가 변형
  const modifiers = ['현황', '문제', '해결', '개선', '정책', '의견', '민원', '지원'];
  modifiers.forEach(modifier => {
    keywords.push(`${district} ${topic} ${modifier}`);
  });

  // 중복 제거 및 개수 제한
  const uniqueKeywords = [...new Set(keywords)];

  return uniqueKeywords.slice(0, targetCount);
}

/**
 * 키워드 품질 검증
 * @param {Array<string>} keywords - 검증할 키워드 배열
 * @param {string} district - 지역구
 * @param {string} topic - 주제
 * @returns {Array<string>} 검증된 키워드 배열
 */
function validateKeywords(keywords, district, topic) {
  return keywords.filter(keyword => {
    // 최소 길이 확인 (2단어 이상)
    const words = keyword.trim().split(/\s+/);
    if (words.length < 2) {
      return false;
    }

    // 최대 길이 확인 (너무 길면 제외)
    if (keyword.length > 100) {
      return false;
    }

    // 특수문자나 숫자만 있는 키워드 제외
    if (!/[가-힣a-zA-Z]/.test(keyword)) {
      return false;
    }

    return true;
  });
}

/**
 * 키워드 확장 및 검증 (전체 프로세스)
 * @param {Object} params - 확장 파라미터
 * @returns {Promise<Array<string>>} 검증된 확장 키워드 배열
 */
async function expandAndValidateKeywords(params) {
  const { district, topic } = params;

  // Gemini로 확장
  const expandedKeywords = await expandKeywordsWithGemini(params);

  // 품질 검증
  const validatedKeywords = validateKeywords(expandedKeywords, district, topic);

  console.log(`✅ [Gemini] 최종 ${validatedKeywords.length}개 키워드 (검증 완료)`);

  return validatedKeywords;
}

module.exports = {
  expandKeywordsWithGemini,
  expandAndValidateKeywords,
  generateFallbackKeywords,
  validateKeywords
};
