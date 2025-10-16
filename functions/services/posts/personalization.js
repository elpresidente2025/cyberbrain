'use strict';

const {
  POLICY_NAMES,
  FAMILY_STATUS_MAP,
  CAREER_RELEVANCE,
  POLITICAL_EXPERIENCE_MAP,
  COMMITTEE_KEYWORDS,
  LOCAL_CONNECTION_MAP
} = require('../../utils/posts/constants');

/**
 * Bio 메타데이터를 기반으로 개인화된 원고 작성 힌트를 생성합니다
 * @param {Object} bioMetadata - 추출된 바이오그래피 메타데이터
 * @returns {string} 개인화 힌트 문자열
 */
function generatePersonalizedHints(bioMetadata) {
  if (!bioMetadata) return '';

  const hints = [];

  // 정치적 성향 기반 힌트
  if (bioMetadata.politicalStance?.progressive > 0.7) {
    hints.push('보수보다 혁신을 강조하는 진보적 관점으로 작성');
  } else if (bioMetadata.politicalStance?.conservative > 0.7) {
    hints.push('안정성과 전통 가치를 중시하는 보수적 관점으로 작성');
  } else if (bioMetadata.politicalStance?.moderate > 0.8) {
    hints.push('균형잡힌 중도적 관점에서 다양한 의견을 수용하여 작성');
  }

  // 소통 스타일 기반 힌트
  const commStyle = bioMetadata.communicationStyle;
  if (commStyle?.tone === 'warm') {
    hints.push('따뜻하고 친근한 어조 사용');
  } else if (commStyle?.tone === 'formal') {
    hints.push('격식있고 전문적인 어조 사용');
  }

  if (commStyle?.approach === 'inclusive') {
    hints.push('모든 계층을 포용하는 수용적 표현');
  } else if (commStyle?.approach === 'collaborative') {
    hints.push('협력과 소통을 강조하는 협업적 표현');
  }

  // 정책 관심도 기반 힌트
  const topPolicy = Object.entries(bioMetadata.policyFocus || {})
    .sort(([,a], [,b]) => b.weight - a.weight)[0];

  if (topPolicy && topPolicy[1].weight > 0.6) {
    hints.push(`${POLICY_NAMES[topPolicy[0]] || topPolicy[0]} 관점에서 표현`);
  }

  // 지역 연결성 기반 힌트
  if (bioMetadata.localConnection?.strength > 0.8) {
    hints.push('지역현안과 주민들의 실제 경험을 구체적으로 반영');
    if (bioMetadata.localConnection.keywords?.length > 0) {
      hints.push(`지역 용어 사용: ${bioMetadata.localConnection.keywords.slice(0, 3).join(', ')}`);
    }
  }

  // 생성 선호도 기반 힌트
  const prefs = bioMetadata.generationProfile?.likelyPreferences;
  if (prefs?.includePersonalExperience > 0.8) {
    hints.push('개인적 경험과 사례를 풍부하게 포함');
  }
  if (prefs?.useStatistics > 0.7) {
    hints.push('구체적인 숫자와 데이터를 적극적으로 사용');
  }
  if (prefs?.focusOnFuture > 0.7) {
    hints.push('미래 비전과 발전 방향을 제시');
  }

  return hints.join(' | ');
}

/**
 * 사용자 개인정보를 기반으로 페르소나 힌트를 생성합니다
 * @param {Object} userProfile - 사용자 프로필 정보
 * @param {string} category - 글 카테고리
 * @param {string} topic - 글 주제
 * @returns {string} 페르소나 힌트 문자열
 */
function generatePersonaHints(userProfile, category, topic) {
  if (!userProfile) return '';

  const hints = [];
  const topicLower = topic ? topic.toLowerCase() : '';

  // 카테고리별 관련도 높은 정보 우선 선택
  const relevantInfo = getRelevantPersonalInfo(userProfile, category, topicLower);

  // 선택된 정보만 자연스럽게 구성
  if (relevantInfo.age) {
    hints.push(relevantInfo.age);
  }

  if (relevantInfo.family) {
    hints.push(relevantInfo.family);
  }

  if (relevantInfo.background) {
    hints.push(relevantInfo.background);
  }

  if (relevantInfo.experience) {
    hints.push(relevantInfo.experience);
  }

  if (relevantInfo.committees && relevantInfo.committees.length > 0) {
    hints.push(`${relevantInfo.committees.join(', ')} 활동 경험을 바탕으로`);
  }

  if (relevantInfo.connection) {
    hints.push(relevantInfo.connection);
  }

  const persona = hints.filter(h => h).join(' ');
  return persona ? `[작성 관점: ${persona}]` : '';
}

/**
 * 글 카테고리와 주제에 따라 관련성 높은 개인정보만 선별합니다
 */
function getRelevantPersonalInfo(userProfile, category, topicLower) {
  const result = {};

  // 나이대 (일상 소통, 가정/육아 관련 주제에서 관련성 높음)
  if (category === 'daily-communication' ||
      topicLower.includes('family') || topicLower.includes('youth') || topicLower.includes('romance')) {
    if (userProfile.ageDecade) {
      result.age = userProfile.ageDetail ?
        `${userProfile.ageDecade} ${userProfile.ageDetail}` : userProfile.ageDecade;
    }
  }

  // 가정 상황 (교육, 복지, 일상 소통에서 관련성 높음)
  if (category === 'daily-communication' ||
      topicLower.includes('교육') || topicLower.includes('육아') || topicLower.includes('복지')) {
    if (userProfile.familyStatus) {
      result.family = FAMILY_STATUS_MAP[userProfile.familyStatus];
    }
  }

  // 배경 경력 (관련 정책 분야에서 관련성 높음)
  if (userProfile.backgroundCareer) {
    const relevantKeywords = CAREER_RELEVANCE[userProfile.backgroundCareer] || [];
    const isRelevant = relevantKeywords.some(keyword => topicLower.includes(keyword));

    if (isRelevant) {
      result.background = `${userProfile.backgroundCareer} 출신으로`;
    }
  }

  // 정치 경험 (의정활동 보고, 정책 제안에서 관련성 높음)
  if (category === 'activity-report' || category === 'policy-proposal') {
    if (userProfile.politicalExperience) {
      result.experience = POLITICAL_EXPERIENCE_MAP[userProfile.politicalExperience];
    }
  }

  // 소속 위원회 (관련 분야에서만 언급)
  if (userProfile.committees && userProfile.committees.length > 0) {
    const validCommittees = userProfile.committees.filter(c => c && c !== '');
    const relevantCommittees = validCommittees.filter(committee => {
      const keywords = COMMITTEE_KEYWORDS[committee] || [];
      return keywords.some(keyword => topicLower.includes(keyword));
    });

    if (relevantCommittees.length > 0) {
      result.committees = relevantCommittees;
    }
  }

  // 지역 연고 (지역현안에서 관련성 높음)
  if (category === 'local-issues' || topicLower.includes('지역') || topicLower.includes('우리 동네')) {
    if (userProfile.localConnection) {
      result.connection = LOCAL_CONNECTION_MAP[userProfile.localConnection];
    }
  }

  return result;
}

module.exports = {
  generatePersonalizedHints,
  generatePersonaHints,
  getRelevantPersonalInfo
};
