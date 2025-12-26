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
    ['title_length', 'keyword_missing', 'keyword_position', 'abstract_expression', 'title_keyword'].includes(i.type)
  );

  const titleGuideline = hasTitleIssues ? `
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 제목 수정 가이드라인 (네이버 SEO 최적화)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ 필수 규칙:
• 25자 이내 (네이버 검색결과에서 잘리지 않도록)
• 핵심 키워드는 제목 앞 8자 이내에 배치 (앞쪽 1/3 법칙)
• 부제목(-, :) 사용 금지, 콤마(,) 사용 권장

❌ 금지 표현 (추상적):
비전, 혁신, 발전, 노력, 최선, 함께, 다짐, 약속

✅ 권장 표현 (구체적):
• 숫자 사용: "3대 정책", "120억 확보", "40% 개선"
• 구체적 사실: "국비 120억 확보", "대형병원 3곳 유치"

📊 좋은 제목 예시:
• "부산 대형병원 3곳 확충, 120억 투입" (22자)
• "청년 일자리 274명 창출, 지원금 85억" (20자)
• "민원 처리 14일→3일, 5배 빨라졌어요" (19자)

❌ 나쁜 제목 예시:
• "부산 의료 혁신: 더 나은 미래를 위한 비전" (추상적, 길이 초과)
• "청년을 위한 노력, 최선을 다하겠습니다" (공약성, 추상적)
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
5. HTML 구조(<p>, <strong> 등)는 유지하세요.

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
