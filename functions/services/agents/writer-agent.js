'use strict';

/**
 * Writer Agent - 초안 작성
 *
 * 역할:
 * - 주어진 컨텍스트로 초안 작성
 * - 개인화된 스타일 적용
 * - 구조화된 콘텐츠 생성
 */

const { BaseAgent } = require('./base');
const { GoogleGenerativeAI } = require('@google/generative-ai');

let genAI = null;
function getGenAI() {
  if (!genAI) {
    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) return null;
    genAI = new GoogleGenerativeAI(apiKey);
  }
  return genAI;
}

class WriterAgent extends BaseAgent {
  constructor() {
    super('WriterAgent');
  }

  getRequiredContext() {
    return ['topic', 'category', 'prompt'];
  }

  async execute(context) {
    const {
      prompt,
      targetWordCount = 1500,
      previousResults = {}
    } = context;

    const ai = getGenAI();
    if (!ai) {
      throw new Error('Gemini API 키가 설정되지 않았습니다');
    }

    // 키워드 에이전트 결과 활용
    const keywords = previousResults.KeywordAgent?.data?.keywords || [];
    const keywordHint = keywords.length > 0
      ? `\n\n[핵심 키워드 (자연스럽게 포함): ${keywords.slice(0, 5).map(k => k.keyword || k).join(', ')}]`
      : '';

    const enhancedPrompt = prompt + keywordHint;

    const model = ai.getGenerativeModel({ model: 'gemini-1.5-flash' });

    const result = await model.generateContent({
      contents: [{ role: 'user', parts: [{ text: enhancedPrompt }] }],
      generationConfig: {
        temperature: 0.8,
        maxOutputTokens: Math.min(targetWordCount * 2, 4000)
      }
    });

    const content = result.response.text();

    return {
      content,
      wordCount: content.replace(/<[^>]*>/g, '').length,
      keywordsUsed: keywords.slice(0, 5).map(k => k.keyword || k)
    };
  }
}

module.exports = { WriterAgent };
