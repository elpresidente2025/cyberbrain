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

  // 유형 7: 정계 이슈·분석 (국가 정책·거시)
  ISSUE_ANALYSIS: {
    id: 'ISSUE_ANALYSIS',
    name: '정계 이슈·분석',
    when: '정계 이슈, 국가 정책 논평, 제도 개혁 분석 시',
    pattern: '이슈명 + "문제", "대안", "분석" (지역명 불필요)',
    naverTip: '정치인이 아닌 일반 검색자도 찾는 뉴스·정책 키워드',
    good: [
      { title: '지방 분권 개혁, 실제로 뭐가 달라질까?', chars: 19, analysis: '이슈명 + 질문형' },
      { title: '정치 자금 투명성, 어떻게 개선할까?', chars: 18, analysis: '이슈 + 질문형' },
      { title: '양극화 문제, 4대 대안 제시', chars: 14, analysis: '사회 이슈 + 대안 수' },
      { title: '교육 격차, 재정 투자로 뭐가 달라질까?', chars: 20, analysis: '사회 문제 + 접근법 + 질문' },
      { title: '선거 제도 개혁, 왜 시급한가?', chars: 15, analysis: '제도명 + 정당성 질문' }
    ],
    bad: [
      { title: '정치 현실에 대해 생각해 봅시다', problem: '구체적 이슈 부재', fix: '지방 분권 개혁, 뭐가 달라질까?' },
      { title: '문제가 많습니다', problem: '어떤 문제?', fix: '양극화 문제, 4대 대안 제시' },
      { title: '제도를 개선해야 합니다', problem: '어떤 제도? 어떻게?', fix: '선거 제도 개혁, 왜 시급한가?' }
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
  const hasLocalTerms = /동\s|구\s|시\s|읍\s|면\s|리\s/.test(contentPreview);
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
function buildTitlePrompt({ contentPreview, backgroundText, topic, fullName, keywords, userKeywords, category, subCategory, status }) {
  // 1. 콘텐츠 유형 자동 감지
  const detectedTypeId = detectContentType(contentPreview, category);
  const primaryType = TITLE_TYPES[detectedTypeId];

  // 2. 선거법 준수 지시문
  const electionCompliance = getElectionComplianceInstruction(status);

  // 3. 키워드 전략 지시문
  const keywordStrategy = getKeywordStrategyInstruction(userKeywords, keywords);

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
• 작성 후 반드시 글자 수 확인!
${electionCompliance}
${keywordStrategy}
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
${contentPreview.substring(0, 800)}

**배경정보**:
${backgroundText ? backgroundText.substring(0, 300) : '(없음)'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 최종 출력 규칙
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **25자 이내** (필수!)
2. **핵심 키워드 앞 8자 배치** (앞쪽 1/3 법칙)
3. 숫자/구체성 포함 (가능하면)
4. 부제목(-, :) 사용 금지
5. "~에 대한", "~관련" 불필요 표현 제거
6. 키워드 최대 3개 (2개 최적)

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
// 템플릿 주입용 간소화된 제목 가이드라인
// ============================================================================

/**
 * 템플릿에 주입할 제목 가이드라인 생성
 * WriterAgent가 본문과 함께 제목을 생성할 때 사용
 * @param {Array} userKeywords - 사용자 입력 키워드
 * @returns {string} 제목 가이드라인 텍스트
 */
function getTitleGuidelineForTemplate(userKeywords = []) {
  const primaryKw = userKeywords[0] || '';

  return `
╔═══════════════════════════════════════════════════════════════╗
║  🚨 제목 필수 조건 - 4가지 모두 충족해야 통과                  ║
╚═══════════════════════════════════════════════════════════════╝

【조건 1】 25자 이내
【조건 2】 숫자 1개 이상 포함 (3곳, 27위, 30%, 5년 등)
【조건 3】 키워드 "${primaryKw || '검색어'}"가 제목 앞 8자 안에 위치
【조건 4】 단일 문장 (콤마/슬래시/하이픈으로 나눈 부제목 금지)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 올바른 제목 공식: [키워드] + [숫자] + [구체적 내용]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ 통과 예시:
• "${primaryKw || '부산 대형병원'} 5곳 24시간 응급실 운영" (21자)
• "${primaryKw || '부산 대형병원'} 순위 27위서 10위권 도약" (20자)
• "청년 일자리 274명 지원금 85억 확보" (19자)

❌ 불통과 예시 (절대 이렇게 쓰지 마세요):
• "부산 대형병원, 순위 올리는 해법" ← 콤마 부제목, 숫자 없음
• "부산 대형병원 순위 진단과 전망" ← 숫자 없음, 추상적
• "의료 혁신을 위한 비전 제시" ← 숫자 없음, 추상적

⚠️ 4가지 조건 중 하나라도 위반하면 제목 실패!
`;
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
  getTitleGuidelineForTemplate
};
