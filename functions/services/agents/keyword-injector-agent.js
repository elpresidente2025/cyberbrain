'use strict';

/**
 * KeywordInjectorAgent - 검색어를 섹션당 1개씩 삽입
 *
 * 🔧 v3: 섹션 기반 삽입으로 재설계
 * - 각 섹션(도입부, 본론1~N, 결말부)에 정확히 1개의 키워드 삽입
 * - 섹션 내 키워드 미만/초과 금지
 *
 * 입력: 구조화된 본문(content), 검색어(userKeywords)
 * 출력: 검색어가 삽입된 본문 (섹션당 1개)
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

  /**
   * 키워드당 최소 삽입 목표 계산
   * 키워드 2개 기준: 각 3~4회, 총합 7~8회 (15문단 기준 약 2문단당 1회)
   */
  getMinTarget(content, sectionCount, keywordCount = 1) {
    const perKeyword = keywordCount >= 2 ? 3 : 5;
    return Math.max(sectionCount, perKeyword);
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

    const { content, title, sourceText, contextAnalysis } = structureResult;

    // 검색어가 없으면 그대로 반환
    if (!userKeywords || userKeywords.length === 0) {
      console.log('⏭️ [KeywordInjectorAgent] 검색어 없음 - 스킵');
      return { content, title, keywordCounts: {} };
    }

    // 섹션 파싱
    const sections = this.parseSections(content);
    console.log(`📊 [KeywordInjectorAgent] 섹션 ${sections.length}개 파싱 완료`);

    // 최소 삽입 목표 계산
    const minTarget = this.getMinTarget(content, sections.length, userKeywords.length);
    console.log(`📊 [KeywordInjectorAgent] 최소 삽입 목표: 각 ${minTarget}회 (키워드 ${userKeywords.length}개, 섹션 ${sections.length}개)`);

    // 섹션별 키워드 카운트
    const sectionCounts = this.countKeywordsPerSection(sections, userKeywords);
    const totalCounts = this.countKeywords(content, userKeywords);

    // 초기 상태 로깅
    console.log(`📊 [KeywordInjectorAgent] 초기 상태:`, {
      sections: sections.length,
      totalCounts,
      sectionCounts: sectionCounts.map((sc, i) => `섹션${i}: ${JSON.stringify(sc)}`)
    });

    // 이미 균형이면 바로 리턴
    if (this.validateSectionBalance(sectionCounts, userKeywords, minTarget).passed) {
      console.log('✅ [KeywordInjectorAgent] 초기 상태부터 키워드 균형 충족');
      return { content, title, keywordCounts: totalCounts, sourceText };
    }

    // 🔄 재시도 로직
    const MAX_RETRIES = 2;
    let attempt = 0;
    let currentContent = content;
    let feedback = '';

    while (attempt <= MAX_RETRIES) {
      attempt++;
      console.log(`🔄 [KeywordInjectorAgent] 시도 ${attempt}/${MAX_RETRIES + 1}`);

      // 프롬프트 생성 (섹션 기반)
      const prompt = this.buildPrompt({
        sections,
        userKeywords,
        sectionCounts,
        feedback,
        contextAnalysis,
        minTarget
      });

      console.log(`📝 [KeywordInjectorAgent] 프롬프트 생성 완료 (${prompt.length}자)`);

      // LLM 호출 (JSON 모드)
      const response = await callGenerativeModel(prompt, 1, 'gemini-2.5-flash', true, 2000);

      // 응답 파싱
      const instructions = this.parseInstructions(response);

      if (!instructions || instructions.length === 0) {
        console.warn('⚠️ [KeywordInjectorAgent] 유효한 지시 없음 - 재시도');
        feedback = '유효한 삽입/삭제 지시가 없었습니다. 다시 시도하세요.';
        continue;
      }

      console.log(`📋 [KeywordInjectorAgent] ${instructions.length}개 지시 파싱됨`);

      // 지시 적용
      currentContent = this.applyInstructions(content, sections, instructions);

      // 재검증
      const newSections = this.parseSections(currentContent);
      const newSectionCounts = this.countKeywordsPerSection(newSections, userKeywords);
      const newTotalCounts = this.countKeywords(currentContent, userKeywords);

      const validation = this.validateSectionBalance(newSectionCounts, userKeywords, minTarget);

      if (validation.passed) {
        console.log(`✅ [KeywordInjectorAgent] 키워드 균형 달성:`, newTotalCounts);
        return {
          content: currentContent,
          title,
          keywordCounts: newTotalCounts,
          sourceText
        };
      }

      // 검증 실패 → 피드백 업데이트
      feedback = validation.feedback;
      console.log(`⚠️ [KeywordInjectorAgent] 검증 실패: ${feedback}`);

      if (attempt > MAX_RETRIES) {
        console.warn('⛔ [KeywordInjectorAgent] 재시도 횟수 초과 - 현재 결과 반환');
        return {
          content: currentContent,
          title,
          keywordCounts: newTotalCounts,
          sourceText
        };
      }
    }

    // fallback: 원본 반환
    return { content, title, keywordCounts: totalCounts, sourceText };
  }

  /**
   * HTML 본문에서 섹션 추출 (h2 태그 기준)
   * - 첫 h2 이전 = 도입부 (intro)
   * - h2 ~ 다음 h2 = 본론 (body1, body2, ...)
   * - 마지막 h2 이후 = 결말부 (conclusion)
   */
  parseSections(content) {
    const sections = [];

    // h2 태그 위치 찾기
    const h2Regex = /<h2[^>]*>[\s\S]*?<\/h2>/gi;
    const h2Matches = [...content.matchAll(h2Regex)];

    if (h2Matches.length === 0) {
      // h2가 없으면 전체를 하나의 섹션으로
      sections.push({
        type: 'single',
        startIndex: 0,
        endIndex: content.length,
        content: content
      });
      return sections;
    }

    // 도입부 (첫 h2 이전)
    const firstH2Start = h2Matches[0].index;
    if (firstH2Start > 0) {
      sections.push({
        type: 'intro',
        startIndex: 0,
        endIndex: firstH2Start,
        content: content.substring(0, firstH2Start)
      });
    }

    // 본론들 (각 h2 ~ 다음 h2)
    for (let i = 0; i < h2Matches.length; i++) {
      const startIndex = h2Matches[i].index;
      const endIndex = i < h2Matches.length - 1
        ? h2Matches[i + 1].index
        : content.length;

      // 마지막 섹션인지 확인 (결말부)
      const isLast = i === h2Matches.length - 1;

      sections.push({
        type: isLast ? 'conclusion' : `body${i + 1}`,
        startIndex,
        endIndex,
        content: content.substring(startIndex, endIndex)
      });
    }

    return sections;
  }

  /**
   * 섹션별 키워드 카운트
   */
  countKeywordsPerSection(sections, keywords) {
    return sections.map(section => {
      const counts = {};
      const plainText = section.content.replace(/<[^>]*>/g, ' ').toLowerCase();

      for (const keyword of keywords) {
        const regex = new RegExp(keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
        const matches = plainText.match(regex);
        counts[keyword] = matches ? matches.length : 0;
      }

      return { type: section.type, counts };
    });
  }

  /**
   * 전체 키워드 카운트
   */
  countKeywords(content, keywords) {
    const counts = {};
    const plainText = content.replace(/<[^>]*>/g, ' ').toLowerCase();

    for (const keyword of keywords) {
      const regex = new RegExp(keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
      const matches = plainText.match(regex);
      counts[keyword] = matches ? matches.length : 0;
    }

    return counts;
  }

  /**
   * 삽입/삭제 지시 프롬프트 생성 (섹션 기반)
   */
  buildPrompt({ sections, userKeywords, sectionCounts, feedback, contextAnalysis, minTarget }) {
    const effectiveMinTarget = minTarget || sections.length;

    // 섹션별 현황
    const sectionStatus = sectionCounts.map((sc, i) => {
      const keywordInfo = userKeywords.map(kw => `${kw}: ${sc.counts[kw] || 0}회`).join(', ');
      return `[섹션 ${i}] ${sc.type}: ${keywordInfo}`;
    }).join('\n');

    // Per-keyword totals
    const kwTotals = {};
    for (const kw of userKeywords) {
      kwTotals[kw] = sectionCounts.reduce((sum, sc) => sum + (sc.counts[kw] || 0), 0);
    }

    // 문제 섹션 파악
    const problems = [];
    for (let i = 0; i < sectionCounts.length; i++) {
      for (const keyword of userKeywords) {
        const count = sectionCounts[i].counts[keyword] || 0;
        if (count === 0) {
          problems.push(`섹션 ${i} (${sectionCounts[i].type}): "${keyword}" 0회 → 1회 삽입 필요`);
        } else if (count > 2) {
          problems.push(`섹션 ${i} (${sectionCounts[i].type}): "${keyword}" ${count}회 → 삭제 필요`);
        }
      }
    }

    // Total deficit
    for (const kw of userKeywords) {
      const total = kwTotals[kw];
      if (total < effectiveMinTarget) {
        const deficit = effectiveMinTarget - total;
        problems.push(`전체 "${kw}": ${total}회 → ${deficit}회 추가 삽입 필요 (목표 ${effectiveMinTarget}회)`);
      }
    }

    // 키워드별 톤 지시 생성
    let toneInstruction = '';
    if (contextAnalysis) {
      const { responsibilityTarget, expectedTone } = contextAnalysis;
      if (responsibilityTarget && expectedTone) {
        // 키워드가 비판 대상과 일치하는지 확인
        const criticalKeywords = userKeywords.filter(kw =>
          responsibilityTarget.includes(kw) || kw.includes(responsibilityTarget)
        );
        if (criticalKeywords.length > 0) {
          toneInstruction = `\n## ⚠️ 톤 지시 (필수)
이 원고의 논조: "${expectedTone}"
비판/요구 대상: "${responsibilityTarget}"
→ "${criticalKeywords.join('", "')}" 키워드는 **${expectedTone}적 맥락**으로 작성할 것
→ 절대 우호적/존경하는 표현 금지 (예: "존경", "감사", "성과", "노력" 등)`;
        }
      }
    }

    let prompt = `검색어가 전체 ${effectiveMinTarget}회 이상, 각 섹션에 최소 1회 등장하도록 새 문장을 생성하세요.

## 검색어
${userKeywords.map(kw => `- "${kw}" (현재 ${kwTotals[kw] || 0}회, 목표 ${effectiveMinTarget}회 이상)`).join('\n')}

## 현재 섹션별 현황
${sectionStatus}

## 필요한 조정
${problems.length > 0 ? problems.join('\n') : '조정 불필요'}
${toneInstruction}

## 규칙
1. **각 섹션 최소 1회**: 검색어가 0회인 섹션에 반드시 삽입
2. **전체 합계 ${effectiveMinTarget}회 이상**: 부족하면 긴 섹션에 추가 삽입 (한 섹션 최대 2회)
3. **검색어 원문 유지**: "${userKeywords[0]}" 형태 그대로 사용 (띄어쓰기, 조사 변경 금지)
4. **짧은 한 문장만 생성**: 30자 내외의 짧은 문장 하나만 생성 (절대 문단 금지)
5. **기존 텍스트 복사 금지**: 원고의 기존 문장을 절대 복사하거나 포함하지 말 것
6. **위치 지정**: 섹션 번호와 동작(insert/delete) 명시

## 출력 형식 (JSON)
{"instructions":[{"section":0,"action":"insert","sentence":"검색어가 포함된 짧은 한 문장"}]}

⚠️ 조정이 필요 없으면: {"instructions":[]}
⚠️ sentence는 30자 내외, 줄바꿈/따옴표 금지, 한 줄로 작성`;

    if (feedback) {
      prompt += `\n\n🚨 이전 시도 실패: ${feedback}`;
    }

    return prompt;
  }

  /**
   * LLM 응답에서 지시 파싱
   */
  parseInstructions(response) {
    if (!response) return null;

    try {
      let jsonStr = response;

      // 코드블록 제거
      const codeBlockMatch = response.match(/```(?:json)?\s*([\s\S]*?)```/);
      if (codeBlockMatch) {
        jsonStr = codeBlockMatch[1].trim();
      }

      // JSON 문자열 정리 (줄바꿈, 제어문자 제거)
      jsonStr = jsonStr
        .replace(/[\r\n]+/g, ' ')  // 줄바꿈을 공백으로
        .replace(/\t/g, ' ')       // 탭을 공백으로
        .replace(/\s+/g, ' ')      // 연속 공백 정리
        .trim();

      // JSON 객체 부분만 추출 시도
      const jsonMatch = jsonStr.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        jsonStr = jsonMatch[0];
      }

      const parsed = JSON.parse(jsonStr);
      const instructions = parsed.instructions || [];

      // 응답 검증: 문장 길이 및 품질 체크
      const validatedInstructions = instructions.filter(ins => {
        if (ins.action !== 'insert' || !ins.sentence) return true; // delete는 통과

        const sentence = ins.sentence.trim();

        // 1. 문장 길이 검증 (100자 초과 시 경고, 200자 초과 시 거부)
        if (sentence.length > 200) {
          console.warn(`⚠️ [KeywordInjectorAgent] 문장 너무 김 (${sentence.length}자) - 거부: "${sentence.substring(0, 50)}..."`);
          return false;
        }
        if (sentence.length > 100) {
          console.warn(`⚠️ [KeywordInjectorAgent] 문장 길이 경고 (${sentence.length}자): "${sentence.substring(0, 50)}..."`);
        }

        // 2. 복사 패턴 감지 (잘린 텍스트 "..." 패턴)
        if (sentence.includes('...') && sentence.indexOf('...') < sentence.length - 5) {
          console.warn(`⚠️ [KeywordInjectorAgent] 복사 패턴 감지 - 거부: "${sentence.substring(0, 50)}..."`);
          return false;
        }

        // 3. 인사말 복사 패턴 감지
        if (sentence.includes('존경하는') && sentence.includes('안녕하십니까')) {
          console.warn(`⚠️ [KeywordInjectorAgent] 인사말 복사 감지 - 거부`);
          return false;
        }

        return true;
      });

      if (validatedInstructions.length < instructions.length) {
        console.log(`📋 [KeywordInjectorAgent] ${instructions.length - validatedInstructions.length}개 지시 검증 실패로 제외`);
      }

      return validatedInstructions;
    } catch (e) {
      console.error('⚠️ [KeywordInjectorAgent] JSON 파싱 실패:', e.message);
      return null;
    }
  }

  /**
   * 지시 적용 (삽입/삭제)
   */
  applyInstructions(content, sections, instructions) {
    if (!instructions || instructions.length === 0) return content;

    let result = content;

    // 섹션 인덱스 내림차순 정렬 (뒤에서부터 처리하여 위치 변경 방지)
    const sortedInstructions = [...instructions].sort((a, b) => b.section - a.section);

    for (const ins of sortedInstructions) {
      const sectionIdx = ins.section;
      if (sectionIdx < 0 || sectionIdx >= sections.length) continue;

      const section = sections[sectionIdx];

      if (ins.action === 'insert' && ins.sentence) {
        // 섹션 끝에 새 문단 삽입
        const insertPos = section.endIndex;
        const newParagraph = `\n<p>${ins.sentence}</p>`;
        result = result.slice(0, insertPos) + newParagraph + result.slice(insertPos);

        console.log(`📝 [KeywordInjectorAgent] 섹션 ${sectionIdx}에 삽입: "${ins.sentence.substring(0, 50)}..."`);
      } else if (ins.action === 'delete' && ins.targetPhrase) {
        // 해당 문구가 포함된 문장 삭제 (주의: 전체 문단 삭제는 위험)
        // 여기서는 문구만 삭제하거나 동의어로 대체하는 방식이 더 안전
        console.log(`🗑️ [KeywordInjectorAgent] 섹션 ${sectionIdx}에서 삭제 시도: "${ins.targetPhrase}"`);
        // 삭제 로직은 복잡하므로 일단 스킵 (삽입 우선)
      }
    }

    return result;
  }

  /**
   * 섹션별 균형 검증 (각 섹션 최소 1회 + 전체 합계 min_target 이상)
   */
  validateSectionBalance(sectionCounts, keywords, minTarget = null) {
    const issues = [];

    for (const keyword of keywords) {
      const totalKwCount = sectionCounts.reduce((sum, sc) => sum + (sc.counts[keyword] || 0), 0);

      // 1) 각 섹션에 최소 1회
      for (let i = 0; i < sectionCounts.length; i++) {
        const count = sectionCounts[i].counts[keyword] || 0;
        if (count === 0) {
          issues.push(`섹션 ${i} (${sectionCounts[i].type})에 "${keyword}" 없음 (1회 삽입 필요)`);
        }
      }

      // 2) 전체 합계가 minTarget 이상
      if (minTarget && totalKwCount < minTarget) {
        const deficit = minTarget - totalKwCount;
        issues.push(`전체 "${keyword}" ${totalKwCount}회 (최소 ${minTarget}회 필요, ${deficit}회 추가 필요)`);
      }

      // 3) 한 섹션에 3회 이상이면 과다 (2회까지 허용)
      for (let i = 0; i < sectionCounts.length; i++) {
        const count = sectionCounts[i].counts[keyword] || 0;
        if (count > 2) {
          issues.push(`섹션 ${i} (${sectionCounts[i].type})에 "${keyword}" ${count}회 (과다, 삭제 필요)`);
        }
      }
    }

    if (issues.length === 0) {
      return { passed: true };
    }

    return {
      passed: false,
      reason: `키워드 삽입 미달: ${issues.length}개 문제`,
      feedback: issues.join(', ')
    };
  }
}

module.exports = { KeywordInjectorAgent };
