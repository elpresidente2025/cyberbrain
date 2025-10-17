'use strict';

const { callGenerativeModel } = require('../gemini');

/**
 * 키워드 출현 횟수 카운팅 (띄어쓰기 정확히 일치)
 * @param {string} content - 검사할 콘텐츠 (HTML 포함 가능)
 * @param {string} keyword - 검색할 키워드
 * @returns {number} 출현 횟수
 */
function countKeywordOccurrences(content, keyword) {
  const cleanContent = content.replace(/<[^>]*>/g, ''); // HTML 제거
  // 특수문자 이스케이프 처리
  const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(escapedKeyword, 'g');
  const matches = cleanContent.match(regex);
  return matches ? matches.length : 0;
}

/**
 * 키워드 삽입 검증 (400자당 1회 기준)
 * @param {string} content - 검증할 콘텐츠
 * @param {Array<string>} keywords - 검증할 키워드 배열
 * @param {number} targetWordCount - 목표 글자수
 * @returns {Object} 검증 결과
 */
function validateKeywordInsertion(content, keywords, targetWordCount) {
  if (!keywords || keywords.length === 0) {
    return { valid: true, details: {} };
  }

  const plainText = content.replace(/<[^>]*>/g, '').replace(/\s/g, '');
  const actualWordCount = plainText.length;

  // 400자당 1회 기준 계산
  const expectedCount = Math.floor(actualWordCount / 400);
  const minCount = Math.max(1, expectedCount); // 최소 1회

  const results = {};
  let totalOccurrences = 0;
  let allValid = true;

  for (const keyword of keywords) {
    const count = countKeywordOccurrences(content, keyword);
    totalOccurrences += count;
    const isValid = count >= minCount;

    results[keyword] = {
      count,
      expected: minCount,
      valid: isValid
    };

    if (!isValid) {
      allValid = false;
    }
  }

  // 키워드 밀도 계산 (전체 키워드 글자수 / 전체 글자수 * 100)
  const totalKeywordChars = keywords.reduce((sum, kw) => {
    const occurrences = countKeywordOccurrences(content, kw);
    return sum + (kw.replace(/\s/g, '').length * occurrences);
  }, 0);
  const density = actualWordCount > 0 ? (totalKeywordChars / actualWordCount * 100) : 0;
  const densityValid = density >= 1.5 && density <= 3.0;

  return {
    valid: allValid && densityValid,
    details: {
      keywords: results,
      density: {
        value: density.toFixed(2),
        valid: densityValid,
        optimal: density >= 1.5 && density <= 2.5
      },
      wordCount: actualWordCount,
      expectedPerKeyword: minCount
    }
  };
}

/**
 * AI 응답 검증 및 재시도
 * @param {Object} params
 * @param {string} params.prompt - 프롬프트
 * @param {string} params.modelName - AI 모델명
 * @param {string} params.fullName - 작성자 이름
 * @param {string} params.fullRegion - 지역명
 * @param {number} params.targetWordCount - 목표 글자수
 * @param {Array<string>} params.keywords - 검증할 키워드 배열
 * @param {number} params.maxAttempts - 최대 시도 횟수
 * @returns {Promise<string>} AI 응답
 */
async function validateAndRetry({
  prompt,
  modelName,
  fullName,
  fullRegion,
  targetWordCount,
  keywords = [],
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
      let parsedContent = null;

      try {
        const jsonMatch = apiResponse.match(/```json\s*([\s\S]*?)\s*```/) ||
                         apiResponse.match(/\{[\s\S]*?\}/);
        if (jsonMatch) {
          parsedContent = JSON.parse(jsonMatch[1] || jsonMatch[0]);
          contentToCheck = parsedContent.content || apiResponse;
        }
      } catch (e) {
        // JSON 파싱 실패시 원본 사용
      }

      // HTML 태그 제거하고 순수 텍스트 길이 계산 (공백 제외)
      const plainText = contentToCheck.replace(/<[^>]*>/g, '').replace(/\s/g, '');
      const actualWordCount = plainText.length;
      const minWordCount = Math.floor(targetWordCount * 0.9); // 목표의 90%

      console.log(`📊 분량 체크 - 실제: ${actualWordCount}자, 목표: ${targetWordCount}자, 최소: ${minWordCount}자`);

      // 기존 검증
      const hasName = !fullName || apiResponse.includes(fullName);
      const hasSufficientLength = actualWordCount >= minWordCount;

      // 지역 미포함 시 경고만 출력
      if (fullRegion && !apiResponse.includes(fullRegion)) {
        console.log(`⚠️ 지역명 '${fullRegion}' 미포함 (경고만, 검증 통과)`);
      }

      // ✨ 새로운 키워드 검증
      const keywordValidation = validateKeywordInsertion(
        contentToCheck,
        keywords,
        targetWordCount
      );

      console.log(`🔍 기본 검증 - 이름: ${hasName}, 분량충족: ${hasSufficientLength}`);
      console.log(`🔑 키워드 검증:`, JSON.stringify(keywordValidation.details, null, 2));

      // 모든 검증 통과 확인
      if (hasName && hasSufficientLength && keywordValidation.valid) {
        console.log(`✅ 모든 검증 통과! (${attempt}번째 시도)`);
        break;
      }

      // 재시도 필요 시 개선 지시사항 추가
      if (attempt < maxAttempts) {
        let improvementInstructions = '\n\n**중요: 다음 사항을 반드시 개선하세요:**\n';
        let needsImprovement = false;

        if (!hasSufficientLength) {
          improvementInstructions += `- 분량 부족: ${targetWordCount}자 이상으로 작성하세요.\n`;
          needsImprovement = true;
        }

        if (!keywordValidation.valid) {
          const { keywords: kwResults, expectedPerKeyword } = keywordValidation.details;
          improvementInstructions += `- 검색어 삽입 부족:\n`;

          for (const [kw, result] of Object.entries(kwResults)) {
            if (!result.valid) {
              improvementInstructions += `  • "${kw}": 현재 ${result.count}회 → 최소 ${expectedPerKeyword}회 이상 필요\n`;
            }
          }

          improvementInstructions += `  • 본문 전체(도입부, 본론, 결론)에 고르게 분산 배치하세요.\n`;
          improvementInstructions += `  • 문장의 주어, 목적어, 수식어 위치에 자연스럽게 배치하세요.\n`;
          needsImprovement = true;
        }

        if (needsImprovement) {
          console.log(`⚠️ 검증 실패 - 재생성 필요:`, improvementInstructions);
          currentPrompt = currentPrompt + improvementInstructions;
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
