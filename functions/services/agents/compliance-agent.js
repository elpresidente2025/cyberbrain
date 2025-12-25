'use strict';

/**
 * Compliance Agent - 선거법/당론 검수 (통합 리팩토링 버전)
 *
 * 역할:
 * - 선거법 위반 표현 검출 및 치환
 * - 당론 적합성 검증
 * - 정치적 리스크 표현 필터링
 * - 환각(Hallucination) 방지 검수
 *
 * prompts/guidelines의 규칙들을 import하여 사용
 */

const { BaseAgent } = require('./base');

// ✅ 기존 guidelines import (구조적 통합 강화)
const { getElectionStage, getPolicySafe, ELECTION_EXPRESSION_RULES } = require('../../prompts/guidelines/legal');
const { OVERRIDE_KEYWORDS, HIGH_RISK_KEYWORDS, POLITICAL_FRAMES } = require('../../prompts/guidelines/framingRules');

// 선거법 위반 패턴 (단계별)
const ELECTION_LAW_PATTERNS = {
  // 모든 단계에서 금지
  universal: [
    { pattern: /기호\s*\d+번/gi, replacement: '', severity: 'critical', reason: '기호 표시 금지' },
    { pattern: /빨갱이|종북|수꼴/gi, replacement: '', severity: 'critical', reason: '혐오 표현' },
    { pattern: /사기꾼|착복|횡령|뇌물/gi, replacement: '', severity: 'critical', reason: '명예훼손 위험' }
  ],

  // 준비/예비후보 단계 (공직선거법 사전선거운동 금지)
  pre_registration: [
    { pattern: /투표\s*해\s*주세요|투표\s*부탁/gi, replacement: '관심 가져주세요', severity: 'high' },
    { pattern: /당선\s*시키|당선\s*되면/gi, replacement: '함께 해주시면', severity: 'high' },
    { pattern: /공약\s*이행|공약을\s*약속/gi, replacement: '정책 방향 제시', severity: 'high' },
    { pattern: /저를\s*뽑아|선택해\s*주세요/gi, replacement: '관심 가져주세요', severity: 'high' },
    { pattern: /~하겠습니다(?=.*공약|약속)/gi, replacement: '~을 제안합니다', severity: 'medium' }
  ],

  // 후보자 단계
  candidate: [
    { pattern: /경쟁\s*후보|상대\s*후보|맞상대/gi, replacement: '', severity: 'medium', reason: '비방 위험' },
    { pattern: /상대\s*진영|상대\s*당/gi, replacement: '', severity: 'medium' }
  ]
};

// 정치적 리스크 패턴
const RISK_PATTERNS = [
  { pattern: /명백한\s*거짓|새빨간\s*거짓말/gi, severity: 'high', reason: '명예훼손 위험' },
  { pattern: /무능|무책임한\s*정부/gi, severity: 'medium', reason: '과격한 비판' },
  { pattern: /망했|망조|파탄/gi, severity: 'medium', reason: '과격한 표현' }
];

// 자당 비판 위험 패턴 (framingRules.js의 HIGH_RISK_KEYWORDS 활용)
const SELF_CRITICISM_PATTERNS = HIGH_RISK_KEYWORDS.SELF_CRITICISM.map(keyword => ({
  pattern: new RegExp(keyword, 'gi'),
  severity: 'medium',
  reason: '자당 비판 위험',
  needsFraming: true
}));

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
    const warnings = [];

    // 1. Firestore에서 동적 정책 로드 (옵션)
    let dynamicPolicy = null;
    try {
      dynamicPolicy = await getPolicySafe();
      console.log(`📋 [ComplianceAgent] 동적 정책 로드 (v${dynamicPolicy.version})`);
    } catch (policyError) {
      console.warn('⚠️ [ComplianceAgent] 동적 정책 로드 실패, 기본 규칙 사용');
    }

    // 2. 선거 단계 확인
    const electionStage = getElectionStage(status);
    console.log(`🗳️ [ComplianceAgent] 선거 단계: ${electionStage?.name || 'NONE'}`);

    // 3. 범용 금지어 검수
    for (const rule of ELECTION_LAW_PATTERNS.universal) {
      const result = this.checkAndReplace(content, rule);
      if (result.found) {
        content = result.content;
        issues.push(...result.issues);
        replacements.push(...result.replacements);
      }
    }

    // 4. 동적 정책의 금지어 검수
    if (dynamicPolicy?.bannedKeywords) {
      for (const keyword of dynamicPolicy.bannedKeywords) {
        const pattern = new RegExp(keyword, 'gi');
        const matches = content.match(pattern);
        if (matches) {
          issues.push({
            type: 'policy_violation',
            severity: 'high',
            matches,
            reason: `금지어 사용: ${keyword}`
          });
          content = content.replace(pattern, '');
          replacements.push({ original: keyword, replaced: '(삭제됨)' });
        }
      }
    }

    // 5. 🗳️ 선거 단계별 검수 (legal.js 구조적 통합)
    if (electionStage) {
      const legalCheckResult = this.applyLegalJsRules(content, electionStage);
      content = legalCheckResult.content;
      issues.push(...legalCheckResult.issues);
      replacements.push(...legalCheckResult.replacements);
    }

    // 6. 기존 패턴 보조 검수 (universal이 아닌 추가 패턴)
    if (['후보', '예비후보'].includes(status)) {
      for (const rule of ELECTION_LAW_PATTERNS.candidate) {
        const result = this.checkAndReplace(content, rule);
        if (result.found) {
          content = result.content;
          issues.push(...result.issues);
          replacements.push(...result.replacements);
        }
      }
    }

    // 7. 정치적 리스크 검수
    for (const rule of RISK_PATTERNS) {
      const matches = content.match(rule.pattern);
      if (matches) {
        issues.push({
          type: 'political_risk',
          severity: rule.severity,
          matches,
          reason: rule.reason
        });
      }
    }

    // 8. 자당 비판 위험 검수 (프레이밍 필요 여부 체크)
    const isOverridden = this.checkOverrideKeywords(content);
    if (!isOverridden) {
      for (const rule of SELF_CRITICISM_PATTERNS) {
        const matches = content.match(rule.pattern);
        if (matches) {
          warnings.push({
            type: 'self_criticism_risk',
            severity: rule.severity,
            matches,
            reason: rule.reason,
            suggestion: '건설적 비판 프레이밍 적용 권장'
          });
        }
      }
    }

    // 9. 가족 환각 검수
    if (userProfile.familyStatus === '미혼' || userProfile.familyStatus === '기혼(자녀 없음)') {
      const familyPatterns = [
        { pattern: /우리\s*아이|제\s*아이|자녀를\s*키우/gi, reason: '자녀 언급 (프로필: 자녀 없음)' },
        { pattern: /아이들의\s*미래|자녀\s*교육/gi, reason: '자녀 관련 표현' },
        { pattern: /학부모로서|부모\s*입장에서/gi, reason: '부모 역할 언급' }
      ];

      for (const rule of familyPatterns) {
        const matches = content.match(rule.pattern);
        if (matches) {
          issues.push({
            type: 'hallucination',
            severity: 'high',
            matches,
            reason: rule.reason
          });
          // 자동 치환
          content = content.replace(rule.pattern, '');
          replacements.push({ original: matches[0], replaced: '(삭제됨 - 프로필 불일치)' });
        }
      }
    }

    // 10. 구조 검증 (무한 루프 방지)
    const structureIssues = this.checkStructure(content);
    issues.push(...structureIssues);

    // 11. 종합 판단
    const criticalCount = issues.filter(i => i.severity === 'critical').length;
    const highCount = issues.filter(i => i.severity === 'high').length;
    const passed = criticalCount === 0 && highCount === 0;

    // 점수 계산 (10점 만점)
    const score = Math.max(0, 10 - (criticalCount * 5) - (highCount * 2) - (issues.length - criticalCount - highCount) * 0.5);

    console.log(`✅ [ComplianceAgent] 검수 완료`, {
      passed,
      issues: issues.length,
      replacements: replacements.length,
      score
    });

    return {
      passed,
      content,
      issues,
      replacements,
      warnings,
      summary: passed
        ? '검수 통과'
        : `${criticalCount + highCount}개의 심각한 문제 발견`,
      score,
      electionStage: electionStage?.name || null,
      policyVersion: dynamicPolicy?.version || null
    };
  }

  /**
   * 패턴 검사 및 치환
   */
  checkAndReplace(content, rule) {
    const matches = content.match(rule.pattern);
    if (!matches) {
      return { found: false, content, issues: [], replacements: [] };
    }

    const issues = [{
      type: 'election_law',
      severity: rule.severity,
      matches,
      reason: rule.reason || '선거법 위반 표현',
      suggestion: rule.replacement || '삭제 권장'
    }];

    const replacements = [];
    let newContent = content;

    if (rule.replacement !== undefined) {
      newContent = content.replace(rule.pattern, rule.replacement);
      replacements.push({
        original: matches[0],
        replaced: rule.replacement || '(삭제됨)'
      });
    }

    return { found: true, content: newContent, issues, replacements };
  }

  /**
   * 🗳️ legal.js 선거법 규칙 적용 (구조적 통합)
   * electionStage의 forbidden 패턴과 replacements를 직접 사용
   */
  applyLegalJsRules(content, electionStage) {
    const issues = [];
    const replacements = [];
    let modifiedContent = content;

    if (!electionStage || !electionStage.forbidden) {
      return { content: modifiedContent, issues, replacements };
    }

    console.log(`🗳️ [ComplianceAgent] legal.js 규칙 적용: ${electionStage.name}`);

    // 1. forbidden 패턴 검사
    const stageReplacements = electionStage.replacements || {};

    for (const [category, patterns] of Object.entries(electionStage.forbidden)) {
      for (const pattern of patterns) {
        const matches = modifiedContent.match(pattern);
        if (matches) {
          // 각 매치에 대해 치환 시도
          for (const match of matches) {
            const replacement = stageReplacements[match] || stageReplacements[match.replace(/\s+/g, ' ')];

            if (replacement !== undefined) {
              // 치환 가능한 경우
              modifiedContent = modifiedContent.replace(match, replacement);
              replacements.push({
                original: match,
                replaced: replacement || '(삭제됨)',
                category
              });
            }

            issues.push({
              type: 'election_law_legal_js',
              severity: category === 'status' || category === 'pledge' ? 'high' : 'medium',
              match,
              category,
              reason: `선거법 위반 (${electionStage.name}/${category})`,
              autoFixed: replacement !== undefined
            });
          }
        }
      }
    }

    // 2. 리터럴 치환 (정규식 매칭 안 된 단순 문자열도 치환)
    for (const [original, replacement] of Object.entries(stageReplacements)) {
      if (modifiedContent.includes(original)) {
        const before = modifiedContent;
        modifiedContent = modifiedContent.split(original).join(replacement);
        if (before !== modifiedContent) {
          replacements.push({
            original,
            replaced: replacement || '(삭제됨)',
            category: 'literal_replacement'
          });
        }
      }
    }

    console.log(`🗳️ [ComplianceAgent] legal.js 규칙 적용 완료: ${issues.length}개 이슈, ${replacements.length}개 치환`);

    return { content: modifiedContent, issues, replacements };
  }

  /**
   * 프레이밍 비활성화 예외 체크 (야당 비판 등)
   */
  checkOverrideKeywords(content) {
    const allOverrides = [
      ...OVERRIDE_KEYWORDS.PAST_GOVERNMENT,
      ...OVERRIDE_KEYWORDS.OPPOSITION_CRITICISM
    ];
    return allOverrides.some(keyword => content.includes(keyword));
  }

  /**
   * 구조 검증 (무한 루프, 중복 문단 등)
   */
  checkStructure(content) {
    const issues = [];

    // 마무리 인사 후 본문 반복 체크
    const closingPatterns = /감사합니다|사랑합니다|고맙습니다/gi;
    const closingMatch = content.match(closingPatterns);
    if (closingMatch) {
      const lastClosingIndex = content.lastIndexOf(closingMatch[closingMatch.length - 1]);
      const afterClosing = content.substring(lastClosingIndex + 10);
      if (afterClosing.length > 100 && /<p>/i.test(afterClosing)) {
        issues.push({
          type: 'structure',
          severity: 'medium',
          reason: '마무리 인사 후 본문 계속됨 (무한 루프 의심)'
        });
      }
    }

    // 문장 미완결 체크
    const sentences = content.replace(/<[^>]*>/g, '').split(/[.!?]/);
    const incompleteCount = sentences.filter(s =>
      s.trim().length > 20 && !s.trim().endsWith('다') && !s.trim().endsWith('요')
    ).length;

    if (incompleteCount > 3) {
      issues.push({
        type: 'structure',
        severity: 'low',
        reason: `${incompleteCount}개의 불완전한 문장 의심`
      });
    }

    return issues;
  }
}

module.exports = { ComplianceAgent };
