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
    const currentLength = content.replace(/<[^>]*>/g, '').replace(/\s/g, '').length;
    const minLength = targetWordCount;
    const maxLength = Math.round(targetWordCount * 1.25);

    console.log(`📊 [StyleAgent] 현재 분량: ${currentLength}자 (목표: ${minLength}~${maxLength})`);

    // 분량 체크
    const needsExpansion = currentLength < minLength;
    const needsTrimming = currentLength > maxLength;

    // 말투 교정 필요 여부 (간단한 패턴 체크)
    const needsStyleFix = this.checkStyleIssues(content);

    if (!needsExpansion && !needsTrimming && !needsStyleFix) {
      console.log('✅ [StyleAgent] 분량/스타일 양호 - 스킵');
      return { content, title, keywordCounts, finalLength: currentLength };
    }

    // 프롬프트 생성
    const prompt = this.buildPrompt({
      content,
      currentLength,
      minLength,
      maxLength,
      needsExpansion,
      needsTrimming,
      userProfile
    });

    console.log(`📝 [StyleAgent] 프롬프트 생성 완료 (${prompt.length}자)`);

    // LLM 호출
    const response = await callGenerativeModel(prompt, 1, 'gemini-2.5-flash', true, 3500);

    // 응답 파싱
    const styled = this.parseResponse(response, content);

    const finalLength = styled.replace(/<[^>]*>/g, '').replace(/\s/g, '').length;
    console.log(`✅ [StyleAgent] 스타일 교정 완료 (${currentLength}자 → ${finalLength}자)`);

    return {
      content: styled,
      title,
      keywordCounts,
      finalLength
    };
  }

  buildPrompt({ content, currentLength, minLength, maxLength, needsExpansion, needsTrimming, userProfile }) {
    const authorName = userProfile?.name || userProfile?.displayName || '화자';

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

## 작성자: ${authorName}

## 현재 본문
${content}

${lengthInstruction}

## 말투 교정 규칙

1. **확신에 찬 어조** 사용:
   - ❌ "~라고 생각합니다" → ✅ "~입니다"
   - ❌ "~할 것입니다" → ✅ "~하겠습니다"
   - ❌ "노력하겠습니다" → ✅ "반드시 해내겠습니다"

2. **3자 관찰 표현 금지**:
   - ❌ "~라는 점입니다", "~상황입니다", "~것으로 보입니다"
   - ✅ 당사자로서 직접 말하는 어조

3. **기계적 반복 금지**:
   - 같은 문장 구조가 연속되면 변형
   - 단, 수사학적 반복(대구법, 점층법)은 OK

4. **HTML 구조 유지**: <h2>, <p> 태그 보존

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

    // HTML 태그가 있으면 그대로 사용
    if (response.includes('<p>') || response.includes('<h2>')) {
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
