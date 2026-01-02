/**
 * functions/prompts/builders/sns-conversion.js
 * SNS 플랫폼별 변환 프롬프트 생성
 *
 * v2.0 - 타래(Thread) 기반 구조로 개편
 * - X/Threads: 3-7개 타래로 분할
 * - Facebook/Instagram: 단일 게시물 (구조 최적화)
 */

'use strict';

// SNS 플랫폼별 제한사항
const SNS_LIMITS = {
  'facebook-instagram': {
    minLength: 800,
    maxLength: 1500,
    hashtagLimit: 7,
    name: 'Facebook/Instagram',
    isThread: false
  },
  x: {
    maxLengthPerPost: 250,  // 게시물당 권장 최대 (공백 제외)
    minLengthPerPost: 150,
    recommendedMinLength: 150,
    hashtagLimit: 2,
    name: 'X(Twitter)',
    isThread: true,
    minPosts: 3,
    maxPosts: 7
  },
  threads: {
    maxLengthPerPost: 250,  // X와 동일하게 통일
    minLengthPerPost: 150,
    recommendedMinLength: 150,
    hashtagLimit: 3,
    name: 'Threads',
    isThread: true,
    minPosts: 3,
    maxPosts: 7
  }
};

/**
 * 원본 콘텐츠의 주제 유형 분석
 */
function analyzeContentType(content) {
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
 * HTML 태그 제거 및 평문 변환
 */
function cleanHTMLContent(originalContent) {
  return originalContent
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
}

/**
 * Facebook/Instagram 단일 게시물용 프롬프트 생성
 */
function buildFacebookInstagramPrompt(cleanContent, platformConfig, userInfo) {
  return `아래는 ${userInfo.name} ${userInfo.position}이 작성한 블로그 원고입니다. 이를 Facebook/Instagram 게시물로 변환해주세요.

**원본 블로그 원고:**
${cleanContent}

**변환 구조:**
1. 도입부 (1-2문장): 핵심 메시지 또는 현안 배경
2. 본론 (3-4문단): 주요 내용, 정책/활동 상세, 근거/수치 포함
3. 의미/전망 (1-2문장): 기대효과 또는 향후 계획
4. 마무리 (1문장): 다짐 또는 소통 의지

**변환 원칙:**
- 문단 구분으로 가독성 확보 (빈 줄로 구분)
- 원문의 논리 흐름과 핵심 정보 보존
- ${userInfo.name} ${userInfo.position}의 격식 있는 어조 유지
- 이모지 사용 금지
- 글자수를 억지로 채우지 말고, 내용에 맞게 자연스럽게

**문체 보존:**
- 원본의 존댓말, 문장 구조, 어미 패턴 유지
- 원본의 정치적 입장과 논조 완전 보존
- 원본에 없는 내용 추가 금지
- 수치/연도/비율은 원문에 있는 것만 사용 (새 숫자 금지)

**결과물 요구사항:**
- 분량: ${platformConfig.minLength}-${platformConfig.maxLength}자 (공백 제외)
- 해시태그: ${platformConfig.hashtagLimit}개
- 모든 문장은 완전히 끝나야 함

**JSON 출력 형식:**
{
  "content": "변환된 Facebook/Instagram 게시물 전체 텍스트",
  "hashtags": ["#태그1", "#태그2", ...],
  "wordCount": 실제글자수
}`;
}

/**
 * X/Threads 타래용 프롬프트 생성 (통일 구조)
 */
function buildThreadPrompt(cleanContent, platform, platformConfig, userInfo, options = {}) {
  const platformName = platformConfig.name;
  const hashtagLimit = platformConfig.hashtagLimit;
  const minPosts = platformConfig.minPosts || 3;
  const maxPosts = platformConfig.maxPosts || 7;
  const minLengthPerPost = platformConfig.minLengthPerPost || 130;
  const recommendedMinLength = platformConfig.recommendedMinLength || 150;
  const maxLengthPerPost = platformConfig.maxLengthPerPost || platformConfig.maxLength || 250;
  const targetPostCount = options.targetPostCount;
  const postCountGuidance = targetPostCount
    ? `**게시물 수는 ${targetPostCount}개로 맞춰주세요.**`
    : `**게시물 수는 원문 분량에 맞게 ${minPosts}~${maxPosts}개 중에서 선택해주세요.**`;

  return `아래는 ${userInfo.name} ${userInfo.position}이 작성한 블로그 원고입니다. 이를 ${platformName} 타래(thread)로 변환해주세요.

**원본 블로그 원고:**
${cleanContent}

**타래 구조 (${minPosts}-${maxPosts}개 게시물):**

- 내용이 적으면 게시물 수를 줄이고, 많으면 늘리세요.
- 각 게시물은 ${recommendedMinLength}-${maxLengthPerPost}자 권장(공백 제외), ${minLengthPerPost}자 미만은 피하기.
- 1번: 훅/핵심 메시지
- 2~(마지막-1): 배경/핵심/근거를 분산
- 마지막: 마무리 + 해시태그 ${hashtagLimit}개 포함

${postCountGuidance}

[1번] 훅
- 가장 강력한 핵심 메시지 한 문장
- 인사나 서론 없이 핵심부터 시작
- 이 게시물만 봐도 전체 맥락 파악 가능
- 타임라인에서 스크롤을 멈추게 하는 역할

[2번] 배경/맥락
- 왜 이 이슈가 중요한지
- 현황, 배경 설명

[3번] 핵심 내용
- 정책/활동/입장의 구체적 내용
- 가장 중요한 포인트

[4~5번] 근거/사례 또는 추가 내용 (필요 시)
- 수치, 팩트, 구체적 사례
- 신뢰성을 높이는 근거

[마지막] 마무리
- 입장 정리 또는 다짐
- 해시태그 ${hashtagLimit}개 포함

**변환 원칙:**
- 리듬 변화: 짧은 훅 → 중간 본문 → 짧은 마무리
- 각 게시물은 독립적으로도 의미 전달 가능해야 함
- 글자수를 억지로 채우지 말고, 권장 범위 안에서 자연스럽게
- 이모지 사용 금지
- 수식어 최소화, 핵심 정보만

**문체 보존:**
- ${userInfo.name}의 어조와 문체 유지
- 원본의 정치적 입장과 논조 완전 보존
- 원본에 없는 내용 추가 금지
- 수치/연도/비율은 원문에 있는 것만 사용 (새 숫자 금지)

**훅 작성 예시:**
좋은 예: "민생경제 3법, 오늘 국회 발의했습니다."
나쁜 예: "안녕하세요, 오늘 국회에서 중요한 법안을..."

**JSON 출력 형식:**
{
  "posts": [
    { "order": 1, "content": "첫 번째 게시물 (훅)", "wordCount": 180 },
    { "order": 2, "content": "두 번째 게시물", "wordCount": 200 },
    { "order": 3, "content": "세 번째 게시물", "wordCount": 210 },
    { "order": 4, "content": "네 번째 게시물", "wordCount": 190 },
    { "order": 5, "content": "다섯 번째 게시물 (마무리) #태그1 #태그2", "wordCount": 170 }
  ],
  "hashtags": ["#태그1", "#태그2"],
  "totalWordCount": 510,
  "postCount": 5
}`;
}

/**
 * SNS 변환 프롬프트 생성 (메인 함수)
 * @param {string} originalContent - 원본 원고 내용 (블로그 원고)
 * @param {string} platform - SNS 플랫폼 ('facebook-instagram', 'x', 'threads')
 * @param {Object} platformConfig - 플랫폼 설정
 * @param {string} postKeywords - 원고 키워드 (미사용, 호환성 유지)
 * @param {Object} userInfo - 사용자 정보 (name, position, region 등)
 * @returns {string} 완성된 SNS 변환 프롬프트
 */
function buildSNSPrompt(originalContent, platform, platformConfig, postKeywords = '', userInfo = {}, options = {}) {
  const cleanContent = cleanHTMLContent(originalContent);

  // Facebook/Instagram은 단일 게시물
  if (platform === 'facebook-instagram') {
    return buildFacebookInstagramPrompt(cleanContent, platformConfig, userInfo);
  }

  // X와 Threads는 타래 구조 (통일)
  return buildThreadPrompt(cleanContent, platform, platformConfig, userInfo, options);
}

module.exports = {
  buildSNSPrompt,
  SNS_LIMITS,
  analyzeContentType,
  cleanHTMLContent
};
