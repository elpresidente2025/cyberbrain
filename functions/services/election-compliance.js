/**
 * functions/services/election-compliance.js
 * 선거법 준수 검사 서비스
 */

const { ELECTION_TYPES, ELECTION_MILESTONES, CONTENT_RESTRICTIONS, WARNING_MESSAGES, ElectionCalendarUtils } = require('../constants/election-calendar');
const { ELECTION_EXPRESSION_RULES, getElectionStage } = require('../prompts/guidelines/legal');

/**
 * 원고 생성 전 선거법 준수 검사
 * @param {Object} params
 * @param {string} params.userId - 사용자 ID
 * @param {string} params.contentType - 콘텐츠 유형
 * @param {string} params.category - 카테고리
 * @param {string} params.topic - 주제
 * @returns {Promise<Object>} 검사 결과
 */
async function checkElectionCompliance(params) {
  const { userId, contentType, category, topic } = params;
  
  try {
    // 1. 사용자의 선거 정보 조회 (향후 DB에서 가져올 예정)
    const userElectionInfo = await getUserElectionInfo(userId);
    
    if (!userElectionInfo || !userElectionInfo.electionDate) {
      return {
        allowed: true,
        phase: 'NO_ELECTION',
        warnings: [],
        restrictions: []
      };
    }

    // 2. 현재 선거 단계 판단
    const currentPhase = ElectionCalendarUtils.getCurrentPhase(
      new Date(userElectionInfo.electionDate),
      userElectionInfo.electionType
    );

    // 3. 콘텐츠 유형별 제한 검사
    const contentRestriction = ElectionCalendarUtils.checkContentRestriction(
      getContentTypeFromCategory(category, topic),
      currentPhase
    );

    // 4. 키워드 기반 추가 검사
    const keywordCheck = checkRestrictedKeywords(topic, currentPhase);

    // 5. 결과 반환
    const result = {
      allowed: contentRestriction.allowed && keywordCheck.allowed,
      phase: currentPhase,
      warnings: [],
      restrictions: [],
      suggestions: [],
      electionInfo: {
        type: userElectionInfo.electionType,
        date: userElectionInfo.electionDate,
        daysUntilElection: Math.ceil((new Date(userElectionInfo.electionDate) - new Date()) / (1000 * 60 * 60 * 24))
      }
    };

    // 6. 경고 및 제한사항 추가
    if (contentRestriction.warning || keywordCheck.warning) {
      result.warnings.push(WARNING_MESSAGES[currentPhase]);
    }

    if (!contentRestriction.allowed) {
      result.restrictions.push(`현재 단계에서는 '${contentType}' 유형의 콘텐츠 생성이 제한됩니다.`);
    }

    if (keywordCheck.restrictedKeywords.length > 0) {
      result.restrictions.push(`다음 키워드 사용이 제한됩니다: ${keywordCheck.restrictedKeywords.join(', ')}`);
    }

    // 7. 개선 제안 추가
    if (currentPhase === 'PRE_CAMPAIGN_WARNING') {
      result.suggestions.push('투표 요청 표현 대신 정책 설명에 집중하세요');
      result.suggestions.push('개인 홍보보다는 지역 현안 해결 방안을 제시하세요');
    }

    return result;

  } catch (error) {
    console.error('Election compliance check failed:', error);
    return {
      allowed: true,
      phase: 'ERROR',
      warnings: [{ title: '시스템 오류', message: '선거법 검사 중 오류가 발생했습니다. 수동으로 확인해주세요.' }]
    };
  }
}

/**
 * 사용자 선거 정보 조회 (임시 구현)
 * @param {string} userId 
 * @returns {Promise<Object>} 
 */
async function getUserElectionInfo(userId) {
  // TODO: Firestore에서 사용자의 선거 정보 조회
  // 현재는 임시로 하드코딩
  return {
    electionType: 'LOCAL_GOVERNMENT',
    electionDate: '2026-06-03', // 제9회 전국동시지방선거
    position: '광역의원',
    constituency: '서울특별시 강남구'
  };
}

/**
 * 카테고리와 주제로부터 콘텐츠 유형 추출
 * @param {string} category 
 * @param {string} topic 
 * @returns {string}
 */
function getContentTypeFromCategory(category, topic) {
  const topicLower = (topic || '').toLowerCase();
  
  // 키워드 기반 분류
  if (topicLower.includes('투표') || topicLower.includes('지지') || topicLower.includes('후보')) {
    return 'VOTE_REQUEST';
  }
  
  if (topicLower.includes('정책') || topicLower.includes('공약') || category === 'policy') {
    return 'POLICY_STATEMENT';
  }
  
  if (topicLower.includes('성과') || topicLower.includes('실적') || category === 'achievement') {
    return 'ACHIEVEMENT_PROMOTION';
  }
  
  return 'PERSONAL_INTRODUCTION';
}

/**
 * 제한 키워드 검사
 * @param {string} topic 
 * @param {string} phase 
 * @returns {Object}
 */
function checkRestrictedKeywords(topic, phase) {
  const restrictedKeywords = {
    'PRE_CAMPAIGN_WARNING': [
      '투표해주세요', '지지해주세요', '뽑아주세요', '당선', '후보자',
      '선거운동', '공천', '출마'
    ],
    'ELECTION_DAY': [
      '투표', '선거', '지지', '후보', '당선', '정치', '정책', '공약'
    ]
  };

  const keywords = restrictedKeywords[phase] || [];
  const foundKeywords = keywords.filter(keyword => 
    topic && topic.toLowerCase().includes(keyword)
  );

  return {
    allowed: foundKeywords.length === 0,
    warning: foundKeywords.length > 0 && phase === 'PRE_CAMPAIGN_WARNING',
    restrictedKeywords: foundKeywords
  };
}

/**
 * 선거 단계별 추천 콘텐츠 유형
 * @param {string} phase 
 * @param {string} electionType 
 * @returns {Array}
 */
function getRecommendedContentTypes(phase, electionType) {
  const recommendations = {
    'NORMAL_PERIOD': [
      { type: 'policy', title: '정책 연구 발표', description: '지역 현안에 대한 정책 제안' },
      { type: 'achievement', title: '의정활동 보고', description: '지난 활동 성과 공유' },
      { type: 'introduction', title: '개인 소개', description: '정치 철학과 가치관 공유' }
    ],
    'PRE_CAMPAIGN_WARNING': [
      { type: 'policy', title: '정책 토론 참여', description: '정책 중심의 건전한 토론' },
      { type: 'local_issue', title: '지역 현안 의견', description: '지역 문제에 대한 의견 표명' },
      { type: 'achievement', title: '의정활동 설명', description: '객관적 활동 내용 설명' }
    ],
    'CAMPAIGN_PERIOD': [
      { type: 'campaign', title: '공식 선거운동', description: '모든 형태의 선거운동 가능' },
      { type: 'debate', title: '공개 토론 참여', description: '후보자 간 정책 토론' },
      { type: 'meet_voters', title: '유권자 만남', description: '지역 주민과의 소통' }
    ],
    'ELECTION_DAY': [
      { type: 'thanks', title: '감사 인사', description: '일반적인 감사 표현만 가능' }
    ]
  };

  return recommendations[phase] || [];
}

// ============================================================================
// 2차 방어: 생성된 콘텐츠 선거법 준수 검증
// ============================================================================

/**
 * 생성된 콘텐츠에서 선거법 위반 표현 검출
 * @param {string} content - 검사할 콘텐츠
 * @param {string} userStatus - 사용자 상태 (준비/현역/예비/후보)
 * @returns {Object} 검증 결과 { valid, violations, violationCount }
 */
function validateElectionCompliance(content, userStatus) {
  if (!content || !userStatus) {
    return { valid: true, violations: [], violationCount: 0 };
  }

  const stage = getElectionStage(userStatus);
  if (!stage || !stage.forbidden) {
    return { valid: true, violations: [], violationCount: 0 };
  }

  const violations = [];

  // 모든 금지 카테고리 검사
  for (const [category, patterns] of Object.entries(stage.forbidden)) {
    for (const pattern of patterns) {
      // 정규식 플래그 재설정 (lastIndex 초기화)
      const regex = new RegExp(pattern.source, pattern.flags);
      const matches = content.match(regex);
      if (matches) {
        violations.push({
          category,
          pattern: pattern.source,
          matches: [...new Set(matches)],  // 중복 제거
          count: matches.length
        });
      }
    }
  }

  return {
    valid: violations.length === 0,
    violations,
    violationCount: violations.reduce((sum, v) => sum + v.count, 0),
    stage: stage.name,
    userStatus
  };
}

// ============================================================================
// 3차 방어: 선거법 위반 표현 자동 치환
// ============================================================================

/**
 * 생성된 콘텐츠에서 선거법 위반 표현을 자동으로 안전한 표현으로 치환
 * @param {string} content - 원본 콘텐츠
 * @param {string} userStatus - 사용자 상태 (준비/현역/예비/후보)
 * @returns {Object} { sanitizedContent, replacementsMade, replacementLog }
 */
function sanitizeElectionContent(content, userStatus) {
  if (!content || !userStatus) {
    return {
      sanitizedContent: content,
      replacementsMade: 0,
      replacementLog: []
    };
  }

  const stage = getElectionStage(userStatus);
  if (!stage || !stage.replacements) {
    return {
      sanitizedContent: content,
      replacementsMade: 0,
      replacementLog: []
    };
  }

  let sanitizedContent = content;
  const replacementLog = [];
  let replacementsMade = 0;

  // 긴 표현부터 먼저 치환 (부분 일치 방지)
  const sortedReplacements = Object.entries(stage.replacements)
    .sort((a, b) => b[0].length - a[0].length);

  for (const [forbidden, replacement] of sortedReplacements) {
    // 정규식 특수문자 이스케이프
    const escapedForbidden = forbidden.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(escapedForbidden, 'g');

    const matches = sanitizedContent.match(regex);
    if (matches) {
      const count = matches.length;
      sanitizedContent = sanitizedContent.replace(regex, replacement);
      replacementsMade += count;
      replacementLog.push({
        original: forbidden,
        replacement: replacement || '(삭제됨)',
        count
      });
    }
  }

  // 추가 정리: 빈 문자열 치환으로 인한 이중 공백 제거
  sanitizedContent = sanitizedContent.replace(/\s{2,}/g, ' ');
  // 빈 괄호 제거
  sanitizedContent = sanitizedContent.replace(/\(\s*\)/g, '');
  // 문장 시작의 공백 제거
  sanitizedContent = sanitizedContent.replace(/<p>\s+/g, '<p>');

  console.log(`🛡️ 선거법 준수 치환 완료: ${replacementsMade}개 표현 수정 (상태: ${userStatus})`);

  if (replacementLog.length > 0) {
    console.log('📝 치환 내역:', JSON.stringify(replacementLog, null, 2));
  }

  return {
    sanitizedContent,
    replacementsMade,
    replacementLog,
    stage: stage.name,
    userStatus
  };
}

/**
 * 검증 + 치환을 한 번에 수행하는 통합 함수
 * @param {string} content - 원본 콘텐츠
 * @param {string} userStatus - 사용자 상태
 * @returns {Object} 통합 결과
 */
function enforceElectionCompliance(content, userStatus) {
  // 1. 먼저 검증
  const validationResult = validateElectionCompliance(content, userStatus);

  // 2. 위반이 있으면 치환
  if (!validationResult.valid) {
    const sanitizationResult = sanitizeElectionContent(content, userStatus);

    // 3. 치환 후 재검증
    const revalidationResult = validateElectionCompliance(
      sanitizationResult.sanitizedContent,
      userStatus
    );

    return {
      originalContent: content,
      sanitizedContent: sanitizationResult.sanitizedContent,
      wasModified: true,
      initialViolations: validationResult.violations,
      replacementsMade: sanitizationResult.replacementsMade,
      replacementLog: sanitizationResult.replacementLog,
      remainingViolations: revalidationResult.violations,
      fullyCompliant: revalidationResult.valid,
      stage: validationResult.stage,
      userStatus
    };
  }

  // 위반 없음
  return {
    originalContent: content,
    sanitizedContent: content,
    wasModified: false,
    initialViolations: [],
    replacementsMade: 0,
    replacementLog: [],
    remainingViolations: [],
    fullyCompliant: true,
    stage: validationResult.stage,
    userStatus
  };
}

module.exports = {
  checkElectionCompliance,
  getRecommendedContentTypes,
  getUserElectionInfo,
  // 2차 방어: 후검증
  validateElectionCompliance,
  // 3차 방어: 자동 치환
  sanitizeElectionContent,
  // 통합 함수
  enforceElectionCompliance
};