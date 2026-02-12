'use strict';

/**
 * StructureAgent - 맥락 인식 및 구조적 글쓰기 에이전트 (Refactored)
 *
 * 역할:
 * - 원시 참고자료(뉴스, 지시사항)를 직접 분석 (ContextAnalyzer 통합)
 * - 카테고리별 템플릿(작법) 적용
 * - 5단 구조(15문단) 강제
 * - 선거법 및 당론 가이드라인 적용
 *
 * 입력: 주제, 참고자료, 사용자 프로필, 카테고리
 * 출력: HTML 형식의 구조화된 본문 (2000~2500자)
 */

const { BaseAgent } = require('./base');
const { callGenerativeModel } = require('../gemini');
const { resolveWritingMethod } = require('../../utils/posts/constants');
const { extractStyleFromText } = require('../../utils/style-analyzer');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const { getGeminiApiKey } = require('../../common/secrets');

// ✅ 주제 기반 자동 분류
const { classifyTopic } = require('../posts/topic-classifier');

// ✅ 선거법 규칙 import
const { getElectionStage } = require('../../prompts/guidelines/legal');

// ✅ 당론 가이드 import
const { getPartyStance } = require('../../prompts/guidelines/theminjoo');

// ✅ 유틸리티 (경고문 등)
const { generateNonLawmakerWarning, generateFamilyStatusWarning } = require('../../prompts/utils/non-lawmaker-warning');

// ✅ 템플릿 빌더 import
const { buildDailyCommunicationPrompt } = require('../../prompts/templates/daily-communication');
const { buildLogicalWritingPrompt } = require('../../prompts/templates/policy-proposal');
const { buildActivityReportPrompt } = require('../../prompts/templates/activity-report');
const { buildCriticalWritingPrompt, buildDiagnosisWritingPrompt } = require('../../prompts/templates/current-affairs');
const { buildLocalIssuesPrompt } = require('../../prompts/templates/local-issues');

// 작법 → 템플릿 빌더 매핑
const TEMPLATE_BUILDERS = {
  'emotional_writing': buildDailyCommunicationPrompt,
  'logical_writing': buildLogicalWritingPrompt,
  'direct_writing': buildActivityReportPrompt,
  'critical_writing': buildCriticalWritingPrompt,
  'diagnostic_writing': buildDiagnosisWritingPrompt,
  'analytical_writing': buildLocalIssuesPrompt
};

function stripHtml(text) {
  return String(text || '').replace(/<[^>]*>/g, '').replace(/\s+/g, '').trim();
}

function normalizeArtifacts(text) {
  if (!text) return '';
  let cleaned = String(text).trim();

  cleaned = cleaned.replace(/```[\s\S]*?```/g, '').trim();
  cleaned = cleaned.replace(/^\s*\\"/, '').replace(/\\"?\s*$/, '');
  cleaned = cleaned.replace(/^\s*["“]/, '').replace(/["”]\s*$/, '');

  // 메타데이터 제거
  cleaned = cleaned
    .replace(/카테고리:[\s\S]*$/m, '')
    .replace(/검색어 삽입 횟수:[\s\S]*$/m, '')
    .replace(/생성 시간:[\s\S]*$/m, '');

  // JSON 키 잔여물 제거
  cleaned = cleaned.replace(/"content"\s*:\s*/g, '');

  return cleaned.trim();
}

class StructureAgent extends BaseAgent {
  constructor() {
    super('StructureAgent');
  }

  getRequiredContext() {
    return ['topic', 'category', 'userProfile'];
  }

  // Gemini API 직접 호출을 위한 헬퍼
  getGenAI() {
    const apiKey = getGeminiApiKey();
    if (!apiKey) return null;
    return new GoogleGenerativeAI(apiKey);
  }

  async execute(context) {
    const {
      topic,
      userProfile,
      category = '',
      subCategory = '',
      instructions = '',
      newsContext = '',
      targetWordCount = 2000,
      userKeywords = [],
      memoryContext = ''
    } = context;

    console.log(`🚀 [StructureAgent] 시작 - 카테고리: ${category || '(자동)'}, 주제: ${topic}`);

    // 1. 작법 결정 (카테고리 없으면 자동 분류)
    let writingMethod;
    if (category && category !== 'auto') {
      // 기존 로직: 명시적 카테고리 사용
      writingMethod = resolveWritingMethod(category, subCategory);
      console.log(`✍️ [StructureAgent] 작법 선택 (카테고리 기반): ${writingMethod}`);
    } else {
      // 🆕 자동 분류: 주제 분석으로 작법 결정
      const classification = await classifyTopic(topic);
      writingMethod = classification.writingMethod;
      console.log(`🤖 [StructureAgent] 작법 자동 추론: ${writingMethod} (신뢰도: ${classification.confidence}, 소스: ${classification.source})`);
    }

    // 2. 저자 정보 구성 (WriterAgent 로직 이관)
    const authorBio = this.buildAuthorBio(userProfile);
    const authorName = userProfile.name || '화자';

    // 3. 당론 가이드 조회 (비동기)
    let partyStanceGuide = null;
    try {
      partyStanceGuide = await getPartyStance(topic);
    } catch (e) {
      console.warn('⚠️ [StructureAgent] 당론 조회 실패:', e.message);
    }

    // 4. ContextAnalyzer 실행 (WriterAgent 로직 이관)
    const contextAnalysis = await this.runContextAnalyzer(instructions, newsContext, authorName);

    // 5. 프롬프트 생성
    const prompt = this.buildPrompt({
      topic,
      category,
      writingMethod,
      authorName,
      authorBio,
      instructions,
      newsContext,
      targetWordCount,
      partyStanceGuide,
      contextAnalysis,
      userProfile,
      memoryContext,
      userKeywords
    });

    console.log(`📝 [StructureAgent] 프롬프트 생성 완료 (${prompt.length}자)`);

    // 6. 생성 및 구조 검증 루프 (최대 3회)
    const MAX_RETRIES = 2;
    let attempt = 0;
    let feedback = '';

    while (attempt <= MAX_RETRIES) {
      attempt++;
      console.log(`🔄 [StructureAgent] 생성 시도 ${attempt}/${MAX_RETRIES + 1}`);

      let currentPrompt = prompt;
      if (feedback) {
        currentPrompt += `\n\n🚨 [중요] 이전 시도가 다음 이유로 반려되었습니다:\n"${feedback}"\n\n위 지적 사항을 반드시 반영하여, 15문단 구조를 완벽히 준수하여 다시 작성하십시오.`;
      }

      // LLM 호출 (JSON 모드 OFF - 긴 텍스트 생성 안정성 확보)
      const response = await callGenerativeModel(currentPrompt, 1, 'gemini-2.5-flash', false, 8192);

      // 🔧 [DEBUG] LLM 원본 응답 로깅 (240자 원인 파악용)
      console.log(`📥 [StructureAgent] LLM 원본 응답 (${response?.length || 0}자):`, response?.substring(0, 500) + (response?.length > 500 ? '...' : ''));

      // 응답 파싱
      const structured = this.parseResponse(response);
      const content = normalizeArtifacts(structured.content);
      let title = normalizeArtifacts(structured.title || '');

      // 출력 검증
      const validation = this.validateOutput(content, targetWordCount);

      if (validation.passed) {
        console.log(`✅ [StructureAgent] 검증 통과: ${stripHtml(content).length}자`);

        // 제목 폴백
        if (!title || !title.trim()) {
          title = topic ? `${topic.substring(0, 20)}` : '새 원고';
        }

        return {
          content,
          title,
          // 후속 에이전트를 위한 메타데이터
          writingMethod,
          contextAnalysis
        };
      }

      // 실폐 처리
      console.warn(`⚠️ [StructureAgent] 검증 실패: ${validation.reason}`);
      feedback = validation.feedback;

      if (attempt > MAX_RETRIES) {
        throw new Error(`StructureAgent 검증 실패 (${MAX_RETRIES}회 초과): ${validation.reason}`);
      }
    }
  }

  // WriterAgent의 ContextAnalyzer 로직 이관
  async runContextAnalyzer(instructions, newsContext, authorName) {
    const sourceText = [instructions, newsContext].filter(Boolean).join('\n');
    if (sourceText.length < 100) return null;

    console.log('🔍 [StructureAgent] ContextAnalyzer 실행...');
    const ai = this.getGenAI();
    if (!ai) return null;

    const contextPrompt = `당신은 정치 뉴스 분석 전문가입니다. 아래 참고자료를 읽고 상황을 정확히 파악하세요.

⚠️ **[중요] 참고자료 구조 안내**:
- **첫 번째 자료**: 글 작성자(${authorName})가 직접 작성한 **페이스북 글 또는 입장문**입니다. 이것이 글의 핵심 논조와 주장입니다.
- **두 번째 이후 자료**: 뉴스 기사, 데이터 등 **배경 정보와 근거 자료**입니다.

분석 목표:
1. 글쓴이의 **입장과 논조** 추출
2. 반드시 인용해야 할 **핵심 공약/정책/주장** 추출 (최우선)
3. 뉴스에서 **팩트와 발언** 추출

⚠️ **mustIncludeFromStance 추출 규칙**:
- 각 항목은 **15자 이상의 완전한 문장**이어야 합니다
- 우선순위: (1) 구체적 공약/정책명, (2) 수치/일정 포함 문장, (3) 핵심 논리/비유, (4) 격언형/수사적 문장
- ❌ "e스포츠", "디즈니" 같은 단어만 추출 금지

[참고자료]
${sourceText.substring(0, 4000)}

다음 JSON 형식으로만 응답하세요:
{
  "issueScope": "이슈 범위 (CENTRAL_ISSUE / LOCAL_ISSUE 등)",
  "responsibilityTarget": "비판/요구 대상 주체",
  "expectedTone": "글의 예상 논조 (비판/지지/분석 등)",
  "mustIncludeFromStance": ["입장문의 핵심 공약/정책/주장 (15자 이상 완전한 문장)", "최대 5개까지"],
  "mustIncludeFacts": ["뉴스에서 추출한 구체적 팩트 5개"],
  "newsQuotes": ["뉴스 주요 발언 3개"]
}`;

    try {
      const model = ai.getGenerativeModel({ model: 'gemini-2.5-flash' });
      const result = await model.generateContent({
        contents: [{ role: 'user', parts: [{ text: contextPrompt }] }],
        generationConfig: { responseMimeType: 'application/json', temperature: 0.1 }
      });

      const text = result.response.text();
      const jsonMatch = text.match(/\{[\s\S]*\}/);
      const analysis = jsonMatch ? JSON.parse(jsonMatch[0]) : JSON.parse(text);

      console.log('✅ [StructureAgent] ContextAnalyzer 완료:', analysis.issueScope);

      // [필터링 적용] WriterAgent와 동일한 로직
      if (analysis.mustIncludeFromStance && Array.isArray(analysis.mustIncludeFromStance)) {
        analysis.mustIncludeFromStance = analysis.mustIncludeFromStance.filter(phrase => {
          if (!phrase || typeof phrase !== 'string') return false;
          const trimmed = phrase.trim();
          if (trimmed.startsWith('⚠️')) return false;
          if (trimmed.startsWith('우선순위:')) return false;
          if (trimmed.startsWith('예시 패턴:')) return false;
          if (trimmed.startsWith('→ 실제')) return false;
          if (trimmed.length < 5) return false; // 5자 미만 제외
          return true;
        });
      }

      return analysis;
    } catch (e) {
      console.warn('⚠️ [StructureAgent] ContextAnalyzer 실패 (무시):', e.message);
      return null;
    }
  }

  buildPrompt(params) {
    const {
      topic, category, writingMethod, authorName, authorBio,
      instructions, newsContext, targetWordCount,
      partyStanceGuide, contextAnalysis, userProfile, memoryContext, userKeywords
    } = params;

    // 1. 템플릿 빌더 선택
    const templateBuilder = TEMPLATE_BUILDERS[writingMethod] || buildDailyCommunicationPrompt;

    // 2. 기본 템플릿 프롬프트 생성 (WriterAgent 방식 사용)
    // 주의: templateBuilder는 instructions/newsContext를 받아서 스타일 가이드를 생성함
    const templatePrompt = templateBuilder({
      topic,
      authorBio,
      authorName,
      instructions,
      keywords: userKeywords, // 키워드 전달
      targetWordCount,
      personalizedHints: memoryContext,
      newsContext,
      isCurrentLawmaker: this.isCurrentLawmaker(userProfile),
      politicalExperience: userProfile.politicalExperience || '정치 신인',
      familyStatus: userProfile.familyStatus || ''
    });

    // 3. 🔴 [CRITICAL FIX] 참고자료 원문 주입 (2026-01-29)
    // 템플릿 빌더가 참고자료를 프롬프트에 삽입하지 않아 AI가 무시하는 버그 수정
    const sourceText = [instructions, newsContext].filter(Boolean).join('\n\n---\n\n');
    let referenceMaterialsSection = '';
    if (sourceText && sourceText.trim().length > 0) {
      referenceMaterialsSection = `
╔═══════════════════════════════════════════════════════════════╗
║  📚 [1차 자료] 참고자료 - 원고의 핵심 소스                     ║
╚═══════════════════════════════════════════════════════════════╝

⚠️ **[CRITICAL] 아래 참고자료가 이 원고의 1차 자료(Primary Source)입니다.**
- 첫 번째 자료: 작성자의 입장문/페이스북 글 (핵심 논조와 주장)
- 이후 자료: 뉴스/데이터 (근거, 팩트, 배경 정보)

**[참고자료 원문]**
${sourceText.substring(0, 6000)}

🚨 **[자료 처리 규칙 - 중요]**
1. **정보 추출**: 참고자료에서 핵심 팩트, 수치, 논점만 추출하세요.
2. **재작성 필수 (CRITICAL)**: 추출한 정보를 **반드시 새로운 문장으로 다시 작성**하세요. 참고자료의 문장을 그대로 복사하지 마세요.
3. **구어체 → 문어체 변환**: 인터뷰/대화체 자료의 경우, 구어체 표현("그래서요", "거예요", "~하거든요" 등)을 문어체로 변환하세요.
4. **창작 금지**: 참고자료에 없는 팩트, 수치를 창작하지 마세요.
5. **주제 유지**: 참고자료의 주제를 벗어나지 마세요.
6. **보조 자료**: 사용자 프로필(Bio)은 화자 정체성과 어조 참고용이며, 분량이 부족할 때만 활용하세요.

❌ **금지 예시**:
- 참고자료: "정확하게 얘기를 하면 그래서 창의적이고 정말 압도적인..."
- ❌ 잘못된 사용: "정확하게 얘기를 하면 그래서 창의적이고..." (복붙)
- ✅ 올바른 사용: "창의적이고 압도적인 콘텐츠 기반 전략이 핵심입니다." (재작성)
`;
      console.log('📚 [StructureAgent] 참고자료 주입 완료:', sourceText.length, '자');
    } else {
      console.warn('⚠️ [StructureAgent] 참고자료 없음 - 사용자 프로필만으로 생성');
    }

    // 4. ContextAnalyzer 결과 주입 (입장문 필수 포함 등)
    let contextInjection = '';
    if (contextAnalysis) {
      const stanceList = contextAnalysis.mustIncludeFromStance || [];
      const stancePhrases = stanceList.map((p, i) => `${i + 1}. "${p}"`).join('\n');
      const stanceCount = stanceList.length;

      contextInjection = `
╔═══════════════════════════════════════════════════════════════╗
║  🔴 [MANDATORY] 핵심 공약/주장별 본론 분리 (절대 합치지 말 것) ║
╚═══════════════════════════════════════════════════════════════╝

아래는 작성자의 핵심 공약/주장 **${stanceCount}개**입니다.
**각 항목을 반드시 별도의 본론 섹션으로 작성**하세요. 두 개 이상을 하나의 본론에 합치면 실패입니다.

${stancePhrases || '(없음)'}

📌 **본론 구조 지시**:
- 위 ${stanceCount}개 공약 → **본론 ${stanceCount}개** (각각 별도 h2 소제목)
- 예: "서울대병원 유치"와 "e스포츠 박물관"은 별도 본론
- 공약 외 현황분석/경쟁구도 등은 도입부나 결론에 배치

⚠️ 공약이 누락되거나 합쳐지면 원고 생성은 실패로 간주됩니다.
`;
    }

    // 4. 구조 강제 프롬프트 (핵심)
    // [추가] Bio 인용구 보존 및 원외 인사 경고 (사용자 요청)
    let bioIntegrityWarning = '';

    // 원외 인사 경고 생성
    const nonLawmakerWarning = generateNonLawmakerWarning({
      isCurrentLawmaker: this.isCurrentLawmaker(userProfile),
      politicalExperience: userProfile.politicalExperience,
      authorBio
    });

    if (nonLawmakerWarning) {
      bioIntegrityWarning += nonLawmakerWarning + '\n\n';
    }

    // Bio 인용구 보존 법칙
    if (authorBio && authorBio.includes('"')) {
      bioIntegrityWarning += `
🚨 [CRITICAL] Bio 인용구 보존 법칙:
- 작성자 정보(Bio)에 있는 **큰따옴표(" ")로 묶인 문장**은 사용자의 핵심 서사(Narrative)이므로, 금지어(예: 국회의원)가 포함되어 있더라도 **절대 수정/삭제/검열하지 말고 원문 그대로 인용**하십시오.
- AI가 임의로 "이재성 했을 텐데"처럼 이름을 넣어 문장을 망치지 마십시오. 원문 그대로 "국회의원 했을 텐데"라고 써야 합니다.
`;
    }

    const structureEnforcement = `
╔═══════════════════════════════════════════════════════════════╗
║  🏗️ [STRUCTURE] 유연한 본론 구조 (내용 중심)                 ║
╚═══════════════════════════════════════════════════════════════╝

당신은 위에서 제시된 **[화법과 스타일]**을 유지하되,
아래의 구조 틀에 맞춰 내용을 배치해야 합니다.

**분량 원칙**:
- 각 문단은 **120~150자** 범위로 작성하십시오.
- 분량보다 **내용의 완결성**이 우선입니다. 참고자료의 핵심 공약/주장을 빠짐없이 다루십시오.
- 동어반복으로 분량을 늘리지 마십시오.

### 구조 (도입 + 본론 3~5개 + 결말)

1. **도입부** (3문단):
   - 문단 1: 인사 및 화자 소개 ("저는...")
   - 문단 2: 이슈의 배경 및 현황
   - 문단 3: 문제 제기 및 집필 의도

2. **본론** (3~5개 섹션, 각 2~3문단) - 각 섹션에 소제목(<h2>) 필수:
   - ⚠️ **참고자료에서 추출된 핵심 공약/정책/주장의 수에 따라 본론 섹션 수를 결정**하십시오.
   - 공약이 3개면 본론 3개, 공약이 5개면 본론 5개.
   - 각 본론 섹션은: (1) 핵심 주장 제시, (2) 구체적 근거/사례, (3) 기대 효과 또는 소결
   - **추출된 공약/주장은 반드시 별도의 본론 섹션으로 다뤄야 합니다. 하나도 빠뜨리지 마십시오.**

3. **결말부** (3문단) - 소제목(<h2>) 필수:
   - 문단 1: 전체 내용 요약 및 핵심 메시지 재강조
   - 문단 2: 미래 비전 제시
   - 문단 3: 강력한 호소 및 마무리 인사

⚠️ **[제약 조건 - 위반 시 실패]**
1. **요약 금지**: 짤막한 요약글이 아니라, 호흡이 긴 에세이/칼럼 형식이어야 합니다.
2. **반복 금지**: 같은 문장을 반복하지 마십시오.
3. **HTML 태그**: 문단은 <p>...</p>, 소제목은 <h2>...</h2>만 사용하십시오.
4. **공약별 본론 분리 필수**: 서로 다른 공약/정책은 절대 하나의 본론에 합치지 마십시오.
   예: "서울대병원"과 "e스포츠 박물관"은 각각 별도 본론 섹션이어야 합니다.
5. **JSON 출력**: 결과는 반드시 JSON 포맷이어야 합니다.
`;

    // 6. 최종 조립
    return `
${templatePrompt}

${partyStanceGuide ? partyStanceGuide : ''}

${referenceMaterialsSection}

${contextInjection}

${bioIntegrityWarning}

${structureEnforcement}

[출력 형식 (JSON Only)]
\`\`\`json
{
  "title": "(제목 미정)",
  "content": "<p>서론 문단 1...</p><p>서론 문단 2...</p>...<h2>본론1 소제목</h2><p>본론1 문단 1...</p>..."
}
\`\`\`
`.trim();
  }

  // WriterAgent에서 이관: 저자 Bio 생성
  buildAuthorBio(userProfile) {
    const name = userProfile.name || '사용자';
    const partyName = userProfile.partyName || '';
    const currentTitle = userProfile.customTitle || userProfile.position || '';
    const basicBio = [partyName, currentTitle, name].filter(Boolean).join(' ');

    // 추가 정보
    const career = userProfile.careerSummary || userProfile.bio || '';
    const slogan = userProfile.slogan ? `"${userProfile.slogan}"` : '';

    return `${basicBio}\n${career}\n${slogan}`.trim();
  }

  // WriterAgent에서 이관: 현역 의원 여부
  isCurrentLawmaker(userProfile) {
    const status = userProfile.status || '';
    const position = userProfile.position || '';
    const title = userProfile.customTitle || '';

    // 현역 키워드: '의원', '구청장', '군수', '시장', '도지사' 등 선출직
    const electedKeywords = ['의원', '구청장', '군수', '시장', '도지사', '교육감'];
    const textToCheck = (status + position + title);

    return electedKeywords.some(k => textToCheck.includes(k));
  }

  validateOutput(content, targetWordCount) {
    if (!content) return { passed: false, reason: '내용 없음', feedback: '내용이 비어있습니다.' };

    const plainLength = stripHtml(content).length;
    const minLength = Math.floor(targetWordCount * 0.85);

    // 1. 길이 검사
    if (plainLength < minLength) {
      return {
        passed: false,
        reason: `길이 부족 (${plainLength} < ${minLength})`,
        feedback: `글이 너무 짧습니다. 각 문단을 2문장 이상 더 추가하여 상세하게 확장하세요.`
      };
    }

    // 2. 구조 검사 (H2 개수)
    const h2Count = (content.match(/<h2>/g) || []).length;
    if (h2Count < 4) { // 본론1,2,3,결론 최소 4개 필요
      return {
        passed: false,
        reason: `소제목 부족 (현재 ${h2Count}개)`,
        feedback: `소제목(<h2>)이 부족합니다. 본론1, 본론2, 본론3, 결말부에 모두 소제목을 붙여주세요.`
      };
    }

    // 3. 문단 수 대략적 검사 (P 개수)
    const pCount = (content.match(/<p>/g) || []).length;
    if (pCount < 10) { // 최소 10개 이상은 되어야 15문단 흉내라도 냄
      return {
        passed: false,
        reason: `문단 수 부족 (현재 ${pCount}개)`,
        feedback: `문단 수가 너무 적습니다. 5단 구조의 각 단계마다 3개의 문단(<p>)을 작성해야 합니다.`
      };
    }

    return { passed: true };
  }

  parseResponse(response) {
    if (!response) return { content: '', title: '' };

    // 코드블록 제거
    const text = response.replace(/```(?:json)?\s*([\s\S]*?)```/g, '$1').trim();

    try {
      // JSON 파싱 시도
      const parsed = JSON.parse(text);
      const content = parsed.content || parsed.body || '';
      console.log(`✅ [StructureAgent] JSON 파싱 성공: content=${content.length}자, title="${parsed.title || '(없음)'}"`);
      return {
        content,
        title: parsed.title || ''
      };
    } catch (e) {
      // JSON 파싱 실패 시 HTML 추출 시도
      console.warn('⚠️ [StructureAgent] JSON 파싱 실패, HTML 직접 추출 시도');

      // 🔧 FIX: 모든 <p>와 <h2> 태그를 포함한 전체 HTML 블록 추출
      // 기존: /<p>[\s\S]*<\/p>/ → 첫 <p>~첫 </p>만 추출 (버그)
      // 수정: 모든 HTML 태그 (<p>, <h2>) 범위를 찾아서 전체 추출

      // 방법 1: 첫 <p> 또는 <h2>부터 마지막 </p> 또는 </h2>까지 추출
      const htmlBlockMatch = text.match(/<(?:p|h[23])[^>]*>[\s\S]*<\/(?:p|h[23])>/i);

      if (htmlBlockMatch) {
        // 첫 매칭 시작점부터 마지막 </p> 또는 </h2>까지 추출
        const firstTagIndex = text.search(/<(?:p|h[23])[^>]*>/i);
        const lastClosingIndex = Math.max(
          text.lastIndexOf('</p>'),
          text.lastIndexOf('</h2>'),
          text.lastIndexOf('</h3>')
        );

        if (firstTagIndex !== -1 && lastClosingIndex !== -1) {
          // 마지막 닫는 태그 뒤까지 포함
          const closingTagLength = text.substring(lastClosingIndex).match(/^<\/[^>]+>/)?.[0]?.length || 4;
          const content = text.substring(firstTagIndex, lastClosingIndex + closingTagLength);
          console.log(`📄 [StructureAgent] HTML 직접 추출 완료: ${content.length}자`);
          return { content, title: '' };
        }
      }

      // 방법 2: 매칭 실패 시 전체 텍스트 반환 (최후의 수단)
      console.warn('⚠️ [StructureAgent] HTML 태그를 찾을 수 없음, 전체 텍스트 반환');
      return { content: text, title: '' };
    }
  }
}

module.exports = { StructureAgent };
