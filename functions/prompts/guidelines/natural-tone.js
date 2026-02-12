/**
 * functions/prompts/guidelines/natural-tone.js
 * 자연스러운 한국어 문체 규칙 - LLM 특유 표현 제거
 *
 * 적용 대상: WriterAgent, TitleAgent, ChainWriterAgent, SNS 변환, EditorAgent
 */

'use strict';

/**
 * LLM 특유 표현 패턴 (블랙리스트)
 */
const BLACKLIST_PATTERNS = {
  // 1. 결론 클리셰
  결론클리셰: [
    '결론적으로', '요약하자면', '정리하면', '종합하면',
    '전반적으로 볼 때', '전체적으로 살펴보면', '마지막으로 정리하자면'
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

  // 3. 완곡 표현
  완곡표현: [
    '인 것 같습니다', '로 보입니다', '라고 여겨집니다',
    '라고 볼 수 있습니다', '라고 할 수 있습니다',
    '일 수 있습니다', '할 수 있습니다'
  ],

  // 4. 추상적 당위 표현
  당위남발: [
    '할 필요가 있습니다', '해야 할 것입니다', '하는 것이 중요합니다',
    '하는 것이 바람직합니다', '할 것으로 기대됩니다', '필요할 것으로 생각됩니다'
  ],

  // 5. 형식적 조사/구문
  형식적구문: [
    { pattern: /에 대해\s/g, severity: 'low' },
    { pattern: /에 있어서\s/g, severity: 'medium' },
    { pattern: /라는 점에서\s/g, severity: 'medium' },
    { pattern: /측면에서 볼 때\s/g, severity: 'high' }
  ],

  // 6. 동사/구문 반복
  동사반복: [
    '던지면서', '던지며',
    '이끌어내며', '이끌어가며'
  ]
};

/**
 * 권장 대체 표현 가이드
 */
const REPLACEMENT_GUIDE = {
  결론제거: {
    rule: '마무리 문장에 "결론적으로" 같은 접속어를 쓰지 마세요. 핵심 문장을 바로 제시하세요.',
    examples: [
      { bad: '결론적으로, 이 정책은 지역 경제에 도움이 될 것으로 보입니다.', good: '이 정책으로 지역 경제가 살아납니다.' },
      { bad: '정리하면, 우리는 청년 일자리 문제를 해결해야 합니다.', good: '청년 일자리 1,200개를 만들겠습니다.' }
    ]
  },
  단정화: {
    rule: '정책과 사실은 "~입니다", "~합니다"로 단정하세요.',
    examples: [
      { bad: '이 문제는 심각한 것 같습니다.', good: '이 문제는 심각합니다.' },
      { bad: '지원이 필요할 것으로 보입니다.', good: '지원이 필요합니다.' }
    ]
  },
  구체화: {
    rule: '"~할 필요가 있습니다" 같은 추상적 당위 대신, 주체와 시기를 명시한 약속을 사용하세요.',
    examples: [
      { bad: '예산을 확보할 필요가 있습니다.', good: '내년 정기국회에서 예산 300억 원을 확보하겠습니다.' },
      { bad: '제도 개선이 중요합니다.', good: '이번 회기에 제도 개선 법안을 발의하겠습니다.' }
    ]
  },
  접속어최소화: {
    rule: '문장 첫머리에 접속어를 반복하지 마세요. 조사와 어순만으로 자연스럽게 연결하세요.',
    examples: [
      { bad: '교육 예산을 늘렸습니다. 또한 복지 예산도 확대했습니다.', good: '교육 예산을 늘렸고, 복지 예산도 확대했습니다.' },
      { bad: '한편, 청년 일자리도 중요합니다.', good: '청년 일자리도 중요합니다.' }
    ]
  }
};

/**
 * 자연스러운 문체 프롬프트 섹션 생성 (XML 형식)
 * @param {Object} options - 옵션 (platform, severity)
 * @returns {string} 프롬프트에 삽입할 가이드 텍스트
 */
function buildNaturalTonePrompt(options = {}) {
  const platform = options.platform || 'general';
  const severity = options.severity || 'standard';

  const isStrict = severity === 'strict' || ['title', 'sns'].includes(platform);

  const cliches = BLACKLIST_PATTERNS.결론클리셰.slice(0, 4).join(', ');
  const conjunctions = '또한, 한편, 더 나아가, 이러한 점에서';
  const euphemisms = '~것 같습니다, ~로 보입니다';
  const musts = '~할 필요가 있습니다';

  const strictExtras = isStrict
    ? `\n    <category name="격식체 잔여" action="간결한 구어체로 변환">따라서, 결과적으로, ~라고 할 수 있습니다</category>`
    : '';

  return `
<natural_tone_rules>
  <banned_expressions>
    <category name="결론 클리셰" action="접속어 없이 핵심만 제시">${cliches} 등</category>
    <category name="과도한 접속어" action="조사와 어순으로 자연스럽게 연결">${conjunctions}</category>
    <category name="완곡 표현" action="단정형 사용: ~입니다, ~합니다">${euphemisms}</category>
    <category name="당위 남발" action="구체적 약속: ~하겠습니다, 추진합니다">${musts}</category>${strictExtras}
    <category name="동사/구문 반복" severity="critical" action="동의어 교체 필수">
      같은 동사를 원고 전체에서 3회 이상 사용 금지 (최대 2회)
      <example>
        <bad>"던지면서" 6회 반복</bad>
        <alternatives>제시하며, 약속하며, 열며, 보여드리며, 선보이며</alternatives>
      </example>
      <example>
        <bad>"이끌어내며" 반복</bad>
        <alternatives>달성하며, 만들어내며, 실현하며</alternatives>
      </example>
    </category>
    <category name="슬로건/캐치프레이즈 반복" severity="critical" action="결론부 1회만 사용">
      같은 비전 문구, 벤치마크 비유를 여러 섹션에서 반복 금지
      <example>
        <bad>도입부+본론+결론에서 "청년이 돌아오는 부산" 3회 반복</bad>
        <good>도입부: "청년 일자리가 풍부한 부산" / 결론부: "청년이 돌아오는 부산" (1회만)</good>
      </example>
    </category>
  </banned_expressions>
  <preferred_style>
    <rule>서론 접속어 없이 바로 본론 시작</rule>
    <rule>단정형 종결: ~입니다, ~합니다</rule>
    <rule>약속형 공약: ~하겠습니다, 추진합니다 (~할 필요가 있습니다 금지)</rule>
  </preferred_style>
</natural_tone_rules>
`;
}

/**
 * SNS 특화 자연스러운 문체 가이드 (간소화 XML 버전)
 */
function buildSNSNaturalToneGuide() {
  return `
<natural_tone_rules platform="sns">
  <banned>결론적으로, 또한, 한편, ~것 같습니다, ~할 필요가 있습니다</banned>
  <preferred>바로 핵심 시작, 단정형 종결 (~입니다), 약속형 (~하겠습니다)</preferred>
  <example>
    <bad>결론적으로, 이 정책은 중요한 것 같습니다.</bad>
    <good>이 정책으로 지역이 달라집니다.</good>
  </example>
</natural_tone_rules>
`;
}

/**
 * 제목 특화 자연스러운 문체 가이드
 */
function buildTitleNaturalToneGuide() {
  return `
<natural_tone_rules platform="title">
  <banned>"~에 대해", "~에 있어서" 형식적 조사, "~것 같다", "~로 보인다" 완곡 표현</banned>
  <preferred>단정적이고 직접적으로 표현</preferred>
</natural_tone_rules>
`;
}

module.exports = {
  BLACKLIST_PATTERNS,
  REPLACEMENT_GUIDE,
  buildNaturalTonePrompt,
  buildSNSNaturalToneGuide,
  buildTitleNaturalToneGuide
};
