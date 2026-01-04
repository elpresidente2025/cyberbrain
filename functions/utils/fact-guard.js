'use strict';

const SINGLE_DIGIT_VALUES = new Set(['1', '2', '3', '4', '5', '6', '7', '8', '9']);
const URL_PATTERN = /https?:\/\/\S+/gi;

const NUMBER_UNIT_TOKENS = [
  '%',
  '퍼센트',
  '프로',
  '%p',
  'p',
  'pt',
  '포인트',
  '개사',
  '개소',
  '개',
  '곳',
  '건',
  '명',
  '인',
  '가구',
  '세대',
  '년',
  '월',
  '일',
  '시',
  '분',
  '초',
  '주',
  '개월',
  '차',
  '위',
  '대',
  '호',
  '번',
  'km',
  'kg',
  'm',
  'cm',
  'mm',
  '㎞',
  '㎏',
  '㎡',
  '평',
  '원',
  '만원',
  '억원',
  '조',
  '억',
  '만',
  '천',
  '배'
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

function normalizeNumericToken(token) {
  if (!token) return '';
  let normalized = String(token).trim();
  if (!normalized) return '';
  normalized = normalized.replace(/\s+/g, '');
  normalized = normalized.replace(/,/g, '');
  normalized = normalized.replace(/[％]/g, '%');
  normalized = normalized.replace(/퍼센트|프로/gi, '%');
  normalized = normalized.replace(/%pt|%p/gi, '%p');
  normalized = normalized.replace(/포인트/gi, 'p');
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

function extractNumericTokens(text) {
  if (!text) return [];
  const plainText = String(text)
    .replace(URL_PATTERN, ' ')
    .replace(/<[^>]*>/g, ' ');
  const matches = plainText.match(NUMBER_TOKEN_REGEX) || [];
  const tokens = matches
    .map(normalizeNumericToken)
    .filter(Boolean);
  return [...new Set(tokens)];
}

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

  return {
    tokens: Array.from(tokens),
    values: Array.from(values)
  };
}

function findUnsupportedNumericTokens(content, allowlist = {}) {
  const extracted = extractNumericTokens(content);
  const allowedTokens = new Set(allowlist.tokens || []);
  const allowedValues = new Set(allowlist.values || []);
  const unsupported = [];

  extracted.forEach((token) => {
    const { value, unit } = splitNumericToken(token);
    if (!value) return;
    if (!unit && SINGLE_DIGIT_VALUES.has(value)) return;

    if (unit) {
      if (!allowedTokens.has(token)) {
        unsupported.push(token);
      }
      return;
    }

    if (!allowedValues.has(value)) {
      unsupported.push(token);
    }
  });

  return {
    passed: unsupported.length === 0,
    tokens: extracted,
    unsupported
  };
}

module.exports = {
  buildFactAllowlist,
  extractNumericTokens,
  findUnsupportedNumericTokens,
  normalizeNumericToken,
  splitNumericToken
};
