/**
 * functions/services/guidelines/chunks/naming.js
 * 인명 호칭 규칙 청크
 *
 * writingMethod (비판/협력)에 따라 다른 규칙 적용
 */

'use strict';

const NAMING_CHUNKS = [
  // ============================================================================
  // HIGH: 기본 호칭 규칙 (협력적 맥락)
  // ============================================================================
  {
    id: 'NM-001',
    type: 'naming',
    priority: 'HIGH',
    applies_to: {
      writingMethod: ['emotional_writing', 'direct_writing', 'logical_writing', 'analytical_writing', 'diagnostic_writing']
    },
    keywords: ['호칭', '의원', '구청장', '시장', '님'],
    instruction: '모든 공직자에 "님" 존칭 필수 (대통령/총리 제외)',
    forbidden: ['의원" (님 누락)', '구청장" (님 누락)'],
    examples: [
      { bad: '박성민 의원은', good: '박성민 의원님께서는' },
      { bad: '김철수 구청장이', good: '김철수 구청장님께서' },
      { bad: '국민의힘 이영희 의원', good: '국민의힘 이영희 의원님' }
    ],
    patterns: {
      nationalAssembly: '[선거구] [이름] 의원님 / [이름] 의원님([선거구])',
      localOfficials: '[이름] [지역명][직책]님 (예: 김철수 계양구청장님)',
      partyOfficials: '[당명] [직책] [이름] [직책]님',
      president: '[이름] 대통령 (님 생략 가능)',
      civilian: '[이름] 씨'
    },
    critical: '의원, 구청장, 시장급은 "님" 누락 시 정치적 결례로 항의 가능성 높음'
  },

  // ============================================================================
  // HIGH: 비판적 맥락 호칭 규칙 (critical_writing)
  // ============================================================================
  {
    id: 'NM-002',
    type: 'naming',
    priority: 'HIGH',
    applies_to: {
      writingMethod: ['critical_writing']
    },
    keywords: ['비판', '비평', '의혹', '문제', '실패'],
    instruction: '비판 대상은 "님" 생략 가능, 단 직함은 반드시 명시',
    forbidden: ['직함 생략', '비하 표현', '비속어'],
    examples: [
      { bad: '윤석열은', good: '윤석열 대통령은' },
      { bad: '이영희가', good: '국민의힘 이영희 의원은' },
      { bad: '박 시장 따위가', good: '박영수 시장은' }
    ],
    rules: {
      politicalOpponents: {
        rule: '정치적 반대편 인사는 "님" 생략 가능 (직함 필수)',
        examples: [
          '윤석열 대통령은 공약을 저버렸습니다',
          '국민의힘 이영희 의원은 이중잣대를 보였습니다'
        ]
      },
      controversy: {
        rule: '비리/의혹 제기 시 "님" 생략',
        examples: [
          '김철수 구청장은 비리 의혹에 휘말렸습니다',
          '박영수 의원은 허위 사실을 유포했습니다'
        ]
      },
      legalWarning: '명예훼손 리스크 주의 - 사실 기반 비판만 허용'
    },
    critical: '직함은 반드시 명시하여 최소한의 예의 유지, 법적 리스크 방지'
  },

  // ============================================================================
  // MEDIUM: 협력 맥락 강화 규칙
  // ============================================================================
  {
    id: 'NM-003',
    type: 'naming',
    priority: 'MEDIUM',
    applies_to: {
      writingMethod: ['emotional_writing', 'direct_writing']
    },
    keywords: ['협력', '행사', '참석', '감사', '함께'],
    instruction: '협력/행사 보고 시 정파 관계없이 모든 인사에 "님" 필수',
    forbidden: [],
    examples: [
      { bad: '국민의힘 이영희 의원도 참석', good: '국민의힘 이영희 의원님도 함께하셨습니다' },
      { bad: '부평구 박성민 의원과 협력', good: '부평구 갑 박성민 의원님과 협력했습니다' }
    ],
    context: '정치적 입장 차이와 무관하게, 협력/참석 사실 보고 시 존칭 필수'
  },

  // ============================================================================
  // MEDIUM: 선거구 표기 규칙
  // ============================================================================
  {
    id: 'NM-010',
    type: 'naming',
    priority: 'MEDIUM',
    applies_to: {
      category: ['all']
    },
    keywords: ['선거구', '갑', '을', '병', '지역구'],
    instruction: '선거구는 "갑/을/병/정" 표기, 법률 문서체 사용 금지',
    forbidden: ['제1선거구', '제2선거구'],
    examples: [
      { bad: '부평구 제1선거구', good: '부평구 갑' },
      { bad: '강남구 제3선거구', good: '강남구 병' }
    ]
  },

  // ============================================================================
  // MEDIUM: 인명 분절 금지
  // ============================================================================
  {
    id: 'NM-011',
    type: 'naming',
    priority: 'MEDIUM',
    applies_to: {
      category: ['all']
    },
    keywords: ['인명', '이름', '성명', '한자'],
    instruction: '한국어 인명(2-3글자)을 분절하거나 한자로 해석 금지',
    forbidden: ['인명 분절', '한자 해석'],
    examples: [
      { bad: '박성(朴姓)과 민(民)을 대표', good: '박성민 의원님' },
      { bad: '이영희로운 정책', good: '이영희 의원님의 정책' }
    ],
    rule: '인명은 항상 하나의 단위로 취급'
  }
];

/**
 * writingMethod에 따른 호칭 규칙 선택
 */
function getChunksForWritingMethod(writingMethod) {
  return NAMING_CHUNKS.filter(chunk => {
    if (!chunk.applies_to.writingMethod) return true;  // all에 적용
    return chunk.applies_to.writingMethod.includes(writingMethod);
  });
}

/**
 * 비판적 맥락인지 판단
 */
function isCriticalContext(writingMethod, topic = '') {
  if (writingMethod === 'critical_writing') return true;

  const criticalKeywords = ['비판', '비평', '문제', '의혹', '실패', '비리', '논란'];
  return criticalKeywords.some(k => topic.includes(k));
}

/**
 * 맥락에 맞는 호칭 규칙 반환
 */
function selectNamingRules(writingMethod, topic = '') {
  const isCritical = isCriticalContext(writingMethod, topic);

  if (isCritical) {
    // 비판적 맥락: NM-002 우선
    return NAMING_CHUNKS.filter(c => c.id === 'NM-002' || c.id === 'NM-010' || c.id === 'NM-011');
  } else {
    // 협력적 맥락: NM-001, NM-003 우선
    return NAMING_CHUNKS.filter(c => c.id !== 'NM-002');
  }
}

module.exports = {
  NAMING_CHUNKS,
  getChunksForWritingMethod,
  isCriticalContext,
  selectNamingRules
};
