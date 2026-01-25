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

    // 🔄 재시도 로직
    const MAX_RETRIES = 2;
    const MIN_LENGTH = 600; // 최소 600자 이상
    let attempt = 0;
    let feedback = '';
    let draft = '';

    while (attempt <= MAX_RETRIES) {
      attempt++;
      console.log(`🔄 [DraftAgent] 시도 ${attempt}/${MAX_RETRIES + 1}`);

      // 프롬프트 생성 (피드백 포함)
      let currentPrompt = prompt;
      if (feedback) {
        currentPrompt += `\n\n🚨 [중요] 이전 시도가 다음 이유로 반려되었습니다:\n"${feedback}"\n\n위 지적 사항을 반드시 반영하여 다시 작성하세요.`;
      }

      console.log(`📝 [DraftAgent] 프롬프트 생성 완료 (${currentPrompt.length}자)`);

      // LLM 호출 (JSON 모드 OFF - 일반 텍스트 출력)
      const response = await callGenerativeModel(currentPrompt, 1, 'gemini-2.5-flash', false, 2000);

      // 응답 파싱
      draft = this.parseResponse(response);

      // 검증
      if (draft && draft.length >= MIN_LENGTH) {
        console.log(`✅ [DraftAgent] 초안 생성 완료 (${draft.length}자)`);
        break;
      }

      // 너무 짧으면 재시도
      console.warn(`⚠️ [DraftAgent] 초안이 너무 짧음 (${draft?.length || 0}/${MIN_LENGTH}자)`);
      feedback = `초안이 ${draft?.length || 0}자로 너무 짧습니다. 반드시 ${MIN_LENGTH}자 이상, 목표 800~1200자로 상세하게 작성해주세요. 참고자료의 핵심 내용을 충실히 반영하세요.`;

      if (attempt > MAX_RETRIES) {
        // 마지막 시도에서도 실패하면 경고하고 진행
        console.warn(`⛔ [DraftAgent] 재시도 초과, 짧은 초안으로 진행 (${draft?.length || 0}자)`);
        if (!draft || draft.length < 100) {
          throw new Error(`DraftAgent 초안 생성 실패: 응답이 너무 짧음 (${draft?.length || 0}자)`);
        }
      }
    }

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

    // 마크다운 코드블록 제거
    let cleaned = response
      .replace(/```[\s\S]*?```/g, '')
      .replace(/`/g, '')
      .trim();

    return cleaned;
  }
}

module.exports = { DraftAgent };
