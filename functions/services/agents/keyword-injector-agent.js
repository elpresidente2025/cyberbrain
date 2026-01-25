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

    // 🔄 재시도 로직 설정
    const MAX_RETRIES = 2; // 총 3회 시도
    let attempt = 0;
    let feedback = '';
    let currentContent = content;
    let currentCounts = this.countKeywords(currentContent, userKeywords);

    // 초기 상태 체크: 이미 충분하면 바로 리턴
    if (this.validateInjection(userKeywords, currentCounts).passed) {
      console.log('✅ [KeywordInjectorAgent] 초기 상태부터 검색어 충족:', currentCounts);
      return { content, title, keywordCounts: currentCounts };
    }

    while (attempt <= MAX_RETRIES) {
      attempt++;
      console.log(`🔄 [KeywordInjectorAgent] 시도 ${attempt}/${MAX_RETRIES + 1}`);

      // 프롬프트 생성 (피드백 포함)
      const prompt = this.buildPrompt({
        content: currentContent,
        userKeywords,
        currentCounts,
        feedback
      });

      console.log(`📝 [KeywordInjectorAgent] 프롬프트 생성 완료 (${prompt.length}자)`);

      // LLM 호출 (JSON 모드 OFF - HTML 직접 출력)
      const response = await callGenerativeModel(prompt, 1, 'gemini-2.5-flash', false, 4000);

      // 응답 파싱
      const injected = this.parseResponse(response, currentContent);

      // 삽입 후 검증
      const newCounts = this.countKeywords(injected, userKeywords);
      const validation = this.validateInjection(userKeywords, newCounts);

      if (validation.passed) {
        console.log(`✅ [KeywordInjectorAgent] 검색어 삽입 성공:`, newCounts);
        return {
          content: injected,
          title,
          keywordCounts: newCounts,
          sourceText
        };
      }

      // 검증 실패 처리
      console.warn(`⚠️ [KeywordInjectorAgent] 검증 실패 (${validation.reason})`);
      feedback = validation.feedback; // 피드백 저장
      currentContent = content;       // 원본 내용을 다시 넣는게 나을까? 아니면 부분 성공한걸 쓸까? -> 부분 성공한 걸 쓰면 문맥이 꼬일 수 있음. 원본 재시도 추천.

      // 만약 2번 실패했다면, 그냥 현재 결과라도 반환 (무한 루프 방지 및 부분 성공 인정)
      if (attempt > MAX_RETRIES) {
        console.warn('⛔ [KeywordInjectorAgent] 재시도 횟수 초과 - 최선 결과 반환');
        return {
          content: injected, // 실패했더라도 시도한 결과물 반환
          title,
          keywordCounts: newCounts,
          sourceText
        };
      }
    }
  }

  validateInjection(keywords, counts) {
    const missing = keywords.filter(kw => (counts[kw] || 0) < 4);

    if (missing.length === 0) {
      return { passed: true };
    }

    // 실패 사유 상세화
    const feedbackList = missing.map(kw => `"${kw}" (${counts[kw] || 0}/4회)`);
    return {
      passed: false,
      reason: `검색어 미달: ${missing.length}개`,
      feedback: `다음 검색어의 삽입 횟수가 부족합니다. 더 적극적으로 본문에 삽입해주세요: ${feedbackList.join(', ')}`
    };
  }

  buildPrompt({ content, userKeywords, currentCounts, feedback }) {
    const keywordList = userKeywords.map(kw =>
      `- "${kw}": 현재 ${currentCounts[kw] || 0}회 → 목표 4~6회`
    ).join('\n');

    let basePrompt = `당신은 SEO 전문가입니다. 본문에 검색어를 자연스럽게 삽입하세요.

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

    if (feedback) {
      basePrompt += `\n\n🚨 [중요] 이전 시도가 다음 이유로 실패했습니다:\n"${feedback}"\n\n위 검색어를 최우선으로 추가 삽입하세요.`;
    }

    return basePrompt;
  }

  parseResponse(response, original) {
    if (!response) return original;

    // 1. JSON 형식 우선 파싱
    // (LLM이 명시적으로 JSON을 반환했거나, 실수로 JSON으로 감싼 경우 처리)
    try {
      // 코드블록 내 JSON 추출
      const jsonMatch = response.match(/```(?:json)?\s*([\s\S]*?)```/);
      const jsonStr = jsonMatch ? jsonMatch[1].trim() : response;

      const parsed = JSON.parse(jsonStr);
      if (parsed.content) return parsed.content;
      if (parsed.html_content) return parsed.html_content;
    } catch {
      // JSON 파싱 실패 시 HTML 태그 확인으로 넘어감
    }

    // 2. HTML 태그가 있으면 그대로 사용 (Fallback)
    if (response.includes('<p>') || response.includes('<h2>')) {
      // 마크다운 코드블록 제거
      return response
        .replace(/```html?\s*/gi, '')
        .replace(/```/g, '')
        .trim();
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
