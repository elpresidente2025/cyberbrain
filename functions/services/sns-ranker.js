/**
 * functions/services/sns-ranker.js
 *
 * Twitter 알고리즘 영감의 2단계 랭킹 파이프라인
 * - Light Ranker: flash-lite로 N개 후보 병렬 생성
 * - Heavy Ranker: flash로 최적 후보 선택 (참여도 예측 스코어링)
 *
 * 참고: Twitter/X의 Light Ranker → Heavy Ranker 아키텍처를 SNS 변환에 적용
 *
 * 비용 참고: flash-lite x3 (병렬) + flash x1 (스코어링) = 4 API 호출/플랫폼
 *           기존 flash x2 (순차 retry) 대비 토큰 소비 증가, 품질 상한선 상승
 */

'use strict';

const { callGenerativeModel } = require('./gemini');

// 랭킹 설정 (불변)
const RANKER_CONFIG = Object.freeze({
  candidateCount: 3,              // Light Ranker 후보 수
  lightModel: 'gemini-2.5-flash-lite', // 빠르고 저렴한 모델
  heavyModel: 'gemini-2.5-flash',      // 정밀 평가 모델
  lightTimeoutMs: 20000,          // Light Ranker 개별 타임아웃
  heavyTimeoutMs: 15000,          // Heavy Ranker 타임아웃
  minCandidates: 2,               // 최소 유효 후보 수 (이하면 fallback)
});

/**
 * Promise에 타임아웃을 적용 (timer leak 방지)
 * @param {Promise} promise - 원본 Promise
 * @param {number} ms - 타임아웃 (ms)
 * @param {string} message - 타임아웃 에러 메시지
 * @returns {Promise}
 */
function withTimeout(promise, ms, message) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(message)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

/**
 * Light Ranker: 빠르게 N개 후보를 병렬 생성
 *
 * Twitter의 Light Ranker처럼 빠른 모델로 다수의 후보를 생성하고,
 * 이후 Heavy Ranker에서 정밀 평가하는 구조.
 *
 * @param {string} prompt - SNS 변환 프롬프트
 * @param {number} candidateCount - 생성할 후보 수 (기본 3)
 * @returns {Promise<string[]>} 유효한 후보 텍스트 배열
 */
async function lightRank(prompt, candidateCount = RANKER_CONFIG.candidateCount) {
  const tasks = Array.from({ length: candidateCount }, () =>
    withTimeout(
      callGenerativeModel(prompt, 1, RANKER_CONFIG.lightModel, true, 25000, { temperature: 0.8 }),
      RANKER_CONFIG.lightTimeoutMs,
      'Light Ranker 타임아웃'
    ).catch((err) => {
      console.warn('Light Ranker 후보 생성 실패:', err.message);
      return null;
    })
  );

  const rawCandidates = await Promise.all(tasks);

  const candidates = rawCandidates.filter(
    (c) => c && typeof c === 'string' && c.trim().length > 0
  );

  console.log(`⚡ Light Ranker: ${candidates.length}/${candidateCount}개 후보 생성 완료`);
  return candidates;
}

/**
 * Heavy Ranker용 스코어링 프롬프트 생성
 *
 * Twitter의 Heavy Ranker가 신경망으로 참여도를 예측하듯,
 * LLM이 각 후보의 SNS 성과를 예측 평가한다.
 *
 * 평가 기준 (Twitter 알고리즘 기반):
 * 1. 임팩트 (Hook Quality) - 스크롤을 멈추게 하는 힘
 * 2. 참여 예측 (Engagement Prediction) - 좋아요/RT/댓글 유도력
 * 3. 정보 밀도 (Information Density) - 글자당 전달 정보량
 * 4. 형식 준수 (Format Compliance) - 플랫폼 규격 적합도
 * 5. 원본 충실도 (Source Fidelity) - 원본 메시지 보존도
 *
 * @param {string[]} candidates - 후보 텍스트 배열
 * @param {string} platform - SNS 플랫폼 ('x', 'threads', 'facebook-instagram')
 * @param {string} originalContent - 원본 블로그 원고 (요약본)
 * @param {Object} context - 추가 컨텍스트
 * @param {Object} context.platformConfig - 플랫폼 설정 (글자수 제한 등)
 * @param {Object} context.userInfo - 사용자 정보 (이름, 직책)
 * @returns {string} 스코어링 프롬프트
 */
function buildScoringPrompt(candidates, platform, originalContent, context = {}) {
  const originalSummary = originalContent.length > 500
    ? originalContent.substring(0, 500) + '...'
    : originalContent;

  const candidateBlocks = candidates
    .map((c, i) => `--- 후보 ${i + 1} ---\n${c}\n--- 끝 ---`)
    .join('\n\n');

  const { platformConfig, userInfo } = context;
  const platformName = platformConfig?.name || platform;
  const authorLabel = userInfo ? `${userInfo.name} ${userInfo.position}` : '작성자';
  const platformLower = String(platform || '').trim().toLowerCase();

  let platformSpecificRules = '';
  if (platformLower === 'facebook-instagram') {
    platformSpecificRules = `
**Facebook/Instagram 공용 게시물 적합도 체크 (필수):**
- 결과가 타래가 아니라 단일 게시물 JSON(content, hashtags, wordCount) 형식인가?
- 첫 2~3줄 안에 핵심 메시지와 맥락이 배치되어 미리보기 구간에서도 의미가 전달되는가?
- Instagram 해시태그 과다 사용이나 Facebook 장문 서론 없이 두 플랫폼 모두에서 자연스러운가?
- 댓글/공감 유도 문장이 짧고 자연스러운가?
- 원문의 고유명사/핵심 수치/핵심 주장 반영이 충분한가?`;
  }

  return `당신은 SNS 콘텐츠 성과 예측 전문가입니다.
아래 원본 블로그 원고를 ${platformName} 플랫폼용으로 변환한 ${candidates.length}개 후보를 평가해주세요.

**작성자:** ${authorLabel}
**원본 원고 (요약):**
${originalSummary}

**후보들:**
${candidateBlocks}

**평가 기준 (가중치 차등, 총 100점):**

1. **임팩트 (Hook Quality)** [25점] - 타임라인에서 스크롤을 멈추게 하는 힘
   - 첫 문장이 관심을 끄는가?
   - 감성적 훅, 질문, 수치, 서사적 대비 등 임팩트 요소가 있는가?
   - 개인 서사나 극적인 숫자 대비가 활용되었는가?

2. **참여 예측 (Engagement Prediction)** [25점] - 좋아요/RT/댓글 유도력
   - 공감을 유도하는 요소가 있는가?
   - CTA(행동 유도)가 자연스러운가?
   - 공유하고 싶은 내용인가?
   - 작성자의 핵심 주제(topic)에 담긴 CTA가 보존되었는가?

3. **정보 밀도 (Information Density)** [20점] - 글자당 전달 정보량
   - 불필요한 수식어 없이 핵심이 전달되는가?
   - 구체적 수치, 고유명사, 사실이 포함되어 있는가?

4. **형식 준수 (Format Compliance)** [15점] - ${platformName} 플랫폼 규격 적합도
   - JSON 형식이 올바른가?
   - 글자수 제한을 준수하는가?${platformConfig?.hashtagLimit ? `\n   - 해시태그 ${platformConfig.hashtagLimit}개 이내인가?` : ''}

5. **원본 충실도 (Source Fidelity)** [15점] - 원본 메시지 보존도
   - 원본의 핵심 메시지가 정확히 전달되는가?
   - 원본에 없는 내용이 추가되지 않았는가?
   - 정치적 입장과 논조가 보존되었는가?

${platformSpecificRules}

**JSON 출력 형식:**
{
  "rankings": [
    {
      "candidateIndex": 0,
      "scores": {
        "hookQuality": 22,
        "engagementPrediction": 20,
        "informationDensity": 18,
        "formatCompliance": 14,
        "sourceFidelity": 13
      },
      "totalScore": 87,
      "strengths": "서사적 대비 활용, 주제 CTA 보존",
      "weaknesses": "글자수 약간 초과"
    }
  ],
  "bestIndex": 0,
  "reason": "후보 1이 임팩트와 정보 밀도에서 우수"
}`;
}

/**
 * Heavy Ranker: 후보 중 최적 SNS 콘텐츠 선택
 *
 * Twitter의 Heavy Ranker가 참여도를 예측하여 최종 노출 순위를 결정하듯,
 * 이 함수는 LLM으로 각 후보의 SNS 성과를 예측하여 최고 품질 콘텐츠를 선택한다.
 *
 * @param {string[]} candidates - 후보 텍스트 배열
 * @param {string} platform - SNS 플랫폼
 * @param {string} originalContent - 원본 블로그 원고
 * @param {Object} context - platformConfig, userInfo 등 추가 컨텍스트
 * @returns {Promise<{ bestIndex: number, bestCandidate: string, rankings: Array, reason: string }>}
 */
async function heavyRank(candidates, platform, originalContent, context = {}) {
  if (candidates.length === 0) {
    return { bestIndex: -1, bestCandidate: null, rankings: [], reason: '후보 없음' };
  }

  if (candidates.length === 1) {
    return {
      bestIndex: 0,
      bestCandidate: candidates[0],
      rankings: [{ candidateIndex: 0, totalScore: 0 }],
      reason: '단일 후보 (스코어링 스킵)',
    };
  }

  try {
    const scoringPrompt = buildScoringPrompt(candidates, platform, originalContent, context);

    const rawResult = await withTimeout(
      callGenerativeModel(scoringPrompt, 1, RANKER_CONFIG.heavyModel, true, 4096),
      RANKER_CONFIG.heavyTimeoutMs,
      'Heavy Ranker 타임아웃'
    );

    const parsed = parseHeavyRankResult(rawResult, candidates.length);

    console.log(`🏆 Heavy Ranker 결과: 후보 ${parsed.bestIndex + 1} 선택 (${parsed.reason})`);
    if (parsed.rankings.length > 0) {
      parsed.rankings.forEach((r) => {
        console.log(`   후보 ${r.candidateIndex + 1}: ${r.totalScore}점`);
      });
    }

    return {
      ...parsed,
      bestCandidate: candidates[parsed.bestIndex],
    };
  } catch (err) {
    console.warn('🏆 Heavy Ranker 실패, 첫 번째 후보 선택:', err.message);
    return {
      bestIndex: 0,
      bestCandidate: candidates[0],
      rankings: [],
      reason: `Heavy Ranker 실패 (${err.message}), 첫 번째 후보 fallback`,
    };
  }
}

/**
 * Heavy Ranker 결과 파싱
 * @param {string} rawResult - Gemini 응답 텍스트
 * @param {number} candidateCount - 후보 수 (유효성 검증용)
 * @returns {{ bestIndex: number, rankings: Array, reason: string }}
 */
function parseHeavyRankResult(rawResult, candidateCount) {
  try {
    // 균형 잡힌 JSON 추출 (greedy regex 대신 depth 기반 파싱)
    const jsonStr = extractFirstBalancedJson(rawResult);
    if (!jsonStr) {
      throw new Error('JSON 형식 없음');
    }

    const parsed = JSON.parse(jsonStr);
    let bestIndex = parsed.bestIndex;

    // bestIndex 교차 검증: rankings의 최고 점수 후보와 일치하는지 확인
    const rankings = Array.isArray(parsed.rankings) ? parsed.rankings : [];
    if (rankings.length > 0) {
      const highestScored = rankings.reduce((a, b) =>
        (a.totalScore || 0) >= (b.totalScore || 0) ? a : b
      );
      if (typeof highestScored.candidateIndex === 'number' && highestScored.candidateIndex !== bestIndex) {
        console.warn(`bestIndex(${bestIndex})와 최고점수 후보(${highestScored.candidateIndex}) 불일치, 최고점수 기준 보정`);
        bestIndex = highestScored.candidateIndex;
      }
    }

    if (typeof bestIndex !== 'number' || bestIndex < 0 || bestIndex >= candidateCount) {
      throw new Error(`유효하지 않은 bestIndex: ${bestIndex}`);
    }

    return {
      bestIndex,
      rankings,
      reason: parsed.reason || '이유 미제공',
    };
  } catch (err) {
    console.warn('Heavy Ranker 파싱 실패:', err.message);
    return {
      bestIndex: 0,
      rankings: [],
      reason: `파싱 실패 (${err.message}), 첫 번째 후보 fallback`,
    };
  }
}

/**
 * 첫 번째 균형 잡힌 JSON 객체를 추출 (greedy regex 문제 방지)
 * @param {string} text - 원본 텍스트
 * @returns {string|null} JSON 문자열 또는 null
 */
function extractFirstBalancedJson(text) {
  const start = text.indexOf('{');
  if (start === -1) return null;
  let depth = 0;
  let inString = false;
  let escape = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (escape) { escape = false; continue; }
    if (ch === '\\') { escape = true; continue; }
    if (ch === '"') { inString = !inString; continue; }
    if (inString) continue;
    if (ch === '{') depth++;
    else if (ch === '}') depth--;
    if (depth === 0) return text.substring(start, i + 1);
  }
  return null;
}

/**
 * 2단계 랭킹 파이프라인 실행 (메인 함수)
 *
 * Twitter 알고리즘의 Light → Heavy 파이프라인을 SNS 변환에 적용:
 * 1. Light Ranker: flash-lite로 3개 후보 병렬 생성
 * 2. Heavy Ranker: flash로 최고 품질 후보 선택
 *
 * @param {string} prompt - SNS 변환 프롬프트
 * @param {string} platform - SNS 플랫폼
 * @param {string} originalContent - 원본 블로그 원고
 * @param {Object} options - 추가 옵션
 * @param {number} options.candidateCount - 후보 수 (기본 3)
 * @param {Object} options.platformConfig - 플랫폼 설정 (Heavy Ranker 평가에 사용)
 * @param {Object} options.userInfo - 사용자 정보 (Heavy Ranker 평가에 사용)
 * @returns {Promise<{ text: string, ranking: Object }>}
 */
async function rankAndSelect(prompt, platform, originalContent, options = {}) {
  const candidateCount = options.candidateCount || RANKER_CONFIG.candidateCount;

  console.log(`🚀 [SNS Ranker] ${platform} 2단계 랭킹 시작 (후보 ${candidateCount}개)`);
  const startTime = Date.now();

  // Phase 1: Light Rank
  const candidates = await lightRank(prompt, candidateCount);

  if (candidates.length === 0) {
    console.warn('Light Ranker 전체 실패, 기본 모델로 단일 생성 fallback');
    try {
      const fallbackText = await withTimeout(
        callGenerativeModel(prompt, 1, RANKER_CONFIG.heavyModel),
        25000,
        'Fallback 단일 생성 타임아웃 (25초)'
      );
      return {
        text: fallbackText,
        ranking: { bestIndex: 0, rankings: [], reason: 'Light Ranker 전체 실패, 단일 생성 fallback' },
      };
    } catch (err) {
      console.error('Fallback 생성도 실패:', err.message);
      return {
        text: null,
        ranking: { bestIndex: -1, rankings: [], reason: 'Light + Fallback 모두 실패' },
      };
    }
  }

  if (candidates.length < RANKER_CONFIG.minCandidates) {
    console.log(`⚡ 유효 후보 ${candidates.length}개 < ${RANKER_CONFIG.minCandidates}개, Heavy Ranker 스킵`);
    return {
      text: candidates[0],
      ranking: { bestIndex: 0, rankings: [], reason: '후보 부족, Heavy Ranker 스킵' },
    };
  }

  // Phase 2: Heavy Rank (platformConfig, userInfo를 context로 전달)
  const context = {
    platformConfig: options.platformConfig,
    userInfo: options.userInfo,
  };
  const ranking = await heavyRank(candidates, platform, originalContent, context);

  const elapsed = Date.now() - startTime;
  console.log(`🚀 [SNS Ranker] ${platform} 완료: ${elapsed}ms, 후보 ${candidates.length}개 중 #${ranking.bestIndex + 1} 선택`);

  return {
    text: ranking.bestCandidate,
    ranking,
  };
}

module.exports = {
  rankAndSelect,
  lightRank,
  heavyRank,
  buildScoringPrompt,
  withTimeout,
  extractFirstBalancedJson,
  RANKER_CONFIG,
};
