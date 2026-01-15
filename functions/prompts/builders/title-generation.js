/**
 * functions/prompts/builders/title-generation.js
 * 네이버 블로그 제목 생성 프롬프트 (7가지 콘텐츠 구조 기반)
 *
 * 핵심 원칙:
 * - 25자 이내 (네이버 검색결과 최적화)
 * - 콘텐츠 구조(유형) 기반 분류 (도메인 X)
 * - AEO(AI 검색) 최적화
 * - 선거법 준수
 */

'use strict';

const { getElectionStage } = require('../guidelines/legal');

// ============================================================================
// 7가지 콘텐츠 구조 유형 정의
// ============================================================================

const TITLE_TYPES = {
  // 유형 1: 구체적 데이터 기반 (성과 보고)
  DATA_BASED: {
    id: 'DATA_BASED',
    name: '구체적 데이터 기반',
    when: '정책 완료, 예산 확보, 사업 완공 등 구체적 성과가 있을 때',
    pattern: '숫자 2개 이상 + 핵심 키워드',
    naverTip: '"억 원", "명", "%" 등 구체적 단위가 있으면 AI 브리핑 인용률 ↑',
    good: [
      { title: '청년 일자리 274명 창출, 지원금 85억 달성', chars: 22, analysis: '숫자 2개(274명, 85억) + 키워드 명확' },
      { title: '주택 234가구 리모델링 지원 완료', chars: 17, analysis: '구체적 수량 + 결과 명시' },
      { title: '노후 산업단지 재생, 국비 120억 확보', chars: 19, analysis: '사업명 + 금액 + 결과' },
      { title: '교통 신호등 15곳 개선, 사고율 40% 감소', chars: 21, analysis: '시설(15곳) + 효과(40%)' },
      { title: '2025년 상반기 민원 처리 3일 이내 달성', chars: 21, analysis: '시간 명시 + 구체적 기준' }
    ],
    bad: [
      { title: '좋은 성과 거뒀습니다', problem: '구체적 정보 전무', fix: '주택 234가구 지원 완료' },
      { title: '최선을 다했습니다', problem: '성과 미제시', fix: '민원 3일 이내 처리율 95%' },
      { title: '예산 많이 확보했어요', problem: '"많이"가 모호', fix: '국비 120억 확보' }
    ]
  },

  // 유형 2: 질문-해답 구조 (AEO 최적화)
  QUESTION_ANSWER: {
    id: 'QUESTION_ANSWER',
    name: '질문-해답 구조',
    when: '주민이 실제로 검색하는 질문에 답할 때',
    pattern: '"어떻게", "무엇을", "왜", "얼마" + 질문형',
    naverTip: '질문형으로 시작하면 AI 브리핑 선택률 3배↑',
    good: [
      { title: '분당구 청년 주거, 월세 지원 얼마까지?', chars: 19, analysis: '지역명 + 질문형' },
      { title: '성남 교통 체증, 어떻게 풀까?', chars: 15, analysis: '지역 + 문제 + 질문' },
      { title: '어르신 일자리, 어떤 프로그램 있나?', chars: 18, analysis: '대상 + 정책 + 질문' },
      { title: '2025년 보육료, 지원 기준 바뀌었나?', chars: 19, analysis: '정책명 + 질문형 + 변화 암시' },
      { title: '전세 사기, 피해 보상은 어떻게?', chars: 16, analysis: '사회문제 + 해결책 질문' }
    ],
    bad: [
      { title: '정책에 대해 설명드립니다', problem: '질문형 아님, 모호', fix: '청년 지원 정책, 무엇이 달라졌나?' },
      { title: '청년에 대한 정책', problem: '검색 의도 미충족', fix: '청년 창업, 몇 년 무이자 지원?' },
      { title: '궁금한 점을 해결해 드립니다', problem: '너무 범용적', fix: '아이 교육비, 지원 금액 얼마?' }
    ]
  },

  // 유형 3: 비교·대조 구조 (성과 증명)
  COMPARISON: {
    id: 'COMPARISON',
    name: '비교·대조 구조',
    when: '정책의 변화, 개선, 해결을 강조할 때',
    pattern: '전후 대비 수치 + "→", "vs", "대비"',
    naverTip: '"→", "달라졌다", "개선" 등이 검색 알고리즘 선호',
    good: [
      { title: '민원 처리 14일→3일, 5배 빨라졌어요', chars: 19, analysis: '수치 변화 + 효과' },
      { title: '청년 기본소득 월 30만→50만원 확대', chars: 19, analysis: '정책명 + 수치 대비' },
      { title: '교통 사고율, 전년 대비 40% 감소', chars: 18, analysis: '지표 + 비교 기준 + 수치' },
      { title: '쓰레기 처리 비용 99억→65억 절감', chars: 18, analysis: '구체적 절감액' },
      { title: '주차장 부족 지역, 12개월 만에 해결', chars: 18, analysis: '문제 + 기간 + 결과' }
    ],
    bad: [
      { title: '이전보다 나아졌어요', problem: '"이전" 모호', fix: '민원 처리 14일→3일 개선' },
      { title: '많이 개선되었습니다', problem: '"많이" 검증 불가', fix: '교통 사고율 40% 감소' },
      { title: '시간이 단축되었습니다', problem: '얼마나?', fix: '민원 처리 14일→3일 단축' }
    ]
  },

  // 유형 4: 지역 맞춤형 정보 (초지역화)
  LOCAL_FOCUSED: {
    id: 'LOCAL_FOCUSED',
    name: '지역 맞춤형 정보',
    when: '특정 동·면·읍의 주민을 타겟할 때',
    pattern: '행정구역명(동 단위) + 정책 + 숫자',
    naverTip: '동단위 키워드는 경쟁도 낮아 상위노출 유리',
    good: [
      { title: '분당구 정자동 도시가스, 기금 70억 확보', chars: 21, analysis: '지역명(동) + 정책 + 숫자' },
      { title: '수지구 풍덕천동 학교 신설, 9월 개교', chars: 19, analysis: '지역명(동) + 사업명 + 일정' },
      { title: '성남시 중원구 보육료, 월 15만원 추가', chars: 20, analysis: '행정구역 + 정책 + 지원액' },
      { title: '용인시 기흥구 요양원, 신청 마감 1주', chars: 19, analysis: '지역명 + 시설 + 긴급성' },
      { title: '영통구 광교동 교통, 6개월간 35% 개선', chars: 21, analysis: '지역명 + 지표 + 기간 + 효과' }
    ],
    bad: [
      { title: '우리 지역을 위해 노력합니다', problem: '지역명 없음', fix: '분당구 정자동 도시가스 70억' },
      { title: '지역 정책 안내', problem: '어느 지역? 어떤 정책?', fix: '성남시 중원구 보육료 월 15만원' },
      { title: '동네 주차장 문제', problem: '지역명·해결책 부재', fix: '분당구 정자동 주차장 50면 추가' }
    ]
  },

  // 유형 5: 전문 지식 공유 (법안·조례·정책)
  EXPERT_KNOWLEDGE: {
    id: 'EXPERT_KNOWLEDGE',
    name: '전문 지식 공유',
    when: '법안 발의, 조례 제정, 정책 분석 글을 쓸 때',
    pattern: '"법안", "조례", "제도" + 핵심 내용',
    naverTip: '전문 용어로 E-E-A-T 강조, 일반인도 검색하는 키워드',
    good: [
      { title: '청년 기본소득법 발의, 월 50만원 지원안', chars: 20, analysis: '법안명 + 정책내용 + 금액' },
      { title: '주차장 설치 의무 조례 개정 추진', chars: 17, analysis: '조례명 + 동작(개정)' },
      { title: '전세 사기 피해자 보호법, 핵심 3가지', chars: 19, analysis: '법안명 + 요약 포인트' },
      { title: '야간 상점 CCTV 의무화 조례안 통과', chars: 18, analysis: '정책내용 + 조례형태 + 결과' },
      { title: '자영업자 신용대출, 금리 인하 정책 추진', chars: 20, analysis: '대상 + 정책 + 구체성' }
    ],
    bad: [
      { title: '법안을 발의했습니다', problem: '"법안" 모호', fix: '청년 기본소득법 발의, 월 50만원' },
      { title: '조례에 대해 설명드립니다', problem: '조례명 부재', fix: '주차장 설치 의무 조례 개정' },
      { title: '제도 개선 관련 제안', problem: '"제도 개선" 추상적', fix: '전세 사기 피해자 보호법 발의' }
    ]
  },

  // 유형 6: 시간 중심 신뢰성 (정기 보고)
  TIME_BASED: {
    id: 'TIME_BASED',
    name: '시간 중심 신뢰성',
    when: '월간 보고서, 분기 리포트, 연간 성과 정리 시',
    pattern: '"2025년", "상반기", "월간" + 형식(보고서/리포트)',
    naverTip: '시간 명시가 검색 신선도 신호로 작용',
    good: [
      { title: '2025년 상반기 의정 보고서, 5대 성과', chars: 20, analysis: '시간 명시 + 형식 + 성과수' },
      { title: '6월 민원 처리 리포트, 1,234건 해결', chars: 20, analysis: '월명 + 형식 + 구체적 수치' },
      { title: '2025년 1분기 예산 집행 현황 공개', chars: 19, analysis: '기간 + 항목명 + 공개 신호' },
      { title: '상반기 주민 의견 분석, 88건 반영 추진', chars: 20, analysis: '기간 + 활동 + 숫자' },
      { title: '월간 의정 뉴스레터 (7월호) 배포', chars: 18, analysis: '시간 명시 + 형식명' }
    ],
    bad: [
      { title: '보고서를 올립니다', problem: '시간 미명시', fix: '2025년 상반기 의정 보고서' },
      { title: '최근 활동을 정리했습니다', problem: '"최근" 애매', fix: '6월 민원 처리 리포트, 1,234건' },
      { title: '분기별 현황입니다', problem: '어느 분기?', fix: '2025년 1분기 예산 집행 현황' }
    ]
  },

  // 유형 7: 정계 이슈·분석 (국가 정책·거시) - 논평/시사 글
  ISSUE_ANALYSIS: {
    id: 'ISSUE_ANALYSIS',
    name: '정계 이슈·분석',
    when: '정계 이슈, 국가 정책 논평, 제도 개혁 분석, 다른 정치인 논평 시',
    pattern: '이슈명 + 화자 관점 + 인용문 스타일',
    naverTip: '작성자(화자) 이름을 제목에 포함하면 개인 브랜딩 + SEO 효과',
    good: [
      { title: '윤석열 사형 구형, 이재성이 본 조경태의 소신', chars: 23, analysis: '이슈 + 화자 관점 + 대상' },
      { title: '이재성 \'헌법 앞에 여야 없다\' 조경태 소신 논평', chars: 24, analysis: '화자 + 인용문 + 대상' },
      { title: '조경태 칭찬한 이재성, 윤석열 사형 구형 논평', chars: 23, analysis: '관계 + 화자 + 이슈' },
      { title: '윤석열 사형 구형? 이재성 \'조경태 소신에 박수\'', chars: 25, analysis: '물음표 + 화자 인용' },
      { title: '박형준 침묵 vs 조경태 소신, 이재성의 평가', chars: 23, analysis: '대비 구조 + 화자 관점' }
    ],
    bad: [
      { title: '윤석열 사형 구형 발언, 조경태 의원 칭찬', problem: '화자 누락, 밋밋함', fix: '윤석열 사형 구형, 이재성이 본 조경태의 소신' },
      { title: '정치인 발언에 대한 논평', problem: '누가? 무슨 발언?', fix: '이재성 \'헌법 앞에 여야 없다\' 조경태 논평' },
      { title: '조경태 의원 관련 글', problem: '구체적 행동 부재', fix: '조경태 칭찬한 이재성, 윤석열 사형 구형 논평' }
    ]
  }
};

// ============================================================================
// 콘텐츠 구조 자동 감지
// ============================================================================

/**
 * 본문 내용을 분석하여 적합한 제목 유형을 감지
 * @param {string} contentPreview - 본문 미리보기
 * @param {string} category - 카테고리 (참고용)
 * @returns {string} - 추천 유형 ID
 */
function detectContentType(contentPreview, category) {
  const text = contentPreview.toLowerCase();

  // 숫자 패턴 감지
  const hasNumbers = /\d+억|\d+만원|\d+%|\d+명|\d+건|\d+가구|\d+곳/.test(contentPreview);
  const hasComparison = /→|에서|으로|전년|대비|개선|감소|증가|변화/.test(text);
  const hasQuestion = /\?|어떻게|무엇|왜|얼마|언제/.test(text);
  const hasLegalTerms = /법안|조례|법률|제도|개정|발의|통과/.test(text);
  const hasTimeTerms = /2025년|상반기|하반기|분기|월간|연간|보고서|리포트/.test(text);
  // 🔴 [Phase 1] 정규식 강화: 띄어쓰기 없이도 인식
  const hasLocalTerms = /[가-힣]+(동|구|군|시|읍|면|리)(?:[가-힣]|\s|,|$)/.test(contentPreview);
  const hasIssueTerms = /개혁|분권|양극화|격차|투명성|문제점|대안/.test(text);

  // 우선순위 기반 유형 결정
  if (hasTimeTerms && (text.includes('보고') || text.includes('리포트') || text.includes('현황'))) {
    return 'TIME_BASED';
  }
  if (hasLegalTerms) {
    return 'EXPERT_KNOWLEDGE';
  }
  if (hasComparison && hasNumbers) {
    return 'COMPARISON';
  }
  if (hasQuestion) {
    return 'QUESTION_ANSWER';
  }
  if (hasNumbers && !hasIssueTerms) {
    return 'DATA_BASED';
  }
  if (hasIssueTerms && !hasLocalTerms) {
    return 'ISSUE_ANALYSIS';
  }
  if (hasLocalTerms) {
    return 'LOCAL_FOCUSED';
  }

  // 카테고리 기반 폴백
  const categoryMapping = {
    'activity-report': 'DATA_BASED',
    'policy-proposal': 'EXPERT_KNOWLEDGE',
    'local-issues': 'LOCAL_FOCUSED',
    'current-affairs': 'ISSUE_ANALYSIS',
    'daily-communication': 'QUESTION_ANSWER'
  };

  return categoryMapping[category] || 'DATA_BASED';
}

// ============================================================================
// 🔴 Phase 1: 본문에서 숫자 추출 (제목 검증용)
// ============================================================================

/**
 * 본문에서 숫자+단위 패턴을 추출
 * 제목에 사용 가능한 숫자 목록 제공
 * 
 * @param {string} content - 본문 내용
 * @returns {Object} { numbers: string[], instruction: string }
 */
function extractNumbersFromContent(content) {
  if (!content) return { numbers: [], instruction: '' };

  // 숫자+단위 패턴 (억, 만원, %, 명, 건, 가구, 곳, 개, 회, 배 등)
  const patterns = [
    /\d+(?:,\d{3})*억원?/g,
    /\d+(?:,\d{3})*만원?/g,
    /\d+(?:\.\d+)?%/g,
    /\d+(?:,\d{3})*명/g,
    /\d+(?:,\d{3})*건/g,
    /\d+(?:,\d{3})*가구/g,
    /\d+(?:,\d{3})*곳/g,
    /\d+(?:,\d{3})*개/g,
    /\d+(?:,\d{3})*회/g,
    /\d+배/g,
    /\d+(?:,\d{3})*원/g,
    /\d+일/g,
    /\d+개월/g,
    /\d+년/g,
    /\d+분기/g
  ];

  const allMatches = new Set();

  for (const pattern of patterns) {
    const matches = content.match(pattern);
    if (matches) {
      matches.forEach(m => allMatches.add(m));
    }
  }

  const numbers = Array.from(allMatches);

  if (numbers.length === 0) {
    return {
      numbers: [],
      instruction: '\n【숫자 제약】본문에 구체적 수치가 없습니다. 숫자 없이 제목을 작성하세요.\n'
    };
  }

  return {
    numbers,
    instruction: `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 【숫자 제약】본문에 등장하는 숫자만 사용 가능!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ 사용 가능 숫자: ${numbers.slice(0, 10).join(', ')}${numbers.length > 10 ? ' (외 ' + (numbers.length - 10) + '개)' : ''}
❌ 위 목록에 없는 숫자는 절대 제목에 넣지 마세요!

예시:
• 본문에 "274명"이 있으면 → "청년 일자리 274명" ✅
• 본문에 "85억"이 없는데 → "지원금 85억" ❌ (날조!)
`
  };
}

// ============================================================================
// 선거법 준수 지시문
// ============================================================================

function getElectionComplianceInstruction(status) {
  const electionStage = getElectionStage(status);
  const isPreCandidate = electionStage?.name === 'STAGE_1';

  if (!isPreCandidate) return '';

  return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 선거법 준수 (현재 상태: ${status} - 예비후보 등록 이전)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

❌ 절대 금지 표현:
• "약속", "공약", "약속드립니다"
• "당선되면", "당선 후"
• "~하겠습니다" (공약성 미래 약속)
• "지지해 주십시오"

✅ 허용 표현:
• "정책 방향", "정책 제시", "비전 공유"
• "연구하겠습니다", "노력하겠습니다"
• "추진", "추구", "검토"

예시:
❌ "청년 기본소득, 꼭 약속드리겠습니다"
✅ "청년 기본소득, 정책 방향 제시"
`;
}

// ============================================================================
// SEO 키워드 삽입 전략 (위치별 가중치)
// ============================================================================

const KEYWORD_POSITION_GUIDE = {
  front: {
    range: '0-8자',
    weight: '100%',
    use: '지역명, 정책명, 핵심 주제',
    example: '"분당구 청년 기본소득" → "분당구"가 검색 가중치 최고'
  },
  middle: {
    range: '9-17자',
    weight: '80%',
    use: '구체적 수치, LSI 키워드',
    example: '"월 50만원", "주거·일자리"'
  },
  end: {
    range: '18-25자',
    weight: '60%',
    use: '행동 유도, 긴급성, 신뢰성 신호',
    example: '"신청 마감 3일 전", "5대 성과"'
  }
};

/**
 * 키워드 삽입 전략 지시문 생성
 */
function getKeywordStrategyInstruction(userKeywords, keywords) {
  const hasUserKeywords = userKeywords && userKeywords.length > 0;
  const primaryKw = hasUserKeywords ? userKeywords[0] : (keywords?.[0] || '');
  const secondaryKw = hasUserKeywords
    ? (userKeywords[1] || keywords?.[0] || '')
    : (keywords?.[1] || '');

  return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔑 SEO 키워드 삽입 전략
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 **앞쪽 1/3 법칙** (가장 중요!)
네이버는 제목 앞 8-10자를 가장 중요하게 평가합니다.
→ 핵심 키워드는 반드시 제목 시작 부분에!

❌ "우리 지역 청년들을 위한 청년 기본소득"
✅ "청년 기본소득, 분당구 월 50만원 지원"

📊 **키워드 밀도: 최소 1개, 최대 3개**
• 최적: 2개 (가장 자연스럽고 효과적)
• 4개 이상: 스팸으로 판단, CTR 감소

✅ "분당구 청년 기본소득, 월 50만원" (2개: 분당구, 청년 기본소득)
❌ "분당구 정자동 청년 기본소득 월 50만원 지원" (4개, 어색)

📍 **위치별 배치 전략**
┌─────────────────────────────────────────────┐
│ [0-8자]     │ [9-17자]      │ [18-25자]   │
│ 지역/정책명  │ 수치/LSI     │ 행동/긴급성  │
│ 가중치 100% │ 가중치 80%   │ 가중치 60%  │
└─────────────────────────────────────────────┘

${primaryKw ? `**1순위 키워드**: "${primaryKw}" → 제목 앞 8자 이내 배치` : ''}
${secondaryKw ? `**2순위 키워드**: "${secondaryKw}" → 제목 중앙 배치` : ''}

🔄 **동의어 활용** (반복 방지)
• 지원 → 지원금, 보조금, 혜택
• 문제 → 현안, 과제, 어려움
• 해결 → 개선, 완화, 해소
`;
}

// ============================================================================
// 프롬프트 빌더
// ============================================================================

/**
 * 본문 내용 기반 제목 생성 프롬프트를 빌드합니다
 */
function buildTitlePrompt({ contentPreview, backgroundText, topic, fullName, keywords, userKeywords, category, subCategory, status, titleScope = null, _forcedType = null }) {
  // 1. 콘텐츠 유형 자동 감지 (또는 강제 유형 사용)
  const avoidLocalInTitle = Boolean(titleScope && titleScope.avoidLocalInTitle);
  let detectedTypeId;

  // 🔴 [Phase 1] _forcedType 파라미터 처리
  if (_forcedType && TITLE_TYPES[_forcedType]) {
    detectedTypeId = _forcedType;
    console.log(`🎯 [TitleGen] 강제 유형 적용: ${_forcedType}`);
  } else {
    detectedTypeId = detectContentType(contentPreview, category);
    if (avoidLocalInTitle && detectedTypeId === 'LOCAL_FOCUSED') {
      detectedTypeId = 'ISSUE_ANALYSIS';
    }
  }
  const primaryType = TITLE_TYPES[detectedTypeId];

  // 🔴 [Phase 1] 숫자 추출 및 검증 지시문 생성
  const numberValidation = extractNumbersFromContent(contentPreview);

  // 2. 선거법 준수 지시문
  const electionCompliance = getElectionComplianceInstruction(status);

  // 3. 키워드 전략 지시문
  const keywordStrategy = getKeywordStrategyInstruction(userKeywords, keywords);

  const regionScopeInstruction = avoidLocalInTitle
    ? [
      '[TITLE REGION SCOPE]',
      `- Target position: ${titleScope && titleScope.position ? titleScope.position : 'metro-level'}`,
      '- Do NOT use district/town names (gu/gun/dong/eup/myeon) in the title.',
      `- Use the metro-wide region like "${titleScope && titleScope.regionMetro ? titleScope.regionMetro : 'the city/province'}".`
    ].join('\n')
    : '';

  // 4. Few-shot 예시 구성
  const goodExamples = primaryType.good
    .map((ex, i) => `${i + 1}. "${ex.title}" (${ex.chars}자)\n   → ${ex.analysis}`)
    .join('\n');

  const badExamples = primaryType.bad
    .map((ex, i) => `${i + 1}. ❌ "${ex.title}"\n   문제: ${ex.problem}\n   ✅ 수정: "${ex.fix}"`)
    .join('\n\n');

  // 5. 키워드 처리 (표시용)
  const primaryKeywords = userKeywords && userKeywords.length > 0
    ? userKeywords.slice(0, 3).join(', ')
    : '';
  const secondaryKeywords = keywords
    ? keywords.filter(k => !userKeywords?.includes(k)).slice(0, 3).join(', ')
    : '';

  return `당신은 네이버 블로그 제목 전문가입니다. 아래 규칙을 엄격히 따라 제목을 생성하세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📏 절대 규칙: 25자 이내
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• 최적: 15~22자 (가장 높은 클릭률)
• 25자 초과 시 네이버 검색결과에서 잘림
• 25자 초과 시 자르지 말고 다시 구성
• 작성 후 반드시 글자 수 확인!
${electionCompliance}
${keywordStrategy}
${numberValidation.instruction}
${regionScopeInstruction}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 감지된 콘텐츠 유형: ${primaryType.name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**사용 시점**: ${primaryType.when}
**제목 패턴**: ${primaryType.pattern}
**네이버 최적화**: ${primaryType.naverTip}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 좋은 예시 (이 패턴을 따라하세요)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
${goodExamples}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
❌ 나쁜 예시 → ✅ 수정 방법
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
${badExamples}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 본문 정보
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**주제**: ${topic}
**작성자**: ${fullName}

**본문 미리보기**:
${String(contentPreview || '').substring(0, 800)}

**배경정보**:
${backgroundText ? backgroundText.substring(0, 300) : '(없음)'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 [최우선] 주제 기반 제목 생성 원칙
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 사용자가 입력한 **"주제"가 제목의 가장 중요한 참고 요소**입니다!

[규칙]
1. 주제에 명시된 핵심 요소(인물, 행동, 대비)를 반드시 제목에 반영
2. Few-Shot 예시는 스타일/패턴 참고용일 뿐, 주제를 대체하면 안 됨
3. 주제와 무관한 본문 내용(경제, AI 등)을 제목으로 쓰지 말 것

예시:
• 주제: "尹 사형 구형, 조경태 칭찬하고 박형준 질타"
  → ✅ "尹 사형 구형, 조경태 칭찬·박형준 질타하는 이재성"
  → ❌ "부산 AI 예산 103억, 경제 혁신 이끈다" (주제 이탈!)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 최종 출력 규칙
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **25자 이내 권장** (필수는 아니지만 네이버 최적화)
2. **길면 자르지 말고 다시 구성**
3. **핵심 키워드 앞 8자 배치** (앞쪽 1/3 법칙)
4. **본문에 실제 등장하는 숫자만 사용** (없으면 생략 가능, 절대 만들어내지 말 것!)
5. 콤마(,), 콜론(:), 물음표(?)는 자연스럽게 사용 가능
6. "~에 대한", "~관련" 불필요 표현 제거
7. 키워드 최대 3개 (2개 최적)

**출력**: 순수한 제목 텍스트만. 따옴표, 설명, 글자수 표시 없이.

제목:`;
}

// ============================================================================
// 유형별 제목 생성 (특정 유형 강제 시)
// ============================================================================

/**
 * 특정 유형으로 제목을 생성하고 싶을 때 사용
 * @param {string} typeId - TITLE_TYPES의 키
 * @param {Object} params - buildTitlePrompt와 동일한 파라미터
 */
function buildTitlePromptWithType(typeId, params) {
  // 원본 detectContentType을 오버라이드
  const originalDetect = detectContentType;
  const overriddenDetect = () => typeId;

  // 임시로 교체 후 프롬프트 생성
  const prompt = buildTitlePrompt({
    ...params,
    // 내부적으로 typeId 강제
    _forcedType: typeId
  });

  return prompt;
}

// ============================================================================
// 🟢 Phase 2-1: 템플릿 주입용 제목 가이드라인 (명확화)
// ============================================================================

/**
 * 템플릿에 주입할 제목 가이드라인 생성
 * WriterAgent가 본문과 함께 제목을 생성할 때 사용
 * 
 * 🔴 Phase 2 개선: 필수/권장/선택 명확히 구분
 * 
 * @param {Array} userKeywords - 사용자 입력 키워드
 * @param {Object} options - { authorName, category }
 * @returns {string} 제목 가이드라인 텍스트
 */
function getTitleGuidelineForTemplate(userKeywords = [], options = {}) {
  const { authorName = '', category = '' } = options;
  const primaryKw = userKeywords[0] || '';
  const isIssueCategory = ['current-affairs', 'bipartisan-cooperation'].includes(category);

  return `
╔═══════════════════════════════════════════════════════════════╗
║  🚨 제목 품질 조건 - 3단계 규칙 체계                              ║
╚═══════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 【필수】 위반 시 재생성 (MUST)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 25자 이내 (네이버 검색결과에서 잘림 방지)
2. 숫자는 본문에 실제 등장한 것만 사용 (날조 금지!)
3. 사실과 다른 표현 금지 (본문에 없는 행동/발언 작성 금지)
4. 주제와 무관한 내용 금지 (입력된 주제 핵심 요소 반영 필수)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟡 【권장】 품질 향상 (SHOULD)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. ${primaryKw ? `키워드 "${primaryKw}"를 제목 앞 8자 안에 배치` : '핵심 키워드를 제목 앞 8자 안에 배치'}
2. 15-22자 길이 (클릭률 최고 구간)
3. 구체적 숫자 포함 (274명, 85억 등)
${isIssueCategory ? `4. 화자 이름 포함 (예: "${authorName || '이재성'}이 본", "${authorName || '이재성'} '...'")` : ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 【선택】 차별화 (COULD)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 물음표(?) 활용 - 호기심 자극
2. 대비 구조 (A vs B, 전→후)
3. 인용문 스타일 ('...')

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 임팩트 제목 패턴 (높은 클릭률)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ 화자 관점: "○○이 본 ~~" → "${authorName || '이재성'}이 본 조경태의 소신"
✅ 인용문형: "○○ '인용' ~~" → "${authorName || '이재성'} '헌법 앞에 여야 없다'"
✅ 대비 구조: "A vs B" → "박형준 침묵 vs 조경태 소신"
✅ 관계 강조: "A 칭찬한 B" → "조경태 칭찬한 ${authorName || '이재성'}"

❌ 밋밋한 제목은 클릭률이 떨어집니다!
`;
}

// ============================================================================
// 🟢 Phase 2-2: 주제-본문 교차 검증 (validateThemeAndContent)
// ============================================================================

/**
 * 주제와 본문 콘텐츠가 일치하는지 검증
 * 제목이 주제를 정확히 반영하는지 확인하는 데 사용
 * 
 * @param {string} topic - 사용자 입력 주제
 * @param {string} content - 본문 내용
 * @param {string} title - 생성된 제목 (선택)
 * @returns {Object} { isValid, mismatchReasons, topicKeywords, contentKeywords, overlapScore }
 */
function validateThemeAndContent(topic, content, title = '') {
  if (!topic || !content) {
    return {
      isValid: false,
      mismatchReasons: ['주제 또는 본문이 비어있습니다'],
      topicKeywords: [],
      contentKeywords: [],
      overlapScore: 0
    };
  }

  // 1. 주제에서 핵심 키워드 추출 (인명, 행동, 핵심어)
  const topicKeywords = extractTopicKeywords(topic);

  // 2. 본문에서 키워드 빈도 확인
  const contentLower = content.toLowerCase();
  const matchedKeywords = [];
  const missingKeywords = [];

  for (const keyword of topicKeywords) {
    if (contentLower.includes(keyword.toLowerCase())) {
      matchedKeywords.push(keyword);
    } else {
      missingKeywords.push(keyword);
    }
  }

  // 3. 점수 계산 (주제 키워드 중 본문에 있는 비율)
  const overlapScore = topicKeywords.length > 0
    ? Math.round((matchedKeywords.length / topicKeywords.length) * 100)
    : 0;

  // 4. 불일치 사유 수집
  const mismatchReasons = [];

  if (overlapScore < 50) {
    mismatchReasons.push(`주제 핵심어 중 ${missingKeywords.length}개가 본문에 없음: ${missingKeywords.join(', ')}`);
  }

  // 5. 제목이 있으면 제목-주제 일치도 검증
  if (title) {
    const titleLower = title.toLowerCase();
    const titleMissingFromTopic = topicKeywords.filter(kw => !titleLower.includes(kw.toLowerCase()));

    if (titleMissingFromTopic.length > topicKeywords.length * 0.5) {
      mismatchReasons.push(`제목에 주제 핵심어 부족: ${titleMissingFromTopic.slice(0, 3).join(', ')}`);
    }
  }

  return {
    isValid: overlapScore >= 50 && mismatchReasons.length === 0,
    mismatchReasons,
    topicKeywords,
    matchedKeywords,
    missingKeywords,
    overlapScore
  };
}

/**
 * 주제에서 핵심 키워드 추출
 * @private
 */
function extractTopicKeywords(topic) {
  const keywords = [];

  // 1. 인명 추출 (2-4자 한글 + 직함)
  const nameMatches = topic.match(/[가-힣]{2,4}(?=\s*(의원|시장|구청장|대통령|총리|장관|대표)?)/g);
  if (nameMatches) {
    keywords.push(...nameMatches.slice(0, 3));  // 최대 3명
  }

  // 2. 핵심 행동/이슈 추출
  const actionKeywords = ['칭찬', '질타', '비판', '논평', '발언', '소신', '침묵', '사형', '구형', '협력', '대립'];
  for (const action of actionKeywords) {
    if (topic.includes(action)) {
      keywords.push(action);
    }
  }

  // 3. 숫자+단위 추출
  const numberMatches = topic.match(/\d+(?:억|만원|%|명|건)?/g);
  if (numberMatches) {
    keywords.push(...numberMatches.slice(0, 2));
  }

  return [...new Set(keywords)];  // 중복 제거
}

// ============================================================================
// 🔵 Phase 3-1: 제목 품질 점수 계산 (calculateTitleQualityScore)
// ============================================================================

/**
 * 제목 품질을 6가지 기준으로 평가하여 점수 산출
 * 
 * 평가 기준:
 * 1. 길이 적합성 (15-25자)
 * 2. 키워드 위치 (앞 8자)
 * 3. 숫자 포함 여부
 * 4. 주제 일치도
 * 5. 본문 사실 일치
 * 6. 임팩트 요소 (물음표, 인용문 등)
 * 
 * @param {string} title - 평가할 제목
 * @param {Object} params - { topic, content, userKeywords, authorName }
 * @returns {Object} { score, breakdown, passed, suggestions }
 */
function calculateTitleQualityScore(title, params = {}) {
  const { topic = '', content = '', userKeywords = [], authorName = '' } = params;

  if (!title) {
    return {
      score: 0,
      breakdown: {},
      passed: false,
      suggestions: ['제목이 없습니다']
    };
  }

  const breakdown = {};
  const suggestions = [];
  const titleLength = title.length;

  // 1. 길이 점수 (최대 20점)
  if (titleLength >= 15 && titleLength <= 22) {
    breakdown.length = { score: 20, max: 20, status: '최적' };
  } else if (titleLength >= 10 && titleLength <= 25) {
    breakdown.length = { score: 15, max: 20, status: '양호' };
  } else if (titleLength > 25) {
    breakdown.length = { score: 0, max: 20, status: '초과' };
    suggestions.push(`제목이 ${titleLength}자입니다. 25자 이내로 줄이세요.`);
  } else {
    breakdown.length = { score: 10, max: 20, status: '짧음' };
    suggestions.push('제목이 너무 짧습니다. 15자 이상 권장.');
  }

  // 2. 키워드 위치 점수 (최대 20점) - 복수 키워드 지원
  if (userKeywords.length > 0) {
    // 모든 키워드의 위치 확인
    const keywordPositions = userKeywords.map(kw => ({
      keyword: kw,
      index: title.indexOf(kw),
      inFront8: title.indexOf(kw) >= 0 && title.indexOf(kw) <= 8
    }));

    const anyInFront8 = keywordPositions.some(kp => kp.inFront8);
    const anyInTitle = keywordPositions.some(kp => kp.index >= 0);
    const frontKeyword = keywordPositions.find(kp => kp.inFront8)?.keyword || '';
    const anyKeyword = keywordPositions.find(kp => kp.index >= 0)?.keyword || '';

    if (anyInFront8) {
      breakdown.keywordPosition = { score: 20, max: 20, status: '최적', keyword: frontKeyword };
    } else if (anyInTitle) {
      breakdown.keywordPosition = { score: 12, max: 20, status: '포함됨', keyword: anyKeyword };
      suggestions.push(`키워드 "${anyKeyword}"를 제목 앞쪽(8자 내)으로 이동하면 SEO 효과 증가.`);
    } else {
      breakdown.keywordPosition = { score: 0, max: 20, status: '없음', keywords: userKeywords };
      suggestions.push(`키워드 중 하나라도 제목에 포함하세요: ${userKeywords.slice(0, 2).join(', ')}`);
    }
  } else {
    breakdown.keywordPosition = { score: 10, max: 20, status: '키워드없음' };
  }

  // 3. 숫자 포함 점수 (최대 15점)
  const hasNumbers = /\d+(?:억|만원|%|명|건|가구|곳)?/.test(title);
  if (hasNumbers) {
    // 본문에서 추출한 숫자와 일치하는지 확인
    const contentNumbers = extractNumbersFromContent(content);
    const titleNumbers = title.match(/\d+(?:억|만원|%|명|건|가구|곳)?/g) || [];

    const allValid = titleNumbers.every(num =>
      contentNumbers.numbers.some(cn => cn.includes(num) || num.includes(cn.replace(/[^\d]/g, '')))
    );

    if (allValid) {
      breakdown.numbers = { score: 15, max: 15, status: '검증됨' };
    } else {
      breakdown.numbers = { score: 5, max: 15, status: '미검증' };
      suggestions.push('제목의 숫자가 본문에서 확인되지 않았습니다.');
    }
  } else {
    breakdown.numbers = { score: 8, max: 15, status: '없음' };
  }

  // 4. 주제 일치도 점수 (최대 25점) - 가장 중요
  if (topic) {
    const themeValidation = validateThemeAndContent(topic, content, title);

    if (themeValidation.overlapScore >= 80) {
      breakdown.topicMatch = { score: 25, max: 25, status: '높음', overlap: themeValidation.overlapScore };
    } else if (themeValidation.overlapScore >= 50) {
      breakdown.topicMatch = { score: 15, max: 25, status: '보통', overlap: themeValidation.overlapScore };
      suggestions.push(...themeValidation.mismatchReasons.slice(0, 1));
    } else {
      breakdown.topicMatch = { score: 5, max: 25, status: '낮음', overlap: themeValidation.overlapScore };
      suggestions.push('제목이 주제와 많이 다릅니다. 주제 핵심어를 반영하세요.');
    }
  } else {
    breakdown.topicMatch = { score: 15, max: 25, status: '주제없음' };
  }

  // 5. 화자 포함 점수 (최대 10점) - 논평/시사 글
  if (authorName) {
    if (title.includes(authorName)) {
      breakdown.authorIncluded = { score: 10, max: 10, status: '포함' };
    } else {
      breakdown.authorIncluded = { score: 0, max: 10, status: '미포함' };
      suggestions.push(`화자 "${authorName}"를 제목에 포함하면 브랜딩에 도움됩니다.`);
    }
  } else {
    breakdown.authorIncluded = { score: 5, max: 10, status: '해당없음' };
  }

  // 6. 임팩트 요소 점수 (최대 10점)
  let impactScore = 0;
  const impactFeatures = [];

  if (title.includes('?')) { impactScore += 3; impactFeatures.push('물음표'); }
  if (/'.*'/.test(title) || /".*"/.test(title)) { impactScore += 3; impactFeatures.push('인용문'); }
  if (/vs|\bvs\b|→|대비/.test(title)) { impactScore += 2; impactFeatures.push('대비구조'); }
  if (/이 본|가 본/.test(title)) { impactScore += 2; impactFeatures.push('관점표현'); }

  breakdown.impact = {
    score: Math.min(impactScore, 10),
    max: 10,
    status: impactScore > 0 ? '있음' : '없음',
    features: impactFeatures
  };

  // 총점 계산
  const totalScore = Object.values(breakdown).reduce((sum, item) => sum + (item.score || 0), 0);
  const maxScore = Object.values(breakdown).reduce((sum, item) => sum + (item.max || 0), 0);
  const normalizedScore = Math.round((totalScore / maxScore) * 100);

  return {
    score: normalizedScore,
    rawScore: totalScore,
    maxScore,
    breakdown,
    passed: normalizedScore >= 70,  // 70점 이상 통과
    suggestions: suggestions.slice(0, 3)  // 최대 3개 제안
  };
}

// ============================================================================
// 🔵 Phase 3-2: 제목 생성 및 자동 검증 (generateAndValidateTitle)
// ============================================================================

/**
 * 제목을 생성하고 품질 점수 기준으로 자동 재시도
 * 
 * 흐름:
 * 1. 제목 생성 (LLM 호출)
 * 2. 품질 점수 계산
 * 3. 70점 미만 시 피드백 포함 재생성
 * 4. 최대 3회 시도 후 최고 점수 버전 반환
 * 
 * @param {Function} generateFn - 제목 생성 함수 (prompt) => Promise<string>
 * @param {Object} params - buildTitlePrompt 파라미터
 * @param {Object} options - { minScore, maxAttempts, onProgress }
 * @returns {Promise<Object>} { title, score, attempts, history }
 */
async function generateAndValidateTitle(generateFn, params, options = {}) {
  const {
    minScore = 70,
    maxAttempts = 3,
    onProgress = null
  } = options;

  const history = [];
  let bestTitle = '';
  let bestScore = 0;
  let bestResult = null;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    // 진행 상황 콜백
    if (onProgress) {
      onProgress({ attempt, maxAttempts, status: 'generating' });
    }

    // 1. 프롬프트 생성 (이전 시도 피드백 포함)
    let prompt;
    if (attempt === 1) {
      prompt = buildTitlePrompt(params);
    } else {
      // 이전 시도 피드백 추가
      const lastAttempt = history[history.length - 1];
      const feedbackPrompt = `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 이전 제목 피드백 (점수: ${lastAttempt.score}/100)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
이전 제목: "${lastAttempt.title}"
문제점:
${lastAttempt.suggestions.map(s => `• ${s}`).join('\n')}

위 문제를 해결한 새로운 제목을 작성하세요.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

`;
      prompt = feedbackPrompt + buildTitlePrompt(params);
    }

    // 2. 제목 생성 (LLM 호출)
    let generatedTitle;
    try {
      generatedTitle = await generateFn(prompt);
      generatedTitle = (generatedTitle || '').trim().replace(/^["']|["']$/g, '');
    } catch (error) {
      console.error(`[TitleGen] 생성 오류 (${attempt}/${maxAttempts}):`, error.message);
      continue;
    }

    if (!generatedTitle) {
      continue;
    }

    // 3. 품질 점수 계산
    const scoreResult = calculateTitleQualityScore(generatedTitle, {
      topic: params.topic,
      content: params.contentPreview,
      userKeywords: params.userKeywords,
      authorName: params.fullName
    });

    // 기록 저장
    history.push({
      attempt,
      title: generatedTitle,
      score: scoreResult.score,
      suggestions: scoreResult.suggestions,
      breakdown: scoreResult.breakdown
    });

    console.log(`🎯 [TitleGen] 시도 ${attempt}: "${generatedTitle}" (점수: ${scoreResult.score})`);

    // 최고 점수 갱신
    if (scoreResult.score > bestScore) {
      bestScore = scoreResult.score;
      bestTitle = generatedTitle;
      bestResult = scoreResult;
    }

    // 통과 시 즉시 반환
    if (scoreResult.score >= minScore) {
      console.log(`✅ [TitleGen] 통과! (${attempt}회 시도, 점수: ${scoreResult.score})`);

      if (onProgress) {
        onProgress({ attempt, maxAttempts, status: 'passed', score: scoreResult.score });
      }

      return {
        title: generatedTitle,
        score: scoreResult.score,
        attempts: attempt,
        passed: true,
        history,
        breakdown: scoreResult.breakdown
      };
    }
  }

  // 최대 시도 후 최고 점수 버전 반환
  console.warn(`⚠️ [TitleGen] ${maxAttempts}회 시도 후 최고 점수 버전 반환 (점수: ${bestScore})`);

  if (onProgress) {
    onProgress({ attempt: maxAttempts, maxAttempts, status: 'best_effort', score: bestScore });
  }

  return {
    title: bestTitle,
    score: bestScore,
    attempts: maxAttempts,
    passed: bestScore >= minScore,
    history,
    breakdown: bestResult?.breakdown || {}
  };
}


// ============================================================================
// Exports
// ============================================================================

module.exports = {
  buildTitlePrompt,
  buildTitlePromptWithType,
  detectContentType,
  TITLE_TYPES,
  KEYWORD_POSITION_GUIDE,
  getElectionComplianceInstruction,
  getKeywordStrategyInstruction,
  // 📌 템플릿 주입용
  getTitleGuidelineForTemplate,
  // 🔴 Phase 1: 숫자 검증
  extractNumbersFromContent,
  // 🟢 Phase 2: 주제-본문 검증
  validateThemeAndContent,
  // 🔵 Phase 3: 품질 점수 & 자동 재시도
  calculateTitleQualityScore,
  generateAndValidateTitle
};

