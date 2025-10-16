'use strict';

const { callGenerativeModel } = require('../gemini');

/**
 * AI 응답 검증 및 재시도
 * @param {Object} params
 * @param {string} params.prompt - 프롬프트
 * @param {string} params.modelName - AI 모델명
 * @param {string} params.fullName - 작성자 이름
 * @param {string} params.fullRegion - 지역명
 * @param {number} params.targetWordCount - 목표 글자수
 * @param {number} params.maxAttempts - 최대 시도 횟수
 * @returns {Promise<string>} AI 응답
 */
async function validateAndRetry({
  prompt,
  modelName,
  fullName,
  fullRegion,
  targetWordCount,
  maxAttempts = 3
}) {
  let apiResponse;
  let attempt = 0;
  let currentPrompt = prompt;

  while (attempt < maxAttempts) {
    attempt++;
    console.log(`🔥 AI 호출 시도 ${attempt}/${maxAttempts}...`);

    apiResponse = await callGenerativeModel(currentPrompt, 1, modelName);

    // 기본 검증
    if (apiResponse && apiResponse.length > 100) {
      // JSON 파싱하여 실제 content 추출
      let contentToCheck = apiResponse;
      try {
        const jsonMatch = apiResponse.match(/```json\s*([\s\S]*?)\s*```/) ||
                         apiResponse.match(/\{[\s\S]*?\}/);
        if (jsonMatch) {
          const parsed = JSON.parse(jsonMatch[1] || jsonMatch[0]);
          contentToCheck = parsed.content || apiResponse;
        }
      } catch (e) {
        // JSON 파싱 실패시 원본 사용
      }

      // HTML 태그 제거하고 순수 텍스트 길이 계산 (공백 제외)
      const plainText = contentToCheck.replace(/<[^>]*>/g, '').replace(/\s/g, '');
      const actualWordCount = plainText.length;
      const minWordCount = Math.floor(targetWordCount * 0.9); // 목표의 90%

      console.log(`📊 분량 체크 - 실제: ${actualWordCount}자, 목표: ${targetWordCount}자, 최소: ${minWordCount}자`);

      // 🔧 수정: 지역 검증을 경고로만 처리 (검증 실패로 취급하지 않음)
      const hasName = fullName && apiResponse.includes(fullName);
      const hasRegion = !fullRegion || apiResponse.includes(fullRegion);
      const hasSufficientLength = actualWordCount >= minWordCount;

      // 지역 미포함 시 경고만 출력
      if (fullRegion && !apiResponse.includes(fullRegion)) {
        console.log(`⚠️ 지역명 '${fullRegion}' 미포함 (경고만, 검증 통과)`);
      }

      console.log(`🔍 검증 결과 - 이름: ${hasName}, 지역: ${hasRegion}, 분량충족: ${hasSufficientLength}`);

      // 🔧 수정: 이름 검증도 선택적으로 변경 (이름이 없으면 검증 통과)
      const nameCheck = !fullName || hasName;

      if (nameCheck && hasSufficientLength) {
        console.log(`✅ 모든 검증 통과! (${attempt}번째 시도)`);
        break;
      }

      if (attempt < maxAttempts) {
        if (!hasSufficientLength) {
          console.log(`⚠️ 분량 부족 (${actualWordCount}/${minWordCount}자) - 재생성 필요`);
          currentPrompt = currentPrompt + `\n\n**중요: 반드시 ${targetWordCount}자 이상으로 작성하세요.**`;
        } else {
          console.log(`❌ 기타 검증 실패 - 재시도 필요`);
        }
        continue;
      }
    }

    if (attempt >= maxAttempts) {
      console.log(`⚠️ 최대 시도 횟수 초과 - 현재 응답 사용`);
    }
  }

  return apiResponse;
}

module.exports = {
  validateAndRetry
};
