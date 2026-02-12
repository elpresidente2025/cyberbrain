'use strict';
// Force Redeploy: 2026-01-16T22:15:00

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
  validateBipartisanPraise,
  validateKeyPhraseInclusion,
  validateCriticismTarget
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
const { buildNaturalTonePrompt } = require('../../prompts/guidelines/natural-tone');
const {
  buildEditorPrompt: buildEditorPromptFromModule,
  buildExpandPrompt
} = require('../../prompts/builders/editor-prompts');

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
const SUMMARY_HEADING_DETECT_REGEX = /<h[23][^>]*>[^<]*(요약|정리|결론|마무리|맺음말)[^<]*<\/h[23]>/i;
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
  return SUMMARY_HEADING_DETECT_REGEX.test(content) || SUMMARY_TEXT_REGEX.test(content);
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

  // 🚨 [FIX] 제목이 키워드와 똑같으면(예: "박형준 시장") 불충분한 것으로 간주하고 확장
  const isIdenticalToKeyword = primaryKeyword && base.replace(/\s+/g, '') === primaryKeyword.replace(/\s+/g, '');

  if (!base || base.length < 5 || isIdenticalToKeyword) {
    base = primaryKeyword ? `${primaryKeyword} 현안 진단` : '현안 진단 보고';
  }

  if (primaryKeyword && !base.includes(primaryKeyword)) {
    base = `${primaryKeyword} ${base}`.trim();
  }

  base = normalizeSpaces(base);

  // 18자 미만이면 "핵심 점검" 등 추가하여 풍성하게 만듦
  if (base.length < 15) {
    base = normalizeSpaces(`${base} 핵심 분석`);
  }

  return trimTitleToLimit(base, primaryKeyword);
}

function trimTitleToLimit(title, primaryKeyword, limit = 25) {
  const normalized = normalizeSpaces(title);
  if (normalized.length <= limit) return normalized;

  // 1. 구분자 기준으로 자르기 (가장 깔끔)
  const separatorRegex = /\s*[-–—:|·,]\s*/;
  if (separatorRegex.test(normalized)) {
    const parts = normalized.split(separatorRegex).map((part) => part.trim()).filter(Boolean);
    // 첫 부분만 썼을 때 너무 짧으면(5자 미만) 두 번째 부분까지 붙여봄
    if (parts.length > 0) {
      if (parts[0].length > 5 && parts[0].length <= limit) {
        return parts[0];
      }
      // 앞부분이 너무 짧으면 합쳐서 시도
      const combined = `${parts[0]} ${parts[1] || ''}`.trim();
      if (combined.length <= limit) return combined;
    }
  }

  // 2. 단어 단위로 뒤에서부터 줄이기
  const words = normalized.split(' ').filter(Boolean);
  while (words.length > 1 && words.join(' ').length > limit) {
    words.pop();
  }

  const compact = normalizeSpaces(words.join(' '));
  if (compact.length <= limit && compact.length >= 5) return compact;

  // 3. 최후의 수단: Fallback 후보군
  const candidates = [];
  if (primaryKeyword) {
    // 🚨 [FIX] 키워드 단독 사용(예: "박형준 시장")은 제외하여 반복 방지
    candidates.push(`${primaryKeyword} 현안 진단`);
    candidates.push(`${primaryKeyword} 이슈 분석`);
    candidates.push(`${primaryKeyword} 리포트`);
    // candidates.push(primaryKeyword); // ❌ 제거: 키워드만 덜렁 제목으로 나오는 현상 방지
  }
  candidates.push('주요 현안 긴급 진단'); // 기본값도 좀 더 있어보이게 변경
  candidates.push('현안 진단 보고');

  const fallback = candidates.find((candidate) => candidate && candidate.length <= limit);
  return fallback || '주요 현안 보고';
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

  const content = [
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
  dilutionAnalysis = null,  // 🔑 키워드 희석 분석 결과
  // 🔑 [방안 1] 핵심 문구 검증용 파라미터
  extractedKeyPhrases = [],
  responsibilityTarget = null,
  category = ''
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

  // 5. 🔑 [방안 1] 핵심 문구 포함 검증 (논평/시사 카테고리)
  if (extractedKeyPhrases && extractedKeyPhrases.length > 0) {
    const keyPhraseResult = validateKeyPhraseInclusion(content, extractedKeyPhrases);

    if (!keyPhraseResult.passed) {
      // 누락된 핵심 문구가 있음
      const missingPhrases = keyPhraseResult.missing
        .map(p => `"${p.length > 40 ? p.substring(0, 40) + '...' : p}"`)
        .join(', ');

      issues.push({
        type: 'key_phrase_missing',
        severity: 'critical',  // 🔴 최고 우선순위
        description: keyPhraseResult.message || `입장문 핵심 문구 누락: ${missingPhrases}`,
        instruction: `다음 핵심 문구를 본문에 반드시 포함하세요 (혼합 방식: 1개는 원문 그대로, 나머지는 의미 유지 패러프레이즈 허용):\n${extractedKeyPhrases.map((p, i) => `${i + 1}. "${p}"`).join('\n')}`
      });

      console.log('🔴 [EditorAgent] 핵심 문구 누락 감지:', keyPhraseResult.missing.length, '개');
    } else {
      console.log('✅ [EditorAgent] 핵심 문구 검증 통과:', keyPhraseResult.included.length, '개 포함');
    }
  }

  // 5-1. 🔑 [방안 1] 비판 대상 명시 검증 (논평/시사 카테고리)
  if (responsibilityTarget && (category === 'current-affairs' || category.includes('논평'))) {
    const targetResult = validateCriticismTarget(content, responsibilityTarget);

    if (!targetResult.passed) {
      // 🔴 [FIX] 의도 역전 감지 - 비판이 협력/존중으로 변질된 경우
      if (targetResult.hasIntentReversal) {
        issues.push({
          type: 'intent_reversal',
          severity: 'critical',  // 🔴 가장 높은 심각도
          description: targetResult.message || `의도 역전 감지: 비판 대상 "${responsibilityTarget}"이(가) 긍정적 맥락으로 언급됨`,
          instruction: `🚨 [CRITICAL] 원본 참고자료에서 "${responsibilityTarget}"은(는) 비판의 대상입니다.
"협력", "존중", "함께", "노력" 등 긍정적 표현을 사용하지 마세요.
원본의 비판적 논조("역부족", "한계", "문제점" 등)를 그대로 유지하세요.
현재 감지된 긍정 표현 ${targetResult.intentReversalCount}회 vs 비판 표현 ${targetResult.criticismContextCount}회`
        });

        console.log('🔴🔴🔴 [EditorAgent] 의도 역전 감지!:', responsibilityTarget,
          `(긍정: ${targetResult.intentReversalCount}회, 비판: ${targetResult.criticismContextCount}회)`);
      } else {
        // 단순 언급 부족
        issues.push({
          type: 'criticism_target_missing',
          severity: 'high',
          description: targetResult.message || `비판 대상 "${responsibilityTarget}" 언급 부족`,
          instruction: `비판/논평의 대상인 "${responsibilityTarget}"을(를) 본문에서 최소 2회 이상 명시적으로 언급하세요. 모호한 표현("해당 공직자", "그 사람")으로 대체하지 마세요.`
        });

        console.log('🔴 [EditorAgent] 비판 대상 언급 부족:', responsibilityTarget, `(${targetResult.count}회)`);
      }
    }
  }

  // 6. 키워드 희석 문제 (경쟁 구문이 메인 키워드보다 많음)
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
  const prompt = buildEditorPromptFromModule({
    content,
    title,
    issues,
    userKeywords,
    status,
    targetWordCount,
    stripHtml  // 유틸 함수 의존성 주입
  });

  try {
    const response = await callGenerativeModel(prompt, 1, modelName, true, 2200);

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
      // 초당적 협력 금지 표현 후처리 - 카테고리가 'bipartisan-cooperation'일 때만 적용
      // 🔴 [FIX] 기존: 모든 카테고리에 무조건 적용 → 비판 글도 협력 프레임으로 왜곡됨
      // 🟢 [FIX] 수정: bipartisan-cooperation 카테고리일 때만 적용
      const isBipartisanCategory = category === 'bipartisan-cooperation' || category === '초당적 협력';
      let finalContent = nextContent;

      let bipartisanIssues = [];
      if (isBipartisanCategory) {
        const bipartisanResult = validateBipartisanPraise(nextContent, {
          rivalNames: userKeywords.filter(k => k.match(/^[가-힣]{2,4}$/)),
          category: 'bipartisan'
        });
        finalContent = bipartisanResult.correctedContent || nextContent;
        bipartisanIssues = bipartisanResult.issues || [];
      }

      return {
        content: finalContent,
        title: nextTitle,
        edited: true,
        editSummary: [...(result.editSummary || []), ...bipartisanIssues]
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

    // 초당적 협력 금지 표현 후처리 - 카테고리가 'bipartisan-cooperation'일 때만 적용
    // 🔴 [FIX] 기존: 모든 카테고리에 무조건 적용 → 비판 글도 협력 프레임으로 왜곡됨
    let finalContent2 = hardFixed.content || content;
    let bipartisanIssues2 = [];

    if (isBipartisanCategory) {
      const bipartisanResult2 = validateBipartisanPraise(hardFixed.content || content, {
        rivalNames: userKeywords.filter(k => k.match(/^[가-힣]{2,4}$/)),
        category: 'bipartisan'
      });
      finalContent2 = bipartisanResult2.correctedContent || hardFixed.content || content;
      bipartisanIssues2 = bipartisanResult2.issues || [];
    }

    return {
      content: finalContent2,
      title: hardFixed.title || title,
      edited: true,
      editSummary: [
        ...(result.editSummary || issues.map(i => i.description)),
        ...(hardFixed.editSummary || []),
        ...bipartisanIssues2
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

  // 🔧 [수정] 요약 확장 복구 + 최대 800자 제한
  const maxExpansion = 800; // 최대 확장 한도
  const actualExpansion = Math.min(deficit, maxExpansion);

  if (deficit > maxExpansion) {
    console.log(`⚠️ [EditorAgent] 부족분 ${deficit}자 중 ${maxExpansion}자까지만 확장 (할루시네이션 방지)`);
  }

  const prompt = buildExpandPrompt({
    body,
    actualExpansion,
    naturalToneGuide: buildNaturalTonePrompt({ severity: 'strict' })
  });

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

// ============================================================================
// [MIGRATED] buildEditorPrompt 함수가 prompts/builders/editor-prompts.js로 이동됨
// 이 함수는 buildEditorPromptFromModule로 import되어 사용됩니다.
// 이전 코드: 1205-1331줄 (약 127줄) 삭제
// ============================================================================


/**
 * 한글 받침 유무 판별
 * @param {string} word - 검사할 단어
 * @returns {boolean} 받침이 있으면 true
 */
function hasFinalConsonant(word) {
  if (!word || word.length === 0) return false;
  const lastChar = word[word.length - 1];
  const code = lastChar.charCodeAt(0);
  // 한글 유니코드 범위: 0xAC00 ~ 0xD7A3
  if (code < 0xAC00 || code > 0xD7A3) return false;
  // 받침 여부: (code - 0xAC00) % 28 !== 0 이면 받침 있음
  return (code - 0xAC00) % 28 !== 0;
}

/**
 * 조사 변환 매핑 (원본 조사 → 받침 유무에 따른 조사)
 * key: 원본 조사, value: [받침 있을 때, 받침 없을 때]
 */
const JOSA_MAP = {
  '이': ['이', '가'],
  '가': ['이', '가'],
  '을': ['을', '를'],
  '를': ['을', '를'],
  '은': ['은', '는'],
  '는': ['은', '는'],
  '과': ['과', '와'],
  '와': ['과', '와'],
  '으로': ['으로', '로'],
  '로': ['으로', '로'],
  '이라': ['이라', '라'],
  '라': ['이라', '라'],
  '이나': ['이나', '나'],
  '나': ['이나', '나'],
  '이란': ['이란', '란'],
  '란': ['이란', '란'],
  '이든': ['이든', '든'],
  '든': ['이든', '든'],
  '이야': ['이야', '야'],
  '야': ['이야', '야'],
  '이여': ['이여', '여'],
  '여': ['이여', '여'],
  '이고': ['이고', '고'],
  '고': ['이고', '고'],
  '이며': ['이며', '며'],
  '며': ['이며', '며'],
};

/**
 * 동의어에 맞는 조사 변환
 * @param {string} originalJosa - 원본 조사
 * @param {string} synonym - 동의어 (조사 앞 단어)
 * @returns {string} 변환된 조사
 */
function convertJosa(originalJosa, synonym) {
  if (!originalJosa || !synonym) return originalJosa || '';

  const mapping = JOSA_MAP[originalJosa];
  if (!mapping) return originalJosa; // 매핑 없으면 원본 유지

  const hasBatchim = hasFinalConsonant(synonym);
  return hasBatchim ? mapping[0] : mapping[1];
}

/**
 * 🚨 과다 키워드 강제 분산 (스팸 방지)
 * - 최대 허용 횟수(6회)를 초과하는 키워드를 동의어로 대체
 * - 교차 제거: 앞에서 4회 유지, 뒤에서 2회 유지, 중간 초과분 대체
 * - 조사 자동 변환: 동의어 받침에 따라 적절한 조사로 변환
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

  // 조사 패턴 (키워드 뒤에 붙을 수 있는 조사들)
  const josaPattern = '(이|가|을|를|은|는|과|와|으로|로|이라|라|이나|나|이란|란|이든|든|이야|야|이여|여|이고|고|이며|며)?';

  let updatedContent = content;
  const summary = [];

  for (const keyword of userKeywords) {
    // 키워드 + 조사를 함께 캡처하는 정규식
    const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regexWithJosa = new RegExp(`(${escapedKeyword})${josaPattern}`, 'g');

    // 먼저 키워드만으로 등장 횟수 체크
    const keywordOnlyRegex = new RegExp(escapedKeyword, 'g');
    const plainText = updatedContent.replace(/<[^>]*>/g, '');
    const matches = [...plainText.matchAll(keywordOnlyRegex)];
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
    let replacedCount = 0;
    let occurrenceIndex = 0;

    updatedContent = updatedContent.replace(regexWithJosa, (match, _keywordPart, josaPart) => {
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

      // 조사가 있으면 동의어에 맞게 변환
      if (josaPart) {
        const convertedJosa = convertJosa(josaPart, synonym);
        return synonym + convertedJosa;
      }

      return synonym;
    });

    if (replacedCount > 0) {
      summary.push(`"${keyword}" ${count}회→${count - replacedCount}회 (${replacedCount}회 동의어 대체)`);
      console.log(`✅ [reduceKeywordSpam] "${keyword}" ${replacedCount}회 동의어 대체 완료 (조사 자동 변환)`);
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

  // 일반 패턴 (지역명이 있으면 유지)
  const foundRegion = regions.find(r => lowerKeyword.includes(r));

  if (lowerKeyword.includes('정책')) {
    if (foundRegion) {
      synonyms.push(`${foundRegion} 정책 방향`, `${foundRegion} 추진 과제`, `${foundRegion}의 핵심 과제`);
    } else {
      synonyms.push('정책 방향', '추진 과제', '핵심 과제');
    }
  }
  if (lowerKeyword.includes('경제')) {
    if (foundRegion) {
      synonyms.push(`${foundRegion} 경제 발전`, `${foundRegion} 지역경제`, `${foundRegion} 경제 혁신`, `${foundRegion}의 경제`);
    } else {
      synonyms.push('경제 발전', '지역 경제', '경제 혁신');
    }
  }
  if (lowerKeyword.includes('교통')) {
    if (foundRegion) {
      synonyms.push(`${foundRegion} 교통 인프라`, `${foundRegion} 교통 체계`, `${foundRegion} 대중교통`);
    } else {
      synonyms.push('교통 인프라', '교통 체계', '대중교통');
    }
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
