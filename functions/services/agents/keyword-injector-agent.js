'use strict';

/**
 * KeywordInjectorAgent - 검색어를 본문에 4~6회 자연스럽게 삽입
 *
 * 역할: StructureAgent의 구조화된 본문에 SEO 검색어 삽입
 * 프롬프트 크기: ~6,000자
 *
 * 입력: 구조화된 본문(content), 검색어(userKeywords)
 * 출력: 검색어가 삽입된 본문
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

    // 현재 키워드 삽입 횟수 확인
    const currentCounts = this.countKeywords(content, userKeywords);
    const needsInjection = userKeywords.some(kw => currentCounts[kw] < 4);

    if (!needsInjection) {
      console.log('✅ [KeywordInjectorAgent] 이미 충분히 삽입됨:', currentCounts);
      return { content, title, keywordCounts: currentCounts };
    }

    // 프롬프트 생성
    const prompt = this.buildPrompt({ content, userKeywords, currentCounts });

    console.log(`📝 [KeywordInjectorAgent] 프롬프트 생성 완료 (${prompt.length}자)`);

    // LLM 호출
    const response = await callGenerativeModel(prompt, 1, 'gemini-2.5-flash', true, 3500);

    // 응답 파싱
    const injected = this.parseResponse(response, content);

    // 삽입 후 검증
    const newCounts = this.countKeywords(injected, userKeywords);
    console.log(`✅ [KeywordInjectorAgent] 검색어 삽입 완료:`, newCounts);

    return {
      content: injected,
      title,
      keywordCounts: newCounts,
      sourceText
    };
  }

  buildPrompt({ content, userKeywords, currentCounts }) {
    const keywordList = userKeywords.map(kw =>
      `- "${kw}": 현재 ${currentCounts[kw] || 0}회 → 목표 4~6회`
    ).join('\n');

    return `당신은 SEO 전문가입니다. 본문에 검색어를 자연스럽게 삽입하세요.

## 삽입할 검색어
${keywordList}

## 현재 본문
${content}

## 규칙

1. **각 검색어를 4~6회** 본문에 삽입하세요.
2. **검색어 원문 그대로** 사용하세요.
   - ✅ "부산 디즈니랜드 유치" → 그대로 사용
   - ❌ "부산에 디즈니랜드를 유치" → 변형 금지!
3. **분산 배치**:
   - 서론: 1~2회
   - 본론들: 각 1회씩
   - 결론: 1회
4. **자연스러운 문맥**에서 삽입하세요.
   - 기존 문장에 녹여 넣거나
   - 새로운 문장을 추가하거나
5. **같은 문단에 2회 이상 반복 금지**
6. **HTML 구조 유지** (<h2>, <p> 태그 보존)

## 출력 형식
검색어가 삽입된 전체 본문만 출력하세요. 설명 없이 HTML 본문만 출력하세요.`;
  }

  parseResponse(response, original) {
    if (!response) return original;

    // HTML 태그가 있으면 그대로 사용
    if (response.includes('<p>') || response.includes('<h2>')) {
      // 마크다운 코드블록 제거
      return response
        .replace(/```html?\s*/gi, '')
        .replace(/```/g, '')
        .trim();
    }

    // JSON 형식이면 content 추출
    try {
      const parsed = JSON.parse(response);
      if (parsed.content) return parsed.content;
    } catch {
      // JSON 아님
    }

    // 그 외에는 원본 유지
    console.warn('⚠️ [KeywordInjectorAgent] 파싱 실패, 원본 유지');
    return original;
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
