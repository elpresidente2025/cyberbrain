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
 * 문단/문장 반복 감지 (범용)
 * @param {string} content - 검사할 콘텐츠 (HTML 포함)
 * @returns {Object} { hasRepetition: boolean, details: string }
 */
function detectRepetition(content) {
  const issues = [];

  // === 1. 문장 끊김 감지 ===
  // "의원으", "주민여", "지역을" 같은 불완전 문장 패턴
  const plainText = content.replace(/<[^>]*>/g, '');
  const incompletePatterns = /[가-힣]{2,}[으로는을를이가]\s*$/m;

  if (incompletePatterns.test(plainText)) {
    const match = plainText.match(incompletePatterns);
    issues.push(`문장 미완성 감지: "${match[0]}"`);
  }

  // === 2. 큰 단위 반복: 문단 유사도 검사 ===
  const paragraphs = content
    .split(/<\/p>/i)
    .map(p => p.replace(/<[^>]*>/g, '').trim())
    .filter(p => p.length > 50); // 50자 이상 문단만 검사

  for (let i = 0; i < paragraphs.length - 1; i++) {
    for (let j = i + 1; j < paragraphs.length; j++) {
      const similarity = calculateJaccardSimilarity(paragraphs[i], paragraphs[j]);

      // 70% 이상 유사하면 반복으로 판단
      if (similarity > 0.7) {
        const preview1 = paragraphs[i].substring(0, 50);
        const preview2 = paragraphs[j].substring(0, 50);
        issues.push(
          `문단 반복 감지 (${(similarity * 100).toFixed(0)}% 유사): ` +
          `"${preview1}..." 와 "${preview2}..."`
        );
      }
    }
  }

  // === 3. 작은 단위 반복: 문장 패턴 검사 ===
  const sentences = plainText.split(/[.!?]\s+/).filter(s => s.length > 20);
  const sentenceCount = {};

  for (const sentence of sentences) {
    // 문장 정규화 (공백, 특수문자 제거)
    const normalized = sentence.replace(/\s+/g, '').replace(/[^\w\uAC00-\uD7A3]/g, '');

    if (normalized.length > 30) { // 30자 이상 문장만 검사
      sentenceCount[normalized] = (sentenceCount[normalized] || 0) + 1;
    }
  }

  for (const [sentence, count] of Object.entries(sentenceCount)) {
    if (count >= 2) {
      // 원본 문장 복원 (첫 30자만)
      const original = sentences.find(s =>
        s.replace(/\s+/g, '').replace(/[^\w\uAC00-\uD7A3]/g, '') === sentence
      );
      issues.push(`동일 문장 ${count}회 반복: "${original ? original.substring(0, 30) : sentence.substring(0, 30)}..."`);
    }
  }

  // === 4. JSON 구조 반복 검사 ===
  // "content": "..." 패턴이 여러 번 나타나는지 검사
  const contentFieldMatches = content.match(/"content"\s*:/g);
  if (contentFieldMatches && contentFieldMatches.length > 1) {
    issues.push(`JSON content 필드가 ${contentFieldMatches.length}회 중복 정의됨`);
  }

  return {
    hasRepetition: issues.length > 0,
    details: issues.join(' | ')
  };
}

/**
 * Jaccard 유사도 계산 (단어 집합 기반)
 * @param {string} str1
 * @param {string} str2
 * @returns {number} 0~1 사이의 유사도
 */
function calculateJaccardSimilarity(str1, str2) {
  // 문장을 단어로 분리 (공백 기준)
  const words1 = new Set(str1.split(/\s+/).filter(w => w.length > 1));
  const words2 = new Set(str2.split(/\s+/).filter(w => w.length > 1));

  if (words1.size === 0 || words2.size === 0) return 0;

  // 교집합 크기 계산
  const intersection = new Set([...words1].filter(x => words2.has(x)));

  // 합집합 크기 계산
  const union = new Set([...words1, ...words2]);

  return intersection.size / union.size;
}

/**
 * 키워드 삽입 검증 (사용자 키워드는 엄격, 자동 키워드는 완화)
 * @param {string} content - 검증할 콘텐츠
 * @param {Array<string>} userKeywords - 사용자 입력 키워드 (엄격 검증)
 * @param {Array<string>} autoKeywords - 자동 추출 키워드 (완화 검증)
 * @param {number} targetWordCount - 목표 글자수
 * @returns {Object} 검증 결과
 */
function validateKeywordInsertion(content, userKeywords = [], autoKeywords = [], targetWordCount) {
  const plainText = content.replace(/<[^>]*>/g, '').replace(/\s/g, '');
  const actualWordCount = plainText.length;

  // 사용자 입력 키워드: 400자당 1회 (엄격)
  const userExpectedCount = Math.floor(actualWordCount / 400);
  const userMinCount = Math.max(1, userExpectedCount);

  // 자동 추출 키워드: 최소 1회만 (완화)
  const autoMinCount = 1;

  const results = {};
  let totalOccurrences = 0;
  let allValid = true;

  // 1. 사용자 입력 키워드 검증 (엄격)
  for (const keyword of userKeywords) {
    const count = countKeywordOccurrences(content, keyword);
    totalOccurrences += count;
    const isValid = count >= userMinCount;

    results[keyword] = {
      count,
      expected: userMinCount,
      valid: isValid,
      type: 'user' // 사용자 키워드 표시
    };

    if (!isValid) {
      allValid = false;
    }
  }

  // 2. 자동 추출 키워드 검증 (완화)
  for (const keyword of autoKeywords) {
    const count = countKeywordOccurrences(content, keyword);
    totalOccurrences += count;
    const isValid = count >= autoMinCount;

    results[keyword] = {
      count,
      expected: autoMinCount,
      valid: isValid,
      type: 'auto' // 자동 키워드 표시
    };

    // 자동 키워드는 검증 실패해도 전체 실패로 처리 안 함
    // if (!isValid) {
    //   allValid = false;
    // }
  }

  // 키워드 밀도 계산 (참고용, 검증에는 사용 안 함)
  const allKeywords = [...userKeywords, ...autoKeywords];
  const totalKeywordChars = allKeywords.reduce((sum, kw) => {
    const occurrences = countKeywordOccurrences(content, kw);
    return sum + (kw.replace(/\s/g, '').length * occurrences);
  }, 0);
  const density = actualWordCount > 0 ? (totalKeywordChars / actualWordCount * 100) : 0;

  return {
    valid: allValid, // 사용자 입력 키워드만 검증
    details: {
      keywords: results,
      density: {
        value: density.toFixed(2),
        valid: true, // 밀도 검증 제거
        optimal: density >= 1.5 && density <= 2.5
      },
      wordCount: actualWordCount
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
  userKeywords = [],
  autoKeywords = [],
  maxAttempts = 3
}) {
  let apiResponse;
  let attempt = 0;
  let currentPrompt = prompt;

  // 검증 변수들을 반복문 밖에서 선언
  let hasName = false;
  let hasSufficientLength = false;
  let actualWordCount = 0;
  let keywordValidation = { valid: false, details: {} };
  let repetitionCheck = { hasRepetition: false, details: '' };

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
      actualWordCount = plainText.length;
      const minWordCount = Math.floor(targetWordCount * 0.9); // 목표의 90%

      console.log(`📊 분량 체크 - 실제: ${actualWordCount}자, 목표: ${targetWordCount}자, 최소: ${minWordCount}자`);

      // 기존 검증
      hasName = !fullName || apiResponse.includes(fullName);
      hasSufficientLength = actualWordCount >= minWordCount;

      // 지역 미포함 시 경고만 출력
      if (fullRegion && !apiResponse.includes(fullRegion)) {
        console.log(`⚠️ 지역명 '${fullRegion}' 미포함 (경고만, 검증 통과)`);
      }

      // ✨ 키워드 검증 (사용자 키워드는 엄격, 자동 키워드는 완화)
      keywordValidation = validateKeywordInsertion(
        contentToCheck,
        userKeywords,
        autoKeywords,
        targetWordCount
      );

      // ✨ 반복 검증 (새로 추가)
      const repetitionCheck = detectRepetition(contentToCheck);

      console.log(`🔍 기본 검증 - 이름: ${hasName}, 분량: ${hasSufficientLength}`);
      console.log(`🔑 키워드 검증:`, JSON.stringify(keywordValidation.details, null, 2));
      console.log(`🔄 반복 검증 - 통과: ${!repetitionCheck.hasRepetition}${repetitionCheck.details ? ', 상세: ' + repetitionCheck.details : ''}`);

      // 모든 검증 통과 확인 (반복 검증 추가)
      if (hasName && hasSufficientLength && keywordValidation.valid && !repetitionCheck.hasRepetition) {
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

        // 반복 검증 실패 시 피드백
        if (repetitionCheck.hasRepetition) {
          improvementInstructions += `\n- ⛔ 반복 금지 위반 (치명적, 즉시 수정 필요):\n`;
          improvementInstructions += `  • 감지된 문제: ${repetitionCheck.details}\n`;
          improvementInstructions += `  • 동일하거나 유사한 문장/문단을 절대 반복하지 마세요\n`;
          improvementInstructions += `  • 이미 작성한 내용을 다시 작성하지 마세요\n`;
          improvementInstructions += `  • 각 문장과 문단은 새로운 정보를 제공해야 합니다\n`;
          improvementInstructions += `  • JSON content 필드는 단 하나만 존재해야 합니다\n`;
          needsImprovement = true;
        }

        if (!keywordValidation.valid) {
          const { keywords: kwResults } = keywordValidation.details;

          // 사용자 입력 키워드만 피드백에 포함 (자동 추출 키워드는 제외)
          const failedUserKeywords = Object.entries(kwResults).filter(([kw, result]) =>
            !result.valid && result.type === 'user'
          );

          if (failedUserKeywords.length > 0) {
            improvementInstructions += `- 노출 희망 검색어 삽입 부족 (필수):\n`;

            for (const [kw, result] of failedUserKeywords) {
              improvementInstructions += `  • "${kw}": 현재 ${result.count}회 → 최소 ${result.expected}회 이상 필요\n`;
            }

            improvementInstructions += `  • 본문 전체(도입부, 본론, 결론)에 고르게 분산 배치하세요.\n`;
            improvementInstructions += `  • 문장의 주어, 목적어, 수식어 위치에 자연스럽게 배치하세요.\n`;
            improvementInstructions += `  • 동일한 문장이나 문단을 반복하지 마세요.\n`;
            improvementInstructions += `  • 마무리 인사 후 본문이 다시 시작되지 않도록 주의하세요.\n`;
            needsImprovement = true;
          }
        }

        if (needsImprovement) {
          console.log(`⚠️ 검증 실패 - 재생성 필요:`, improvementInstructions);
          currentPrompt = currentPrompt + improvementInstructions;
        }

        continue;
      }
    }

    // 최대 시도 횟수 초과 시 상세 에러 메시지와 함께 실패 처리
    if (attempt >= maxAttempts) {
      const errors = [];

      if (!hasName && fullName) {
        errors.push(`작성자 이름 '${fullName}' 미포함`);
      }

      if (!hasSufficientLength) {
        errors.push(`분량 부족 (실제: ${actualWordCount}자, 최소: ${Math.floor(targetWordCount * 0.9)}자)`);
      }

      if (!keywordValidation.valid) {
        const { keywords: kwResults } = keywordValidation.details;
        // 사용자 입력 키워드만 에러에 포함
        const missingUserKeywords = Object.entries(kwResults)
          .filter(([_, result]) => !result.valid && result.type === 'user')
          .map(([kw, result]) => `'${kw}' (${result.count}/${result.expected}회)`)
          .join(', ');
        if (missingUserKeywords) {
          errors.push(`검색어 부족: ${missingUserKeywords}`);
        }
      }

      // 반복 검증 실패 추가
      if (repetitionCheck.hasRepetition) {
        errors.push(`반복 감지: ${repetitionCheck.details}`);
      }

      console.error(`❌ ${maxAttempts}번 시도 후에도 품질 기준 미달:`, errors.join(' | '));
      throw new Error(`AI 원고 생성 품질 기준 미달: ${errors.join(', ')}`);
    }
  }

  return apiResponse;
}

module.exports = {
  validateAndRetry
};
