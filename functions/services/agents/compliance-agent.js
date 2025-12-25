'use strict';

/**
 * Compliance Agent - 선거법/당론 검수
 *
 * 역할:
 * - 선거법 위반 표현 검출
 * - 당론 적합성 검증
 * - 정치적 리스크 표현 필터링
 */

const { BaseAgent } = require('./base');

// 선거법 위반 패턴
const ELECTION_LAW_PATTERNS = [
  { pattern: /투표\s*해\s*주세요|투표\s*부탁/gi, replacement: '관심 가져주세요', severity: 'high' },
  { pattern: /기호\s*\d+번/gi, replacement: '', severity: 'high' },
  { pattern: /공약\s*이행/gi, replacement: '정책 방향', severity: 'medium' },
  { pattern: /당선\s*시키/gi, replacement: '함께 해주시', severity: 'high' },
  { pattern: /경쟁\s*후보|상대\s*후보|맞상대/gi, replacement: '', severity: 'medium' }
];

// 정치적 리스크 표현
const RISK_PATTERNS = [
  { pattern: /명백한\s*거짓|새빨간\s*거짓말/gi, severity: 'high', reason: '명예훼손 위험' },
  { pattern: /무능|무책임한\s*정부/gi, severity: 'medium', reason: '과격한 비판' },
  { pattern: /빨갱이|종북/gi, severity: 'high', reason: '혐오 표현' }
];

class ComplianceAgent extends BaseAgent {
  constructor() {
    super('ComplianceAgent');
  }

  getRequiredContext() {
    return ['previousResults'];
  }

  async execute(context) {
    const { previousResults = {}, userProfile = {} } = context;

    // Writer Agent 결과에서 콘텐츠 가져오기
    const writerResult = previousResults.WriterAgent;
    if (!writerResult?.success || !writerResult?.data?.content) {
      throw new Error('Writer Agent 결과가 없습니다');
    }

    let content = writerResult.data.content;
    const status = userProfile.status || '현역';
    const issues = [];
    const replacements = [];

    // 1. 선거법 검수 (사용자 상태에 따라)
    if (['후보', '예비후보', '준비'].includes(status)) {
      for (const rule of ELECTION_LAW_PATTERNS) {
        const matches = content.match(rule.pattern);
        if (matches) {
          issues.push({
            type: 'election_law',
            severity: rule.severity,
            matches: matches,
            suggestion: rule.replacement || '삭제 권장'
          });

          // 자동 치환
          if (rule.replacement !== undefined) {
            content = content.replace(rule.pattern, rule.replacement);
            replacements.push({
              original: matches[0],
              replaced: rule.replacement || '(삭제됨)'
            });
          }
        }
      }
    }

    // 2. 정치적 리스크 검수
    for (const rule of RISK_PATTERNS) {
      const matches = content.match(rule.pattern);
      if (matches) {
        issues.push({
          type: 'political_risk',
          severity: rule.severity,
          matches: matches,
          reason: rule.reason
        });
      }
    }

    // 3. 가족 환각 검수
    if (userProfile.familyStatus === '미혼' || userProfile.familyStatus === '기혼(자녀 없음)') {
      const familyPatterns = [
        /우리\s*아이|자녀를\s*키우|아이들의\s*미래/gi,
        /학부모로서|부모\s*입장에서/gi
      ];

      for (const pattern of familyPatterns) {
        const matches = content.match(pattern);
        if (matches) {
          issues.push({
            type: 'hallucination',
            severity: 'high',
            matches: matches,
            reason: '프로필과 불일치 (자녀 없음)'
          });
        }
      }
    }

    // 4. 종합 판단
    const highSeverityCount = issues.filter(i => i.severity === 'high').length;
    const passed = highSeverityCount === 0;

    return {
      passed,
      content,  // 치환된 콘텐츠
      issues,
      replacements,
      summary: passed
        ? '검수 통과'
        : `${highSeverityCount}개의 심각한 문제 발견`,
      score: Math.max(0, 10 - (highSeverityCount * 3) - (issues.length - highSeverityCount))
    };
  }
}

module.exports = { ComplianceAgent };
