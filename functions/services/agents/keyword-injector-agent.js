'use strict';

/**
 * KeywordInjectorAgent - 검색어를 본문에 4~6회 자연스럽게 삽입
 *
 * 🔧 v2: 원본 보존 방식으로 재설계
 * - LLM은 삽입할 문장과 위치만 JSON으로 반환
 * - 코드에서 원본에 직접 삽입 → 원본 100% 보존
 *
 * 입력: 구조화된 본문(content), 검색어(userKeywords)
 * 출력: 검색어가 삽입된 본문 (원본 구조 유지)
 */

const { BaseAgent } = require('./base');
const { callGenerativeModel } = require('../gemini');

class KeywordInjectorAgent extends BaseAgent {
  constructor() {
    super('KeywordInjectorAgent');
  }

  getRequiredContext() {
    return ['previousResults', 'userKeywords'];
  }

  async execute(context) {
    const {
      previousResults,
      userKeywords = []
    } = context;

    // StructureAgent 결과 가져오기
    const structureResult = previousResults?.StructureAgent?.data;
    if (!structureResult?.content) {
      throw new Error('StructureAgent 결과가 없습니다');
    }

    const { content, title, sourceText } = structureResult;

    // 검색어가 없으면 그대로 반환
    if (!userKeywords || userKeywords.length === 0) {
      console.log('⏭️ [KeywordInjectorAgent] 검색어 없음 - 스킵');
      return { content, title, keywordCounts: {} };
    }

    // 현재 키워드 카운트
    let currentCounts = this.countKeywords(content, userKeywords);

    // 초기 상태 체크: 이미 충분하면 바로 리턴
    if (this.validateInjection(userKeywords, currentCounts).passed) {
      console.log('✅ [KeywordInjectorAgent] 초기 상태부터 검색어 충족:', currentCounts);
      return { content, title, keywordCounts: currentCounts };
    }

    // 문단 파싱
    const paragraphs = this.parseParagraphs(content);
    console.log(`📊 [KeywordInjectorAgent] 문단 ${paragraphs.length}개 파싱 완료`);

    // 🔄 재시도 로직
    const MAX_RETRIES = 2;
    let attempt = 0;
    let currentContent = content;
    let feedback = '';

    while (attempt <= MAX_RETRIES) {
      attempt++;
      console.log(`🔄 [KeywordInjectorAgent] 시도 ${attempt}/${MAX_RETRIES + 1}`);

      // 프롬프트 생성 (삽입 위치/문장만 요청)
      const prompt = this.buildPrompt({
        paragraphs,
        userKeywords,
        currentCounts,
        feedback
      });

      console.log(`📝 [KeywordInjectorAgent] 프롬프트 생성 완료 (${prompt.length}자)`);

      // LLM 호출 (JSON 모드)
      const response = await callGenerativeModel(prompt, 1, 'gemini-2.5-flash', true, 2000);

      // 삽입 지시 파싱
      const insertions = this.parseInsertions(response);

      if (!insertions || insertions.length === 0) {
        console.warn('⚠️ [KeywordInjectorAgent] 삽입 지시 파싱 실패');
        feedback = '삽입할 문장을 JSON 형식으로 정확히 반환해주세요.';
        continue;
      }

      console.log(`📌 [KeywordInjectorAgent] 삽입 지시 ${insertions.length}개 수신`);

      // 원본에 직접 삽입
      currentContent = this.applyInsertions(content, insertions);

      // 검증
      const newCounts = this.countKeywords(currentContent, userKeywords);
      const validation = this.validateInjection(userKeywords, newCounts);

      if (validation.passed) {
        console.log(`✅ [KeywordInjectorAgent] 검색어 삽입 성공:`, newCounts);
        return {
          content: currentContent,
          title,
          keywordCounts: newCounts,
          sourceText
        };
      }

      // 검증 실패
      console.warn(`⚠️ [KeywordInjectorAgent] 검증 실패 (${validation.reason})`);
      feedback = validation.feedback;
      currentCounts = newCounts;

      if (attempt > MAX_RETRIES) {
        console.warn('⛔ [KeywordInjectorAgent] 재시도 횟수 초과 - 현재 결과 반환');
        return {
          content: currentContent,
          title,
          keywordCounts: newCounts,
          sourceText
        };
      }
    }

    // fallback: 원본 반환
    return { content, title, keywordCounts: currentCounts, sourceText };
  }

  /**
   * HTML 본문에서 문단 추출
   */
  parseParagraphs(content) {
    const paragraphs = [];
    const regex = /<(p|h2)[^>]*>([\s\S]*?)<\/\1>/gi;
    let match;
    let index = 0;

    while ((match = regex.exec(content)) !== null) {
      paragraphs.push({
        index,
        tag: match[1].toLowerCase(),
        content: match[2].replace(/<[^>]*>/g, '').trim(),
        fullMatch: match[0]
      });
      index++;
    }

    return paragraphs;
  }

  /**
   * 삽입 지시 프롬프트 생성
   */
  buildPrompt({ paragraphs, userKeywords, currentCounts, feedback }) {
    const keywordStatus = userKeywords.map(kw => {
      const current = currentCounts[kw] || 0;
      const needed = Math.max(0, 4 - current);
      return `- "${kw}": 현재 ${current}회, 추가 필요 ${needed}회`;
    }).join('\n');

    const paragraphList = paragraphs.map((p, i) =>
      `[${i}] <${p.tag}> ${p.content.substring(0, 80)}${p.content.length > 80 ? '...' : ''}`
    ).join('\n');

    let prompt = `검색어를 본문에 삽입할 위치와 문장을 지정하세요.

## 검색어 현황
${keywordStatus}

## 본문 문단 목록
${paragraphList}

## 규칙
1. 각 검색어가 총 4~6회 등장하도록 삽입 문장 생성
2. 검색어는 **원문 그대로** 사용 (띄어쓰기, 조사 변경 금지)
3. 삽입 위치는 문단 번호로 지정 (해당 문단 뒤에 새 <p> 추가)
4. 자연스러운 문장으로 작성

## 출력 형식 (JSON)
{
  "insertions": [
    { "after": 0, "sentence": "검색어가 포함된 새 문장" },
    { "after": 2, "sentence": "검색어가 포함된 새 문장" }
  ]
}`;

    if (feedback) {
      prompt += `\n\n🚨 이전 시도 실패: ${feedback}`;
    }

    return prompt;
  }

  /**
   * LLM 응답에서 삽입 지시 파싱
   */
  parseInsertions(response) {
    if (!response) return null;

    try {
      // JSON 파싱
      let jsonStr = response;

      // 코드블록 제거
      const codeBlockMatch = response.match(/```(?:json)?\s*([\s\S]*?)```/);
      if (codeBlockMatch) {
        jsonStr = codeBlockMatch[1].trim();
      }

      const parsed = JSON.parse(jsonStr);
      return parsed.insertions || parsed.insert || [];
    } catch (e) {
      console.error('⚠️ [KeywordInjectorAgent] JSON 파싱 실패:', e.message);
      return null;
    }
  }

  /**
   * 원본에 삽입 적용
   */
  applyInsertions(content, insertions) {
    if (!insertions || insertions.length === 0) return content;

    // 문단 위치 찾기
    const paragraphPositions = [];
    const regex = /<\/(p|h2)>/gi;
    let match;

    while ((match = regex.exec(content)) !== null) {
      paragraphPositions.push({
        index: paragraphPositions.length,
        endPos: match.index + match[0].length
      });
    }

    // 뒤에서부터 삽입 (위치 변경 방지)
    const sortedInsertions = [...insertions].sort((a, b) => b.after - a.after);
    let result = content;

    for (const ins of sortedInsertions) {
      const afterIdx = ins.after;
      if (afterIdx < 0 || afterIdx >= paragraphPositions.length) continue;

      const insertPos = paragraphPositions[afterIdx].endPos;
      const newParagraph = `\n<p>${ins.sentence}</p>`;

      result = result.slice(0, insertPos) + newParagraph + result.slice(insertPos);
    }

    return result;
  }

  validateInjection(keywords, counts) {
    const missing = keywords.filter(kw => (counts[kw] || 0) < 4);

    if (missing.length === 0) {
      return { passed: true };
    }

    const feedbackList = missing.map(kw => `"${kw}" (${counts[kw] || 0}/4회)`);
    return {
      passed: false,
      reason: `검색어 미달: ${missing.length}개`,
      feedback: `다음 검색어 삽입 부족: ${feedbackList.join(', ')}`
    };
  }

  countKeywords(content, keywords) {
    const counts = {};
    const plainText = content.replace(/<[^>]*>/g, '');

    for (const keyword of keywords) {
      const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp(escaped, 'gi');
      const matches = plainText.match(regex);
      counts[keyword] = matches ? matches.length : 0;
    }

    return counts;
  }
}

module.exports = { KeywordInjectorAgent };
