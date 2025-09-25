// functions/templates/guidelines/editorial.js - 편집 기준 및 작성 규칙

'use strict';

// ============================================================================
// SEO 최적화 규칙 (네이버 기준)
// ============================================================================

const SEO_RULES = {
  // 분량 규칙
  wordCount: {
    min: 1800,
    max: 2300,
    target: 1750,
    description: '네이버 SEO 최적화를 위한 권장 분량',
    rationale: '1800자 미만은 콘텐츠 부족, 2300자 초과는 가독성 저하'
  },
  
  // 키워드 배치 전략
  keywordPlacement: {
    title: {
      count: 1,
      position: 'natural',
      description: '제목에 핵심 키워드 1회, 자연스럽게 배치'
    },
    body: {
      interval: 400,
      method: 'contextual',
      description: '본문 400자당 1회, 맥락에 맞게 자연스럽게 포함',
      avoidance: '키워드 스터핑 금지, 강제 삽입 금지'
    },
    density: {
      optimal: '1.5-2.5%',
      maximum: '3%',
      warning: '3% 초과 시 스팸으로 분류 위험'
    }
  },
  
  // 구조 최적화
  structure: {
    headings: {
      h1: { count: 1, rule: '제목으로만 사용' },
      h2: { count: '2-3개', rule: '주요 섹션 구분' },
      h3: { count: '3-5개', rule: '세부 내용 구조화' },
      h4: { count: '필요시', rule: '상세 분류용' }
    },
    paragraphs: {
      count: '6-8개',
      length: '150-250자',
      rule: '한 문단 하나의 주제'
    },
    lists: {
      usage: '정보 나열 시 적극 활용',
      format: 'HTML ul/ol 태그 사용'
    }
  },
  
  // 검색 최적화 전략
  searchOptimization: {
    titleStrategy: [
      '핵심 키워드 앞쪽 배치',
      '구체적이고 명확한 표현',
      '감정적 어필 요소 포함',
      '지역명/날짜 등 구체 정보 활용'
    ],
    contentStrategy: [
      '첫 문단에 주제 명확히 제시',
      '중요 정보는 앞쪽에 배치',
      '관련 키워드 자연스럽게 포함',
      '구체적 수치와 사실 제시'
    ],
    metaStrategy: [
      '읽기 쉬운 문장 구조',
      '전문 용어 최소화',
      '지역 특화 정보 강조'
    ]
  }
};

// ============================================================================
// 콘텐츠 작성 규칙
// ============================================================================

const CONTENT_RULES = {
  // 기본 톤앤매너
  tone: {
    style: {
      formality: '존댓말 사용',
      warmth: '서민적이고 친근한 어조',
      authority: '전문성 있되 권위적이지 않게',
      empathy: '공감대 형성과 포용적 자세'
    },
    voice: {
      firstPerson: '"저는", "제가"',
      secondPerson: '"여러분", "주민 여러분"',
      avoid: ['나는', '당신', '너희']
    },
    prohibitions: [
      '직접 지시/명령 톤 금지',
      '상하관계 암시 표현 금지',
      '일방적 주장 톤 금지'
    ]
  },

  // 문서 구조 가이드
  structure: {
    opening: {
      greeting: '인사말로 시작',
      introduction: '주제 간략 소개',
      connection: '독자와의 접점 마련'
    },
    body: {
      logical: '논리적 순서로 전개',
      evidence: '근거와 사례 제시',
      balance: '다양한 관점 고려'
    },
    closing: {
      summary: '핵심 내용 요약',
      commitment: '향후 계획이나 다짐',
      invitation: '소통 지속 의지 표현'
    }
  },

  // 표현 스타일 가이드
  expression: {
    positive: {
      preferred: [
        '"함께 만들어가겠습니다"',
        '"더 나은 방향으로 발전시키겠습니다"',
        '"주민 여러분과 소통하겠습니다"'
      ],
      tone: '희망적이고 건설적인 메시지'
    },
    inclusive: {
      preferred: [
        '"모든 주민이 함께"',
        '"다양한 의견을 수렴하여"',
        '"포용적 관점에서"'
      ],
      avoid: ['특정 계층만', '일부만', '선별적으로']
    },
    humble: {
      preferred: [
        '"부족하지만 최선을 다해"',
        '"더 많이 배우고 노력하겠습니다"',
        '"여러분의 지혜를 모아"'
      ],
      avoid: ['확신합니다', '자신있게', '완벽하게']
    }
  },

  // 경험 활용 가이드
  experienceIntegration: {
    required: '작성자 자기소개 내용 필수 반영',
    format: [
      '"제가 [구체적 활동/경험]을 통해 느낀 점은..."',
      '"[경험] 과정에서 확인한 바로는..."',
      '"직접 경험해보니..."'
    ],
    purpose: '개인 경험으로 설득력과 진정성 확보',
    balance: '과도한 자기PR 지양, 교훈과 통찰 중심'
  },

  // 호칭 및 정체성 규칙
  identity: {
    audienceAddress: {
      withRegion: '"○○ 주민 여러분"',
      withoutRegion: '"여러분"',
      formal: '"시민 여러분"',
      intimate: '"이웃 여러분"'
    },
    selfReference: {
      incumbent: '"의원으로서"',
      candidate: '"예비후보로서"',
      public: '"한 사람의 시민으로서"'
    },
    statusConsistency: {
      incumbent: '현역 의원은 경험과 성과 기반 발언',
      candidate: '예비후보는 비전과 계획 중심 발언',
      prohibition: '예비후보가 현역 의원처럼 발언 금지'
    }
  }
};

// ============================================================================
// 출력 및 형식 규칙
// ============================================================================

const FORMAT_RULES = {
  // JSON 출력 규격
  outputStructure: {
    required: {
      title: 'string - 매력적이고 SEO 최적화된 제목',
      content: 'string - HTML 형식의 본문 내용',
      wordCount: 'number - 실제 글자 수',
      style: 'string - 작성 스타일 식별자'
    },
    optional: {
      summary: 'string - 한 줄 요약 (필요시)',
      tags: 'array - 관련 태그 (필요시)',
      category: 'string - 분류 정보'
    },
    restrictions: [
      'JSON 외 추가 설명 금지',
      'code-fence(```) 사용 금지',
      '마크다운 형식 금지'
    ]
  },

  // HTML 형식 가이드
  htmlGuidelines: {
    structure: [
      '<p> 태그로 문단 구성',
      '<h2>, <h3> 태그로 소제목',
      '<ul>, <ol> 태그로 목록',
      '<strong> 태그로 강조'
    ],
    semantics: [
      '의미에 맞는 태그 사용',
      '접근성 고려한 구조',
      '검색엔진 친화적 마크업'
    ],
    prohibitions: [
      'CSS 스타일 속성 사용 금지',
      '인라인 스타일 금지',
      '불필요한 div 태그 금지'
    ]
  },

  // 품질 기준
  qualityStandards: {
    readability: {
      sentenceLength: '평균 25-40자',
      paragraphLength: '3-5문장',
      complexWords: '전문용어 최소화'
    },
    coherence: {
      logicalFlow: '논리적 연결성',
      topicConsistency: '주제 일관성',
      transitionSmoothness: '자연스러운 전환'
    },
    engagement: {
      personalTouch: '개인적 경험 포함',
      emotionalConnection: '감정적 공감대',
      actionOriented: '구체적 행동 제시'
    }
  }
};

// ============================================================================
// 통합 편집 가이드라인
// ============================================================================

const EDITORIAL_WORKFLOW = {
  // 작성 프로세스
  writingProcess: {
    planning: [
      '1. 주제 분석 및 키워드 추출',
      '2. 독자층 파악 및 톤 설정',
      '3. 구조 설계 (제목, 소제목, 흐름)',
      '4. 핵심 메시지 및 call-to-action 결정'
    ],
    drafting: [
      '1. 매력적인 제목 작성 (키워드 포함)',
      '2. 인사말과 주제 소개',
      '3. 본문 전개 (논리적 순서)',
      '4. 개인 경험 자연스럽게 삽입',
      '5. 결론 및 다짐으로 마무리'
    ],
    revision: [
      '1. SEO 최적화 점검 (분량, 키워드 배치)',
      '2. 법적 위험 요소 검토',
      '3. 톤앤매너 일관성 확인',
      '4. 가독성 및 흐름 개선',
      '5. JSON 형식 최종 확인'
    ]
  },

  // 품질 체크리스트
  qualityChecklist: {
    content: [
      '✅ 주제 관련성 확보',
      '✅ 개인 경험 적절히 반영',
      '✅ 건설적이고 미래지향적 메시지',
      '✅ 독자와의 공감대 형성'
    ],
    seo: [
      '✅ 1800-2300자 분량 준수',
      '✅ 키워드 자연스러운 배치',
      '✅ 제목 매력도 및 검색 최적화',
      '✅ 구조화된 소제목 활용'
    ],
    format: [
      '✅ JSON 형식 정확성',
      '✅ HTML 마크업 적절성',
      '✅ 가독성 확보',
      '✅ 일관된 톤앤매너'
    ],
    safety: [
      '✅ 법적 위험 요소 없음',
      '✅ 차별적 표현 없음',
      '✅ 사실 기반 내용',
      '✅ 출처 표기 완료'
    ]
  },

  // 개선 권장사항
  improvementTips: {
    engagement: [
      '구체적 수치와 사례 활용',
      '지역 특화 정보 포함',
      '시각적 구조화 (목록, 소제목)',
      '감정적 어필과 이성적 근거 균형'
    ],
    differentiation: [
      '개인만의 경험과 시각 강조',
      '지역 특성 반영',
      '실용적 정보 제공',
      '독자 참여 유도'
    ]
  }
};

// ============================================================================
// 내보내기
// ============================================================================

module.exports = {
  // SEO 최적화
  SEO_RULES,
  
  // 콘텐츠 작성
  CONTENT_RULES,
  
  // 형식 및 출력
  FORMAT_RULES,
  
  // 편집 워크플로우
  EDITORIAL_WORKFLOW,
};