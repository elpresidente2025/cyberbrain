/**
 * functions/prompts/guidelines/natural-tone.js
 * 자연스러운 한국어 문체 규칙 - LLM 특유 표현 제거
 *
 * 목적:
 * - AI 특유의 형식적/교과서적 표현 방지
 * - 정치인 화법에 맞는 자연스러운 표현 유도
 * - 실제 사람이 쓴 것처럼 보이는 문체 구현
 *
 * 적용 대상:
 * - WriterAgent (블로그 본문)
 * - TitleAgent (제목)
 * - ChainWriterAgent (고품질 본문)
 * - SNS 변환 (X, Threads, Instagram)
 * - EditorAgent (자동 수정)
 */

'use strict';

/**
 * LLM 특유 표현 패턴 (블랙리스트)
 * 연구 기반: KAIST XDAC, 한국어 AI 댓글 탐지 연구
 */
const BLACKLIST_PATTERNS = {
  // 1. 결론 클리셰 (영어 "in conclusion" 직역체)
  결론클리셰: [
    '결론적으로',
    '요약하자면',
    '정리하면',
    '종합하면',
    '전반적으로 볼 때',
    '전체적으로 살펴보면',
    '마지막으로 정리하자면'
  ],

  // 2. 과도한 접속어 (문단 첫머리에 기계적 반복)
  과도한접속어: [
    { pattern: /^또한\s/gm, severity: 'medium', replacement: '' },
    { pattern: /^한편\s/gm, severity: 'medium', replacement: '' },
    { pattern: /^더 나아가\s/gm, severity: 'high', replacement: '' },
    { pattern: /^이러한 점에서\s/gm, severity: 'high', replacement: '' },
    { pattern: /^이와 관련하여\s/gm, severity: 'high', replacement: '' },
    { pattern: /^이와 함께\s/gm, severity: 'medium', replacement: '' },
    { pattern: /^그럼에도 불구하고\s/gm, severity: 'medium', replacement: '그러나 ' },
    { pattern: /^따라서\s/gm, severity: 'low', replacement: '' },
    { pattern: /^이에 따라\s/gm, severity: 'medium', replacement: '' },
    { pattern: /^결과적으로\s/gm, severity: 'high', replacement: '' }
  ],

  // 3. 완곡 표현 (책임 회피처럼 들림)
  완곡표현: [
    '인 것 같습니다',
    '로 보입니다',
    '라고 여겨집니다',
    '라고 볼 수 있습니다',
    '라고 할 수 있습니다',
    '일 수 있습니다',  // 무의미한 가능성 표현
    '할 수 있습니다'   // 습관적 사용
  ],

  // 4. 추상적 당위 표현
  당위남발: [
    '할 필요가 있습니다',
    '해야 할 것입니다',
    '하는 것이 중요합니다',
    '하는 것이 바람직합니다',
    '할 것으로 기대됩니다',
    '필요할 것으로 생각됩니다'
  ],

  // 5. 형식적 조사/구문
  형식적구문: [
    { pattern: /에 대해\s/g, severity: 'low' },
    { pattern: /에 있어서\s/g, severity: 'medium' },
    { pattern: /라는 점에서\s/g, severity: 'medium' },
    { pattern: /측면에서 볼 때\s/g, severity: 'high' }
  ]
};

/**
 * 권장 대체 표현 가이드
 */
const REPLACEMENT_GUIDE = {
  // 결론 클리셰 → 접속어 없이 바로 핵심
  결론제거: {
    rule: '마무리 문장에 "결론적으로" 같은 접속어를 쓰지 마세요. 핵심 문장을 바로 제시하세요.',
    examples: [
      {
        bad: '결론적으로, 이 정책은 지역 경제에 도움이 될 것으로 보입니다.',
        good: '이 정책으로 지역 경제가 살아납니다.'
      },
      {
        bad: '정리하면, 우리는 청년 일자리 문제를 해결해야 합니다.',
        good: '청년 일자리 1,200개를 만들겠습니다.'
      }
    ]
  },

  // 완곡 표현 → 단정형
  단정화: {
    rule: '정책과 사실은 "~입니다", "~합니다"로 단정하세요. "~것 같습니다", "~로 보입니다"는 불확실할 때만 사용하세요.',
    examples: [
      {
        bad: '이 문제는 심각한 것 같습니다.',
        good: '이 문제는 심각합니다.'
      },
      {
        bad: '지원이 필요할 것으로 보입니다.',
        good: '지원이 필요합니다.'
      }
    ]
  },

  // 추상적 당위 → 구체적 약속/공약
  구체화: {
    rule: '"~할 필요가 있습니다" 같은 추상적 당위 대신, 주체와 시기를 명시한 약속을 사용하세요.',
    examples: [
      {
        bad: '예산을 확보할 필요가 있습니다.',
        good: '내년 정기국회에서 예산 300억 원을 확보하겠습니다.'
      },
      {
        bad: '제도 개선이 중요합니다.',
        good: '이번 회기에 제도 개선 법안을 발의하겠습니다.'
      }
    ]
  },

  // 과도한 접속어 → 조사/어순으로 연결
  접속어최소화: {
    rule: '문장 첫머리에 접속어를 반복하지 마세요. 조사와 어순만으로 자연스럽게 연결하세요.',
    examples: [
      {
        bad: '교육 예산을 늘렸습니다. 또한 복지 예산도 확대했습니다.',
        good: '교육 예산을 늘렸고, 복지 예산도 확대했습니다.'
      },
      {
        bad: '한편, 청년 일자리도 중요합니다.',
        good: '청년 일자리도 중요합니다.'
      }
    ]
  }
};

/**
 * 자연스러운 문체 프롬프트 섹션 생성
 * @param {Object} options - 옵션 (platform, severity)
 * @returns {string} 프롬프트에 삽입할 가이드 텍스트
 */
function buildNaturalTonePrompt(options = {}) {
  const platform = options.platform || 'general';  // 'general', 'sns', 'title'
  const severity = options.severity || 'standard'; // 'strict', 'standard', 'relaxed'

  // 플랫폼별 강도 조정
  const strictness = {
    title: 'strict',      // 제목은 가장 엄격 (짧아서 티가 남)
    sns: 'strict',        // SNS도 엄격 (스크롤 환경)
    general: 'standard'   // 블로그 본문은 표준
  };

  const level = strictness[platform] || severity;

  // 공통 금지 표현
  const forbiddenPhrases = [
    ...BLACKLIST_PATTERNS.결론클리셰,
    '또한', '한편', '더 나아가', '이러한 점에서', '이와 관련하여',
    '~인 것 같습니다', '~로 보입니다', '~라고 볼 수 있습니다',
    '~할 필요가 있습니다', '~하는 것이 중요합니다'
  ];

  // 엄격 모드 추가 금지
  if (level === 'strict') {
    forbiddenPhrases.push(
      '따라서', '결과적으로', '이에 따라',
      '~라고 할 수 있습니다', '~할 수 있습니다'
    );
  }

  return `
╔═══════════════════════════════════════════════════════════════╗
║  ✍️ 자연스러운 문체 - LLM 특유 표현 금지                         ║
╚═══════════════════════════════════════════════════════════════╝

**[금지 표현 - 절대 사용하지 마세요]**

❌ **결론 클리셰**: ${BLACKLIST_PATTERNS.결론클리셰.slice(0, 4).join(', ')} 등
   → 마무리 문장에 접속어 없이 핵심만 제시 (단, 문맥 연결을 위한 "따라서", "그렇기에" 등은 허용)

❌ **과도한 접속어**: "또한", "한편", "더 나아가", "이러한 점에서"
   → 조사와 어순으로 자연스럽게 연결

❌ **완곡 표현**: "~것 같습니다", "~로 보입니다", "~라고 볼 수 있습니다"
   → 정책/사실은 단정형 "~입니다", "~합니다" 사용

❌ **당위 남발**: "~할 필요가 있습니다", "~하는 것이 중요합니다"
   → 구체적 약속 "~하겠습니다", "추진합니다"

---

**[권장 표현 - 자연스럽게 작성하세요]**

✅ **바로 핵심 시작**: 서론 접속어 없이 바로 본론
✅ **단정형 종결**: "~입니다", "~합니다", "~했습니다"
✅ **약속형 공약**: "~하겠습니다", "추진합니다", "실현합니다"
✅ **조사로 연결**: "~이며", "~이고", "동시에~"

---

**[Before/After 예시]**

❌ 나쁜 예:
"결론적으로, 이러한 정책은 지역 경제 활성화에 중요한 역할을 할 것으로 보입니다.
또한 청년 일자리 창출에도 기여할 필요가 있습니다."

✅ 좋은 예:
"이 정책으로 지역 경제가 살아납니다.
청년 일자리 1,200개를 만들겠습니다."

---

**[체크리스트]**
- [ ] "결론적으로" 같은 결론 접속어 0회
- [ ] 문장 시작 "또한", "한편" 최소화 (0-1회)
- [ ] "~것 같습니다" → "~입니다" 전환
- [ ] "~할 필요가 있습니다" → "~하겠습니다" 전환
`;
}

/**
 * SNS 특화 자연스러운 문체 가이드 (간소화 버전)
 */
function buildSNSNaturalToneGuide() {
  return `
**[자연스러운 문체 - LLM 말투 금지]**

❌ 금지: "결론적으로", "또한", "한편", "~것 같습니다", "~할 필요가 있습니다"
✅ 권장: 바로 핵심 시작, 단정형 종결 (~입니다), 약속형 (~하겠습니다)

예시:
❌ "결론적으로, 이 정책은 중요한 것 같습니다."
✅ "이 정책으로 지역이 달라집니다."
`;
}

/**
 * 제목 특화 자연스러운 문체 가이드
 */
function buildTitleNaturalToneGuide() {
  return `
**[제목 문체 규칙]**
- "~에 대해", "~에 있어서" 같은 형식적 조사 금지
- "~것 같다", "~로 보인다" 완곡 표현 금지
- 단정적이고 직접적으로 표현
`;
}

module.exports = {
  BLACKLIST_PATTERNS,
  REPLACEMENT_GUIDE,
  buildNaturalTonePrompt,
  buildSNSNaturalToneGuide,
  buildTitleNaturalToneGuide
};
