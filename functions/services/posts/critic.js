/**
 * functions/services/posts/critic.js
 * Critic Agent - 생성된 원고의 지침 준수 여부를 검토하는 편집장 모듈
 *
 * 역할:
 * 1. 엄격한 편집장: 지침 위반 사항 검출
 * 2. 까다로운 유권자: 진정성/정무적 판단
 */

'use strict';

const { callGenerativeModel } = require('../gemini');
const { logError } = require('../../common/log');

// 검증 항목 정의
const VIOLATION_TYPES = {
  C1: { id: 'C1', name: '선거법 위반', severity: 'HARD' },
  C2_A: { id: 'C2-a', name: '팩트 오류', severity: 'HARD' },
  C2_B: { id: 'C2-b', name: '해석 과잉', severity: 'SOFT' },
  C3: { id: 'C3', name: '심각한 반복', severity: 'HARD' },
  C4: { id: 'C4', name: '구조 미완', severity: 'SOFT' },
  C5: { id: 'C5', name: '톤 이탈', severity: 'SOFT' },
  C6: { id: 'C6', name: '유권자 관점', severity: 'POLITICAL' }
};

/**
 * Critic 프롬프트 생성
 */
function buildCriticPrompt({ draft, ragContext, guidelines, status, topic, authorName }) {
  return `당신은 두 가지 역할을 동시에 수행합니다:

【역할 1: 엄격한 편집장】
- 지침 위반 사항을 빠짐없이 찾아내는 검수관
- 팩트 오류에 무관용

【역할 2: 까다로운 유권자】
- "${authorName || '이 의원'}님을 지지할지 고민하는 중립적 시민"
- 진정성이 느껴지는지, 기계적 홍보는 아닌지 판단

═══════════════════════════════════════
[검토 대상 초안]
═══════════════════════════════════════
${draft}

═══════════════════════════════════════
[사실 확인용 참조 데이터 (RAG)]
이 데이터에 있는 내용만 '팩트'로 인정됩니다.
═══════════════════════════════════════
${ragContext || '(제공된 참조 데이터 없음 - 일반적 내용만 허용)'}

═══════════════════════════════════════
[적용된 핵심 지침]
═══════════════════════════════════════
${guidelines || '(기본 지침 적용)'}

═══════════════════════════════════════
[검토 체크리스트]
═══════════════════════════════════════

🔴 HARD FAIL (반드시 수정)
━━━━━━━━━━━━━━━━━━━━━━━━
C1. 선거법 위반 (현재 상태: ${status || '미지정'})
    → 준비/현역이면 "~하겠습니다" 공약 표현 금지
    → 예: 추진하겠습니다, 만들겠습니다, 실현하겠습니다 등

C2-a. 팩트 오류
    → 수치, 날짜, 지역명, 사업명이 [참조 데이터]와 다르면 위반
    → 예: "100억 투자" → 참조에 "50억"만 있으면 위반
    → [참조 데이터]가 없으면 구체적 수치/사업명 사용 자체가 위반

C3. 심각한 반복
    → 같은 문장이 2회 이상 등장하면 위반
    → 같은 내용을 표현만 바꿔 반복해도 위반

🟡 SOFT FAIL (개선 권고)
━━━━━━━━━━━━━━━━━━━━━━━━
C2-b. 해석 과잉
    → [참조 데이터]에 없는 공약/계획을 과도하게 확대 해석
    → 단, 일반적 인사말/연결어는 허용

C4. 구조 미완
    → 글이 자연스럽게 끝나지 않음
    → 끝인사 후 본문이 다시 시작됨

C5. 톤 이탈
    → 격식체 말투에서 벗어남
    → 비서관다운 품위 부족

🟢 POLITICAL REVIEW (정무적 검토)
━━━━━━━━━━━━━━━━━━━━━━━━
C6. 유권자 관점
    → "이 글이 진정성 있게 느껴지는가?"
    → "너무 기계적인 홍보문 같지 않은가?"
    → "유권자로서 공감이 가는가?"

═══════════════════════════════════════
[출력 형식 - 반드시 JSON만 출력]
═══════════════════════════════════════
\`\`\`json
{
  "passed": true 또는 false,
  "score": 0-100 사이 정수,
  "violations": [
    {
      "id": "C1, C2-a, C2-b, C3, C4, C5, C6 중 하나",
      "severity": "HARD" 또는 "SOFT" 또는 "POLITICAL",
      "type": "위반 유형 이름",
      "location": "위치 (n번째 문단, 또는 구체적 위치)",
      "problematic": "문제가 된 원문 발췌 (30자 이내)",
      "suggestion": "구체적인 수정 제안"
    }
  ],
  "politicalReview": {
    "authenticity": "진정성 평가 (1줄)",
    "voterAppeal": "유권자 호소력 평가 (1줄)"
  },
  "summary": "종합 평가 (1줄)"
}
\`\`\`

위반 사항이 없으면 "passed": true, "violations": [], "score": 100으로 응답하세요.
JSON 외의 다른 텍스트는 출력하지 마세요.`;
}

/**
 * Critic 응답 파싱
 */
function parseCriticReport(response) {
  try {
    // JSON 블록 추출
    const jsonMatch = response.match(/```json\s*([\s\S]*?)\s*```/);
    const jsonStr = jsonMatch ? jsonMatch[1] : response;

    // JSON 파싱
    const report = JSON.parse(jsonStr.trim());

    // 필수 필드 검증
    if (typeof report.passed !== 'boolean') {
      report.passed = false;
    }
    if (!Array.isArray(report.violations)) {
      report.violations = [];
    }
    if (typeof report.score !== 'number') {
      report.score = calculateScore(report);
    }

    return report;

  } catch (error) {
    console.error('❌ Critic 응답 파싱 실패:', error.message);
    console.error('원본 응답:', response?.substring(0, 500));

    // 파싱 실패 시 기본 리포트 반환
    return {
      passed: false,
      score: 50,
      violations: [{
        id: 'PARSE_ERROR',
        severity: 'SOFT',
        type: '검토 오류',
        location: '전체',
        problematic: '파싱 실패',
        suggestion: '재검토 필요'
      }],
      politicalReview: {
        authenticity: '평가 불가',
        voterAppeal: '평가 불가'
      },
      summary: 'Critic 응답 파싱 실패'
    };
  }
}

/**
 * 점수 계산
 */
function calculateScore(criticReport) {
  let score = 100;

  if (!criticReport.violations || !Array.isArray(criticReport.violations)) {
    return score;
  }

  for (const v of criticReport.violations) {
    switch (v.severity) {
      case 'HARD':
        score -= 30;  // 치명적 위반
        break;
      case 'SOFT':
        score -= 10;  // 개선 필요
        break;
      case 'POLITICAL':
        score -= 5;   // 권고 사항
        break;
      default:
        score -= 5;
    }
  }

  return Math.max(0, Math.min(100, score));
}

/**
 * HARD 위반 존재 여부 확인
 */
function hasHardViolations(criticReport) {
  if (!criticReport.violations || !Array.isArray(criticReport.violations)) {
    return false;
  }
  return criticReport.violations.some(v => v.severity === 'HARD');
}

/**
 * 재시도 필요 여부 판단
 */
function shouldRetry(criticReport) {
  // HARD 위반이 있거나 점수가 70 미만이면 재시도
  return hasHardViolations(criticReport) || criticReport.score < 70;
}

/**
 * Critic Agent 실행
 *
 * @param {Object} options
 * @param {string} options.draft - 검토할 초안
 * @param {string} options.ragContext - RAG 컨텍스트
 * @param {string} options.guidelines - 적용된 지침
 * @param {string} options.status - 사용자 상태
 * @param {string} options.topic - 원고 주제
 * @param {string} options.authorName - 작성자 이름
 * @param {string} options.modelName - 사용할 모델
 * @returns {Promise<Object>} Critic 리포트
 */
async function runCriticReview({
  draft,
  ragContext,
  guidelines,
  status,
  topic,
  authorName,
  modelName = 'gemini-2.5-flash'
}) {
  console.log('👔 Critic Agent 검토 시작...');

  try {
    // Critic 프롬프트 생성
    const prompt = buildCriticPrompt({
      draft,
      ragContext,
      guidelines,
      status,
      topic,
      authorName
    });

    // Gemini 호출
    const response = await callGenerativeModel(prompt, 1, modelName);

    if (!response) {
      throw new Error('Critic Agent 응답 없음');
    }

    // 응답 파싱
    const report = parseCriticReport(response);

    // 점수 재계산 (일관성 보장)
    report.score = calculateScore(report);
    report.needsRetry = shouldRetry(report);

    console.log(`👔 Critic 검토 완료: ${report.passed ? '✅ 통과' : '❌ 위반 발견'} (점수: ${report.score})`);

    if (report.violations.length > 0) {
      console.log(`   위반 사항 ${report.violations.length}건:`);
      report.violations.forEach((v, i) => {
        console.log(`   ${i + 1}. [${v.severity}] ${v.type}: ${v.problematic?.substring(0, 30)}...`);
      });
    }

    return report;

  } catch (error) {
    console.error('❌ Critic Agent 오류:', error.message);
    logError('runCriticReview', 'Critic Agent 실행 실패', { error: error.message });

    // 오류 시 통과 처리 (Fail-open)
    return {
      passed: true,
      score: 70,
      violations: [],
      politicalReview: {
        authenticity: '검토 실패로 평가 불가',
        voterAppeal: '검토 실패로 평가 불가'
      },
      summary: 'Critic 검토 중 오류 발생 - 기본 통과 처리',
      needsRetry: false,
      error: error.message
    };
  }
}

/**
 * 핵심 지침 요약 생성 (프롬프트 하단 배치용)
 */
function summarizeGuidelines(status, topic) {
  const guidelines = [];

  // 선거법 관련
  if (status === '준비' || status === '현역') {
    guidelines.push('⚠️ 선거법: "~하겠습니다" 공약 표현 절대 금지');
  }

  // 공통 지침
  guidelines.push('📝 반복 금지: 같은 내용/문장 반복 불가');
  guidelines.push('✅ 완결성: 글은 자연스럽게 끝맺을 것');
  guidelines.push('🎯 팩트 준수: RAG 데이터에 없는 수치/사업명 사용 금지');

  return guidelines.join('\n');
}

module.exports = {
  buildCriticPrompt,
  parseCriticReport,
  calculateScore,
  hasHardViolations,
  shouldRetry,
  runCriticReview,
  summarizeGuidelines,
  VIOLATION_TYPES
};
