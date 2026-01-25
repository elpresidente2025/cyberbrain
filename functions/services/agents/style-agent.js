'use strict';

/**
 * StyleAgent - 말투/어미 교정, 분량 조절
 *
 * 역할: 최종 본문의 말투를 교정하고 분량을 조절
 * 프롬프트 크기: ~5,000자
 *
 * 입력: 검색어 삽입된 본문(content), 사용자 프로필
 * 출력: 말투 교정 + 분량 조절된 최종 본문
 */

const { BaseAgent } = require('./base');
const { callGenerativeModel } = require('../gemini');

function stripHtml(text) {
  return String(text || '').replace(/<[^>]*>/g, '').replace(/\s+/g, '').trim();
}

function normalizeArtifacts(text) {
  if (!text) return text;
  let cleaned = String(text).trim();
  cleaned = cleaned.replace(/```[\s\S]*?```/g, '').trim();
  cleaned = cleaned.replace(/^\s*\\"/, '').replace(/\\"?\s*$/, '');
  cleaned = cleaned.replace(/^\s*["“]/, '').replace(/["”]\s*$/, '');
  cleaned = cleaned
    .replace(/카테고리:[\s\S]*$/m, '')
    .replace(/검색어 삽입 횟수:[\s\S]*$/m, '')
    .replace(/생성 시간:[\s\S]*$/m, '');
  cleaned = cleaned.replace(/^\s*\d+\s*자\s*$/gm, '');
  return cleaned.trim();
}

class StyleAgent extends BaseAgent {
  constructor() {
    super('StyleAgent');
  }

  getRequiredContext() {
    return ['previousResults', 'userProfile'];
  }

  async execute(context) {
    const {
      previousResults,
      userProfile,
      targetWordCount = 2000
    } = context;

    // KeywordInjectorAgent 결과 가져오기
    const keywordResult = previousResults?.KeywordInjectorAgent?.data;
    if (!keywordResult?.content) {
      throw new Error('KeywordInjectorAgent 결과가 없습니다');
    }

    const { content, title, keywordCounts } = keywordResult;

    // 현재 분량 확인
    const currentLength = stripHtml(content).length;
    const minLength = Math.max(1200, Math.floor(targetWordCount * 0.85));
    const targetMin = targetWordCount;
    // 목표 범위: ±10% (최대 1.1배까지만 허용)
    const maxLength = Math.floor(targetWordCount * 1.1);

    console.log(`📊 [StyleAgent] 현재 분량: ${currentLength}자 (목표: ${minLength}~${maxLength})`);

    // 분량 체크
    const needsExpansion = currentLength < targetMin;
    const needsTrimming = currentLength > maxLength;

    // 말투 교정 필요 여부 (간단한 패턴 체크)
    const needsStyleFix = this.checkStyleIssues(content);

    if (!needsExpansion && !needsTrimming && !needsStyleFix) {
      console.log('✅ [StyleAgent] 분량/스타일 양호 - 스킵');
      return { content, title, keywordCounts, finalLength: currentLength };
    }

    const maxAttempts = 2;
    let attempt = 0;
    let workingContent = content;
    let finalContent = content;
    let finalLength = currentLength;

    while (attempt < maxAttempts) {
      attempt += 1;
      const workingLength = stripHtml(workingContent).length;

      const prompt = this.buildPrompt({
        content: workingContent,
        currentLength: workingLength,
        minLength: targetMin,
        maxLength,
        needsExpansion: workingLength < targetMin,
        needsTrimming: workingLength > maxLength,
        userProfile
      });

      console.log(`📝 [StyleAgent] 프롬프트 생성 완료 (${prompt.length}자, 시도 ${attempt}/${maxAttempts})`);

      // LLM 호출 (JSON 모드 OFF - HTML 직접 출력)
      const response = await callGenerativeModel(prompt, 1, 'gemini-2.5-flash', false, 4000);
      const styled = this.parseResponse(response, workingContent);

      const styledLength = stripHtml(styled).length;
      console.log(`✅ [StyleAgent] 스타일 교정 완료 (${workingLength}자 → ${styledLength}자)`);

      // 🛡️ Safety Check: 급격한 분량 감소(30% 이상)는 모델 붕괴로 간주
      if (styledLength < workingLength * 0.7) {
        console.warn(`⚠️ [StyleAgent] 모델 붕괴 감지 (분량 ${workingLength} -> ${styledLength}로 급감). 이번 시도를 무시하고 원본을 유지합니다.`);
        // 롤백하지만, 다음 시도를 위해 finalContent는 업데이트하지 않음 (혹은 루프 중단)
        // 여기서는 안전하게 롤백 후 루프 중단 (모델이 이 컨텍스트를 처리 못하는 것으로 판단)
        finalContent = workingContent;
        finalLength = workingLength;
        break;
      }

      finalContent = normalizeArtifacts(styled);
      finalLength = styledLength;

      const stillShort = finalLength < minLength;
      const stillLong = finalLength > maxLength;

      // 검증 통과 시 조기 종료
      if (!stillShort && !stillLong) {
        break;
      }

      workingContent = finalContent;
    }

    // 🚨 Soft Fail: 분량이 부족해도 에러를 던지지 않고 최선의 결과 반환
    if (finalLength < minLength) {
      console.warn(`⚠️ [StyleAgent] 최종 분량 부족 (${finalLength}/${minLength}자). 에러 대신 현재 결과를 반환합니다.`);
    }

    return {
      content: finalContent,
      title,
      keywordCounts,
      finalLength
    };
  }

  buildPrompt({ content, currentLength, minLength, maxLength, needsExpansion, needsTrimming, userProfile, keywordCounts }) {
    const authorName = userProfile?.name || userProfile?.displayName || '화자';

    // 키워드 목록 추출 (보존해야 할 대상)
    const keywordsToPreserve = Object.keys(keywordCounts || {})
      .map(k => `- "${k}"`)
      .join('\n');

    let lengthInstruction = '';
    if (needsExpansion) {
      const deficit = minLength - currentLength;
      lengthInstruction = `
## 분량 확장 필요
현재 ${currentLength}자 → 최소 ${minLength}자 필요 (${deficit}자 추가)
- 기존 논점을 **더 깊이 설명**하세요 (예시, 근거 추가)
- **새로운 주제를 추가하지 마세요**
- 기존 문장을 풍부하게 확장하세요`;
    } else if (needsTrimming) {
      const excess = currentLength - maxLength;
      lengthInstruction = `
## 분량 축소 필요
현재 ${currentLength}자 → 최대 ${maxLength}자 이하 (${excess}자 삭제)
- 중복/반복 표현 제거
- 불필요한 수식어 삭제
- 핵심 논점은 유지`;
    }

    return `당신은 정치인 블로그 글의 최종 교정 전문가입니다.
아래 본문의 말투를 교정하고 분량을 조절해주세요.

⚠️ **[절대 원칙]**
1. **내용 요약 금지**: 전체 내용을 그대로 유지하며 서술만 다듬으세요.
2. **문단 삭제 금지**: 기존의 문단 구조(15개 내외)를 유지하세요.
3. **분량 보존**: 내용을 크게 줄이지 마세요.
4. **검색어(키워드) 절대 보존**: 아래 검색어는 SEO를 위해 필수적이므로 **절대 삭제하거나 변형하지 마십시오.**
${keywordsToPreserve}

## 작성자: ${authorName}

## 현재 본문
${content}

${lengthInstruction}

## 말투 교정 규칙

    1. ** 확신에 찬 어조 ** 사용:
    - ❌ "~라고 생각합니다" → ✅ "~입니다"
      - ❌ "~할 것입니다" → ✅ "~하겠습니다"
        - ❌ "노력하겠습니다" → ✅ "반드시 해내겠습니다"

    2. ** 3자 관찰 표현 금지 **:
    - ❌ "~라는 점입니다", "~상황입니다", "~것으로 보입니다"
      - ✅ 당사자로서 직접 말하는 어조

    3. ** 기계적 반복 금지 **:
    - 같은 문장 구조가 연속되면 변형
      - 단, 수사학적 반복(대구법, 점층법)은 OK

    4. ** HTML 구조 유지 **: <h2>, <p> 태그 보존

      ## 문법/표현 교정 규칙 (필수)

      1. **행정구역명+여러분 오류**:
      - ❌ "부산광역시 여러분" → ✅ "부산 시민 여러분"
      - ❌ "서울특별시 여러분" → ✅ "서울 시민 여러분"
      - 지역명 뒤에 "시민", "도민", "구민" 등을 반드시 붙여야 함

      2. **지역 중복 오류**:
      - ❌ "부울경 부산광역시" → ✅ "부울경" 또는 "부산광역시" (둘 중 하나만)
      - "부울경"은 이미 부산+울산+경남을 포함하므로 중복 금지

      3. **구어체 → 문어체 변환**:
      - ❌ "역부족인 거예요" → ✅ "역부족입니다"
      - ❌ "~인 거죠" → ✅ "~입니다"
      - ❌ "~거에요" → ✅ "~것입니다"

      4. **인용문 정리**:
      - 인용 시 따옴표 앞뒤 불필요한 공백 제거
      - ❌ '" 역부족인 거예요. "' → ✅ '"역부족입니다"'

      ## 출력 형식
      교정된 전체 본문만 출력하세요. 설명 없이 HTML 본문만 출력하세요.`;
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
      return response
        .replace(/```html?\s*/gi, '')
        .replace(/```/g, '')
        .trim();
    }

    console.warn('⚠️ [StyleAgent] 파싱 실패, 원본 유지');
    return original;
  }

  checkStyleIssues(content) {
    const issues = [
      // 말투 문제
      /라고 생각합니다/,
      /것으로 보입니다/,
      /라는 점입니다/,
      /상황입니다/,
      /노력하겠습니다/,
      /노력할 것입니다/,
      // 문법/표현 오류
      /부산광역시\s*여러분/,       // "부산광역시 시민 여러분"이 맞음
      /서울특별시\s*여러분/,
      /대구광역시\s*여러분/,
      /인천광역시\s*여러분/,
      /광주광역시\s*여러분/,
      /대전광역시\s*여러분/,
      /울산광역시\s*여러분/,
      /부울경\s*부산/,            // 부울경은 이미 부산 포함
      /역부족인\s*거/,            // 구어체
      /거예요/,                   // 구어체
      /거에요/,                   // 구어체
      /인\s*거죠/,                // 구어체
      /"\s+/,                     // 따옴표 뒤 불필요한 공백
      /\s+"/,                     // 따옴표 앞 불필요한 공백
    ];

    return issues.some(pattern => pattern.test(content));
  }
}

module.exports = { StyleAgent };
