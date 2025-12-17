'use strict';

const { buildTitlePrompt } = require('../../prompts/builders/title-generation');
const { callGenerativeModel } = require('../gemini');

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
async function generateTitleFromContent({ content, backgroundInfo, keywords, userKeywords, topic, fullName, modelName, category, subCategory, status }) {
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
    // 제목 생성은 순수 텍스트 모드 (JSON mode 비활성화)
    const titleResponse = await callGenerativeModel(titlePrompt, 1, modelName, false);

    // JSON이나 코드 블록 제거
    let cleanTitle = titleResponse
      .replace(/```json/g, '')
      .replace(/```/g, '')
      .trim();

    // 첫 번째 줄만 추출 (여러 줄인 경우)
    cleanTitle = cleanTitle.split('\n')[0].trim();

    // 따옴표 제거
    cleanTitle = cleanTitle.replace(/^["']|["']$/g, '');

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
