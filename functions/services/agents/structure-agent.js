'use strict';

/**
 * StructureAgent - 초안을 5단 구조로 확장
 *
 * 역할: DraftAgent의 초안을 받아 서론/본론1/본론2/본론3/결론으로 구조화
 * 프롬프트 크기: ~8,000자
 *
 * 입력: 초안(draft), 주제, 참고자료
 * 출력: HTML 형식의 구조화된 본문 (2000~2500자)
 */

const { BaseAgent } = require('./base');
const { callGenerativeModel } = require('../gemini');

class StructureAgent extends BaseAgent {
  constructor() {
    super('StructureAgent');
  }

  getRequiredContext() {
    return ['previousResults'];
  }

  async execute(context) {
    const {
      previousResults,
      topic,
      userProfile,
      targetWordCount = 2000
    } = context;

    // DraftAgent 결과 가져오기
    const draftResult = previousResults?.DraftAgent?.data;
    if (!draftResult?.draft) {
      throw new Error('DraftAgent 결과가 없습니다');
    }

    const { draft, sourceText, authorName, authorTitle } = draftResult;

    // 프롬프트 생성
    const prompt = this.buildPrompt({
      draft,
      sourceText,
      topic,
      authorName,
      authorTitle,
      targetWordCount
    });

    console.log(`📝 [StructureAgent] 프롬프트 생성 완료 (${prompt.length}자)`);

    // LLM 호출
    const response = await callGenerativeModel(prompt, 1, 'gemini-2.5-flash', true, 3500);

    // 응답 파싱
    const structured = this.parseResponse(response);

    if (!structured.content || structured.content.length < 500) {
      console.warn('⚠️ [StructureAgent] 구조화 결과가 부실함');
      // 기본 구조로 감싸기
      structured.content = this.wrapWithBasicStructure(draft, topic);
    }

    console.log(`✅ [StructureAgent] 구조화 완료 (${structured.content.length}자)`);

    return {
      content: structured.content,
      title: structured.title || `${topic} 관련`,
      draft,  // 원본 초안 보존
      sourceText
    };
  }

  buildPrompt({ draft, sourceText, topic, authorName, authorTitle, targetWordCount }) {
    // 참고자료에서 핵심 팩트 추출용 (너무 길면 축약)
    const truncatedSource = sourceText && sourceText.length > 3000
      ? sourceText.substring(0, 3000) + '\n[...]'
      : sourceText;

    return `당신은 블로그 글을 구조화하는 전문 에디터입니다.

## 작성자 정보
- 이름: ${authorName || '화자'}
- 직함: ${authorTitle || ''}

## 원본 초안 (이것을 확장합니다)
${draft}

## 참고자료 (팩트 확인용)
${truncatedSource || '(없음)'}

## 작업 지침

초안을 **5단 구조**로 확장하여 **${targetWordCount}~${targetWordCount + 500}자** 분량으로 만드세요.

### 구조 (필수)
1. **서론** (200~300자): 화자 소개 + 문제 제기
2. **본론1** (400~500자): 첫 번째 핵심 논점 (소제목 필수)
3. **본론2** (400~500자): 두 번째 핵심 논점 (소제목 필수)
4. **본론3** (400~500자): 세 번째 핵심 논점 (소제목 필수)
5. **결론** (200~300자): 요약 + 다짐/호소

### 규칙
1. **HTML 태그 사용**: <h2>소제목</h2>, <p>문단</p> 형식
2. **소제목(H2)은 구체적으로**: "본론1" 같은 추상적 제목 금지
   - 좋은 예: "다대포 디즈니랜드, 왜 가능한가?"
   - 나쁜 예: "본론", "첫 번째 논점"
3. **1인칭 화자** 유지: "저는...", "제가..."
4. **초안의 핵심 내용**을 반드시 포함하고 확장
5. **새로운 사실 창작 금지**: 초안과 참고자료에 없는 내용 쓰지 마세요

### 출력 형식 (JSON)
\`\`\`json
{
  "title": "25자 이내 제목",
  "content": "<p>서론 내용...</p><h2>소제목1</h2><p>본론1...</p>..."
}
\`\`\`

JSON만 출력하세요.`;
  }

  parseResponse(response) {
    if (!response) return { content: '', title: '' };

    // JSON 추출
    try {
      // 코드블록 내 JSON
      const jsonMatch = response.match(/```(?:json)?\s*([\s\S]*?)```/);
      if (jsonMatch) {
        return JSON.parse(jsonMatch[1].trim());
      }

      // 직접 JSON
      const directMatch = response.match(/\{[\s\S]*\}/);
      if (directMatch) {
        return JSON.parse(directMatch[0]);
      }
    } catch (e) {
      console.warn('⚠️ [StructureAgent] JSON 파싱 실패:', e.message);
    }

    // 파싱 실패 시 원본 텍스트를 content로
    return {
      content: response.replace(/```[\s\S]*?```/g, '').trim(),
      title: ''
    };
  }

  wrapWithBasicStructure(draft, topic) {
    // 초안을 기본 구조로 감싸기 (폴백)
    const paragraphs = draft.split('\n\n').filter(p => p.trim());
    const third = Math.ceil(paragraphs.length / 3);

    const intro = paragraphs.slice(0, 1).join('\n\n');
    const body1 = paragraphs.slice(1, third + 1).join('\n\n');
    const body2 = paragraphs.slice(third + 1, third * 2 + 1).join('\n\n');
    const body3 = paragraphs.slice(third * 2 + 1, -1).join('\n\n');
    const conclusion = paragraphs.slice(-1).join('\n\n');

    return `<p>${intro}</p>
<h2>${topic} 현황 분석</h2>
<p>${body1 || '...'}</p>
<h2>핵심 쟁점</h2>
<p>${body2 || '...'}</p>
<h2>향후 전망</h2>
<p>${body3 || '...'}</p>
<h2>맺음말</h2>
<p>${conclusion}</p>`;
  }
}

module.exports = { StructureAgent };
