'use strict';

/**
 * Evaluation Service - LLM-as-Judge 기반 콘텐츠 품질 평가
 *
 * Context Engineering 적용:
 * - 생성된 콘텐츠의 품질을 자동 평가
 * - 평가 기준: 당론 적합성, SEO 적합성, 스타일 일치도, 가독성
 * - 점수 기반 best_posts 자동 선별
 */

const { GoogleGenerativeAI } = require('@google/generative-ai');

// Gemini 클라이언트 초기화
let genAI = null;
function getGenAI() {
  if (!genAI) {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      console.warn('⚠️ [Evaluation] GEMINI_API_KEY 없음 - 평가 스킵');
      return null;
    }
    genAI = new GoogleGenerativeAI(apiKey);
  }
  return genAI;
}

// ============================================================================
// 평가 프롬프트
// ============================================================================

const EVALUATION_PROMPT = `당신은 정치인 블로그 콘텐츠 품질 평가 전문가입니다.
다음 콘텐츠를 평가하고 JSON 형식으로 점수를 매겨주세요.

## 평가 기준 (각 1-10점)

1. **relevance** (주제 적합성): 주어진 주제를 잘 다루고 있는가?
2. **readability** (가독성): 문장이 자연스럽고 읽기 쉬운가?
3. **structure** (구조): 서론-본론-결론 구조가 명확한가?
4. **authenticity** (진정성): 정치인의 진솔한 목소리가 느껴지는가?
5. **engagement** (참여 유도): 독자의 공감과 반응을 이끌어낼 수 있는가?

## 콘텐츠 정보
- 카테고리: {category}
- 주제: {topic}
- 작성자: {author}

## 콘텐츠
{content}

## 응답 형식 (JSON만 출력)
{
  "scores": {
    "relevance": 8,
    "readability": 7,
    "structure": 8,
    "authenticity": 6,
    "engagement": 7
  },
  "overallScore": 7.2,
  "strengths": ["강점1", "강점2"],
  "improvements": ["개선점1", "개선점2"],
  "summary": "한 줄 평가"
}`;

// ============================================================================
// 평가 함수
// ============================================================================

/**
 * 콘텐츠 품질 평가
 * @param {Object} params - 평가 파라미터
 * @param {string} params.content - 평가할 콘텐츠
 * @param {string} params.category - 카테고리
 * @param {string} params.topic - 주제
 * @param {string} params.author - 작성자 정보
 * @returns {Promise<Object>} 평가 결과
 */
async function evaluateContent({ content, category, topic, author }) {
  const ai = getGenAI();
  if (!ai) {
    return getDefaultEvaluation();
  }

  if (!content || content.length < 100) {
    console.warn('⚠️ [Evaluation] 콘텐츠가 너무 짧음 - 평가 스킵');
    return getDefaultEvaluation();
  }

  try {
    const model = ai.getGenerativeModel({ model: 'gemini-2.0-flash-exp' });

    // 콘텐츠 길이 제한 (토큰 절약)
    const truncatedContent = content.length > 3000
      ? content.substring(0, 3000) + '...(이하 생략)'
      : content;

    const prompt = EVALUATION_PROMPT
      .replace('{category}', category || '일반')
      .replace('{topic}', topic || '미지정')
      .replace('{author}', author || '작성자')
      .replace('{content}', truncatedContent);

    const result = await model.generateContent({
      contents: [{ role: 'user', parts: [{ text: prompt }] }],
      generationConfig: {
        temperature: 0.3,  // 일관된 평가를 위해 낮은 temperature
        maxOutputTokens: 500
      }
    });

    const response = result.response.text();

    // JSON 파싱
    const evaluation = parseEvaluationResponse(response);

    console.log('✅ [Evaluation] 평가 완료:', {
      overallScore: evaluation.overallScore,
      summary: evaluation.summary
    });

    return evaluation;
  } catch (error) {
    console.error('❌ [Evaluation] 평가 실패:', error.message);
    return getDefaultEvaluation();
  }
}

/**
 * 평가 응답 파싱
 */
function parseEvaluationResponse(response) {
  try {
    // JSON 블록 추출
    const jsonMatch = response.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      throw new Error('JSON not found in response');
    }

    const parsed = JSON.parse(jsonMatch[0]);

    // 필수 필드 검증
    if (!parsed.scores || typeof parsed.overallScore !== 'number') {
      throw new Error('Invalid evaluation format');
    }

    // 점수 범위 정규화 (1-10)
    const normalizeScore = (score) => Math.min(10, Math.max(1, Number(score) || 5));

    return {
      scores: {
        relevance: normalizeScore(parsed.scores.relevance),
        readability: normalizeScore(parsed.scores.readability),
        structure: normalizeScore(parsed.scores.structure),
        authenticity: normalizeScore(parsed.scores.authenticity),
        engagement: normalizeScore(parsed.scores.engagement)
      },
      overallScore: normalizeScore(parsed.overallScore),
      strengths: Array.isArray(parsed.strengths) ? parsed.strengths.slice(0, 3) : [],
      improvements: Array.isArray(parsed.improvements) ? parsed.improvements.slice(0, 3) : [],
      summary: parsed.summary || '평가 완료',
      evaluated: true
    };
  } catch (error) {
    console.warn('⚠️ [Evaluation] 응답 파싱 실패:', error.message);
    return getDefaultEvaluation();
  }
}

/**
 * 기본 평가 (평가 실패 시)
 */
function getDefaultEvaluation() {
  return {
    scores: {
      relevance: 5,
      readability: 5,
      structure: 5,
      authenticity: 5,
      engagement: 5
    },
    overallScore: 5,
    strengths: [],
    improvements: [],
    summary: '자동 평가 미수행',
    evaluated: false
  };
}

/**
 * 베스트 포스트 기준 충족 여부
 * @param {Object} evaluation - 평가 결과
 * @param {number} threshold - 기준 점수 (기본 7.0)
 * @returns {boolean}
 */
function meetsQualityThreshold(evaluation, threshold = 7.0) {
  if (!evaluation || !evaluation.evaluated) return false;
  return evaluation.overallScore >= threshold;
}

/**
 * 빠른 품질 체크 (저품질 필터링용)
 * - 전체 평가보다 빠르게 명백한 저품질 콘텐츠 필터링
 */
function quickQualityCheck(content) {
  if (!content) return { pass: false, reason: 'empty_content' };

  const text = content.replace(/<[^>]*>/g, '');  // HTML 태그 제거

  // 길이 체크
  if (text.length < 200) {
    return { pass: false, reason: 'too_short', length: text.length };
  }

  // 반복 패턴 체크
  const words = text.split(/\s+/);
  const uniqueWords = new Set(words);
  const uniqueRatio = uniqueWords.size / words.length;

  if (uniqueRatio < 0.3) {
    return { pass: false, reason: 'too_repetitive', uniqueRatio };
  }

  // 문장 수 체크
  const sentences = text.split(/[.!?]\s+/).filter(s => s.trim().length > 5);
  if (sentences.length < 3) {
    return { pass: false, reason: 'too_few_sentences', count: sentences.length };
  }

  return { pass: true };
}

// ============================================================================
// 배치 평가 (관리자용)
// ============================================================================

/**
 * 여러 콘텐츠 배치 평가
 * @param {Array} contents - 평가할 콘텐츠 배열
 * @returns {Promise<Array>} 평가 결과 배열
 */
async function batchEvaluate(contents) {
  const results = [];

  for (const item of contents) {
    // 빠른 품질 체크 먼저
    const quickCheck = quickQualityCheck(item.content);
    if (!quickCheck.pass) {
      results.push({
        ...item,
        evaluation: {
          ...getDefaultEvaluation(),
          overallScore: 3,
          summary: `품질 미달: ${quickCheck.reason}`
        }
      });
      continue;
    }

    // 전체 평가
    const evaluation = await evaluateContent(item);
    results.push({ ...item, evaluation });

    // Rate limiting (1초 간격)
    await new Promise(resolve => setTimeout(resolve, 1000));
  }

  return results;
}

module.exports = {
  evaluateContent,
  meetsQualityThreshold,
  quickQualityCheck,
  batchEvaluate,
  getDefaultEvaluation
};
