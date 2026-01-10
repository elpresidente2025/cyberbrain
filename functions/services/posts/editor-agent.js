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
const {
  stripHtml,
  splitContentBySignature,
  joinContent
} = require('./content-processor');

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
  const maxTargetCount = targetWordCount ? Math.round(targetWordCount * 1.1) : null;
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
    const maxTarget = maxTargetCount || Math.round(targetWordCount * 1.1);
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

  // 🌟 [NEW] 최후의 말투 교정 (강제 치환)
  updatedContent = forceFixContent(updatedContent);

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

    // 🆕 분량 부족 시 우선적으로 본문 확장 시도 (요약문 생성 및 삽입)
    const lengthIssue = issues.find(i => i.type === 'content_length' && i.description.includes('분량 부족'));
    if (lengthIssue && typeof targetWordCount === 'number') {
      console.log(`📉 [EditorAgent] 분량 부족 감지 (${lengthIssue.description}) -> 요약문 생성 및 확장 시도`);
      const expansionResult = await expandContentToTarget({
        content,
        targetWordCount,
        modelName,
        status
      });

      if (expansionResult.edited) {
        content = expansionResult.content;
        // 분량이 채워졌다고 가정하고 이슈 목록에서 제거하거나, 재검증 로직에 의해 다음 루프에서 처리됨
        // 여기서는 일단 content를 업데이트하고 계속 진행 (다른 이슈들도 고쳐야 하므로)
        console.log('✅ [EditorAgent] 분량 확장/요약문 삽입 완료');
      }
    }

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
  const maxTarget = Math.round(targetWordCount * 1.1);

  if (currentLength >= targetWordCount) {
    return { content, edited: false };
  }

  const deficit = targetWordCount - currentLength;
  console.log(`📊 [EditorAgent] 분량 부족: ${deficit}자 필요 (현재 ${currentLength} / 목표 ${targetWordCount})`);

  // 사용자 요청: 본론 요약문 생성하여 결론 앞에 삽입
  const prompt = `
당신은 전문 원고 교정가입니다.
현재 원고의 분량이 **${deficit}자** 부족합니다.
아래 [본문]의 핵심 내용을 **구체적으로 요약 및 재진술**하여, **정확히 ${Math.max(deficit, 300)}자** 분량의 새로운 문단들을 작성해 주십시오.

[지시사항]
1. **분량 필수**: 반드시 **${Math.max(deficit, 300)}자 이상**의 텍스트가 나와야 합니다. (너무 짧으면 안 됨)
2. **위치**: 이 내용은 **'결론' 바로 앞**에 삽입될 것입니다.
3. **내용**: 앞선 본론(1,2,3)의 내용을 종합적으로 아우르면서, 독자에게 다시 한번 강조하는 "종합 요약" 성격으로 쓰십시오.
4. **형식**: <p> 태그로 감싸진 2~3개의 문단으로 작성하십시오. 소제목(H2)은 쓰지 마십시오.
5. **어조**: 원문의 어조(합쇼체)를 유지하십시오.

[본문]
${body}

다음 JSON 형식으로만 응답하세요:
{
  "summaryBlock": "<p>...요약 내용 1...</p><p>...요약 내용 2...</p>"
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
  const maxTarget = typeof targetWordCount === 'number' ? Math.round(targetWordCount * 1.1) : null;
  const lengthGuideline = hasLengthIssue && typeof targetWordCount === 'number'
    ? `\n📏 분량 목표: ${targetWordCount}~${maxTarget}자(공백 제외), 현재 ${currentLength}자\n- 새 주제/추신/요약 추가 금지\n- 기존 문단의 근거를 구체화해 분량을 맞출 것`
    : '';

  // 🆕 키워드 과다 사용 체크 및 변주 가이드 생성
  const keywordAnalysis = analyzeKeywordUsage(content, userKeywords);
  const keywordVariationGuide = buildKeywordVariationGuide(keywordAnalysis);

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

  const structureGuideline = `
╔═══════════════════════════════════════════════════════════════╗
║  🚨 [CRITICAL] 5단 구조 유지 필수 (황금 비율)                 ║
╚═══════════════════════════════════════════════════════════════╝
1. 전체 구조: **[서론] - [본론1] - [본론2] - [본론3] - [결론]** (총 5개 섹션 유지)
2. 문단 규칙: **각 섹션은 반드시 3개의 문단**으로 구성하세요. (총 15문단)
3. 길이 규칙: **한 문단은 120~150자** 내외로 짧게 끊어 쓰세요.
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
     - **"~라는 점입니다", "~것이라는 점입니다"** 패턴은 발견 즉시 삭제하거나 자연스러운 종결어미("**~입니다**", "**~합니다**", "**~것입니다**")로 고쳐 쓰세요. (문장을 분해해서라도 반드시 수정)
     - **"노력하겠습니다"** 보다는 **"반드시 해내겠습니다"** 또는 **"완수하겠습니다"** 같은 단호한 표현을 쓰세요.
     - **"하고 있습니다", "하고자 합니다"** 같은 진행형/유보적 표현을 금지하고, **"합니다", "약속합니다"**로 명확히 끝내세요.

  2. **[CRITICAL] 정치적 화법 준수**:
     - 후원회장이나 지지자는 '조력자'일 뿐입니다. 공약은 후보자인 **'저'** 또는 **'제가'** 직접 약속하는 형식을 취하세요.
     - 외부(정부/당) 정책 인용 시, "윤석열 정부의 정책을 **제가 부산에서 완성하겠습니다**"와 같이 주체성을 확보하세요.

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
     - 키워드는 문맥에 맞게 자연스럽게 녹이되, 전체 글에서 **최대 5~6회**까지만 사용하세요. (과도한 반복 금지)
     - 숫자나 통계는 원문에 있는 것만 정확히 인용하세요.

  5. **[최소한의 수정 원칙]**:
     - 위 문제들이 없는 문장은 원문의 맛을 살려 그대로 두세요.
     - 선거법 위반 표현만 완곡하게 다듬으세요.
${keywordVariationGuide}
다음 JSON 형식으로만 응답하세요:
{
  "title": "수정된 제목",
  "content": "수정된 본문 (HTML) - h2, h3, p 태그 구조 준수",
  "editSummary": ["~라는 점입니다 말투 수정", "소제목 태그 적용"]
}`;
}

/**
 * 악성 말투 강제 교정 (최후의 수단)
 */
function forceFixContent(content) {
  if (!content) return content;
  let fixed = content;

  // 0. [NEW] 메타 발언 및 주석 제거 (안전장치)
  fixed = fixed.replace(/(관련 데이터|정확한 수치|출처|구체적인 수치|통계)(.*)(확보|확인|검증)(가|이) (필요합니다|바랍니다|요구됩니다|불분명합니다)\.?/gi, '');
  fixed = fixed.replace(/※.*$/gm, ''); // 당구장 표시 주석 제거

  // 1. "~라는 점입니다" 계열 제거 -> content-processor.js로 이관 (중복 제거)
  // 🗑️ 삭제됨: 규칙 통합을 위해 content-processor.js에서만 처리

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
