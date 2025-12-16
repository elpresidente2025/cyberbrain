// functions/templates/guidelines/legal.js - 법적 사항 및 정책 관리

'use strict';

const crypto = require('crypto');
const NodeCache = require('node-cache');
const { getApps, initializeApp } = require('firebase-admin/app');
const { getFirestore } = require('firebase-admin/firestore');

// Admin SDK init (이미 초기화되어 있으면 스킵)
if (getApps().length === 0) initializeApp();

// ============================================================================
// 정책 관리 시스템
// ============================================================================

const cache = new NodeCache({ stdTTL: 600, checkperiod: 120 }); // 10분

const FALLBACK_POLICY = {
  version: 0,
  body: `[금지] 비방/모욕, 허위·추측, 차별(지역·성별·종교), 선거 지지·반대, 불법 선거정보
[원칙] 사실기반·정책중심·미래지향 톤, 출처 명시, 불확실시 의견표현`,
  bannedKeywords: ['빨갱이','사기꾼','착복','위조','기피','뇌물','추행','전과자','도피','체납'],
  patterns: [],
  hash: 'fallback'
};

async function loadPolicyFromDB() {
  const cached = cache.get('LEGAL_POLICY');
  if (cached) return cached;

  const db = getFirestore();
  const snap = await db.doc('policies/LEGAL_GUARDRAIL').get();
  if (!snap.exists) throw new Error('POLICY_NOT_FOUND');

  const data = snap.data() || {};
  if (typeof data.body !== 'string' || typeof data.version !== 'number') {
    throw new Error('POLICY_INVALID');
  }

  const hash = crypto.createHash('sha256').update(data.body).digest('hex').slice(0, 12);

  const policy = {
    version: data.version,
    body: data.body,
    bannedKeywords: Array.isArray(data.bannedKeywords) ? data.bannedKeywords : FALLBACK_POLICY.bannedKeywords,
    patterns: Array.isArray(data.patterns) ? data.patterns : FALLBACK_POLICY.patterns,
    hash
  };

  cache.set('LEGAL_POLICY', policy);
  return policy;
}

const ENFORCE = (process.env.POLICY_ENFORCE || 'fail_closed').toLowerCase();

/** 정책을 안전하게 가져오기: 실패 시 fail-closed(기본) 또는 fallback */
async function getPolicySafe() {
  try {
    return await loadPolicyFromDB();
  } catch (e) {
    if (ENFORCE === 'fail_closed') throw e;
    return FALLBACK_POLICY;
  }
}

// ============================================================================
// 법적 가이드라인
// ============================================================================

const LEGAL_GUIDELINES = {
  // 절대 금지 사항
  prohibited: {
    defamation: {
      items: ['비방', '모욕', '인신공격', '명예훼손', '인격 모독'],
      description: '개인이나 단체에 대한 부정적 인격 공격'
    },
    falseInfo: {
      items: ['허위사실', '추측성 발언', '확인되지 않은 정보', '루머', '카더라'],
      description: '사실 확인이 되지 않은 정보나 추측에 기반한 내용'
    },
    discrimination: {
      items: ['지역차별', '성별차별', '종교차별', '연령차별', '계층차별'],
      description: '특정 집단에 대한 차별적 표현이나 편견'
    },
    election: {
      items: ['선거 지지', '선거 반대', '투표 독려', '후보 비교', '당선 예측'],
      description: '선거와 관련된 직접적인 지지나 반대 표현'
    },
    illegal: {
      items: ['불법 선거정보', '금품 제공', '특혜 약속', '이권 개입'],
      description: '법적으로 문제가 될 수 있는 내용'
    }
  },

  // 필수 준수 사항
  required: {
    factBased: {
      rule: '모든 주장은 사실에 근거해야 함',
      application: '통계, 정책, 제도 등 객관적 근거 제시'
    },
    sourceRequired: {
      rule: '주요 통계와 정보에 출처 명시 필수',
      format: '[출처: 기관명/자료명] 형식으로 문장 끝에 표기'
    },
    opinionClear: {
      rule: '의견과 사실을 명확히 구분',
      expressions: ['"제 생각에는"', '"개인적으로는"', '"저는 ~라고 봅니다"']
    },
    policyFocused: {
      rule: '정책 중심의 건설적 내용',
      approach: '문제 제기 시 반드시 대안 제시'
    },
    futureOriented: {
      rule: '미래 지향적이고 긍정적 톤 유지',
      avoid: '과거 매몰, 부정적 단정, 비관적 전망'
    }
  },

  // 안전한 표현 가이드 (리스크 회피)
  safeExpressions: {
    criticism: {
      safe: ['"~한 측면에서 아쉬움이 있지만"', '"~한 부분은 개선이 필요하다고 생각합니다"'],
      risky: ['"~는 잘못되었다"', '"~는 실패작이다"']
    },
    suggestion: {
      safe: ['"보다 나은 방향은 ~입니다"', '"~한 방안을 제안드립니다"'],
      risky: ['"반드시 ~해야 한다"', '"~하지 않으면 큰일난다"']
    },
    uncertainty: {
      safe: ['"현재 확인 중인 사안으로"', '"추가 검토가 필요한 부분입니다"'],
      risky: ['"확실히"', '"틀림없이"', '"분명히"']
    },
    opinion: {
      safe: ['"제 생각에는"', '"개인적 견해로는"', '"저는 ~라고 봅니다"'],
      risky: ['"당연히"', '"누구나 알고 있듯이"', '"말할 필요도 없이"']
    }
  },

  // 위험한 표현 패턴 (회피 필수)
  dangerousPatterns: {
    absolute: {
      expressions: ['확실히', '틀림없이', '반드시', '절대', '100%'],
      why: '단정적 표현은 법적 리스크 높음'
    },
    extreme: {
      expressions: ['모든', '전부', '절대', '완전히', '아예'],
      why: '극단적 표현은 반박 여지 제공'
    },
    speculative: {
      expressions: ['들었다', '카더라', '소문에', '~것 같다', '추정하건대'],
      why: '추측성 표현은 허위사실 유포 위험'
    },
    inflammatory: {
      expressions: ['당연히', '말도 안 되는', '어이없는', '한심한'],
      why: '선동적 표현은 품위 손상'
    }
  },

  // 검토 체크리스트
  reviewChecklist: [
    '개인/단체 비방 여부 확인',
    '허위사실이나 추측 내용 제거',
    '차별적 표현 점검',
    '선거 관련 직접 언급 회피',
    '출처 명시 완료',
    '의견과 사실 구분 명확화',
    '건설적 대안 제시 여부',
    '미래 지향적 톤 유지'
  ]
};

// ============================================================================
// 정책 위반 탐지 시스템
// ============================================================================

const VIOLATION_DETECTOR = {
  // 위험 키워드 감지
  checkBannedKeywords: (text) => {
    const violations = [];
    FALLBACK_POLICY.bannedKeywords.forEach(keyword => {
      if (text.includes(keyword)) {
        violations.push({ type: 'banned_keyword', keyword });
      }
    });
    return violations;
  },

  // 위험 패턴 감지
  checkDangerousPatterns: (text) => {
    const violations = [];
    Object.entries(LEGAL_GUIDELINES.dangerousPatterns).forEach(([type, pattern]) => {
      pattern.expressions.forEach(expr => {
        if (text.includes(expr)) {
          violations.push({ type: 'dangerous_pattern', pattern: expr, category: type });
        }
      });
    });
    return violations;
  },

  // 종합 위험도 평가
  assessRisk: (text) => {
    const keywordViolations = VIOLATION_DETECTOR.checkBannedKeywords(text);
    const patternViolations = VIOLATION_DETECTOR.checkDangerousPatterns(text);
    
    const totalViolations = keywordViolations.length + patternViolations.length;
    let riskLevel = 'LOW';
    
    if (totalViolations >= 3) riskLevel = 'HIGH';
    else if (totalViolations >= 1) riskLevel = 'MEDIUM';
    
    return {
      level: riskLevel,
      keywordViolations,
      patternViolations,
      totalViolations
    };
  }
};

// ============================================================================
// 안전장치 및 유틸리티
// ============================================================================

/** JSON 파싱 실패 시 사용할 기본 초안 */
function createFallbackDraft(topic = '', category = '') {
  const title = `${category || '일반'}: ${topic || '제목 미정'}`;
  const content = [
    `<h2>${title}</h2>`,
    `<p>원고 생성 중 오류가 발생하여 기본 초안을 제시합니다. 주제와 관련한 사실 확인과 출처 추가가 필요합니다.</p>`,
    `<h3>핵심 요약</h3>`,
    `<ul><li>주제: ${topic || '-'}</li><li>분류: ${category || '-'}</li></ul>`,
    `<p>이재명 정신에 기반한 포용적 관점에서 다시 검토하여 보완하겠습니다.</p>`,
    `<p>[출처: 직접 추가 필요]</p>`
  ].join('');
  return { 
    title, 
    content, 
    wordCount: Math.ceil(content.length / 2), 
    style: '이재명정신_폴백' 
  };
}

/** 정책 위반 여부 사전 검사 */
function validateContent(text) {
  const risk = VIOLATION_DETECTOR.assessRisk(text);
  
  if (risk.level === 'HIGH') {
    return {
      valid: false,
      message: '고위험 내용 감지: 법적 검토 필요',
      violations: risk
    };
  }
  
  if (risk.level === 'MEDIUM') {
    return {
      valid: true,
      warning: '중위험 내용 감지: 표현 수정 권장',
      violations: risk
    };
  }
  
  return {
    valid: true,
    message: '법적 리스크 낮음',
    violations: risk
  };
}

// ============================================================================
// 선거법 준수 표현 규칙 (3단계)
// 1단계: 예비후보 등록 이전 (준비, 현역)
// 2단계: 예비후보 등록 이후 (예비)
// 3단계: 본 후보 등록 이후 (후보)
// ============================================================================

const ELECTION_EXPRESSION_RULES = {
  // 1단계: 예비후보 등록 이전
  STAGE_1: {
    applies_to: ['준비', '현역'],
    description: '예비후보 등록 이전 - 일반 정치인, 당직자, 현역 의원/단체장',
    forbidden: {
      // 신분 관련 - 정규식 패턴
      status: [
        /예비\s*후보/g,
        /출마\s*예정/g,
        /[가-힣]+이\s*되겠습니다/g,  // "○○시장이 되겠습니다"
      ],
      // 공약성 표현
      pledge: [
        /공약을?\s*(발표|제시|말씀)/g,
        /공약\s*사항/g,
        /공약입니다/g,
        /[0-9]+\s*번째\s*공약/g,
        /첫\s*번째\s*공약/g,
        /두\s*번째\s*공약/g,
        /세\s*번째\s*공약/g,
        /약속\s*드립니다/g,
        /약속\s*드리겠습니다/g,
        /약속\s*하겠습니다/g,
        /반드시\s*실현/g,
        /꼭\s*실현/g,
        /당선\s*되면/g,
        /당선\s*후에?/g,
        /당선되어/g,
      ],
      // 지지 호소
      support: [
        /지지해?\s*주십시오/g,
        /지지를?\s*부탁/g,
        /지지와\s*참여/g,
        /함께해?\s*주십시오/g,
        /선택해?\s*주십시오/g,
        /지원\s*부탁/g,
        /투표해?\s*주십시오/g,
        /한\s*표\s*부탁/g,
      ],
      // 선거 직접 언급
      election: [
        /다음\s*선거/g,
        /[0-9]{4}년\s*(지방)?선거/g,
        /재선을?\s*위해/g,
        /선거\s*준비/g,
        /출마\s*준비/g,
      ]
    },
    // 자동 치환 규칙 (forbidden → replacement)
    replacements: {
      '공약': '정책 방향',
      '공약을 발표': '정책 방향을 제안',
      '공약을 제시': '정책 방향을 제안',
      '공약 사항': '정책 제안 사항',
      '첫 번째 공약': '첫 번째 정책 제안',
      '두 번째 공약': '두 번째 정책 제안',
      '세 번째 공약': '세 번째 정책 제안',
      '약속드립니다': '이 방향으로 노력하겠습니다',
      '약속 드립니다': '이 방향으로 노력하겠습니다',
      '약속드리겠습니다': '이 방향으로 노력하겠습니다',
      '약속하겠습니다': '이 방향으로 노력하겠습니다',
      '반드시 실현': '실현될 수 있도록 노력',
      '꼭 실현': '실현될 수 있도록 노력',
      '당선되면': '이 정책이 실현된다면',
      '당선 후': '향후',
      '당선되어': '힘을 모아',
      '지지해 주십시오': '관심 가져 주십시오',
      '지지를 부탁': '관심을 부탁',
      '지지와 참여를 부탁': '관심과 성원을 부탁',
      '지지와 참여': '관심과 성원',
      '함께해 주십시오': '함께 고민해 주십시오',
      '선택해 주십시오': '관심 가져 주십시오',
      '투표해 주십시오': '관심 가져 주십시오',
      '다음 선거': '앞으로',
      '재선을 위해': '더 나은 지역을 위해',
      '선거 준비': '정책 연구',
      '출마 준비': '정책 연구',
      '예비후보': '',  // 삭제
      '출마 예정': '정치 활동 중인',
    },
    // 프롬프트에 주입할 지시문
    promptInstruction: `
[⚠️ 선거법 준수 - 예비후보 등록 이전 단계]
현재 상태에서는 선거법상 다음 표현을 사용할 수 없습니다.

** 절대 금지 표현 **
❌ "공약", "공약을 발표합니다", "○번째 공약"
❌ "약속드립니다", "약속하겠습니다", "반드시 실현하겠습니다"
❌ "당선되면 ○○하겠습니다", "당선 후에"
❌ "지지해 주십시오", "함께해 주십시오", "선택해 주십시오"
❌ "투표해 주십시오", "지지를 부탁드립니다"
❌ "다음 선거에서", "2026년 지방선거에서", "재선을 위해"
❌ "예비후보", "후보", "출마 예정자"

** 반드시 사용할 대체 표현 **
✅ "공약" → "정책 방향", "비전", "정책 제안"
✅ "약속드립니다" → "이 방향으로 노력하겠습니다", "연구하고 있습니다"
✅ "당선되면" → "이 정책이 실현된다면"
✅ "지지 부탁" → "관심 부탁드립니다"

** 사용 가능한 표현 **
"정책 방향을 제안합니다"
"비전을 공유드립니다"
"이런 방향의 정책을 연구하고 있습니다"
"논의를 이어가겠습니다"
"정책 제안을 드립니다"
`
  },

  // 2단계: 예비후보 등록 이후
  STAGE_2: {
    applies_to: ['예비'],
    description: '예비후보 등록 이후 - 선관위 등록 완료',
    forbidden: {
      // 본후보 전용 표현만 금지
      fullCandidateOnly: [
        /투표해?\s*주십시오/g,
        /저를\s*선택해?\s*주십시오/g,
        /기호\s*[0-9]+번/g,  // 아직 기호 없음
      ]
    },
    replacements: {
      '투표해 주십시오': '지지해 주십시오',
      '저를 선택해 주십시오': '함께해 주십시오',
    },
    promptInstruction: `
[선거법 준수 - 예비후보 단계]
예비후보로서 대부분의 선거 표현이 가능합니다.

✅ 사용 가능: "공약", "약속드립니다", "당선되면", "지지해 주십시오"
❌ 아직 불가: "투표해 주십시오" (선거기간에만 가능)
`
  },

  // 3단계: 본 후보 등록 이후 (선거기간)
  STAGE_3: {
    applies_to: ['후보'],
    description: '본 후보 등록 이후 - 선거기간',
    forbidden: {
      // 불법 표현만 금지
      illegal: [
        /금품/g,
        /향응/g,
        /돈을?\s*드리/g,
      ]
    },
    replacements: {},
    promptInstruction: `
[선거법 준수 - 정식 후보 단계]
대부분의 선거운동 표현이 가능합니다.
❌ 금지: 금품/향응 제공 암시, 허위사실 유포
`
  }
};

/**
 * 상태에 해당하는 선거법 단계 반환
 * @param {string} status - 사용자 상태 (준비/현역/예비/후보)
 * @returns {Object|null} 해당 단계의 규칙
 */
function getElectionStage(status) {
  for (const [stageName, stage] of Object.entries(ELECTION_EXPRESSION_RULES)) {
    if (stage.applies_to && stage.applies_to.includes(status)) {
      return { name: stageName, ...stage };
    }
  }
  return null;
}

// ============================================================================
// 내보내기
// ============================================================================

module.exports = {
  // 정책 관리
  getPolicySafe,
  loadPolicyFromDB,
  FALLBACK_POLICY,

  // 법적 가이드라인
  LEGAL_GUIDELINES,

  // 위반 탐지 시스템
  VIOLATION_DETECTOR,

  // 안전장치
  createFallbackDraft,
  validateContent,

  // 선거법 준수 규칙
  ELECTION_EXPRESSION_RULES,
  getElectionStage,
};