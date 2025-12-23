/**
 * functions/services/guidelines/grounding.js
 * Guideline Grounding 메인 모듈
 *
 * 핵심 기능:
 * 1. 상황에 맞는 지침 선택 (status, category, writingMethod, topic)
 * 2. Primacy/Recency Effect 기반 배치
 * 3. 프롬프트에 주입할 텍스트 생성
 */

'use strict';

const { selectGuidelines, getCriticalChunks } = require('./selector');
const { generateReminder, generateElectionLawReminder } = require('./reminder');
const { buildSEOGuideline } = require('./chunks/seo');

/**
 * 청크를 프롬프트 텍스트로 포맷팅
 *
 * @param {Array} chunks - 청크 배열
 * @param {string} sectionTitle - 섹션 제목
 * @returns {string} 포맷된 텍스트
 */
function formatChunksToText(chunks, sectionTitle = '') {
  if (!chunks || chunks.length === 0) return '';

  const lines = [];

  if (sectionTitle) {
    lines.push(`\n[${sectionTitle}]`);
  }

  for (const chunk of chunks) {
    // 지시문
    lines.push(`• ${chunk.instruction}`);

    // 예시 (첫 번째만)
    if (chunk.examples && chunk.examples.length > 0) {
      const ex = chunk.examples[0];
      lines.push(`  ❌ ${ex.bad}`);
      lines.push(`  ✅ ${ex.good}`);
    }
  }

  return lines.join('\n');
}

/**
 * CRITICAL 지침을 강조 형식으로 포맷팅
 */
function formatCriticalSection(chunks, status) {
  if (!chunks || chunks.length === 0) return '';

  let header = `
╔═══════════════════════════════════════════════════════════════╗
║  🚨 [필수 준수 규칙] - 위반 시 원고 폐기                        ║
╚═══════════════════════════════════════════════════════════════╝
`;

  // 선거법 상태 표시
  if (status === '준비' || status === '현역') {
    header += `\n⚠️ 현재 상태: ${status} (예비후보 등록 이전) - 공약성 표현 금지\n`;
  }

  const body = chunks.map(chunk => {
    let text = `\n▶ ${chunk.instruction}`;

    // 금지 표현 나열
    if (chunk.forbidden && chunk.forbidden.length > 0) {
      const forbiddenList = chunk.forbidden.slice(0, 5).join(', ');
      text += `\n  ❌ 금지: ${forbiddenList}`;
    }

    // 대체 표현 (예시에서 추출)
    if (chunk.examples && chunk.examples.length > 0) {
      text += `\n  ✅ 대신: "${chunk.examples[0].good}"`;
    }

    return text;
  }).join('\n');

  return header + body + '\n';
}

/**
 * HIGH 지침을 포맷팅
 */
function formatHighSection(chunks) {
  if (!chunks || chunks.length === 0) return '';

  const header = `
┌───────────────────────────────────────────────────────────────┐
│  ✅ [품질 규칙]                                                │
└───────────────────────────────────────────────────────────────┘
`;

  const body = chunks.map(chunk => {
    return `• ${chunk.instruction}`;
  }).join('\n');

  return header + body + '\n';
}

/**
 * CONTEXTUAL 지침을 포맷팅 (주제 관련)
 */
function formatContextualSection(chunks, topic) {
  if (!chunks || chunks.length === 0) return '';

  const header = `\n[📌 "${topic?.substring(0, 20) || '주제'}" 관련 주의사항]\n`;

  const body = chunks.map(chunk => {
    return `• ${chunk.instruction}`;
  }).join('\n');

  return header + body + '\n';
}

/**
 * Guideline Grounding 메인 함수
 *
 * 프롬프트 구조:
 * 1. [시작] CRITICAL 지침 (Primacy Effect)
 * 2. [중간] 템플릿 본문 (외부에서 삽입)
 * 3. [후반] HIGH + SEO 지침
 * 4. [끝] CONTEXTUAL + Reminder (Recency Effect)
 *
 * @param {Object} context
 * @param {string} context.status - 사용자 상태
 * @param {string} context.category - 글 카테고리
 * @param {string} context.writingMethod - 작법
 * @param {string} context.topic - 주제
 * @param {Array} context.keywords - SEO 키워드
 * @param {number} context.targetWordCount - 목표 글자수
 * @returns {Object} { prefix, suffix, reminder }
 */
function buildGroundedGuidelines(context) {
  const {
    status,
    category,
    writingMethod,
    topic,
    keywords = [],
    targetWordCount = 2050
  } = context;

  console.log('🔧 Guideline Grounding 시작:', {
    status,
    category,
    writingMethod,
    topic: topic?.substring(0, 30)
  });

  // 1. 지침 선택
  const { critical, high, contextual } = selectGuidelines({
    status,
    category,
    writingMethod,
    topic
  });

  // 2. PREFIX 생성 (프롬프트 시작 - Primacy Effect)
  let prefix = '';

  // CRITICAL 지침 (선거법, 반복 금지 등)
  prefix += formatCriticalSection(critical, status);

  // 3. SUFFIX 생성 (프롬프트 후반)
  let suffix = '';

  // HIGH 지침 (품질 규칙)
  suffix += formatHighSection(high);

  // SEO 지침
  if (keywords.length > 0 || targetWordCount) {
    suffix += `\n${buildSEOGuideline(keywords, targetWordCount)}`;
  }

  // CONTEXTUAL 지침 (주제 관련)
  if (contextual.length > 0) {
    suffix += formatContextualSection(contextual, topic);
  }

  // 4. REMINDER 생성 (프롬프트 끝 - Recency Effect)
  const reminder = generateReminder(critical, { status, topic });

  // 선거법 특화 리마인더 추가
  const electionReminder = generateElectionLawReminder(status);

  console.log('✅ Guideline Grounding 완료:', {
    prefixLength: prefix.length,
    suffixLength: suffix.length,
    reminderLength: reminder.length,
    criticalCount: critical.length,
    highCount: high.length,
    contextualCount: contextual.length
  });

  return {
    prefix,
    suffix,
    reminder: electionReminder + reminder,
    stats: {
      critical: critical.length,
      high: high.length,
      contextual: contextual.length,
      totalChunks: critical.length + high.length + contextual.length
    }
  };
}

/**
 * 간소화된 버전 (용량 최소화)
 */
function buildCompactGuidelines(context) {
  const { status, topic } = context;

  const critical = getCriticalChunks(context);

  // 핵심만 추출
  const essentialRules = critical.slice(0, 3).map(c => c.instruction).join(' | ');

  const prefix = `⚠️ 필수 규칙: ${essentialRules}\n`;

  const reminder = `\n📋 최종 확인: ${essentialRules}`;

  return { prefix, suffix: '', reminder };
}

/**
 * 특정 타입 지침만 추출
 */
function getGuidelinesByType(type, context) {
  const { critical, high, contextual } = selectGuidelines(context);

  const allSelected = [...critical, ...high, ...contextual];

  return allSelected.filter(c => c.type === type);
}

/**
 * 디버그용: 선택된 지침 요약
 */
function summarizeSelectedGuidelines(context) {
  const { critical, high, contextual } = selectGuidelines(context);

  return {
    critical: critical.map(c => c.id),
    high: high.map(c => c.id),
    contextual: contextual.map(c => c.id),
    total: critical.length + high.length + contextual.length
  };
}

module.exports = {
  buildGroundedGuidelines,
  buildCompactGuidelines,
  getGuidelinesByType,
  summarizeSelectedGuidelines,
  formatChunksToText,
  formatCriticalSection,
  formatHighSection
};
