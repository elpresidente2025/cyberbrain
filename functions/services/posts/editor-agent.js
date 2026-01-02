'use strict';

/**
 * EditorAgent - 검증 결과 기반 LLM 수정
 *
 * 역할:
 * - 휴리스틱 검증 결과(선거법, 반복 등)를 받아 LLM으로 자연스럽게 수정
 * - 키워드 미포함 문제 해결
 * - SEO 제안 사항 반영
 *
 * 흐름:
 * 생성 → 검증(문제 발견) → EditorAgent(LLM 수정) → 출력
 */

const { callGenerativeModel } = require('../gemini');

/**
 * 검증 결과를 기반으로 원고를 LLM으로 수정
 *
 * @param {Object} params
 * @param {string} params.content - 원본 콘텐츠 (HTML)
 * @param {string} params.title - 원본 제목
 * @param {Object} params.validationResult - 휴리스틱 검증 결과
 * @param {Object} params.keywordResult - 키워드 검증 결과
 * @param {Array} params.userKeywords - 사용자 입력 키워드
 * @param {string} params.status - 사용자 상태 (준비/현역/예비/후보)
 * @param {string} params.modelName - 사용할 모델
 * @returns {Promise<{content: string, title: string, edited: boolean, editSummary: string[]}>}
 */
async function refineWithLLM({
  content,
  title,
  validationResult,
  keywordResult,
  userKeywords = [],
  status,
  modelName
}) {
  // 수정이 필요한 문제들 수집
  const issues = [];

  // 1. 휴리스틱 검증 문제
  if (validationResult && !validationResult.passed) {
    // 선거법 위반
    if (validationResult.details?.electionLaw?.violations?.length > 0) {
      issues.push({
        type: 'election_law',
        severity: 'critical',
        description: `선거법 위반 표현 발견: ${validationResult.details.electionLaw.violations.join(', ')}`,
        instruction: '이 표현들을 선거법을 준수하면서 동일한 의미를 전달하는 완곡한 표현으로 수정하세요. 예: "~하겠습니다" → "~을 추진합니다", "~을 연구하고 있습니다"'
      });
    }

    // 문장 반복
    if (validationResult.details?.repetition?.repeatedSentences?.length > 0) {
      issues.push({
        type: 'repetition',
        severity: 'high',
        description: `문장 반복 발견: ${validationResult.details.repetition.repeatedSentences.join(', ')}`,
        instruction: '반복되는 문장을 다른 표현으로 바꾸거나 삭제하세요.'
      });
    }

    if (validationResult.details?.factCheck) {
      const factCheck = validationResult.details.factCheck || {};
      const unsupportedContent = factCheck.content?.unsupported || [];
      const unsupportedTitle = factCheck.title?.unsupported || [];

      if (unsupportedContent.length > 0) {
        issues.push({
          type: 'fact_check',
          severity: 'critical',
          description: `근거 없는 수치(본문): ${unsupportedContent.join(', ')}`,
          instruction: '원문/배경자료에 없는 수치는 삭제하거나 근거 있는 수치로 교체하세요.'
        });
      }
      if (unsupportedTitle.length > 0) {
        issues.push({
          type: 'title_fact_check',
          severity: 'high',
          description: `근거 없는 수치(제목): ${unsupportedTitle.join(', ')}`,
          instruction: '제목의 수치를 본문/자료에 있는 수치로 바꾸거나 수치를 제거하세요.'
        });
      }
    }
  }

  // 2. 키워드 미포함 문제
  if (keywordResult && !keywordResult.valid) {
    const missingKeywords = Object.entries(keywordResult.details?.keywords || {})
      .filter(([_, info]) => !info.valid && info.type === 'user')
      .map(([keyword, info]) => `"${keyword}" (현재 ${info.count}회, 최소 ${info.expected}회 필요)`);

    if (missingKeywords.length > 0) {
      issues.push({
        type: 'missing_keywords',
        severity: 'high',
        description: `필수 키워드 부족: ${missingKeywords.join(', ')}`,
        instruction: '이 키워드들을 본문에 자연스럽게 추가하세요. 특히 도입부에 포함하면 SEO에 효과적입니다.'
      });
    }
  }

  // 3. 제목 품질 문제 (validation.js에서 검증한 결과)
  if (validationResult?.details?.titleQuality && !validationResult.details.titleQuality.passed) {
    const titleIssues = validationResult.details.titleQuality.issues || [];
    for (const issue of titleIssues) {
      // 이미 있는 이슈와 중복 방지
      if (!issues.some(i => i.type === issue.type)) {
        issues.push({
          type: issue.type,
          severity: issue.severity,
          description: issue.description,
          instruction: issue.instruction
        });
      }
    }
  }

  // 3-1. 분량 문제 (contentLength)
  if (validationResult?.details?.contentLength && validationResult.details.contentLength.passed === false) {
    const lengthInfo = validationResult.details.contentLength;
    const current = lengthInfo.current;
    const min = lengthInfo.min;
    const max = lengthInfo.max;
    let instruction = '본문 분량을 기준 범위로 조정하세요.';

    if (typeof min === 'number' && current < min) {
      instruction = `본문 분량을 ${min}자 이상으로 확장하세요. 기존 맥락을 유지하면서 근거/사례를 보강하고 과도한 반복은 피하세요.`;
    } else if (typeof max === 'number' && current > max) {
      instruction = `본문 분량을 ${max}자 이하로 줄이세요. 핵심 근거는 유지하고 군더더기 표현을 정리하세요.`;
    }

    issues.push({
      type: 'content_length',
      severity: 'high',
      description: `본문 분량 ${current}자 (기준: ${typeof min === 'number' ? min : '-'}~${typeof max === 'number' ? max : '-'})`,
      instruction
    });
  }

  // 3-2. SEO 개선 이슈 (SEOAgent 결과)
  if (validationResult?.details?.seo) {
    const seoDetails = validationResult.details.seo;
    const seoIssues = Array.isArray(seoDetails.issues) ? seoDetails.issues : [];
    const seoSuggestions = Array.isArray(seoDetails.suggestions) ? seoDetails.suggestions : [];

    for (const issue of seoIssues) {
      const description = issue.message || issue.description || issue.reason || 'SEO 기준 미달';
      const instruction = issue.instruction || description;
      issues.push({
        type: issue.id || 'seo_issue',
        severity: issue.severity || 'high',
        description,
        instruction
      });
    }

    for (const suggestion of seoSuggestions) {
      const text = typeof suggestion === 'string'
        ? suggestion
        : (suggestion.message || suggestion.suggestion || '');
      if (!text) continue;
      issues.push({
        type: 'seo_suggestion',
        severity: 'medium',
        description: text,
        instruction: text
      });
    }
  }

  // 4. 사용자 키워드가 제목에 없는 경우 (titleQuality에서 이미 체크하지만 폴백)
  if (userKeywords.length > 0 && title && !issues.some(i => i.type === 'keyword_missing')) {
    const keywordsInTitle = userKeywords.filter(kw => title.includes(kw));
    if (keywordsInTitle.length === 0) {
      issues.push({
        type: 'title_keyword',
        severity: 'medium',
        description: `제목에 노출 희망 검색어 없음: ${userKeywords.join(', ')}`,
        instruction: '제목에 위 키워드 중 하나를 자연스럽게 포함하세요. 제목은 25자 이내로 유지하세요.'
      });
    }
  }

  // 수정할 문제가 없으면 원본 반환
  if (issues.length === 0) {
    console.log('✅ [EditorAgent] 수정 필요 없음 - 원본 유지');
    return {
      content,
      title,
      edited: false,
      editSummary: []
    };
  }

  console.log(`📝 [EditorAgent] ${issues.length}개 문제 발견, LLM 수정 시작`);

  // LLM 프롬프트 생성
  const prompt = buildEditorPrompt({
    content,
    title,
    issues,
    userKeywords,
    status
  });

  try {
    const response = await callGenerativeModel(prompt, 1, modelName, true);

    // JSON 파싱
    let result;
    try {
      // JSON 블록 추출
      const jsonMatch = response.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        result = JSON.parse(jsonMatch[0]);
      } else {
        throw new Error('JSON 형식 없음');
      }
    } catch (parseError) {
      console.error('❌ [EditorAgent] JSON 파싱 실패:', parseError.message);
      return { content, title, edited: false, editSummary: ['파싱 실패로 원본 유지'] };
    }

    console.log('✅ [EditorAgent] LLM 수정 완료:', {
      titleChanged: result.title !== title,
      contentLength: result.content?.length || 0,
      editSummary: result.editSummary
    });

    return {
      content: result.content || content,
      title: result.title || title,
      edited: true,
      editSummary: result.editSummary || issues.map(i => i.description)
    };

  } catch (error) {
    console.error('❌ [EditorAgent] LLM 호출 실패:', error.message);
    return { content, title, edited: false, editSummary: ['LLM 호출 실패로 원본 유지'] };
  }
}

/**
 * EditorAgent용 프롬프트 생성
 */
function buildEditorPrompt({ content, title, issues, userKeywords, status }) {
  const issuesList = issues.map((issue, idx) =>
    `${idx + 1}. [${issue.severity.toUpperCase()}] ${issue.description}\n   → ${issue.instruction}`
  ).join('\n\n');

  const statusNote = (status === '준비' || status === '현역')
    ? `\n⚠️ 작성자 상태: ${status} (예비후보 등록 전) - "~하겠습니다" 같은 공약성 표현 금지`
    : '';

  // 제목 관련 이슈가 있으면 상세 가이드라인 추가
  const hasTitleIssues = issues.some(i =>
    i.type.startsWith('title_') || ['keyword_missing', 'keyword_position', 'abstract_expression'].includes(i.type)
  );

  const titleGuideline = hasTitleIssues ? `
╔═══════════════════════════════════════════════════════════════╗
║  🚨 [CRITICAL] 제목 수정 필수 - 반드시 아래 규칙을 따르세요  ║
╚═══════════════════════════════════════════════════════════════╝

🔴 절대 금지 (위반 시 제목 재작성):
• 부제목 패턴: "-", ":", "/" 사용 금지
• 콤마 부제목: "OO, 해법을 찾다" 같은 패턴 금지
• 추상적 명사: 해법, 진단, 방안, 대책, 과제, 분석, 전망, 혁신, 발전
• 추상적 동사: 찾다, 막는다, 나선다, 밝히다, 모색
• 25자 초과

✅ 필수 규칙:
• 25자 이내 (엄격히 준수)
• 핵심 키워드는 제목 맨 앞에 배치
• 반드시 구체적인 숫자 1개 이상 포함
• 제목의 숫자/단위는 본문에 실제 등장한 수치만 사용
• 단일 문장 형태 (부제목 없이)

📊 올바른 제목 형식 (반드시 이 패턴 사용):
• "[키워드] + [숫자/사실] + [결과]"
• "부산 대형병원 5곳 응급실 확대" (17자) ✅
• "부산 대형병원 순위 27위→10위권" (17자) ✅
• "환자 유출 30% 감소 3년 목표" (15자) ✅

❌ 절대 사용 금지 패턴:
• "부산 대형병원, 순위 올리는 해법" ❌ (콤마 부제목, 해법)
• "부산 대형병원 순위 진단과 전망" ❌ (진단, 전망)
• "대형병원 문제, 이렇게 해결한다" ❌ (콤마 부제목, 추상적)
• "의료 혁신을 위한 5대 과제" ❌ (혁신, 과제)
` : '';

  return `당신은 정치 원고 편집 전문가입니다. 아래 원고에서 발견된 문제들을 수정해주세요.

[수정이 필요한 문제들]
${issuesList}
${statusNote}
${titleGuideline}
[원본 제목]
${title}

[원본 본문]
${content}

[필수 포함 키워드]
${userKeywords.join(', ') || '(없음)'}

[수정 지침]
1. 지적된 문제들만 최소한으로 수정하세요. 원고의 전체적인 톤과 맥락은 유지하세요.
2. 선거법 위반 표현은 동일한 의미를 전달하면서 완곡하게 수정하세요.
3. 키워드는 자연스럽게 문맥에 맞게 삽입하세요. 억지로 끼워넣지 마세요.
4. 제목은 25자 이내로 유지하고, 키워드를 앞쪽에 배치하세요.
5. 숫자/연도/비율은 원문·배경자료에 있는 것만 사용하세요.
6. HTML 구조(<p>, <strong> 등)는 유지하세요.

다음 JSON 형식으로만 응답하세요:
{
  "title": "수정된 제목",
  "content": "수정된 본문 (HTML)",
  "editSummary": ["수정한 내용 1", "수정한 내용 2"]
}`;
}

module.exports = {
  refineWithLLM
};
