/**
 * functions/prompts/templates/intelligent-selector.js
 * 주제와 카테고리를 분석하여 최적의 프롬프트 파라미터를 자동 선택합니다.
 */

'use strict';

// 각 카테고리별 프롬프트 모듈의 ID 상수들을 import
const { EMOTIONAL_ARCHETYPES, NARRATIVE_FRAMES, VOCABULARY_MODULES: DAILY_VOCAB } = require('./daily-communication');
const { DECLARATIVE_STRUCTURES, RHETORICAL_TACTICS, VOCABULARY_MODULES: ACTIVITY_VOCAB } = require('./activity-report');
const { LOGICAL_STRUCTURES, ARGUMENTATION_TACTICS, VOCABULARY_MODULES: POLICY_VOCAB } = require('./policy-proposal');
const { CRITICAL_STRUCTURES, OFFENSIVE_TACTICS, VOCABULARY_MODULES: AFFAIRS_VOCAB } = require('./current-affairs');
const { ANALYTICAL_STRUCTURES, EXPLANATORY_TACTICS, VOCABULARY_MODULES: LOCAL_VOCAB } = require('./local-issues');

// ============================================================================
// 일상 소통형 (daily-communication) 지능형 선택기
// ============================================================================

/**
 * 주제를 분석하여 최적의 감정 원형(Emotional Archetype)을 선택합니다.
 */
function selectEmotionalArchetype(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 호소와 탄원형 - 도움 요청, 사과, 지지 요청
  if (text.match(/도와|지지|응원|함께|힘|부탁|죄송|미안|반성|성찰/)) {
    return EMOTIONAL_ARCHETYPES.PLEA_AND_PETITION.id;
  }

  // 2. 사연 설득형 - 구체적인 사람 이야기, 현장 이야기
  if (text.match(/만났습니다|들었습니다|사연|이야기|주민|상인|학부모|어르신|청년|아이|가족/)) {
    return EMOTIONAL_ARCHETYPES.STORYTELLING_PERSUASION.id;
  }

  // 3. 공동체 정서 호명형 - 우리, 함께, 연대
  if (text.match(/우리|함께|모두|다함께|연대|단결|화합|하나|공동체/)) {
    return EMOTIONAL_ARCHETYPES.COMMUNITY_APPEAL.id;
  }

  // 4. 시적 서정형 - 계절, 자연, 감성적 표현
  if (text.match(/봄|여름|가을|겨울|꽃|나무|하늘|바람|비|눈|아침|저녁|밤|별|달/)) {
    return EMOTIONAL_ARCHETYPES.POETIC_LYRICISM.id;
  }

  // 5. 감정 해석형 - 감정 표현 키워드
  if (text.match(/분노|억울|슬픔|기쁨|희망|두려움|불안|걱정|안타까움|기대/)) {
    return EMOTIONAL_ARCHETYPES.EMOTIONAL_INTERPRETATION.id;
  }

  // 6. 기본값: 개인 서사형
  return EMOTIONAL_ARCHETYPES.PERSONAL_NARRATIVE.id;
}

/**
 * 주제를 분석하여 최적의 서사 프레임(Narrative Frame)을 선택합니다.
 */
function selectNarrativeFrame(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 청년 세대 대표 서사
  if (text.match(/청년|젊은|20대|30대|청춘|미래세대|다음세대/)) {
    return NARRATIVE_FRAMES.YOUTH_REPRESENTATIVE.id;
  }

  // 2. 고난 극복 서사
  if (text.match(/어려움|힘들|고난|역경|극복|이겨내|헤쳐나가|도전|시련/)) {
    return NARRATIVE_FRAMES.OVERCOMING_HARDSHIP.id;
  }

  // 3. 강인한 투사 서사
  if (text.match(/투쟁|싸움|맞서|저항|개혁|변화|바꾸|혁신|불의|부조리|특권|기득권/)) {
    return NARRATIVE_FRAMES.RELENTLESS_FIGHTER.id;
  }

  // 4. 기본값: 서민의 동반자 서사
  return NARRATIVE_FRAMES.SERVANT_LEADER.id;
}

/**
 * 주제를 분석하여 최적의 어휘 모듈을 선택합니다.
 */
function selectDailyVocabulary(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 진정성과 호소
  if (text.match(/죄송|미안|부족|반성|도와|지지|응원|함께해|힘/)) {
    return DAILY_VOCAB.SINCERITY_AND_APPEAL.id;
  }

  // 2. 책임과 약속
  if (text.match(/약속|책임|다짐|반드시|꼭|결단|의지|실천|지키겠/)) {
    return DAILY_VOCAB.RESPONSIBILITY_AND_PLEDGE.id;
  }

  // 3. 개혁과 투쟁
  if (text.match(/개혁|변화|투쟁|싸움|맞서|저항|바꾸|혁신|특권|기득권|불의|부조리/)) {
    return DAILY_VOCAB.REFORM_AND_STRUGGLE.id;
  }

  // 4. 고난과 가족
  if (text.match(/가족|어머니|아버지|부모|자식|어려움|힘들|고난|극복|헌신|희생/)) {
    return DAILY_VOCAB.HARDSHIP_AND_FAMILY.id;
  }

  // 5. 기본값: 연대와 서민
  return DAILY_VOCAB.SOLIDARITY_AND_PEOPLE.id;
}

// ============================================================================
// 활동 보고형 (activity-report) 지능형 선택기
// ============================================================================

function selectDeclarativeStructure(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 입법 활동 보고
  if (text.match(/조례|법안|개정|발의|통과|입법|법률|조항/)) {
    return DECLARATIVE_STRUCTURES.LEGISLATIVE_REPORT.id;
  }

  // 2. 예산 확보 보고
  if (text.match(/예산|확보|배정|억원|조원|만원|사업비|재원|지원금/)) {
    return DECLARATIVE_STRUCTURES.BUDGET_REPORT.id;
  }

  // 3. 성과 중심 보고
  if (text.match(/성과|결과|해냈습니다|이뤘습니다|완료|달성|실현|결실/)) {
    return DECLARATIVE_STRUCTURES.PERFORMANCE_SHOWCASE_REPORT.id;
  }

  // 4. 의정활동 원칙 선언
  if (text.match(/원칙|철학|신념|가치|소신|믿음|지향/)) {
    return DECLARATIVE_STRUCTURES.PRINCIPLE_DECLARATION.id;
  }

  // 5. 기본값: 일반 의정활동 보고
  return DECLARATIVE_STRUCTURES.GENERAL_ACTIVITY_REPORT.id;
}

function selectRhetoricalTactic(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 주민 약속 강조
  if (text.match(/약속|다짐|반드시|꼭|실천|지키겠습니다/)) {
    return RHETORICAL_TACTICS.PLEDGE_EMPHASIS.id;
  }

  // 2. 성과 귀속 및 강조
  if (text.match(/해냈습니다|이뤘습니다|성과|결실|완료|달성/)) {
    return RHETORICAL_TACTICS.CREDIT_TAKING.id;
  }

  // 3. 주민 생활 연결
  if (text.match(/주민|시민|이웃|우리 동네|아이들|어르신|가족|생활|일상/)) {
    return RHETORICAL_TACTICS.RELATING_TO_RESIDENTS.id;
  }

  // 4. 기본값: 사실과 근거 제시
  return RHETORICAL_TACTICS.FACTS_AND_EVIDENCE.id;
}

function selectActivityVocabulary(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 단호하고 확고한 어휘
  if (text.match(/반드시|원칙|책임|결단|약속|확고/)) {
    return ACTIVITY_VOCAB.RESOLUTE_AND_FIRM.id;
  }

  // 2. 지역/공동체 어휘
  if (text.match(/지역|동네|골목|마을|공동체|이웃|주민/)) {
    return ACTIVITY_VOCAB.LOCAL_AND_COMMUNITY.id;
  }

  // 3. 신뢰/유능함 어휘
  if (text.match(/성과|해결|추진|확보|성공|개선|결실|이뤄냈/)) {
    return ACTIVITY_VOCAB.RELIABLE_AND_COMPETENT.id;
  }

  // 4. 기본값: 공식/보고 어휘
  return ACTIVITY_VOCAB.FORMAL_AND_REPORTING.id;
}

// ============================================================================
// 정책 제안형 (policy-proposal) 지능형 선택기
// ============================================================================

function selectLogicalStructure(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 비교 우위 구조
  if (text.match(/타지역|다른 지역|비교|우리는|우리 지역은|반면/)) {
    return LOGICAL_STRUCTURES.COMPARATIVE_ADVANTAGE.id;
  }

  // 2. 단계별 로드맵 구조
  if (text.match(/단계|1단계|2단계|로드맵|계획|일정|순서대로|먼저|다음|마지막/)) {
    return LOGICAL_STRUCTURES.STEP_BY_STEP_ROADMAP.id;
  }

  // 3. 원인-결과 구조
  if (text.match(/원인|이유|때문에|결과|따라서|그래서|그러므로/)) {
    return LOGICAL_STRUCTURES.CAUSE_AND_EFFECT.id;
  }

  // 4. 기본값: 문제-해결 구조
  return LOGICAL_STRUCTURES.PROBLEM_SOLUTION.id;
}

function selectArgumentationTactic(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 기대효과 강조
  if (text.match(/효과|변화|개선|긍정|혜택|도움|이익/)) {
    return ARGUMENTATION_TACTICS.BENEFIT_EMPHASIS.id;
  }

  // 2. 유추 기반 논증
  if (text.match(/과거|역사|사례|비슷|마찬가지|다른|선진국/)) {
    return ARGUMENTATION_TACTICS.ANALOGY.id;
  }

  // 3. 기본값: 사례 및 데이터 인용
  return ARGUMENTATION_TACTICS.EVIDENCE_CITATION.id;
}

function selectPolicyVocabulary(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 비전과 희망 어휘
  if (text.match(/미래|희망|비전|꿈|새로운|발전/)) {
    return POLICY_VOCAB.VISION_AND_HOPE.id;
  }

  // 2. 행동 촉구 어휘
  if (text.match(/행동|동참|참여|함께|지금|바로|나섭시다/)) {
    return POLICY_VOCAB.ACTION_URGING.id;
  }

  // 3. 정책 분석 어휘
  if (text.match(/분석|통계|데이터|체계|합리|장기적/)) {
    return POLICY_VOCAB.POLICY_ANALYSIS.id;
  }

  // 4. 기본값: 합리적 설득 어휘
  return POLICY_VOCAB.RATIONAL_PERSUASION.id;
}

// ============================================================================
// 시사 비평형 (current-affairs) 지능형 선택기
// ============================================================================

function selectCriticalStructure(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 문제 고발 구조
  if (text.match(/문제|심각|우려|위험|부정|비리|특혜|부당|불법/)) {
    return CRITICAL_STRUCTURES.EXPOSE_PROBLEM.id;
  }

  // 2. 양면 분석 구조
  if (text.match(/장점|단점|긍정|부정|한편|반면|그러나|하지만/)) {
    return CRITICAL_STRUCTURES.TWO_SIDED_ANALYSIS.id;
  }

  // 3. 역사적 맥락 구조
  if (text.match(/역사|과거|전통|유래|~년|~시대|당시|그때/)) {
    return CRITICAL_STRUCTURES.HISTORICAL_CONTEXT.id;
  }

  // 4. 기본값: 현상 진단 구조
  return CRITICAL_STRUCTURES.DIAGNOSE_CURRENT_SITUATION.id;
}

function selectOffensiveTactic(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 대안 제시
  if (text.match(/대안|방안|해법|해결책|제안|개선|바꿔야/)) {
    return OFFENSIVE_TACTICS.ALTERNATIVE_PROPOSAL.id;
  }

  // 2. 모순 지적
  if (text.match(/모순|말과 행동|겉과 속|이중|다르다|불일치/)) {
    return OFFENSIVE_TACTICS.EXPOSING_CONTRADICTION.id;
  }

  // 3. 기본값: 심층 질문 제기
  return OFFENSIVE_TACTICS.DEEP_QUESTIONING.id;
}

function selectAffairsVocabulary(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 비판과 경고 어휘
  if (text.match(/문제|심각|우려|위험|경고|비판|부정|잘못/)) {
    return AFFAIRS_VOCAB.CRITICAL_AND_WARNING.id;
  }

  // 2. 객관적 분석 어휘
  if (text.match(/분석|평가|진단|고찰|검토|판단|추정/)) {
    return AFFAIRS_VOCAB.OBJECTIVE_ANALYSIS.id;
  }

  // 3. 기본값: 시의성과 화두 어휘
  return AFFAIRS_VOCAB.TIMELINESS_AND_AGENDA.id;
}

// ============================================================================
// 지역 현안형 (local-issues) 지능형 선택기
// ============================================================================

function selectAnalyticalStructure(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 현장 르포 구조
  if (text.match(/현장|방문|직접|둘러|다녀왔습니다|가보니|찾아가/)) {
    return ANALYTICAL_STRUCTURES.FIELD_REPORTAGE.id;
  }

  // 2. 비교 분석 구조
  if (text.match(/타지역|다른|비교|우리는|반면|차이|격차/)) {
    return ANALYTICAL_STRUCTURES.COMPARATIVE_ANALYSIS.id;
  }

  // 3. 지역 역사 구조
  if (text.match(/역사|전통|과거|옛날|유래|~년|~시대/)) {
    return ANALYTICAL_STRUCTURES.LOCAL_HISTORY.id;
  }

  // 4. 기본값: 지역 문제 진단 구조
  return ANALYTICAL_STRUCTURES.LOCAL_PROBLEM_DIAGNOSIS.id;
}

function selectExplanatoryTactic(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 주민 의견 수렴
  if (text.match(/주민|의견|목소리|요구|바람|민원|건의|청원/)) {
    return EXPLANATORY_TACTICS.RESIDENT_VOICES.id;
  }

  // 2. 사실과 수치
  if (text.match(/통계|수치|순위|비율|퍼센트|위|명|건|억원|데이터/)) {
    return EXPLANATORY_TACTICS.FACTS_AND_FIGURES.id;
  }

  // 3. 기본값: 현장 관찰
  return EXPLANATORY_TACTICS.FIELD_OBSERVATION.id;
}

function selectLocalVocabulary(topic, instructions) {
  const text = `${topic} ${instructions || ''}`.toLowerCase();

  // 1. 애정과 자부심 어휘
  if (text.match(/자랑|긍지|소중|아름다운|훌륭|특별|유일/)) {
    return LOCAL_VOCAB.AFFECTION_AND_PRIDE.id;
  }

  // 2. 위기와 절박함 어휘
  if (text.match(/위기|심각|급박|시급|절박|당장|더이상|한계/)) {
    return LOCAL_VOCAB.CRISIS_AND_URGENCY.id;
  }

  // 3. 기본값: 구체성과 현장성 어휘
  return LOCAL_VOCAB.SPECIFICITY_AND_FIELDWORK.id;
}

// ============================================================================
// 통합 선택 함수 (Main Entry Point)
// ============================================================================

/**
 * 카테고리와 주제를 분석하여 최적의 프롬프트 파라미터를 자동 선택합니다.
 * @param {string} category - 원고 카테고리 ('daily-communication', 'activity-report', etc.)
 * @param {string} topic - 원고 주제
 * @param {string} instructions - 배경 정보 (선택사항)
 * @returns {Object} 선택된 파라미터 객체
 */
function selectPromptParameters(category, topic, instructions = '') {
  console.log(`🎯 지능형 파라미터 선택 시작 - 카테고리: ${category}, 주제: ${topic.substring(0, 50)}...`);

  let selectedParams = {};

  switch (category) {
    case 'daily-communication':
      selectedParams = {
        emotionalArchetypeId: selectEmotionalArchetype(topic, instructions),
        narrativeFrameId: selectNarrativeFrame(topic, instructions),
        vocabularyModuleId: selectDailyVocabulary(topic, instructions)
      };
      break;

    case 'activity-report':
      selectedParams = {
        declarativeStructureId: selectDeclarativeStructure(topic, instructions),
        rhetoricalTacticId: selectRhetoricalTactic(topic, instructions),
        vocabularyModuleId: selectActivityVocabulary(topic, instructions)
      };
      break;

    case 'policy-proposal':
      selectedParams = {
        logicalStructureId: selectLogicalStructure(topic, instructions),
        argumentationTacticId: selectArgumentationTactic(topic, instructions),
        vocabularyModuleId: selectPolicyVocabulary(topic, instructions)
      };
      break;

    case 'current-affairs':
      selectedParams = {
        criticalStructureId: selectCriticalStructure(topic, instructions),
        offensiveTacticId: selectOffensiveTactic(topic, instructions),
        vocabularyModuleId: selectAffairsVocabulary(topic, instructions)
      };
      break;

    case 'local-issues':
      selectedParams = {
        analyticalStructureId: selectAnalyticalStructure(topic, instructions),
        explanatoryTacticId: selectExplanatoryTactic(topic, instructions),
        vocabularyModuleId: selectLocalVocabulary(topic, instructions)
      };
      break;

    default:
      console.warn(`⚠️ 알 수 없는 카테고리: ${category}, 기본 파라미터 사용`);
      selectedParams = {
        emotionalArchetypeId: EMOTIONAL_ARCHETYPES.PERSONAL_NARRATIVE.id,
        narrativeFrameId: NARRATIVE_FRAMES.SERVANT_LEADER.id,
        vocabularyModuleId: DAILY_VOCAB.SOLIDARITY_AND_PEOPLE.id
      };
  }

  console.log(`✅ 파라미터 선택 완료:`, selectedParams);
  return selectedParams;
}

module.exports = {
  selectPromptParameters
};
