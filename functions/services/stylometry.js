'use strict';

/**
 * functions/services/stylometry.js
 * Stylometry 기반 문체 분석 모듈
 *
 * 사용자 Bio 텍스트에서 고유한 문체(Style Fingerprint)를 추출합니다.
 * - Phase 1: Stylometry 분석 (어휘, 구문, 수사, 어조)
 * - Phase 2: Style Fingerprint 생성 (프롬프트 주입용)
 *
 * 단일 Gemini 호출로 전체 분석 수행 (비용/속도 최적화)
 */

const { callGenerativeModel } = require('./gemini');

/**
 * 텍스트에서 통계적 문체 정보를 추출합니다 (LLM 없이 직접 계산)
 * @param {string} text - 분석할 텍스트
 * @returns {Object} 통계적 문체 정보
 */
function analyzeTextStatistics(text) {
  if (!text || text.trim().length < 50) {
    return null;
  }

  const cleanText = text.trim();

  // 1. 문장 분리 (마침표, 물음표, 느낌표 기준)
  const sentences = cleanText
    .split(/[.!?]+/)
    .map(s => s.trim())
    .filter(s => s.length > 5); // 너무 짧은 문장 제외

  if (sentences.length < 3) {
    return null; // 문장이 너무 적으면 통계 의미 없음
  }

  // 2. 문장 길이 통계
  const lengths = sentences.map(s => s.length);
  const avgLength = Math.round(lengths.reduce((a, b) => a + b, 0) / lengths.length);
  const minLength = Math.min(...lengths);
  const maxLength = Math.max(...lengths);

  // 표준편차 계산
  const variance = lengths.reduce((sum, len) => sum + Math.pow(len - avgLength, 2), 0) / lengths.length;
  const stdDev = Math.round(Math.sqrt(variance));

  // 3. 구두점 빈도 분석
  const totalChars = cleanText.length;
  const punctuationStats = {
    comma: (cleanText.match(/,/g) || []).length,           // 콤마
    period: (cleanText.match(/\./g) || []).length,         // 마침표
    question: (cleanText.match(/\?/g) || []).length,       // 물음표
    exclamation: (cleanText.match(/!/g) || []).length,     // 느낌표
    colon: (cleanText.match(/:/g) || []).length,           // 콜론
    semicolon: (cleanText.match(/;/g) || []).length,       // 세미콜론
    ellipsis: (cleanText.match(/\.{3}|…/g) || []).length,  // 말줄임표
  };

  // 문장당 콤마 수 (콤마 과다 사용 지표)
  const commasPerSentence = sentences.length > 0
    ? Math.round((punctuationStats.comma / sentences.length) * 10) / 10
    : 0;

  // 4. 문장 복잡도 추정 (콤마, 접속사 기반)
  const conjunctions = (cleanText.match(/그리고|그러나|하지만|또한|그래서|따라서|그러므로|왜냐하면/g) || []).length;
  const complexityScore = (punctuationStats.comma + conjunctions) / sentences.length;

  let clauseComplexity;
  if (complexityScore < 1) clauseComplexity = 'simple';
  else if (complexityScore < 2.5) clauseComplexity = 'medium';
  else clauseComplexity = 'complex';

  // 5. 문장 길이 분포 (짧은/중간/긴 비율)
  const shortSentences = lengths.filter(l => l < 30).length;
  const mediumSentences = lengths.filter(l => l >= 30 && l <= 60).length;
  const longSentences = lengths.filter(l => l > 60).length;

  const distribution = {
    short: Math.round((shortSentences / sentences.length) * 100),   // 30자 미만
    medium: Math.round((mediumSentences / sentences.length) * 100), // 30-60자
    long: Math.round((longSentences / sentences.length) * 100)      // 60자 초과
  };

  console.log(`📊 [TextStats] 분석 완료: 문장 ${sentences.length}개, 평균 ${avgLength}자, 콤마/문장 ${commasPerSentence}`);

  return {
    sentenceCount: sentences.length,
    sentenceLength: {
      avg: avgLength,
      min: minLength,
      max: maxLength,
      stdDev,
      distribution
    },
    punctuation: {
      ...punctuationStats,
      commasPerSentence,
      totalPunctuation: Object.values(punctuationStats).reduce((a, b) => a + b, 0)
    },
    complexity: {
      score: Math.round(complexityScore * 10) / 10,
      level: clauseComplexity,
      conjunctionsCount: conjunctions
    },
    // 프롬프트 주입용 요약
    summary: `문장 평균 ${avgLength}자(${minLength}~${maxLength}자), 콤마 ${commasPerSentence}회/문장, 복잡도 ${clauseComplexity}`
  };
}

/**
 * Bio 텍스트에서 Style Fingerprint를 추출합니다
 * @param {string} bioContent - 사용자 자기소개 텍스트
 * @param {Object} options - 추가 옵션
 * @param {string} options.userName - 사용자 이름 (분석 컨텍스트용)
 * @param {string} options.region - 지역 (지역 용어 추출용)
 * @returns {Promise<Object>} Style Fingerprint 객체
 */
async function extractStyleFingerprint(bioContent, options = {}) {
  if (!bioContent || bioContent.trim().length < 100) {
    console.warn('⚠️ Bio 텍스트가 너무 짧아 stylometry 분석 불가 (최소 100자)');
    return null;
  }

  const { userName = '', region = '' } = options;

  // 📊 1단계: 통계적 분석 (LLM 없이 직접 계산)
  const textStats = analyzeTextStatistics(bioContent);
  if (textStats) {
    console.log(`📊 [Stylometry] 통계 분석 결과: ${textStats.summary}`);
  }

  const prompt = `당신은 정치 텍스트 전문 언어학자입니다. 다음 정치인의 자기소개 텍스트를 stylometry(문체 분석) 관점에서 분석하여 고유한 "Style Fingerprint"를 추출하세요.

[분석 대상 텍스트]
"""
${bioContent}
"""

${userName ? `[참고] 작성자: ${userName}` : ''}
${region ? `[참고] 지역: ${region}` : ''}

다음 JSON 형식으로 정확히 응답하세요. 텍스트에서 실제로 발견되는 패턴만 추출하세요.

{
  "characteristicPhrases": {
    "greetings": ["인사 표현 1-3개, 없으면 빈 배열"],
    "transitions": ["전환 표현 2-5개"],
    "conclusions": ["마무리 표현 1-3개"],
    "emphatics": ["강조 표현 2-5개"],
    "signatures": ["이 사람만의 독특한 표현 1-5개"]
  },

  "sentencePatterns": {
    "avgLength": 평균_문장_길이_숫자,
    "preferredStarters": ["선호하는 문장 시작어 3-5개"],
    "clauseComplexity": "simple 또는 medium 또는 complex",
    "listingStyle": "numbered 또는 bullet 또는 prose",
    "endingPatterns": ["자주 쓰는 문장 종결 패턴 2-4개"]
  },

  "vocabularyProfile": {
    "frequentWords": ["고빈도 명사/동사 5-10개"],
    "preferredVerbs": ["선호 동사 3-5개"],
    "preferredAdjectives": ["선호 형용사 2-4개"],
    "technicalLevel": "accessible 또는 moderate 또는 technical",
    "localTerms": ["지역 관련 용어 (있으면)"]
  },

  "toneProfile": {
    "formality": 0.0-1.0 사이 숫자 (0:친근 ~ 1:격식),
    "emotionality": 0.0-1.0 사이 숫자 (0:논리적 ~ 1:감성적),
    "directness": 0.0-1.0 사이 숫자 (0:완곡 ~ 1:직설),
    "optimism": 0.0-1.0 사이 숫자 (0:비판적 ~ 1:희망적),
    "toneDescription": "전체적인 어조를 한 문장으로 설명"
  },

  "rhetoricalDevices": {
    "usesRepetition": true 또는 false,
    "usesRhetoricalQuestions": true 또는 false,
    "usesMetaphors": true 또는 false,
    "usesEnumeration": true 또는 false,
    "examplePatterns": ["실제 사용된 수사적 패턴 2-5개"]
  },

  "aiAlternatives": {
    "instead_of_평범한_이웃": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_함께_힘을_모아": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_더_나은_내일": "이 사람이 실제로 쓸 대체 표현",
    "instead_of_밝은_미래": "이 사람이 실제로 쓸 대체 표현"
  },

  "analysisMetadata": {
    "confidence": 0.0-1.0 사이 숫자 (분석 신뢰도),
    "dominantStyle": "이 사람의 문체를 한 마디로 정의",
    "uniqueFeatures": ["다른 정치인과 구별되는 독특한 특징 2-3개"]
  }
}

분석 지침:
1. 텍스트에서 실제로 발견되는 패턴만 추출하세요. 추측하지 마세요.
2. 배열이 비어있어도 괜찮습니다. 억지로 채우지 마세요.
3. 수치는 텍스트 분석을 기반으로 정확하게 계산하세요.
4. aiAlternatives는 AI 상투어를 이 사람의 실제 어휘로 대체할 표현입니다.
5. JSON만 반환하세요. 다른 설명은 하지 마세요.`;

  try {
    console.log(`🔍 [Stylometry] 분석 시작 (텍스트 길이: ${bioContent.length}자)`);

    const response = await callGenerativeModel(prompt);
    const fingerprint = JSON.parse(response);

    // 검증 및 정규화 (통계값으로 보정)
    const validated = validateStyleFingerprint(fingerprint, bioContent.length, textStats);

    console.log(`✅ [Stylometry] 분석 완료 (신뢰도: ${validated.analysisMetadata.confidence})`);

    return validated;

  } catch (error) {
    console.error('❌ [Stylometry] 분석 실패:', error.message);
    throw new Error('문체 분석 중 오류가 발생했습니다: ' + error.message);
  }
}

/**
 * Style Fingerprint 유효성 검사 및 정규화
 * @param {Object} fingerprint - LLM이 반환한 fingerprint
 * @param {number} sourceLength - 원본 텍스트 길이
 * @param {Object} textStats - 통계적 분석 결과 (선택)
 */
function validateStyleFingerprint(fingerprint, sourceLength, textStats = null) {
  // 📊 통계값이 있으면 실제 계산값 사용, 없으면 LLM 추측값 또는 기본값
  const actualAvgLength = textStats?.sentenceLength?.avg
    || fingerprint.sentencePatterns?.avgLength
    || 45;

  const actualComplexity = textStats?.complexity?.level
    || fingerprint.sentencePatterns?.clauseComplexity
    || 'medium';

  // 기본 구조 보장
  const validated = {
    characteristicPhrases: {
      greetings: ensureArray(fingerprint.characteristicPhrases?.greetings, 3),
      transitions: ensureArray(fingerprint.characteristicPhrases?.transitions, 5),
      conclusions: ensureArray(fingerprint.characteristicPhrases?.conclusions, 3),
      emphatics: ensureArray(fingerprint.characteristicPhrases?.emphatics, 5),
      signatures: ensureArray(fingerprint.characteristicPhrases?.signatures, 5)
    },

    sentencePatterns: {
      // 📊 실제 통계값으로 오버라이드
      avgLength: clamp(actualAvgLength, 15, 100),
      minLength: textStats?.sentenceLength?.min || 10,
      maxLength: textStats?.sentenceLength?.max || 100,
      lengthRange: textStats ? `${textStats.sentenceLength.min}~${textStats.sentenceLength.max}자` : null,
      distribution: textStats?.sentenceLength?.distribution || null,
      preferredStarters: ensureArray(fingerprint.sentencePatterns?.preferredStarters, 5),
      clauseComplexity: ensureEnum(actualComplexity, ['simple', 'medium', 'complex'], 'medium'),
      listingStyle: ensureEnum(
        fingerprint.sentencePatterns?.listingStyle,
        ['numbered', 'bullet', 'prose'],
        'prose'
      ),
      endingPatterns: ensureArray(fingerprint.sentencePatterns?.endingPatterns, 4)
    },

    // 📊 구두점 통계 (신규)
    punctuationProfile: textStats ? {
      commasPerSentence: textStats.punctuation.commasPerSentence,
      totalCommas: textStats.punctuation.comma,
      questionMarks: textStats.punctuation.question,
      exclamationMarks: textStats.punctuation.exclamation,
      // 콤마 사용 권장 수준 결정
      commaGuidance: textStats.punctuation.commasPerSentence < 1
        ? '콤마 적게 사용 (문장당 1회 미만)'
        : textStats.punctuation.commasPerSentence < 2
          ? '콤마 보통 사용 (문장당 1-2회)'
          : '콤마 자주 사용 (문장당 2회 이상)'
    } : null,

    vocabularyProfile: {
      frequentWords: ensureArray(fingerprint.vocabularyProfile?.frequentWords, 10),
      preferredVerbs: ensureArray(fingerprint.vocabularyProfile?.preferredVerbs, 5),
      preferredAdjectives: ensureArray(fingerprint.vocabularyProfile?.preferredAdjectives, 4),
      technicalLevel: ensureEnum(
        fingerprint.vocabularyProfile?.technicalLevel,
        ['accessible', 'moderate', 'technical'],
        'accessible'
      ),
      localTerms: ensureArray(fingerprint.vocabularyProfile?.localTerms, 10)
    },

    toneProfile: {
      formality: clamp(fingerprint.toneProfile?.formality || 0.5, 0, 1),
      emotionality: clamp(fingerprint.toneProfile?.emotionality || 0.5, 0, 1),
      directness: clamp(fingerprint.toneProfile?.directness || 0.5, 0, 1),
      optimism: clamp(fingerprint.toneProfile?.optimism || 0.5, 0, 1),
      toneDescription: fingerprint.toneProfile?.toneDescription || '중립적인 어조'
    },

    rhetoricalDevices: {
      usesRepetition: Boolean(fingerprint.rhetoricalDevices?.usesRepetition),
      usesRhetoricalQuestions: Boolean(fingerprint.rhetoricalDevices?.usesRhetoricalQuestions),
      usesMetaphors: Boolean(fingerprint.rhetoricalDevices?.usesMetaphors),
      usesEnumeration: Boolean(fingerprint.rhetoricalDevices?.usesEnumeration),
      examplePatterns: ensureArray(fingerprint.rhetoricalDevices?.examplePatterns, 5)
    },

    aiAlternatives: {
      'instead_of_평범한_이웃': fingerprint.aiAlternatives?.['instead_of_평범한_이웃'] || '주민 여러분',
      'instead_of_함께_힘을_모아': fingerprint.aiAlternatives?.['instead_of_함께_힘을_모아'] || '함께 만들어가겠습니다',
      'instead_of_더_나은_내일': fingerprint.aiAlternatives?.['instead_of_더_나은_내일'] || '실질적인 변화',
      'instead_of_밝은_미래': fingerprint.aiAlternatives?.['instead_of_밝은_미래'] || '구체적인 성과'
    },

    analysisMetadata: {
      confidence: clamp(fingerprint.analysisMetadata?.confidence || 0.7, 0, 1),
      dominantStyle: fingerprint.analysisMetadata?.dominantStyle || '표준적인 정치 문체',
      uniqueFeatures: ensureArray(fingerprint.analysisMetadata?.uniqueFeatures, 3),
      sourceLength,
      analyzedAt: new Date().toISOString(),
      version: '2.0',  // 📊 통계 분석 추가 버전
      // 📊 통계 분석 포함 여부
      hasStatistics: !!textStats
    },

    // 📊 원본 통계 데이터 (디버깅/분석용)
    textStatistics: textStats || null
  };

  // 신뢰도 보정: 텍스트 길이에 따라 조정
  if (sourceLength < 200) {
    validated.analysisMetadata.confidence = Math.min(validated.analysisMetadata.confidence, 0.6);
  } else if (sourceLength < 500) {
    validated.analysisMetadata.confidence = Math.min(validated.analysisMetadata.confidence, 0.75);
  }

  // 📊 통계 데이터가 있으면 신뢰도 상향
  if (textStats) {
    validated.analysisMetadata.confidence = Math.min(
      validated.analysisMetadata.confidence + 0.1,
      1.0
    );
  }

  return validated;
}

const STYLE_GUIDE_SENTENCE_SPLIT_RE = /(?<=[.!?])\s+|\n+/;
const STYLE_GUIDE_TRANSITION_PREFIXES = ['이제', '그리고', '그러나', '하지만', '무엇보다', '그래서', '또한', '먼저', '결국', '저는'];
const STYLE_GUIDE_POSITIONING_MARKERS = ['태어나', '자라', '출신', '로서', '경험', '기업인', '전문가', '막내', '아들', '딸', '사람'];
const STYLE_GUIDE_EMOTION_MARKERS = ['반드시', '분명', '책임', '약속', '희망', '감사', '애정', '소중', '지키겠습니다', '해내겠습니다'];

function normalizeGuideSentence(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

function truncateGuideSentence(text, maxLength = 90) {
  const normalized = normalizeGuideSentence(text);
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, Math.max(1, maxLength - 1)).trim()}…`;
}

function splitGuideSentences(text, maxItems = 40) {
  if (!text || typeof text !== 'string') {
    return [];
  }

  return text
    .split(STYLE_GUIDE_SENTENCE_SPLIT_RE)
    .map(normalizeGuideSentence)
    .filter(sentence => sentence.length >= 18)
    .slice(0, maxItems);
}

function collectGuideExamples(sentences, predicate, used, limit = 2) {
  const results = [];
  for (const sentence of sentences) {
    const key = sentence.toLowerCase();
    if (used.has(key) || !predicate(sentence)) {
      continue;
    }
    used.add(key);
    results.push(truncateGuideSentence(sentence));
    if (results.length >= limit) {
      break;
    }
  }
  return results;
}

function buildSourceStyleExamples(fingerprint, sourceText = '') {
  const sentences = splitGuideSentences(sourceText);
  if (sentences.length === 0) {
    return {
      transitionExamples: [],
      concretizationExamples: [],
      shortExample: '',
      longExample: '',
      positioningExamples: [],
      emotionExamples: [],
    };
  }

  const phrases = fingerprint.characteristicPhrases || {};
  const patterns = fingerprint.sentencePatterns || {};
  const vocab = fingerprint.vocabularyProfile || {};
  const rhetoric = fingerprint.rhetoricalDevices || {};
  const used = new Set();

  const transitionTokens = [
    ...(phrases.transitions || []),
    ...(patterns.preferredStarters || []),
    ...STYLE_GUIDE_TRANSITION_PREFIXES,
  ].filter(Boolean).map(normalizeGuideSentence);
  const vocabTokens = [
    ...(vocab.localTerms || []),
    ...(vocab.frequentWords || []),
    ...(vocab.preferredVerbs || []),
  ].filter(Boolean).map(normalizeGuideSentence);
  const emotionTokens = [
    ...(phrases.emphatics || []),
    ...(phrases.conclusions || []),
    ...STYLE_GUIDE_EMOTION_MARKERS,
  ].filter(Boolean).map(normalizeGuideSentence);
  const signatureTokens = (phrases.signatures || []).filter(Boolean).map(normalizeGuideSentence);

  const transitionExamples = collectGuideExamples(
    sentences,
    sentence => transitionTokens.some(token => token && sentence.includes(token)),
    used,
    2
  );
  const concretizationExamples = collectGuideExamples(
    sentences,
    sentence => /\d/.test(sentence)
      || vocabTokens.some(token => token && sentence.includes(token))
      || ((sentence.length >= 24 && sentence.length <= 95) && /(일자리|골목|아이|항만|주거|교육|복지|경제)/.test(sentence)),
    used,
    2
  );
  const positioningExamples = collectGuideExamples(
    sentences,
    sentence => signatureTokens.some(token => token && sentence.includes(token))
      || (/^(?:저는|저 이|저는 바로|이재성은|저는 부산)/.test(sentence)
        && STYLE_GUIDE_POSITIONING_MARKERS.some(token => sentence.includes(token))),
    used,
    2
  );
  const emotionExamples = collectGuideExamples(
    sentences,
    sentence => emotionTokens.some(token => token && sentence.includes(token)),
    used,
    2
  );
  const shortExample = collectGuideExamples(sentences, sentence => sentence.length <= 38, used, 1)[0] || '';
  const longExample = collectGuideExamples(sentences, sentence => sentence.length >= 58, used, 1)[0] || '';

  if (!transitionExamples.length && rhetoric.examplePatterns?.length) {
    for (const item of rhetoric.examplePatterns.slice(0, 2)) {
      const normalized = truncateGuideSentence(item);
      const key = normalized.toLowerCase();
      if (!normalized || used.has(key)) {
        continue;
      }
      used.add(key);
      transitionExamples.push(normalized);
      if (transitionExamples.length >= 2) {
        break;
      }
    }
  }

  return {
    transitionExamples,
    concretizationExamples,
    shortExample,
    longExample,
    positioningExamples,
    emotionExamples,
  };
}

/**
 * Style Fingerprint를 프롬프트 주입용 텍스트로 변환
 * @param {Object} fingerprint - Style Fingerprint 객체
 * @param {Object} options - 옵션
 * @param {boolean} options.compact - 간소화 버전 여부
 * @returns {string} 프롬프트에 주입할 스타일 가이드 텍스트
 */
function buildStyleGuidePrompt(fingerprint, options = {}) {
  if (!fingerprint || fingerprint.analysisMetadata?.confidence < 0.5) {
    return ''; // 신뢰도 낮으면 스타일 가이드 생략
  }

  const { compact = false, sourceText = '' } = options;
  const phrases = fingerprint.characteristicPhrases || {};
  const patterns = fingerprint.sentencePatterns || {};
  const vocab = fingerprint.vocabularyProfile || {};
  const tone = fingerprint.toneProfile || {};
  const rhetoric = fingerprint.rhetoricalDevices || {};
  const analysis = fingerprint.analysisMetadata || {};
  const punctuation = fingerprint.punctuationProfile || {};

  const transitions = (phrases.transitions || []).filter(Boolean).slice(0, 4);
  const examplePatterns = (rhetoric.examplePatterns || []).filter(Boolean).slice(0, 3);
  const signatures = (phrases.signatures || []).filter(Boolean).slice(0, 4);
  const emphatics = (phrases.emphatics || []).filter(Boolean).slice(0, 3);
  const conclusions = (phrases.conclusions || []).filter(Boolean).slice(0, 3);
  const starters = (patterns.preferredStarters || []).filter(Boolean).slice(0, 3);
  const endings = (patterns.endingPatterns || []).filter(Boolean).slice(0, 3);
  const frequentWords = (vocab.frequentWords || []).filter(Boolean).slice(0, 5);
  const preferredVerbs = (vocab.preferredVerbs || []).filter(Boolean).slice(0, 4);
  const preferredAdjectives = (vocab.preferredAdjectives || []).filter(Boolean).slice(0, 3);
  const localTerms = (vocab.localTerms || []).filter(Boolean).slice(0, 4);
  const uniqueFeatures = (analysis.uniqueFeatures || []).filter(Boolean).slice(0, 3);
  const sourceExamples = buildSourceStyleExamples(fingerprint, sourceText);

  if (compact) {
    // 간소화 버전 (토큰 절약)
    return buildCompactStyleGuide(fingerprint, { sourceText });
  }

  // 전체 버전
  const sections = [];
  const lengthInfo = patterns.lengthRange
    ? `${patterns.avgLength}자 내외 (${patterns.lengthRange})`
    : `${patterns.avgLength || 45}자 내외`;

  if (transitions.length > 0 || examplePatterns.length > 0 || sourceExamples.transitionExamples.length > 0) {
    const transitionLines = [];
    if (sourceExamples.transitionExamples.length > 0) {
      transitionLines.push(`- 실제 사용자 문장 예시: ${sourceExamples.transitionExamples.map(item => `"${item}"`).join(', ')}`);
    }
    if (transitions.length > 0) {
      transitionLines.push(`- 선언 뒤 연결: ${transitions.map(item => `"${item}"`).join(', ')}`);
    }
    if (examplePatterns.length > 0) {
      transitionLines.push(`- 실제 전개 예시: ${examplePatterns.map(item => `"${item}"`).join(', ')}`);
    }
    sections.push(`1. 전환 패턴:\n   ${transitionLines.join('\n   ')}`);
  }

  const concretizationLines = [
    `- 추상 주장을 푸는 밀도: ${lengthInfo}, 복잡도 ${patterns.clauseComplexity || 'medium'}`
  ];
  const concretizationWords = localTerms.length > 0 ? localTerms : frequentWords;
  if (sourceExamples.concretizationExamples.length > 0) {
    concretizationLines.push(`- 실제 사용자 문장 예시: ${sourceExamples.concretizationExamples.map(item => `"${item}"`).join(', ')}`);
  }
  if (concretizationWords.length > 0) {
    concretizationLines.push(`- 생활/현장 언어: ${concretizationWords.join(', ')}`);
  }
  if (preferredVerbs.length > 0) {
    concretizationLines.push(`- 행동 동사: ${preferredVerbs.join(', ')}`);
  }
  concretizationLines.push(`- 사실·정책 설명 수준: ${vocab.technicalLevel || 'accessible'}`);
  sections.push(`2. 구체화 패턴:\n   ${concretizationLines.join('\n   ')}`);

  const rhythmLines = [
    `- 문장 길이: ${lengthInfo}`,
    `- 문장 복잡도: ${patterns.clauseComplexity || 'medium'}`
  ];
  if (starters.length > 0) {
    rhythmLines.push(`- 선호 시작어: ${starters.map(item => `"${item}"`).join(', ')}`);
  }
  if (endings.length > 0) {
    rhythmLines.push(`- 단락/문장 마감: ${endings.join(', ')}`);
  }
  if (rhetoric.usesRepetition) rhythmLines.push('- 반복 구조를 활용하는 편');
  if (rhetoric.usesEnumeration) rhythmLines.push('- 나열형 전개를 활용하는 편');
  if (punctuation.commaGuidance) rhythmLines.push(`- 콤마: ${punctuation.commaGuidance}`);
  sections.push(`3. 리듬 패턴:\n   ${rhythmLines.join('\n   ')}`);

  const vocabLines = [];
  if (preferredVerbs.length > 0) {
    vocabLines.push(`- 반복 동사: ${preferredVerbs.join(', ')}`);
  }
  if (frequentWords.length > 0) {
    vocabLines.push(`- 생활 명사/핵심 단어: ${frequentWords.join(', ')}`);
  }
  if (localTerms.length > 0) {
    vocabLines.push(`- 지역/현장 용어: ${localTerms.join(', ')}`);
  }
  const phraseCluster = [...signatures, ...emphatics, ...preferredAdjectives].filter(Boolean).slice(0, 6);
  if (phraseCluster.length > 0) {
    vocabLines.push(`- 시그니처 표현: ${phraseCluster.map(item => `"${item}"`).join(', ')}`);
  }
  if (vocabLines.length > 0) {
    sections.push(`4. 선호 어휘 클러스터:\n   ${vocabLines.join('\n   ')}`);
  }

  const positioningLines = [];
  if (analysis.dominantStyle) {
    positioningLines.push(`- 기본 포지셔닝: ${analysis.dominantStyle}`);
  }
  if (uniqueFeatures.length > 0) {
    positioningLines.push(`- 두드러진 정체성 요소: ${uniqueFeatures.join(', ')}`);
  }
  if (signatures.length > 0) {
    positioningLines.push(`- 자기 소개/선언 표현: ${signatures.map(item => `"${item}"`).join(', ')}`);
  }
  if (sourceExamples.positioningExamples.length > 0) {
    positioningLines.push(`- 실제 자기 선언 예시: ${sourceExamples.positioningExamples.map(item => `"${item}"`).join(', ')}`);
  }
  if (positioningLines.length > 0) {
    sections.push(`5. 화자 포지셔닝 방식:\n   ${positioningLines.join('\n   ')}`);
  }

  const toneDesc = [];
  if (tone.formality > 0.6) toneDesc.push('격식체');
  else if (tone.formality < 0.4) toneDesc.push('친근체');
  if (tone.directness > 0.6) toneDesc.push('직접적');
  if (tone.optimism > 0.6) toneDesc.push('희망적');
  const emotionLines = [];
  if (toneDesc.length > 0) {
    emotionLines.push(`- 어조: ${toneDesc.join(', ')}`);
  }
  if (tone.toneDescription) {
    emotionLines.push(`- 감정 표현 설명: ${tone.toneDescription}`);
  }
  if ((tone.emotionality || 0) >= 0.6) {
    emotionLines.push('- 감정을 직접 드러내는 편');
  } else if ((tone.emotionality || 0) <= 0.4) {
    emotionLines.push('- 감정보다 사실과 단정으로 밀어붙이는 편');
  }
  const emotionPhrases = [...emphatics, ...conclusions].filter(Boolean).slice(0, 5);
  if (emotionPhrases.length > 0) {
    emotionLines.push(`- 확신/마감 표현: ${emotionPhrases.map(item => `"${item}"`).join(', ')}`);
  }
  if (sourceExamples.emotionExamples.length > 0) {
    emotionLines.push(`- 실제 감정/선언 문장: ${sourceExamples.emotionExamples.map(item => `"${item}"`).join(', ')}`);
  }
  if (emotionLines.length > 0) {
    sections.push(`6. 감정 표현 방식:\n   ${emotionLines.join('\n   ')}`);
  }

  const alts = fingerprint.aiAlternatives || {};
  const altLines = Object.entries(alts)
    .map(([rawKey, rawValue]) => {
      const source = String(rawKey || '').replace('instead_of_', '').replaceAll('_', ' ').trim();
      const target = String(rawValue || '').trim();
      if (!source || !target) return '';
      return `- "${source}" 대신 "${target}"`;
    })
    .filter(Boolean)
    .slice(0, 4);

  if (altLines.length > 0) {
    sections.push(`7. AI 상투어 대체:\n   ${altLines.join('\n   ')}`);
  }

  if (sections.length === 0) {
    return '';
  }

  return `
┌───────────────────────────────────────────────────────────────┐
│  🎨 [문체 가이드] - 이 사용자의 고유 스타일을 따르세요         │
└───────────────────────────────────────────────────────────────┘

${sections.join('\n\n')}

`;
}

/**
 * 간소화된 스타일 가이드 (토큰 절약)
 */
function buildCompactStyleGuide(fingerprint, options = {}) {
  const characteristicPhrases = fingerprint.characteristicPhrases || {};
  const phrases = (characteristicPhrases.signatures || []).slice(0, 3);
  const transitions = (characteristicPhrases.transitions || []).slice(0, 2);
  const rhetoric = fingerprint.rhetoricalDevices || {};
  const examplePatterns = (rhetoric.examplePatterns || []).slice(0, 2);
  const tone = fingerprint.toneProfile || {};
  const patterns = fingerprint.sentencePatterns || {};
  const sourceExamples = buildSourceStyleExamples(fingerprint, options.sourceText || '');

  let guide = `[문체] `;

  if (phrases.length > 0) {
    guide += `표현: ${phrases.map(p => `"${p}"`).join(', ')}. `;
  }
  if (transitions.length > 0) {
    guide += `전환: ${transitions.map(p => `"${p}"`).join(', ')}. `;
  }
  if (examplePatterns.length > 0) {
    guide += `전개 예시: ${examplePatterns.map(p => `"${p}"`).join(', ')}. `;
  }

  if (sourceExamples.transitionExamples.length > 0) {
    guide += `실제 문장: ${sourceExamples.transitionExamples.map(p => `"${p}"`).join(', ')}. `;
  }

  const toneWords = [];
  if (tone.formality > 0.6) toneWords.push('격식체');
  if (tone.directness > 0.6) toneWords.push('직접적');
  if (tone.optimism > 0.6) toneWords.push('희망적');

  if (toneWords.length > 0) {
    guide += `어조: ${toneWords.join('/')}. `;
  }

  // 📊 문장 길이 (범위 포함)
  const lengthInfo = patterns.lengthRange
    ? `${patterns.avgLength}자(${patterns.lengthRange})`
    : `${patterns.avgLength || 45}자`;
  guide += `문장 ${lengthInfo}.`;

  // 📊 콤마 가이드 (있으면)
  const punctuation = fingerprint.punctuationProfile;
  if (punctuation && punctuation.commasPerSentence < 1.5) {
    guide += ` 콤마 절제.`;
  }

  return guide + '\n';
}

// 유틸리티 함수들
function ensureArray(value, maxLength) {
  if (!Array.isArray(value)) return [];
  return value.filter(v => v && typeof v === 'string').slice(0, maxLength);
}

function clamp(value, min, max) {
  if (typeof value !== 'number' || isNaN(value)) return (min + max) / 2;
  return Math.max(min, Math.min(max, value));
}

function ensureEnum(value, allowed, defaultValue) {
  if (allowed.includes(value)) return value;
  return defaultValue;
}

/**
 * 2단계 생성 (Option B): Text Style Transfer
 * 중립적 초안을 사용자 고유 문체로 변환합니다.
 *
 * @param {string} neutralDraft - 1단계에서 생성된 중립적 초안
 * @param {Object} styleFingerprint - 사용자의 Style Fingerprint
 * @param {Object} options - 추가 옵션
 * @param {string} options.userName - 사용자 이름
 * @param {string} options.category - 글 카테고리
 * @returns {Promise<string>} 스타일 변환된 텍스트
 */
async function transferStyle(neutralDraft, styleFingerprint, options = {}) {
  if (!neutralDraft || !styleFingerprint) {
    console.warn('⚠️ [StyleTransfer] 입력 누락 - 원본 반환');
    return neutralDraft;
  }

  const confidence = styleFingerprint.analysisMetadata?.confidence || 0;
  if (confidence < 0.6) {
    console.warn(`⚠️ [StyleTransfer] 신뢰도 낮음 (${confidence}) - 원본 반환`);
    return neutralDraft;
  }

  const { userName = '', category = '' } = options;

  // Style Fingerprint에서 핵심 요소 추출
  const phrases = styleFingerprint.characteristicPhrases || {};
  const patterns = styleFingerprint.sentencePatterns || {};
  const vocab = styleFingerprint.vocabularyProfile || {};
  const tone = styleFingerprint.toneProfile || {};
  const rhetoric = styleFingerprint.rhetoricalDevices || {};
  const alts = styleFingerprint.aiAlternatives || {};

  const prompt = `당신은 텍스트 문체 변환 전문가입니다. 주어진 중립적 초안을 특정 화자의 고유한 문체로 변환하세요.

[변환할 초안]
"""
${neutralDraft}
"""

[목표 문체 - Style Fingerprint]

1. 특징적 표현 (반드시 적절한 위치에 사용):
   - 인사: ${phrases.greetings?.slice(0, 2).join(', ') || '없음'}
   - 강조: ${phrases.emphatics?.slice(0, 3).join(', ') || '없음'}
   - 마무리: ${phrases.conclusions?.slice(0, 2).join(', ') || '없음'}
   - 시그니처: ${phrases.signatures?.slice(0, 3).join(', ') || '없음'}

2. 문장 패턴:
   - 문장 길이: ${patterns.avgLength || 45}자 내외${patterns.lengthRange ? ` (${patterns.lengthRange})` : ''}
   - 선호 시작어: ${patterns.preferredStarters?.slice(0, 3).join(', ') || '없음'}
   - 복잡도: ${patterns.clauseComplexity || 'medium'}
   - 종결 패턴: ${patterns.endingPatterns?.slice(0, 2).join(', ') || '습니다/합니다'}${styleFingerprint.punctuationProfile ? `
   - 콤마 사용: ${styleFingerprint.punctuationProfile.commaGuidance}` : ''}

3. 어휘:
   - 선호 단어: ${vocab.frequentWords?.slice(0, 5).join(', ') || '없음'}
   - 선호 동사: ${vocab.preferredVerbs?.slice(0, 3).join(', ') || '없음'}
   - 전문성 수준: ${vocab.technicalLevel || 'accessible'}

4. 어조 수치 (0.0~1.0):
   - 격식성: ${tone.formality?.toFixed(2) || 0.5} (0:친근 ~ 1:격식)
   - 감성도: ${tone.emotionality?.toFixed(2) || 0.5} (0:논리 ~ 1:감성)
   - 직접성: ${tone.directness?.toFixed(2) || 0.5} (0:완곡 ~ 1:직설)
   - 희망성: ${tone.optimism?.toFixed(2) || 0.5} (0:비판 ~ 1:희망)
   - 전체 어조: ${tone.toneDescription || '중립적'}

5. 수사 장치:
   ${rhetoric.usesRepetition ? '- 반복 사용 ✓' : ''}
   ${rhetoric.usesRhetoricalQuestions ? '- 수사적 질문 사용 ✓' : ''}
   ${rhetoric.usesEnumeration ? '- 열거 사용 ✓' : ''}
   - 예시: ${rhetoric.examplePatterns?.slice(0, 2).join(', ') || '없음'}

6. AI 상투어 대체 (반드시 대체):
   - "평범한 이웃" → "${alts['instead_of_평범한_이웃'] || '주민 여러분'}"
   - "함께 힘을 모아" → "${alts['instead_of_함께_힘을_모아'] || '함께 만들어가겠습니다'}"
   - "더 나은 내일" → "${alts['instead_of_더_나은_내일'] || '실질적인 변화'}"
   - "밝은 미래" → "${alts['instead_of_밝은_미래'] || '구체적인 성과'}"

[변환 지침]
1. 내용과 구조는 유지하면서 문체만 변환하세요.
2. 특징적 표현을 자연스럽게 녹여 넣으세요. 억지로 끼워 넣지 마세요.
3. 문장 길이와 복잡도를 목표 패턴에 맞추세요.
4. 어조 수치를 참고하여 전체적인 톤을 조정하세요.
5. AI 상투어는 반드시 대체 표현으로 바꾸세요.
6. 원본의 핵심 메시지는 절대 변경하지 마세요.
7. 자연스러움이 가장 중요합니다.

${userName ? `[참고] 화자: ${userName}` : ''}
${category ? `[참고] 글 유형: ${category}` : ''}

변환된 텍스트만 반환하세요. 설명이나 주석은 포함하지 마세요.`;

  try {
    console.log(`🔄 [StyleTransfer] 문체 변환 시작 (초안 ${neutralDraft.length}자)`);

    const transformed = await callGenerativeModel(prompt);

    console.log(`✅ [StyleTransfer] 변환 완료 (${transformed.length}자)`);

    return transformed.trim();

  } catch (error) {
    console.error('❌ [StyleTransfer] 변환 실패:', error.message);
    // 실패 시 원본 반환 (graceful degradation)
    return neutralDraft;
  }
}

/**
 * 2단계 고품질 생성 파이프라인
 * 1단계: 중립적 초안 생성 → 2단계: 문체 변환
 *
 * @param {Function} generateNeutralDraft - 중립적 초안 생성 함수
 * @param {Object} styleFingerprint - Style Fingerprint
 * @param {Object} options - 옵션
 * @returns {Promise<{drafts: string[], metadata: Object}>}
 */
async function generateWithStyleTransfer(generateNeutralDraft, styleFingerprint, options = {}) {
  const { count = 3, userName = '', category = '' } = options;

  console.log(`🚀 [HighQuality] 2단계 생성 시작 (${count}개)`);

  // 1단계: 중립적 초안 생성
  console.log('📝 [HighQuality] 1단계: 중립적 초안 생성...');
  const neutralDrafts = await generateNeutralDraft();

  if (!neutralDrafts || neutralDrafts.length === 0) {
    throw new Error('중립적 초안 생성 실패');
  }

  console.log(`✅ [HighQuality] 중립적 초안 ${neutralDrafts.length}개 생성 완료`);

  // Style Fingerprint 없으면 1단계 결과 반환
  if (!styleFingerprint || styleFingerprint.analysisMetadata?.confidence < 0.6) {
    console.log('⚠️ [HighQuality] Style Fingerprint 없음 - 1단계 결과 반환');
    return {
      drafts: neutralDrafts,
      metadata: {
        mode: 'single-stage',
        reason: 'no-style-fingerprint'
      }
    };
  }

  // 2단계: 문체 변환
  console.log('🎨 [HighQuality] 2단계: 문체 변환...');
  const transformedDrafts = [];

  for (let i = 0; i < neutralDrafts.length; i++) {
    console.log(`   [${i + 1}/${neutralDrafts.length}] 변환 중...`);
    const transformed = await transferStyle(neutralDrafts[i], styleFingerprint, {
      userName,
      category
    });
    transformedDrafts.push(transformed);

    // API 쿼터 보호 (2초 딜레이)
    if (i < neutralDrafts.length - 1) {
      await new Promise(r => setTimeout(r, 2000));
    }
  }

  console.log(`✅ [HighQuality] 2단계 생성 완료 (${transformedDrafts.length}개)`);

  return {
    drafts: transformedDrafts,
    metadata: {
      mode: 'two-stage',
      styleConfidence: styleFingerprint.analysisMetadata?.confidence,
      dominantStyle: styleFingerprint.analysisMetadata?.dominantStyle
    }
  };
}

module.exports = {
  extractStyleFingerprint,
  buildStyleGuidePrompt,
  validateStyleFingerprint,
  transferStyle,
  generateWithStyleTransfer,
  // 📊 통계 분석 함수 (독립 사용 가능)
  analyzeTextStatistics
};
