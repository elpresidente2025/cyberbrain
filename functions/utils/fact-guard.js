'use strict';

const { callGenerativeModel } = require('../services/gemini');

// ============================================================================
// 상수 정의
// ============================================================================

const SINGLE_DIGIT_VALUES = new Set(['1', '2', '3', '4', '5', '6', '7', '8', '9']);
const URL_PATTERN = /https?:\/\/\S+/gi;

// 1-1. 일반 상식 화이트리스트
const COMMON_KNOWLEDGE = new Set([
  // 현재 연도 ±2년 (동적 생성 권장하지만 일단 하드코딩)
  '2024', '2025', '2026', '2027', '2028',
  // 대한민국 주요 행정구역 인구 (공식 통계 기준)
  '5100만', '5000만',       // 대한민국 총인구
  '1300만',                 // 영남권
  '950만', '1000만',        // 서울
  '340만', '330만',         // 부산
  '300만', '290만',         // 인천
  '250만', '240만',         // 대구
  '150만', '145만',         // 대전, 광주
  // 일반적 표현
  '100%', '50%', '0%',
  '1위', '2위', '3위', '10위', '10위권', '20위권', '100위권',
  // 일반 기간
  '1년', '2년', '3년', '5년', '10년',
  '1개월', '3개월', '6개월', '12개월',
  // 배수/비율 표현
  '2배', '3배', '10배', '100배',
  '절반', '1/2', '1/3', '1/4'
]);

// 수치 단위 토큰
const NUMBER_UNIT_TOKENS = [
  '%', '퍼센트', '프로', '%p', 'p', 'pt', '포인트',
  '명', '인', '개', '개사', '개소', '곳', '건', '위', '대', '호',
  '가구', '세대', '회', '차',
  '년', '월', '일', '주', '시', '분', '초',
  'km', 'kg', '㎡', '평', 'm', 'cm', 'mm',
  '원', '만원', '억원', '조원', '조', '억', '만', '천',
  '배'  // 배수 추가
];

const UNIT_PATTERN = NUMBER_UNIT_TOKENS
  .slice()
  .sort((a, b) => b.length - a.length)
  .map((token) => token.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  .join('|');

const NUMBER_TOKEN_REGEX = new RegExp(
  `\\d+(?:,\\d{3})*(?:\\.\\d+)?\\s*(?:${UNIT_PATTERN})?`,
  'gi'
);

// 1-3. 한글 숫자 매핑
const KOREAN_DIGIT_MAP = {
  '영': 0, '공': 0, '零': 0,
  '일': 1, '하나': 1, '한': 1, '壹': 1,
  '이': 2, '둘': 2, '두': 2, '貳': 2,
  '삼': 3, '셋': 3, '세': 3, '參': 3,
  '사': 4, '넷': 4, '네': 4, '四': 4,
  '오': 5, '다섯': 5, '五': 5,
  '육': 6, '여섯': 6, '六': 6,
  '칠': 7, '일곱': 7, '七': 7,
  '팔': 8, '여덟': 8, '八': 8,
  '구': 9, '아홉': 9, '九': 9,
  '십': 10, '열': 10, '十': 10,
  '백': 100, '百': 100,
  '천': 1000, '千': 1000,
  '만': 10000, '萬': 10000,
  '억': 100000000, '億': 100000000,
  '조': 1000000000000, '兆': 1000000000000
};

// ============================================================================
// 기본 유틸리티 함수
// ============================================================================

function normalizeNumericToken(token) {
  if (!token) return '';
  let normalized = String(token).trim();
  if (!normalized) return '';
  normalized = normalized.replace(/\s+/g, '');
  normalized = normalized.replace(/,/g, '');
  normalized = normalized.replace(/％/g, '%');
  normalized = normalized.replace(/퍼센트|프로/gi, '%');
  normalized = normalized.replace(/포인트/gi, 'p');
  normalized = normalized.replace(/%p/gi, 'p');
  normalized = normalized.replace(/pt$/i, 'p');
  return normalized;
}

function splitNumericToken(token) {
  const normalized = normalizeNumericToken(token);
  if (!normalized) return { value: '', unit: '' };
  const match = normalized.match(/^(\d+(?:\.\d+)?)(.*)$/);
  if (!match) return { value: '', unit: '' };
  return { value: match[1], unit: match[2] || '' };
}

function normalizeNumericSpacing(text) {
  if (!text) return '';
  let normalized = String(text);
  normalized = normalized.replace(/(\d)\s*\.\s*(\d)/g, '$1.$2');
  normalized = normalized.replace(/(\d)\s*,\s*(\d)/g, '$1,$2');
  normalized = normalized.replace(/(\d)\s*(%|퍼센트|포인트|%p|p|pt)/gi, '$1$2');
  normalized = normalized.replace(/(\d)\s*(명|개|곳|가구|억|조|원|만원|억원|조원|km|kg|m|cm|mm|배)/gi, '$1$2');
  return normalized;
}

// ============================================================================
// 1-3. 한글 숫자 정규화
// ============================================================================

function normalizeKoreanNumber(text) {
  if (!text) return text;
  let result = String(text);

  // 복합 한글 숫자 패턴 (예: 삼백오십만, 이천이백)
  const complexPattern = /([일이삼사오육칠팔구십백천만억조]+)/g;

  result = result.replace(complexPattern, (match) => {
    return convertKoreanToNumber(match);
  });

  return result;
}

function convertKoreanToNumber(koreanStr) {
  if (!koreanStr) return koreanStr;

  let total = 0;
  let current = 0;
  let bigUnit = 0;

  const chars = koreanStr.split('');

  for (const char of chars) {
    const value = KOREAN_DIGIT_MAP[char];
    if (value === undefined) continue;

    if (value >= 100000000) {  // 억 이상
      if (current === 0) current = 1;
      bigUnit += (current + (bigUnit > 0 ? 0 : total)) * value;
      total = 0;
      current = 0;
    } else if (value >= 10000) {  // 만
      if (current === 0) current = 1;
      total += current * value;
      current = 0;
    } else if (value >= 10) {  // 십, 백, 천
      if (current === 0) current = 1;
      current *= value;
    } else {  // 1-9
      current = current * 10 + value;
    }
  }

  total += current + bigUnit;

  if (total === 0) return koreanStr;  // 변환 실패시 원본 반환
  return String(total);
}

// ============================================================================
// 수치 추출
// ============================================================================

function extractNumericTokens(text) {
  if (!text) return [];

  // 한글 숫자 정규화 먼저 적용
  const normalizedText = normalizeKoreanNumber(text);

  const plainText = normalizeNumericSpacing(String(normalizedText))
    .replace(URL_PATTERN, ' ')
    .replace(/<[^>]*>/g, ' ');
  const matches = plainText.match(NUMBER_TOKEN_REGEX) || [];
  const tokens = matches
    .map(normalizeNumericToken)
    .filter(Boolean);
  return [...new Set(tokens)];
}

// ============================================================================
// 1-2. 수치 범위 허용 (±5%)
// ============================================================================

function isWithinTolerance(value, allowedValues, tolerance = 0.05) {
  const num = parseFloat(value);
  if (isNaN(num)) return false;

  for (const allowed of allowedValues) {
    const allowedNum = parseFloat(allowed);
    if (isNaN(allowedNum) || allowedNum === 0) continue;

    const diff = Math.abs(num - allowedNum) / Math.abs(allowedNum);
    if (diff <= tolerance) return true;
  }
  return false;
}

// ============================================================================
// 2-1. 파생 수치 자동 생성
// ============================================================================

function buildDerivedValues(allowlist) {
  const tokens = allowlist.tokens || [];
  const derived = {
    sums: new Set(),
    diffs: new Set(),
    ratios: new Set()
  };

  // 수치 추출 (단위 분리)
  const numbers = [];
  tokens.forEach(token => {
    const { value, unit } = splitNumericToken(token);
    const num = parseFloat(value);
    if (!isNaN(num) && num > 0) {
      numbers.push({ num, unit, original: token });
    }
  });

  // 같은 단위끼리만 합계/차이 계산
  for (let i = 0; i < numbers.length; i++) {
    for (let j = i + 1; j < numbers.length; j++) {
      const a = numbers[i];
      const b = numbers[j];

      // 같은 단위인 경우에만
      if (a.unit === b.unit) {
        const sum = a.num + b.num;
        const diff = Math.abs(a.num - b.num);
        derived.sums.add(`${sum}${a.unit}`);
        if (diff > 0) derived.diffs.add(`${diff}${a.unit}`);
      }

      // 비율 계산 (단위 무관, 분모가 0이 아닌 경우)
      if (b.num !== 0) {
        const ratio = ((a.num - b.num) / b.num * 100);
        if (Math.abs(ratio) <= 1000) {  // 1000% 이내만
          derived.ratios.add(`${Math.round(ratio)}%`);
          derived.ratios.add(`${Math.abs(Math.round(ratio))}%`);
        }
      }
      if (a.num !== 0) {
        const ratio = ((b.num - a.num) / a.num * 100);
        if (Math.abs(ratio) <= 1000) {
          derived.ratios.add(`${Math.round(ratio)}%`);
          derived.ratios.add(`${Math.abs(Math.round(ratio))}%`);
        }
      }
    }
  }

  return {
    sums: Array.from(derived.sums),
    diffs: Array.from(derived.diffs),
    ratios: Array.from(derived.ratios),
    all: [
      ...Array.from(derived.sums),
      ...Array.from(derived.diffs),
      ...Array.from(derived.ratios)
    ]
  };
}

// ============================================================================
// 3-1. LLM 시맨틱 검증
// ============================================================================

async function validateNumericContext(sentence, token, allowlist, modelName = null) {
  const allowedTokens = (allowlist.tokens || []).slice(0, 20).join(', ') || '(없음)';

  const prompt = `당신은 팩트체크 전문가입니다. 문장에서 사용된 수치가 적절한지 판단하세요.

[검증 대상 문장]
"${sentence}"

[검증 대상 수치]
${token}

[출처에서 확인된 수치 목록]
${allowedTokens}

[판단 기준]
1. ALLOWED - 출처 목록에서 직접 인용한 수치
2. DERIVED - 출처 목록의 수치들로 계산/추론 가능 (합계, 차이, 비율 등)
3. COMMON - 일반 상식 수치 (현재 연도, 공식 인구통계, 일반적 표현)
4. GOAL - 미래 목표/계획 수치 (출처 없어도 허용 가능)
5. HALLUCINATION - 출처 없는 구체적 수치 (위험)

반드시 다음 JSON 형식으로만 응답:
{"type": "ALLOWED|DERIVED|COMMON|GOAL|HALLUCINATION", "confidence": 0.0-1.0, "reason": "판단 근거"}`;

  try {
    const response = await callGenerativeModel(prompt, 1, modelName, true);
    const jsonMatch = response.match(/\{[\s\S]*\}/);
    if (jsonMatch) {
      return JSON.parse(jsonMatch[0]);
    }
    return { type: 'UNKNOWN', confidence: 0, reason: 'JSON 파싱 실패' };
  } catch (error) {
    console.warn('⚠️ [FactGuard] LLM 검증 실패:', error.message);
    return { type: 'UNKNOWN', confidence: 0, reason: error.message };
  }
}

// 위험도 등급
const RISK_LEVELS = {
  ALLOWED: 0,       // 통과
  DERIVED: 1,       // 통과 + 로그
  COMMON: 1,        // 통과 + 로그
  GOAL: 2,          // 경고 (목표는 주의 필요)
  UNKNOWN: 2,       // 판단 불가
  HALLUCINATION: 3  // 차단 권고
};

// ============================================================================
// 허용 목록 생성 (기존 + 파생 수치)
// ============================================================================

function buildFactAllowlist(sourceTexts = []) {
  const tokens = new Set();
  const values = new Set();

  sourceTexts
    .filter(Boolean)
    .forEach((sourceText) => {
      const extracted = extractNumericTokens(sourceText);
      extracted.forEach((token) => {
        tokens.add(token);
        const { value, unit } = splitNumericToken(token);
        if (value && !unit) values.add(value);
      });
    });

  const baseAllowlist = {
    tokens: Array.from(tokens),
    values: Array.from(values)
  };

  // 파생 수치 생성 및 추가
  const derived = buildDerivedValues(baseAllowlist);

  return {
    tokens: Array.from(tokens),
    values: Array.from(values),
    derived: derived.all,
    _meta: {
      sourceCount: sourceTexts.length,
      tokenCount: tokens.size,
      derivedCount: derived.all.length
    }
  };
}

// ============================================================================
// 통합 검증 함수 (개선된 버전)
// ============================================================================

function findUnsupportedNumericTokens(content, allowlist = {}, options = {}) {
  const {
    toleranceEnabled = true,
    tolerance = 0.05,
    commonKnowledgeEnabled = true
  } = options;

  const extracted = extractNumericTokens(content);
  const allowedTokens = new Set(allowlist.tokens || []);
  const allowedValues = new Set(allowlist.values || []);
  const derivedTokens = new Set(allowlist.derived || []);

  const results = [];

  extracted.forEach((token) => {
    const { value, unit } = splitNumericToken(token);
    if (!value) return;

    // 1. 단일 숫자 예외 (단위 없는 1-9)
    if (!unit && SINGLE_DIGIT_VALUES.has(value)) {
      results.push({ token, status: 'ALLOWED', reason: '단일 숫자 예외' });
      return;
    }

    // 2. 직접 매칭 (원본 허용 목록)
    if (allowedTokens.has(token)) {
      results.push({ token, status: 'ALLOWED', reason: '출처 확인' });
      return;
    }
    if (!unit && allowedValues.has(value)) {
      results.push({ token, status: 'ALLOWED', reason: '출처 확인 (값)' });
      return;
    }

    // 3. 파생 수치 매칭
    if (derivedTokens.has(token)) {
      results.push({ token, status: 'DERIVED', reason: '계산된 수치' });
      return;
    }

    // 4. 일반 상식 화이트리스트
    if (commonKnowledgeEnabled && COMMON_KNOWLEDGE.has(token)) {
      results.push({ token, status: 'COMMON', reason: '일반 상식' });
      return;
    }

    // 5. 수치 범위 허용 (±5%)
    if (toleranceEnabled && unit) {
      const allValues = [...allowedTokens, ...derivedTokens]
        .map(t => splitNumericToken(t))
        .filter(s => s.unit === unit)
        .map(s => s.value);

      if (isWithinTolerance(value, allValues, tolerance)) {
        results.push({ token, status: 'DERIVED', reason: `${tolerance * 100}% 오차 범위 내` });
        return;
      }
    }

    // 6. 미지원 수치
    results.push({ token, status: 'UNSUPPORTED', reason: '출처 미확인' });
  });

  const unsupported = results.filter(r => r.status === 'UNSUPPORTED').map(r => r.token);
  const derived = results.filter(r => r.status === 'DERIVED').map(r => r.token);
  const common = results.filter(r => r.status === 'COMMON').map(r => r.token);

  return {
    passed: unsupported.length === 0,
    tokens: extracted,
    unsupported,
    derived,
    common,
    details: results
  };
}

// ============================================================================
// 고급 검증 (LLM 포함)
// ============================================================================

async function validateWithLLM(content, allowlist = {}, options = {}) {
  const { modelName = null, maxLLMCalls = 3 } = options;

  // 1단계: 규칙 기반 검증
  const ruleBasedResult = findUnsupportedNumericTokens(content, allowlist, options);

  // 모두 통과하면 LLM 호출 불필요
  if (ruleBasedResult.passed) {
    return {
      ...ruleBasedResult,
      llmValidated: false
    };
  }

  // 2단계: 미지원 수치에 대해 LLM 검증
  const unsupportedTokens = ruleBasedResult.unsupported.slice(0, maxLLMCalls);
  const llmResults = [];

  for (const token of unsupportedTokens) {
    // 토큰이 포함된 문장 추출
    const sentences = content.split(/[.!?]/);
    const relevantSentence = sentences.find(s => s.includes(token)) || content.slice(0, 200);

    const llmResult = await validateNumericContext(
      relevantSentence.trim(),
      token,
      allowlist,
      modelName
    );

    llmResults.push({
      token,
      ...llmResult,
      riskLevel: RISK_LEVELS[llmResult.type] ?? 2
    });
  }

  // 결과 재분류
  const finalUnsupported = llmResults
    .filter(r => r.riskLevel >= 3)
    .map(r => r.token);

  const warnings = llmResults
    .filter(r => r.riskLevel === 2)
    .map(r => r.token);

  return {
    passed: finalUnsupported.length === 0,
    tokens: ruleBasedResult.tokens,
    unsupported: finalUnsupported,
    warnings,
    derived: ruleBasedResult.derived,
    common: ruleBasedResult.common,
    llmValidated: true,
    llmResults
  };
}

// ============================================================================
// Exports
// ============================================================================

module.exports = {
  // 기존 호환
  buildFactAllowlist,
  extractNumericTokens,
  findUnsupportedNumericTokens,
  normalizeNumericSpacing,
  normalizeNumericToken,
  splitNumericToken,

  // 신규 기능
  normalizeKoreanNumber,
  convertKoreanToNumber,
  isWithinTolerance,
  buildDerivedValues,
  validateNumericContext,
  validateWithLLM,

  // 상수
  COMMON_KNOWLEDGE,
  RISK_LEVELS
};
