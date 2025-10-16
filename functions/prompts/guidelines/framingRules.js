/**
 * functions/templates/guidelines/framingRules.js (최종본)
 * 전자두뇌비서관의 '지능적 프레이밍' 시스템을 위한 핵심 규칙 정의 파일입니다.
 * 모든 규칙은 '우선순위'에 따라 적용되어 논리적 충돌을 방지합니다.
 */

'use strict';

// 1-A. 프레이밍 비활성화 예외 키워드 (Overrides)
const OVERRIDE_KEYWORDS = {
  PAST_GOVERNMENT: [
    '문재인 정부', '김대중 정부', '노무현 정부', '지난 정부', '이전 정부', '과거 정부'
  ],
  OPPOSITION_CRITICISM: [
    '윤석열 정부', '국민의힘', '야당', '보수 정권', '상대 당'
  ],
};

// 1-B. 고위험 키워드 사전 (Risk Detection Dictionary)
const HIGH_RISK_KEYWORDS = {
  SELF_CRITICISM: [
    '이재명 정부', '민주당 정부', '우리 정부', '현 정부', '이번 정부',
    '이재명 대통령', '민주당의', '정부여당', '집권여당'
  ],
  PRE_ELECTION_PLEDGE: [
    '공약', '선거 약속', '저를 뽑아주신다면'
  ],
};

// 2. 정치적 프레임 정의 (Political Framing Rules)
const POLITICAL_FRAMES = {
  CONSTRUCTIVE_CRITICISM: {
    id: 'constructive_criticism',
    description: '자당 정부 비판을 건설적 대안 제시로 전환하는 프레임',
    promptInjection: `
[⚠️ 중요: '건설적 비판' 프레이밍 적용]
너의 역할은 비판이 아닌, 정부의 성공을 돕는 충언을 하는 것이다. 다음 구조를 반드시 준수하라:
1.  **시작 (긍정적 평가)**: 먼저 현 정부가 해당 분야에서 노력하고 있는 점을 언급하며 긍정적으로 시작하라.
2.  **본론 (국민 목소리 전달)**: '다만, 현장에서 만나 뵙는 주민들께서는 ~라는 아쉬움을 토로하십니다' 와 같이, 비판의 주체를 '나'가 아닌 '주민'으로 설정하여 완곡하게 문제점을 전달하라.
3.  **결론 (건설적 대안 제시)**: '따라서 우리 민주당 정부가 ~점을 보완한다면, 국민의 더 큰 지지를 받을 것이라 확신합니다' 와 같이, 비판이 아닌 '보완 제언'의 형태로 대안을 제시하며 희망적으로 마무리하라.
절대 정부를 직접적으로 공격하거나 '실패'와 같은 부정적 단어를 사용해서는 안 된다.`
  },
  POLICY_VISION_FRAMING: {
    id: 'policy_vision_framing',
    description: '선거 공약을 정책 비전으로 순화하는 프레임',
    promptInjection: `
[⚠️ 중요: '정책 비전' 프레이밍 적용]
'공약', '약속' 등 선거법에 위촉될 수 있는 단어 사용을 엄격히 금지한다.
대신 '저의 정치적 비전은', '우리 지역의 숙원 사업인' 등과 같은 표현을 사용하여,
장기적인 정책 목표를 제시하는 형태로 내용을 순화하여 작성하라.`
  },
};

module.exports = {
  OVERRIDE_KEYWORDS,
  HIGH_RISK_KEYWORDS,
  POLITICAL_FRAMES,
};
