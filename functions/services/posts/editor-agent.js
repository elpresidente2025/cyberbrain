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
const { findUnsupportedNumericTokens } = require('../../utils/fact-guard');

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

const NEUTRAL_PARAGRAPHS = [
  '현안의 구조적 원인을 객관적으로 점검할 필요가 있습니다.',
  '현재 상황의 흐름과 배경을 차분히 살펴보는 것이 중요합니다.',
  '핵심 쟁점을 정리하고 사실관계를 확인해야 합니다.',
  '관련 지표와 맥락을 함께 살펴보는 진단이 필요합니다.',
  '문제의 원인과 영향이 어떻게 이어지는지 점검해야 합니다.'
];

const KEYWORD_SENTENCES = [
  '{kw} 관련 현황은 지역사회에서 꾸준히 논의되고 있습니다.',
  '이번 이슈는 {kw} 측면에서 구조적 진단이 필요합니다.',
  '{kw}과 맞물린 여건을 객관적으로 살펴볼 필요가 있습니다.',
  '{kw}에 대한 체감과 지표를 함께 확인해야 합니다.'
];

const SUMMARY_INTRO = '그래서 결국 내가 하고 싶은 이야기는 다음과 같습니다.';
const SUMMARY_LINES = [
  '첫째, {topic}의 현재 상황을 데이터와 체감으로 차분히 점검할 필요가 있습니다.',
  '둘째, 원인과 구조를 분리해 진단의 초점을 분명히 하는 과정이 중요합니다.',
  '셋째, 지역 여건에 맞는 개선 과제를 정리해 다음 논의로 이어가는 것이 필요합니다.'
];

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function stripHtml(html) {
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
}

function normalizeSpaces(text) {
  return text.replace(/\s{2,}/g, ' ').replace(/\s+([.,!?])/g, '$1').trim();
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

function replaceUnsupportedTokens(text, tokens) {
  let updated = text;
  tokens.forEach((token) => {
    if (!token) return;
    let replacement = '일정 수준';
    if (/[0-9]/.test(token)) {
      if (/%|퍼센트|포인트/.test(token)) {
        replacement = '상당한 비율';
      } else if (/(명|개|건|곳|가구|세대|회|차)/.test(token)) {
        replacement = '여러';
      } else if (/(년|월|일)/.test(token)) {
        replacement = '해당 시기';
      } else if (/(원|만원|억원|조|억|만|천)/.test(token)) {
        replacement = '상당한 규모';
      } else if (/(km|kg|㎡|평)/i.test(token)) {
        replacement = '일정 규모';
      }
    }
    updated = updated.replace(new RegExp(escapeRegExp(token), 'g'), replacement);
  });
  return normalizeSpaces(updated);
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

function neutralizePledgeParagraphs(html) {
  let index = 0;
  return html.replace(/<p[^>]*>[\s\S]*?<\/p>/gi, (match) => {
    const text = match.replace(/<[^>]*>/g, '');
    if (containsPledge(text) || /겠/.test(text)) {
      const replacement = NEUTRAL_PARAGRAPHS[index % NEUTRAL_PARAGRAPHS.length];
      index += 1;
      return `<p>${replacement}</p>`;
    }
    return match;
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

function ensureParagraphCount(html, minCount, maxCount) {
  const paragraphs = html.match(/<p[^>]*>[\s\S]*?<\/p>/gi) || [];
  let updated = html;

  if (paragraphs.length < minCount) {
    const needed = minCount - paragraphs.length;
    let additions = '';
    for (let i = 0; i < needed; i += 1) {
      additions += `<p>${NEUTRAL_PARAGRAPHS[i % NEUTRAL_PARAGRAPHS.length]}</p>\n`;
    }
    updated = `${updated}\n${additions}`;
  } else if (paragraphs.length > maxCount) {
    for (let i = paragraphs.length - 1; i >= maxCount; i -= 1) {
      updated = updated.replace(paragraphs[i], '');
    }
  }

  return updated.replace(/\n{3,}/g, '\n\n');
}

function ensureLength(html, minLength, maxLength) {
  if (!minLength) return html;
  let updated = html;
  let currentLength = stripHtml(updated).replace(/\s/g, '').length;
  const maxTarget = maxLength || Math.round(minLength * 1.1);

  let guard = 0;
  while (currentLength < minLength && guard < 20) {
    const paragraphCount = (updated.match(/<p[^>]*>[\s\S]*?<\/p>/gi) || []).length;
    if (paragraphCount >= 10) {
      updated = appendNeutralSentence(updated, NEUTRAL_PARAGRAPHS[guard % NEUTRAL_PARAGRAPHS.length]);
    } else {
      updated += `\n<p>${NEUTRAL_PARAGRAPHS[guard % NEUTRAL_PARAGRAPHS.length]}</p>`;
    }
    currentLength = stripHtml(updated).replace(/\s/g, '').length;
    guard += 1;
  }

  if (currentLength > maxTarget) {
    const paragraphs = updated.match(/<p[^>]*>[\s\S]*?<\/p>/gi) || [];
    for (let i = paragraphs.length - 1; i >= 0 && currentLength > maxTarget; i -= 1) {
      updated = updated.replace(paragraphs[i], '');
      currentLength = stripHtml(updated).replace(/\s/g, '').length;
    }
  }

  return updated;
}

function appendKeywordSentences(html, keyword, countNeeded) {
  if (!keyword || countNeeded <= 0) return html;
  let updated = html;
  const sentences = [];
  for (let i = 0; i < countNeeded; i += 1) {
    const template = KEYWORD_SENTENCES[i % KEYWORD_SENTENCES.length];
    sentences.push(template.replace('{kw}', keyword));
  }
  const addition = sentences.join(' ');
  const lastParagraphMatch = updated.match(/<p[^>]*>[\s\S]*?<\/p>(?![\s\S]*<p)/i);
  if (lastParagraphMatch) {
    const replacement = lastParagraphMatch[0].replace(/<\/p>\s*$/i, ` ${addition}</p>`);
    updated = updated.replace(lastParagraphMatch[0], replacement);
  } else {
    updated += `\n<p>${addition}</p>`;
  }
  return updated;
}

function appendNeutralSentence(html, sentence) {
  if (!sentence) return html;
  const lastParagraphMatch = html.match(/<p[^>]*>[\s\S]*?<\/p>(?![\s\S]*<p)/i);
  if (lastParagraphMatch) {
    const replacement = lastParagraphMatch[0].replace(/<\/p>\s*$/i, ` ${sentence}</p>`);
    return html.replace(lastParagraphMatch[0], replacement);
  }
  return `${html}\n<p>${sentence}</p>`;
}

function buildSummaryLines(keyword) {
  const topic = normalizeSpaces(keyword || '이 사안');
  return SUMMARY_LINES.map((line) => line.replace('{topic}', topic));
}

function buildSummaryText(keyword) {
  const lines = buildSummaryLines(keyword);
  return normalizeSpaces(`${SUMMARY_INTRO} ${lines.join(' ')}`);
}

function buildSummaryBlock(keyword, mode = 'full') {
  const lines = buildSummaryLines(keyword);
  if (mode === 'single') {
    return [
      '<h2>핵심 요약</h2>',
      `<p>${buildSummaryText(keyword)}</p>`
    ].join('\n');
  }
  if (mode === 'compact') {
    return [
      '<h2>핵심 요약</h2>',
      `<p>${SUMMARY_INTRO}</p>`,
      `<p>${lines.join(' ')}</p>`
    ].join('\n');
  }
  return [
    '<h2>핵심 요약</h2>',
    `<p>${SUMMARY_INTRO}</p>`,
    ...lines.map((line) => `<p>${line}</p>`)
  ].join('\n');
}

function ensureSummaryBlock(html, keyword, maxAdditionalChars = null) {
  if (!html || html.includes(SUMMARY_INTRO)) return html;

  const paragraphCount = (html.match(/<p[^>]*>[\s\S]*?<\/p>/gi) || []).length;
  const inlineText = buildSummaryText(keyword);
  const fullBlock = buildSummaryBlock(keyword, 'full');
  const compactBlock = buildSummaryBlock(keyword, 'compact');
  const singleBlock = buildSummaryBlock(keyword, 'single');

  const options = [];
  if (paragraphCount <= 6) {
    options.push({ mode: 'full', content: fullBlock });
  }
  if (paragraphCount <= 8) {
    options.push({ mode: 'compact', content: compactBlock });
  }
  if (paragraphCount <= 9) {
    options.push({ mode: 'single', content: singleBlock });
  }
  options.push({ mode: 'inline', content: inlineText });

  let chosen = options[0];
  if (maxAdditionalChars !== null) {
    chosen = options.find((option) => {
      const length = option.mode === 'inline'
        ? inlineText.replace(/\s/g, '').length
        : stripHtml(option.content).replace(/\s/g, '').length;
      return length <= maxAdditionalChars;
    });
  }

  if (!chosen) return html;
  if (chosen.mode === 'inline') {
    return appendNeutralSentence(html, inlineText);
  }
  return `${html}\n${chosen.content}`;
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
  if (base.length > 25) {
    base = base.substring(0, 25).trim();
  }
  return base;
}

function sanitizeTopicForFacts(topic, factAllowlist) {
  if (!topic) return '';
  let sanitized = topic;
  if (factAllowlist) {
    const check = findUnsupportedNumericTokens(sanitized, factAllowlist);
    if (!check.passed) {
      sanitized = replaceUnsupportedTokens(sanitized, check.unsupported || []);
    }
  }
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

  const intro = `${safeTopic}에 대한 현황과 구조를 점검합니다.`;
  const paragraphs = [
    intro,
    NEUTRAL_PARAGRAPHS[0],
    NEUTRAL_PARAGRAPHS[1],
    NEUTRAL_PARAGRAPHS[2],
    NEUTRAL_PARAGRAPHS[3],
    NEUTRAL_PARAGRAPHS[4]
  ];

  let content = [
    `<p>${paragraphs[0]}</p>`,
    '<h2>현안 개요</h2>',
    `<p>${paragraphs[1]}</p>`,
    '<h2>핵심 진단</h2>',
    `<p>${paragraphs[2]}</p>`,
    `<p>${paragraphs[3]}</p>`,
    '<h2>영향과 확인 과제</h2>',
    `<p>${paragraphs[4]}</p>`,
    `<p>${paragraphs[5]}</p>`
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

  if (factAllowlist) {
    const contentCheck = findUnsupportedNumericTokens(updatedContent, factAllowlist);
    if (!contentCheck.passed) {
      updatedContent = replaceUnsupportedTokens(updatedContent, contentCheck.unsupported || []);
      summary.push('근거 없는 수치 완화');
    }
    if (updatedTitle) {
      const titleCheck = findUnsupportedNumericTokens(updatedTitle, factAllowlist);
      if (!titleCheck.passed) {
        updatedTitle = replaceUnsupportedTokens(updatedTitle, titleCheck.unsupported || []);
        summary.push('제목 수치 완화');
      }
    }
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
    updatedContent = ensureParagraphCount(updatedContent, 5, 10);
    summary.push('문단 수 보정');
  }

  let currentCharCount = stripHtml(updatedContent).replace(/\s/g, '').length;
  if (needsLength && targetWordCount && currentCharCount < targetWordCount) {
    const summaryKeyword = primaryKeyword
      || (seoKeywords[0] && seoKeywords[0].keyword ? seoKeywords[0].keyword : seoKeywords[0])
      || '';
    const availableChars = maxTargetCount ? Math.max(0, maxTargetCount - currentCharCount) : null;
    const withSummary = ensureSummaryBlock(updatedContent, summaryKeyword, availableChars);
    if (withSummary !== updatedContent) {
      updatedContent = withSummary;
      summary.push('요약 보강');
      currentCharCount = stripHtml(updatedContent).replace(/\s/g, '').length;
    }
  }

  if (needsLength && targetWordCount) {
    const maxTarget = maxTargetCount || Math.round(targetWordCount * 1.1);
    if (currentCharCount < targetWordCount || (maxTarget && currentCharCount > maxTarget)) {
      updatedContent = ensureLength(updatedContent, targetWordCount, maxTargetCount);
      summary.push('분량 보정');
    }
  }

  const keywordCandidates = [...userKeywords, ...seoKeywords]
    .map(k => (k && k.keyword) ? k.keyword : k)
    .filter(Boolean);
  const uniqueKeywords = [...new Set(keywordCandidates)];
  const textForCount = stripHtml(updatedContent);
  let wordCount = textForCount.split(/\s+/).filter(Boolean).length || 1;
  let charCount = textForCount.replace(/\s/g, '').length || 1;
  const userMinCount = Math.max(1, Math.floor(charCount / 400));
  const minDensityCount = Math.max(1, Math.ceil(wordCount * 0.003));
  const primaryMinCount = Math.max(1, Math.ceil(wordCount * 0.015));

  uniqueKeywords.forEach((keyword) => {
    const currentCount = countOccurrences(updatedContent, keyword);
    const isUserKeyword = userKeywords.includes(keyword);
    let targetCount = keyword === primaryKeyword ? primaryMinCount : minDensityCount;
    if (isUserKeyword) {
      targetCount = Math.max(targetCount, userMinCount);
    }
    if (currentCount < targetCount) {
      updatedContent = appendKeywordSentences(updatedContent, keyword, targetCount - currentCount);
      summary.push(`키워드 보강: ${keyword}`);
    }
  });

  const updatedText = stripHtml(updatedContent);
  wordCount = updatedText.split(/\s+/).filter(Boolean).length || 1;
  const maxDensityCount = Math.max(1, Math.floor(wordCount * 0.03));
  uniqueKeywords.forEach((keyword) => {
    const currentCount = countOccurrences(updatedContent, keyword);
    if (currentCount > maxDensityCount) {
      updatedContent = replaceOccurrencesAfterLimit(
        updatedContent,
        keyword,
        maxDensityCount,
        '해당 사안'
      );
      summary.push(`키워드 과다 완화: ${keyword}`);
    }
  });

  if (needsParagraphs) {
    updatedContent = ensureParagraphCount(updatedContent, 5, 10);
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

    if (validationResult.details?.factCheck) {
      const factCheck = validationResult.details.factCheck || {};
      const unsupportedContent = factCheck.content?.unsupported || [];
      const unsupportedTitle = factCheck.title?.unsupported || [];

      if (unsupportedContent.length > 0) {
        issues.push({
          type: 'fact_check',
          severity: 'critical',
          description: `근거 없는 수치(본문): ${unsupportedContent.join(', ')}`,
          instruction: '원문/배경자료에 없는 수치는 삭제하거나 근거 있는 수치로 교체하세요.'
        });
      }
      if (unsupportedTitle.length > 0) {
        issues.push({
          type: 'title_fact_check',
          severity: 'high',
          description: `근거 없는 수치(제목): ${unsupportedTitle.join(', ')}`,
          instruction: '제목의 수치를 본문/자료에 있는 수치로 바꾸거나 수치를 제거하세요.'
        });
      }
    }
  }

  // 2. 키워드 미포함 문제
  if (keywordResult && !keywordResult.valid) {
    const missingKeywords = Object.entries(keywordResult.details?.keywords || {})
      .filter(([_, info]) => !info.valid && info.type === 'user')
      .map(([keyword, info]) => `"${keyword}" (현재 ${info.count}회, 최소 ${info.expected}회 필요)`);

    if (missingKeywords.length > 0) {
      issues.push({
        type: 'missing_keywords',
        severity: 'high',
        description: `필수 키워드 부족: ${missingKeywords.join(', ')}`,
        instruction: '이 키워드들을 본문에 자연스럽게 추가하세요. 특히 도입부에 포함하면 SEO에 효과적입니다.'
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
      const instruction = issue.instruction || description;
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
    status
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
      const hardFixed = applyHardConstraints({
        content,
        title,
        validationResult,
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

    const hardFixed = applyHardConstraints({
      content: result.content || content,
      title: result.title || title,
      validationResult,
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
    const hardFixed = applyHardConstraints({
      content,
      title,
      validationResult,
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
 * EditorAgent용 프롬프트 생성
 */
function buildEditorPrompt({ content, title, issues, userKeywords, status }) {
  const issuesList = issues.map((issue, idx) =>
    `${idx + 1}. [${issue.severity.toUpperCase()}] ${issue.description}\n   → ${issue.instruction}`
  ).join('\n\n');

  const statusNote = (status === '준비' || status === '현역')
    ? `\n⚠️ 작성자 상태: ${status} (예비후보 등록 전) - "~하겠습니다" 같은 공약성 표현 금지`
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
• 콤마 부제목: "OO, 해법을 찾다" 같은 패턴 금지
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
• "부산 대형병원, 순위 올리는 해법" ❌ (콤마 부제목, 해법)
• "부산 대형병원 순위 진단과 전망" ❌ (진단, 전망)
• "대형병원 문제, 이렇게 해결한다" ❌ (콤마 부제목, 추상적)
• "의료 혁신을 위한 5대 과제" ❌ (혁신, 과제)
` : '';

  return `당신은 정치 원고 편집 전문가입니다. 아래 원고에서 발견된 문제들을 수정해주세요.

[수정이 필요한 문제들]
${issuesList}
${statusNote}
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
3. 키워드는 자연스럽게 문맥에 맞게 삽입하세요. 억지로 끼워넣지 마세요.
4. 제목은 25자 이내로 유지하고, 키워드를 앞쪽에 배치하세요.
5. 숫자/연도/비율은 원문·배경자료에 있는 것만 사용하세요.
6. HTML 구조(<p>, <strong> 등)는 유지하세요.

다음 JSON 형식으로만 응답하세요:
{
  "title": "수정된 제목",
  "content": "수정된 본문 (HTML)",
  "editSummary": ["수정한 내용 1", "수정한 내용 2"]
}`;
}

module.exports = {
  refineWithLLM,
  buildCompliantDraft
};
