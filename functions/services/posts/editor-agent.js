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
  validateTitleQuality,
  validateBipartisanPraise
} = require('./validation');
const {
  stripHtml,
  splitContentBySignature,
  joinContent
} = require('./content-processor');
const {
  preventDoubleTransformation,
  determineWritingContext,
  normalizeNameSpacing
} = require('../../prompts/guidelines/editorial');

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

// (삭제됨 - 하드코딩 매핑 테이블 제거, LLM 기반 동의어 생성으로 대체)

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

const SUMMARY_HEADING_REGEX = /<h[23][^>]*>[^<]*(요약|정리|결론|마무리|맺음말)[^<]*<\/h[23]>/ig;
const SUMMARY_TEXT_REGEX = /(정리하면|요약하면|결론적으로|핵심을 정리하면)/;

/**
 * 마크다운 헤딩을 HTML로 변환
 */
function convertMarkdownToHtml(content) {
  if (!content) return content;
  let converted = content;
  // ### 를 <h3>로 변환 (먼저 처리)
  converted = converted.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>');
  // ## 를 <h2>로 변환
  converted = converted.replace(/^##\s+(.+)$/gm, '<h2>$1</h2>');
  return converted;
}

/**
 * 공백 정규화
 */
function normalizeSpaces(text) {
  if (!text) return '';
  return String(text).replace(/\s+/g, ' ').trim();
}

/**
 * 선거법 위반 제목 중립화
 */
function neutralizePledgeTitle(title) {
  if (!title) return '';
  let neutralized = title;
  // "약속", "공약" 등 제거
  for (const { pattern, replacement } of PLEDGE_REPLACEMENTS) {
    neutralized = neutralized.replace(pattern, replacement);
  }
  return neutralized;
}

/**
 * 요약문 존재 여부 확인
 */
function hasSummarySignal(content) {
  if (!content) return false;
  return SUMMARY_HEADING_REGEX.test(content) || SUMMARY_TEXT_REGEX.test(content);
}

/**
 * 요약 블록 생성 (분량에 맞춰)
 */
function buildSummaryBlockToFit(body, maxChars) {
  if (!body || maxChars <= 0) return '';
  // 간단한 요약 블록 생성 (실제로는 더 복잡한 로직 필요)
  const summary = '<p data-summary="true">위 내용을 정리하면 다음과 같습니다.</p>';
  return summary.length <= maxChars ? summary : '';
}

/**
 * 키워드 사용 빈도 체크 (범용)
 * @returns {{ keyword: string, count: number, shouldVary: boolean }[]}
 */
function analyzeKeywordUsage(content, keywords) {
  const results = [];

  for (const keyword of keywords) {
    const regex = new RegExp(keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    const matches = content.match(regex) || [];
    const count = matches.length;

    // 5회 이상 사용 시 변주 권장
    const shouldVary = count >= 5;

    results.push({
      keyword,
      count,
      shouldVary
    });
  }

  return results;
}

/**
 * 키워드 과다 사용 시 LLM에게 의미론적 변주 요청
 * (범용 설계: LLM이 문맥 기반으로 동의어 생성)
 */
function buildKeywordVariationGuide(keywordAnalysis) {
  const overusedKeywords = keywordAnalysis.filter(k => k.shouldVary);

  if (overusedKeywords.length === 0) {
    return '';
  }

  const keywordList = overusedKeywords.map(k =>
    `- **"${k.keyword}"** (현재 ${k.count}회 사용)`
  ).join('\n');

  return `
╔═══════════════════════════════════════════════════════════════╗
║  🎯 [SEO 최적화] 키워드 과다 사용 방지 - 의미론적 변주 필수  ║
╚═══════════════════════════════════════════════════════════════╝

**[CRITICAL] 검색엔진 스터핑 페널티 방지를 위해 아래 키워드를 반드시 변주하세요:**

${keywordList}

**변주 방법 (LLM이 자율적으로 판단)**:
각 키워드에 대해 문맥에 맞는 **동의어, 유사어, 상위어, 하위어**를 찾아 자연스럽게 혼용하세요.

**변주 원칙**:
1. **첫 등장**(제목, 서론 첫 문단): 정확한 키워드 사용 (SEO 앵커)
2. **본문 중반**: 의미론적 변주 표현 30% 이상 혼용 (자연스러움)
3. **결론**: 다시 정확한 키워드로 회귀 (강조)

**변주 예시 (few-shot)**:
- "디즈니랜드" → "세계구급 테마파크", "글로벌 IP 시설", "국제급 엔터테인먼트 단지"
- "AI 디지털밸리" → "첨단 산업 클러스터", "기술 혁신 단지", "차세대 산업 거점"
- "공약" → "정책 방향", "비전", "추진 과제"

**주의사항**:
- 변주 표현은 원래 키워드와 **정확히 같은 의미**여야 함
- 독자가 "이게 뭐지?" 하지 않도록 문맥상 자연스러워야 함
- 검색엔진은 시맨틱 이해 능력이 있으므로 동의어도 같은 주제로 인식함
`;
}

// ...

function insertSummaryAtConclusion(body, block) {
  if (!block) return body;
  if (!body) return block;

  const matches = [...body.matchAll(SUMMARY_HEADING_REGEX)];

  // 1. 결론/마무리 헤딩이 없는 경우 -> 본문 맨 뒤(서명 앞)에 붙임 (어쩔 수 없음)
  if (matches.length === 0) {
    return `${body}\n${block}`.replace(/\n{3,}/g, '\n\n');
  }

  // 2. 결론 헤딩이 있는 경우 -> 헤딩 "바로 앞"에 삽입 (결론 섹션 시작 전)
  const lastMatch = matches[matches.length - 1]; // 가장 마지막에 나오는 결론부 헤딩
  const insertIndex = lastMatch.index;

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

  // [강화된 기준] 소제목이 최소 3개 이상이어야 함 (2000자 기준)
  const hasHeadings = h2Count >= 3 || (h2Count + h3Count) >= 4;

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

  // [NEW] 마크다운 소제목 변환 (가장 먼저 수행)
  // eslint-disable-next-line no-param-reassign
  content = convertMarkdownToHtml(content);

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

function buildSafeTitle(title, userKeywords = [], seoKeywords = []) {
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
  const title = buildSafeTitle(seedTitle, userKeywords, seoKeywords);

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

  // 1. 선거법 위반 표현 필터 (기계적 치환 삭제 -> LLM 위임)
  /*
  const electionViolations = validationResult?.details?.electionLaw?.violations || [];
  if (electionViolations.length > 0) {
    updatedContent = neutralizePledgeParagraphs(updatedContent);
    updatedTitle = neutralizePledgeTitle(updatedTitle);
    summary.push('선거법 위험 표현 완화');
  }
  */

  // 2. 문장 반복 제거 (LLM 위임)
  // removeRepeatedSentences 함수는 구현되지 않았으므로 LLM이 처리하도록 함
  const repetitionIssues = validationResult?.details?.repetition?.repeatedSentences || [];
  if (repetitionIssues.length > 0) {
    summary.push('문장 반복 감지 (LLM 수정 필요)');
  }

  const primaryKeyword = userKeywords[0] || '';
  // [수정] 제목 강제 변경 조건 대폭 완화
  // 기존에는 길이(18~25자)나 키워드 미포함 시 무조건 '안전한 제목(노잼)'으로 바꿨음.
  // 이제는 제목이 없거나 너무 짧은(5자 미만) 경우에만 개입함.
  const needsSafeTitle = !updatedTitle || updatedTitle.length < 5;

  if (needsSafeTitle) {
    updatedTitle = buildSafeTitle(updatedTitle, userKeywords, seoKeywords);
    summary.push('제목 보정(누락/너무 짧음)');
  }

  const seoIssues = validationResult?.details?.seo?.issues || [];
  const needsHeadings = seoIssues.some(issue => issue.id === 'structure_headings')
    || !/<h2>|<h3>/i.test(updatedContent);
  const paragraphCount = (updatedContent.match(/<p[^>]*>[\s\S]*?<\/p>/gi) || []).length;
  const needsParagraphs = seoIssues.some(issue => issue.id === 'structure_paragraphs')
    || paragraphCount < 5
    || paragraphCount > 10;
  const contentCharCount = stripHtml(updatedContent).replace(/\s/g, '').length;
  const maxTargetCount = targetWordCount ? Math.round(targetWordCount * 1.2) : null;
  const needsLength = seoIssues.some(issue => issue.id === 'content_length')
    || (targetWordCount && (contentCharCount < targetWordCount || (maxTargetCount && contentCharCount > maxTargetCount)));

  // 구조/분량 관련 강제 로직(ensureHeadings, ensureLength 등)은 
  // 5단 구조(황금 비율)를 파괴하므로 전면 제거.
  // 오직 LLM이 프롬프트 규칙에 따라 수정하도록 함.

  // 1. 소제목 보강 로직 제거 (LLM 위임)
  /*
  if (needsHeadings) {
    updatedContent = ensureHeadings(updatedContent);
    summary.push('소제목 보강');
  }
  */

  // 2. 문단 수 보정 로직 제거 (LLM 위임)
  /*
  if (needsParagraphs) {
    updatedContent = ensureParagraphCount(updatedContent, 5, 10, primaryKeyword);
    summary.push('문단 수 보정');
  }
  */

  // 3. 분량 강제 조절 로직 제거 (가장 큰 원인 - 뒤를 잘라버림)
  /*
  let currentCharCount = stripHtml(updatedContent).replace(/\s/g, '').length;
  if (needsLength && targetWordCount && currentCharCount < targetWordCount) {
    // ... 요약 추가 로직 ...
  }

  if (needsLength && targetWordCount) {
    // ... 강제 자르기 로직 ...
  }
  */

  // 중복 문장 제거는 LLM이 처리하도록 함 (removeRepeatedSentences 미구현)

  // 4. 재검증 후 분량 조절 로직 제거
  /*
  if (needsLength && targetWordCount) {
     // ...
  }
  */

  // 3. 키워드 강제 주입 및 과다 조정 로직 (문맥 파괴의 주범 -> 삭제)
  // 키워드 부족 문제는 LLM 프롬프트(refineWithLLM)에서 해결하도록 유도함.
  /*
  const keywordCandidates = [...userKeywords, ...seoKeywords]
    .map(k => (k && k.keyword) ? k.keyword : k)
    .filter(Boolean);
  const uniqueKeywords = [...new Set(keywordCandidates)];
  
  // ... forEach 루프 및 appendKeywordSentences 삭제 ...
  */

  // 5. 마지막 분량 상한 조정 로직 제거
  /*
  if (needsLength && targetWordCount) {
    const maxTarget = maxTargetCount || Math.round(targetWordCount * 1.2);
    const finalCharCount = stripHtml(updatedContent).replace(/\s/g, '').length;
    if (maxTarget && finalCharCount > maxTarget) {
      updatedContent = ensureLength(updatedContent, targetWordCount, maxTargetCount, primaryKeyword);
      summary.push('분량 상한 조정');
    }
  }
  */

  /*
  if (needsParagraphs) {
    updatedContent = ensureParagraphCount(updatedContent, 5, 10, primaryKeyword);
  }
  */

  // 🌟 [NEW] 최후의 말투 교정 + 과다 키워드 분산 (강제 치환)
  updatedContent = forceFixContent(updatedContent, userKeywords);

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
  targetWordCount = null,
  dilutionAnalysis = null  // 🔑 키워드 희석 분석 결과
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
        const maxTarget = Math.round(targetWordCount * 1.2);
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

  // 5. 키워드 희석 문제 (경쟁 구문이 메인 키워드보다 많음)
  if (dilutionAnalysis && dilutionAnalysis.hasDilution && dilutionAnalysis.competitors?.length > 0) {
    const competitorInfo = dilutionAnalysis.competitors
      .map(c => `"${c.phrase}" (현재 ${c.count}회, 메인 키워드 "${dilutionAnalysis.primaryKeyword}": ${dilutionAnalysis.primaryCount}회)`)
      .join(', ');

    const alternatives = dilutionAnalysis.competitors
      .map(c => {
        // 경쟁 구문별 대체어 제안
        if (c.phrase.includes('병원')) {
          return `"${c.phrase}" → "의료 인프라", "대형 의료기관", "상급종합병원" 등`;
        }
        if (c.phrase.includes('유치')) {
          return `"${c.phrase}" → "유치 추진", "유치 노력", "유치 목표" 등`;
        }
        return `"${c.phrase}" → 동의어/유사어로 분산`;
      })
      .join('; ');

    issues.push({
      type: 'keyword_dilution',
      severity: 'high',
      description: `키워드 희석 위험: ${competitorInfo}`,
      instruction: `메인 SEO 키워드는 "${dilutionAnalysis.primaryKeyword}"입니다. 다음 경쟁 구문들을 동의어로 분산하여 메인 키워드가 가장 많이 등장하도록 하세요: ${alternatives}`
    });

    console.log(`⚠️ [EditorAgent] 키워드 희석 문제 발견: ${dilutionAnalysis.competitors.length}개 경쟁 구문`);
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
    const response = await callGenerativeModel(prompt, 1, modelName, true, 1700);

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
      // 초당적 협력 금지 표현 후처리 (자동 대체)
      const bipartisanResult = validateBipartisanPraise(nextContent, {
        rivalNames: userKeywords.filter(k => k.match(/^[가-힣]{2,4}$/)),  // 이름 형태 키워드 추출
        category: 'bipartisan'  // 일단 항상 적용 (향후 카테고리 정보 추가 필요)
      });
      const finalContent = bipartisanResult.correctedContent || nextContent;

      return {
        content: finalContent,
        title: nextTitle,
        edited: true,
        editSummary: [...(result.editSummary || []), ...(bipartisanResult.issues || [])]
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

    // 초당적 협력 금지 표현 후처리 (자동 대체)
    const bipartisanResult2 = validateBipartisanPraise(hardFixed.content || content, {
      rivalNames: userKeywords.filter(k => k.match(/^[가-힣]{2,4}$/)),
      category: 'bipartisan'
    });
    const finalContent2 = bipartisanResult2.correctedContent || hardFixed.content || content;

    return {
      content: finalContent2,
      title: hardFixed.title || title,
      edited: true,
      editSummary: [
        ...(result.editSummary || issues.map(i => i.description)),
        ...(hardFixed.editSummary || []),
        ...(bipartisanResult2.issues || [])
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
  // HTML 태그와 공백을 제거한 실제 글자 수 (기준)
  const currentLength = stripHtml(body).replace(/\s/g, '').length;
  const maxTarget = Math.round(targetWordCount * 1.2);

  if (currentLength >= targetWordCount) {
    return { content, edited: false };
  }

  const deficit = targetWordCount - currentLength;
  console.log(`📊 [EditorAgent] 분량 부족: ${deficit}자 필요 (현재 ${currentLength} / 목표 ${targetWordCount})`);

  // 🔧 [수정] 요약 확장 복구 + 최대 250자 제한
  const maxExpansion = 250; // 최대 확장 한도
  const actualExpansion = Math.min(deficit, maxExpansion);

  if (deficit > maxExpansion) {
    console.log(`⚠️ [EditorAgent] 부족분 ${deficit}자 중 ${maxExpansion}자까지만 확장 (할루시네이션 방지)`);
  }

  const prompt = `
당신은 전문 원고 교정가입니다.
현재 원고의 분량이 부족합니다. 아래 [본문]의 핵심 내용을 **간결하게 요약**하여, **정확히 ${actualExpansion}자** 분량의 마무리 문단을 작성해 주십시오.

[지시사항]
1. **분량 엄수**: 반드시 **${actualExpansion}자** 내외로 작성. 절대 초과 금지.
2. **위치**: 결론 바로 앞에 삽입됩니다.
3. **내용**: 본론의 핵심을 한 문장으로 압축하고, 긍정적 전망으로 마무리.
4. **형식**: <p> 태그 하나로 감싸서 작성.
5. **금지**: 자기소개 반복, 인사말 반복, 새로운 사실 창작 금지.

[본문]
${body}

다음 JSON 형식으로만 응답하세요:
{
  "summaryBlock": "<p>...요약 마무리 문단...</p>"
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
      console.warn('⚠️ [EditorAgent] 요약문 생성 JSON 파싱 실패:', parseError.message);
      return { content, edited: false };
    }

    const summaryBlock = result?.summaryBlock;
    if (!summaryBlock) {
      return { content, edited: false };
    }

    // 결론 앞에 요약문 삽입
    // insertSummaryAtConclusion 함수가 이미 editor-agent.js 내부에 존재함 (활용)
    const updatedBody = insertSummaryAtConclusion(body, summaryBlock);
    const finalContent = joinContent(updatedBody, tail);

    console.log(`✅ [EditorAgent] 요약문(${stripHtml(summaryBlock).length}자) 추가 완료`);
    return { content: finalContent, edited: true };

  } catch (error) {
    console.warn('⚠️ [EditorAgent] 분량 확장(요약문 생성) 실패:', error.message);
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
  const maxTarget = typeof targetWordCount === 'number' ? Math.round(targetWordCount * 1.2) : null;

  const lengthGuideline = hasLengthIssue && typeof targetWordCount === 'number'
    ? `\n📏 분량 목표: ${targetWordCount}~${maxTarget}자(공백 제외), 현재 ${currentLength}자\n- 새 주제/추신 추가 금지\n- 기존 문단의 근거를 구체화해 분량을 맞출 것\n🚨 [CRITICAL] 문단 복사 붙여넣기 절대 금지! 동일한 문단이 2번 이상 등장하면 원고 폐기됩니다.`
    : '';

  const titleGuideline = `
4. [CRITICAL] 제목 규칙:
   - "XXX 님의 공지", "XXX 후보의 약속" 같은 제목 절대 금지.
   - 반드시 **"[지역명] 핵심키워드 - 구체적 이득/행동"** 형식으로 작성.
   - 예: "[부산] 가덕신공항 조기 착공 - 국비 5천억 추가 확보 확정"`;

  const repetitionInstruction = issues.some(i => i.type === 'repetition')
    ? `\n\n🚨 [반복 서술 감지됨] 동일한 문장이나 표현을 반복하지 마십시오. 같은 내용을 말하더라도 반드시 다른 단어와 문장 구조를 사용해야 합니다.`
    : '';

  const structureGuideline = `
╔═══════════════════════════════════════════════════════════════╗
║  🚨 [CRITICAL] 5단 구조 유지 필수 (황금 비율)                 ║
╚═══════════════════════════════════════════════════════════════╝
1. 전체 구조: **[서론] - [본론1] - [본론2] - [본론3] - [결론]** (총 5개 섹션 유지)
2. 문단 규칙: **각 섹션은 반드시 3개의 문단**으로 구성하세요. (총 15문단)
3. 길이 규칙: **한 문단은 100~150자** 내외로 유연하게 쓰세요.
4. 소제목(H2) 규칙:
   - ❌ **서론**: 소제목 절대 금지 (인사말로 시작)
   - ✅ **본론1~3, 결론**: 각 섹션 시작 부분에 반드시 **뉴스 헤드라인형 소제목** 삽입
   - 예: <h2>이관훈 배우, 부산 방문</h2>
5. 편집/수정 시 이 **섹션-문단 구조를 절대 깨지 마세요.** 내용이 늘어나거나 줄어들어도 이 비율을 유지해야 합니다.
`;

  return `당신은 정치 원고 편집 전문가입니다. 아래 원고에서 발견된 문제들을 수정해주세요.

[수정이 필요한 문제들]
${issuesList}
${statusNote}
${structureGuideline}
${lengthGuideline}
${titleGuideline}
[원본 제목]
${title}

[원본 본문]
${content}

[필수 포함 키워드]
${userKeywords.join(', ') || '(없음)'}

  [수정 지침 (매우 중요)]
  1. **[CRITICAL] 말투 강제 교정 (AI 투 제거)**:
     - **"~라는 점입니다", "~것이라는 점입니다"** 패턴은 발견 즉시 삭제하거나 자연스러운 종결어미("**~입니다**", "**~합니다**", "**~것입니다**")로 고쳐 쓰세요.
     - **본인에 대한 서술에 추측성 어미 금지**: "저는 ~일 것입니다", "저는 ~알고 있을 것입니다"와 같이 자기 자신의 행동이나 감정을 남 말하듯 추측하지 마세요. 반드시 **"~입니다", "~하고 있습니다"**로 명확하게 쓰세요.
     - **과도한 확신 자제**: "반드시 해내겠습니다", "무조건 ~합니다"와 같은 표현이 너무 잦으면 오만해 보일 수 있습니다. 진정성 있는 **"노력하겠습니다", "최선을 다하겠습니다"** 표현도 적절히 섞어 쓰세요.
     - **부자연스러운 수동태/피동형 금지**: "~보여주는 증거일 것입니다" → "~보여줍니다"

  3. **[구조 및 서식 (AEO 최적화 소제목)]**:
     - 소제목(H2)은 검색 사용자가 궁금해하는 **구체적인 질문**이나 **데이터 기반 정보** 형태로 작성하세요. (12~25자 권장)
     - **✅ 좋은 예시 (따라 할 것)**:
       - "청년 기본소득, **신청 방법은 무엇인가요?**" (질문형+키워드 전진배치)
       - "부산 의료 관광 **클러스터 3대 핵심 전략**" (구체적 수치)
       - "이관훈 후원회장 **위촉 배경과 역할은?**" (구체적 질문)
       - "기존 정책 vs 신규 공약 **차이점 분석**" (비교형)
     - **❌ 나쁜 예시 (절대 금지 - 무조건 수정)**:
       - "관련 내용", "정책 안내" (너무 짧고 모호함)
       - "이관훈은?", "부산은?" (단순 명사/질문 → 구체적으로 서술어 포함할 것)
     - 소제목 텍스트는 반드시 **<h2> 태그**로 감싸세요.
     - 문단은 3줄~4줄 정도로 호흡을 짧게 끊어 가독성을 높이세요.

  4. **[검색어/SEO]**:
     - 키워드는 문맥에 맞게 자연스럽게 녹이되, 전체 글에서 **4~6회**까지만 사용하세요.
     - **[CRITICAL]** 제공된 검색어를 단 한 글자도 바꾸지 말고 그대로 사용해야 합니다 (패러프레이즈 금지).
     - 숫자나 통계는 원문에 있는 것만 정확히 인용하세요.

  5. **[CRITICAL] 글의 품질 향상 (중복·과장·논리 비약 제거)**:
     - **중복 표현 제거**: 같은 의미를 짧은 구간에 반복 서술하지 마세요.
       ❌ 나쁜 예: "충분히 가능합니다. ... 디즈니랜드 한국 유치는 현실적인 목표입니다."
       ✅ 좋은 예: "충분히 실현 가능한 비전임을 확신합니다." (하나로 통합)

     - **과장된 수사 완화**: "압도적", "판을 뒤집다", "대혁신" 등은 최대 1~2회만 사용하세요.
       ❌ 나쁜 예: "판을 완전히 뒤집어 놓을", "압도적인 교통", "압도적인 IP"
       ✅ 좋은 예: "근본적으로 혁신할", "뛰어난 교통", "강력한 IP"

     - **논리적 비약 방지**: A→B 유추가 억지스러우면 제거하거나 연결고리 추가
       ❌ 나쁜 예: "넷플릭스가 성공했으니 디즈니랜드도 성공한다"
       ✅ 좋은 예: "과거 대형 투자 프로젝트들도 초기엔 회의적이었지만..."

     - **섹션 간 연결 강화**: 디즈니랜드→AI 비전 전환 시 "이와 함께", "동시에" 등으로 자연스럽게 연결

     - **호칭 문법 교정**: 지역명을 직접 호칭하는 문법 오류를 수정하세요.
       ❌ 나쁜 예: "존경하는 부산광역시 여러분", "사랑하는 서울 여러분"
       ✅ 좋은 예: "존경하는 부산광역시민 여러분", "사랑하는 서울시민 여러분"
       (장소가 아닌 사람을 호칭해야 합니다)

  6. **[최소한의 수정 원칙]**:
     - 위 문제들이 없는 문장은 원문의 맛을 살려 그대로 두세요.
     - 선거법 위반 표현만 완곡하게 다듬으세요.
      - 선거법 위반 표현만 완곡하게 다듬으세요.
${repetitionInstruction}
${keywordVariationGuide}
다음 JSON 형식으로만 응답하세요:
{
  "title": "수정된 제목",
  "content": "수정된 본문 (HTML) - h2, h3, p 태그 구조 준수",
  "editSummary": ["~라는 점입니다 말투 수정", "소제목 태그 적용"]
}`;
}

/**
 * 🚨 과다 키워드 강제 분산 (스팸 방지)
 * - 최대 허용 횟수(6회)를 초과하는 키워드를 동의어로 대체
 * - 교차 제거: 앞에서 4회 유지, 뒤에서 2회 유지, 중간 초과분 대체
 *
 * @param {string} content - HTML 본문
 * @param {Array<string>} userKeywords - 사용자 입력 키워드
 * @returns {Object} { content, reduced, summary }
 */
function reduceKeywordSpam(content, userKeywords = []) {
  if (!content || !userKeywords || userKeywords.length === 0) {
    return { content, reduced: false, summary: [] };
  }

  const maxAllowed = 6;
  const preserveFront = 4; // 앞에서 4회는 유지 (SEO 중요)
  const preserveBack = 2;  // 뒤에서 2회는 유지 (결론 강조)

  let updatedContent = content;
  const summary = [];

  for (const keyword of userKeywords) {
    // 키워드 등장 위치 찾기
    const regex = new RegExp(keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
    const plainText = updatedContent.replace(/<[^>]*>/g, '');
    const matches = [...plainText.matchAll(regex)];
    const count = matches.length;

    if (count <= maxAllowed) {
      continue; // 허용 범위 내
    }

    const excess = count - maxAllowed;
    console.warn(`🚨 [reduceKeywordSpam] "${keyword}" 과다: ${count}회 → ${excess}회 삭감 필요`);

    // 동의어 목록 생성 (키워드 기반)
    const synonyms = generateKeywordSynonyms(keyword);

    if (synonyms.length === 0) {
      console.warn(`⚠️ [reduceKeywordSpam] "${keyword}" 동의어 없음 - 삭감 불가`);
      continue;
    }

    // 중간 부분 등장을 동의어로 대체 (preserveFront+1 ~ count-preserveBack)
    // HTML에서 직접 대체 (위치 기반)
    let replacedCount = 0;
    let occurrenceIndex = 0;

    updatedContent = updatedContent.replace(regex, (match) => {
      occurrenceIndex++;

      // 앞 4개, 뒤 2개는 유지
      if (occurrenceIndex <= preserveFront || occurrenceIndex > count - preserveBack) {
        return match;
      }

      // 이미 충분히 대체했으면 유지
      if (replacedCount >= excess) {
        return match;
      }

      // 동의어로 대체 (순환 사용)
      const synonym = synonyms[replacedCount % synonyms.length];
      replacedCount++;
      return synonym;
    });

    if (replacedCount > 0) {
      summary.push(`"${keyword}" ${count}회→${count - replacedCount}회 (${replacedCount}회 동의어 대체)`);
      console.log(`✅ [reduceKeywordSpam] "${keyword}" ${replacedCount}회 동의어 대체 완료`);
    }
  }

  return {
    content: updatedContent,
    reduced: summary.length > 0,
    summary
  };
}

/**
 * 키워드 기반 동의어 생성
 * @param {string} keyword - 원본 키워드
 * @returns {Array<string>} 동의어 목록
 */
function generateKeywordSynonyms(keyword) {
  const synonyms = [];
  const lowerKeyword = keyword.toLowerCase();

  // 의료 관련
  if (lowerKeyword.includes('병원') && lowerKeyword.includes('순위')) {
    synonyms.push('의료기관 랭킹', '의료 경쟁력', '의료 수준', '의료 인프라 현황');
  }
  if (lowerKeyword.includes('병원')) {
    synonyms.push('의료기관', '의료시설', '대형 의료기관');
  }

  // 유치 관련
  if (lowerKeyword.includes('유치')) {
    synonyms.push('유치 추진', '유치 목표', '유치 계획');
  }

  // 지역 관련 - 지역명은 유지하고 뒤 단어만 변경
  const regions = ['부산', '서울', '대구', '인천', '광주', '대전', '울산'];
  for (const region of regions) {
    if (lowerKeyword.includes(region)) {
      if (lowerKeyword.includes('순위')) {
        synonyms.push(`${region} 의료 현황`, `${region} 의료 경쟁력`, `${region}지역 의료`);
      }
    }
  }

  // 일반 패턴
  if (lowerKeyword.includes('정책')) {
    synonyms.push('정책 방향', '추진 과제', '핵심 과제');
  }
  if (lowerKeyword.includes('경제')) {
    synonyms.push('경제 발전', '지역 경제', '경제 혁신');
  }
  if (lowerKeyword.includes('교통')) {
    synonyms.push('교통 인프라', '교통 체계', '대중교통');
  }

  // 기본 동의어 (아무것도 매칭 안 되면)
  if (synonyms.length === 0) {
    // 키워드를 분해해서 대체어 생성 시도
    const parts = keyword.split(/\s+/).filter(p => p.length > 1);
    if (parts.length >= 2) {
      synonyms.push(`${parts[0]} 관련 현황`);
      synonyms.push(`${parts[0]} 이슈`);
      synonyms.push(`해당 ${parts[parts.length - 1]}`);
    }
  }

  return synonyms;
}

/**
 * 악성 말투 강제 교정 (최후의 수단)
 */
function forceFixContent(content, userKeywords = []) {
  if (!content) return content;
  let fixed = content;

  // 🚨 [NEW] 과다 키워드 강제 분산 (스팸 방지)
  const spamReduced = reduceKeywordSpam(fixed, userKeywords);
  if (spamReduced.reduced) {
    fixed = spamReduced.content;
    console.log('🚨 [forceFixContent] 과다 키워드 분산:', spamReduced.summary.join(', '));
  }

  // 0. [NEW] 메타 발언 및 주석 제거 (안전장치)
  fixed = fixed.replace(/(관련 데이터|정확한 수치|출처|구체적인 수치|통계)(.*)(확보|확인|검증)(가|이) (필요합니다|바랍니다|요구됩니다|불분명합니다)\.?/gi, '');
  fixed = fixed.replace(/※.*$/gm, ''); // 당구장 표시 주석 제거

  // 1. 🔴 [Phase 1] 이중 변환 방지 (CRITICAL - 반드시 마지막 전에 실행)
  //    "것일 것입니다" → "것입니다" 등 부자연스러운 이중 변환 수정
  const doubleTransformResult = preventDoubleTransformation(fixed);
  if (doubleTransformResult.hadDoubleTransform) {
    console.log('🔧 [forceFixContent] 이중 변환 감지 및 수정:',
      doubleTransformResult.corrections.map(c => c.patternId).join(', '));
    fixed = doubleTransformResult.content;
  }

  // 2. 힘 없는 표현 강화
  fixed = fixed.replace(/노력하겠습니다/g, '반드시 해내겠습니다');

  return fixed;
}

module.exports = {
  refineWithLLM,
  buildCompliantDraft,
  buildFollowupValidation,
  applyHardConstraintsOnly,
  expandContentToTarget
};
