/**
 * functions/prompts/prompts.js
 * 전자두뇌비서관의 메인 프롬프트 라우터(Router)입니다.
 * 사용자의 요청에 따라 적절한 작법 모듈을 호출하고,
 * '지능적 프레이밍'과 'editorial' 규칙을 적용하여 최종 프롬프트를 완성합니다.
 */

'use strict';

// 가이드라인 및 규칙 import
const { SEO_RULES, FORMAT_RULES } = require('./guidelines/editorial');
const { OVERRIDE_KEYWORDS, HIGH_RISK_KEYWORDS, POLITICAL_FRAMES } = require('./guidelines/framingRules');
const { generateNonLawmakerWarning, generateFamilyStatusWarning } = require('./utils/non-lawmaker-warning');
const { getElectionStage } = require('./guidelines/legal');
const { buildSEOInstruction, buildAntiRepetitionInstruction } = require('./guidelines/seo');

// [신규] 작법별 프롬프트 빌더 모듈 import
const { buildDailyCommunicationPrompt } = require('./templates/daily-communication');
const { buildLogicalWritingPrompt } = require('./templates/policy-proposal');
const { buildActivityReportPrompt } = require('./templates/activity-report');
const { buildCriticalWritingPrompt } = require('./templates/current-affairs');
const { buildLocalIssuesPrompt } = require('./templates/local-issues');

// ============================================================================
// 지능적 프레이밍 에이전트 (누락되었던 부분 복구)
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
// 선거법 준수 지침 주입기
// ============================================================================

/**
 * 사용자 상태에 따른 선거법 준수 지침을 프롬프트에 주입
 * @param {string} basePrompt - 기본 프롬프트
 * @param {string} status - 사용자 상태 (준비/현역/예비/후보)
 * @returns {string} 선거법 준수 지침이 추가된 프롬프트
 */
function injectElectionLawCompliance(basePrompt, status) {
  if (!status) return basePrompt;

  const electionStage = getElectionStage(status);
  if (!electionStage || !electionStage.promptInstruction) {
    return basePrompt;
  }

  // 준비/현역 단계에서는 공약성 표현 금지 강화
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

  // 다른 단계는 기본 지침만 주입
  return `${electionStage.promptInstruction}\n\n---\n\n${basePrompt}`;
}

// ============================================================================
// 공통 품질 규칙 주입기 (강화됨)
// ============================================================================

/**
 * 모든 템플릿에 공통으로 적용되는 품질 규칙
 * @param {string} basePrompt - 기본 프롬프트
 * @returns {string} 품질 규칙이 추가된 프롬프트
 */
function injectUniversalQualityRules(basePrompt) {
  const qualityRules = `

╔═══════════════════════════════════════════════════════════════╗
║  ⛔ [치명적 오류 방지 가이드] - 위반 시 생성 실패로 간주됨  ⛔  ║
╚═══════════════════════════════════════════════════════════════╝

다음 3가지 오류는 절대 발생해서는 안 됩니다. 출력 전 반드시 스스로 검증하세요.

1. **구조 오류 (Endless Loop Prohibition)**
   - 마무리 인사("감사합니다", "사랑합니다" 등) 이후에 본문 내용이 다시 시작되면 안 됩니다.
   - 글의 맺음말이 나오면 거기서 즉시 종료하세요.
   - JSON의 content 필드 내에서 글을 완벽히 끝맺으세요.

2. **문단 반복 (No Repetition)**
   - 같은 내용, 같은 공약, 같은 비전 제시를 '표현만 바꾸어' 반복하는 것을 금지합니다.
   - 1문단 1메시지 원칙: 새로운 문단은 반드시 새로운 정보를 담아야 합니다.
   - 할 말이 없다고 해서 앞의 내용을 요약하며 분량을 늘리지 마세요. 차라리 짧게 끝내세요.

3. **문장 완결성 (Completeness)**
   - 문장이 중간에 끊기지 않도록 하세요. (예: "주민 여러분과 함께")
   - 모든 문장은 "~입니다", "~하겠습니다" 등으로 명확히 종결되어야 합니다.

---

╔═══════════════════════════════════════════════════════════════╗
║  ✅ 필수 품질 규칙 - 모든 원고에 공통 적용                   ║
╚═══════════════════════════════════════════════════════════════╝

0. **내용 우선 원칙 (최우선)**
   - 분량보다 내용의 충실도가 우선입니다.
   - 추상적 표현("노력", "최선", "중요") 대신 구체적 정보(숫자, 날짜, 사례)를 포함하세요.

1. **구조 일관성**
   - JSON 형식으로 출력할 때, content 필드는 단 하나만 존재해야 합니다.

2. **JSON 출력 형식 준수**
   - 응답은 반드시 유효한 JSON 포맷이어야 합니다.
   - 마크다운 코드 블록(\`\`\`json ... \`\`\`) 안에 감싸서 출력하세요.

---

`;

  return qualityRules + basePrompt;
}

// ============================================================================
// 통합 프롬프트 빌더 (v3 - Router)
// ============================================================================

async function buildSmartPrompt(options) {
  try {
    const { writingMethod, topic, status } = options;
    let generatedPrompt;

    // 1. [라우팅] 사용자가 선택한 작법(writingMethod)에 따라 적절한 빌더 호출
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
        console.warn(`알 수 없는 작법: ${writingMethod}. 기본 작법으로 대체합니다.`);
        generatedPrompt = buildDailyCommunicationPrompt(options);
        break;
    }

    // 2. [원외 인사 경고] 공통 적용
    const nonLawmakerWarning = generateNonLawmakerWarning({
      isCurrentLawmaker: options.isCurrentLawmaker,
      politicalExperience: options.politicalExperience,
      authorBio: options.authorBio
    });

    if (nonLawmakerWarning) {
      generatedPrompt = nonLawmakerWarning + '\n\n' + generatedPrompt;
    }

    // 2.5. [가족 상황 경고] 공통 적용 (자녀 환각 방지)
    const familyWarning = generateFamilyStatusWarning({
      familyStatus: options.familyStatus
    });

    if (familyWarning) {
      generatedPrompt = familyWarning + '\n\n' + generatedPrompt;
    }

    // 3. [선거법 준수] 사용자 상태에 따른 선거법 준수 지침 적용
    const electionCompliantPrompt = injectElectionLawCompliance(generatedPrompt, status);

    // 4. [공통 품질 규칙] 모든 템플릿에 적용
    const qualityEnhancedPrompt = injectUniversalQualityRules(electionCompliantPrompt);

    // 5. [프레이밍] 지능적 프레이밍 적용
    const selectedFrame = analyzeAndSelectFrame(topic);
    const framedPrompt = applyFramingToPrompt(qualityEnhancedPrompt, selectedFrame);

    // 6. [Editorial] 기존 SEO 규칙 적용 (필요시)
    const editorialPrompt = options.applyEditorialRules
      ? injectEditorialRules(framedPrompt, options)
      : framedPrompt;

    // 7. [SEO 최적화 + 반복 금지] 최상단에 핵심 규칙 주입 (최우선)
    const seoInstruction = buildSEOInstruction({
      keywords: options.keywords,
      targetWordCount: options.targetWordCount
    });
    const antiRepetitionInstruction = buildAntiRepetitionInstruction();
    const finalPrompt = seoInstruction + antiRepetitionInstruction + editorialPrompt;

    console.log('✅ buildSmartPrompt 완료:', {
      writingMethod,
      status,
      keywordCount: options.keywords?.length || 0,
      electionLawApplied: status ? `STAGE for ${status}` : 'None',
      framingApplied: selectedFrame ? selectedFrame.id : 'None',
    });

    return finalPrompt;

  } catch (error) {
    console.error('❌ buildSmartPrompt 오류:', error);
    return `[시스템 오류] 프롬프트 생성에 실패했습니다: ${error.message}`;
  }
}

// Editorial 규칙 주입기
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
};