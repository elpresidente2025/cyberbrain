'use strict';

/**
 * DraftAgent - 참고자료 기반 순수 초안 생성
 *
 * 역할: 참고자료에서 핵심 내용을 추출하여 800~1200자 초안 생성
 * 프롬프트 크기: ~5,000자 (가벼움)
 *
 * 입력: 참고자료(instructions/newsContext), 주제(topic), 사용자 프로필
 * 출력: 핵심 논점이 담긴 초안 (구조화 전 상태)
 */

const { BaseAgent } = require('./base');
const { callGenerativeModel } = require('../gemini');

class DraftAgent extends BaseAgent {
  constructor() {
    super('DraftAgent');
  }

  getRequiredContext() {
    return ['topic', 'userProfile'];
  }

  async execute(context) {
    const {
      topic,
      userProfile,
      instructions = '',
      newsContext = '',
      category = ''
    } = context;

    // 참고자료 병합
    const sourceText = [instructions, newsContext].filter(Boolean).join('\n\n');

    if (!sourceText || sourceText.trim().length < 50) {
      console.warn('⚠️ [DraftAgent] 참고자료 부족 - 기본 초안 생성');
    }

    // 사용자 정보 추출
    const authorName = userProfile?.name || userProfile?.displayName || '';
    const authorTitle = userProfile?.customTitle || '';
    const authorBio = userProfile?.bio || '';

    // 간결한 프롬프트 (핵심만)
    const prompt = this.buildPrompt({
      topic,
      sourceText,
      authorName,
      authorTitle,
      authorBio,
      category
    });

    console.log(`📝 [DraftAgent] 프롬프트 생성 완료 (${prompt.length}자)`);

    // LLM 호출
    const response = await callGenerativeModel(prompt, 1, 'gemini-2.5-flash', true, 1500);

    // 응답 파싱
    let draft = this.parseResponse(response);

    if (!draft || draft.length < 200) {
      console.warn('⚠️ [DraftAgent] 초안이 너무 짧음, 원본 응답 사용');
      draft = response;
    }

    console.log(`✅ [DraftAgent] 초안 생성 완료 (${draft.length}자)`);

    return {
      draft,
      topic,
      sourceText,  // 후속 에이전트용
      authorName,
      authorTitle
    };
  }

  buildPrompt({ topic, sourceText, authorName, authorTitle, authorBio, category }) {
    // 참고자료가 길면 앞부분만 사용 (토큰 절약)
    const truncatedSource = sourceText.length > 5000
      ? sourceText.substring(0, 5000) + '\n\n[... 이하 생략 ...]'
      : sourceText;

    return `당신은 정치인의 블로그 글을 대필하는 전문 작가입니다.

## 작성자 정보
- 이름: ${authorName || '(미제공)'}
- 직함: ${authorTitle || '(미제공)'}

## 주제
${topic}

## 참고자료 (이것이 글의 핵심입니다)
${truncatedSource || '(참고자료 없음 - 주제만으로 작성)'}

## 작성 지침

1. **참고자료의 핵심 논점**을 파악하여 800~1200자 분량의 초안을 작성하세요.
2. **1인칭 화자**(작성자) 시점으로 작성하세요. "저는...", "우리는..."
3. **참고자료에 있는 구체적 사실**(인물명, 수치, 발언 인용)을 반드시 포함하세요.
4. **새로운 정보를 창작하지 마세요.** 참고자료에 없는 내용은 쓰지 마세요.
5. 아직 **구조화(서론/본론/결론)는 하지 마세요.** 핵심 내용만 서술하세요.
6. **HTML 태그 없이** 일반 텍스트로 작성하세요.

## 출력 형식
초안 내용만 출력하세요. 부연 설명이나 메타 코멘트 없이 본문만 작성하세요.`;
  }

  parseResponse(response) {
    if (!response) return '';

    // JSON 형식이면 content 추출
    try {
      const parsed = JSON.parse(response);
      if (parsed.content) return parsed.content;
      if (parsed.draft) return parsed.draft;
    } catch {
      // JSON이 아니면 그대로 사용
    }

    // 마크다운 코드블록 제거
    let cleaned = response
      .replace(/```[\s\S]*?```/g, '')
      .replace(/`/g, '')
      .trim();

    return cleaned;
  }
}

module.exports = { DraftAgent };
