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
const { findUnsupportedNumericTokens } = require('../../utils/fact-guard');

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

const DIAGNOSIS_ACTION_PATTERNS = [
  /대안|해법|해결책|방안|정책\s*방향|정책\s*제안/gi,
  /추진|실행|도입|확대|강화|지원|마련|설립|구축|개선/gi,
  /약속|공약|하겠/gi
];

const DIAGNOSIS_NEUTRAL_SENTENCES = [
  '현황과 원인을 분리해 살펴보는 과정이 중요합니다.',
  '관련 지표와 배경을 객관적으로 정리할 필요가 있습니다.',
  '문제의 구조적 요인을 점검하는 것이 우선입니다.'
];

function getDiagnosisReplacement(index) {
  return DIAGNOSIS_NEUTRAL_SENTENCES[index % DIAGNOSIS_NEUTRAL_SENTENCES.length];
}

function neutralizeDiagnosisContent(content) {
  if (!content || !/<p[^>]*>/i.test(content)) {
    return { content, replaced: 0, replacements: [], issues: [] };
  }

  let replaced = 0;
  let replacementIndex = 0;
  const replacements = [];
  const issues = [];

  const updated = content.replace(/<p[^>]*>[\s\S]*?<\/p>/gi, (match) => {
    const text = match.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
    if (!text) return match;

    const sentences = text.match(/[^.!?]+[.!?]+|[^.!?]+$/g) || [];
    const nextSentences = sentences.map((sentence) => {
      const trimmed = sentence.trim();
      if (!trimmed) return trimmed;

      const isAction = DIAGNOSIS_ACTION_PATTERNS.some((pattern) => pattern.test(trimmed));
      if (!isAction) return trimmed;

      const replacement = getDiagnosisReplacement(replacementIndex);
      replacementIndex += 1;
      replaced += 1;
      replacements.push({ original: trimmed, replaced: replacement });
      issues.push({
        type: 'diagnosis_action',
        severity: 'medium',
        match: trimmed,
        reason: '현안 진단 원고에서 대안/해결/공약 표현을 중립화',
        autoFixed: true
      });
      return replacement;
    });

    return `<p>${nextSentences.join(' ')}</p>`;
  });

  return { content: updated, replaced, replacements, issues };
}


// 🏷️ 제목 필수 조건 (화이트리스트 방식)
const TITLE_REQUIREMENTS = {
  maxLength: 25,
  mustHaveNumber: false,
  noSubtitle: true  // 콤마, 슬래시, 하이픈으로 나눈 부제목 금지
};

function normalizeNumericToken(token) {
  return token.replace(/[\s,]/g, '').replace(/퍼센트/g, '%');
}

function extractNumericTokens(text) {
  if (!text) return [];
  const plainText = text.replace(/<[^>]*>/g, ' ');
  const regex = /\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*(?:%|퍼센트|[가-힣]+)?/g;
  const matches = plainText.match(regex) || [];
  return [...new Set(matches.map(normalizeNumericToken).filter(Boolean))];
}

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
    const factAllowlist = context.factAllowlist || null;
    const category = context.category || '';
    const subCategory = context.subCategory || '';

    // Writer Agent 결과에서 콘텐츠 가져오기
    const writerResult = previousResults.WriterAgent;
    if (!writerResult?.success || !writerResult?.data?.content) {
      throw new Error('Writer Agent 결과가 없습니다');
    }

    let content = writerResult.data.content;
    let title = writerResult.data.title || '';
    const status = userProfile.status || '현역';
    const issues = [];
    const replacements = [];
    const warnings = [];
    const titleIssues = [];

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

    // 6-1. 현안 진단 카테고리: 해법/정책 제안 표현 중화
    if (category === 'current-affairs' && subCategory === 'current_affairs_diagnosis') {
      const diagnosisResult = neutralizeDiagnosisContent(content);
      if (diagnosisResult.replaced > 0) {
        content = diagnosisResult.content;
        issues.push(...diagnosisResult.issues);
        replacements.push(...diagnosisResult.replacements);
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

    // 🏷️ 10. 제목 검증 (금지 표현, 길이)
    if (title && title.trim()) {
      const titleValidation = this.checkTitle(title, content);
      titleIssues.push(...titleValidation.issues);
      issues.push(...titleValidation.issues);
    } else {
      // 제목 미존재도 high 이슈로 처리 → passed: false → 재검증 루프 트리거
      const noTitleIssue = {
        type: 'title_missing',
        severity: 'high',
        reason: '제목이 없거나 비어있음',
        current: title || '(없음)',
        suggestion: '25자 이내, 숫자 포함, 키워드 앞배치 제목 필요'
      };
      titleIssues.push(noTitleIssue);
      issues.push(noTitleIssue);
    }

    // 11. 구조 검증 (무한 루프 방지)
    // 10-1. 수치 근거 검증 (팩트 체크)
    if (factAllowlist) {
      const contentCheck = findUnsupportedNumericTokens(content, factAllowlist);
      if (!contentCheck.passed) {
        console.warn('⚠️ [ComplianceAgent] 근거 없는 수치 감지(본문):', contentCheck.unsupported);
      }

      if (title && title.trim()) {
        const titleCheck = findUnsupportedNumericTokens(title, factAllowlist);
        if (!titleCheck.passed) {
          console.warn('⚠️ [ComplianceAgent] 근거 없는 수치 감지(제목):', titleCheck.unsupported);
        }
      }
    }

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
      title,  // 🏷️ 제목도 반환
      issues,
      titleIssues,  // 🏷️ 제목 관련 이슈 별도 반환
      replacements,
      warnings,
      summary: passed
        ? '검수 통과'
        : `${criticalCount + highCount}개의 심각한 문제 발견${titleIssues.length > 0 ? ` (제목 문제 ${titleIssues.length}개)` : ''}`,
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

  /**
   * 🏷️ 제목 검증 (화이트리스트 방식 - 필수 조건 체크)
   *
   * 필수 조건 4가지:
   * 1. 25자 이내
   * 2. 본문 수치 기반 숫자 포함 (본문에 수치 없으면 예외)
   * 3. 단일 문장 (부제목 구분자 없음)
   * 4. 키워드가 앞에 위치 (선택)
   */
  checkTitle(title, content = '') {
    const issues = [];
    const titleNumericTokens = extractNumericTokens(title);
    const contentNumericTokens = extractNumericTokens(content);
    const hasContentNumbers = contentNumericTokens.length > 0;

    // 【조건 1】 25자 이내
    if (title.length > TITLE_REQUIREMENTS.maxLength) {
      issues.push({
        type: 'title_length',
        severity: 'high',
        reason: `제목 ${title.length}자 → 25자 이내로`,
        current: title,
        suggestion: '불필요한 단어 제거. 예: "부산 대형병원 5곳 응급실 확대"'
      });
    }

    // 【조건 2】 숫자 1개 이상 포함 (본문에 숫자가 있을 때만)
    if (TITLE_REQUIREMENTS.mustHaveNumber && hasContentNumbers && titleNumericTokens.length === 0) {
      issues.push({
        type: 'title_no_number',
        severity: 'high',
        reason: '본문에 수치가 있는데 제목에 숫자 없음',
        current: title,
        suggestion: `본문에 있는 수치를 제목에 포함. 예: "${contentNumericTokens[0] || '27위'}" 활용`
      });
    }

    // 【조건 2-1】 제목 수치가 본문과 불일치
    if (titleNumericTokens.length > 0) {
      if (!hasContentNumbers) {
        issues.push({
          type: 'title_number_mismatch',
          severity: 'high',
          reason: '제목 수치에 대한 본문 근거 없음',
          current: title,
          suggestion: '본문에 실제로 있는 수치/단위를 제목에 사용하거나 숫자를 제거'
        });
      } else {
        const missingTokens = titleNumericTokens.filter(token => !contentNumericTokens.includes(token));
        if (missingTokens.length > 0) {
          issues.push({
            type: 'title_number_mismatch',
            severity: 'high',
            reason: `제목 수치/단위가 본문과 불일치: ${missingTokens.join(', ')}`,
            current: title,
            suggestion: `본문에 있는 수치로 교체 (예: ${contentNumericTokens.slice(0, 2).join(', ') || '28개사'})`
          });
        }
      }
    }

    // 【조건 3】 단일 문장 (부제목 구분자 없음)
    if (TITLE_REQUIREMENTS.noSubtitle) {
      const hasSubtitle =
        title.includes(' - ') ||  // 하이픈
        title.includes(': ') ||   // 콜론
        title.includes('/');      // 슬래시

      if (hasSubtitle) {
        issues.push({
          type: 'title_has_subtitle',
          severity: 'high',
          reason: '부제목 패턴 금지 (-, :, /)',
          current: title,
          suggestion: '단일 문장으로. 예: "부산 대형병원 5곳 응급실 24시간 운영"'
        });
      }
    }

    // 【조건 4】 선거법 위반 표현 (제목에 "약속", "공약" 금지)
    const electionBannedWords = ['약속', '공약'];
    for (const word of electionBannedWords) {
      if (title.includes(word)) {
        issues.push({
          type: 'title_election_violation',
          severity: 'critical',
          reason: `제목에 선거법 위반 표현 "${word}" 포함`,
          current: title,
          suggestion: `"${word}"을 "비전", "정책 방향", "계획" 등으로 교체`
        });
      }
    }

    if (issues.length > 0) {
      console.log(`🏷️ [ComplianceAgent] 제목 필수조건 미충족:`, issues.map(i => i.reason).join(' | '));
    }

    return { issues };
  }
}

module.exports = { ComplianceAgent };
