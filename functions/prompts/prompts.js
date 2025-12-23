/**
 * functions/prompts/prompts.js
 * 전자두뇌비서관의 메인 프롬프트 라우터(Router)입니다.
 *
 * v4: Guideline Grounding 통합
 * - 상황에 맞는 지침만 선택적으로 주입
 * - Primacy/Recency Effect 기반 배치
 * - Lost in the Middle 문제 해결
 */

'use strict';

// 가이드라인 및 규칙 import
const { SEO_RULES, FORMAT_RULES } = require('./guidelines/editorial');
const { OVERRIDE_KEYWORDS, HIGH_RISK_KEYWORDS, POLITICAL_FRAMES } = require('./guidelines/framingRules');
const { generateNonLawmakerWarning, generateFamilyStatusWarning } = require('./utils/non-lawmaker-warning');

// [신규] Guideline Grounding
const { buildGroundedGuidelines } = require('../services/guidelines/grounding');

// 작법별 프롬프트 빌더 모듈 import
const { buildDailyCommunicationPrompt } = require('./templates/daily-communication');
const { buildLogicalWritingPrompt } = require('./templates/policy-proposal');
const { buildActivityReportPrompt } = require('./templates/activity-report');
const { buildCriticalWritingPrompt } = require('./templates/current-affairs');
const { buildLocalIssuesPrompt } = require('./templates/local-issues');

// ============================================================================
// 지능적 프레이밍 에이전트
// ============================================================================

function analyzeAndSelectFrame(topic) {
  if (!topic) return null;
  const isOverridden = Object.values(OVERRIDE_KEYWORDS).flat().some(keyword => topic.includes(keyword));
  if (isOverridden) return null;
  const isSelfCriticism = HIGH_RISK_KEYWORDS.SELF_CRITICISM.some(keyword => topic.includes(keyword));
  if (isSelfCriticism) return POLITICAL_FRAMES.CONSTRUCTIVE_CRITICISM;
  return null;
}

function applyFramingToPrompt(basePrompt, frame) {
  if (!frame) return basePrompt;
  return `${frame.promptInjection}\n\n---\n\n${basePrompt}`;
}

// ============================================================================
// 카테고리 → writingMethod 매핑
// ============================================================================

function getWritingMethodFromCategory(category) {
  const mapping = {
    'daily': 'emotional_writing',
    'activity': 'direct_writing',
    'policy': 'logical_writing',
    'current': 'critical_writing',
    'local': 'analytical_writing'
  };
  return mapping[category] || 'emotional_writing';
}

// ============================================================================
// 통합 프롬프트 빌더 (v4 - Guideline Grounding)
// ============================================================================

async function buildSmartPrompt(options) {
  try {
    const {
      writingMethod,
      topic,
      status,
      keywords = [],
      targetWordCount = 2050
    } = options;

    // 1. [라우팅] 작법별 템플릿 프롬프트 생성
    let templatePrompt;
    switch (writingMethod) {
      case 'emotional_writing':
        templatePrompt = buildDailyCommunicationPrompt(options);
        break;
      case 'logical_writing':
        templatePrompt = buildLogicalWritingPrompt(options);
        break;
      case 'direct_writing':
        templatePrompt = buildActivityReportPrompt(options);
        break;
      case 'critical_writing':
        templatePrompt = buildCriticalWritingPrompt(options);
        break;
      case 'analytical_writing':
        templatePrompt = buildLocalIssuesPrompt(options);
        break;
      default:
        console.warn(`알 수 없는 작법: ${writingMethod}. 기본 작법으로 대체합니다.`);
        templatePrompt = buildDailyCommunicationPrompt(options);
        break;
    }

    // 2. [원외 인사 경고] 공통 적용
    const nonLawmakerWarning = generateNonLawmakerWarning({
      isCurrentLawmaker: options.isCurrentLawmaker,
      politicalExperience: options.politicalExperience,
      authorBio: options.authorBio
    });

    if (nonLawmakerWarning) {
      templatePrompt = nonLawmakerWarning + '\n\n' + templatePrompt;
    }

    // 3. [가족 상황 경고] 공통 적용 (자녀 환각 방지)
    const familyWarning = generateFamilyStatusWarning({
      familyStatus: options.familyStatus
    });

    if (familyWarning) {
      templatePrompt = familyWarning + '\n\n' + templatePrompt;
    }

    // 3.5. [타 지역 주제 경고] 공통 적용 ("우리 지역" 표현 오용 방지)
    if (options.regionHint) {
      templatePrompt = options.regionHint + '\n\n' + templatePrompt;
      console.log('🗺️ 타 지역 관점 지시 주입됨');
    }

    // 4. [Guideline Grounding] 상황에 맞는 지침 선택 및 배치
    const category = getWritingMethodFromCategory(options.category) || writingMethod;
    const { prefix, suffix, reminder, stats } = buildGroundedGuidelines({
      status,
      category,
      writingMethod,
      topic,
      keywords,
      targetWordCount
    });

    // 5. [프롬프트 조립] Primacy/Recency Effect 적용
    // 구조: prefix(CRITICAL) → 템플릿 → suffix(HIGH/SEO) → reminder(체크리스트)
    let assembledPrompt = '';

    // 5.1 시작: CRITICAL 지침 (Primacy Effect)
    assembledPrompt += prefix;

    // 5.2 중간: 템플릿 본문
    assembledPrompt += '\n' + templatePrompt + '\n';

    // 5.3 후반: HIGH/SEO 지침
    assembledPrompt += suffix;

    // 5.4 Editorial 규칙 (필요시)
    if (options.applyEditorialRules) {
      assembledPrompt = injectEditorialRules(assembledPrompt, options);
    }

    // 6. [프레이밍] 지능적 프레이밍 적용
    const selectedFrame = analyzeAndSelectFrame(topic);
    const framedPrompt = applyFramingToPrompt(assembledPrompt, selectedFrame);

    // 7. [끝] 리마인더 (Recency Effect)
    const finalPrompt = framedPrompt + reminder;

    console.log('✅ buildSmartPrompt v4 완료:', {
      writingMethod,
      status,
      keywordCount: keywords.length,
      guidelinesApplied: stats,
      promptLength: finalPrompt.length,
      framingApplied: selectedFrame ? selectedFrame.id : 'None'
    });

    return finalPrompt;

  } catch (error) {
    console.error('❌ buildSmartPrompt 오류:', error);
    // Fallback: 기존 방식으로 생성
    return buildSmartPromptLegacy(options);
  }
}

// ============================================================================
// Legacy 프롬프트 빌더 (Fallback용)
// ============================================================================

const { getElectionStage } = require('./guidelines/legal');
const { buildSEOInstruction, buildAntiRepetitionInstruction } = require('./guidelines/seo');

function injectElectionLawCompliance(basePrompt, status) {
  if (!status) return basePrompt;

  const electionStage = getElectionStage(status);
  if (!electionStage || !electionStage.promptInstruction) {
    return basePrompt;
  }

  if (electionStage.name === 'STAGE_1') {
    const enhancedInstruction = `
╔═══════════════════════════════════════════════════════════════╗
║  ⚖️ [선거법 준수 - 최우선 원칙] ⚖️                            ║
╚═══════════════════════════════════════════════════════════════╝

**현재 상태: ${status} (예비후보 등록 이전)**

${electionStage.promptInstruction}

** 추가 주의사항 - 공약성 어미 금지 **
다음과 같은 "~하겠습니다" 형태의 공약성 어미는 사용 금지:
❌ 추진하겠습니다, 실현하겠습니다, 만들겠습니다, 해내겠습니다
❌ 전개하겠습니다, 제공하겠습니다, 활성화하겠습니다
❌ 개선하겠습니다, 확대하겠습니다, 강화하겠습니다
❌ 설립하겠습니다, 구축하겠습니다, 마련하겠습니다
❌ 지원하겠습니다, 해결하겠습니다, 바꾸겠습니다

✅ 대신 사용할 표현:
"~이 필요합니다", "~을 제안합니다", "~을 연구하고 있습니다"
"~을 위해 노력 중입니다", "~에 대해 논의하고 있습니다"

---

`;
    return enhancedInstruction + basePrompt;
  }

  return `${electionStage.promptInstruction}\n\n---\n\n${basePrompt}`;
}

function injectUniversalQualityRules(basePrompt) {
  const qualityRules = `

╔═══════════════════════════════════════════════════════════════╗
║  ⛔ [치명적 오류 방지 가이드] - 위반 시 생성 실패로 간주됨  ⛔  ║
╚═══════════════════════════════════════════════════════════════╝

다음 3가지 오류는 절대 발생해서는 안 됩니다. 출력 전 반드시 스스로 검증하세요.

1. **구조 오류 (Endless Loop Prohibition)**
   - 마무리 인사("감사합니다", "사랑합니다" 등) 이후에 본문 내용이 다시 시작되면 안 됩니다.
   - 글의 맺음말이 나오면 거기서 즉시 종료하세요.

2. **문단 반복 (No Repetition)**
   - 같은 내용, 같은 공약, 같은 비전 제시를 '표현만 바꾸어' 반복하는 것을 금지합니다.
   - 1문단 1메시지 원칙: 새로운 문단은 반드시 새로운 정보를 담아야 합니다.

3. **문장 완결성 (Completeness)**
   - 문장이 중간에 끊기지 않도록 하세요.
   - 모든 문장은 "~입니다", "~하겠습니다" 등으로 명확히 종결되어야 합니다.

---

`;

  return qualityRules + basePrompt;
}

async function buildSmartPromptLegacy(options) {
  console.warn('⚠️ Guideline Grounding 실패 - Legacy 방식으로 Fallback');

  const { writingMethod, topic, status } = options;
  let generatedPrompt;

  switch (writingMethod) {
    case 'emotional_writing':
      generatedPrompt = buildDailyCommunicationPrompt(options);
      break;
    case 'logical_writing':
      generatedPrompt = buildLogicalWritingPrompt(options);
      break;
    case 'direct_writing':
      generatedPrompt = buildActivityReportPrompt(options);
      break;
    case 'critical_writing':
      generatedPrompt = buildCriticalWritingPrompt(options);
      break;
    case 'analytical_writing':
      generatedPrompt = buildLocalIssuesPrompt(options);
      break;
    default:
      generatedPrompt = buildDailyCommunicationPrompt(options);
      break;
  }

  const nonLawmakerWarning = generateNonLawmakerWarning({
    isCurrentLawmaker: options.isCurrentLawmaker,
    politicalExperience: options.politicalExperience,
    authorBio: options.authorBio
  });

  if (nonLawmakerWarning) {
    generatedPrompt = nonLawmakerWarning + '\n\n' + generatedPrompt;
  }

  const familyWarning = generateFamilyStatusWarning({
    familyStatus: options.familyStatus
  });

  if (familyWarning) {
    generatedPrompt = familyWarning + '\n\n' + generatedPrompt;
  }

  const electionCompliantPrompt = injectElectionLawCompliance(generatedPrompt, status);
  const qualityEnhancedPrompt = injectUniversalQualityRules(electionCompliantPrompt);

  const selectedFrame = analyzeAndSelectFrame(topic);
  const framedPrompt = applyFramingToPrompt(qualityEnhancedPrompt, selectedFrame);

  const editorialPrompt = options.applyEditorialRules
    ? injectEditorialRules(framedPrompt, options)
    : framedPrompt;

  const seoInstruction = buildSEOInstruction({
    keywords: options.keywords,
    targetWordCount: options.targetWordCount
  });
  const antiRepetitionInstruction = buildAntiRepetitionInstruction();

  return seoInstruction + antiRepetitionInstruction + editorialPrompt;
}

// ============================================================================
// Editorial 규칙 주입기
// ============================================================================

function injectEditorialRules(basePrompt, options) {
  const seoSection = `
[🎯 SEO 최적화 규칙 (editorial.js 적용)]
- **필수 분량**: ${SEO_RULES.wordCount.min}~${SEO_RULES.wordCount.max}자 (목표: ${SEO_RULES.wordCount.target}자)`;

  const formatSection = `
[📝 출력 형식 (editorial.js 적용)]
- **출력 구조**: 제목(title), 본문(content)을 포함한 JSON 형식으로 출력
- **HTML 가이드라인**: ${FORMAT_RULES.htmlGuidelines.structure.join(', ')}

[🔍 품질 검증 필수사항]
- 문장 완결성: 모든 문장이 완전한 구조를 갖추고 있는지 확인
- 조사/어미 검증: "주민여하여", "주민소리에" 같은 조사 누락 절대 금지
- 구체성 확보: 괄호 안 예시가 아닌 실제 구체적 내용으로 작성
- 논리적 연결: 도입-전개-결론의 자연스러운 흐름 구성
- 문체 일관성: 존댓말 통일 및 어색한 표현 제거`;

  return basePrompt
    .replace(/(\[📊 SEO 최적화 규칙\])/g, seoSection)
    .replace(/(\[📝 출력 형식\])/g, formatSection);
}

// ============================================================================
// 내보내기
// ============================================================================

module.exports = {
  buildSmartPrompt,
  // Legacy 함수들도 export (다른 모듈에서 사용할 경우)
  buildSmartPromptLegacy,
  injectElectionLawCompliance,
  injectUniversalQualityRules
};
