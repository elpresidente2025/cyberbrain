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

// [신규] 작법별 프롬프트 빌더 모듈 import
const { buildDailyCommunicationPrompt } = require('./templates/daily-communication');
const { buildLogicalWritingPrompt } = require('./templates/policy-proposal');
const { buildActivityReportPrompt } = require('./templates/activity-report'); // direct-writing -> activity-report
const { buildCriticalWritingPrompt } = require('./templates/current-affairs');
const { buildLocalIssuesPrompt } = require('./templates/local-issues'); // analytical-writing -> local-issues

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
// 공통 품질 규칙 주입기
// ============================================================================

/**
 * 모든 템플릿에 공통으로 적용되는 품질 규칙
 * @param {string} basePrompt - 기본 프롬프트
 * @returns {string} 품질 규칙이 추가된 프롬프트
 */
function injectUniversalQualityRules(basePrompt) {
  const qualityRules = `

╔═══════════════════════════════════════════════════════════════╗
║  ⛔ 필수 품질 규칙 - 모든 원고에 공통 적용  ⛔                  ║
╚═══════════════════════════════════════════════════════════════╝

** 이 규칙을 위반하면 원고가 자동으로 폐기되고 재생성됩니다 **

1. **반복 절대 금지**
   - 동일하거나 유사한 문장을 반복하지 말 것
   - 동일하거나 유사한 문단을 반복하지 말 것
   - 이미 작성한 내용을 다시 작성하지 마세요
   - 각 문장과 문단은 새로운 정보나 관점을 제공해야 함

   예시:
   ❌ "A 정책이 필요합니다. ...중략... A 정책이 필요합니다." (같은 문장 반복)
   ❌ "<p>첫 번째 문단</p> ...중략... <p>첫 번째 문단</p>" (같은 문단 반복)
   ✅ 각 문단이 서로 다른 내용을 담고 있어야 함

2. **구조 일관성**
   - JSON 형식으로 출력할 때, content 필드는 단 하나만 존재해야 함
   - 마무리 표현 후 본문이 다시 시작되지 않도록 할 것
   - 글의 끝은 명확하게 한 번만 맺을 것

3. **문장 완결성**
   - 모든 문장이 완전한 구조를 갖출 것 (주어-서술어 완비)
   - 조사나 어미가 누락되지 않도록 할 것
   - 문장 중간에 끊기지 않도록 할 것

   예시:
   ❌ "이러한 사실을 알리는 것이 지역 의원으" (문장 미완성)
   ✅ "이러한 사실을 알리는 것이 지역 의원으로서의 책임입니다" (완성)

---

`;

  return qualityRules + basePrompt;
}

// ============================================================================
// 통합 프롬프트 빌더 (v3 - Router)
// ============================================================================

async function buildSmartPrompt(options) {
  try {
    const { writingMethod, topic } = options;
    let generatedPrompt;

    // 1. [라우팅] 사용자가 선택한 작법(writingMethod)에 따라 적절한 빌더 호출
    switch (writingMethod) {
      case 'emotional_writing':
        generatedPrompt = buildDailyCommunicationPrompt(options);
        break;
      case 'logical_writing':
        generatedPrompt = buildLogicalWritingPrompt(options);
        break;
      case 'direct_writing': // formConstants에서 activity-report, policy-proposal 등이 direct_writing을 사용할 수 있음
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

    // 3. [공통 품질 규칙] 모든 템플릿에 적용
    const qualityEnhancedPrompt = injectUniversalQualityRules(generatedPrompt);

    // 4. [프레이밍] 지능적 프레이밍 적용
    const selectedFrame = analyzeAndSelectFrame(topic);
    const framedPrompt = applyFramingToPrompt(qualityEnhancedPrompt, selectedFrame);

    // 5. [Editorial] SEO 규칙 적용 (필요시)
    const finalPrompt = options.applyEditorialRules
      ? injectEditorialRules(framedPrompt, options)
      : framedPrompt;

    console.log('✅ buildSmartPrompt 완료:', {
      writingMethod,
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
