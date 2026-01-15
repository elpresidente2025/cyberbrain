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
const { generateCompactReminder } = require('../services/guidelines/reminder');

// [신규] 자연스러운 문체 규칙 (LLM 티 제거)
const { buildNaturalTonePrompt } = require('./guidelines/natural-tone');

// 작법별 프롬프트 빌더 모듈 import
const { buildDailyCommunicationPrompt } = require('./templates/daily-communication');
const { buildLogicalWritingPrompt } = require('./templates/policy-proposal');
const { buildActivityReportPrompt } = require('./templates/activity-report');
const { buildCriticalWritingPrompt, buildDiagnosisWritingPrompt } = require('./templates/current-affairs');
const { buildLocalIssuesPrompt } = require('./templates/local-issues');
const { buildBipartisanCooperationPrompt, PRAISE_BOUNDARIES } = require('./templates/bipartisan-cooperation');

// [신규] 정치인 소속 정당 조회 및 관계 판단
const { analyzeTextForPoliticians, formatRelationshipsForPrompt } = require('../services/politician-lookup');

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
      userKeywords = [],  // 🔑 사용자 직접 입력 키워드 (최우선)
      factAllowlist = null,
      targetWordCount = 2050
    } = options;

    // 0. [검색어(userKeywords) CRITICAL 섹션] - SEO 필수 삽입
    // ※ 검색어 ≠ 키워드. 검색어는 반드시 삽입, 키워드는 맥락 참고용
    let searchTermsCritical = '';
    if (userKeywords && userKeywords.length > 0) {
      const searchTermList = userKeywords.map((kw, i) => `  ${i + 1}. "${kw}"`).join('\n');
      searchTermsCritical = `
╔═══════════════════════════════════════════════════════════════╗
║  🔍 [CRITICAL] 노출 희망 검색어 - SEO 필수 삽입                ║
╚═══════════════════════════════════════════════════════════════╝

검색어:
${searchTermList}

[필수 규칙]
✅ 각 검색어 최소 2회 포함
✅ 도입부(첫 문단)에 1회 포함
✅ 문맥에 자연스럽게 녹일 것
❌ 검색어 나열 금지
❌ 한 문장에 여러 검색어 몰아넣기 금지

`;
    }

    // 1. [라우팅] 작법별 템플릿 프롬프트 생성

    let factLockSection = '';
    if (factAllowlist) {
      const allowedTokens = (factAllowlist.tokens || []).slice(0, 30);
      if (allowedTokens.length > 0) {
        factLockSection = `
[수치 제한 규칙]
- 아래 수치/날짜/금액만 사용하고, 나머지 수치는 사용하지 마세요.
- 허용된 표현 외 다른 수치를 만들지 마세요.
- 허용 목록: ${allowedTokens.join(', ')}
`;
      } else {
        factLockSection = `
[수치 제한 규칙]
- 수치 정보를 사용하지 마세요. 출처(자료/통계 등)가 없기 때문입니다.
- 구체적인 숫자나 비율을 언급하지 마세요.
`;
      }
    }

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
      case 'diagnostic_writing':
        templatePrompt = buildDiagnosisWritingPrompt(options);
        break;
      case 'analytical_writing':
        templatePrompt = buildLocalIssuesPrompt(options);
        break;
      case 'bipartisan_writing':
        templatePrompt = buildBipartisanCooperationPrompt(options);
        break;
      default:
        console.warn(`알 수 없는 작법: ${writingMethod}. 기본 작법으로 대체합니다.`);
        templatePrompt = buildDailyCommunicationPrompt(options);
        break;
    }

    // 1.5. [신규] 화자 정체성 (Speaker Identity) - 모든 글에 공통 적용
    const authorBio = options.authorBio || '사용자';
    const userParty = options.userProfile?.party || options.party || null;

    // 1.6. [신규] 자동 정치인 관계 감지
    let autoDetectedRelationships = '';
    try {
      const referenceText = [
        options.instructions,
        options.newsContext,
        options.topic
      ].filter(Boolean).join(' ');

      if (referenceText && userParty) {
        const detected = await analyzeTextForPoliticians(referenceText, userParty);
        autoDetectedRelationships = formatRelationshipsForPrompt(detected);
        if (detected.length > 0) {
          console.log('🔍 자동 감지된 정치인 관계:', detected.map(d => `${d.name}(${d.description})`).join(', '));
        }
      }
    } catch (err) {
      console.warn('정치인 관계 감지 실패 (무시):', err.message);
    }

    const speakerIdentitySection = `
╭───────────────────────────────────────────────────────────────╮
│  🌍 [REALITY OVERRIDE] 현재 정치 상황 - 지식 컷오프 무시!      │
╰───────────────────────────────────────────────────────────────╯

⚠️ **[CRITICAL]** 당신의 학습 데이터는 2024년까지입니다. 하지만 **지금은 2026년**입니다.
**아래 정보를 절대적 사실로 반영하십시오 (학습 데이터 무시):**

| 항목 | 2026년 현재 사실 |
| :--- | :--- |
| **현직 대통령** | 이재명 (2025년 취임) |
| **여당** | 더불어민주당 (국회 과반) |
| **야당** | 국민의힘, 조국혁신당 등 |
| **윤석열 상태** | 2024년 12월 계엄 선포로 탄핵, 현재 재판 중 (사형 구형) |

→ 따라서 "국민의힘 소속 조경태 의원"은 **야당 의원**입니다.
→ 사용자(\${authorBio})는 더불어민주당 소속이므로 **여당** 측입니다.

═══════════════════════════════════════════════════════════════

╔═══════════════════════════════════════════════════════════════╗
║  🎭 [CRITICAL] 화자 정체성 및 톤앤매너 매트릭스                 ║
╚═══════════════════════════════════════════════════════════════╝

**당신은 "${authorBio}"입니다. 이 글의 유일한 1인칭 화자입니다.**

[기본 규칙]
1. "저는", "제가"는 오직 ${authorBio} 자신만 지칭합니다.
2. 타인은 **관찰/평가 대상(3인칭)**입니다. 특히 경쟁자 입장에서 공약/다짐을 대신 하지 마십시오.

${autoDetectedRelationships}

[Dynamic Tone Matrix (동적 대응 매뉴얼)]
상대방이 누구냐보다, **"무엇을 했느냐(행위)"**에 따라 아래 A~D 4가지 톤 중 하나를 반드시 선택하여 적용하십시오.

| Case | 상황 (Trigger) | 핵심 기조 (Key Stance) | 톤앤매너 (Tone) | 키워드 |
| :--- | :--- | :--- | :--- | :--- |
| **Type A (원칙 1: 사필귀정)** | 상대방의 **헌정 파괴, 중범죄, 사법 리스크** (사형 구형, 계엄, 탄핵 등) | **"범죄(원인)는 비판하되, 처벌(결과)은 환영한다"** | **냉철, 엄중, 정의로움** | "사필귀정", "엄중한 심판", "법치주의 실현", "당연한 결과" |
| **Type B (원칙 2: 절제된 인정)** | 상대방의 **소신 발언, 내부 비판, 원칙 준수** (쓴소리, 용기 있는 행동) | **"1~2문장만 인정 후, 즉시 자기PR로 복귀"** | **절제된 인정** | "높이 평가한다", "주목할 만하다" |
| **Type C (원칙 3: 정책 견제)** | 일반적인 **정쟁, 정책 차이, 단순 행보** | **"정중하지만 날선 비판과 대안 제시"** | **논리적 비판, 견제** | "유감입니다", "재고해야 합니다", "의문입니다", "건강한 경쟁" |
| **Type D (원칙 4: 인류애)** | **재난, 사고, 사망, 국가적 비극** | **"정쟁 중단, 무조건적 위로"** | **애도, 슬픔, 위로** | "참담한 심정", "깊은 애도", "명복을 빕니다" |

⚠️ **[Type A(사필귀정) 필수 가이드 - 인과관계 명확화]**
1. **절대 금지**: "사형 구형 소식에 마음이 무겁다", "안타깝다", "헌정이 흔들린다(X)"
   - 이는 범죄자를 옹호하는 뉘앙스입니다. 절대 금지합니다.
2. **필수 논리**: **"헌정 질서를 파괴한 것은 그들의 범죄(원인)이며, 이번 구형은 이를 바로잡는 정의(결과)다."**
   - 구형/처벌은 민주주의의 위기가 아니라 **회복**입니다.

[올바른 적용 예시]
- (상황: 경쟁자가 사형 구형을 받음) → **Type A**: "이는 **사필귀정**입니다. 헌정을 유린한 자들에 대한 **엄중한 심판**은 무너진 법치를 바로세우는 첫걸음입니다." (O)
- (상황: 경쟁자 조경태가 소신 발언을 함) → **Type B**: "비록 당은 다르지만, 헌법을 지키려는 조경태 의원의 태도는 **높이 평가합니다**." (O)

⚠️ **[Type B 겳쟁자 과잘 칭찬 금지 - 필수 준수]**
1. 경쟁자 칭찬은 **1~2문장**으로 끝내십시오. (예: "~한 점은 높이 평가합니다.")
2. **절대 금지 표현**: "~의 정신을 이어받아", "~에게 배워야", "~의 뜻을 받들어", "깊은 울림", "용기에 박수", "배울 점"
3. 칭찬 직후 **반드시 자기PR로 복귀**하십시오. (예: "저 또한 이러한 원칙을...")
`;

    // 1.7. [신규] 결론부 품질 규칙 - 모든 글에 공통 적용
    const conclusionRulesSection = `
╔═══════════════════════════════════════════════════════════════╗
║  📝 [CRITICAL] 결론부 구조 - 단일 문단 통합 (One Paragraph)     ║
╚═══════════════════════════════════════════════════════════════╝

[핵심 규칙]
1. 결론은 **하나의 문단(One Paragraph)**으로 통합하는 것을 원칙으로 합니다.
2. 단, 문장이 너무 길어지거나 호흡이 끊길 경우, 흐름을 잇기 위해 **자연스러운 연결어(그리고, 따라서, 다짐컨대 등)**를 적절히 사용하십시오.
3. 기계적으로 짧은 문장을 나열("저는 합니다. 저는 합니다")하지 말고, **유려한 문체**로 작성하십시오.

✅ [올바른 결론 구조 (통합형 - 자연스러운 흐름)]
"(요약) 오늘 말씀드린 정책을 통해 부산의 변화를 이끌겠습니다. (연결) 이러한 변화는 저 혼자만의 힘으로는 불가능합니다. (다짐) 그렇기에 저 이재성은 언제나 시민 여러분과 함께 끝까지 뛰겠습니다. (인사) 감사합니다. (서명) ${authorBio} 드림"

❌ [금지된 구조 (분리형)]
- 문단 1: 요약...
- 문단 2: 다짐...
- 문단 3: 인사...
`;

    // 1.8. [신규] 자연스러운 문체 규칙 - LLM 티 제거
    const naturalToneSection = buildNaturalTonePrompt({
      platform: 'general',
      severity: 'standard'
    });

    templatePrompt = speakerIdentitySection + conclusionRulesSection + naturalToneSection + templatePrompt;

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
    const { prefix, suffix, stats } = buildGroundedGuidelines({
      status,
      category,
      writingMethod,
      topic,
      keywords,
      targetWordCount
    });

    // 5. [프롬프트 조립] Primacy/Recency Effect 적용
    // 구조: 검색어(CRITICAL) → prefix(CRITICAL) → 템플릿 → suffix(HIGH/SEO) → reminder(체크리스트)
    let assembledPrompt = '';

    // 5.0 최우선: 검색어 (Primacy Effect - 가장 앞에)
    if (searchTermsCritical) {
      assembledPrompt += searchTermsCritical;
    }

    if (factLockSection) {
      assembledPrompt += factLockSection;
    }

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
    const compactReminder = generateCompactReminder([], status);
    const finalPrompt = framedPrompt + '\n' + compactReminder;

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
    throw new Error(`프롬프트 생성 실패: ${error.message}`);
  }
}


// ============================================================================
// Editorial 규칙 주입기
// ============================================================================

function injectEditorialRules(basePrompt, options) {
  const seoSection = `
[🎯 SEO 기본 규칙]
- 분량: ${SEO_RULES.wordCount.min}~${SEO_RULES.wordCount.max}자 (목표: ${SEO_RULES.wordCount.target}자)`;

  const formatSection = `
[📝 출력 형식]
- JSON 형식으로 제목(title)·본문(content) 출력
- HTML 구조: ${FORMAT_RULES.htmlGuidelines.structure.join(', ')}
- 문체: 합쇼체 유지, 같은 문단의 어미 반복은 피하고 유사 표현으로 분산하도록 권장
- 조사 누락·문장 미완결 금지`;

  return basePrompt
    .replace(/(\[📊 SEO 최적화 규칙\])/g, seoSection)
    .replace(/(\[📝 출력 형식\])/g, formatSection);
}

// ============================================================================
// 내보내기
// ============================================================================

module.exports = {
  buildSmartPrompt
};
