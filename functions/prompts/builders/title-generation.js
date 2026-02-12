/**
 * functions/prompts/builders/title-generation.js
 * 네이버 블로그 제목 생성 프롬프트 (7가지 콘텐츠 구조 기반)
 *
 * 핵심 원칙:
 * - 35자 이내 (네이버 검색결과 최적화)
 * - 콘텐츠 구조(유형) 기반 분류 (도메인 X)
 * - AEO(AI 검색) 최적화
 * - 선거법 준수
 */

'use strict';

const { getElectionStage } = require('../guidelines/election-rules');

// ============================================================================
// 7가지 콘텐츠 구조 유형 정의
// ============================================================================

const TITLE_TYPES = {
  // 유형 0: 서사적 긴장감 (Narrative Hook) - 일상 소통 기본값
  VIRAL_HOOK: {
    id: 'VIRAL_HOOK',
    name: '서사적 긴장감 (Narrative Hook)',
    when: '독자의 호기심을 유발하되, 구체적 사실 기반의 서사적 긴장감으로 클릭을 유도할 때 (기본값)',
    pattern: '정보 격차(Information Gap) 구조: 구체적 팩트 + 미완결 서사 or 의외의 대비',
    naverTip: '제목이 "답"이 아니라 "질문"을 남길 때 CTR이 가장 높음',
    principle: '【좋은 제목의 판단 기준】\n'
      + '- 읽었을 때 "그래서 어떻게 됐지?" 또는 "왜?"라는 생각이 드는가?\n'
      + '- 정보 요소가 3개 이하인가? (과밀 = 읽히지 않음)\n'
      + '- 기법 하나만 자연스럽게 녹아 있는가? (기법 2개 이상 = 억지)\n'
      + '\n'
      + '【안티패턴: 이렇게 하면 안 된다】\n'
      + '- ❌ 아무 문장 끝에 "~의 선택은?" 붙이기 (형식만 미완결, 내용은 공허)\n'
      + '- ❌ 키워드 4개 이상 욱여넣기 (읽는 순간 피로)\n'
      + '- ❌ 예시 제목의 어미만 복사하기 (패턴 모방 ≠ 긴장감)',
    good: [
      { title: '부산 지방선거, 왜 이 남자가 뛰어들었나', chars: 20, analysis: '왜 질문형 — 미완결 질문' },
      { title: '부산 지방선거에 뛰어든 부두 노동자의 아들', chars: 21, analysis: '서사 아크 — 출신 서사' },
      { title: '부산 지방선거, 이재성은 왜 다른가', chars: 17, analysis: '간결 도발형 — 짧고 강렬' },
      { title: '부산 지방선거, 10만 청년이 떠난 도시의 반란', chars: 22, analysis: '수치+사건형 — 팩트 충격' },
      { title: '부산 지방선거, 원칙만으로 이길 수 있을까', chars: 20, analysis: '도발적 질문 — 가치 논쟁' }
    ],
    bad: [
      { title: '부산 지방선거, AI 전문가 이재성이 경제를 바꾼다', problem: '선언형 — 답을 다 알려줌', fix: '부산 지방선거, 왜 이 남자가 뛰어들었나' },
      { title: '이재성 부산 지방선거, AI 3대 강국?', problem: '키워드 나열 — 문장 아님', fix: '부산 지방선거, 이재성은 왜 다른가' },
      { title: '결국 터질 게 터졌습니다... 충격적 현실', problem: '낚시 자극 — 구체성 없음', fix: '부산 지방선거, 10만 청년이 떠난 도시의 반란' },
      { title: '부산 지방선거, 이재명 2호 이재성 원칙 내건 그의 선택은', problem: '기계적 모방 — 요소 과밀 + 형식적 꼬리', fix: '부산 지방선거, 이재성은 왜 다른가' }
    ]
  },

  // 유형 1: 구체적 데이터 기반 (성과 보고)
  DATA_BASED: {
    id: 'DATA_BASED',
    name: '구체적 데이터 기반',
    when: '정책 완료, 예산 확보, 사업 완공 등 구체적 성과가 있을 때',
    pattern: '숫자 2개 이상 + 핵심 키워드',
    naverTip: '"억 원", "명", "%" 등 구체적 단위가 있으면 AI 브리핑 인용률 ↑',
    good: [
      { title: '청년 일자리 274명 창출, 지원금 85억', chars: 18, analysis: '숫자 2개 + 키워드' },
      { title: '주택 234가구 리모델링 지원 완료', chars: 14, analysis: '수량 + 결과' },
      { title: '노후 산단 재생, 국비 120억 확보', chars: 16, analysis: '사업 + 금액' },
      { title: '신호등 15곳 개선, 사고율 40% 감소', chars: 17, analysis: '시설 + 효과' },
      { title: '상반기 민원 처리 3일 이내 달성', chars: 15, analysis: '기간 + 기준' }
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
      { title: '분당구 청년 주거, 월세 지원 얼마?', chars: 15, analysis: '지역 + 질문형' },
      { title: '성남 교통 체증, 어떻게 풀까?', chars: 13, analysis: '지역 + 질문' },
      { title: '어르신 일자리, 어떤 프로그램?', chars: 14, analysis: '대상 + 질문' },
      { title: '2025년 보육료, 지원 기준 바뀌었나?', chars: 18, analysis: '정책 + 질문' },
      { title: '주민 민원, 실제로 언제 해결돼요?', chars: 16, analysis: '문제 + 질문' }
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
      { title: '청년 기본소득 월 30만→50만원 확대', chars: 18, analysis: '정책 + 수치 대비' },
      { title: '교통 사고율, 전년 대비 40% 감소', chars: 16, analysis: '지표 + 비교' },
      { title: '쓰레기 비용 99억→65억, 절감 실현', chars: 17, analysis: '절감액' },
      { title: '주차장 부족, 12개월 만에 해결', chars: 14, analysis: '문제 + 기간' }
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
      { title: '분당 정자동 도시가스, 기금 70억 확보', chars: 19, analysis: '지역 + 정책 + 숫자' },
      { title: '수지 풍덕천동 학교 신설, 9월 개교', chars: 17, analysis: '지역 + 사업 + 일정' },
      { title: '성남 중원구 보육료, 월 15만원 추가', chars: 17, analysis: '행정구역 + 정책' },
      { title: '용인 기흥구 요양원, 신청 마감 1주', chars: 17, analysis: '지역 + 긴급성' },
      { title: '영통 광교동 교통, 6개월 35% 개선', chars: 17, analysis: '지역 + 효과' }
    ],
    bad: [
      { title: '우리 지역을 위해 노력합니다', problem: '지역명 없음', fix: '분당 정자동 도시가스 70억' },
      { title: '지역 정책 안내', problem: '어느 지역? 어떤 정책?', fix: '성남 중원구 보육료 월 15만원' },
      { title: '동네 주차장 문제', problem: '지역명·해결책 부재', fix: '분당 정자동 주차장 50면 추가' }
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
      { title: '청년 기본소득법 발의, 월 50만원', chars: 16, analysis: '법안 + 금액' },
      { title: '주차장 설치 의무 조례 개정 추진', chars: 15, analysis: '조례 + 동작' },
      { title: '전세 사기 피해자 보호법, 핵심 3가지', chars: 17, analysis: '법안 + 요약' },
      { title: '야간 상점 CCTV 의무화 조례안 통과', chars: 17, analysis: '정책 + 결과' },
      { title: '자영업자 신용대출, 금리 인하 추진', chars: 17, analysis: '대상 + 정책' }
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
      { title: '2025 상반기 의정 보고서, 5대 성과', chars: 18, analysis: '시간 + 형식 + 성과' },
      { title: '6월 민원 처리 리포트, 1,234건 해결', chars: 19, analysis: '월 + 수치' },
      { title: '2025 1분기 예산 집행 현황 공개', chars: 17, analysis: '기간 + 항목' },
      { title: '상반기 주민 의견 분석, 88건 반영', chars: 17, analysis: '기간 + 숫자' },
      { title: '월간 의정 뉴스레터 (7월호) 배포', chars: 17, analysis: '시간 + 형식' }
    ],
    bad: [
      { title: '보고서를 올립니다', problem: '시간 미명시', fix: '2025년 상반기 의정 보고서' },
      { title: '최근 활동을 정리했습니다', problem: '"최근" 애매', fix: '6월 민원 처리 리포트, 1,234건' },
      { title: '분기별 현황입니다', problem: '어느 분기?', fix: '2025년 1분기 예산 집행 현황' }
    ]
  },

  // 유형 7: 정계 이슈·분석 (국가 정책·거시) - 질문형 분석
  ISSUE_ANALYSIS: {
    id: 'ISSUE_ANALYSIS',
    name: '정계 이슈·분석',
    when: '정계 이슈, 국가 정책 분석, 제도 개혁 논의 시',
    pattern: '이슈명 + 질문형 또는 대안 제시',
    naverTip: '질문형(?)으로 끝내면 AI 브리핑 선택률 증가',
    good: [
      { title: '지방 분권 개혁, 실제로 뭐가 달라질까?', chars: 18, analysis: '이슈 + 질문형' },
      { title: '정치 자금 투명성, 어떻게 개선할까?', chars: 18, analysis: '이슈 + 질문형' },
      { title: '양극화 문제, 4대 대안 제시', chars: 14, analysis: '이슈 + 대안 수' },
      { title: '교육 격차, 재정 투자로 뭐가 달라질까?', chars: 19, analysis: '이슈 + 해결책 + 질문' },
      { title: '선거 제도 개혁, 왜 시급한가?', chars: 15, analysis: '이슈 + 당위성 질문' }
    ],
    bad: [
      { title: '정치 현실에 대해 생각해 봅시다', problem: '모호함, 구체성 없음', fix: '지방 분권 개혁, 실제로 뭐가 달라질까?' },
      { title: '문제가 많습니다', problem: '어떤 문제?', fix: '양극화 문제, 4대 대안 제시' },
      { title: '제도를 개선해야 합니다', problem: '어떤 제도?', fix: '선거 제도 개혁, 왜 시급한가?' }
    ]
  },

  // 유형 8: 논평/화자 관점 (다른 정치인 평가)
  COMMENTARY: {
    id: 'COMMENTARY',
    name: '논평/화자 관점',
    when: '다른 정치인 논평, 인물 평가, 정치적 입장 표명 시',
    pattern: '화자 + 관점 표현 + 대상/이슈',
    naverTip: '화자 이름을 앞에 배치하면 개인 브랜딩 + SEO 효과',
    good: [
      { title: '박형준 역부족? 이재성이 본 부산 경제', chars: 19, analysis: '대상 + 질문 + 화자 관점' },
      { title: '조경태 칭찬한 이재성, 尹 사형 논평', chars: 18, analysis: '관계 + 화자 + 이슈' },
      { title: '이재성 "박형준, 경제 성적 낙제점"', chars: 18, analysis: '화자 + 인용문' },
      { title: '이재성이 본 조경태의 소신 있는 발언', chars: 18, analysis: '화자 관점 + 대상 + 평가' },
      { title: '박형준 침묵 vs 조경태 소신, 이재성 평가', chars: 21, analysis: '대비 구조 + 화자' }
    ],
    bad: [
      { title: '윤석열 사형 구형 발언, 조경태 의원 칭찬', problem: '화자 누락', fix: '조경태 칭찬한 이재성, 尹 사형 논평' },
      { title: '정치인 발언에 대한 논평', problem: '누가? 무슨 발언?', fix: '이재성 "박형준, 경제 성적 낙제점"' },
      { title: '박형준 시장 경제 발전 역부족? 이재성, 부산 0.7% 성장률 지적', problem: '너무 김 (36자), 정보 과다', fix: '박형준 역부족? 이재성이 본 부산 경제' }
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
  // 🆕 논평/화자 관점 감지 (다른 정치인 평가)
  const hasCommentaryTerms = /칭찬|질타|비판|논평|평가|소신|침묵|역부족|낙제|심판/.test(text);
  const hasPoliticianNames = /박형준|조경태|윤석열|이재명|한동훈/.test(contentPreview);

  // 우선순위 기반 유형 결정
  if (hasTimeTerms && (text.includes('보고') || text.includes('리포트') || text.includes('현황'))) {
    return 'TIME_BASED';
  }
  if (hasLegalTerms) {
    return 'EXPERT_KNOWLEDGE';
  }
  // 🆕 논평/화자 관점 우선 감지 (다른 정치인 이름 + 평가 표현)
  if (hasCommentaryTerms && hasPoliticianNames) {
    return 'COMMENTARY';
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
    'daily-communication': 'VIRAL_HOOK',
    'bipartisan-cooperation': 'COMMENTARY'  // 🆕 초당적 협력 → 논평 유형
  };

  return categoryMapping[category] || 'VIRAL_HOOK';
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

  const result = {
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

  console.log('[DEBUG] extractNumbersFromContent result:', result?.numbers ? result.numbers.length : 'undefined keywords');
  return result;
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
    range: '18-35자',
    weight: '60%',
    use: '행동 유도, 긴급성, 신뢰성 신호',
    example: '"신청 마감 3일 전", "5대 성과"'
  }
};

/**
 * 두 키워드가 유사한지 판별 (공통 어절이 있는지)
 * 예: "서면 영광도서", "부산 영광도서" → 공통 "영광도서" → 유사
 * 예: "계양산 러브버그 방역", "계양구청" → 공통 없음 → 독립
 */
function areKeywordsSimilar(kw1, kw2) {
  if (!kw1 || !kw2) return false;
  const words1 = kw1.split(/\s+/);
  const words2 = kw2.split(/\s+/);
  return words1.some(w => words2.includes(w) && w.length >= 2);
}

/**
 * 키워드 삽입 전략 지시문 생성
 */
function getKeywordStrategyInstruction(userKeywords, keywords) {
  const hasUserKeywords = userKeywords && userKeywords.length > 0;
  const primaryKw = hasUserKeywords ? userKeywords[0] : (keywords?.[0] || '');
  const secondaryKw = hasUserKeywords
    ? (userKeywords[1] || keywords?.[0] || '')
    : (keywords?.[1] || '');

  // 두 키워드 간 유사/독립 판별
  const hasTwoKeywords = primaryKw && secondaryKw && primaryKw !== secondaryKw;
  const similar = hasTwoKeywords && areKeywordsSimilar(primaryKw, secondaryKw);

  let titleKeywordRule = '';
  if (hasTwoKeywords) {
    if (similar) {
      // 유사 키워드: 제목은 1번 키워드로 시작, 2번 키워드는 어절 해체하여 배치
      const kw2Words = secondaryKw.split(/\s+/);
      const kw1Words = primaryKw.split(/\s+/);
      const uniqueWords = kw2Words.filter(w => !kw1Words.includes(w));
      titleKeywordRule = `
📌 **제목 키워드 배치 규칙 (유사 키워드)**
두 검색어("${primaryKw}", "${secondaryKw}")가 공통 어절을 공유하므로:
• 제목은 반드시 "${primaryKw}"로 시작
• "${secondaryKw}"는 어절 단위로 해체하여 자연스럽게 배치 (${uniqueWords.length > 0 ? `"${uniqueWords.join('", "')}"를 제목 뒤쪽에 녹여넣기` : '공통 어절로 자동 충족'})
• 예시: "${primaryKw}, <보고있나, ${uniqueWords[0] || secondaryKw.split(/\s+/)[0]}> 출판기념회에 초대합니다"
`;
    } else {
      // 독립 키워드: 제목은 1번 키워드로 시작, 2번 키워드는 뒤에 배치
      titleKeywordRule = `
📌 **제목 키워드 배치 규칙 (독립 키워드)**
두 검색어("${primaryKw}", "${secondaryKw}")가 독립적이므로:
• 제목은 반드시 "${primaryKw}"로 시작
• "${secondaryKw}"는 제목 뒤쪽에 자연스럽게 배치
• 예시: "${primaryKw}, 확장 공사에 ${secondaryKw} 적극 구제 촉구"
`;
    }
  }

  return `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔑 SEO 키워드 삽입 전략
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📍 **앞쪽 1/3 법칙** (가장 중요!)
네이버는 제목 앞 8-10자를 가장 중요하게 평가합니다.
→ 핵심 키워드는 반드시 제목 시작 부분에!

❌ "우리 지역 청년들을 위한 청년 기본소득"
✅ "청년 기본소득, 분당구 월 50만원 지원"
${titleKeywordRule}
📊 **키워드 밀도: 최소 1개, 최대 3개**
• 최적: 2개 (가장 자연스럽고 효과적)
• 4개 이상: 스팸으로 판단, CTR 감소

📍 **위치별 배치 전략**
┌─────────────────────────────────────────────┐
│ [0-8자]     │ [9-20자]      │ [21-35자]   │
│ 지역/정책명  │ 수치/LSI     │ 행동/긴급성  │
│ 가중치 100% │ 가중치 80%   │ 가중치 60%  │
└─────────────────────────────────────────────┘

${primaryKw ? `**1순위 키워드**: "${primaryKw}" → 제목 앞 8자 이내 배치` : ''}
${secondaryKw ? `**2순위 키워드**: "${secondaryKw}" → ${similar ? '어절 해체하여 자연 배치' : '제목 뒤쪽 배치'}` : ''}

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
  if (!primaryType) {
    console.warn(`[TitleGen] detectedTypeId '${detectedTypeId}' not found, falling back to DATA_BASED`);
    detectedTypeId = 'DATA_BASED';
  }

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
  const goodExamples = (TITLE_TYPES[detectedTypeId] || TITLE_TYPES.DATA_BASED).good
    .map((ex, i) => `${i + 1}. "${ex.title}" (${ex.chars}자)\n   → ${ex.analysis}`)
    .join('\n');

  const badExamples = (TITLE_TYPES[detectedTypeId] || TITLE_TYPES.DATA_BASED).bad
    .map((ex, i) => `${i + 1}. ❌ "${ex.title}"\n   문제: ${ex.problem}\n   ✅ 수정: "${ex.fix}"`)
    .join('\n\n');

  // 5. 키워드 처리 (표시용)
  const primaryKeywords = userKeywords && userKeywords.length > 0
    ? userKeywords.slice(0, 3).join(', ')
    : '';
  const secondaryKeywords = keywords
    ? keywords.filter(k => !userKeywords?.includes(k)).slice(0, 3).join(', ')
    : '';

  return `<title_generation_prompt>

<role>네이버 블로그 제목 전문가</role>

<rules priority="critical">
  <rule id="length_max">🚨 35자 이내 (네이버 검색결과 잘림 방지) - 절대 초과 금지!</rule>
  <rule id="length_optimal">18-30자 권장 (클릭률 최고 구간)</rule>
  <rule id="no_ellipsis">말줄임표("...") 절대 금지</rule>
  <rule id="keyword_position">핵심 키워드를 앞 8자에 배치. 키워드 직후에 반드시 구분자(쉼표, 물음표, 조사+쉼표)를 넣어라. ✅ "부산 지방선거, 왜~" ✅ "부산 지방선거에 뛰어든~" ❌ "부산 지방선거 이재성" (네이버가 하나의 키워드로 인식)</rule>
  <rule id="no_greeting">인사말/서술형 제목 절대 금지</rule>
  <rule id="info_density">제목에 담는 정보 요소는 최대 3개. SEO 키워드는 1개로 카운트. "부산 지방선거, 왜 이 남자가 뛰어들었나" = 2개 OK. "부산 지방선거 이재명 2호 이재성 원칙 선택" = 5개 NG.</rule>
  <rule id="narrative_tension">읽은 뒤 "그래서?" "왜?"가 떠오르는 제목이 좋다. 기법을 억지로 넣지 말고 자연스러운 호기심을 만들어라. 선언형 종결("~바꾼다") 금지.</rule>
</rules>

<forbidden_patterns priority="critical">
  <pattern type="greeting">존경하는, 안녕하십니까, 안녕하세요, 여러분</pattern>
  <pattern type="ending">~입니다, ~습니다, ~습니까, ~니다</pattern>
  <pattern type="content_start">본문 첫 문장을 제목으로 사용</pattern>
  <pattern type="too_long">35자 초과 제목</pattern>
  <example bad="true">존경하는 부산 시민 여러분, 안녕하십니까</example>
  <example bad="true">박형준 시장 경제 발전 역부족? 이재성, 부산 0.7% 성장률 지적하며 AI 강국 대안 제시 (40자, 정보 과다)</example>
</forbidden_patterns>

${electionCompliance}
${keywordStrategy}
${numberValidation.instruction}
${regionScopeInstruction}

<content_type detected="${primaryType.id}">
  <name>${primaryType.name}</name>
  <when>${primaryType.when}</when>
  <pattern>${primaryType.pattern}</pattern>
  <naver_tip>${primaryType.naverTip}</naver_tip>
</content_type>

<examples type="good">
${goodExamples}
</examples>

<examples type="bad">
${badExamples}
</examples>

<input>
  <topic>${topic}</topic>
  <author>${fullName}</author>
  <content_preview>${String(contentPreview || '').substring(0, 800)}</content_preview>
  <background>${backgroundText ? backgroundText.substring(0, 300) : '(없음)'}</background>
</input>

<topic_priority priority="highest">
  <instruction>🚨 제목의 방향은 반드시 주제(topic)를 따라야 합니다. 본문 내용이 아무리 많아도 topic이 절대 우선.</instruction>
  <rules>
    <rule>주제가 "후원"이면 제목도 후원/응원/함께에 관한 것이어야 함 — 경제/AI/정책으로 빠지면 안 됨</rule>
    <rule>주제가 "원칙"이면 제목도 원칙/품격에 관한 것이어야 함</rule>
    <rule>본문(content_preview)은 배경 정보일 뿐, 제목 방향을 결정하지 않음</rule>
    <rule>주제 키워드를 전부 넣을 필요는 없지만, 주제의 핵심 행동/요청은 반드시 반영</rule>
  </rules>
  <example>
    <topic>원칙과 품격, 부산시장 예비후보 이재성 후원</topic>
    <good>부산 지방선거, 이재성에게 힘을 보태는 방법</good>
    <bad reason="주제 이탈 — 후원이 주제인데 경제로 빠짐">부산 지방선거, 경제 0.7% 늪에서 이재성이 꺼낸 비책은</bad>
  </example>
</topic_priority>

<output_rules>
  <rule>🚨 35자 이내 필수 (초과 시 검색결과 잘림)</rule>
  <rule>18-30자 권장 (클릭률 최고)</rule>
  <rule>말줄임표 절대 금지</rule>
  <rule>핵심 키워드 앞 8자 배치</rule>
  <rule>본문에 실제 등장하는 숫자만 사용</rule>
  <rule>정보 요소 3개 이하 (과다 정보 = 긴 제목)</rule>
  <rule>"~에 대한", "~관련" 불필요 표현 제거</rule>
</output_rules>

<output_format>순수한 제목 텍스트만. 따옴표, 설명, 글자수 표시 없이.</output_format>

</title_generation_prompt>

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
  const isCommentaryCategory = ['current-affairs', 'bipartisan-cooperation'].includes(category);

  return `
╔═══════════════════════════════════════════════════════════════╗
║  🚨 제목 품질 조건 - 네이버 블로그 최적화                          ║
╚═══════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 【필수】 위반 시 재생성 (MUST)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **35자 이내** (네이버 검색결과 35자 초과 시 잘림!)
2. 숫자는 본문에 실제 등장한 것만 사용 (날조 금지)
3. 주제 핵심 요소 반영 필수
4. 말줄임표("...") 절대 금지

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟡 【권장】 품질 향상 (SHOULD)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. **18-30자** (클릭률 최고 구간)
2. ${primaryKw ? `키워드 "${primaryKw}"를 제목 앞 8자 안에 배치` : '핵심 키워드를 제목 앞 8자 안에 배치'}
3. 구체적 숫자 포함 (274명, 85억 등)
${isCommentaryCategory ? `4. 화자 연결 패턴: "${authorName || '이재성'}이 본", "칭찬한 ${authorName || '이재성'}"` : ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 【선택】 서사적 긴장감 (COULD)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
읽은 뒤 "그래서?" "왜?"가 떠오르는 제목이 좋다.
기법을 억지로 넣지 말고 자연스러운 호기심을 만들 것.
선언형("~바꾼다", "~이끈다") 금지. 정보 요소 3개 이하.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 좋은 제목 예시 (18-30자)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ "부산 지방선거, 왜 이 남자가 뛰어들었나" (20자)
✅ "부산 지방선거에 뛰어든 부두 노동자의 아들" (21자)
✅ "부산 지방선거, ${authorName || '이재성'}은 왜 다른가" (17자)
✅ "부산 지방선거, ${authorName || '이재성'}이 경제에 거는 한 수" (22자)
✅ "부산 청년이 떠나는 도시, ${authorName || '이재성'}의 답은" (19자)

❌ 나쁜 제목 예시:
• "부산 지방선거, AI 전문가 ${authorName || '이재성'}이 경제를 바꾼다" (선언형 — 답을 다 알려줌)
• "${authorName || '이재성'} 부산 지방선거, AI 3대 강국?" (키워드 나열 — 문장 아님)
• "결국 터졌습니다... 충격적 현실" (낚시 자극 — 구체성 없음)
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
 * 1. 길이 적합성 (18-35자)
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
  try {
    const { topic = '', content = '', userKeywords = [], authorName = '' } = params;

    if (!title) {
      return {
        score: 0,
        breakdown: {},
        passed: false,
        suggestions: ['제목이 없습니다']
      };
    }

    // 🚨 [CRITICAL] 본문 패턴 검증 - 본문처럼 보이는 제목은 즉시 0점
    const looksLikeContent =
      title.includes('여러분') ||           // 호칭 (본문 첫 문장)
      title.includes('<') ||                 // HTML 태그
      title.endsWith('입니다') ||            // 서술형 종결
      title.endsWith('습니다') ||            // 서술형 종결
      title.endsWith('습니까') ||            // 의문형 종결 (인사말)
      title.endsWith('니다') ||              // 서술형 종결
      title.length > 50;                     // 너무 긴 제목

    if (looksLikeContent) {
      const reason = title.includes('여러분') ? '호칭("여러분") 포함' :
        title.includes('<') ? 'HTML 태그 포함' :
          title.length > 50 ? '50자 초과' : '서술형 종결어미';
      return {
        score: 0,
        breakdown: { contentPattern: { score: 0, max: 100, status: '실패', reason } },
        passed: false,
        suggestions: [`제목이 본문처럼 보입니다 (${reason}). 검색어 중심의 간결한 제목으로 다시 작성하세요.`]
      };
    }

    // 🚨 [HARD FAIL] 말줄임표 금지 - 즉시 실패
    if (title.includes('...') || title.endsWith('..')) {
      return {
        score: 0,
        breakdown: { ellipsis: { score: 0, max: 100, status: '실패', reason: '말줄임표 포함' } },
        passed: false,
        suggestions: ['말줄임표("...") 사용 금지. 내용을 자르지 말고 완결된 제목을 작성하세요.']
      };
    }

    const breakdown = {};
    const suggestions = [];
    const titleLength = title.length;

    // 🚨 [HARD FAIL] 글자수 범위 (12자 미만 또는 35자 초과 시 실패)
    // 네이버 검색결과 35자 초과 시 잘림
    if (titleLength < 12 || titleLength > 35) {
      return {
        score: 0,
        breakdown: { length: { score: 0, max: 100, status: '실패', reason: `${titleLength}자 (18-35자 필요)` } },
        passed: false,
        suggestions: [`제목이 ${titleLength}자입니다. 18-35자 범위로 작성하세요. (35자 초과 시 검색결과 잘림)`]
      };
    }

    // 1. 길이 점수 (최대 20점) - 기준: 18-30자 최적, 31-35자 허용
    if (titleLength >= 18 && titleLength <= 30) {
      breakdown.length = { score: 20, max: 20, status: '최적' };
    } else if (titleLength >= 12 && titleLength < 18) {
      breakdown.length = { score: 12, max: 20, status: '짧음' };
      suggestions.push(`제목이 ${titleLength}자입니다. 18자 이상 권장.`);
    } else if (titleLength > 30 && titleLength <= 35) {
      breakdown.length = { score: 12, max: 20, status: '경계' };
      suggestions.push(`제목이 ${titleLength}자입니다. 30자 이하가 클릭률 최고.`);
    } else {
      breakdown.length = { score: 0, max: 20, status: '부적정' };
      suggestions.push(`제목이 ${titleLength}자입니다. 18-30자 범위로 작성하세요.`);
    }

    // 2. 키워드 위치 점수 (최대 20점) - 복수 키워드 지원, 앞 10자 기준
    if (userKeywords && userKeywords.length > 0) {
      // 모든 키워드의 위치 확인
      const keywordPositions = userKeywords.map(kw => ({
        keyword: kw,
        index: title.indexOf(kw),
        inFront10: title.indexOf(kw) >= 0 && title.indexOf(kw) <= 10
      }));

      const anyInFront10 = keywordPositions.some(kp => kp.inFront10);
      const anyInTitle = keywordPositions.some(kp => kp.index >= 0);
      const frontKeyword = keywordPositions.find(kp => kp.inFront10)?.keyword || '';
      const anyKeyword = keywordPositions.find(kp => kp.index >= 0)?.keyword || '';

      // 키워드 뒤 구분자 검증: 쉼표, 물음표, 조사 등으로 분리되어야 함
      const delimiters = new Set([',', '?', '!', '.', '에', '의', '을', '를', '은', '는', '이', '가', ':']);
      let kwDelimiterOk = true;
      for (const kp of keywordPositions) {
        if (kp.index >= 0) {
          const endPos = kp.index + kp.keyword.length;
          if (endPos < title.length) {
            const nextChar = title[endPos];
            if (!delimiters.has(nextChar) && nextChar !== ' ') {
              kwDelimiterOk = false;
            } else if (nextChar === ' ' && endPos + 1 < title.length) {
              const afterSpace = title.charCodeAt(endPos + 1);
              if (afterSpace >= 0xAC00 && afterSpace <= 0xD7A3) kwDelimiterOk = false;
            }
          }
        }
      }

      // 듀얼 키워드 배치 검증: 1번 키워드가 제목 시작에 있는지
      let dualKwBonus = 0;
      let dualKwPenalty = 0;
      if (userKeywords.length >= 2) {
        const kw1 = userKeywords[0];
        const kw1Idx = title.indexOf(kw1);
        const kw1StartsTitle = kw1Idx >= 0 && kw1Idx <= 2; // 제목 맨 앞(0~2자 내)
        if (kw1StartsTitle) {
          dualKwBonus = 3; // 1번 키워드가 제목 시작 → 보너스
        } else if (kw1Idx >= 0) {
          dualKwPenalty = 0; // 포함은 되어 있으나 앞쪽 아님 → 감점 없음 (이미 위치 점수로 반영)
        } else {
          dualKwPenalty = 5; // 1번 키워드 미포함 → 감점
          suggestions.push(`1순위 키워드 "${kw1}"가 제목에 없습니다. 제목 시작 부분에 배치하세요.`);
        }

        // 2번 키워드: 유사 키워드면 어절 해체 충족 여부, 독립 키워드면 포함 여부
        const kw2 = userKeywords[1];
        const similar = areKeywordsSimilar(kw1, kw2);
        if (similar) {
          // 유사 키워드: 2번 키워드의 고유 어절이 제목에 있으면 OK
          const kw2Words = kw2.split(/\s+/);
          const kw1Words = kw1.split(/\s+/);
          const uniqueWords = kw2Words.filter(w => !kw1Words.includes(w) && w.length >= 2);
          const hasUniqueWord = uniqueWords.length === 0 || uniqueWords.some(w => title.includes(w));
          if (!hasUniqueWord) {
            dualKwPenalty += 3;
            suggestions.push(`2순위 키워드 "${kw2}"의 고유 어절(${uniqueWords.join(', ')})이 제목에 없습니다.`);
          }
        } else {
          // 독립 키워드: 제목에 포함되어야 함
          if (!title.includes(kw2)) {
            dualKwPenalty += 3;
            suggestions.push(`2순위 키워드 "${kw2}"가 제목에 포함되지 않았습니다.`);
          }
        }
      }

      if (anyInFront10) {
        const score = Math.min(20, Math.max(0, (kwDelimiterOk ? 20 : 15) + dualKwBonus - dualKwPenalty));
        const status = kwDelimiterOk ? '최적' : '최적(구분자 부족)';
        breakdown.keywordPosition = { score, max: 20, status, keyword: frontKeyword };
        if (!kwDelimiterOk) {
          suggestions.push(`키워드 "${frontKeyword}" 뒤에 쉼표나 조사를 넣어 다음 단어와 분리하세요. (예: "부산 지방선거, ~")`);
        }
      } else if (anyInTitle) {
        const score = Math.max(0, 12 - dualKwPenalty);
        breakdown.keywordPosition = { score, max: 20, status: '포함됨', keyword: anyKeyword };
        suggestions.push(`키워드 "${anyKeyword}"를 제목 앞쪽(10자 내)으로 이동하면 SEO 효과 증가.`);
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
      // Safety guard for contentNumbers
      const safeContentNumbers = contentNumbers && contentNumbers.numbers ? contentNumbers.numbers : [];

      const titleNumbers = title.match(/\d+(?:억|만원|%|명|건|가구|곳)?/g) || [];

      const allValid = titleNumbers.every(num =>
        safeContentNumbers.some(cn => cn.includes(num) || num.includes(cn.replace(/[^\d]/g, '')))
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
        // 🆕 화자 연결 패턴 보너스 체크 ("이 본", "가 본", "의 평가", "칭찬한", "질타한" 등)
        const speakerPatterns = [
          new RegExp(`${authorName}이 본`),
          new RegExp(`${authorName}가 본`),
          new RegExp(`${authorName}의 평가`),
          new RegExp(`${authorName}의 시각`),
          new RegExp(`칭찬한 ${authorName}`),
          new RegExp(`질타한 ${authorName}`),
          new RegExp(`${authorName} ['"\`]`)  // 인용문 패턴
        ];
        const hasSpeakerPattern = speakerPatterns.some(p => p.test(title));

        if (hasSpeakerPattern) {
          breakdown.authorIncluded = { score: 10, max: 10, status: '패턴 적용', pattern: true };
        } else {
          breakdown.authorIncluded = { score: 6, max: 10, status: '단순 포함' };
          suggestions.push(`"${authorName}이 본", "칭찬한 ${authorName}" 등 관계형 표현 권장.`);
        }
      } else {
        breakdown.authorIncluded = { score: 0, max: 10, status: '미포함' };
        suggestions.push(`화자 "${authorName}"를 제목에 포함하면 브랜딩에 도움됩니다.`);
      }
    } else {
      breakdown.authorIncluded = { score: 5, max: 10, status: '해당없음' };
    }

    // 6. 임팩트 요소 점수 (최대 10점) - 서사적 긴장감 패턴 포함
    let impactScore = 0;
    const impactFeatures = [];

    if (title.includes('?') || title.endsWith('나') || title.endsWith('까')) { impactScore += 3; impactFeatures.push('질문/미완결'); }
    if (/'.*'/.test(title) || /".*"/.test(title)) { impactScore += 3; impactFeatures.push('인용문'); }
    if (/vs|\bvs\b|→|대비/.test(title)) { impactScore += 2; impactFeatures.push('대비구조'); }
    if (/이 본|가 본/.test(title)) { impactScore += 2; impactFeatures.push('관점표현'); }
    // 서사적 긴장감 패턴
    if (/(은|는|카드는|답은|선택|한 수|이유)$/.test(title)) { impactScore += 2; impactFeatures.push('미완결서사'); }
    if (/에서.*까지/.test(title)) { impactScore += 2; impactFeatures.push('서사아크'); }
    if (/왜\s|어떻게\s/.test(title)) { impactScore += 2; impactFeatures.push('원인질문'); }
    // 정보 과밀 패널티: 실질 요소(2글자 이상)가 7개 이상이면 감점
    const substantiveElements = (title.match(/[가-힣A-Za-z0-9]{2,}/g) || []);
    if (substantiveElements.length >= 7) { impactScore -= 2; impactFeatures.push('정보과밀(-2)'); }

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
  } catch (error) {
    console.error('❌ [TitleGen] calculateTitleQualityScore CRASH:', error);
    // Return a safe fallback to prevent TitleAgent from failing completely
    return {
      score: 50, // Fail by default but don't crash the agent
      breakdown: { error: { score: 0, status: 'Crash' } },
      passed: false,
      suggestions: ['제목 품질 검사 중 오류 발생']
    };
  }
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
    try {
      if (attempt === 1 || history.length === 0) {
        prompt = buildTitlePrompt(params);
      } else {
        // 이전 시도 피드백 추가
        const lastAttempt = history[history.length - 1];

        // Safety check just in case
        if (!lastAttempt) {
          prompt = buildTitlePrompt(params);
        } else {
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
      }
    } catch (e) {
      console.error('[CRITICAL] buildTitlePrompt THREW:', e);
      throw e;
    }

    // 2. 제목 생성 (LLM 호출)
    let generatedTitle;
    try {
      console.log(`[DEBUG] Attempt ${attempt}: Calling generateFn...`);
      generatedTitle = await generateFn(prompt);
      generatedTitle = (generatedTitle || '').trim().replace(/^["']|["']$/g, '');
      console.log(`[DEBUG] Generated title: "${generatedTitle}"`);
    } catch (error) {
      console.error(`[TitleGen] 생성 오류 (${attempt}/${maxAttempts}):`, error.message);
      continue;
    }

    if (!generatedTitle) {
      console.log('[DEBUG] Generated title is empty, continuing...');
      continue;
    }

    // 3. 품질 점수 계산
    console.log('[DEBUG] Calling calculateTitleQualityScore...');
    let scoreResult;
    try {
      scoreResult = calculateTitleQualityScore(generatedTitle, {
        topic: params.topic,
        content: params.contentPreview,
        userKeywords: params.userKeywords,
        authorName: params.fullName
      });
      console.log('[DEBUG] calculateTitleQualityScore returned score:', scoreResult?.score);
    } catch (e) {
      console.error('[CRITICAL] calculateTitleQualityScore THREW:', e);
      throw e; // Re-throw to see if it's caught upstream
    }

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
        try {
          console.log('[DEBUG] Calling onProgress passed...');
          onProgress({ attempt, maxAttempts, status: 'passed', score: scoreResult.score });
        } catch (e) {
          console.error('[CRITICAL] onProgress passed callback FAILED:', e);
        }
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

  // [수정] 점수가 너무 낮으면(인사말 등) 아예 실패 처리 (빈 제목 반환)
  // 또는 35자 초과면 강제 실패
  if (bestScore < 30 || (bestTitle && bestTitle.length > 35)) {
    const reason = bestTitle && bestTitle.length > 35
      ? `35자 초과 (${bestTitle.length}자)`
      : `점수 미달 (${bestScore}점)`;
    console.error(`🚨 [TitleGen] ${reason} - 저품질 제목 폐기: "${bestTitle}"`);
    bestTitle = ''; // 빈 문자열 반환 -> Orchestrator에서 제목 없음 처리됨
  }

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
  areKeywordsSimilar,
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

