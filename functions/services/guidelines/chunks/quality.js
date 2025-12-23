/**
 * functions/services/guidelines/chunks/quality.js
 * 품질 규칙 지침 청크
 */

'use strict';

const QUALITY_CHUNKS = [
  // ============================================================================
  // CRITICAL: 문장 반복 금지
  // ============================================================================
  {
    id: 'QA-001',
    type: 'quality',
    priority: 'CRITICAL',
    applies_to: { category: ['all'] },
    keywords: ['반복', '중복', '같은 문장', '동일'],
    instruction: '동일 문장 2회 이상 반복 절대 금지 → 각 문장은 새로운 정보 포함',
    forbidden: ['같은 문장 반복', '표현만 바꿔 반복', '유사 문단 반복'],
    examples: [
      {
        bad: '"청년 일자리가 중요합니다." ... "청년 일자리가 중요합니다."',
        good: '"청년 일자리가 중요합니다." ... "특히 지역 내 스타트업 육성이 핵심입니다."'
      },
      {
        bad: '같은 내용을 표현만 바꿔 3번 반복',
        good: '1문단 1메시지 원칙 준수'
      }
    ],
    rule: '1문단 1메시지: 새 문단은 반드시 새로운 정보를 담아야 함'
  },

  // ============================================================================
  // CRITICAL: 구조 완결성 (Endless Loop 금지)
  // ============================================================================
  {
    id: 'QA-002',
    type: 'quality',
    priority: 'CRITICAL',
    applies_to: { category: ['all'] },
    keywords: ['구조', '마무리', '끝', '완결', '인사'],
    instruction: '마무리 인사 이후 본문 재시작 금지 → 끝맺음 후 즉시 종료',
    forbidden: ['마무리 후 본문 재시작', '감사합니다 후 새 내용', '무한 반복'],
    examples: [
      {
        bad: '"감사합니다." <p>그리고 또한 청년 정책에 대해...</p>',
        good: '"감사합니다." (여기서 글 종료)'
      },
      {
        bad: '결론 → 새 주제 → 다시 결론',
        good: '도입 → 본론 → 결론 (한 번만)'
      }
    ],
    rule: '글의 맺음말이 나오면 그 지점에서 완전히 종료'
  },

  // ============================================================================
  // CRITICAL: 문장 완결성
  // ============================================================================
  {
    id: 'QA-003',
    type: 'quality',
    priority: 'CRITICAL',
    applies_to: { category: ['all'] },
    keywords: ['완결', '문장', '종결', '어미', '조사'],
    instruction: '모든 문장은 완전한 형태로 종결 → 중간 끊김 금지',
    forbidden: ['문장 중간 끊김', '조사 누락', '어미 누락'],
    examples: [
      {
        bad: '"주민 여러분과 함께"',
        good: '"주민 여러분과 함께 만들어가겠습니다."'
      },
      {
        bad: '"정책을 추진하여 발전"',
        good: '"정책을 추진하여 발전시키겠습니다."'
      }
    ],
    rule: '모든 문장은 "~입니다", "~합니다" 등으로 명확히 종결'
  },

  // ============================================================================
  // HIGH: 내용 충실도 (추상적 표현 지양)
  // ============================================================================
  {
    id: 'QA-010',
    type: 'quality',
    priority: 'HIGH',
    applies_to: { category: ['all'] },
    keywords: ['구체적', '수치', '사례', '팩트', '근거'],
    instruction: '추상적 표현 대신 구체적 정보(수치, 날짜, 사례) 사용',
    forbidden: ['추상적 표현만 나열', '근거 없는 주장'],
    examples: [
      {
        bad: '"노력하겠습니다", "최선을 다하겠습니다", "중요합니다"만 반복',
        good: '"2024년 3월 시행된 정책으로 청년 취업률 15% 증가"'
      },
      {
        bad: '"많은 성과를 이뤘습니다"',
        good: '"지난 1년간 120건의 민원을 해결했습니다"'
      }
    ],
    rule: '분량보다 내용의 충실도 우선'
  },

  // ============================================================================
  // HIGH: 톤앤매너 일관성
  // ============================================================================
  {
    id: 'QA-011',
    type: 'quality',
    priority: 'HIGH',
    applies_to: { category: ['all'] },
    keywords: ['톤', '말투', '존댓말', '격식'],
    instruction: '전체 원고에서 일관된 존댓말 사용, 격식체 유지',
    forbidden: ['반말 혼용', '격식체-비격식체 혼용'],
    examples: [
      {
        bad: '"~합니다" + "~해요" 혼용',
        good: '전체 "~합니다" 통일'
      },
      {
        bad: '"저는" 연속 3문장 시작',
        good: '주어 다양화 (저는/정책은/지역구민께서는)'
      }
    ],
    rule: '서민적이고 친근하되 품위 유지'
  },

  // ============================================================================
  // MEDIUM: "저는" 과다 사용 방지
  // ============================================================================
  {
    id: 'QA-020',
    type: 'quality',
    priority: 'MEDIUM',
    applies_to: { category: ['all'] },
    keywords: ['저는', '제가', '1인칭', '주어'],
    instruction: '"저는"으로 시작하는 문장 30% 이하, 주어 다양화',
    forbidden: ['"저는" 연속 3문장 시작'],
    examples: [
      {
        bad: '저는... 저는... 저는... (연속)',
        good: '저는... 이번 정책은... 주민 여러분께서는...'
      }
    ],
    alternatives: [
      '명사형 종결: "이번 정책은 중요한 의미를 갖습니다"',
      '수동태: "이 문제는 반드시 해결되어야 합니다"',
      '주체 전환: "계양구는", "이번 행사는"',
      '무주어: "더욱 발전된 모습을 보여드리겠습니다"'
    ]
  },

  // ============================================================================
  // MEDIUM: JSON 출력 형식
  // ============================================================================
  {
    id: 'QA-030',
    type: 'quality',
    priority: 'MEDIUM',
    applies_to: { category: ['all'] },
    keywords: ['JSON', '출력', '형식', '포맷'],
    instruction: '응답은 유효한 JSON 형식, title/content/wordCount 필드 포함',
    forbidden: ['JSON 외 텍스트', 'code-fence 미사용'],
    examples: [
      {
        bad: '원고 내용입니다... (텍스트만)',
        good: '```json\n{"title": "...", "content": "...", "wordCount": 1800}\n```'
      }
    ],
    schema: {
      required: ['title', 'content', 'wordCount'],
      optional: ['summary', 'tags', 'category']
    }
  }
];

/**
 * 우선순위별 청크 필터링
 */
function getChunksByPriority(priority) {
  return QUALITY_CHUNKS.filter(c => c.priority === priority);
}

/**
 * CRITICAL + HIGH 청크 반환
 */
function getEssentialQualityChunks() {
  return QUALITY_CHUNKS.filter(c =>
    c.priority === 'CRITICAL' || c.priority === 'HIGH'
  );
}

module.exports = {
  QUALITY_CHUNKS,
  getChunksByPriority,
  getEssentialQualityChunks
};
