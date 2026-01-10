'use strict';

const { sanitizeElectionContent, validateElectionCompliance } = require('../election-compliance');

const DIAGNOSTIC_TAIL_MARKERS = [
  '불확실성과 추가 확인 필요 사항',
  '불확실성과 추가 확인 필요',
  '불확실성 및 추가 확인 필요',
  '불확실성',
  '추가 확인 필요 사항',
  '추가 확인 필요',
  '추가 확인',
  '추신',
  '진단 요약'
];

const SIGNATURE_MARKERS = [
  '부산의 준비된 신상품',
  '부산경제는 이재성',
  '감사합니다',
  '감사드립니다',
  '고맙습니다',
  '사랑합니다',
  '드림'
];

const CLOSING_PARAGRAPH_REGEX = /<p[^>]*>[^<]*(감사합니다|감사드립니다|고맙습니다|사랑합니다|드림)[^<]*<\/p>/gi;

const CLOSING_MARKERS = [
  '감사합니다',
  '감사드립니다',
  '고맙습니다',
  '사랑합니다',
  '드림'
];

const SUMMARY_PARAGRAPH_REGEX = /<p[^>]*data-summary=["']true["'][^>]*>[\s\S]*?<\/p>/gi;
const CONCLUSION_HEADING_REGEX = /<h[23][^>]*>[^<]*(정리|결론|요약|마무리)[^<]*<\/h[23]>/i;

function ensureParagraphTags(content) {
  if (!content) return content;
  if (/<p\b/i.test(content)) return content;

  const lines = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length === 0) return content;

  const wrapped = lines.map((line) => {
    if (/^<h[23]\b/i.test(line) || /^<ul\b/i.test(line) || /^<ol\b/i.test(line)) {
      return line;
    }
    return `<p>${line}</p>`;
  });

  return wrapped.join('\n');
}

function stripHtml(text) {
  return String(text || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

function normalizeHeadingSpaces(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

function extractQuotedTerm(text) {
  if (!text) return '';
  const match = String(text).match(/[“"‘']([^”"’']+)[”"’']/);
  return match ? match[1].trim() : '';
}

function makeCompactQuestion(phrase) {
  const cleaned = normalizeHeadingSpaces(phrase).replace(/\?$/, '').trim();
  if (!cleaned) return '';
  if (looksLikeQuestion(cleaned)) return `${cleaned}?`;
  const particle = pickTopicParticle(cleaned);
  return `${cleaned}${particle}?`;
}

function shortenHeadingText(text, maxLength = MAX_HEADING_LENGTH) {
  if (!text) return text;
  const normalized = normalizeHeadingSpaces(text);
  if (normalized.length <= maxLength) return normalized;

  const base = normalized.replace(/\?$/, '').trim();
  const withoutParen = base.replace(/\([^)]*\)/g, '').trim();
  const quoted = extractQuotedTerm(withoutParen);
  const candidates = [];

  if (quoted) {
    const trimmedQuoted = quoted.length > maxLength - 4
      ? quoted.slice(0, Math.max(1, maxLength - 4))
      : quoted;
    candidates.push(`${trimmedQuoted} 핵심`);
  }

  const splitCandidate = withoutParen.split(/,|·|:|—|–|-|및|그리고/)[0]?.trim();
  if (splitCandidate) candidates.push(splitCandidate);

  if (withoutParen) candidates.push(withoutParen);

  for (const candidate of candidates) {
    const question = makeCompactQuestion(candidate);
    if (question && question.length <= maxLength) return question;
  }

  const cut = withoutParen.slice(0, Math.max(1, maxLength - 1));
  const lastSpace = cut.lastIndexOf(' ');
  const safeCut = lastSpace > 6 ? cut.slice(0, lastSpace) : cut;
  return `${safeCut}?`;
}

function ensureHeadingLength(text) {
  // 🔧 강제 수정 로직 비활성화: AI가 생성한 소제목을 그대로 사용
  // 기존 로직은 "은은 현황은?" 같은 문법 오류를 유발함
  return normalizeHeadingSpaces(text);
}

function normalizeHeadingText(text) {
  // 🔧 강제 의문문 변환 제거: "다대포 디즈니랜드는?" 처럼 억지스러운 표현 방지
  const shortened = shortenHeadingText(text, MAX_HEADING_LENGTH);
  return ensureHeadingLength(shortened);
}

function isBannedHeading(text) {
  const cleaned = normalizeHeadingSpaces(text);
  return BANNED_HEADING_PATTERNS.some((pattern) => pattern.test(cleaned));
}

function hasEmptyHeadingSection(body) {
  const headingRegex = /<h[23][^>]*>[\s\S]*?<\/h[23]>/gi;
  let match;
  while ((match = headingRegex.exec(body)) !== null) {
    const after = body.slice(match.index + match[0].length);
    const nextContent = after.match(/<p[^>]*>|<ul[^>]*>|<ol[^>]*>|<h[23][^>]*>/i);
    if (!nextContent) return true;
    if (/^<h[23]/i.test(nextContent[0])) return true;
  }
  return false;
}

function hasWeakHeadings(body) {
  const headings = [];
  body.replace(/<h[23][^>]*>([\s\S]*?)<\/h[23]>/gi, (_match, inner) => {
    headings.push(stripHtml(inner));
    return _match;
  });

  if (headings.some((heading) => !heading.trim())) return true;
  if (headings.some((heading) => heading.length > MAX_HEADING_LENGTH)) return true;
  // 일반 소제목: 12자 미만이면 weak
  if (headings.some((heading) => !isConclusionHeadingText(heading) && heading.length < MIN_HEADING_LENGTH)) return true;
  // 결론 소제목: 6자 미만이면 weak ("정리"=2자 금지)
  if (headings.some((heading) => isConclusionHeadingText(heading) && heading.length < MIN_CONCLUSION_HEADING_LENGTH)) return true;
  if (headings.some((heading) => isBannedHeading(heading))) return true;
  // 🔧 불완전한 질문형 감지 (예: "다대포 디즈니랜드는?", "부산은?")
  if (headings.some((heading) => isIncompleteQuestion(heading))) return true;
  if (hasEmptyHeadingSection(body)) return true;
  return false;
}

function stripEmptyHeadingSections(content) {
  if (!content) return content;
  return content.replace(/<h([23])[^>]*>[\s\S]*?<\/h\1>\s*(?=<h[23][^>]*>|$)/gi, '');
}

const HEADING_TAG_REGEX = /<h[23][^>]*>[\s\S]*?<\/h[23]>/gi;
const MIN_HEADING_LENGTH = 12;
const MAX_HEADING_LENGTH = 25;
const MIN_CONCLUSION_HEADING_LENGTH = 6;  // 결론 소제목 최소 길이 ("정리"=2자 금지)
const BANNED_HEADING_PATTERNS = [
  /^무엇을 나누고 싶은가/i,
  /^생각의 핵심은 무엇인가/i,
  /^함께 생각할 점은 무엇인가/i,
  /^현안은 무엇인가/i,
  /^핵심 쟁점은 무엇인가/i,
  /^영향과 과제는 무엇인가/i
];

/**
 * 불완전한 질문형 소제목 감지
 * - "~은?", "~는?" 형태로 끝나면서 구체적 질문어가 없는 경우
 * - 예: "다대포 디즈니랜드는?", "부산은?", "이스포츠 박물관은?"
 */
function isIncompleteQuestion(text) {
  if (!text) return false;
  const cleaned = text.trim();
  // "~은?", "~는?" 형태 (물음표 있든 없든)
  if (/[은는]\??$/.test(cleaned)) {
    // 구체적 질문어가 있으면 OK (무엇, 어떻게, 왜 등)
    if (/무엇|어떻게|왜|어디|언제|누가|얼마|어떤/.test(cleaned)) return false;
    return true;  // 구체적 질문어 없이 "~은/는?"만 있으면 불완전
  }
  return false;
}

const REPEATED_ENDINGS = [
  { ending: '합니다', replacements: ['하겠습니다', '할 것입니다'] },
  { ending: '됩니다', replacements: ['될 것입니다', '되어야 합니다'] },
  { ending: '입니다', replacements: ['일 것입니다', '이라고 확신합니다'] },
  { ending: '있습니다', replacements: ['있을 것입니다', '있다고 자부합니다'] },
  { ending: '없습니다', replacements: ['없을 것입니다', '없다고 생각합니다'] }
];

// 🆕 이미 변환된 어미 패턴 - 이 어미로 끝나면 재변환하지 않음
const ALREADY_TRANSFORMED_ENDINGS = [
  '것입니다',
  '겠습니다',
  '확신합니다',
  '자부합니다',
  '생각합니다',
  '것일 것입니다',
  '있을 것입니다',
  '없을 것입니다',
  '될 것입니다',
  '할 것입니다'
];

const SORTED_REPEATED_ENDINGS = [...REPEATED_ENDINGS].sort(
  (a, b) => b.ending.length - a.ending.length
);
const TRAILING_PUNCTUATION_REGEX = /([.!?]+)?(["'”’)\]]*)$/;

function stripMarkdownEmphasis(content) {
  if (!content) return content;
  return content.replace(/\*\*/g, '');
}

function splitPlainSentences(text) {
  if (!text) return [];
  // 단순 마침표 분리가 아닌, 소수점(0.7)을 보호하는 정교한 분리 로직
  // 1. 숫자가 아닌 문자 뒤의 마침표
  // 2. 또는 문장 부호(!?)
  // 3. 또는 소수점이 아닌 마침표
  // 이를 구현하기 위해 "숫자+점+숫자" 패턴을 제외하고 매칭하거나,
  // 더 안전하게는 세그먼트 매칭을 사용

  // "어떤 문자들의 나열(소수점 포함 가능)" + "종결 부호(.!?)" + "공백 혹은 끝"
  // 정규식 설명:
  // ([^.!?]|(?<=\d)\.(?=\d))+  : 마침표/!/?가 아니거나, 숫자 사이의 점(소수점)인 것들의 반복
  // ([.!?]+|$)                : 그리고 문장 부호 덩어리 또는 문자열 끝
  const matches = String(text).match(/([^.!?]|(?<=\d)\.(?=\d))+([.!?]+|$)/g);

  if (!matches) return [];
  return matches.map((s) => s.trim()).filter(Boolean);
}

function findEndingRule(text) {
  if (!text) return null;
  const trimmed = String(text).replace(/\s+$/g, '');
  if (!trimmed) return null;

  // 🆕 이미 변환된 어미로 끝나면 재변환하지 않음 (이중 변환 방지)
  for (const transformed of ALREADY_TRANSFORMED_ENDINGS) {
    if (trimmed.endsWith(transformed)) {
      return null;
    }
  }

  for (const rule of SORTED_REPEATED_ENDINGS) {
    if (trimmed.endsWith(rule.ending)) {
      return rule;
    }
  }
  return null;
}

function parseSentenceEnding(sentence) {
  const normalized = String(sentence || '').replace(/\s+/g, ' ').trim();
  if (!normalized) return null;
  const match = normalized.match(TRAILING_PUNCTUATION_REGEX);
  const punctuation = match ? (match[1] || '') : '';
  const trailing = match ? (match[2] || '') : '';
  const trimLength = punctuation.length + trailing.length;
  const base = trimLength > 0 ? normalized.slice(0, -trimLength) : normalized;
  const trimmedBase = base.replace(/\s+$/g, '');
  const rule = findEndingRule(trimmedBase);
  if (!rule) return null;
  const prefix = trimmedBase.slice(0, trimmedBase.length - rule.ending.length);
  return {
    prefix,
    rule,
    punctuation,
    trailing
  };
}

function applyEndingReplacement(parsed, replacement) {
  if (!parsed || !replacement) return null;
  const { prefix, punctuation, trailing } = parsed;
  return `${prefix}${replacement}${punctuation}${trailing}`.replace(/\s+/g, ' ').trim();
}

function dedupeRepeatedEndings(sentences) {
  let lastEnding = null;
  const replacementIndex = new Map();
  return sentences.map((sentence) => {
    const parsed = parseSentenceEnding(sentence);
    if (!parsed) {
      lastEnding = null;
      return String(sentence).replace(/\s+/g, ' ').trim();
    }

    const { rule } = parsed;
    if (lastEnding === rule.ending && rule.replacements && rule.replacements.length > 0) {
      const index = replacementIndex.get(rule.ending) || 0;
      const replacement = rule.replacements[index % rule.replacements.length];
      replacementIndex.set(rule.ending, index + 1);
      const updated = applyEndingReplacement(parsed, replacement);
      lastEnding = null;
      return updated || String(sentence).replace(/\s+/g, ' ').trim();
    }

    lastEnding = rule.ending;
    return String(sentence).replace(/\s+/g, ' ').trim();
  });
}

function normalizeParagraphEndings(content) {
  if (!content) return content;
  return content.replace(/<p[^>]*>[\s\S]*?<\/p>/gi, (match) => {
    const openTagMatch = match.match(/^<p[^>]*>/i);
    const openTag = openTagMatch ? openTagMatch[0] : '<p>';
    const inner = match.replace(/^<p[^>]*>/i, '').replace(/<\/p>$/i, '');
    if (/<[^>]+>/.test(inner)) {
      return match;
    }
    const plain = inner.replace(/\s+/g, ' ').trim();
    if (!plain) return match;
    const sentences = splitPlainSentences(plain);
    const updated = dedupeRepeatedEndings(sentences).join(' ');
    if (!updated || updated == plain) return match;
    return `${openTag}${updated}</p>`;
  });
}

// 🆕 비문 패턴 중앙 집중 처리 (기존 3곳에서 통합)
const GRAMMATICAL_ERROR_PATTERNS = [
  { pattern: /것이라는 점입니다/g, replacement: '것입니다' },
  { pattern: /거라는 점입니다/g, replacement: '것입니다' },
  { pattern: /한다는 점입니다/g, replacement: '합니다' },
  { pattern: /하다는 점입니다/g, replacement: '합니다' },
  { pattern: /된다는 점입니다/g, replacement: '됩니다' },
  { pattern: /있다는 점입니다/g, replacement: '있습니다' },
  { pattern: /없다는 점입니다/g, replacement: '없습니다' },
  { pattern: /이라는 점입니다/g, replacement: '입니다' },
  { pattern: /라는 점입니다/g, replacement: '입니다' },
  // 🆕 이중 변환 복원 (것일 것입니다 → 것입니다)
  { pattern: /것일 것입니다/g, replacement: '것입니다' },
  { pattern: /있을 것일 것입니다/g, replacement: '있을 것입니다' },
  { pattern: /없을 것일 것입니다/g, replacement: '없을 것입니다' },
  { pattern: /될 것일 것입니다/g, replacement: '될 것입니다' },
  { pattern: /할 것일 것입니다/g, replacement: '할 것입니다' }
];

function removeGrammaticalErrors(content) {
  if (!content) return content;
  let fixed = content;
  for (const { pattern, replacement } of GRAMMATICAL_ERROR_PATTERNS) {
    fixed = fixed.replace(pattern, replacement);
  }
  return fixed;
}

function cleanupPostContent(content) {
  if (!content) return content;
  // 🆕 [1단계] 비문 패턴 제거 (가장 먼저 실행)
  let updated = removeGrammaticalErrors(content);
  updated = stripMarkdownEmphasis(updated);
  updated = normalizeParagraphEndings(updated);
  updated = stripEmptyHeadingSections(updated);

  // 🔧 [FIX] 소수점 뒤 공백 제거 (0. 7% -> 0.7%)
  // splitPlainSentences가 소수점을 문장 끝으로 오인하여 분리 후 join(' ')을 할 때 발생하는 문제 해결
  updated = updated.replace(/(\d)\.\s+(\d)/g, '$1.$2');

  return updated;
}
const CONTENT_BLOCK_REGEX = /<p[^>]*>[\s\S]*?<\/p>|<ul[^>]*>[\s\S]*?<\/ul>|<ol[^>]*>[\s\S]*?<\/ol>/gi;

function getBodyHeadingTexts(category, subCategory, count) {
  const presets = {
    'current-affairs': [
      '현안은 무엇인가?',
      '핵심 쟁점은 무엇인가?',
      '영향과 과제는 무엇인가?'
    ],
    'policy-proposal': [
      '왜 필요한가?',
      '핵심 방향은 무엇인가?',
      '기대 효과는 무엇인가?'
    ],
    'activity-report': [
      '무엇을 했나?',
      '현장의 핵심은 무엇인가?',
      '의미와 과제는 무엇인가?'
    ],
    'daily-communication': [
      '무엇을 나누고 싶은가?',
      '생각의 핵심은 무엇인가?',
      '함께 생각할 점은 무엇인가?'
    ]
  };
  const base = presets[category] || [
    '핵심은 무엇인가?',
    '왜 중요한가?',
    '어떤 과제가 남는가?'
  ];
  const safeCount = Math.max(1, count || 1);
  const result = [];
  for (let i = 0; i < safeCount; i += 1) {
    result.push(base[i % base.length]);
  }
  return result;
}

function getConclusionHeadingText(category, subCategory) {
  if (category === 'activity-report') {
    return '앞으로의 다짐';
  }
  if (category === 'daily-communication') {
    return '함께 만들어갈 미래';
  }
  if (category === 'policy-proposal') {
    return '기대하는 변화';
  }
  if (category === 'current-affairs') {
    return '앞으로의 과제';
  }
  return '마무리 인사';  // 기본값 (6자 이상)
}

function isConclusionHeadingText(text) {
  // 기존 단어 + 새로 추가된 결론 소제목 패턴
  return /(정리|결론|마무리|요약|다짐|미래|변화|과제|인사)/.test(text || '');
}

function looksLikeQuestion(text) {
  return /(무엇|어떤|어떻게|왜|언제|누가|인가|인가요|까요|할까|해야할까|어떤가)\s*\??$/.test(text || '');
}

function isGreetingBlock(text) {
  if (!text) return false;
  const normalized = String(text).replace(/\s+/g, ' ').trim();
  if (!normalized) return false;
  return /^(존경하는|사랑하는|안녕하세요|안녕하십니까)/.test(normalized)
    || normalized.includes('시민 여러분')
    || normalized.includes('주민 여러분')
    || normalized.includes('인사드립니다')
    || normalized.includes('뼛속까지');
}

function isIdentityBlock(text, options = {}) {
  if (!text) return false;
  const normalized = String(text).replace(/\s+/g, ' ').trim();
  if (!normalized) return false;
  const fullName = (options.fullName || '').trim();
  if (fullName && normalized.includes(fullName)) return true;
  if (/(지역위원장|위원장|국회의원|시의원|구의원|구청장|시장|도지사|의원)/.test(normalized)) return true;
  return normalized.startsWith('저는 ') || normalized.includes('입니다');
}

function getIntroBlockCount(blocks, options = {}) {
  if (!blocks || blocks.length === 0) return 0;
  if (blocks.length === 1) return 1;
  const firstPlain = stripHtml(blocks[0]);
  const secondPlain = stripHtml(blocks[1]);
  if (isGreetingBlock(firstPlain) && isIdentityBlock(secondPlain, options)) {
    return 2;
  }
  return 1;
}

function pickTopicParticle(text) {
  if (!text) return '은';
  const trimmed = String(text).trim();
  if (!trimmed) return '은';
  for (let i = trimmed.length - 1; i >= 0; i -= 1) {
    const code = trimmed.charCodeAt(i);
    if (code >= 0xac00 && code <= 0xd7a3) {
      const jong = (code - 0xac00) % 28;
      return jong === 0 ? '는' : '은';
    }
    if (/[A-Za-z0-9]/.test(trimmed[i])) {
      return '은';
    }
  }
  return '은';
}

function toQuestionHeading(text) {
  if (!text) return text;
  const cleaned = String(text).replace(/\s+/g, ' ').trim();
  if (!cleaned) return cleaned;
  if (isConclusionHeadingText(cleaned)) return cleaned;
  if (cleaned.endsWith('?')) return cleaned;

  const isShort = cleaned.length <= 8;
  const hasNumber = /\d/.test(cleaned);
  if (isShort && !hasNumber) {
    if (/현안|이슈|사안/.test(cleaned)) return '현안은 무엇인가?';
    if (/핵심|쟁점/.test(cleaned)) return '핵심 쟁점은 무엇인가?';
    if (/영향|과제/.test(cleaned)) return '영향과 과제는 무엇인가?';
    if (/진단/.test(cleaned)) return '핵심 진단은 무엇인가?';
    if (/배경/.test(cleaned)) return '배경은 무엇인가?';
    if (/방향|전략/.test(cleaned)) return '핵심 방향은 무엇인가?';
    if (/효과|기대/.test(cleaned)) return '기대 효과는 무엇인가?';
    if (/활동|실적/.test(cleaned)) return '무엇을 했나?';
    if (/의미/.test(cleaned)) return '의미와 과제는 무엇인가?';
  }

  if (looksLikeQuestion(cleaned)) return `${cleaned}?`;
  const particle = pickTopicParticle(cleaned);
  return `${cleaned}${particle} 무엇인가?`;
}

function normalizeExistingHeadings(body) {
  if (!body) return body;
  return body.replace(/<h([23])([^>]*)>([\s\S]*?)<\/h\1>/gi, (match, level, attrs, inner) => {
    const plain = String(inner).replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    if (!plain) return match;
    const normalized = normalizeHeadingText(plain);
    return `<h${level}${attrs}>${normalized}</h${level}>`;
  });
}

function splitBlocksIntoSections(blocks, sectionCount) {
  const safeCount = Math.max(1, Math.min(sectionCount, blocks.length));
  const sections = [];
  let start = 0;
  for (let i = 0; i < safeCount; i += 1) {
    const remaining = blocks.length - start;
    const remainingSections = safeCount - i;
    const size = Math.ceil(remaining / remainingSections);
    sections.push(blocks.slice(start, start + size));
    start += size;
  }
  return sections;
}

function splitContentBySignature(content) {
  if (!content) return { body: '', tail: '' };
  const signatureIndex = findLastIndexOfAny(content, SIGNATURE_MARKERS);
  if (signatureIndex === -1) return { body: content, tail: '' };

  const paragraphStart = content.lastIndexOf('<p', signatureIndex);
  if (paragraphStart !== -1) {
    return {
      body: content.slice(0, paragraphStart).trim(),
      tail: content.slice(paragraphStart).trim()
    };
  }

  return {
    body: content.slice(0, signatureIndex).trim(),
    tail: content.slice(signatureIndex).trim()
  };
}

function joinContent(body, tail) {
  if (!tail) return body;
  if (!body) return tail;
  return `${body}\n${tail}`.replace(/\n{3,}/g, '\n\n');
}

function ensureSectionHeadings(content, options = {}) {
  if (!content) return content;
  const { body, tail } = splitContentBySignature(content);
  const normalizedBody = normalizeExistingHeadings(body);
  const headingCount = (normalizedBody.match(/<h[23][^>]*>/gi) || []).length;
  const hasConclusionHeading = /<h[23][^>]*>[^<]*(정리|결론|마무리|요약)[^<]*<\/h[23]>/i.test(normalizedBody);
  const forceRebuild = Number.isInteger(options.introBlockCount) && options.introBlockCount > 0;
  if (headingCount >= 3 && hasConclusionHeading && !forceRebuild && !hasWeakHeadings(normalizedBody)) {
    return joinContent(normalizedBody, tail);
  }

  const bodyWithoutHeadings = normalizedBody.replace(HEADING_TAG_REGEX, '');
  const blocks = (bodyWithoutHeadings.match(CONTENT_BLOCK_REGEX) || [])
    .filter((block) => stripHtml(block).length > 0);
  if (blocks.length < 2) {
    return joinContent(bodyWithoutHeadings.trim() || body, tail);
  }

  const providedIntroCount = Number.isInteger(options.introBlockCount)
    && options.introBlockCount > 0
    ? options.introBlockCount
    : null;
  const rawIntroCount = providedIntroCount || getIntroBlockCount(blocks, options) || 1;
  const maxIntroCount = Math.max(1, blocks.length - 2);
  const introCount = Math.min(rawIntroCount, maxIntroCount);
  const introBlocks = blocks.slice(0, introCount);
  const conclusionBlockCount = 1;
  const conclusionBlocks = blocks.slice(blocks.length - conclusionBlockCount);
  const bodyBlocks = blocks.slice(introCount, blocks.length - conclusionBlockCount);

  let desiredBodyHeadings = bodyBlocks.length >= 6 ? 3 : 2;
  if (bodyBlocks.length < desiredBodyHeadings) {
    desiredBodyHeadings = Math.max(1, bodyBlocks.length);
  }

  const providedHeadings = Array.isArray(options.bodyHeadings)
    ? options.bodyHeadings.map((heading) => normalizeHeadingText(heading)).filter(Boolean)
    : [];
  let bodyHeadings = [];
  if (providedHeadings.length > 0) {
    bodyHeadings = [...providedHeadings];
    if (bodyHeadings.length > desiredBodyHeadings) {
      bodyHeadings = bodyHeadings.slice(0, desiredBodyHeadings);
    } else if (bodyHeadings.length < desiredBodyHeadings) {
      const fallbackHeadings = getBodyHeadingTexts(options.category, options.subCategory, desiredBodyHeadings);
      for (let i = bodyHeadings.length; i < desiredBodyHeadings; i += 1) {
        const fallback = fallbackHeadings[i] || fallbackHeadings[fallbackHeadings.length - 1];
        bodyHeadings.push(normalizeHeadingText(fallback));
      }
    }
  } else {
    bodyHeadings = getBodyHeadingTexts(options.category, options.subCategory, desiredBodyHeadings)
      .map((heading) => normalizeHeadingText(heading));
  }
  const sections = splitBlocksIntoSections(bodyBlocks, desiredBodyHeadings);

  let rebuilt = introBlocks.join('\n');
  sections.forEach((sectionBlocks, index) => {
    if (!sectionBlocks || sectionBlocks.length === 0) return;
    rebuilt += `
<h2>${bodyHeadings[index]}</h2>
${sectionBlocks.join('\n')}`;
  });

  if (conclusionBlocks.length > 0) {
    const conclusionHeading = getConclusionHeadingText(options.category, options.subCategory);
    rebuilt += `
<h2>${conclusionHeading}</h2>
${conclusionBlocks.join('\n')}`;
  }

  return joinContent(rebuilt, tail);
}

function findLastIndexOfAny(text, markers) {
  return markers.reduce((maxIndex, marker) => {
    const index = text.lastIndexOf(marker);
    return index > maxIndex ? index : maxIndex;
  }, -1);
}

function findFirstIndexOfAny(text, markers, startIndex = 0) {
  let foundIndex = -1;
  markers.forEach((marker) => {
    const index = text.indexOf(marker, startIndex);
    if (index !== -1 && (foundIndex === -1 || index < foundIndex)) {
      foundIndex = index;
    }
  });
  return foundIndex;
}

function trimFromIndex(text, cutIndex) {
  if (cutIndex < 0) return text;
  const paragraphStart = text.lastIndexOf('<p', cutIndex);
  if (paragraphStart !== -1) {
    const tagEnd = text.indexOf('>', paragraphStart);
    if (tagEnd !== -1 && tagEnd < cutIndex) {
      return text.slice(0, paragraphStart).trim();
    }
  }
  return text.slice(0, cutIndex).trim();
}

function trimTrailingDiagnostics(content, options = {}) {
  if (!content) return content;
  const allowDiagnosticTail = options.allowDiagnosticTail === true;
  const signatureIndex = findLastIndexOfAny(content, SIGNATURE_MARKERS);
  if (signatureIndex !== -1) {
    const tail = content.slice(signatureIndex);
    const closeTagMatch = tail.match(/<\/p>|<\/div>|<\/section>|<\/article>/i);
    let cutIndex = signatureIndex;
    if (closeTagMatch) {
      cutIndex += closeTagMatch.index + closeTagMatch[0].length;
    } else {
      const lineBreakIndex = tail.search(/[\r\n]/);
      cutIndex = lineBreakIndex === -1 ? content.length : signatureIndex + lineBreakIndex;
    }
    return content.slice(0, cutIndex).trim();
  }

  if (!allowDiagnosticTail) {
    const startIndex = Math.floor(content.length * 0.65);
    const tailIndex = findFirstIndexOfAny(content, DIAGNOSTIC_TAIL_MARKERS, startIndex);
    if (tailIndex !== -1) {
      return trimFromIndex(content, tailIndex);
    }
  }

  return content;
}

function trimAfterClosing(content) {
  if (!content) return content;
  CLOSING_PARAGRAPH_REGEX.lastIndex = 0;
  let lastMatch = null;
  let match;
  while ((match = CLOSING_PARAGRAPH_REGEX.exec(content)) !== null) {
    lastMatch = match;
  }
  if (lastMatch && typeof lastMatch.index === 'number') {
    return content.slice(0, lastMatch.index + lastMatch[0].length).trim();
  }

  let lastIndex = -1;
  let lastMarker = '';
  CLOSING_MARKERS.forEach((marker) => {
    const index = content.lastIndexOf(marker);
    if (index > lastIndex) {
      lastIndex = index;
      lastMarker = marker;
    }
  });

  if (lastIndex !== -1) {
    const endIndex = lastIndex + lastMarker.length;
    const lineEnd = content.indexOf('\n', endIndex);
    const cutIndex = lineEnd === -1 ? endIndex : lineEnd;
    return content.slice(0, cutIndex).trim();
  }

  return content;
}

function moveSummaryToConclusionStart(content) {
  if (!content) return content;
  const { body, tail } = splitContentBySignature(content);
  const summaryMatches = body.match(SUMMARY_PARAGRAPH_REGEX);
  if (!summaryMatches || summaryMatches.length === 0) {
    return content;
  }

  let cleanedBody = body.replace(SUMMARY_PARAGRAPH_REGEX, '').replace(/\n{3,}/g, '\n\n').trim();
  const headingMatch = cleanedBody.match(CONCLUSION_HEADING_REGEX);
  if (headingMatch) {
    const insertIndex = cleanedBody.indexOf(headingMatch[0]) + headingMatch[0].length;
    cleanedBody = `${cleanedBody.slice(0, insertIndex)}\n${summaryMatches.join('\n')}\n${cleanedBody.slice(insertIndex)}`
      .replace(/\n{3,}/g, '\n\n');
  } else {
    cleanedBody = `${cleanedBody}\n${summaryMatches.join('\n')}`.trim();
  }

  return joinContent(cleanedBody, tail);
}




function hashString(text) {
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) | 0;
  }
  return hash;
}

function shouldReplaceByProbability(seed, index, probability) {
  if (probability <= 0) return false;
  if (probability >= 1) return true;
  const value = Math.abs(seed + index * 101) % 100;
  return value < Math.round(probability * 100);
}

function pickReplacement(list, seed, index) {
  if (!list || list.length === 0) return '';
  const position = Math.abs(seed + index * 31) % list.length;
  return list[position];
}



/**
 * AI가 생성한 원고에 대한 후처리 및 보정
 * @param {Object} params
 * @param {string} params.content - 생성된 원고 내용
 * @param {string} params.fullName - 작성자 이름
 * @param {string} params.fullRegion - 지역명
 * @param {string} params.currentStatus - 현재 상태 (현역/예비/준비)
 * @param {Object} params.userProfile - 사용자 프로필
 * @param {Object} params.config - 상태별 설정
 * @param {string} params.customTitle - 사용자 지정 직위 (선택)
 * @param {string} params.displayTitle - 표시할 직위 (customTitle 또는 config.title)
 * @param {boolean} params.isCurrentLawmaker - 현역 의원 여부
 * @returns {string} 수정된 원고 내용
 */
function processGeneratedContent({
  content,
  fullName,
  fullRegion,
  currentStatus,
  userProfile,
  config,
  customTitle,
  displayTitle,
  isCurrentLawmaker,
  category,
  subCategory
}) {
  console.log('🔩 후처리 시작 - 필수 정보 강제 삽입');

  if (!content) return content;

  let fixedContent = ensureParagraphTags(content);
  fixedContent = ensureSectionHeadings(fixedContent, { category, subCategory });

  // 🔥 원외 인사의 경우 강력한 "의원" 표현 제거
  if (isCurrentLawmaker === false) {
    console.log('⚠️ 원외 인사 감지 - "의원" 및 "지역구" 표현 강력 제거 시작');

    // "국회의원", "지역구 국회의원" 등 제거
    fixedContent = fixedContent.replace(/국회\s*의원/g, fullName);
    fixedContent = fixedContent.replace(/지역구\s*국회\s*의원/g, fullName);
    fixedContent = fixedContent.replace(/지역구\s*의원/g, fullName);

    // "의원으로서" → "저로서" 또는 customTitle
    const asPhrase = customTitle ? `${customTitle}으로서` : '저로서';
    fixedContent = fixedContent.replace(/의원으로서/g, asPhrase);

    // "의원입니다" → 이름
    fixedContent = fixedContent.replace(/의원입니다/g, `${fullName}입니다`);

    // "의원의 한 사람으로서" → "시민의 한 사람으로서"
    fixedContent = fixedContent.replace(/의원의 한 사람으로서/g, '시민의 한 사람으로서');

    // "의정활동" → "활동"
    fixedContent = fixedContent.replace(/의정활동/g, '활동');

    // 🔥 "지역구" 표현 제거 (국회의원 전용 용어)
    // "지역구 발전" → "부산 발전" 또는 "지역 발전"
    const regionName = fullRegion || '지역';
    fixedContent = fixedContent.replace(/지역구\s*발전/g, `${regionName} 발전`);
    fixedContent = fixedContent.replace(/지역구\s*주민/g, `${regionName} 주민`);
    fixedContent = fixedContent.replace(/지역구\s*현안/g, `${regionName} 현안`);
    fixedContent = fixedContent.replace(/지역구를/g, `${regionName}을`);
    fixedContent = fixedContent.replace(/지역구의/g, `${regionName}의`);
    fixedContent = fixedContent.replace(/지역구에/g, `${regionName}에`);

    console.log('✅ 원외 인사 "의원" 및 "지역구" 표현 제거 완료');
  }

  // 1. 기본적인 호칭 수정
  // '준비' 상태는 이름만 사용하므로 직위 표현을 제거
  if (currentStatus === '준비') {
    fixedContent = fixedContent.replace(/의원입니다/g, `${fullName}입니다`);
    fixedContent = fixedContent.replace(/의원으로서/g, customTitle ? `${customTitle}으로서` : '저로서');
    fixedContent = fixedContent.replace(/후보입니다/g, `${fullName}입니다`);
    fixedContent = fixedContent.replace(/후보으로서/g, customTitle ? `${customTitle}으로서` : '저로서');
    fixedContent = fixedContent.replace(/예비후보입니다/g, `${fullName}입니다`);
    fixedContent = fixedContent.replace(/예비후보으로서/g, customTitle ? `${customTitle}으로서` : '저로서');
  } else {
    fixedContent = fixedContent.replace(/의원입니다/g, `${fullName}입니다`);
    fixedContent = fixedContent.replace(/의원으로서/g, `${displayTitle}으로서`);
    fixedContent = fixedContent.replace(/국회 의원/g, displayTitle);
    fixedContent = fixedContent.replace(/\s의원\s/g, ` ${displayTitle} `);
  }

  // 은퇴 상태 특별 수정
  if (currentStatus === '은퇴') {
    fixedContent = applyRetirementCorrections(fixedContent, fullName, userProfile);
  }

  // 2. 인사말에 이름 삽입
  if (!fixedContent.includes(`저 ${fullName}`)) {
    fixedContent = fixedContent.replace(/(<p>)안녕하세요/g, `$1안녕하세요 ${fullName}입니다`);
  }
  fixedContent = fixedContent.replace(/(<p>)안녕 ([^가-힣])/g, `$1안녕 ${fullName} $2`);

  // 3. 인사말 지역정보 수정
  if (fullRegion) {
    fixedContent = fixedContent.replace(/우리 지역의/g, `${fullRegion}의`);
    fixedContent = fixedContent.replace(/우리 지역에/g, `${fullRegion}에`);
    fixedContent = fixedContent.replace(/지역의/g, `${fullRegion} `);
    fixedContent = fixedContent.replace(/\s를\s/g, ` ${fullRegion}를`);
    fixedContent = fixedContent.replace(/\s의 발전을/g, ` ${fullRegion}의 발전을`);
    fixedContent = fixedContent.replace(/에서의/g, `${fullRegion}에서의`);
    fixedContent = fixedContent.replace(/,\s*의\s/g, `, ${fullRegion}의`);
    fixedContent = fixedContent.replace(/\s*에서\s*인/g, ` ${fullRegion}에서 인구`);
  }

  // 4. 시작 문장에 호칭 포함 체크
  if (!fixedContent.includes(`${fullName}입니다`)) {
    // fullRegion은 이미 "민"이 붙어있으므로 "도민" 하드코딩 제거
    const greeting = fullRegion ? `존경하는 ${fullRegion} 여러분` : '존경하는 여러분';
    fixedContent = fixedContent.replace(/^<p>[^<]*?<\/p>/,
      `<p>${greeting}, ${fullName}입니다.</p>`);
  }

  // 5. 마지막에 서명 수정
  if (currentStatus !== '은퇴') {
    fixedContent = fixedContent.replace(/의원 올림/g, `${fullName} 드림`);
    fixedContent = fixedContent.replace(/의원 드림/g, `${fullName} 드림`);

    if (!fixedContent.includes(`${fullName} 드림`) && !fixedContent.includes(`${fullName} 올림`)) {
      fixedContent = fixedContent.replace(/<\/p>$/, `</p><p>${fullName} 드림</p>`);
    }
  }

  // 6. 기타 패턴 수정
  fixedContent = fixedContent.replace(/도민 여러분 의원입니다/g, `도민 여러분 ${fullName}입니다`);
  fixedContent = fixedContent.replace(/여러분께, 의원입니다/g, `여러분께, ${fullName}입니다`);

  // 불완전한 문장 수정
  fixedContent = fixedContent.replace(/행복하겠습니다/g, '행복을 높이겠습니다');
  fixedContent = fixedContent.replace(/도민들의 목소리재현/g, '도민들의 목소리를 듣고 있재현');
  fixedContent = fixedContent.replace(/모두의 소통 미래를/g, '모두의 소통을 채워가며 미래를');

  // 이상한 텍스트 조각 수정
  fixedContent = fixedContent.replace(/양양군시민들이 행복이/g, '양양군시민 여러분을 위해 행복이');
  fixedContent = fixedContent.replace(/불여해서/g, '제 여러분께');

  // 최종 중복 이름 패턴 제거
  fixedContent = removeDuplicateNames(fixedContent, fullName);

  // 🛡️ 선거법 준수 검증 및 치환 (3차 방어)
  if (currentStatus) {
    console.log(`🛡️ 선거법 준수 검사 시작 (상태: ${currentStatus})`);

    // 1. 먼저 검증하여 금지 표현 감지
    const validationResult = validateElectionCompliance(fixedContent, currentStatus);

    if (!validationResult.valid) {
      console.warn(`⚠️ 선거법 위반 표현 감지됨 (${validationResult.violationCount}개):`);
      for (const v of validationResult.violations) {
        console.warn(`   - [${v.category}] "${v.matches.join('", "')}" (${v.count}회)`);
      }
    }

    // 2. 치환 가능한 표현 자동 수정
    const electionResult = sanitizeElectionContent(fixedContent, currentStatus);

    if (electionResult.replacementsMade > 0) {
      console.log(`🔧 선거법 위반 표현 ${electionResult.replacementsMade}개 자동 수정됨`);
      fixedContent = electionResult.sanitizedContent;
    }

    // 3. 수정 후에도 남은 위반 표현 재검증
    const remainingResult = validateElectionCompliance(fixedContent, currentStatus);

    if (!remainingResult.valid) {
      console.warn(`⚠️ 자동 수정 불가한 위반 표현 ${remainingResult.violationCount}개 남음 - AI 프롬프트 개선 필요:`);
      for (const v of remainingResult.violations) {
        console.warn(`   - [${v.category}] "${v.matches.join('", "')}"`);
      }
    } else {
      console.log('✅ 선거법 준수 검사 통과');
    }
  }

  const allowDiagnosticTail = category === 'current-affairs'
    && subCategory === 'current_affairs_diagnosis';
  fixedContent = trimTrailingDiagnostics(fixedContent, { allowDiagnosticTail });
  fixedContent = trimAfterClosing(fixedContent);

  console.log('✅ 후처리 완료 - 필수 정보 삽입됨');
  return fixedContent;
}

/**
 * 은퇴 상태 특별 수정
 */
function applyRetirementCorrections(content, fullName, userProfile) {
  let fixed = content;

  // 모든 호칭 제거
  fixed = fixed.replace(/은퇴예비후보/g, '저');
  fixed = fixed.replace(/예비후보/g, '저');
  fixed = fixed.replace(/의원으로서/g, '저로서');
  fixed = fixed.replace(/은퇴.*예비후보.*로서/g, '저로서');

  // 공약/정치 활동 표현 제거
  fixed = fixed.replace(/의정활동을 통해/g, '제 경험과의 소통을 통해');
  fixed = fixed.replace(/현역 의원으로서/g, '저로서');
  fixed = fixed.replace(/성과를/g, '경험을');
  fixed = fixed.replace(/실적을/g, '활동을');
  fixed = fixed.replace(/추진하겠습니다/g, '생각합니다');
  fixed = fixed.replace(/기여하겠습니다/g, '관심을 갖고 있습니다');

  // 3인칭을 1인칭 변경
  const sentences = fixed.split('</p>');
  for (let i = 1; i < sentences.length; i++) {
    sentences[i] = sentences[i].replace(new RegExp(`${fullName}는`, 'g'), '저는');
    sentences[i] = sentences[i].replace(new RegExp(`${fullName}가`, 'g'), '제가');
    sentences[i] = sentences[i].replace(new RegExp(`${fullName}를`, 'g'), '저를');
    sentences[i] = sentences[i].replace(new RegExp(`${fullName}의`, 'g'), '저의');
  }
  fixed = sentences.join('</p>');

  // 마지막 형식 마무리/인사 완전 제거
  fixed = fixed.replace(new RegExp(`${fullName} 드림`, 'g'), '');
  fixed = fixed.replace(/드림<\/p>/g, '</p>');
  fixed = fixed.replace(/<p>드림<\/p>/g, '');
  fixed = fixed.replace(/\n\n드림$/g, '');
  fixed = fixed.replace(/드림$/g, '');
  fixed = fixed.replace(/올림<\/p>/g, '</p>');
  fixed = fixed.replace(/<p>올림<\/p>/g, '');

  // 이상한 지역 표현 수정
  const regionName = userProfile.regionLocal || userProfile.regionMetro || '양양군시';
  const baseRegion = regionName.replace('도민', '').replace('민', '');
  fixed = fixed.replace(new RegExp(`${baseRegion}도민 경제`, 'g'), `${baseRegion} 경제`);
  fixed = fixed.replace(new RegExp(`${baseRegion}도민 관광`, 'g'), `${baseRegion} 관광`);
  fixed = fixed.replace(new RegExp(`${baseRegion}도민 발전`, 'g'), `${baseRegion} 발전`);

  // 중복/이상한 표현 정리
  fixed = fixed.replace(/양양군시민을 포함한 많은 군민들/g, '많은 주민들');
  fixed = fixed.replace(/양양군시민 여러분을 포함한/g, '제 여러분을 포함한');

  // 불완전한 문장 감지 및 제거
  fixed = fixed.replace(/([가-힣]+)\s*<\/p>/g, (match, word) => {
    if (!word.match(/[다요까니다요면네요습것음임음]$/)) {
      return '</p>';
    }
    return match;
  });

  // 빈 문단 제거
  fixed = fixed.replace(/<p><\/p>/g, '');
  fixed = fixed.replace(/<p>\s*<\/p>/g, '');

  // 이상한 조사 수정
  fixed = fixed.replace(/양양군을 통해/g, '양양군내를 통해');
  fixed = fixed.replace(/양양군을/g, '양양군내를');

  return fixed;
}

/**
 * 중복 이름 패턴 제거
 */
function removeDuplicateNames(content, fullName) {
  let fixed = content;

  console.log('🔩 최종 중복 이름 제거 시작');

  fixed = fixed.replace(new RegExp(`안녕 ${fullName} ${fullName}입`, 'g'), `안녕 ${fullName}입`);
  fixed = fixed.replace(new RegExp(`안녕 ${fullName} ${fullName}가`, 'g'), `안녕 ${fullName}가`);
  fixed = fixed.replace(new RegExp(`안녕 ${fullName} ${fullName}를`, 'g'), `안녕 ${fullName}를`);
  fixed = fixed.replace(new RegExp(`안녕 ${fullName} ${fullName}`, 'g'), `안녕 ${fullName}`);
  fixed = fixed.replace(new RegExp(`${fullName} ${fullName}입`, 'g'), `${fullName}입`);
  fixed = fixed.replace(new RegExp(`${fullName} ${fullName}가`, 'g'), `${fullName}가`);
  fixed = fixed.replace(new RegExp(`${fullName} ${fullName}를`, 'g'), `${fullName}를`);
  fixed = fixed.replace(new RegExp(`${fullName} ${fullName}`, 'g'), fullName);

  // 3연속 이상 중복도 처리
  fixed = fixed.replace(new RegExp(`${fullName} ${fullName} ${fullName}`, 'g'), fullName);
  fixed = fixed.replace(new RegExp(`안녕 ${fullName} ${fullName} ${fullName}`, 'g'), `안녕 ${fullName}`);

  return fixed;
}

module.exports = {
  processGeneratedContent,
  trimTrailingDiagnostics,
  trimAfterClosing,
  cleanupPostContent,
  moveSummaryToConclusionStart,
  ensureParagraphTags,
  ensureSectionHeadings,
  getIntroBlockCount,
  getBodyHeadingTexts,
  getConclusionHeadingText,
  splitBlocksIntoSections
};
