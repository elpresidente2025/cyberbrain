'use strict';

/**
 * EditorAgent - 검증 결과 기반 LLM 수정
 *
 * 역할:
 * - 휴리스틱 검증 결과(선거법, 반복 등)를 받아 LLM으로 자연스럽게 수정
 * - 키워드 미포함 문제 해결
 * - SEO 제안 사항 반영
 *
 * 흐름:
 * 생성 → 검증(문제 발견) → EditorAgent(LLM 수정) → 출력
 */

const { callGenerativeModel } = require('../gemini');
const {
  runHeuristicValidationSync,
  validateKeywordInsertion,
  validateTitleQuality
} = require('./validation');

const PLEDGE_PATTERNS = [
  /약속드?립니다/,
  /약속합니다/,
  /공약드?립니다/,
  /공약합니다/,
  /하겠습니다/,
  /하겠/,
  /되겠습니다/,
  /되겠/,
  /추진하겠/,
  /마련하겠/,
  /실현하겠/,
  /강화하겠/,
  /확대하겠/,
  /줄이겠/,
  /늘리겠/
];

const PLEDGE_REPLACEMENTS = [
  { pattern: /약속드?립니다/g, replacement: '필요성을 말씀드립니다' },
  { pattern: /약속합니다/g, replacement: '필요하다고 봅니다' },
  { pattern: /공약드?립니다/g, replacement: '방향을 제시합니다' },
  { pattern: /공약합니다/g, replacement: '방향을 제시합니다' },
  { pattern: /추진하겠(?:습니다)?/g, replacement: '추진이 필요합니다' },
  { pattern: /마련하겠(?:습니다)?/g, replacement: '마련이 필요합니다' },
  { pattern: /실현하겠(?:습니다)?/g, replacement: '실현이 필요합니다' },
  { pattern: /강화하겠(?:습니다)?/g, replacement: '강화가 필요합니다' },
  { pattern: /확대하겠(?:습니다)?/g, replacement: '확대가 필요합니다' },
  { pattern: /줄이겠(?:습니다)?/g, replacement: '줄이는 노력이 필요합니다' },
  { pattern: /늘리겠(?:습니다)?/g, replacement: '늘리는 방안이 필요합니다' },
  { pattern: /되겠(?:습니다)?/g, replacement: '되는 방향을 모색해야 합니다' },
  { pattern: /하겠(?:습니다)?/g, replacement: '할 필요가 있습니다' }
];

const KEYWORD_REPLACEMENTS = [
  '관련 현안',
  '지역 현안',
  '이 문제',
  '이 과제',
  '관련 이슈'
];

const TITLE_SUFFIXES = [
  '시장',
  '군수',
  '구청장',
  '도지사',
  '지사',
  '위원장',
  '의원',
  '후보',
  '대표',
  '의장',
  '총장',
  '총재',
  '장관'
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

const SIGNATURE_REGEXES = [
  /<p[^>]*>\s*감사합니다\.?\s*<\/p>/i,
  /<p[^>]*>\s*감사드립니다\.?\s*<\/p>/i,
  /<p[^>]*>\s*고맙습니다\.?\s*<\/p>/i,
  /<p[^>]*>\s*[^<]*드림\s*<\/p>/i,
  /감사합니다/,
  /감사드립니다/,
  /고맙습니다/,
  /사랑합니다/,
  /드림/
];

const SUMMARY_HEADING_REGEX = /<h[23][^>]*>[^<]*(요약|정리|결론)[^<]*<\/h[23]>/i;
const SUMMARY_TEXT_REGEX = /(정리하면|요약하면|결론적으로|핵심을 정리하면)/;

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function stripHtml(html) {
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

function normalizeSpaces(text) {
  return text.replace(/\s{2,}/g, ' ').replace(/\s+([.,!?])/g, '$1').trim();
}

function trimTextToLength(text, maxChars) {
  if (!text || !maxChars || maxChars <= 0) return '';
  let count = 0;
  let endIndex = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (!/\s/.test(ch)) {
      count += 1;
    }
    if (count > maxChars) {
      break;
    }
    endIndex = i + 1;
  }
  let trimmed = text.slice(0, endIndex).trim();
  if (!trimmed) return '';
  const lastSpace = trimmed.lastIndexOf(' ');
  const lastPunct = Math.max(
    trimmed.lastIndexOf('.'),
    trimmed.lastIndexOf('!'),
    trimmed.lastIndexOf('?')
  );
  const cutIndex = Math.max(lastSpace, lastPunct);
  if (cutIndex > 0 && cutIndex >= Math.floor(trimmed.length * 0.6)) {
    return trimmed.slice(0, cutIndex + 1).trim();
  }
  return '';
}

function findSignatureStartIndex(html) {
  if (!html) return -1;
  const threshold = Math.floor(html.length * 0.5);
  let candidate = -1;

  const considerIndex = (index) => {
    if (index >= threshold && (candidate === -1 || index < candidate)) {
      candidate = index;
    }
  };

  SIGNATURE_MARKERS.forEach((marker) => {
    const index = html.lastIndexOf(marker);
    if (index !== -1) {
      considerIndex(index);
    }
  });

  SIGNATURE_REGEXES.forEach((pattern) => {
    const regex = new RegExp(pattern.source, 'gi');
    let match;
    while ((match = regex.exec(html)) !== null) {
      considerIndex(match.index);
    }
  });

  return candidate;
}

function splitContentBySignature(html) {
  if (!html) return { body: '', tail: '' };
  const signatureIndex = findSignatureStartIndex(html);
  if (signatureIndex === -1) return { body: html, tail: '' };

  const paragraphStart = html.lastIndexOf('<p', signatureIndex);
  if (paragraphStart !== -1) {
    return {
      body: html.slice(0, paragraphStart).trim(),
      tail: html.slice(paragraphStart).trim()
    };
  }

  return {
    body: html.slice(0, signatureIndex).trim(),
    tail: html.slice(signatureIndex).trim()
  };
}

function joinContent(body, tail) {
  if (!tail) return body;
  if (!body) return tail;
  return `${body}\n${tail}`.replace(/\n{3,}/g, '\n\n');
}

function countOccurrences(html, keyword) {
  if (!keyword) return 0;
  const plainText = stripHtml(html);
  const escaped = escapeRegExp(keyword);
  const regex = new RegExp(escaped, 'g');
  const matches = plainText.match(regex);
  return matches ? matches.length : 0;
}

function replaceOccurrencesAfterLimit(html, keyword, limit, replacement) {
  if (!keyword || limit < 0) return html;
  let count = 0;
  const pattern = new RegExp(escapeRegExp(keyword), 'g');
  return html.replace(pattern, (match) => {
    count += 1;
    if (count > limit) {
      return replacement;
    }
    return match;
  });
}

function buildKeywordTemplateRegexes(keyword) {
  return [];
}

function reduceKeywordOccurrences(html, keyword, maxCount) {
  if (!keyword || maxCount < 0) return html;
  const templateRegexes = buildKeywordTemplateRegexes(keyword);
  if (templateRegexes.length === 0) {
    return replaceKeywordBeyondLimit(html, keyword, maxCount);
  }
  const { body, tail } = splitContentBySignature(html || '');
  let updatedBody = body || '';
  let currentCount = countOccurrences(updatedBody, keyword);
  if (currentCount <= maxCount) return html;

  const paragraphs = updatedBody.match(/<p[^>]*>[\s\S]*?<\/p>/gi) || [];
  const updatedParagraphs = [];

  for (const paragraph of paragraphs) {
    if (currentCount <= maxCount) {
      updatedParagraphs.push(paragraph);
      continue;
    }

    const text = paragraph.replace(/<[^>]*>/g, '').trim();
    if (!text) continue;

    const sentences = splitIntoSentences(text);
    const kept = [];

    for (const sentence of sentences) {
      const sentenceCount = countOccurrences(sentence, keyword);
      const isTemplate = templateRegexes.some((regex) => regex.test(sentence));

      if (currentCount > maxCount && sentenceCount > 0 && isTemplate) {
        currentCount -= sentenceCount;
        continue;
      }
      kept.push(sentence);
    }

    if (kept.length > 0) {
      updatedParagraphs.push(`<p>${normalizeSpaces(kept.join(' '))}</p>`);
    }
  }

  updatedBody = updatedParagraphs.join('\n');
  return joinContent(updatedBody, tail);
}

function replaceKeywordBeyondLimit(html, keyword, maxCount) {
  if (!keyword || maxCount < 0) return html;
  let count = 0;
  let replacementIndex = 0;
  const pattern = new RegExp(escapeRegExp(keyword), 'g');
  return html.replace(pattern, (match) => {
    count += 1;
    if (count > maxCount) {
      const replacements = getKeywordReductionReplacements(keyword);
      const replacement = replacements[replacementIndex % replacements.length];
      replacementIndex += 1;
      return replacement;
    }
    return match;
  });
}

function isTitleToken(token) {
  if (!token) return false;
  return TITLE_SUFFIXES.some((suffix) => token.endsWith(suffix));
}

function buildKeywordVariants(keyword) {
  const trimmed = String(keyword || '').trim();
  if (!trimmed) return [];
  const parts = trimmed.split(/\s+/).filter(Boolean);
  const variants = [];

  if (parts.length >= 2) {
    const first = parts[0];
    const rest = parts.slice(1).join(' ');

    if (isTitleToken(parts[parts.length - 1])) {
      const title = parts[parts.length - 1];
      const name = parts.slice(0, parts.length - 1).join(' ');
      variants.push(`${title} ${name}`);
    }

    variants.push(`${first}의 ${rest}`);
  }

  return [...new Set(variants)]
    .filter((variant) => variant && variant !== trimmed && !variant.includes(trimmed));
}

function getKeywordReductionReplacements(keyword) {
  const variants = buildKeywordVariants(keyword);
  if (variants.length > 0) return variants;
  return KEYWORD_REPLACEMENTS;
}

function collapseNumericPlaceholders(text) {
  if (!text) return text;
  const placeholders = [
    '일정 수준',
    '일정 비율',
    '해당 시기',
    '일정 규모',
    '여러'
  ];
  const group = placeholders.map(escapeRegExp).join('|');
  let updated = text;
  const duplicatePattern = new RegExp(`(${group})\\s*[.,]\\s*(${group})`, 'g');
  updated = updated.replace(duplicatePattern, '$1');
  return updated;
}

function replaceUnsupportedTokens(text, tokens) {
  let updated = text;
  tokens.forEach((token) => {
    if (!token) return;
    let replacement = '일정 수준';
    if (/[0-9]/.test(token)) {
      if (/%|퍼센트|프로|%p|p|pt|포인트/i.test(token)) {
        replacement = '일정 비율';
      } else if (/(명|인|개|곳|건|가구|세대|회|차|위|대|호)/.test(token)) {
        replacement = '여러';
      } else if (/(년|월|일|주|시|분|초)/.test(token)) {
        replacement = '해당 시기';
      } else if (/(원|만원|억원|조원|조|억|만|천)/.test(token)) {
        replacement = '일정 규모';
      } else if (/(km|kg|㎡|평|m|cm|mm)/i.test(token)) {
        replacement = '일정 규모';
      }
    }
    updated = updated.replace(new RegExp(escapeRegExp(token), 'g'), replacement);
  });
  return normalizeSpaces(collapseNumericPlaceholders(updated));
}

function containsPledge(text) {
  return PLEDGE_PATTERNS.some((pattern) => pattern.test(text));
}

function neutralizePledgeTitle(title) {
  if (!title) return title;
  let updated = title;
  PLEDGE_PATTERNS.forEach((pattern) => {
    updated = updated.replace(new RegExp(pattern.source, 'g'), '');
  });
  updated = updated.replace(/겠습니다/g, '').replace(/하겠(다|습니다)?/g, '');
  return normalizeSpaces(updated);
}

function softenPledgeSentence(sentence) {
  if (!sentence) return sentence;
  let updated = sentence;
  PLEDGE_REPLACEMENTS.forEach(({ pattern, replacement }) => {
    updated = updated.replace(pattern, replacement);
  });
  updated = normalizeSpaces(updated);
  return updated;
}


function neutralizePledgeParagraphs(html) {
  return html.replace(/<p[^>]*>[\s\S]*?<\/p>/gi, (match) => {
    const text = match.replace(/<[^>]*>/g, '').trim();
    if (!text) return match;
    const sentences = splitIntoSentences(text);
    let changed = false;
    const updated = sentences.map((sentence) => {
      if (containsPledge(sentence)) {
        const softened = softenPledgeSentence(sentence);
        if (softened && !containsPledge(softened) && softened.length >= 10) {
          changed = true;
          return softened;
        }
        changed = true;
        return '';
      }
      return sentence;
    });
    if (!changed) {
      return match;
    }
    const filtered = updated.filter(Boolean);
    if (filtered.length === 0) {
      return '';
    }
    return `<p>${normalizeSpaces(filtered.join(' '))}</p>`;
  });
}

function ensureHeadings(html) {
  if (/<h2>|<h3>/i.test(html)) {
    return html;
  }
  const firstParagraphMatch = html.match(/<p[^>]*>[\s\S]*?<\/p>/i);
  if (firstParagraphMatch) {
    return html.replace(firstParagraphMatch[0], `${firstParagraphMatch[0]}\n<h2>현안 개요</h2>`);
  }
  return `<h2>현안 개요</h2>\n${html}`;
}

function ensureParagraphCount(html, minCount, maxCount, keyword = '') {
  const { body, tail } = splitContentBySignature(html);
  const bodyParagraphs = body.match(/<p[^>]*>[\s\S]*?<\/p>/gi) || [];
  const tailParagraphs = tail.match(/<p[^>]*>[\s\S]*?<\/p>/gi) || [];
  const totalCount = bodyParagraphs.length + tailParagraphs.length;
  let updated = body;

  if (totalCount < minCount) {
    const updatedParagraphs = [...bodyParagraphs];
    let count = totalCount;
    for (let i = 0; i < updatedParagraphs.length && count < minCount; i += 1) {
      const text = stripHtml(updatedParagraphs[i]).trim();
      const sentences = splitIntoSentences(text);
      if (sentences.length < 2) continue;
      const mid = Math.ceil(sentences.length / 2);
      const first = normalizeSpaces(sentences.slice(0, mid).join(' '));
      const second = normalizeSpaces(sentences.slice(mid).join(' '));
      if (!first || !second) continue;
      updatedParagraphs.splice(i, 1, `<p>${first}</p>`, `<p>${second}</p>`);
      count += 1;
    }
    updated = updatedParagraphs.join('\n');
  } else if (totalCount > maxCount) {
    const removeCount = totalCount - maxCount;
    for (let i = 0; i < removeCount; i += 1) {
      const index = bodyParagraphs.length - 1 - i;
      if (index < 0) break;
      updated = updated.replace(bodyParagraphs[index], '');
    }
  }

  const normalized = updated.replace(/\n{3,}/g, '\n\n');
  return joinContent(normalized, tail);
}

function ensureLength(html, minLength, maxLength, keyword = '') {
  if (!minLength) return html;
  let updated = html;
  let currentLength = stripHtml(updated).replace(/\s/g, '').length;
  const maxTarget = maxLength || Math.round(minLength * 1.1);

  if (currentLength < minLength) {
    return html;
  }

  if (currentLength > maxTarget) {
    const { body, tail } = splitContentBySignature(updated);
    const paragraphs = body.match(/<p[^>]*>[\s\S]*?<\/p>/gi) || [];
    let trimmedBody = body;
    for (let i = paragraphs.length - 1; i >= 0 && currentLength > maxTarget; i -= 1) {
      trimmedBody = trimmedBody.replace(paragraphs[i], '');
      const merged = joinContent(trimmedBody, tail);
      currentLength = stripHtml(merged).replace(/\s/g, '').length;
    }
    updated = joinContent(trimmedBody, tail);
  }

  return updated;
}

function injectKeywordByReplacement(html, keyword) {
  if (!keyword) return html;
  const { body, tail } = splitContentBySignature(html || '');
  let updated = body || '';
  for (const fallback of KEYWORD_REPLACEMENTS) {
    if (updated.includes(fallback)) {
      updated = updated.replace(fallback, keyword);
      return joinContent(updated, tail);
    }
  }
  return html;
}

function appendKeywordInline(html, keyword) {
  if (!keyword) return html;
  const { body, tail } = splitContentBySignature(html || '');
  let updated = body || '';
  const lastParagraphMatch = updated.match(/<p[^>]*>[\s\S]*?<\/p>(?![\s\S]*<p)/i);
  const phrase = `${keyword}`;
  if (lastParagraphMatch) {
    const replacement = lastParagraphMatch[0].replace(/<\/p>\s*$/i, ` (${phrase})</p>`);
    updated = updated.replace(lastParagraphMatch[0], replacement);
  } else {
    updated += `\n<p>${phrase}</p>`;
  }
  return joinContent(updated, tail);
}

function countKeywordCoverage(html, keyword) {
  if (!keyword) return 0;
  const variants = buildKeywordVariants(keyword);
  const keywords = [keyword, ...variants];
  return keywords.reduce((sum, kw) => sum + countOccurrences(html, kw), 0);
}

function appendKeywordSentences(html, keyword, countNeeded) {
  if (!keyword || countNeeded <= 0) return html;
  let updated = html;
  const variants = [keyword, ...buildKeywordVariants(keyword)];
  let index = 0;
  for (let i = 0; i < countNeeded; i += 1) {
    const candidate = variants[index % variants.length] || keyword;
    const replaced = injectKeywordByReplacement(updated, candidate);
    if (replaced !== updated) {
      updated = replaced;
    } else {
      updated = appendKeywordInline(updated, candidate);
    }
    index += 1;
  }
  return updated;
}

function isGreetingText(text) {
  if (!text) return false;
  const normalized = text.replace(/\s+/g, ' ').trim();
  if (!normalized) return false;
  return /^(존경하는|사랑하는|안녕하세요|안녕하십니까)/.test(normalized)
    || normalized.includes('시민 여러분')
    || normalized.includes('주민 여러분');
}

function extractSummaryCandidates(body) {
  const paragraphs = body.match(/<p[^>]*>[\s\S]*?<\/p>/gi) || [];
  const candidates = [];
  paragraphs.forEach((paragraph) => {
    const text = stripHtml(paragraph).trim();
    if (!text || isGreetingText(text)) return;
    const sentences = splitIntoSentences(text);
    if (sentences.length === 0) return;
    const sentence = sentences[0];
    if (!candidates.includes(sentence)) {
      candidates.push(sentence);
    }
  });
  return candidates;
}

function buildSummaryBlockFromBody(body, maxChars) {
  const candidates = extractSummaryCandidates(body).slice(0, 3);
  if (candidates.length === 0) return '';
  const merged = normalizeSpaces(candidates.join(' '));
  const trimmed = maxChars ? trimTextToLength(merged, maxChars) : merged;
  if (!trimmed) return '';
  return `<p data-summary="true">${trimmed}</p>`;
}

function splitIntoSentences(text) {
  if (!text) return [];
  const matches = String(text).match(/[^.!?]+[.!?]+|[^.!?]+$/g);
  if (!matches) return [];
  return matches.map((s) => s.trim()).filter(Boolean);
}

function removeRepeatedSentences(html) {
  const seen = new Set();
  return html.replace(/<p[^>]*>[\s\S]*?<\/p>/gi, (match) => {
    const text = match.replace(/<[^>]*>/g, '').trim();
    if (!text) return '';
    const sentences = splitIntoSentences(text);
    const filtered = sentences.filter((sentence) => {
      const normalized = sentence.replace(/\s+/g, '').toLowerCase();
      if (seen.has(normalized)) {
        return false;
      }
      seen.add(normalized);
      return true;
    });
    if (filtered.length === 0) {
      return '';
    }
    return `<p>${normalizeSpaces(filtered.join(' '))}</p>`;
  });
}

function hasSummarySignal(html) {
  if (!html) return false;
  const plain = stripHtml(html);
  return SUMMARY_HEADING_REGEX.test(html) || SUMMARY_TEXT_REGEX.test(plain);
}

function buildSummaryBlockToFit(body, maxChars) {
  if (!body) return '';
  if (!maxChars || maxChars <= 0) return '';
  return buildSummaryBlockFromBody(body, maxChars);
}

function insertSummaryAtConclusion(body, block) {
  if (!block) return body;
  if (!body) return block;

  const matches = [...body.matchAll(SUMMARY_HEADING_REGEX)];
  if (matches.length === 0) {
    return `${body}\n${block}`.replace(/\n{3,}/g, '\n\n');
  }

  const lastMatch = matches[matches.length - 1];
  const insertIndex = lastMatch.index + lastMatch[0].length;
  return `${body.slice(0, insertIndex)}\n${block}\n${body.slice(insertIndex)}`.replace(/\n{3,}/g, '\n\n');
}



function ensureSummaryBlock(html, _keyword, maxAdditionalChars = null) {
  if (!html) return html;
  if (hasSummarySignal(html)) return html;
  if (maxAdditionalChars !== null && maxAdditionalChars <= 0) return html;

  const { body, tail } = splitContentBySignature(html);
  const block = buildSummaryBlockToFit(body, maxAdditionalChars || 0);
  if (!block) return html;

  const updatedBody = insertSummaryAtConclusion(body, block);
  return joinContent(updatedBody, tail);
}

function buildSeoIssues(content, primaryKeyword, targetWordCount) {
  const issues = [];

  const h2Count = (content.match(/<h2>/gi) || []).length;
  const h3Count = (content.match(/<h3>/gi) || []).length;
  const pCount = (content.match(/<p>/gi) || []).length;
  const hasHeadings = h2Count >= 1 || h3Count >= 2;

  if (!hasHeadings) {
    issues.push({
      id: 'structure_headings',
      severity: 'high',
      message: '제목 구조가 부족합니다.'
    });
  }

  if (pCount < 5 || pCount > 10) {
    issues.push({
      id: 'structure_paragraphs',
      severity: 'high',
      message: '문단 수가 기준을 벗어났습니다.'
    });
  }

  if (typeof targetWordCount === 'number') {
    const charCount = stripHtml(content).replace(/\s/g, '').length;
    const min = targetWordCount;
    const max = Math.round(min * 1.1);
    if (charCount < min || charCount > max) {
      issues.push({
        id: 'content_length',
        severity: 'critical',
        message: '본문 분량이 기준을 벗어났습니다.'
      });
    }
  }

  if (!primaryKeyword) {
    issues.push({
      id: 'keywords_missing',
      severity: 'critical',
      message: 'SEO 키워드가 없습니다.'
    });
  }

  return {
    passed: issues.length === 0,
    issues,
    suggestions: [],
    revalidated: true
  };
}

function buildFollowupValidation({
  content,
  title,
  status,
  userKeywords,
  seoKeywords = [],
  factAllowlist,
  targetWordCount
}) {
  const heuristic = runHeuristicValidationSync(content, status, title, { factAllowlist });
  const titleQuality = validateTitleQuality(title, userKeywords, content, {
    strictFacts: !!factAllowlist
  });
  const primaryKeyword = userKeywords[0]
    || (seoKeywords[0] && seoKeywords[0].keyword ? seoKeywords[0].keyword : seoKeywords[0])
    || '';
  const seo = buildSeoIssues(content, primaryKeyword, targetWordCount);

  const passed = heuristic.passed && titleQuality.passed && seo.passed;
  return {
    passed,
    issues: [
      ...(heuristic.issues || []),
      ...(titleQuality.issues || []),
      ...(seo.issues || [])
    ],
    details: {
      ...heuristic.details,
      titleQuality,
      seo
    }
  };
}

function applyHardConstraintsOnly({
  content,
  title,
  status,
  userKeywords = [],
  seoKeywords = [],
  factAllowlist = null,
  targetWordCount = null
}) {
  if (!content) {
    return {
      content,
      title,
      edited: false,
      editSummary: []
    };
  }

  const validationResult = buildFollowupValidation({
    content,
    title,
    status,
    userKeywords,
    seoKeywords,
    factAllowlist,
    targetWordCount
  });

  const keywordResult = validateKeywordInsertion(
    content,
    userKeywords,
    [],
    targetWordCount
  );

  if (validationResult.passed && keywordResult.valid) {
    return {
      content,
      title,
      edited: false,
      editSummary: []
    };
  }

  const hardFixed = applyHardConstraints({
    content,
    title,
    validationResult,
    userKeywords,
    seoKeywords,
    factAllowlist,
    targetWordCount
  });

  return {
    content: hardFixed.content,
    title: hardFixed.title,
    edited: hardFixed.content !== content || hardFixed.title !== title,
    editSummary: hardFixed.editSummary || []
  };
}

function buildSafeTitle(title, userKeywords = []) {
  const primaryKeyword = userKeywords[0] || (seoKeywords[0]?.keyword || seoKeywords[0] || '');
  let base = neutralizePledgeTitle(title || '');
  if (!base || base.length < 5) {
    base = primaryKeyword ? `${primaryKeyword} 현안 진단` : '현안 진단 보고';
  }
  if (primaryKeyword && !base.includes(primaryKeyword)) {
    base = `${primaryKeyword} ${base}`.trim();
  }
  base = normalizeSpaces(base);
  if (base.length < 18) {
    base = normalizeSpaces(`${base} 핵심 점검`);
  }
  return trimTitleToLimit(base, primaryKeyword);
}

function trimTitleToLimit(title, primaryKeyword, limit = 25) {
  const normalized = normalizeSpaces(title);
  if (normalized.length <= limit) return normalized;

  const separatorRegex = /\s*[-–—:|·,]\s*/;
  if (separatorRegex.test(normalized)) {
    const parts = normalized.split(separatorRegex).map((part) => part.trim()).filter(Boolean);
    if (parts.length > 0 && parts[0].length <= limit) {
      return parts[0];
    }
  }

  const words = normalized.split(' ').filter(Boolean);
  while (words.length > 1 && words.join(' ').length > limit) {
    words.pop();
  }
  const compact = normalizeSpaces(words.join(' '));
  if (compact.length <= limit) return compact;

  const candidates = [];
  if (primaryKeyword) {
    candidates.push(`${primaryKeyword} 현안 진단`);
    candidates.push(`${primaryKeyword} 현안`);
    candidates.push(`${primaryKeyword} 진단`);
    candidates.push(primaryKeyword);
  }
  candidates.push('현안 진단');
  candidates.push('현안 점검');
  const fallback = candidates.find((candidate) => candidate && candidate.length <= limit);
  return fallback || '현안 진단';
}

function sanitizeTopicForFacts(topic, factAllowlist) {
  if (!topic) return '';
  let sanitized = topic;
  sanitized = neutralizePledgeTitle(sanitized);
  return normalizeSpaces(sanitized);
}

function buildCompliantDraft({
  topic = '',
  userKeywords = [],
  seoKeywords = [],
  targetWordCount = 2000,
  factAllowlist = null
}) {
  const safeTopic = sanitizeTopicForFacts(topic, factAllowlist) || '현안';
  const seedTitle = `${safeTopic} 현안 진단`;
  const titleKeywords = userKeywords.length > 0 ? userKeywords : seoKeywords;
  const title = buildSafeTitle(seedTitle, titleKeywords);

  const paragraphs = [
    `${safeTopic}에 대한 현황과 구조를 점검합니다.`,
    `${safeTopic}의 배경과 최근 흐름을 객관적으로 살펴봅니다.`,
    '핵심 지표와 사실관계를 중심으로 현안을 정리합니다.',
    '영향과 과제를 구분해 추가로 확인할 지점을 정리합니다.'
  ];

  let content = [
    `<p>${paragraphs[0]}</p>`,
    '<h2>현안 개요</h2>',
    `<p>${paragraphs[1]}</p>`,
    '<h2>핵심 진단</h2>',
    `<p>${paragraphs[2]}</p>`,
    '<h2>영향과 확인 과제</h2>',
    `<p>${paragraphs[3]}</p>`
  ].join('\n');

  const validationResult = {
    passed: false,
    details: {
      electionLaw: { violations: [] },
      repetition: { repeatedSentences: [] },
      titleQuality: { passed: false, issues: [] },
      seo: {
        passed: false,
        issues: [
          { id: 'structure_headings' },
          { id: 'structure_paragraphs' },
          { id: 'content_length' }
        ],
        suggestions: []
      }
    }
  };

  return applyHardConstraints({
    content,
    title,
    validationResult,
    userKeywords,
    seoKeywords,
    factAllowlist,
    targetWordCount
  });
}

function applyHardConstraints({
  content,
  title,
  validationResult,
  userKeywords = [],
  seoKeywords = [],
  factAllowlist,
  targetWordCount
}) {
  let updatedContent = content;
  let updatedTitle = title;
  const summary = [];

  const electionViolations = validationResult?.details?.electionLaw?.violations || [];
  if (electionViolations.length > 0) {
    updatedContent = neutralizePledgeParagraphs(updatedContent);
    updatedTitle = neutralizePledgeTitle(updatedTitle);
    summary.push('선거법 위험 표현 완화');
  }

  const repetitionIssues = validationResult?.details?.repetition?.repeatedSentences || [];
  if (repetitionIssues.length > 0) {
    updatedContent = removeRepeatedSentences(updatedContent);
    summary.push('문장 반복 완화');
  }

  const primaryKeyword = userKeywords[0] || '';
  const needsSafeTitle = !updatedTitle
    || updatedTitle.length < 18
    || updatedTitle.length > 25
    || (primaryKeyword && !updatedTitle.includes(primaryKeyword))
    || (validationResult?.details?.titleQuality && validationResult.details.titleQuality.passed === false);

  if (needsSafeTitle) {
    const titleKeywords = userKeywords.length > 0 ? userKeywords : seoKeywords;
    updatedTitle = buildSafeTitle(updatedTitle, titleKeywords);
    summary.push('제목 보정');
  }

  const seoIssues = validationResult?.details?.seo?.issues || [];
  const needsHeadings = seoIssues.some(issue => issue.id === 'structure_headings')
    || !/<h2>|<h3>/i.test(updatedContent);
  const paragraphCount = (updatedContent.match(/<p[^>]*>[\s\S]*?<\/p>/gi) || []).length;
  const needsParagraphs = seoIssues.some(issue => issue.id === 'structure_paragraphs')
    || paragraphCount < 5
    || paragraphCount > 10;
  const contentCharCount = stripHtml(updatedContent).replace(/\s/g, '').length;
  const maxTargetCount = targetWordCount ? Math.round(targetWordCount * 1.1) : null;
  const needsLength = seoIssues.some(issue => issue.id === 'content_length')
    || (targetWordCount && (contentCharCount < targetWordCount || (maxTargetCount && contentCharCount > maxTargetCount)));

  if (needsHeadings) {
    updatedContent = ensureHeadings(updatedContent);
    summary.push('소제목 보강');
  }

  if (needsParagraphs) {
    updatedContent = ensureParagraphCount(updatedContent, 5, 10, primaryKeyword);
    summary.push('문단 수 보정');
  }

  let currentCharCount = stripHtml(updatedContent).replace(/\s/g, '').length;
  if (needsLength && targetWordCount && currentCharCount < targetWordCount) {
    const summaryKeyword = primaryKeyword
      || (seoKeywords[0] && seoKeywords[0].keyword ? seoKeywords[0].keyword : seoKeywords[0])
      || '';
    const deficit = targetWordCount - currentCharCount;
    const withSummary = ensureSummaryBlock(updatedContent, summaryKeyword, deficit);
    if (withSummary !== updatedContent) {
      updatedContent = withSummary;
      summary.push('요약 보강');
      currentCharCount = stripHtml(updatedContent).replace(/\s/g, '').length;
    }
  }

  if (needsLength && targetWordCount) {
    const maxTarget = maxTargetCount || Math.round(targetWordCount * 1.1);
    if (currentCharCount < targetWordCount || (maxTarget && currentCharCount > maxTarget)) {
      updatedContent = ensureLength(updatedContent, targetWordCount, maxTargetCount, primaryKeyword);
      summary.push('분량 보정');
    }
  }

  const dedupedContent = removeRepeatedSentences(updatedContent);
  if (dedupedContent !== updatedContent) {
    updatedContent = dedupedContent;
    summary.push('중복 문장 정리');
  }

  if (needsLength && targetWordCount) {
    const refreshedCount = stripHtml(updatedContent).replace(/\s/g, '').length;
    if (refreshedCount < targetWordCount) {
      updatedContent = ensureLength(updatedContent, targetWordCount, maxTargetCount, primaryKeyword);
    }
  }

  const keywordCandidates = [...userKeywords, ...seoKeywords]
    .map(k => (k && k.keyword) ? k.keyword : k)
    .filter(Boolean);
  const uniqueKeywords = [...new Set(keywordCandidates)];
  const textForCount = stripHtml(updatedContent);
  const charCount = textForCount.replace(/\s/g, '').length || 1;
  const userTargetCount = Math.max(1, Math.floor(charCount / 400));
  const userMaxCount = userTargetCount;
  const userMinCount = userTargetCount;
  const userKeywordSet = new Set(userKeywords);

  uniqueKeywords.forEach((keyword) => {
    const currentCount = countKeywordCoverage(updatedContent, keyword);
    const isUserKeyword = userKeywordSet.has(keyword);
    const ensureOnce = isUserKeyword || (!userKeywords.length && keyword === primaryKeyword);

    if (ensureOnce && currentCount < userMinCount) {
      updatedContent = appendKeywordSentences(updatedContent, keyword, userMinCount - currentCount);
      summary.push(`키워드 보강: ${keyword}`);
    }

    const adjustedExactCount = countOccurrences(updatedContent, keyword);
    if (isUserKeyword && adjustedExactCount > userMaxCount) {
      const reduced = reduceKeywordOccurrences(updatedContent, keyword, userMaxCount);
      updatedContent = reduced;
      const reducedCount = countOccurrences(updatedContent, keyword);
      if (reducedCount > userMaxCount) {
        updatedContent = replaceKeywordBeyondLimit(updatedContent, keyword, userMaxCount);
      }
      summary.push(`키워드 과다 조정: ${keyword}`);
    }
  });

  if (needsLength && targetWordCount) {
    const maxTarget = maxTargetCount || Math.round(targetWordCount * 1.1);
    const finalCharCount = stripHtml(updatedContent).replace(/\s/g, '').length;
    if (maxTarget && finalCharCount > maxTarget) {
      updatedContent = ensureLength(updatedContent, targetWordCount, maxTargetCount, primaryKeyword);
      summary.push('분량 상한 조정');
    }
  }

  if (needsParagraphs) {
    updatedContent = ensureParagraphCount(updatedContent, 5, 10, primaryKeyword);
  }

  return {
    content: updatedContent,
    title: updatedTitle,
    editSummary: summary
  };
}

/**
 * 검증 결과를 기반으로 원고를 LLM으로 수정
 *
 * @param {Object} params
 * @param {string} params.content - 원본 콘텐츠 (HTML)
 * @param {string} params.title - 원본 제목
 * @param {Object} params.validationResult - 휴리스틱 검증 결과
 * @param {Object} params.keywordResult - 키워드 검증 결과
 * @param {Array} params.userKeywords - 사용자 입력 키워드
 * @param {Array} params.seoKeywords - SEO 키워드(검수 기준)
 * @param {string} params.status - 사용자 상태 (준비/현역/예비/후보)
 * @param {string} params.modelName - 사용할 모델
 * @param {Object} params.factAllowlist - 허용 수치 토큰
 * @param {number} params.targetWordCount - 목표 글자 수
 * @returns {Promise<{content: string, title: string, edited: boolean, editSummary: string[]}>}
 */
async function refineWithLLM({
  content,
  title,
  validationResult,
  keywordResult,
  userKeywords = [],
  seoKeywords = [],
  status,
  modelName,
  factAllowlist = null,
  targetWordCount = null
}) {
  // 수정이 필요한 문제들 수집
  const issues = [];

  // 1. 휴리스틱 검증 문제
  if (validationResult && !validationResult.passed) {
    // 선거법 위반
    if (validationResult.details?.electionLaw?.violations?.length > 0) {
      issues.push({
        type: 'election_law',
        severity: 'critical',
        description: `선거법 위반 표현 발견: ${validationResult.details.electionLaw.violations.join(', ')}`,
        instruction: '이 표현들을 선거법을 준수하면서 동일한 의미를 전달하는 완곡한 표현으로 수정하세요. 예: "~하겠습니다" → "~을 추진합니다", "~을 연구하고 있습니다"'
      });
    }

    // 문장 반복
    if (validationResult.details?.repetition?.repeatedSentences?.length > 0) {
      issues.push({
        type: 'repetition',
        severity: 'high',
        description: `문장 반복 발견: ${validationResult.details.repetition.repeatedSentences.join(', ')}`,
        instruction: '반복되는 문장을 다른 표현으로 바꾸거나 삭제하세요.'
      });
    }
  }

  // 2. 키워드 미포함 문제
  if (keywordResult && !keywordResult.valid) {
    const keywordEntries = Object.entries(keywordResult.details?.keywords || {})
      .filter(([_, info]) => info.type === 'user');
    const missingKeywords = keywordEntries
      .filter(([_, info]) => (info.coverage ?? info.count) < info.expected)
      .map(([keyword, info]) => `"${keyword}" (현재 ${info.coverage ?? info.count}회, 최소 ${info.expected}회 필요)`);
    const overusedKeywords = keywordEntries
      .filter(([_, info]) => typeof info.max === 'number' && (info.exactCount ?? info.count) > info.max)
      .map(([keyword, info]) => `"${keyword}" (현재 ${info.exactCount ?? info.count}회, 최대 ${info.max}회 허용)`);

    if (missingKeywords.length > 0) {
      issues.push({
        type: 'missing_keywords',
        severity: 'high',
        description: `필수 키워드 부족: ${missingKeywords.join(', ')}`,
        instruction: '이 키워드들을 본문에 자연스럽게 추가하세요. 특히 도입부에 포함하면 SEO에 효과적입니다.'
      });
    }
    if (overusedKeywords.length > 0) {
      issues.push({
        type: 'overused_keywords',
        severity: 'high',
        description: `키워드 과다: ${overusedKeywords.join(', ')}`,
        instruction: '동일 키워드 반복을 줄이고, 중복 문장을 정리하세요.'
      });
    }
  }

  // 3. 제목 품질 문제 (validation.js에서 검증한 결과)
  if (validationResult?.details?.titleQuality && !validationResult.details.titleQuality.passed) {
    const titleIssues = validationResult.details.titleQuality.issues || [];
    for (const issue of titleIssues) {
      // 이미 있는 이슈와 중복 방지
      if (!issues.some(i => i.type === issue.type)) {
        issues.push({
          type: issue.type,
          severity: issue.severity,
          description: issue.description,
          instruction: issue.instruction
        });
      }
    }
  }

  // 3-1. 분량 문제 (contentLength)
  if (validationResult?.details?.contentLength && validationResult.details.contentLength.passed === false) {
    const lengthInfo = validationResult.details.contentLength;
    const current = lengthInfo.current;
    const min = lengthInfo.min;
    const max = lengthInfo.max;
    let instruction = '본문 분량을 기준 범위로 조정하세요.';

    if (typeof min === 'number' && current < min) {
      instruction = `본문 분량을 ${min}자 이상으로 확장하세요. 기존 맥락을 유지하면서 근거/사례를 보강하고 과도한 반복은 피하세요.`;
    } else if (typeof max === 'number' && current > max) {
      instruction = `본문 분량을 ${max}자 이하로 줄이세요. 핵심 근거는 유지하고 군더더기 표현을 정리하세요.`;
    }

    issues.push({
      type: 'content_length',
      severity: 'high',
      description: `본문 분량 ${current}자 (기준: ${typeof min === 'number' ? min : '-'}~${typeof max === 'number' ? max : '-'})`,
      instruction
    });
  }

  // 3-2. SEO 개선 이슈 (SEOAgent 결과)
  if (validationResult?.details?.seo) {
    const seoDetails = validationResult.details.seo;
    const seoIssues = Array.isArray(seoDetails.issues) ? seoDetails.issues : [];
    const seoSuggestions = Array.isArray(seoDetails.suggestions) ? seoDetails.suggestions : [];

    for (const issue of seoIssues) {
      const description = issue.message || issue.description || issue.reason || 'SEO 기준 미달';
      let instruction = issue.instruction || description;
      if (issue.id === 'content_length' && typeof targetWordCount === 'number') {
        const currentCount = stripHtml(content).replace(/\s/g, '').length;
        const minTarget = targetWordCount;
        const maxTarget = Math.round(targetWordCount * 1.1);
        if (currentCount < minTarget) {
          instruction = `본문을 ${minTarget}~${maxTarget}자(공백 제외)로 확장하세요. 기존 사실/근거를 유지하고 이미 언급된 항목을 1~2문장씩 구체화하세요. 새 주제/추신/요약 추가는 금지합니다.`;
        } else if (currentCount > maxTarget) {
          instruction = `본문을 ${minTarget}~${maxTarget}자(공백 제외)로 줄이세요. 중복과 군더더기를 정리하되 핵심 사실은 유지하세요.`;
        }
      }
      issues.push({
        type: issue.id || 'seo_issue',
        severity: issue.severity || 'high',
        description,
        instruction
      });
    }

    for (const suggestion of seoSuggestions) {
      const text = typeof suggestion === 'string'
        ? suggestion
        : (suggestion.message || suggestion.suggestion || '');
      if (!text) continue;
      issues.push({
        type: 'seo_suggestion',
        severity: 'medium',
        description: text,
        instruction: text
      });
    }
  }

  // 4. 사용자 키워드가 제목에 없는 경우 (titleQuality에서 이미 체크하지만 폴백)
  if (userKeywords.length > 0 && title && !issues.some(i => i.type === 'keyword_missing')) {
    const keywordsInTitle = userKeywords.filter(kw => title.includes(kw));
    if (keywordsInTitle.length === 0) {
      issues.push({
        type: 'title_keyword',
        severity: 'medium',
        description: `제목에 노출 희망 검색어 없음: ${userKeywords.join(', ')}`,
        instruction: '제목에 위 키워드 중 하나를 자연스럽게 포함하세요. 제목은 25자 이내로 유지하세요.'
      });
    }
  }

  // 수정할 문제가 없으면 원본 반환
  if (issues.length === 0) {
    console.log('✅ [EditorAgent] 수정 필요 없음 - 원본 유지');
    return {
      content,
      title,
      edited: false,
      editSummary: []
    };
  }

  console.log(`📝 [EditorAgent] ${issues.length}개 문제 발견, LLM 수정 시작`);

  // LLM 프롬프트 생성
  const prompt = buildEditorPrompt({
    content,
    title,
    issues,
    userKeywords,
    status,
    targetWordCount
  });

  try {
    const response = await callGenerativeModel(prompt, 1, modelName, true);

    // JSON 파싱
    let result;
    try {
      // JSON 블록 추출
      const jsonMatch = response.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        result = JSON.parse(jsonMatch[0]);
      } else {
        throw new Error('JSON 형식 없음');
      }
    } catch (parseError) {
      console.error('❌ [EditorAgent] JSON 파싱 실패:', parseError.message);
      const refreshedValidation = buildFollowupValidation({
        content,
        title,
        status,
        userKeywords,
        seoKeywords,
        factAllowlist,
        targetWordCount
      });
      const hardFixed = applyHardConstraints({
        content,
        title,
        validationResult: refreshedValidation,
        userKeywords,
        seoKeywords,
        factAllowlist,
        targetWordCount
      });
      const edited = hardFixed.content !== content || hardFixed.title !== title;
      return {
        content: hardFixed.content || content,
        title: hardFixed.title || title,
        edited,
        editSummary: hardFixed.editSummary?.length
          ? hardFixed.editSummary
          : ['파싱 실패로 자동 보정 적용']
      };
    }

    console.log('✅ [EditorAgent] LLM 수정 완료:', {
      titleChanged: result.title !== title,
      contentLength: result.content?.length || 0,
      editSummary: result.editSummary
    });

    const nextContent = result.content || content;
    const nextTitle = result.title || title;
    const refreshedValidation = buildFollowupValidation({
      content: nextContent,
      title: nextTitle,
      status,
      userKeywords,
      seoKeywords,
      factAllowlist,
      targetWordCount
    });
    const refreshedKeyword = validateKeywordInsertion(
      nextContent,
      userKeywords,
      [],
      targetWordCount
    );

    if (refreshedValidation.passed && refreshedKeyword.valid) {
      return {
        content: nextContent,
        title: nextTitle,
        edited: true,
        editSummary: result.editSummary || []
      };
    }

    const hardFixed = applyHardConstraints({
      content: nextContent,
      title: nextTitle,
      validationResult: refreshedValidation,
      userKeywords,
      seoKeywords,
      factAllowlist,
      targetWordCount
    });

    return {
      content: hardFixed.content || content,
      title: hardFixed.title || title,
      edited: true,
      editSummary: [
        ...(result.editSummary || issues.map(i => i.description)),
        ...(hardFixed.editSummary || [])
      ].filter(Boolean)
    };

  } catch (error) {
    console.error('❌ [EditorAgent] LLM 호출 실패:', error.message);
    const refreshedValidation = buildFollowupValidation({
      content,
      title,
      status,
      userKeywords,
      seoKeywords,
      factAllowlist,
      targetWordCount
    });
    const hardFixed = applyHardConstraints({
      content,
      title,
      validationResult: refreshedValidation,
      userKeywords,
      seoKeywords,
      factAllowlist,
      targetWordCount
    });
    const edited = hardFixed.content !== content || hardFixed.title !== title;
    return {
      content: hardFixed.content || content,
      title: hardFixed.title || title,
      edited,
      editSummary: hardFixed.editSummary?.length
        ? hardFixed.editSummary
        : ['LLM 호출 실패로 자동 보정 적용']
    };
  }
}

/**
 * 분량 부족 시 본문만 확장 (서명/슬로건은 유지)
 */
async function expandContentToTarget({
  content,
  targetWordCount,
  modelName,
  status
}) {
  if (!content || typeof targetWordCount !== 'number') {
    return { content, edited: false };
  }

  const { body, tail } = splitContentBySignature(content);
  const currentLength = stripHtml(body).replace(/\s/g, '').length;
  const maxTarget = Math.round(targetWordCount * 1.1);

  if (currentLength >= targetWordCount) {
    return { content, edited: false };
  }

  const prompt = `다음 HTML 본문의 분량을 ${targetWordCount}~${maxTarget}자(공백 제외) 범위로 늘리세요.
- 새 주제/새 소제목/요약/추신/마무리/감사 인사 추가 금지
- 기존 문단에 1~2문장씩 구체화하여 확장
- 원문에 없는 수치/사실 추가 금지
- 합쇼체 유지
- HTML 태그(<p>, <h2>, <h3>) 유지

[본문]
${body}

다음 JSON 형식으로만 응답하세요:
{
  "content": "확장된 본문(HTML)"
}`;

  try {
    const response = await callGenerativeModel(prompt, 1, modelName, true);
    let result;
    try {
      const jsonMatch = response.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        result = JSON.parse(jsonMatch[0]);
      } else {
        throw new Error('JSON 형식 없음');
      }
    } catch (parseError) {
      console.warn('⚠️ [EditorAgent] 분량 확장 JSON 파싱 실패:', parseError.message);
      return { content, edited: false };
    }

    const nextBody = result?.content || body;
    if (!nextBody || nextBody === body) {
      return { content, edited: false };
    }

    let merged = joinContent(nextBody, tail);
    const mergedLength = stripHtml(merged).replace(/\s/g, '').length;
    if (mergedLength > maxTarget) {
      merged = ensureLength(merged, targetWordCount, maxTarget);
    }
    return { content: merged, edited: true };
  } catch (error) {
    console.warn('⚠️ [EditorAgent] 분량 확장 실패:', error.message);
    return { content, edited: false };
  }
}

/**
 * EditorAgent용 프롬프트 생성
 */
function buildEditorPrompt({ content, title, issues, userKeywords, status, targetWordCount }) {
  const issuesList = issues.map((issue, idx) =>
    `${idx + 1}. [${issue.severity.toUpperCase()}] ${issue.description}\n   → ${issue.instruction}`
  ).join('\n\n');

  const statusNote = (status === '준비' || status === '현역')
    ? `\n⚠️ 작성자 상태: ${status} (예비후보 등록 전) - "~하겠습니다" 같은 공약성 표현 금지`
    : '';

  const hasLengthIssue = issues.some((issue) => issue.type === 'content_length');
  const currentLength = stripHtml(content || '').replace(/\s/g, '').length;
  const maxTarget = typeof targetWordCount === 'number' ? Math.round(targetWordCount * 1.1) : null;
  const lengthGuideline = hasLengthIssue && typeof targetWordCount === 'number'
    ? `\n📏 분량 목표: ${targetWordCount}~${maxTarget}자(공백 제외), 현재 ${currentLength}자\n- 새 주제/추신/요약 추가 금지\n- 기존 문단의 근거를 구체화해 분량을 맞출 것`
    : '';

  // 제목 관련 이슈가 있으면 상세 가이드라인 추가
  const hasTitleIssues = issues.some(i =>
    i.type.startsWith('title_') || ['keyword_missing', 'keyword_position', 'abstract_expression'].includes(i.type)
  );

  const titleGuideline = hasTitleIssues ? `
╔═══════════════════════════════════════════════════════════════╗
║  🚨 [CRITICAL] 제목 수정 필수 - 반드시 아래 규칙을 따르세요  ║
╚═══════════════════════════════════════════════════════════════╝

🔴 절대 금지 (위반 시 제목 재작성):
• 부제목 패턴: "-", ":", "/" 사용 금지
• 선거법 위반: "약속", "공약" (준비/현역 상태에서 금지)
• 추상적 명사: 해법, 진단, 방안, 대책, 과제, 분석, 전망, 혁신, 발전
• 추상적 동사: 찾다, 막는다, 나선다, 밝히다, 모색
• 25자 초과

✅ 필수 규칙:
• 25자 이내 (엄격히 준수)
• 핵심 키워드는 제목 맨 앞에 배치
• 반드시 구체적인 숫자 1개 이상 포함
• 제목의 숫자/단위는 본문에 실제 등장한 수치만 사용
• 단일 문장 형태 (부제목 없이)

📊 올바른 제목 형식 (반드시 이 패턴 사용):
• "[키워드] + [숫자/사실] + [결과]"
• "부산 대형병원 5곳 응급실 확대" (17자) ✅
• "부산 대형병원 순위 27위→10위권" (17자) ✅
• "환자 유출 30% 감소 3년 목표" (15자) ✅

❌ 절대 사용 금지 패턴:
• "부산의 미래를 위한 약속" ❌ (약속 = 선거법 위반)
• "부산 대형병원 순위 진단과 전망" ❌ (진단, 전망)
• "의료 혁신을 위한 5대 과제" ❌ (혁신, 과제)
` : '';

  return `당신은 정치 원고 편집 전문가입니다. 아래 원고에서 발견된 문제들을 수정해주세요.

[수정이 필요한 문제들]
${issuesList}
${statusNote}
${lengthGuideline}
${titleGuideline}
[원본 제목]
${title}

[원본 본문]
${content}

[필수 포함 키워드]
${userKeywords.join(', ') || '(없음)'}

  [수정 지침]
  1. 지적된 문제들만 최소한으로 수정하세요. 원고의 전체적인 톤과 맥락은 유지하세요.
  2. 선거법 위반 표현은 동일한 의미를 전달하면서 완곡하게 수정하세요.
  3. 합쇼체(합니다체)를 유지하되, 같은 문단에서 동일 어미가 연속되지 않도록 유사 표현으로 분산하는 것을 권장합니다.
  4. 키워드는 문맥에 자연스럽게 삽입하세요. 억지로 끼워넣지 마세요.
  5. 숫자/연도/비율은 원문·배경자료에 있는 것만 사용하세요.
  6. 제목은 25자 이내로 유지하고, 키워드를 앞쪽에 배치하세요.
  7. HTML 구조(<p>, <strong> 등)는 유지하세요.

다음 JSON 형식으로만 응답하세요:
{
  "title": "수정된 제목",
  "content": "수정된 본문 (HTML)",
  "editSummary": ["수정한 내용 1", "수정한 내용 2"]
}`;
}

module.exports = {
  refineWithLLM,
  buildCompliantDraft,
  buildFollowupValidation,
  applyHardConstraintsOnly,
  expandContentToTarget
};
