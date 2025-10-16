'use strict';

/**
 * 사용자 상태별 설정
 */
const STATUS_CONFIG = {
  '현역': {
    guideline: '현역 의원으로서 경험과 성과를 바탕으로 신뢰있는 내용을 포함하세요. 실제 의정활동 경험을 언급하는게 좋습니다.',
    title: '의원'
  },
  '예비': {
    guideline: '예비후보로서 정책과 공약을 중심으로 신뢰있는 내용을 작성하세요. 미래 비전과 구체적 계획을 제시하세요',
    title: '예비후보'
  },
  '은퇴': {
    guideline: '은퇴 상태에서는 어떤 호칭도 사용하지 않고 개인 이름으로만 지칭하세요. 현상 진단과 개인적 견해만 표현하세요. 절대 "은퇴예비후보", "예비후보", "의원", "현역 의원으로서", "의정활동", "성과", "실적", "추진함", "기여함" 같은 표현을 사용하지 마세요. 구체적인 비전이나 계획을 언급하지 마세요. 오직 현 상황에 대한 개인적 경험과 진단만 표현하세요',
    title: ''
  }
};

/**
 * 카테고리 → 작법(writingMethod) 매핑
 */
const CATEGORY_TO_WRITING_METHOD = {
  'daily-communication': 'emotional_writing',
  'activity-report': 'direct_writing',
  'policy-proposal': 'logical_writing',
  'current-affairs': 'critical_writing',
  'local-issues': 'analytical_writing'
};

/**
 * 정책 이름 매핑
 */
const POLICY_NAMES = {
  economy: '경제정책',
  education: '교육정책',
  welfare: '복지정책',
  environment: '환경정책',
  security: '안보정책',
  culture: '문화정책'
};

/**
 * 가족 상태 매핑
 */
const FAMILY_STATUS_MAP = {
  '미혼': '싱글 생활의 경험을 가진',
  '기혼(자녀 있음)': '자녀 양육 가정의 경험을 가진',
  '기혼(자녀 없음)': '가정을 꾸리며',
  '한부모': '한부모 가정의 경험을 가진'
};

/**
 * 배경 경력 관련성 키워드
 */
const CAREER_RELEVANCE = {
  '교육자': ['교육', '학생', '학교', '교사'],
  '사업가': ['경제', '중소상공인', '영업', '창업'],
  '공무원': ['행정', '정책', '공공서비스'],
  '의료인': ['의료', '건강', '코로나', '보건'],
  '법조인': ['법', '제도', '정의', '권리']
};

/**
 * 정치 경험 매핑
 */
const POLITICAL_EXPERIENCE_MAP = {
  '초선': '초선 의원으로서 신선한 관점에서',
  '재선': '의정 경험을 바탕으로',
  '3선이상': '다선 의정 경험으로',
  '정치 신인': '새로운 시각에서'
};

/**
 * 위원회 키워드 매핑
 */
const COMMITTEE_KEYWORDS = {
  '교육위원회': ['교육', '학생', '학교', '대학'],
  '보건복지위원회': ['복지', '의료', '건강', '연금'],
  '국토교통위원회': ['교통', '주거', '도로', '건설'],
  '환경노동위원회': ['환경', '노동', '일자리'],
  '여성가족위원회': ['여성', '가족', '육아', '출산']
};

/**
 * 지역 연고 매핑
 */
const LOCAL_CONNECTION_MAP = {
  '토박이': '지역 토박이로서',
  '오래 거주': '오랫동안 이 지역에 거주해',
  '이주민': '이 지역에서 새로운 삶을 시작한 고향으로 일구',
  '귀농': '고향으로 돌아온'
};

module.exports = {
  STATUS_CONFIG,
  CATEGORY_TO_WRITING_METHOD,
  POLICY_NAMES,
  FAMILY_STATUS_MAP,
  CAREER_RELEVANCE,
  POLITICAL_EXPERIENCE_MAP,
  COMMITTEE_KEYWORDS,
  LOCAL_CONNECTION_MAP
};
