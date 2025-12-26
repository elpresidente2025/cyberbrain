/**
 * functions/prompts/title-generation.js
 * 제목 생성 프롬프트 템플릿
 */

'use strict';

const { getElectionStage } = require('../guidelines/legal');

/**
 * 본문 내용 기반 제목 생성 프롬프트를 빌드합니다
 * @param {Object} params - 프롬프트 빌드에 필요한 파라미터
 * @param {string} params.contentPreview - 본문 미리보기 (HTML 태그 제거됨)
 * @param {string} params.backgroundText - 배경정보 텍스트
 * @param {string} params.topic - 주제
 * @param {string} params.fullName - 작성자 이름
 * @param {Array<string>} params.keywords - 필수 키워드 목록
 * @param {string} params.category - 카테고리
 * @param {string} params.subCategory - 하위 카테고리
 * @param {string} params.status - 사용자 상태 (준비/현역/예비/후보)
 * @returns {string} 완성된 제목 생성 프롬프트
 */
function buildTitlePrompt({ contentPreview, backgroundText, topic, fullName, keywords, userKeywords, category, subCategory, status }) {
  // 선거법 단계 확인 (준비/현역은 STAGE_1)
  const electionStage = getElectionStage(status);
  const isPreCandidate = electionStage?.name === 'STAGE_1'; // 준비/현역 단계

  // 카테고리별 제목 가이드라인 (선거법 준수 반영)
  const categoryGuides = {
    'daily-communication': {
      'gratitude_message': '감사 메시지: "~에 감사드립니다", "고마운 마음을 전합니다", "따뜻한 격려에 감사합니다" 스타일. 감사와 따뜻함이 느껴지는 제목',
      'encouragement_support': '격려 및 응원: "함께 이겨냅시다", "응원합니다", "힘내세요" 스타일',
      'celebration_congratulation': '축하 및 기념: "축하드립니다", "뜻깊은 순간", "기념하며" 스타일',
      'daily_life_sharing': '일상 공유: "~한 하루", "~를 만나다", "~한 시간" 스타일'
    },
    'current-affairs': {
      'current_affairs_commentary': '시사 논평: "~의 문제점", "~왜 불참했나?", "~에 대한 입장" 스타일',
      'fake_news_rebuttal': '가짜뉴스 반박: "사실이 아닙니다", "진실은", "왜곡된 ~" 스타일'
    },
    'activity-report': {
      'performance_report': '성과 보고: "~확보했습니다", "~달성했습니다", "예산 XX억 확보" 스타일',
      'parliamentary_audit_report': '국정감사: "국정감사에서 ~", "지적했습니다", "시정 요구" 스타일',
      'bill_ordinance_report': '법안/조례: "~법안 발의", "~조례 제정", "제도 개선" 스타일'
    },
    'local-issues': {
      'local_issue_analysis': '지역 현안: "~문제, 이렇게 해결", "~의 실태", "현장에서" 스타일',
      'event_complaint_report': '행사/민원: "~행사 개최", "민원 해결", "주민과 함께" 스타일',
      'volunteering_review': '봉사 후기: "~에서의 하루", "봉사하며 느낀", "함께한 시간" 스타일'
    },
    'policy-proposal': {
      // 준비/현역 단계에서는 '약속', '공약' 금지
      'policy_pledge_announcement': isPreCandidate
        ? '정책 제안: "~정책 방향 제시", "~을 연구하겠습니다", "~비전 공유" 스타일 (⚠️ "약속", "공약" 표현 금지)'
        : '정책/공약: "~정책 제안", "~하겠습니다" 스타일',
      'vision_philosophy_declaration': '비전/철학: "~을 꿈꾸며", "제가 그리는 미래", "신념" 스타일'
    }
  };

  const categoryGuide = categoryGuides[category]?.[subCategory] || '본문의 핵심 내용을 반영하여 작성';

  // 선거법 준수 지시문 (준비/현역 단계일 때만)
  const electionComplianceInstruction = isPreCandidate ? `
---

[⚠️ 선거법 준수 - 필수]
**현재 상태: ${status} (예비후보 등록 이전)**
제목에서 다음 표현을 절대 사용하지 마세요:
❌ "약속", "공약", "~하겠습니다" (공약성 표현)
❌ "당선되면", "당선 후"
❌ "지지해 주십시오", "함께해 주십시오"

✅ 대신 사용할 표현:
- "정책 방향", "비전", "연구하겠습니다"
- "노력하겠습니다", "추진하겠습니다"

` : '';

  return `[제목 생성 가이드]
너는 본문 내용의 핵심을 담아, 아래 원칙과 예시를 깊이 학습하여 가장 효과적인 제목을 만들어야 한다.
${electionComplianceInstruction}
---

[🎯 카테고리별 제목 스타일 가이드]
**현재 카테고리: ${category} → ${subCategory}**
**제목 스타일 가이드: ${categoryGuide}**

⚠️ 중요: 이 카테고리 스타일을 반드시 준수하세요. 본문 내용이 다른 주제를 다루더라도, 제목은 이 카테고리에 맞는 스타일로 작성해야 합니다.

---

[✅ 제목 생성 핵심 원칙]
1. **키워드 전진 배치**: 가장 중요한 핵심 키워드(지역명, 정책명, 인물 등)를 제목의 가장 앞부분에 배치하여 검색 노출과 독자의 주목도를 극대화하라.
2. **숫자로 증명**: 예산, 기간, 통계, D-day, N가지 방법 등 구체적인 숫자를 활용하여 성과를 증명하고 신뢰도를 높여라.
3. **문제 해결 제시**: 독자(주민)가 겪는 문제(Pain Point)를 직접 언급하고, 그것을 어떻게 해결해 줄 수 있는지 명확하게 보여주어라. (예: 'OOO 문제, OOO으로 해결!')
4. **호기심 자극**: '왜 OOO일까?', '~해도 괜찮을까?' 등 질문을 던지거나, 통념을 뒤집는 반전 효과를 활용하여 독자의 클릭을 유도하라.
5. **가치/감성 포함**: ${isPreCandidate ? "'눈물', '우리', '희망' 등 감성어 활용 (⚠️ '약속' 금지)" : "'약속', '눈물', '반드시', '우리' 등 긍정적/부정적 감성어를 활용"}하여 독자의 공감대를 형성하고 지지를 유도하라.

---

[👍 좋은 제목 예시 (Few-shot)]
${isPreCandidate ? `- "신월동 상습 침수 문제, 빗물 저류 시설 확충(예산 120억)으로 해결 추진"
- "국비 50억 확보! OOO 체육센터 건립 확정, 주민과 함께 이뤄낸 성과"
- "시민의 혈세 100억, 정말 '이곳'에 쓰는 것이 최선입니까?"
- "지난 5년간 아동 병원 30% 급감, 우리 아이들이 갈 곳이 없습니다. (데이터 분석)"
- "정치를 시작했던 그날의 초심을 떠올리게 해준 한 통의 손편지."` : `- "신월동 상습 침수 문제, 빗물 저류 시설 확충(예산 120억)으로 해결하겠습니다."
- "주민 여러분과의 약속, 드디어 해냈습니다! 국비 50억 확보로 OOO 체육센터 건립 확정."
- "시민의 혈세 100억, 정말 '이곳'에 쓰는 것이 최선입니까?"
- "지난 5년간 아동 병원 30% 급감, 우리 아이들이 갈 곳이 없습니다. (데이터 분석)"
- "정치를 시작했던 그날의 초심을 떠올리게 해준 한 통의 손편지."`}

---

[👎 나쁜 제목 예시 (절대 금지)]
- "미래를 위한 정책 제안" (Critique: 너무 추상적이고 구체적인 내용이 없음. 무슨 정책인지 알 수 없음.)
- "최선을 다해 뛰었습니다" (Critique: 구체적인 성과(숫자, 결과)가 없어 신뢰도가 떨어짐.)
- "OOO는 각성하라" (Critique: 근거 없는 비난이며, 감정적인 구호에 그쳐 논리적이지 않음.)
${isPreCandidate ? `- "OOO 약속드립니다" (Critique: ⚠️ 선거법 위반 - 예비후보 등록 전 공약성 표현 금지)
- "당선되면 OOO 하겠습니다" (Critique: ⚠️ 선거법 위반 - 예비후보 등록 전 사용 불가)` : ''}

---

[본문 정보]
본문 내용 (일부):
${contentPreview}

배경정보 핵심:
${backgroundText.substring(0, 500)}

주제: ${topic}
작성자: ${fullName}

⚠️ **필수 포함 키워드 (최우선 - 사용자 지정)**:
${userKeywords && userKeywords.length > 0 ? userKeywords.join(', ') : '(지정 없음)'}
→ 이 키워드들은 사용자가 직접 입력한 "노출 희망 검색어"입니다.
   제목에 이 중 최소 1개는 **반드시 정확하게** 포함되어야 합니다.

참고 키워드 (선택):
${userKeywords && userKeywords.length > 0 ? keywords.filter(k => !userKeywords.includes(k)).slice(0, 5).join(', ') : keywords.slice(0, 5).join(', ')}

---

[🚨 CRITICAL - 최종 요구사항]

⚠️⚠️⚠️ 제목 길이: 20~30자 이내 (절대 엄수!) ⚠️⚠️⚠️
→ 30자를 초과하면 네이버/구글 검색결과에서 잘립니다. 반드시 30자 이내로!
→ 작성 후 반드시 글자 수를 세어보세요.

1. **필수 포함 키워드** 중 최소 1개는 **반드시** 제목에 포함 (최우선 조건)
2. 핵심 메시지를 압축하여 짧고 강렬하게 표현
3. 부제목(:, -)은 절대 사용 금지 - 제목이 길어지는 주요 원인!
4. "~에 대한", "~관련" 같은 불필요한 표현 제거

**출력 형식: 순수한 제목 텍스트만. 따옴표, 기호, 설명 없이.**

제목:`;
}

module.exports = {
  buildTitlePrompt,
};
