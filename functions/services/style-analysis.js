/**
 * functions/services/style-analysis.js (개편안)
 * 사용자의 자기소개(bio) 텍스트를 분석하여, 시스템에 정의된 '글쓰기 부품' ID와
 * 가장 일치하는 스타일 프로필을 생성하는 '스타일 분석 에이전트'입니다.
 */

'use strict';

const { callGenerativeModel } = require('./gemini');
const { logError } = require('../common/log');

// 분석의 기준이 될 글쓰기 부품 라이브러리를 직접 가져옵니다.
const { EMOTIONAL_ARCHETYPES, NARRATIVE_FRAMES } = require('../prompts/templates/daily-communication');
const { LOGICAL_STRUCTURES } = require('../prompts/templates/policy-proposal');
// ... 다른 작법 모듈들도 필요에 따라 추가 가능

/**
 * @function analyzeBioForStyle
 * @description 자기소개 텍스트를 분석하여 최적의 글쓰기 부품 ID 조합을 반환합니다.
 * @param {string} bioText 사용자의 자기소개 글
 * @returns {Promise<object|null>} 분석된 스타일 프로필 객체(부품 ID 조합) 또는 실패 시 null
 */
async function analyzeBioForStyle(bioText) {
  if (!bioText || bioText.trim().length < 50) {
    console.log('분석하기에 자기소개 글이 너무 짧습니다.');
    return null;
  }

  // AI에게 전달할 선택지를 동적으로 생성합니다.
  const emotionalArchetypeOptions = Object.values(EMOTIONAL_ARCHETYPES).map(a => `- ${a.id}: ${a.name}`).join('\n');
  const narrativeFrameOptions = Object.values(NARRATIVE_FRAMES).map(f => `- ${f.id}: ${f.name}`).join('\n');
  const logicalStructureOptions = Object.values(LOGICAL_STRUCTURES).map(s => `- ${s.id}: ${s.name}`).join('\n');

  const analysisPrompt = `
    # 역할
    당신은 정치인의 글쓰기 스타일을 분석하여, 그들의 글을 구성하는 핵심 '글쓰기 부품'을 찾아내는 최고의 분석가입니다. 주어진 자기소개 글을 깊이 있게 분석하여, 아래 제시된 선택지 중에서 글쓴이의 스타일과 가장 일치하는 부품 ID를 각각 하나씩 선택해주세요.

    # 분석할 글
    "${bioText}"

    # 선택지 라이브러리

    ## 1. 감성 원형 (emotionalArchetypeId) - 글에 담긴 핵심 감정
    ${emotionalArchetypeOptions}

    ## 2. 서사 프레임 (narrativeFrameId) - 이야기를 전개하는 방식 (감성적 글)
    ${narrativeFrameOptions}

    ## 3. 논리 구조 (logicalStructureId) - 주장을 펼치는 방식 (논리적 글)
    ${logicalStructureOptions}

    # 최종 임무
    위 분석을 바탕으로, 글쓴이의 글쓰기 DNA와 가장 일치하는 부품 ID들을 아래 JSON 형식으로 출력해주세요. 글의 성격에 따라 '서사 프레임'과 '논리 구조' 중 더 두드러지는 하나를 중심으로 판단하세요.

    # 출력 형식 (오직 JSON 객체만 출력)
    {
      "emotionalArchetypeId": "...",
      "narrativeFrameId": "...",
      "logicalStructureId": "..."
    }
  `;

  try {
    const rawResult = await callGenerativeModel(analysisPrompt);
    const jsonString = rawResult.match(/{[\s\S]*}/)[0];
    const styleProfile = JSON.parse(jsonString);
    console.log('✅ 스타일 분석 성공 (부품 ID 매칭):', styleProfile);
    return styleProfile;
  } catch (error) {
    logError('analyzeBioForStyle', '스타일 분석 실패', { error: error.message });
    return null;
  }
}

module.exports = { analyzeBioForStyle };
