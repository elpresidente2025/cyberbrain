/**
 * functions/prompts/templates/bipartisan-cooperation.js
 * '초당적 협력' 작법 전용 프롬프트 생성 모듈입니다.
 * 
 * 5단계 톤앤매너 프레임워크 기반
 * - 한국 정치의 팬덤 정치, 진영 논리, 강성 지지층의 민감성 고려
 * - 차이 먼저 명시, 인물은 분리
 * - 구체성 필수, 추상 극찬 금지
 * - 초당적 협력으로 연결
 */

'use strict';

// ============================================================================
// 5단계 톤 강도 프레임워크 (TONE INTENSITY LEVELS)
// ============================================================================

const TONE_LEVELS = {
    // 1단계: 객관적 인정 (가장 안전)
    LEVEL_1_OBJECTIVE: {
        id: 'objective_acknowledgment',
        name: '1단계: 객관적 인정 (가장 안전)',
        when: '팩트만 전달할 때',
        tone: '감정 배제, 절제됨',
        template: '○○ 의원이 제시한 [구체적 내용]의 문제 지적은 근거가 있다.',
        caution: '감탄·칭찬 톤 최소화'
    },

    // 2단계: 구체적 인정 (권장)
    LEVEL_2_SPECIFIC: {
        id: 'specific_acknowledgment',
        name: '2단계: 구체적 인정 (권장)',
        when: '특정 행동·성과를 긍정할 때',
        tone: '구체적 근거 + 범위 한정',
        template: '[구체적 행동]을 보여준 ○○ 의원의 노력만큼은 진심으로 인정할 수 있다.',
        connection: '+ 이런 부분은 여야가 함께 배워야 한다'
    },

    // 3단계: 정중한 인정 + 차이 명시
    LEVEL_3_POLITE: {
        id: 'polite_with_difference',
        name: '3단계: 정중한 인정 + 차이 명시',
        when: '의견은 다르지만 인물·과정은 인정할 때',
        structure: '차이 먼저 → 구체적 인정 → 인격 존중',
        template: '정책 방향은 다르지만, ○○ 의원의 [구체적 행동]은 바람직하다고 본다.'
    },

    // 4단계: 한정적 협력 제안
    LEVEL_4_LIMITED_COOPERATION: {
        id: 'limited_cooperation',
        name: '4단계: 한정적 협력 제안',
        when: '공동 이익이 있을 때만',
        required: '협력 범위를 명확히 한정',
        template: '[특정 사안]만큼은 여야가 함께 논의할 가치가 있다.',
        caution: '"정책 기조의 차이는 남아 있다" 명시 필수'
    }
};

// ============================================================================
// 5단계: 금지 표현 (FORBIDDEN EXPRESSIONS)
// ============================================================================

const FORBIDDEN_EXPRESSIONS = {
    // 자진영 폄하
    SELF_DEPRECATION: {
        phrases: ['우리보다 낫다', '우리보다 훨씬 낫다', '우리는 저렇게 못한다'],
        reason: '지지층 배신 신호',
        alternatives: ['이 부분은 참고할 만하다', '이번 사안은 주목할 필요가 있다']
    },

    // 전면적 동의
    FULL_AGREEMENT: {
        phrases: ['정책이 100% 맞다', '전적으로 동의한다', '전적으로 공감', '완전히 옳다'],
        reason: '입장 혼선',
        alternatives: ['이 부분만큼은 인정할 수 있다', '이번 사안에 한해 공감한다']
    },

    // 과장 극찬
    EXAGGERATED_PRAISE: {
        phrases: ['정치인 중 최고', '유일하게 믿을 수 있다', '가장 훌륭하다', '정말 훌륭하다'],
        reason: '팬덤 자극',
        alternatives: ['이번 행동은 인정할 만하다', '이 점은 참고할 수 있다']
    },

    // 사적 친분 (🔴 후처리에서 삭제하지 않음 - 프롬프트 가이드라인으로만 제공)
    PERSONAL_AFFINITY: {
        phrases: ['개인적으로 좋아한다'],
        reason: '밀실 정치 이미지',
        alternatives: ['정치적 경쟁자이지만', '같은 지역 정치인으로서']
    },

    // 진영 전환
    FACTION_SHIFT: {
        phrases: ['이제 저 당이 맞다', '저쪽으로 가야', '우리 당이 틀렸다'],
        reason: '당내 혼란',
        alternatives: ['정책 방향은 다르지만', '입장 차이가 있지만']
    },

    // 추상적 극찬 (구체성 없음)
    ABSTRACT_PRAISE: {
        phrases: ['정신을 이어받아', '뜻을 받들어', '배워야 합니다', '본받아', '깊은 울림', '용기에 박수', '귀감이 됩니다'],
        reason: '구체적 근거 없는 극찬 금지',
        alternatives: ['이 점은 인정할 수 있다', '이번 행동은 참고할 만하다']
    },

    // 🆕 감정 과잉 표현
    EMOTIONAL_EXCESS: {
        phrases: ['깊이 공감', '절실히 필요', '동력이 될 것', '나침반이 될 것', '큰 울림', '귀감'],
        reason: '과도한 감정 표현',
        alternatives: ['주목할 만하다', '필요하다고 본다', '참고할 수 있다']
    }
};

// 모든 금지 표현을 하나의 배열로
const ALL_FORBIDDEN_PHRASES = Object.values(FORBIDDEN_EXPRESSIONS)
    .flatMap(category => category.phrases);

// ============================================================================
// 생성 템플릿 (GENERATION TEMPLATES)
// ============================================================================

const GENERATION_TEMPLATES = {
    // 템플릿 1: 정책 성과 인정
    POLICY_ACHIEVEMENT: {
        id: 'policy_achievement',
        name: '정책 성과 인정',
        structure: `[차이 인정] 정책 방향은 다를 수 있지만,
[구체적 근거] ○○ 의원이 [구체적 행동/성과]
[존중 표현] 점은 높이 평가한다.
[초당 연결] 이런 부분은 여야가 함께 배워야 한다.`,
        example: '정책 방향은 다를 수 있지만, ○○ 의원이 일 년간 중소상인들을 직접 방문해 현황을 청취하는 모습은 진심으로 인정할 수 있습니다. 이런 현장 중심의 의정활동은 여야가 함께 배워야 한다고 봅니다.'
    },

    // 템플릿 2: 위기 대응·인물 인정
    CRISIS_RESPONSE: {
        id: 'crisis_response',
        name: '위기 대응/인물 인정',
        structure: `[상황] 이번 [사건]에서
[인물 행동] ○○ 시장의 [구체적 행동]은
[절제된 인정] 시민 안전을 우선한 선택이다.
[협력 제안] 이런 부분에서는 정파를 넘어 함께 움직일 가치가 있다.`,
        example: '이번 재난 대응에서 ○○ 시장이 신속하게 현장에 나가 여야 구분 없이 피해자를 챙긴 모습은 시민 안전을 우선한 선택이라고 봅니다. 이런 순간에는 정파를 넘어 함께 움직여야 한다고 생각합니다.'
    },

    // 템플릿 3: 한정적 협력 제안
    LIMITED_COOPERATION: {
        id: 'limited_cooperation',
        name: '한정적 협력 제안',
        structure: `[입장 차이] ○○ 의원과는 [쟁점]에서 입장이 다르지만,
[공동 이익] [국익/민생/안보]에서는
[협력 범위] 이 부분만큼은 함께 논의할 가치가 있다.
[한계 명시] 정책 기조의 차이는 남아 있다.`,
        example: '재정 정책에서는 입장이 다르지만, 국가 채무 투명성 강화 차원에서는 ○○ 의원의 제안을 함께 검토할 가치가 있다고 봅니다. 정책 시행 방식에서는 여전히 입장 차이가 있습니다.'
    },

    // 템플릿 4: 소신 발언 인정 (조경태 케이스)
    PRINCIPLED_STANCE: {
        id: 'principled_stance',
        name: '소신 발언 인정',
        structure: `[상황] 이번 [사안]에서
[인물 행동] ○○ 의원이 [소신 발언/행동]한 점은
[범위 한정] 이 부분만큼은 높이 평가한다.
[자기 PR] 저 또한 이러한 원칙 위에서 [화자의 비전/정책]을 추진한다.`,
        example: '이번 헌정 위기 상황에서 조경태 의원이 당을 넘어 원칙을 지킨 점은 높이 평가합니다. 저 또한 이러한 원칙 위에서 부산의 미래를 위한 정책을 추진하겠습니다.'
    }
};

// ============================================================================
// 검증 체크리스트 (VALIDATION CHECKLIST)
// ============================================================================

const VALIDATION_CHECKLIST = [
    { id: 'fact_based', label: '사실 기반: 구체적 근거가 있고 과장하지 않았는가?' },
    { id: 'scope_clear', label: '범위 명확: "이 부분은", "이번 사안에 한해" 같은 한정 표현이 있는가?' },
    { id: 'no_self_deprecation', label: '자당 비하 없음: 우리 진영을 낮추는 표현이 없는가?' },
    { id: 'no_fandom_trigger', label: '팬덤 자극 없음: "최고", "유일" 같은 과한 극찬이 없는가?' },
    { id: 'neutrality', label: '중립성 유지: 정책 입장의 차이를 명확히 했는가?' },
    { id: 'no_group_insult', label: '집단 비하 없음: 제3자나 직업군을 건드리는 말이 없는가?' }
];

// ============================================================================
// 한국 정치 문화 특수성 (KOREAN POLITICAL CULTURE)
// ============================================================================

const KOREAN_POLITICAL_CONTEXT = `
**한국 정치 문화의 특수성** (LLM 생성 시 반드시 반영):

1. **팬덤 정치의 강력함**: 과한 인물 띄우기는 '정치적 실수'로 읽힘
2. **강성 지지층의 민감도**: 자당 폄하는 '배신'으로 해석될 수 있음
3. **초당적 협력의 실질성**: 추상적 "함께하자"보다 구체적 사안 제시가 중요
4. **현장 중심 평가**: "무엇을 했는가"가 "얼마나 훌륭한가"보다 더 설득력 있음
5. **상위 정체성 활용**: "지역에는 여야가 없다", "국가 이익 우선" 등 활용 가능
`;

// ============================================================================
// 프롬프트 빌더 함수
// ============================================================================

function buildBipartisanCooperationPrompt(options = {}) {
    // 기본값 정의
    const defaults = {
        topic: '',
        targetCount: 1800,
        authorBio: '이재성',
        instructions: '',
        newsContext: '',
        templateId: 'principled_stance',
        toneLevel: 'LEVEL_2_SPECIFIC'
    };

    // 옵션 병합
    const mergedOptions = { ...defaults, ...options };
    const {
        topic,
        targetCount,
        authorBio,
        instructions,
        newsContext,
        templateId,
        toneLevel,
        personalizedHints // 🆕 자기PR 소스 (필수)
    } = mergedOptions;

    // 🔴 Phase 1: 입력값 검증 추가
    if (targetCount < 500 || targetCount > 5000) {
        console.warn(`⚠️ [BipartisanPrompt] targetCount ${targetCount}는 범위(500~5000)를 벗어났습니다. 기본값 1800 사용.`);
    }

    // 템플릿 선택 (경고 로깅 추가)
    const templateKey = templateId.toUpperCase();
    if (!GENERATION_TEMPLATES[templateKey]) {
        console.warn(`⚠️ [BipartisanPrompt] 유효하지 않은 templateId: ${templateId}. 기본값 PRINCIPLED_STANCE 사용.`);
    }
    const template = GENERATION_TEMPLATES[templateKey] || GENERATION_TEMPLATES.PRINCIPLED_STANCE;

    // 톤 레벨 선택 (경고 로깅 추가)
    const toneKey = toneLevel.toUpperCase();
    if (!TONE_LEVELS[toneKey]) {
        console.warn(`⚠️ [BipartisanPrompt] 유효하지 않은 toneLevel: ${toneLevel}. 기본값 LEVEL_2_SPECIFIC 사용.`);
    }
    const tone = TONE_LEVELS[toneKey] || TONE_LEVELS.LEVEL_2_SPECIFIC;

    // 검증된 targetCount 사용
    const validTargetCount = (targetCount >= 500 && targetCount <= 5000) ? targetCount : 1800;

    return `
╔═══════════════════════════════════════════════════════════════╗
║  🤝 [초당적 협력] 타 정당 인사 제한적 인정 템플릿              ║
╚═══════════════════════════════════════════════════════════════╝

🔴🔴🔴 **[최우선 규칙] 경쟁자 칭찬 비중 10-20% 제한** 🔴🔴🔴
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- 경쟁자(조경태 등) 언급은 **최대 ${Math.round(validTargetCount * 0.2)}자** (20%)
- **자기PR이 50% (${Math.round(validTargetCount * 0.5)}자) 이상**이어야 함
- 초과 시 원고 폐기됨
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${KOREAN_POLITICAL_CONTEXT}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 **[절대 금지] 금지 표현 → 대체 표현** (위반 시 원고 폐기)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| ❌ 금지 표현 | ✅ 대체 표현 |
| :--- | :--- |
| "전적으로 동의한다" | "이 부분만큼은 인정할 수 있다" |
| "전적으로 공감한다" | "이번 사안에 한해 공감한다" |
| "본받아야 한다" | "이 점은 참고할 수 있다" |
| "깊이 공감한다" | "이번 발언은 주목할 만하다" |
| "깊은 울림" | "주목할 만한 발언" |
| "용기에 박수" | "원칙을 지킨 점은 인정" |
| "귀감이 됩니다" | "참고할 만합니다" |
| "동력이 될 것" | "긍정적 계기" |
| "나침반이 될 것" | "방향 제시" |
| "충격적인 소식" | "주목할 만한 소식" |
| "마음이 무겁다" | "엄중하게 받아들인다" |
| "안타깝다" | "유감스럽다" |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📢 [윤석열 사태 관련 논리 구조(Logic) 가이드 - CRITICAL]
1. **[인과관계 절대 준수]**:
   - ❌ "사형 구형 소식이 충격적이다/민주주의 위기다" (절대 금지 - 구형을 비판하는 것처럼 읽힘)
   - ✅ "12.3 내란(범죄)이 민주주의 위기였으며, **사형 구형(심판)은 정의의 실현**이다." (구형을 환영해야 함)
   
2. **[감정 배제]**: "안타깝다", "마음이 무겁다", "충격" 등의 표현은 **피해자 코스프레**로 오해받을 수 있으므로 절대 쓰지 마십시오. 오직 **"사필귀정", "엄정한 법의 심판", "당연한 귀결"**로만 표현하십시오.

3. **[용어 통일]**: "전 대통령" 호칭은 유지하되, 예우를 갖추거나 안타까워하는 수식어는 뺍니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 핵심 원칙 3가지
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. **차이 먼저 명시, 인물은 분리**: 정책 방향은 다르지만 인격·행동·노력은 존중
2. **구체성 필수, 추상 극찬 금지**: "정말 훌륭하다"보다 "○○를 지속적으로 제기해 온 점"
3. **초당적 협력으로 연결**: 칭찬 후 바로 공동목표(민생, 안보, 국익)로 이어가기

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 현재 톤 강도: ${tone.name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**사용 시점**: ${tone.when}
**톤 특성**: ${tone.tone || tone.structure || ''}
**템플릿**: ${tone.template}
${tone.caution ? `**주의**: ${tone.caution}` : ''}
${tone.connection ? `**연결**: ${tone.connection}` : ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 [CRITICAL] 5단계 금지 표현 - 위반 시 원고 폐기
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| 유형 | 금지 표현 | 이유 |
| :--- | :--- | :--- |
| 자진영 폄하 | "우리보다 낫다", "우리는 저렇게 못한다" | 지지층 배신 신호 |
| 전면적 동의 | "전적으로 동의/공감", "정책이 100% 맞다" | 입장 혼선 |
| 과장 극찬 | "정치인 중 최고", "유일하게 믿을 수 있다" | 팬덤 자극 |
| 추상 극찬 | "정신을 이어받아", "본받아", "귀감" | 구체성 없음 |
| 감정 과잉 | "깊이 공감", "동력", "나침반", "큰 울림" | 과도한 감정 |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 생성 템플릿: ${template.name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**구조**:
${template.structure}

**예시**:
${template.example}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 올바른 예시 vs ❌ 잘못된 예시
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ **올바른 예시 (경쟁자 인정 150자, 10%)**:
"이번 헌정 위기에서 조경태 의원이 당을 넘어 원칙을 지킨 점만큼은 인정합니다. 
저 또한 이러한 원칙 위에서 부산의 미래를 위한 AI 정책을 추진하겠습니다."
→ 이후 자기PR 900자 (50%) 필수!

❌ **잘못된 예시 (경쟁자 칭찬 800자, 74% - 폐기 대상)**:
"조경태 의원의 용기에 깊이 공감합니다... 본받아야 합니다... 
전적으로 동의합니다... 동력이 될 것입니다..." (장황한 칭찬 800자)
→ 자기PR 300자 (25%) 부족 = 폐기!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 생성 후 검증 체크리스트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

${VALIDATION_CHECKLIST.map(item => `- [ ] ${item.label}`).join('\n')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✍️ 원고 정보
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**주제**: ${topic}
**목표 글자 수**: ${validTargetCount}자
**화자**: ${authorBio}

${instructions ? `**배경/지시**: ${instructions}\n` : ''}
${personalizedHints ? `**[CRITICAL] 자기PR 컨텐츠 소스 (필수 반영)**:\n${personalizedHints}\n` : ''}
${newsContext ? `**참고 뉴스**: ${newsContext.substring(0, 500)}...` : ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 **[필수 준수] 비중 배분 가이드** (2회차 강조)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| 섹션 | 비중 | 글자 수 (${validTargetCount}자 기준) |
| :--- | :--- | :--- |
| 상황 설명 | 15% | ~${Math.round(validTargetCount * 0.15)}자 |
| **경쟁자 인정** | **10-20%** | **최대 ${Math.round(validTargetCount * 0.2)}자** |
| **자기PR/비전** | **50% 이상** | **최소 ${Math.round(validTargetCount * 0.5)}자 (필수!)** |
| 차별화/마무리 | 15-25% | ~${Math.round(validTargetCount * 0.2)}자 |

⚠️ **경쟁자 칭찬 > 20% 또는 자기PR < 50%이면 원고 폐기!**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 **[마지막 확인] 작성 순서** (3회차 강조)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. **자기PR (50%, ${Math.round(validTargetCount * 0.5)}자)** ← 가장 먼저, 가장 많이!
2. 상황 설명 (15%)
3. 차별화/마무리 (15-25%)
4. **경쟁자 인정 (10-20%, 최대 ${Math.round(validTargetCount * 0.2)}자)** ← 마지막에, 짧게!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HTML 형식으로 본문을 작성하세요. <p> 태그로 문단을 구성하세요.
`;
}

// ============================================================================
// 금지 표현 검사 함수
// ============================================================================

function checkForbiddenExpressions(content) {
    const violations = [];

    for (const [category, data] of Object.entries(FORBIDDEN_EXPRESSIONS)) {
        for (const phrase of data.phrases) {
            if (content.includes(phrase)) {
                violations.push({
                    category,
                    phrase,
                    reason: data.reason
                });
            }
        }
    }

    return {
        hasForbidden: violations.length > 0,
        violations
    };
}

// ============================================================================
// 🔴 Phase 1: 정규식 기반 검증 패턴 (VALIDATION_PATTERNS)
// ============================================================================

const VALIDATION_PATTERNS = {
    // 범위 한정 표현 (있으면 좋음)
    scopeLimiters: /이\s?번\s?사안|이\s?부분|만큼은|에\s?한해/g,
    // 초당적 키워드 (최소 2개 이상)
    bipartisanKeywords: /여야|정파|초당|국익|공동|협력/g,
    // 사적 친분 표현 (없어야 함)
    // 🔴 [FIX] "형" 제거 - 사형/구형/금고형/벌금형 등 법률 용어와 충돌
    // LLM이 프롬프트 지시("사적 친분 금지: 형, 누나")를 보고 맥락으로 판단하도록 위임
    personalTone: /누나|친구|동지|개인적으로/g,
    // 최상급 표현 (없어야 함)
    superlatives: /최고|유일|가장|정말\s?훌륭/g,
    // 자당 비하 표현 (없어야 함)
    selfDeprecation: /우리보다|우리는\s?저렇게|우리\s?당이\s?틀/g
};

// ============================================================================
// 🔴 Phase 1: 종합 검증 함수 (validateGeneratedContent)
// ============================================================================

/**
 * 생성된 콘텐츠의 초당적 협력 규칙 준수 여부 종합 검증
 * @param {string} content - 검증할 콘텐츠
 * @returns {Object} 검증 결과
 */
function validateGeneratedContent(content) {
    if (!content || typeof content !== 'string') {
        return {
            passed: false,
            error: '콘텐츠가 비어 있거나 문자열이 아닙니다.',
            forbidden: { hasForbidden: false, violations: [] },
            scopeClarity: false,
            selfDeprecation: false,
            superlatives: 0,
            bipartisanTone: 0,
            personalTone: false
        };
    }

    // 1. 금지 표현 검사
    const forbidden = checkForbiddenExpressions(content);

    // 2. 범위 명확성 (한정 표현 포함 여부)
    const scopeMatches = content.match(VALIDATION_PATTERNS.scopeLimiters) || [];
    const scopeClarity = scopeMatches.length >= 1;

    // 3. 자당 비하 탐지
    const selfDeprecation = VALIDATION_PATTERNS.selfDeprecation.test(content);

    // 4. 최상급 표현 카운트
    const superlativeMatches = content.match(VALIDATION_PATTERNS.superlatives) || [];
    const superlatives = superlativeMatches.length;

    // 5. 초당적 프레임 포함도
    const bipartisanMatches = content.match(VALIDATION_PATTERNS.bipartisanKeywords) || [];
    const bipartisanTone = bipartisanMatches.length;

    // 6. 사적 친분 표현 탐지
    const personalTone = VALIDATION_PATTERNS.personalTone.test(content);

    // 종합 판정
    const issues = [];
    if (forbidden.hasForbidden) {
        issues.push(`금지 표현 ${forbidden.violations.length}개 발견`);
    }
    if (!scopeClarity) {
        issues.push('범위 한정 표현 없음 (예: "이 부분은", "만큼은")');
    }
    if (selfDeprecation) {
        issues.push('자당 비하 표현 감지됨');
    }
    if (superlatives > 0) {
        issues.push(`최상급 표현 ${superlatives}개 감지됨`);
    }
    if (bipartisanTone < 2) {
        issues.push(`초당적 키워드 부족 (${bipartisanTone}개, 최소 2개 권장)`);
    }
    if (personalTone) {
        issues.push('사적 친분 표현 감지됨');
    }

    const passed = !forbidden.hasForbidden && !selfDeprecation && superlatives === 0 && !personalTone;

    return {
        passed,
        issues,
        forbidden,
        scopeClarity,
        selfDeprecation,
        superlatives,
        bipartisanTone,
        personalTone
    };
}

// ============================================================================
// 🔴 Phase 1: 테스트 케이스 (TEST_CASES)
// ============================================================================

const TEST_CASES = [
    {
        name: '조경태 의원 소신 발언 인정',
        options: {
            topic: '헌정 위기와 야당 의원의 소신 발언',
            templateId: 'PRINCIPLED_STANCE',
            toneLevel: 'LEVEL_2_SPECIFIC',
            targetCount: 1200,
            authorBio: '부산 사하을 지역위원장 이재성'
        },
        expectedTemplate: 'PRINCIPLED_STANCE'
    },
    {
        name: '재난 대응 위기 관리',
        options: {
            topic: '부산 폭우 피해와 시장의 신속 대응',
            templateId: 'CRISIS_RESPONSE',
            toneLevel: 'LEVEL_3_POLITE',
            targetCount: 1500
        },
        expectedTemplate: 'CRISIS_RESPONSE'
    },
    {
        name: '정책 협력 제안',
        options: {
            topic: '지역 예산 확보를 위한 초당적 협력',
            templateId: 'LIMITED_COOPERATION',
            toneLevel: 'LEVEL_4_LIMITED_COOPERATION',
            targetCount: 1800
        },
        expectedTemplate: 'LIMITED_COOPERATION'
    },
    {
        name: '정책 성과 인정',
        options: {
            topic: '야당 의원의 중소상인 지원 정책',
            templateId: 'POLICY_ACHIEVEMENT',
            toneLevel: 'LEVEL_1_OBJECTIVE',
            targetCount: 2000
        },
        expectedTemplate: 'POLICY_ACHIEVEMENT'
    }
];

/**
 * 테스트 케이스 실행 (개발용)
 * @returns {Object[]} 테스트 결과
 */
function runTestCases() {
    const results = [];
    for (const testCase of TEST_CASES) {
        try {
            const prompt = buildBipartisanCooperationPrompt(testCase.options);
            const hasExpectedTemplate = prompt.includes(testCase.expectedTemplate) ||
                prompt.includes(GENERATION_TEMPLATES[testCase.expectedTemplate]?.name);
            results.push({
                name: testCase.name,
                passed: !!prompt && prompt.length > 500 && hasExpectedTemplate,
                promptLength: prompt.length
            });
        } catch (error) {
            results.push({
                name: testCase.name,
                passed: false,
                error: error.message
            });
        }
    }
    return results;
}

// ============================================================================
// 사용 예시 (Usage Example)
// ============================================================================

/*
// 기본 사용법
const prompt = buildBipartisanCooperationPrompt({
    topic: '헌정 위기와 조경태 의원 소신 발언',
    targetCount: 1800,
    authorBio: '부산 사하을 지역위원장 이재성',
    templateId: 'PRINCIPLED_STANCE',
    toneLevel: 'LEVEL_2_SPECIFIC'
});

// 생성된 콘텐츠 검증
const validationResult = validateGeneratedContent(generatedContent);
if (!validationResult.passed) {
    console.log('검증 실패:', validationResult.issues);
}

// 테스트 케이스 실행
const testResults = runTestCases();
console.log(testResults);
*/

module.exports = {
    TONE_LEVELS,
    FORBIDDEN_EXPRESSIONS,
    ALL_FORBIDDEN_PHRASES,
    GENERATION_TEMPLATES,
    VALIDATION_CHECKLIST,
    VALIDATION_PATTERNS,
    KOREAN_POLITICAL_CONTEXT,
    TEST_CASES,
    buildBipartisanCooperationPrompt,
    checkForbiddenExpressions,
    validateGeneratedContent,
    runTestCases
};

