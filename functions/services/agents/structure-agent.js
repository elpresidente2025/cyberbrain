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

    console.log(`🚀 [StructureAgent] 시작 - 카테고리: ${category}, 주제: ${topic}`);

    // 1. 작법 결정
    const writingMethod = resolveWritingMethod(category, subCategory);
    console.log(`✍️ [StructureAgent] 작법 선택: ${writingMethod}`);

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

      // LLM 호출 (JSON 모드 사용)
      const response = await callGenerativeModel(currentPrompt, 1, 'gemini-2.5-flash', true, 8192);

      // 응답 파싱
      const structured = this.parseResponse(response);
      let content = normalizeArtifacts(structured.content);
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
2. 반드시 인용해야 할 **입장문 핵심 문구** 추출 (최우선)
3. 뉴스에서 **팩트와 발언** 추출

[참고자료]
${sourceText.substring(0, 4000)}

다음 JSON 형식으로만 응답하세요:
{
  "issueScope": "이슈 범위 (CENTRAL_ISSUE / LOCAL_ISSUE 등)",
  "responsibilityTarget": "비판/요구 대상 주체",
  "expectedTone": "글의 예상 논조 (비판/지지/분석 등)",
  "mustIncludeFromStance": ["입장문(첫번째 자료)에서 추출한 가장 강력한 문장 2~3개 (원문 그대로)"],
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

    // 3. ContextAnalyzer 결과 주입 (입장문 필수 포함 등)
    let contextInjection = '';
    if (contextAnalysis) {
      const stancePhrases = (contextAnalysis.mustIncludeFromStance || [])
        .map(p => `- "${p}"`).join('\n');

      contextInjection = `
╔═══════════════════════════════════════════════════════════════╗
║  🔴 [MANDATORY] 입장문 핵심 문구 반영 (절대 누락 금지)        ║
╚═══════════════════════════════════════════════════════════════╝
아래 문장들은 작성자의 입장이 담긴 핵심 문구입니다. **반드시 본문에 원문 그대로 또는 핵심을 살려 포함하십시오.**

${stancePhrases || '(없음)'}

⚠️ 위 문구가 포함되지 않으면 원고 생성은 실패로 간주됩니다.
`;
    }

    // 4. 구조 강제 프롬프트 (핵심)
    const structureEnforcement = `
╔═══════════════════════════════════════════════════════════════╗
║  🏗️ [ABSOLUTE STRUCTURE] 15문단 구조 강제 (매우 중요)        ║
╚═══════════════════════════════════════════════════════════════╝

당신은 위에서 제시된 **[화법과 스타일]**을 유지하되, 
반드시 아래의 **[5단 구조, 총 15문단]** 틀에 맞춰 내용을 배치해야 합니다.

**목표 분량: 총 ${targetWordCount}자 내외 (±10%) 필수**
- **최소 ${Math.floor(targetWordCount * 0.9)}자 ~ 최대 ${Math.floor(targetWordCount * 1.1)}자**를 반드시 준수하십시오.
- 너무 짧거나(요약X) 너무 길어지지(장황X) 않도록 각 문단의 길이를 조절하십시오. 
- 각 문단은 평균 130~150자 내외가 적당합니다.

### 필수 구조 (총 15개의 <p> 문단)

1. **도입부** (3문단):
   - 문단 1: 인사 및 화자 소개 ("저는...") - 200자 이상
   - 문단 2: 이슈의 배경 및 현황 - 200자 이상
   - 문단 3: 문제 제기 및 집필 의도 - 200자 이상

2. **본론1** (3문단) - 소제목(<h2>) 필수:
   - 문단 1: 첫 번째 핵심 논점/주장 제시 - 200자 이상
   - 문단 2: 구체적 근거/사례/데이터 (뉴스 팩트 활용) - 200자 이상
   - 문단 3: 소결 및 의미 부여 - 200자 이상

3. **본론2** (3문단) - 소제목(<h2>) 필수:
   - 문단 1: 두 번째 핵심 논점/주장 - 200자 이상
   - 문단 2: 심층 분석 또는 반론 제기 - 200자 이상
   - 문단 3: 논리적 확장 - 200자 이상

4. **본론3** (3문단) - 소제목(<h2>) 필수:
   - 문단 1: 세 번째 핵심 논점/해결책 제안 - 200자 이상
   - 문단 2: 구체적 실행 방안 또는 공약 연결 - 200자 이상
   - 문단 3: 기대 효과 - 200자 이상

5. **결말부** (3문단) - 소제목(<h2>) 필수:
   - 문단 1: 전체 내용 요약 및 핵심 메시지 재강조 - 200자 이상
   - 문단 2: 미래 비전 제시 - 200자 이상
   - 문단 3: 강력한 호소 및 마무리 인사 - 200자 이상

⚠️ **[제약 조건 - 위반 시 실패]**
1. **요약 금지**: 짤막한 요약글이 아니라, 호흡이 긴 에세이/칼럼 형식이어야 합니다.
2. **반복 금지**: 같은 문장을 반복하지 마십시오.
3. **HTML 태그**: 문단은 <p>...</p>, 소제목은 <h2>...</h2>만 사용하십시오.
4. **문단 수 준수**: 각 섹션은 정확히 3개의 문단이어야 합니다 (총 15개).
5. **JSON 출력**: 결과는 반드시 JSON 포맷이어야 합니다.
`;

    // 5. 최종 조립
    return `
${templatePrompt}

${partyStanceGuide ? partyStanceGuide : ''}

${contextInjection}

${structureEnforcement}

[출력 형식 (JSON Only)]
\`\`\`json
{
  "title": "25자 이내의 매력적인 제목",
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
    let text = response.replace(/```(?:json)?\s*([\s\S]*?)```/g, '$1').trim();

    try {
      // JSON 파싱 시도
      const parsed = JSON.parse(text);
      return {
        content: parsed.content || parsed.body || '',
        title: parsed.title || ''
      };
    } catch (e) {
      // JSON 파싱 실패 시 HTML 추출 시도
      console.warn('⚠️ [StructureAgent] JSON 파싱 실패, HTML 직접 추출 시도');
      const contentMatch = text.match(/<p>[\s\S]*<\/p>/);
      const content = contentMatch ? contentMatch[0] : text;
      return { content, title: '' };
    }
  }
}

module.exports = { StructureAgent };
