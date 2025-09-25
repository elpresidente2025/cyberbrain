/**
 * frontend/src/constants/bio-types.js
 * Bio 엔트리 타입 정의 (프론트엔드용)
 */

/**
 * Bio 엔트리 타입 정의
 */
export const BIO_ENTRY_TYPES = {
  SELF_INTRODUCTION: {
    id: 'self_introduction',
    name: '자기소개',
    description: '개인 철학, 가치관, 정치적 신념 등',
    icon: 'person',
    color: '#152484',
    maxLength: 2000,
    placeholder: '본인의 정치 철학, 가치관, 지역에 대한 애정 등을 자유롭게 작성해주세요.',
    rows: 4
  },

  POLICY: {
    id: 'policy',
    name: '정책/공약',
    description: '추진하고자 하는 정책이나 공약 내용',
    icon: 'assignment',
    color: '#003A87',
    maxLength: 2500,
    placeholder: '중점적으로 추진하고자 하는 정책이나 공약을 구체적으로 작성해주세요.',
    rows: 5
  },

  LEGISLATION: {
    id: 'legislation',
    name: '법안/조례',
    description: '발의하거나 지지하는 법안, 조례안',
    icon: 'gavel',
    color: '#006261',
    maxLength: 2000,
    placeholder: '발의했거나 발의하고자 하는 법안, 조례안의 내용과 취지를 설명해주세요.',
    rows: 4
  },

  EXPERIENCE: {
    id: 'experience',
    name: '경험/활동',
    description: '정치 활동, 지역 활동, 사회 경험 등',
    icon: 'timeline',
    color: '#006261',
    maxLength: 1800,
    placeholder: '정치 활동, 지역 사회 활동, 직업 경험 등을 통해 쌓은 경험과 노하우를 작성해주세요.',
    rows: 4
  },

  ACHIEVEMENT: {
    id: 'achievement',
    name: '성과/실적',
    description: '이룬 성과, 해결한 문제, 추진한 사업 등',
    icon: 'emoji_events',
    color: '#55207D',
    maxLength: 1500,
    placeholder: '그동안 이룬 구체적인 성과나 해결한 지역 현안 등을 사례 중심으로 작성해주세요.',
    rows: 3
  },

  VISION: {
    id: 'vision',
    name: '비전/목표',
    description: '미래 비전, 장기적 목표, 지역 발전 계획',
    icon: 'visibility',
    color: '#55207D',
    maxLength: 1800,
    placeholder: '지역과 국가의 미래에 대한 비전과 장기적인 목표를 제시해주세요.',
    rows: 4
  },

  REFERENCE: {
    id: 'reference',
    name: '기타 참고자료',
    description: '언론 인터뷰, 칼럼, 연설문 등',
    icon: 'library_books',
    color: '#006261',
    maxLength: 2500,
    placeholder: '언론 인터뷰, 기고문, 연설문 등 본인을 더 잘 알 수 있는 자료를 추가해주세요.',
    rows: 5
  }
};

/**
 * Bio 엔트리 타입 순서 (UI 표시용)
 */
export const BIO_TYPE_ORDER = [
  BIO_ENTRY_TYPES.SELF_INTRODUCTION,
  BIO_ENTRY_TYPES.VISION,
  BIO_ENTRY_TYPES.POLICY,
  BIO_ENTRY_TYPES.ACHIEVEMENT,
  BIO_ENTRY_TYPES.LEGISLATION,
  BIO_ENTRY_TYPES.EXPERIENCE,
  BIO_ENTRY_TYPES.REFERENCE
];

/**
 * Bio 엔트리 카테고리 분류
 */
export const BIO_CATEGORIES = {
  PERSONAL: {
    name: '자기소개',
    description: '자기소개, 비전, 경험, 참고자료',
    types: [
      BIO_ENTRY_TYPES.SELF_INTRODUCTION,
      BIO_ENTRY_TYPES.VISION,
      BIO_ENTRY_TYPES.EXPERIENCE,
      BIO_ENTRY_TYPES.REFERENCE
    ]
  },
  PERFORMANCE: {
    name: '추가 정보',
    description: '구체적인 정책, 성과, 법안 등',
    types: [
      BIO_ENTRY_TYPES.POLICY,
      BIO_ENTRY_TYPES.ACHIEVEMENT,
      BIO_ENTRY_TYPES.LEGISLATION
    ]
  }
};

/**
 * 유효성 검사 규칙
 */
export const VALIDATION_RULES = {
  minEntries: 1,
  maxEntries: 15,
  maxEntriesPerType: 5,
  minContentLength: 50,
  maxTotalLength: 20000
};