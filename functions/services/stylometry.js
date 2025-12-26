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

    // 검증 및 정규화
    const validated = validateStyleFingerprint(fingerprint, bioContent.length);

    console.log(`✅ [Stylometry] 분석 완료 (신뢰도: ${validated.analysisMetadata.confidence})`);

    return validated;

  } catch (error) {
    console.error('❌ [Stylometry] 분석 실패:', error.message);
    throw new Error('문체 분석 중 오류가 발생했습니다: ' + error.message);
  }
}

/**
 * Style Fingerprint 유효성 검사 및 정규화
 */
function validateStyleFingerprint(fingerprint, sourceLength) {
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
      avgLength: clamp(fingerprint.sentencePatterns?.avgLength || 45, 15, 100),
      preferredStarters: ensureArray(fingerprint.sentencePatterns?.preferredStarters, 5),
      clauseComplexity: ensureEnum(
        fingerprint.sentencePatterns?.clauseComplexity,
        ['simple', 'medium', 'complex'],
        'medium'
      ),
      listingStyle: ensureEnum(
        fingerprint.sentencePatterns?.listingStyle,
        ['numbered', 'bullet', 'prose'],
        'prose'
      ),
      endingPatterns: ensureArray(fingerprint.sentencePatterns?.endingPatterns, 4)
    },

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
      version: '1.0'
    }
  };

  // 신뢰도 보정: 텍스트 길이에 따라 조정
  if (sourceLength < 200) {
    validated.analysisMetadata.confidence = Math.min(validated.analysisMetadata.confidence, 0.6);
  } else if (sourceLength < 500) {
    validated.analysisMetadata.confidence = Math.min(validated.analysisMetadata.confidence, 0.75);
  }

  return validated;
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

  const { compact = false } = options;

  if (compact) {
    // 간소화 버전 (토큰 절약)
    return buildCompactStyleGuide(fingerprint);
  }

  // 전체 버전
  const sections = [];

  // 1. 특징적 표현
  const phrases = fingerprint.characteristicPhrases;
  const allPhrases = [
    ...phrases.signatures,
    ...phrases.emphatics,
    ...phrases.conclusions
  ].filter(p => p).slice(0, 7);

  if (allPhrases.length > 0) {
    sections.push(`1. 특징적 표현 사용:\n   ${allPhrases.map(p => `"${p}"`).join(', ')}`);
  }

  // 2. 문장 구조
  const patterns = fingerprint.sentencePatterns;
  const starters = patterns.preferredStarters.slice(0, 3);
  if (starters.length > 0) {
    sections.push(`2. 문장 구조:\n   - 평균 ${patterns.avgLength}자 내외\n   - 시작: ${starters.map(s => `"${s}"`).join(', ')}\n   - 복잡도: ${patterns.clauseComplexity}`);
  }

  // 3. 어휘 선택
  const vocab = fingerprint.vocabularyProfile;
  const words = vocab.frequentWords.slice(0, 5);
  if (words.length > 0) {
    sections.push(`3. 어휘 선택:\n   - 선호 단어: ${words.join(', ')}\n   - 전문성: ${vocab.technicalLevel}`);
  }

  // 4. 어조
  const tone = fingerprint.toneProfile;
  const toneDesc = [];
  if (tone.formality > 0.6) toneDesc.push('격식체');
  else if (tone.formality < 0.4) toneDesc.push('친근체');
  if (tone.directness > 0.6) toneDesc.push('직접적');
  if (tone.optimism > 0.6) toneDesc.push('희망적');

  if (toneDesc.length > 0 || tone.toneDescription) {
    sections.push(`4. 어조:\n   - ${toneDesc.join(', ') || tone.toneDescription}`);
  }

  // 5. AI 상투어 대체
  const alts = fingerprint.aiAlternatives;
  const altLines = [];
  if (alts['instead_of_평범한_이웃'] !== '주민 여러분') {
    altLines.push(`"평범한 이웃" → "${alts['instead_of_평범한_이웃']}"`);
  }
  if (alts['instead_of_함께_힘을_모아'] !== '함께 만들어가겠습니다') {
    altLines.push(`"함께 힘을 모아" → "${alts['instead_of_함께_힘을_모아']}"`);
  }
  if (alts['instead_of_더_나은_내일'] !== '실질적인 변화') {
    altLines.push(`"더 나은 내일" → "${alts['instead_of_더_나은_내일']}"`);
  }

  if (altLines.length > 0) {
    sections.push(`5. AI 상투어 대체:\n   ${altLines.join('\n   ')}`);
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
function buildCompactStyleGuide(fingerprint) {
  const phrases = fingerprint.characteristicPhrases.signatures.slice(0, 3);
  const tone = fingerprint.toneProfile;

  let guide = `[문체] `;

  if (phrases.length > 0) {
    guide += `표현: ${phrases.map(p => `"${p}"`).join(', ')}. `;
  }

  const toneWords = [];
  if (tone.formality > 0.6) toneWords.push('격식체');
  if (tone.directness > 0.6) toneWords.push('직접적');
  if (tone.optimism > 0.6) toneWords.push('희망적');

  if (toneWords.length > 0) {
    guide += `어조: ${toneWords.join('/')}. `;
  }

  guide += `문장 ${fingerprint.sentencePatterns.avgLength}자 내외.`;

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
   - 평균 문장 길이: ${patterns.avgLength || 45}자 내외
   - 선호 시작어: ${patterns.preferredStarters?.slice(0, 3).join(', ') || '없음'}
   - 복잡도: ${patterns.clauseComplexity || 'medium'}
   - 종결 패턴: ${patterns.endingPatterns?.slice(0, 2).join(', ') || '습니다/합니다'}

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
  generateWithStyleTransfer
};
