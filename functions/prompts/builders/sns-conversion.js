/**
 * functions/prompts/builders/sns-conversion.js
 * SNS 플랫폼별 변환 프롬프트 생성
 */

'use strict';

// SNS 플랫폼별 제한사항 (공백 제외 글자수 기준)
const SNS_LIMITS = {
  'facebook-instagram': {
    maxLength: 1800,
    recommendedLength: 1800,
    hashtagLimit: 7,
    name: 'Facebook/Instagram'
  },
  x: {
    maxLength: 230,
    recommendedLength: 230,
    hashtagLimit: 2,
    name: 'X(Twitter)'
  },
  threads: {
    maxLength: 400,
    recommendedLength: 400,
    hashtagLimit: 3,
    name: 'Threads'
  }
};

/**
 * 원본 콘텐츠의 주제 유형 분석
 */
function analyzeContentType(content) {
  // 자기어필 중심 콘텐츠 키워드들
  const personalAppealKeywords = [
    '안녕하세요', '인사드립니다', '근황', '일상', '소통', '대화', '이야기',
    '지역', '현장', '방문', '만남', '간담회', '토론회', '설명회', '보고회',
    '주민', '시민', '구민', '동민', '마을', '우리동네', '지역구',
    '의정', '국감', '질의', '질문', '발언', '제안', '건의', '요청',
    '위원회', '본회의', '의정보고', '활동보고', '성과', '실적',
    '추진', '노력', '최선', '앞으로도', '계속', '지속',
    '저는', '제가', '개인적으로', '생각해보니', '느낀점', '다짐', '약속',
    '감사합니다', '부탁드립니다', '응원', '관심', '성원'
  ];

  // 정책/이슈 중심 콘텐츠 키워드들
  const policyIssueKeywords = [
    '정책', '제도', '법안', '예산', '계획', '방안', '대책',
    '경제', '교육', '복지', '보건', '환경', '교통', '안전',
    '개발', '투자', '지원', '확대', '개선', '강화', '추진',
    '문제', '과제', '해결', '검토', '논의', '결정',
    '정부', '정당', '의원', '장관', '시장', '도지사'
  ];

  let personalScore = 0;
  let policyScore = 0;

  personalAppealKeywords.forEach(keyword => {
    if (content.includes(keyword)) personalScore++;
  });

  policyIssueKeywords.forEach(keyword => {
    if (content.includes(keyword)) policyScore++;
  });

  return personalScore > policyScore || personalScore >= 3;
}

/**
 * 주제 유형과 플랫폼에 따른 콘텐츠 가공 가이드라인 생성
 */
function getContentFocusGuideline(isPersonalAppealContent, platform, userInfo) {
  if (isPersonalAppealContent) {
    if (platform === 'x') {
      return `- 자기어필이 글의 목적이므로 "${userInfo.name} ${userInfo.position}" 정체성 유지
- 하지만 230자 제약으로 핵심 활동/메시지만 압축하여 표현`;
    } else if (platform === 'threads') {
      return `- 자기어필 중심 글이므로 개인적 소통 톤 적절히 유지
- 400자 제약으로 핵심 활동과 소통 의지를 간결하게 표현`;
    }
  } else {
    if (platform === 'x') {
      return `- 정책/이슈 중심 글이므로 자기소개는 최소화하고 핵심 내용에 집중
- "${userInfo.name}"은 간단히 언급하되 대부분 분량을 주제 내용에 할당`;
    } else if (platform === 'threads') {
      return `- 정책/이슈 중심 글이므로 개인 어필보다 내용 전달에 집중
- 자기소개는 간략히, 대부분을 주제와 관련된 핵심 내용으로 구성`;
    }
  }
  return '';
}

/**
 * SNS 변환 프롬프트 생성
 * @param {string} originalContent - 원본 원고 내용
 * @param {string} platform - SNS 플랫폼 ('facebook-instagram', 'x', 'threads')
 * @param {Object} platformConfig - 플랫폼 설정
 * @param {string} postKeywords - 원고 키워드
 * @param {Object} userInfo - 사용자 정보 (name, position, region 등)
 * @returns {string} 완성된 SNS 변환 프롬프트
 */
function buildSNSPrompt(originalContent, platform, platformConfig, postKeywords = '', userInfo = {}) {
  // HTML 태그를 제거하고 평문으로 변환
  const cleanContent = originalContent
    .replace(/<\/?(h[1-6]|p|div|br|li)[^>]*>/gi, '\n')
    .replace(/<\/?(ul|ol)[^>]*>/gi, '\n\n')
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  // 플랫폼별 목표 글자수 설정 (공백 제외)
  const targetLength = Math.floor(platformConfig.maxLength * 0.85);

  // 원본 글의 주제 유형 분석
  const isPersonalAppealContent = analyzeContentType(cleanContent);

  // 플랫폼별 가공 방식 정의
  const platformInstructions = {
    'facebook-instagram': `원본 원고를 Facebook/Instagram 연동 게시에 맞게 가공:
- 원본의 핵심 내용과 논리 구조를 적절히 보존
- ${userInfo.name} ${userInfo.position}의 격식 있는 어조와 문체 유지
- 중요한 정책, 수치, 사례는 반드시 포함
- 분량이 충분하므로 적절한 자기 소개와 마무리 포함 가능
- Facebook 게시 + Instagram 연동을 고려한 완성도 있는 구성
- ${platformConfig.maxLength}자 이내로 품격 있게 가공`,

    x: `원본 원고를 X(Twitter)에 맞게 핵심 압축:
${getContentFocusGuideline(isPersonalAppealContent, 'x', userInfo)}
- 230자 극한 제약으로 핵심 메시지만 선별
- 원본의 가장 중요한 한 가지 포인트에만 집중
- 완전한 문장으로 마무리하되 불필요한 수식어 제거
- 원본의 논조와 입장을 정확히 표현`,

    threads: `원본 원고를 Threads에 맞게 대화형 가공:
${getContentFocusGuideline(isPersonalAppealContent, 'threads', userInfo)}
- 400자 제약으로 핵심 내용 위주 구성
- 대화하듯 자연스러운 톤으로 가공
- 원본의 주요 메시지를 압축하여 전달
- 간결하면서도 완성도 있는 스토리로 구성`
  };

  return `아래는 ${userInfo.name} ${userInfo.position}이 작성한 원본 정치인 원고입니다. 이를 ${platformConfig.name} 플랫폼에 맞게 가공해주세요.

**원본 원고 (가공 대상):**
${cleanContent}

**가공 지침:**
${platformInstructions[platform]}

**원본 문체 분석 및 보존 요구사항:**
- 어조: ${cleanContent.substring(0, 200)}... 이 문체 그대로 유지
- 표현법: 원본에서 사용한 존댓말, 문장 구조, 어미 패턴 보존
- 어휘: 원본에서 사용한 정치적 표현, 전문 용어 그대로 사용
- 논조: 원본의 정치적 입장과 태도 완전 보존

**가공 결과물 요구사항:**
- 목표 길이: ${targetLength}자 (공백 제외, ±50자 허용)
- 최대 한도: ${platformConfig.maxLength}자 절대 초과 금지
- 해시태그: ${platformConfig.hashtagLimit}개
- 완결성: 모든 문장이 완전히 끝나야 함 ("다/니다/습니다" 등)

**가공 시 절대 준수사항:**
1. 원본을 "요약"하지 말고 "가공"하세요 - 새로 쓰는 것이 아닙니다
2. ${userInfo.name}의 실제 어조, 문체, 표현 방식을 정확히 모방하세요
3. 원본의 핵심 메시지와 정보는 빠뜨리지 말고 모두 포함하세요
4. 원본의 정치적 입장과 논조를 절대 바꾸지 마세요
5. 원본에 없는 내용이나 의견을 추가하지 마세요

**JSON 출력 형식:**
{
  "content": "원본 원고를 ${platformConfig.name}에 맞게 가공한 완전한 텍스트",
  "hashtags": ["#관련태그1", "#관련태그2", "#관련태그3"],
  "wordCount": 실제글자수
}

원본의 품격과 내용을 손상시키지 않으면서 ${platformConfig.name}에 최적화된 가공 결과물을 만들어주세요.`;
}

module.exports = {
  buildSNSPrompt,
  SNS_LIMITS
};
