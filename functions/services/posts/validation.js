'use strict';

const { callGenerativeModel } = require('../gemini');
const { getElectionStage, VIOLATION_DETECTOR } = require('../../prompts/guidelines/legal');
const { runCriticReview, hasHardViolations, summarizeGuidelines } = require('./critic');
const { applyCorrections, summarizeViolations } = require('./corrector');
const { GENERATION_STAGES, createProgressState, createRetryMessage } = require('./generation-stages');

// ============================================================================
// 선거법 검증 v3 - 화이트리스트 + LLM 하이브리드
// ============================================================================

/**
 * 허용되는 문장 종결 패턴 (준비/현역 단계)
 * 이 패턴으로 끝나는 문장은 공약이 아닌 것으로 간주
 */
const ALLOWED_ENDINGS = [
  // 현황 설명 (서술)
  /입니다\.?$/,
  /습니다\.?$/,          // ~하고 있습니다, ~되고 있습니다
  /됩니다\.?$/,          // ~가 됩니다 (수동)

  // 과거형
  /했습니다\.?$/,
  /되었습니다\.?$/,
  /였습니다\.?$/,
  /었습니다\.?$/,

  // 당위/필요성 (본인 약속 아님)
  /해야\s*합니다\.?$/,
  /되어야\s*합니다\.?$/,
  /필요합니다\.?$/,
  /바랍니다\.?$/,

  // 의견/관점
  /생각합니다\.?$/,
  /봅니다\.?$/,
  /압니다\.?$/,
  /느낍니다\.?$/,

  // 질문
  /[까요까]\?$/,
  /[습읍]니까\?$/,

  // 인용/전달
  /라고\s*합니다\.?$/,
  /답니다\.?$/,
];

/**
 * 명시적 금지 패턴 (빠른 차단)
 * 이 패턴은 LLM 확인 없이 즉시 위반 처리
 */
const EXPLICIT_PLEDGE_PATTERNS = [
  /약속드립니다/,
  /약속합니다/,
  /공약합니다/,
  /반드시.*하겠습니다/,
  /꼭.*하겠습니다/,
  /제가.*하겠습니다/,
  /저는.*하겠습니다/,
  /당선되면/,
  /당선\s*후/,
];

/**
 * 문장 추출 (마침표, 물음표, 느낌표 기준)
 */
function extractSentences(text) {
  const plainText = text.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  return plainText
    .split(/(?<=[.?!])\s+/)
    .map(s => s.trim())
    .filter(s => s.length > 10);
}

/**
 * 화이트리스트 검사 - 허용 패턴이면 true
 */
function isAllowedEnding(sentence) {
  return ALLOWED_ENDINGS.some(pattern => pattern.test(sentence));
}

/**
 * 명시적 금지 패턴 검사 - 금지면 true
 */
function isExplicitPledge(sentence) {
  return EXPLICIT_PLEDGE_PATTERNS.some(pattern => pattern.test(sentence));
}

/**
 * ~겠 포함 여부 (LLM 검증 대상)
 */
function containsPledgeCandidate(sentence) {
  // "겠습니다", "겠어요" 등 미래 의지 표현
  return /겠[습어]/.test(sentence);
}

/**
 * LLM 시맨틱 검증 - 공약 여부 판단
 * @param {string[]} sentences - 검증할 문장 배열
 * @returns {Promise<Object[]>} - { sentence, isPledge, reason }[]
 */
async function checkPledgesWithLLM(sentences) {
  if (sentences.length === 0) return [];

  const prompt = `당신은 대한민국 선거법 전문가입니다.
아래 문장들이 "정치인 본인의 선거 공약/약속"인지 판단하세요.

[판단 기준]
- 공약 O: 정치인 본인이 주어로, 미래에 ~하겠다는 약속
  예: "일자리를 만들겠습니다", "교통 문제를 해결하겠습니다"

- 공약 X: 다음은 공약이 아님
  예: "비가 오겠습니다" (날씨 예측)
  예: "좋은 결과가 있겠습니다" (희망/기대)
  예: "정부가 해야겠습니다" (제3자 당위)
  예: "함께 만들어가겠습니다" (시민 참여 호소, 맥락에 따라)

[검증 대상 문장]
${sentences.map((s, i) => `${i + 1}. "${s}"`).join('\n')}

[출력 형식 - JSON]
{
  "results": [
    { "index": 1, "isPledge": true/false, "reason": "판단 근거" },
    ...
  ]
}`;

  try {
    const response = await callGenerativeModel(prompt, 1, 'gemini-2.0-flash-exp', true);
    const parsed = JSON.parse(response);

    return parsed.results.map((r, i) => ({
      sentence: sentences[r.index - 1] || sentences[i],
      isPledge: r.isPledge,
      reason: r.reason
    }));
  } catch (error) {
    console.warn('⚠️ LLM 공약 검증 실패, 보수적 처리:', error.message);
    // LLM 실패 시 보수적으로 모두 공약으로 처리
    return sentences.map(s => ({
      sentence: s,
      isPledge: true,
      reason: 'LLM 검증 실패 - 보수적 처리'
    }));
  }
}

/**
 * 하이브리드 선거법 검증 (v3)
 * 1차: 화이트리스트로 빠른 통과
 * 2차: 명시적 금지 패턴 즉시 차단
 * 3차: ~겠 포함 문장 LLM 검증
 */
async function detectElectionLawViolationHybrid(content, status, title = '') {
  // 상태가 없거나 예비후보/후보 단계면 검사 스킵
  if (!status) {
    return { passed: true, violations: [], skipped: true };
  }

  const electionStage = getElectionStage(status);
  if (!electionStage || electionStage.name !== 'STAGE_1') {
    return { passed: true, violations: [], skipped: true };
  }

  const fullText = (title + ' ' + content);
  const sentences = extractSentences(fullText);

  const violations = [];
  const llmCandidates = [];

  // 1차: 문장별 분류
  for (const sentence of sentences) {
    // 명시적 금지 패턴 → 즉시 위반
    if (isExplicitPledge(sentence)) {
      violations.push({
        sentence: sentence.substring(0, 60) + (sentence.length > 60 ? '...' : ''),
        type: 'EXPLICIT_PLEDGE',
        reason: '명시적 공약 표현'
      });
      continue;
    }

    // 화이트리스트 통과 → OK
    if (isAllowedEnding(sentence)) {
      continue;
    }

    // ~겠 포함 → LLM 검증 대상
    if (containsPledgeCandidate(sentence)) {
      llmCandidates.push(sentence);
    }
  }

  // 2차: LLM 시맨틱 검증 (후보가 있을 때만)
  if (llmCandidates.length > 0) {
    console.log(`🔍 LLM 공약 검증: ${llmCandidates.length}개 문장`);
    const llmResults = await checkPledgesWithLLM(llmCandidates);

    for (const result of llmResults) {
      if (result.isPledge) {
        violations.push({
          sentence: result.sentence.substring(0, 60) + (result.sentence.length > 60 ? '...' : ''),
          type: 'LLM_DETECTED',
          reason: result.reason
        });
      }
    }
  }

  // 3차: 기존 VIOLATION_DETECTOR 검사 (기부행위, 허위사실)
  const plainText = fullText.replace(/<[^>]*>/g, ' ');

  const briberyViolations = VIOLATION_DETECTOR.checkBriberyRisk(plainText);
  briberyViolations.forEach(v => {
    violations.push({
      sentence: v.match || '',
      type: 'BRIBERY',
      reason: v.reason
    });
  });

  const factViolations = VIOLATION_DETECTOR.checkFactClaims(plainText);
  factViolations.forEach(v => {
    violations.push({
      sentence: v.match || '',
      type: v.severity === 'CRITICAL' ? 'FACT_CRITICAL' : 'FACT_WARNING',
      reason: v.reason
    });
  });

  return {
    passed: violations.length === 0,
    violations,
    status,
    stage: electionStage.name,
    stats: {
      totalSentences: sentences.length,
      llmChecked: llmCandidates.length,
      violationCount: violations.length
    }
  };
}

// ============================================================================
// 휴리스틱 품질 검증 (v2 - LLM 없이 빠른 검증) - 레거시 유지
// ============================================================================

/**
 * 문장 반복 검출
 * 동일한 문장이 2회 이상 등장하면 실패
 *
 * @param {string} content - 검증할 HTML 콘텐츠
 * @returns {Object} { passed: boolean, repeatedSentences: string[] }
 */
function detectSentenceRepetition(content) {
  // HTML 태그 제거
  const plainText = content.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();

  // 문장 분리 (마침표, 물음표, 느낌표 기준)
  const sentences = plainText
    .split(/(?<=[.?!])\s+/)
    .map(s => s.trim())
    .filter(s => s.length > 20); // 20자 이상 문장만 검사 (짧은 문장 제외)

  // 정규화: 공백 제거, 소문자화 (유사 문장 검출용)
  const normalizedSentences = sentences.map(s =>
    s.replace(/\s+/g, '').toLowerCase()
  );

  // 중복 검출
  const sentenceCount = {};
  const repeatedSentences = [];

  normalizedSentences.forEach((normalized, index) => {
    if (!sentenceCount[normalized]) {
      sentenceCount[normalized] = { count: 0, original: sentences[index] };
    }
    sentenceCount[normalized].count++;
  });

  Object.values(sentenceCount).forEach(({ count, original }) => {
    if (count >= 2) {
      repeatedSentences.push(`"${original.substring(0, 50)}..." (${count}회 반복)`);
    }
  });

  return {
    passed: repeatedSentences.length === 0,
    repeatedSentences
  };
}

/**
 * 선거법 위반 검출 (공약성 표현)
 * 사용자 상태가 '준비' 또는 '현역'일 때 ~하겠습니다 표현 검출
 *
 * @param {string} content - 검증할 HTML 콘텐츠
 * @param {string} status - 사용자 상태 (준비/현역/예비/후보)
 * @returns {Object} { passed: boolean, violations: string[] }
 */
function detectElectionLawViolation(content, status, title = '') {
  // 상태가 없거나 예비/후보 단계면 검사 스킵
  if (!status) {
    return { passed: true, violations: [], skipped: true };
  }

  const electionStage = getElectionStage(status);
  if (!electionStage || electionStage.name !== 'STAGE_1') {
    // 예비후보/후보 단계는 공약 표현 허용
    return { passed: true, violations: [], skipped: true };
  }

  // HTML 태그 제거 + 제목도 포함하여 검사
  const plainText = (title + ' ' + content).replace(/<[^>]*>/g, ' ');

  // 공약성 표현 패턴 (준비/현역 단계에서 금지)
  // "~겠습니다" 형태 + "~ㅂ니다" 형태 모두 포함
  const pledgePatterns = [
    // ~겠습니다 형태
    /추진하겠습니다/g,
    /실현하겠습니다/g,
    /만들겠습니다/g,
    /해내겠습니다/g,
    /전개하겠습니다/g,
    /제공하겠습니다/g,
    /활성화하겠습니다/g,
    /개선하겠습니다/g,
    /확대하겠습니다/g,
    /강화하겠습니다/g,
    /설립하겠습니다/g,
    /구축하겠습니다/g,
    /마련하겠습니다/g,
    /지원하겠습니다/g,
    /해결하겠습니다/g,
    /바꾸겠습니다/g,
    /펼치겠습니다/g,
    /이루겠습니다/g,
    /열겠습니다/g,
    /세우겠습니다/g,
    /이뤄내겠습니다/g,
    /해드리겠습니다/g,
    /드리겠습니다/g,
    /약속드리겠습니다/g,
    // ~ㅂ니다 형태 (공약 단정 표현)
    /바꿉니다/g,
    /만듭니다/g,
    /이룹니다/g,
    /해결합니다/g,
    /약속합니다/g,
    /실현합니다/g,
    /책임집니다/g,
  ];

  const violations = [];

  // 1. 공약성 표현 검사
  pledgePatterns.forEach(pattern => {
    const matches = plainText.match(pattern);
    if (matches) {
      violations.push(`"${matches[0]}" (${matches.length}회) - 공약성 표현`);
    }
  });

  // 2. 기부행위 금지 검사 (제85조 6항) - VIOLATION_DETECTOR 활용
  const briberyViolations = VIOLATION_DETECTOR.checkBriberyRisk(plainText);
  briberyViolations.forEach(v => {
    violations.push(`🔴 ${v.reason}`);
  });

  // 3. 허위사실/비방 위험 검사 (제250조, 제251조)
  const factViolations = VIOLATION_DETECTOR.checkFactClaims(plainText);
  factViolations.forEach(v => {
    if (v.severity === 'CRITICAL') {
      violations.push(`🔴 ${v.reason}`);
    } else {
      violations.push(`⚠️ ${v.reason}`);
    }
  });

  return {
    passed: violations.length === 0,
    violations,
    status,
    stage: electionStage.name,
    hasCritical: briberyViolations.length > 0 || factViolations.some(v => v.severity === 'CRITICAL')
  };
}

// ============================================================================
// 제목 품질 검증 (title-generation.js 기준)
// ============================================================================

function normalizeNumericToken(token) {
  return token.replace(/[\s,]/g, '').replace(/퍼센트/g, '%');
}

function extractNumericTokens(text) {
  if (!text) return [];
  const plainText = text.replace(/<[^>]*>/g, ' ');
  const regex = /\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:%|퍼센트|[가-힣]+)?/g;
  const matches = plainText.match(regex) || [];
  return [...new Set(matches.map(normalizeNumericToken).filter(Boolean))];
}

/**
 * 제목 품질 검증
 * @param {string} title - 검증할 제목
 * @param {Array} userKeywords - 사용자 입력 키워드 (SEO용)
 * @returns {Object} { passed, issues, details }
 */
function validateTitleQuality(title, userKeywords = [], content = '') {
  if (!title) {
    return { passed: true, issues: [], details: {} };
  }

  const issues = [];
  const details = {
    length: title.length,
    maxLength: 25,
    keywordPosition: null,
    abstractExpressions: [],
    hasNumbers: false
  };

  // 1. 길이 검증 (25자 초과 = 네이버에서 잘림)
  if (title.length > 25) {
    issues.push({
      type: 'title_length',
      severity: 'critical',
      description: `제목 ${title.length}자 → 25자 초과 (네이버에서 잘림)`,
      instruction: '25자 이내로 줄이세요. 불필요한 조사, 부제목(:, -) 제거.'
    });
  }

  // 2. 키워드 위치 검증 (핵심 키워드가 앞쪽 8자 내에 없으면)
  if (userKeywords && userKeywords.length > 0) {
    const primaryKw = userKeywords[0];
    const kwIndex = title.indexOf(primaryKw);
    details.keywordPosition = kwIndex;

    if (kwIndex === -1) {
      issues.push({
        type: 'keyword_missing',
        severity: 'high',
        description: `핵심 키워드 "${primaryKw}" 제목에 없음`,
        instruction: `"${primaryKw}"를 제목 앞부분에 포함하세요.`
      });
    } else if (kwIndex > 10) {
      issues.push({
        type: 'keyword_position',
        severity: 'medium',
        description: `키워드 "${primaryKw}" 위치 ${kwIndex}자 → 너무 뒤쪽`,
        instruction: '핵심 키워드는 제목 앞쪽 8자 이내에 배치하세요 (앞쪽 1/3 법칙).'
      });
    }
  }

  // 3. 제목 수치/단위가 본문과 불일치하는지 검증
  if (content) {
    const titleNumericTokens = extractNumericTokens(title);
    const contentNumericTokens = extractNumericTokens(content);

    if (titleNumericTokens.length > 0) {
      if (contentNumericTokens.length === 0) {
        issues.push({
          type: 'title_number_mismatch',
          severity: 'high',
          description: '제목에 수치가 있으나 본문에 근거 수치 없음',
          instruction: '본문에 실제로 있는 수치/단위를 제목에 사용하세요.'
        });
      } else {
        const missingTokens = titleNumericTokens.filter(token => !contentNumericTokens.includes(token));
        if (missingTokens.length > 0) {
          issues.push({
            type: 'title_number_mismatch',
            severity: 'high',
            description: `제목 수치/단위가 본문과 불일치: ${missingTokens.join(', ')}`,
            instruction: '본문에 실제로 등장하는 수치/단위를 제목에 그대로 사용하세요.'
          });
        }
      }
    }
  }

  // 4. 추상적 표현 감지 (구체성 없는 뻔한 표현들)
  const abstractPatterns = [
    // 기존 추상어
    { pattern: /비전/, word: '비전' },
    { pattern: /혁신/, word: '혁신' },
    { pattern: /발전/, word: '발전' },
    { pattern: /노력/, word: '노력' },
    { pattern: /최선/, word: '최선' },
    { pattern: /약속/, word: '약속' },
    { pattern: /다짐/, word: '다짐' },
    { pattern: /함께/, word: '함께' },
    // 추가: 정책 상투어
    { pattern: /확충/, word: '확충' },
    { pattern: /개선/, word: '개선' },
    { pattern: /추진/, word: '추진' },
    { pattern: /시급/, word: '시급' },
    { pattern: /강화/, word: '강화' },
    { pattern: /증진/, word: '증진' },
    { pattern: /도모/, word: '도모' },
    { pattern: /향상/, word: '향상' },
    { pattern: /활성화/, word: '활성화' },
    { pattern: /선도/, word: '선도' },
    { pattern: /선진/, word: '선진' },
    { pattern: /미래/, word: '미래' }
  ];

  const foundAbstract = abstractPatterns.filter(p => p.pattern.test(title));
  if (foundAbstract.length > 0) {
    details.abstractExpressions = foundAbstract.map(p => p.word);
    issues.push({
      type: 'abstract_expression',
      severity: 'medium',
      description: `추상적 표현 사용: ${details.abstractExpressions.join(', ')}`,
      instruction: '구체적 수치나 사실로 대체하세요. 예: "발전" → "40% 증가", "비전" → "3대 핵심 정책"'
    });
  }

  // 5. 숫자/구체성 체크 (권장 사항)
  details.hasNumbers = /\d/.test(title);
  if (!details.hasNumbers && issues.length > 0) {
    // 다른 문제가 있을 때만 숫자 부재 언급 (너무 많은 피드백 방지)
    issues.push({
      type: 'no_numbers',
      severity: 'low',
      description: '숫자/구체적 데이터 없음',
      instruction: '가능하면 숫자를 포함하세요. 예: "3대 정책", "120억 확보", "40% 개선"'
    });
  }

  return {
    passed: issues.filter(i => i.severity === 'critical' || i.severity === 'high').length === 0,
    issues,
    details
  };
}

/**
 * 통합 휴리스틱 검증 (동기 버전 - 빠른 검증)
 * 화이트리스트 + 명시적 금지 패턴만 검사 (LLM 없음)
 */
function runHeuristicValidationSync(content, status, title = '') {
  const issues = [];

  // 1. 문장 반복 검출
  const repetitionResult = detectSentenceRepetition(content);
  if (!repetitionResult.passed) {
    issues.push(`⚠️ 문장 반복 감지: ${repetitionResult.repeatedSentences.join(', ')}`);
  }

  // 2. 선거법 위반 검출 (레거시 블랙리스트)
  const electionResult = detectElectionLawViolation(content, status, title);
  if (!electionResult.passed) {
    issues.push(`⚠️ 선거법 위반 표현: ${electionResult.violations.join(', ')}`);
  }

  return {
    passed: issues.length === 0,
    issues,
    details: {
      repetition: repetitionResult,
      electionLaw: electionResult
    }
  };
}

/**
 * 통합 휴리스틱 검증 (비동기 버전 - 하이브리드)
 * 화이트리스트 + 명시적 금지 + LLM 시맨틱 검증 + 제목 품질 검증
 *
 * @param {string} content - 검증할 콘텐츠
 * @param {string} status - 사용자 상태
 * @param {string} title - 제목 (선거법 검증 + 품질 검증)
 * @param {Object} options - { useLLM: boolean, userKeywords: Array }
 * @returns {Promise<Object>} { passed: boolean, issues: string[], details: Object }
 */
async function runHeuristicValidation(content, status, title = '', options = {}) {
  const { useLLM = true, userKeywords = [] } = options;
  const issues = [];

  // 1. 문장 반복 검출 (동기)
  const repetitionResult = detectSentenceRepetition(content);
  if (!repetitionResult.passed) {
    issues.push(`⚠️ 문장 반복 감지: ${repetitionResult.repeatedSentences.join(', ')}`);
  }

  // 2. 선거법 위반 검출
  let electionResult;
  if (useLLM) {
    // 하이브리드: 화이트리스트 + LLM
    electionResult = await detectElectionLawViolationHybrid(content, status, title);
    if (!electionResult.passed) {
      const violationSummary = electionResult.violations
        .map(v => `"${v.sentence}" (${v.reason})`)
        .join(', ');
      issues.push(`⚠️ 선거법 위반: ${violationSummary}`);
    }
  } else {
    // 빠른 검증: 블랙리스트만
    electionResult = detectElectionLawViolation(content, status, title);
    if (!electionResult.passed) {
      issues.push(`⚠️ 선거법 위반 표현: ${electionResult.violations.join(', ')}`);
    }
  }

  // 3. 제목 품질 검증 (title-generation.js 기준)
  const titleResult = validateTitleQuality(title, userKeywords, content);
  if (!titleResult.passed) {
    const titleIssues = titleResult.issues
      .filter(i => i.severity === 'critical' || i.severity === 'high')
      .map(i => i.description);
    if (titleIssues.length > 0) {
      issues.push(`⚠️ 제목 품질 문제: ${titleIssues.join(', ')}`);
    }
  }

  return {
    passed: issues.length === 0,
    issues,
    details: {
      repetition: repetitionResult,
      electionLaw: electionResult,
      titleQuality: titleResult  // 🔑 EditorAgent가 참조할 수 있도록 추가
    }
  };
}

// ============================================================================
// 키워드 검증 함수
// ============================================================================

/**
 * 키워드 출현 횟수 카운팅 (띄어쓰기 정확히 일치)
 */
function countKeywordOccurrences(content, keyword) {
  const cleanContent = content.replace(/<[^>]*>/g, '');
  // 특수문자 이스케이프 처리
  const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(escapedKeyword, 'g');
  const matches = cleanContent.match(regex);
  return matches ? matches.length : 0;
}

/**
 * 키워드 삽입 검증 (사용자 키워드는 엄격, 자동 키워드는 완화)
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
      type: 'user'
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
      type: 'auto'
    };
  }

  // 키워드 밀도 계산 (참고용)
  const allKeywords = [...userKeywords, ...autoKeywords];
  const totalKeywordChars = allKeywords.reduce((sum, kw) => {
    const occurrences = countKeywordOccurrences(content, kw);
    return sum + (kw.replace(/\s/g, '').length * occurrences);
  }, 0);
  const density = actualWordCount > 0 ? (totalKeywordChars / actualWordCount * 100) : 0;

  return {
    valid: allValid,
    details: {
      keywords: results,
      density: {
        value: density.toFixed(2),
        valid: true,
        optimal: density >= 1.5 && density <= 2.5
      },
      wordCount: actualWordCount
    }
  };
}

// ============================================================================
// Critic Agent 통합 검증 (v3)
// ============================================================================

/**
 * AI 응답 생성 + 휴리스틱 검증 + Critic Agent + Corrector
 *
 * 흐름:
 * 1. 초안 생성
 * 2. 휴리스틱 사전 검증 (빠른 필터)
 * 3. 실패 시 재생성 (최대 3회)
 * 4. 휴리스틱 통과 후 Critic Agent 검토
 * 5. HARD 위반 시 Corrector로 수정
 * 6. 최대 2회 Critic-Corrector 루프
 * 7. 최고 점수 버전 반환
 *
 * @param {Object} options
 * @param {string} options.prompt - AI 프롬프트
 * @param {string} options.modelName - 모델명
 * @param {string} options.status - 사용자 상태 (선거법 검증용)
 * @param {string} options.ragContext - RAG 컨텍스트 (Critic용)
 * @param {string} options.authorName - 작성자 이름
 * @param {string} options.topic - 원고 주제
 * @param {Function} options.onProgress - 진행 상황 콜백
 * @param {number} options.maxAttempts - 초안 생성 최대 시도 횟수 (기본: 3)
 * @param {number} options.maxCriticAttempts - Critic 루프 최대 횟수 (기본: 2)
 */
async function validateAndRetry({
  prompt,
  modelName,
  fullName,
  fullRegion,
  targetWordCount,
  userKeywords = [],
  autoKeywords = [],
  status = null,
  ragContext = null,
  authorName = null,
  topic = null,
  onProgress = null,
  maxAttempts = 3,
  maxCriticAttempts = 2
}) {
  // 진행 상황 알림 헬퍼
  const notifyProgress = (stageId, additionalInfo = {}) => {
    if (onProgress && typeof onProgress === 'function') {
      try {
        onProgress(createProgressState(stageId, additionalInfo));
      } catch (e) {
        console.warn('Progress 콜백 오류:', e.message);
      }
    }
  };

  // 최고 점수 버전 추적
  let bestVersion = null;
  let bestScore = 0;

  // ========================================
  // Phase 1: 초안 생성 + 휴리스틱 검증
  // ========================================
  notifyProgress('DRAFTING');

  let draft = null;
  let heuristicPassed = false;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    console.log(`🔥 AI 호출 (${attempt}/${maxAttempts})...`);

    // AI에게 글 쓰기 요청
    const apiResponse = await callGenerativeModel(prompt, 1, modelName);

    if (!apiResponse || apiResponse.length < 100) {
      console.warn(`⚠️ 응답이 너무 짧음 (${attempt}회차)`);
      continue;
    }

    draft = apiResponse;

    // 휴리스틱 검증 (Phase 1에서는 빠른 검증 - LLM 없이)
    notifyProgress('BASIC_CHECK');
    const heuristicResult = await runHeuristicValidation(draft, status, '', { useLLM: false });

    if (heuristicResult.passed) {
      console.log(`✅ 휴리스틱 검증 통과 (${attempt}회차, ${draft.length}자)`);
      heuristicPassed = true;
      break;
    }

    // 검증 실패
    console.warn(`⚠️ 휴리스틱 검증 실패 (${attempt}회차):`, heuristicResult.issues);

    // 점수 추정 (휴리스틱 실패는 70점 기준)
    const estimatedScore = 70 - (heuristicResult.issues.length * 15);
    if (estimatedScore > bestScore) {
      bestScore = estimatedScore;
      bestVersion = draft;
    }

    if (attempt < maxAttempts) {
      console.log(`🔄 재생성 시도...`);
      notifyProgress('DRAFTING', { attempt: attempt + 1 });
    }
  }

  // 휴리스틱조차 통과 못하면 최선 버전 반환
  if (!heuristicPassed) {
    console.error(`❌ ${maxAttempts}회 시도 후에도 휴리스틱 검증 실패`);

    if (bestVersion && bestVersion.length >= 100) {
      console.warn(`⚠️ 최선 버전 반환 (점수: ${bestScore})`);
      notifyProgress('COMPLETED', { warning: '품질 검증 일부 실패' });
      return bestVersion;
    }

    throw new Error('AI 원고 생성 실패: 모든 시도에서 품질 기준 미달');
  }

  // ========================================
  // Phase 2: Critic Agent 검토 + Corrector 루프
  // ========================================

  // 핵심 지침 요약 (프롬프트 하단용)
  const guidelines = summarizeGuidelines(status, topic);

  let currentDraft = draft;
  let criticAttempt = 0;

  while (criticAttempt < maxCriticAttempts) {
    criticAttempt++;

    // Critic 검토
    const retryMsg = createRetryMessage(criticAttempt, maxCriticAttempts, bestScore);
    notifyProgress('EDITOR_REVIEW', {
      attempt: criticAttempt,
      message: retryMsg.message,
      detail: retryMsg.detail
    });

    console.log(`👔 Critic Agent 검토 (${criticAttempt}/${maxCriticAttempts})...`);

    const criticReport = await runCriticReview({
      draft: currentDraft,
      ragContext,
      guidelines,
      status,
      topic,
      authorName,
      modelName: 'gemini-2.0-flash-exp'
    });

    // 점수 추적
    if (criticReport.score > bestScore) {
      bestScore = criticReport.score;
      bestVersion = currentDraft;
    }

    // 통과 시 반환
    if (criticReport.passed || !criticReport.needsRetry) {
      console.log(`✅ Critic 검토 통과 (점수: ${criticReport.score})`);
      notifyProgress('FINALIZING');

      // 최종 선거법 검증 (LLM 하이브리드)
      const finalCheck = await runHeuristicValidation(currentDraft, status, '', { useLLM: true });
      if (!finalCheck.passed) {
        console.warn(`⚠️ 최종 선거법 검증 실패:`, finalCheck.issues);
        // 위반 발견 시 Corrector로 수정 시도
        if (finalCheck.details.electionLaw?.violations?.length > 0) {
          console.log(`🔧 선거법 위반 자동 수정 시도...`);
          const correctionResult = await applyCorrections({
            draft: currentDraft,
            violations: finalCheck.details.electionLaw.violations.map(v => ({
              type: 'HARD',
              field: 'content',
              issue: v.reason,
              suggestion: `"${v.sentence}" 표현을 수정하세요`
            })),
            ragContext,
            authorName,
            status,
            modelName: 'gemini-2.0-flash-exp'
          });

          if (correctionResult.success && !correctionResult.unchanged) {
            console.log(`✅ 선거법 위반 수정 완료`);
            currentDraft = correctionResult.corrected;
          }
        }
      }

      notifyProgress('COMPLETED', { score: criticReport.score });
      return currentDraft;
    }

    // HARD 위반이 있으면 수정 시도
    if (hasHardViolations(criticReport)) {
      notifyProgress('CORRECTING', {
        violations: summarizeViolations(criticReport.violations)
      });

      console.log(`✨ Corrector로 수정 시도 (위반: ${criticReport.violations.length}건)...`);

      const correctionResult = await applyCorrections({
        draft: currentDraft,
        violations: criticReport.violations,
        ragContext,
        authorName,
        status,
        modelName: 'gemini-2.0-flash-exp'
      });

      if (correctionResult.success && !correctionResult.unchanged) {
        currentDraft = correctionResult.corrected;
        console.log(`✨ 수정 완료: ${correctionResult.originalLength}자 → ${correctionResult.correctedLength}자`);
      } else {
        console.warn(`⚠️ Corrector 수정 실패: ${correctionResult.error || '변경 없음'}`);
        // 수정 실패해도 루프 계속
      }
    } else {
      // SOFT 위반만 있으면 경고하고 통과
      console.log(`ℹ️ SOFT 위반만 발견 (${criticReport.violations.length}건) - 통과 처리`);
      notifyProgress('COMPLETED', {
        score: criticReport.score,
        warnings: criticReport.violations.length
      });
      return currentDraft;
    }
  }

  // ========================================
  // Phase 3: 루프 종료 - 최선 버전 반환
  // ========================================
  console.warn(`⚠️ Critic 루프 ${maxCriticAttempts}회 완료 - 최선 버전 반환 (점수: ${bestScore})`);

  notifyProgress('COMPLETED', {
    score: bestScore,
    warning: '일부 품질 기준 미달 - 수동 검토 권장'
  });

  // 최종 버전과 최고 점수 버전 비교
  const finalDraft = bestScore >= 70 ? bestVersion : currentDraft;

  return finalDraft || currentDraft || draft;
}

// ============================================================================
// Legacy 호환 함수
// ============================================================================

/**
 * LLM을 활용한 원고 품질 검증 (Legacy - Critic으로 대체)
 */
async function evaluateQualityWithLLM(content, modelName) {
  // Critic Agent로 대체됨 - 하위 호환성 유지
  return { passed: true, issues: [], suggestions: [] };
}

module.exports = {
  validateAndRetry,
  evaluateQualityWithLLM,
  // 개별 검증 함수도 export (테스트용)
  detectSentenceRepetition,
  detectElectionLawViolation,
  detectElectionLawViolationHybrid,  // v3 하이브리드
  runHeuristicValidation,            // async (기본 LLM 사용)
  runHeuristicValidationSync,        // sync (LLM 없이 빠른 검증)
  validateKeywordInsertion,
  validateTitleQuality,              // 제목 품질 검증
  countKeywordOccurrences,
  // 화이트리스트/블랙리스트 (테스트용)
  ALLOWED_ENDINGS,
  EXPLICIT_PLEDGE_PATTERNS,
  // Progress 관련
  GENERATION_STAGES
};
