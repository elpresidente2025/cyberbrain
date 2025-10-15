/**
 * functions/prompts/title-generation.js
 * 제목 생성 프롬프트 템플릿
 */

'use strict';

/**
 * 본문 내용 기반 제목 생성 프롬프트를 빌드합니다
 * @param {Object} params - 프롬프트 빌드에 필요한 파라미터
 * @param {string} params.contentPreview - 본문 미리보기 (HTML 태그 제거됨)
 * @param {string} params.backgroundText - 배경정보 텍스트
 * @param {string} params.topic - 주제
 * @param {string} params.fullName - 작성자 이름
 * @param {Array<string>} params.keywords - 필수 키워드 목록
 * @returns {string} 완성된 제목 생성 프롬프트
 */
function buildTitlePrompt({ contentPreview, backgroundText, topic, fullName, keywords }) {
  return `다음 본문을 읽고 핵심 내용을 담은 구체적인 제목을 생성하세요.

본문 내용 (일부):
${contentPreview}

배경정보 핵심:
${backgroundText.substring(0, 500)}

주제: ${topic}
작성자: ${fullName}
필수 포함 키워드: ${keywords.slice(0, 5).join(', ')}

요구사항:
1. 제목 길이: 20-30자
2. 본문의 핵심 내용을 정확히 반영
3. 필수 키워드 중 최소 1개 이상 포함
4. 구체적인 숫자, 이름, 행사명 등 포함
5. 추상적 표현 금지

제목만 출력하세요:`;
}

module.exports = {
  buildTitlePrompt,
};
