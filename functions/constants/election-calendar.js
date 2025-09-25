/**
 * functions/constants/election-calendar.js
 * 선거법 준수를 위한 캘린더 시스템 상수 정의
 */

/**
 * 선거 유형별 정의
 */
const ELECTION_TYPES = {
  PRESIDENTIAL: {
    id: 'presidential',
    name: '대통령선거',
    campaignPeriod: 23, // 선거기간 (일)
    businessCardAllowed: 240, // 명함 배포 허용 기간 (일)
    colorCode: '#FF6B6B'
  },
  NATIONAL_ASSEMBLY: {
    id: 'national_assembly',
    name: '국회의원선거',
    campaignPeriod: 14,
    businessCardAllowed: 180,
    colorCode: '#4ECDC4'
  },
  LOCAL_GOVERNMENT: {
    id: 'local_government',
    name: '지방자치단체선거',
    campaignPeriod: 14,
    businessCardAllowed: 180,
    colorCode: '#45B7D1'
  },
  BY_ELECTION: {
    id: 'by_election',
    name: '보궐선거',
    campaignPeriod: 14,
    businessCardAllowed: 180,
    colorCode: '#96CEB4'
  }
};

/**
 * 선거법상 중요한 마일스톤 정의
 */
const ELECTION_MILESTONES = {
  BUSINESS_CARD_START: {
    id: 'business_card_start',
    name: '명함 배포 시작 가능',
    description: '개인 명함에 한하여 배포 가능 (정치적 내용 포함 불가)',
    daysBeforeElection: (electionType) => ELECTION_TYPES[electionType].businessCardAllowed,
    restrictions: [
      '정치적 목적이 명시되지 않은 개인 명함만 가능',
      '선거운동 성격의 내용 포함 불가',
      '일반적인 인사말 수준만 허용'
    ],
    allowedActivities: ['개인 명함 배포', '일반적 인사 활동'],
    restrictedActivities: ['정치적 메시지', '정책 홍보', '투표 요청']
  },
  
  OFFICIAL_RESIGNATION_DEADLINE: {
    id: 'official_resignation',
    name: '특정 공직자 사임 의무',
    description: '선거사무장 등이 되려는 공직자의 사임 마감일',
    daysBeforeElection: 90,
    restrictions: [
      '각급선거관리위원회위원 사임',
      '예비군 중대장급 이상 간부 사임',
      '주민자치위원회위원 사임',
      '통·리·반의 장 사임'
    ],
    note: '선거일 후 6개월 이내 복직 불가'
  },

  PRE_CAMPAIGN_WARNING: {
    id: 'pre_campaign_warning',
    name: '사전 선거운동 주의 기간',
    description: '사전 선거운동 금지 조항 특별 주의 기간',
    daysBeforeElection: 30,
    restrictions: [
      '후보자 홍보성 내용 금지',
      '정책 공약 적극적 홍보 제한',
      '투표 요청 행위 금지'
    ],
    allowedActivities: [
      '일반적인 정치 활동',
      '정책 연구 발표',
      '지역 현안 의견 표명'
    ]
  },

  CAMPAIGN_PERIOD_START: {
    id: 'campaign_start',
    name: '선거운동 기간 시작',
    description: '공식적인 선거운동 가능 기간 시작',
    daysBeforeElection: (electionType) => ELECTION_TYPES[electionType].campaignPeriod,
    allowedActivities: [
      '모든 형태의 선거운동',
      '공개 연설 및 토론',
      '선거 벽보 부착',
      '확성기 사용',
      '문자메시지 발송 (8회 제한)'
    ]
  },

  ELECTION_DAY: {
    id: 'election_day',
    name: '선거일',
    description: '투표일 - 모든 선거운동 금지',
    daysBeforeElection: 0,
    restrictions: [
      '모든 형태의 선거운동 금지',
      '투표 독려 행위 금지',
      '정치적 메시지 전파 금지'
    ]
  }
};

/**
 * 콘텐츠 유형별 제한 규칙
 */
const CONTENT_RESTRICTIONS = {
  POLICY_STATEMENT: {
    name: '정책 발표',
    phases: {
      NORMAL_PERIOD: { allowed: true, warning: false },
      PRE_CAMPAIGN_WARNING: { allowed: true, warning: true },
      CAMPAIGN_PERIOD: { allowed: true, warning: false },
      ELECTION_DAY: { allowed: false, warning: false }
    }
  },
  
  ACHIEVEMENT_PROMOTION: {
    name: '성과 홍보',
    phases: {
      NORMAL_PERIOD: { allowed: true, warning: false },
      PRE_CAMPAIGN_WARNING: { allowed: true, warning: true },
      CAMPAIGN_PERIOD: { allowed: true, warning: false },
      ELECTION_DAY: { allowed: false, warning: false }
    }
  },

  VOTE_REQUEST: {
    name: '투표 요청',
    phases: {
      NORMAL_PERIOD: { allowed: false, warning: false },
      PRE_CAMPAIGN_WARNING: { allowed: false, warning: false },
      CAMPAIGN_PERIOD: { allowed: true, warning: false },
      ELECTION_DAY: { allowed: false, warning: false }
    }
  },

  PERSONAL_INTRODUCTION: {
    name: '개인 소개',
    phases: {
      NORMAL_PERIOD: { allowed: true, warning: false },
      PRE_CAMPAIGN_WARNING: { allowed: true, warning: false },
      CAMPAIGN_PERIOD: { allowed: true, warning: false },
      ELECTION_DAY: { allowed: true, warning: false }
    }
  }
};

/**
 * 경고 메시지 템플릿
 */
const WARNING_MESSAGES = {
  PRE_CAMPAIGN: {
    title: '사전 선거운동 주의',
    message: '현재 사전 선거운동 금지 기간입니다. 생성되는 내용이 선거법에 위반되지 않도록 주의해주세요.',
    suggestions: [
      '투표 요청 문구 제외',
      '과도한 자기 홍보 지양',
      '정책 설명 위주로 작성'
    ]
  },
  CAMPAIGN_PERIOD: {
    title: '선거운동 기간',
    message: '공식 선거운동 기간입니다. 선거법에 따른 제한 사항을 준수해주세요.',
    suggestions: [
      '문자 발송 횟수 제한 (8회)',
      '허위사실 유포 금지',
      '타 후보자 비방 금지'
    ]
  },
  ELECTION_DAY: {
    title: '선거일 - 선거운동 금지',
    message: '투표일에는 모든 형태의 선거운동이 금지됩니다.',
    suggestions: [
      '정치적 메시지 게시 금지',
      '투표 독려 행위 금지',
      '일반적인 감사 인사만 가능'
    ]
  }
};

/**
 * 유틸리티 함수들
 */
const ElectionCalendarUtils = {
  /**
   * 현재 선거 단계 판단
   * @param {Date} electionDate - 선거일
   * @param {string} electionType - 선거 유형
   * @returns {string} 현재 단계
   */
  getCurrentPhase(electionDate, electionType) {
    const now = new Date();
    const daysUntilElection = Math.ceil((electionDate - now) / (1000 * 60 * 60 * 24));
    
    if (daysUntilElection === 0) return 'ELECTION_DAY';
    if (daysUntilElection < 0) return 'POST_ELECTION';
    if (daysUntilElection <= ELECTION_TYPES[electionType].campaignPeriod) return 'CAMPAIGN_PERIOD';
    if (daysUntilElection <= 30) return 'PRE_CAMPAIGN_WARNING';
    
    return 'NORMAL_PERIOD';
  },

  /**
   * 콘텐츠 생성 가능 여부 확인
   * @param {string} contentType - 콘텐츠 유형
   * @param {string} phase - 현재 선거 단계
   * @returns {Object} 허용 여부와 경고 정보
   */
  checkContentRestriction(contentType, phase) {
    const restriction = CONTENT_RESTRICTIONS[contentType];
    if (!restriction) return { allowed: true, warning: false };
    
    return restriction.phases[phase] || { allowed: false, warning: false };
  },

  /**
   * 다음 마일스톤까지 남은 일수
   * @param {Date} electionDate - 선거일
   * @param {string} electionType - 선거 유형
   * @returns {Object} 다음 마일스톤 정보
   */
  getNextMilestone(electionDate, electionType) {
    const now = new Date();
    const daysUntilElection = Math.ceil((electionDate - now) / (1000 * 60 * 60 * 24));
    
    for (const milestone of Object.values(ELECTION_MILESTONES)) {
      const milestoneDays = typeof milestone.daysBeforeElection === 'function' 
        ? milestone.daysBeforeElection(electionType)
        : milestone.daysBeforeElection;
        
      if (daysUntilElection >= milestoneDays) {
        return {
          milestone,
          daysUntil: daysUntilElection - milestoneDays
        };
      }
    }
    
    return null;
  }
};

module.exports = {
  ELECTION_TYPES,
  ELECTION_MILESTONES,
  CONTENT_RESTRICTIONS,
  WARNING_MESSAGES,
  ElectionCalendarUtils
};