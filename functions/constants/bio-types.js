/**
 * functions/constants/bio-types.js
 * Bio 엔트리 타입 정의 및 설정
 */

'use strict';

/**
 * Bio 엔트리 타입 정의
 */
const BIO_ENTRY_TYPES = {
  SELF_INTRODUCTION: {
    id: 'self_introduction',
    name: '자기소개',
    description: '개인 철학, 가치관, 정치적 신념 등',
    icon: 'person',
    color: '#2196F3',
    maxLength: 2000,
    placeholder: '본인의 정치 철학, 가치관, 지역에 대한 애정 등을 자유롭게 작성해주세요.',
    analysisWeight: 1.0,
    analysisAreas: ['politicalStance', 'communicationStyle', 'personalValues']
  },

  POLICY: {
    id: 'policy',
    name: '정책/공약',
    description: '추진하고자 하는 정책이나 공약 내용',
    icon: 'assignment',
    color: '#4CAF50',
    maxLength: 2500,
    placeholder: '중점적으로 추진하고자 하는 정책이나 공약을 구체적으로 작성해주세요.',
    analysisWeight: 0.9,
    analysisAreas: ['policyFocus', 'expertise', 'implementationStyle']
  },

  LEGISLATION: {
    id: 'legislation',
    name: '법안/조례',
    description: '발의하거나 지지하는 법안, 조례안',
    icon: 'gavel',
    color: '#FF9800',
    maxLength: 2000,
    placeholder: '발의했거나 발의하고자 하는 법안, 조례안의 내용과 취지를 설명해주세요.',
    analysisWeight: 0.8,
    analysisAreas: ['legislativeStance', 'legalExpertise', 'reformDirection']
  },

  EXPERIENCE: {
    id: 'experience',
    name: '경험/활동',
    description: '정치 활동, 지역 활동, 사회 경험 등',
    icon: 'timeline',
    color: '#9C27B0',
    maxLength: 1800,
    placeholder: '정치 활동, 지역 사회 활동, 직업 경험 등을 통해 쌓은 경험과 노하우를 작성해주세요.',
    analysisWeight: 0.7,
    analysisAreas: ['localConnection', 'practicalExpertise', 'networkStrength']
  },

  ACHIEVEMENT: {
    id: 'achievement',
    name: '성과/실적',
    description: '이룬 성과, 해결한 문제, 추진한 사업 등',
    icon: 'emoji_events',
    color: '#FF5722',
    maxLength: 1500,
    placeholder: '그동안 이룬 구체적인 성과나 해결한 지역 현안 등을 사례 중심으로 작성해주세요.',
    analysisWeight: 0.8,
    analysisAreas: ['trackRecord', 'problemSolving', 'leadershipStyle']
  },

  VISION: {
    id: 'vision',
    name: '비전/목표',
    description: '미래 비전, 장기적 목표, 지역 발전 계획',
    icon: 'visibility',
    color: '#3F51B5',
    maxLength: 1800,
    placeholder: '지역과 국가의 미래에 대한 비전과 장기적인 목표를 제시해주세요.',
    analysisWeight: 0.9,
    analysisAreas: ['futureOrientation', 'strategicThinking', 'inspirationalCapacity']
  },

  REFERENCE: {
    id: 'reference',
    name: '기타 참고자료',
    description: '언론 인터뷰, 칼럼, 연설문 등',
    icon: 'library_books',
    color: '#607D8B',
    maxLength: 2500,
    placeholder: '언론 인터뷰, 기고문, 연설문 등 본인을 더 잘 알 수 있는 자료를 추가해주세요.',
    analysisWeight: 0.6,
    analysisAreas: ['publicImage', 'mediaStrategy', 'messageConsistency']
  }
};

/**
 * 타입별 분석 가중치
 */
const TYPE_ANALYSIS_WEIGHTS = {
  [BIO_ENTRY_TYPES.SELF_INTRODUCTION.id]: 1.0,
  [BIO_ENTRY_TYPES.VISION.id]: 0.9,
  [BIO_ENTRY_TYPES.POLICY.id]: 0.9,
  [BIO_ENTRY_TYPES.ACHIEVEMENT.id]: 0.8,
  [BIO_ENTRY_TYPES.LEGISLATION.id]: 0.8,
  [BIO_ENTRY_TYPES.EXPERIENCE.id]: 0.7,
  [BIO_ENTRY_TYPES.REFERENCE.id]: 0.6
};

/**
 * 원고 생성 시 타입별 활용도
 */
const GENERATION_UTILIZATION = {
  [BIO_ENTRY_TYPES.SELF_INTRODUCTION.id]: {
    usage: 'always',
    purpose: '전체적인 톤앤매너 결정',
    weight: 1.0
  },
  [BIO_ENTRY_TYPES.POLICY.id]: {
    usage: 'policy_related',
    purpose: '정책 관련 원고에서 전문성 강조',
    weight: 0.9
  },
  [BIO_ENTRY_TYPES.LEGISLATION.id]: {
    usage: 'legal_topics',
    purpose: '법안, 제도 관련 내용에서 활용',
    weight: 0.8
  },
  [BIO_ENTRY_TYPES.EXPERIENCE.id]: {
    usage: 'credibility_needed',
    purpose: '신뢰성과 경험 강조가 필요한 경우',
    weight: 0.8
  },
  [BIO_ENTRY_TYPES.ACHIEVEMENT.id]: {
    usage: 'performance_focus',
    purpose: '성과와 실적 강조가 필요한 경우',
    weight: 0.9
  },
  [BIO_ENTRY_TYPES.VISION.id]: {
    usage: 'future_topics',
    purpose: '미래 계획, 비전 제시 관련 원고',
    weight: 0.9
  },
  [BIO_ENTRY_TYPES.REFERENCE.id]: {
    usage: 'context_support',
    purpose: '배경 맥락 제공 및 일관성 확인',
    weight: 0.6
  }
};

/**
 * 유효한 Bio 엔트리 타입 목록 (순서대로 UI에 표시)
 */
const BIO_TYPE_ORDER = [
  BIO_ENTRY_TYPES.SELF_INTRODUCTION,
  BIO_ENTRY_TYPES.VISION,
  BIO_ENTRY_TYPES.POLICY,
  BIO_ENTRY_TYPES.ACHIEVEMENT,
  BIO_ENTRY_TYPES.LEGISLATION,
  BIO_ENTRY_TYPES.EXPERIENCE,
  BIO_ENTRY_TYPES.REFERENCE
];

/**
 * Bio 엔트리 유효성 검사 규칙
 */
const VALIDATION_RULES = {
  minEntries: 1,
  maxEntries: 15,
  maxEntriesPerType: 5,
  requiredTypes: [BIO_ENTRY_TYPES.SELF_INTRODUCTION.id], // 자기소개는 필수
  minContentLength: 50,
  maxTotalLength: 20000
};

module.exports = {
  BIO_ENTRY_TYPES,
  TYPE_ANALYSIS_WEIGHTS,
  GENERATION_UTILIZATION,
  BIO_TYPE_ORDER,
  VALIDATION_RULES
};