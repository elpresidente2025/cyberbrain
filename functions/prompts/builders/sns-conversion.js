/**
 * functions/prompts/builders/sns-conversion.js
 * SNS 플랫폼별 변환 프롬프트 생성
 *
 * v2.0 - 타래(Thread) 기반 구조로 개편
 * - X/Threads: 3-7개 타래로 분할
 * - Facebook/Instagram: 단일 게시물 (구조 최적화)
 *
 * v2.1 - 자연스러운 문체 규칙 추가 (LLM 티 제거)
 */

'use strict';

// 자연스러운 문체 규칙 import
const { buildSNSNaturalToneGuide } = require('../guidelines/natural-tone');

// SNS 플랫폼별 제한사항 (2026 알고리즘 연구 기반 최적화)
const SNS_LIMITS = {
  'facebook-instagram': {
    minLength: 300,   // 연구 기반: 800-1000자 권장이나, 생성 실패 방지를 위해 최소값 완화
    maxLength: 1000,  // 연구 기반: 800-1000자 최적
    hashtagLimit: 5,  // 연구 기반: 3-5개
    charsPerLine: 22, // 모바일 기준 20-25자
    previewLimit: 125, // "더보기" 전 표시 글자
    name: 'Facebook/Instagram',
    isThread: false
  },
  x: {
    maxLengthPerPost: 160,  // 임팩트 헤드라인: 130-160자
    minLengthPerPost: 130,
    recommendedMinLength: 130,
    hashtagLimit: 2,
    charsPerLine: 32,  // 30-35자
    name: 'X(Twitter)',
    isThread: true,
    minPosts: 1,
    maxPosts: 1
  },
  threads: {
    maxLengthPerPost: 350,  // 연구 기반: 250-350자 권장
    minLengthPerPost: 250,
    recommendedMinLength: 250,
    hashtagLimit: 3,
    charsPerLine: 27,  // 25-30자
    name: 'Threads',
    isThread: true,
    minPosts: 2,
    maxPosts: 5
  }
};

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
 * v3.0 - 2026 알고리즘 연구 기반 최적화
 * 
 * 핵심 연구 결과:
 * - 키워드 풍부한 캡션: 도달률 30% ↑, 좋아요 2배 ↑
 * - 첫 125자에 핵심 메시지 + 키워드
 * - 한 줄당 20-25자 (모바일 최적화)
 * - 이모지: 참여도 47.7% ↑ (앞부분 + 글머리 기호)
 * - 해시태그: 3-5개, 캡션 본문에 포함 (댓글X)
 * - CTA: 댓글/저장 유도로 알고리즘 신호 강화
 */
function buildFacebookInstagramPrompt(cleanContent, platformConfig, userInfo, options = {}) {
  const charsPerLine = platformConfig.charsPerLine || 22;
  const topic = options.topic || '';
  const title = options.title || '';
  const naturalToneGuide = buildSNSNaturalToneGuide();

  // 주제/제목 컨텍스트 블록
  const topicBlock = topic
    ? `\n**[최우선] 작성자가 전달하고자 하는 핵심 주제:**\n"${topic}"\n→ 이 주제의 핵심 메시지와 CTA(행동 유도)를 반드시 보존하세요. 주제에 담긴 어조와 의도가 캡션에 살아있어야 합니다.\n`
    : '';
  const titleBlock = title ? `**원고 제목:** ${title}\n` : '';

  return `아래는 ${userInfo.name} ${userInfo.position}이 작성한 블로그 원고입니다. 이를 Instagram 캡션으로 변환해주세요.
${topicBlock}${titleBlock}
**원본 블로그 원고:**
${cleanContent}

---

${naturalToneGuide}

---

## 📱 Instagram 알고리즘 최적화 가이드 (2026 연구 기반)

### [핵심 원칙: SEO 및 도달률 극대화]
1. **검색 최적화(SEO)**: 인스타그램은 이제 '검색 엔진'입니다. 본문이 길고 키워드가 많을수록 노출 확률이 높아집니다.
2. **체류 시간 증대**: 상세하고 깊이 있는 설명으로 유저가 오래 머물게 하세요. (알고리즘 점수 ↑)
3. **키워드 반복**: 핵심 키워드는 본문에 자연스럽게 4-5회 이상 녹여내세요.
4. **구조화된 가독성**: 긴 글도 읽히도록 이모지와 글머리 기호를 적극 활용하세요.
5. **${charsPerLine}자 호흡**: 모바일 최적화를 위해 짧은 호흡으로 줄바꿈하세요.

### [캡션 구조: High-Density SEO Mode]

**[1] 훅 (첫 125자)**
- 🎯 타겟 유저를 부르는 강력한 한 문장
- "더보기"를 누를 수밖에 없는 질문이나 예고
- 주요 키워드 배치

**[2] 핵심 요약 (3-4줄)**
- 바쁜 유저를 위한 빠른 요약 (✅ 이모지 활용)

**[3] 상세 분석 (Deep Dive) - SEO 핵심 구간**
- 블로그 내용을 단순히 요약하지 말고, **상세하게 풀어서 설명**하세요.
- 정책의 배경, 기대효과, 구체적 수치를 모두 포함하세요.
- 💡, 📌, 📈 등의 이모지로 문단을 나누세요.
- 유저가 "저장"하고 싶을 만큼 유용한 정보를 담으세요.

**[4] 진정성 있는 마무리**
- 정치적 구호보다는 개인적인 소회나 비전

**[5] 강력한 CTA**
- 💬 "여러분의 지역구는 어떤가요? 댓글로 알려주세요!" (구체적 행동 유도)

**[6] 검색용 해시태그 그룹**
- 본문과 3줄 띄우기

### [작성 원칙]

**✅ 권장:**
- **최대한 길고 자세하게 작성하세요.** (목표: 800자 이상)
- 전문 용어가 있다면 쉽게 풀어서 설명하여 키워드 다양성을 확보하세요.
- "요약"보다는 "해설" 느낌으로 접근하세요.

**❌ 금지:**
- 단순히 내용을 줄이거나 생략하는 행위 (SEO에 치명적)
- "자세한 건 블로그에서"라고 퉁치기 (이탈률 증가)

### [예시 구조]

🎮 [핵심 메시지 - 키워드 포함]

[배경 설명 1-2줄]

🏛️ [정책/활동 1]
→ 상세 설명

🎖️ [정책/활동 2]  
→ 상세 설명

[의미/기대효과 1-2줄]

[다짐 한 줄]

💬 여러분의 생각을 댓글로 남겨주세요!

ㅤ
ㅤ
ㅤ
#키워드1 #키워드2 #키워드3 #키워드4 #이름

---

**결과물 요구사항:**
- 분량: ${platformConfig.minLength}-${platformConfig.maxLength}자 (공백 포함)
- 해시태그: ${platformConfig.hashtagLimit}개
- 이모지: 4-5개 (앞부분 1 + 글머리 2-3 + CTA 1)
- ${userInfo.name} ${userInfo.position}의 격식 있는 어조 유지
- 원본의 정치적 입장과 논조 완전 보존
- 원본에 없는 내용 추가 금지

**JSON 출력 형식:**
{
  "content": "변환된 Instagram 캡션 전체 텍스트",
  "hashtags": ["#태그1", "#태그2", "#태그3", "#태그4", "#태그5"],
  "wordCount": 실제글자수
}`;
}

/**
 * X(트위터) 임팩트 헤드라인 모드 프롬프트 생성
 * v2.2 - 카테고리 기반 스타일 분기 (김민석: 공식적, 이재명: 친근함)
 */
function buildXPrompt(cleanContent, platformConfig, userInfo, options = {}) {
  const hashtagLimit = platformConfig.hashtagLimit;
  const minLengthPerPost = platformConfig.minLengthPerPost || 130;
  const maxLengthPerPost = platformConfig.maxLengthPerPost || 160;
  const blogUrl = options.blogUrl || '';
  const category = options.category || '';
  const subCategory = options.subCategory || '';
  const topic = options.topic || '';
  const title = options.title || '';
  const naturalToneGuide = buildSNSNaturalToneGuide();

  // 카테고리 기반 스타일 결정
  const isFriendlyStyle = category === '일상 소통' ||
    (category === '지역 현안 및 활동' && subCategory === '봉사 후기');
  const styleName = isFriendlyStyle ? '친근한 리더 (이재명 스타일)' : '공식적 리더 (김민석 스타일)';

  // 카테고리 기반 게시물 수 결정 (추후 타래 도입 대비)
  // - 일상 소통, 봉사 후기: 단일 게시물 고정
  // - 그 외: 현재 1개, 추후 타래(2-3개) 확장 가능
  const forceSinglePost = isFriendlyStyle;
  const postCount = forceSinglePost ? 1 : 1; // TODO: 추후 타래 로직 추가 시 조건부로 변경

  // 스타일별 작성 원칙
  const styleGuide = isFriendlyStyle ? `
**스타일: 친근한 리더 (이재명 스타일)**
- 비격식체, 친근한 어조
- 이모지 허용: ^^, ㅎㅎ, 😁 등 (적절히 사용)
- 유머, 밈, 신조어 허용 (예: "인생샷", "확실하죠?")
- 인간적 에피소드, 유머러스한 훅
- 멘션(@) 적극 활용
- 마무리: 웃음 마크 (^^, ㅎㅎ)` : `
**스타일: 공식적 리더 (김민석 스타일)**
- 격식체, 공식적 어조
- 이모지 금지
- 차분하고 신뢰감 있는 표현
- 느낌표 절제
- 역사적/제도적 맥락 강조
- 마무리: 공식 직함 또는 각오 표명`;

  // 주제/제목 컨텍스트 블록
  const topicBlock = topic
    ? `\n**[최우선] 작성자가 전달하고자 하는 핵심 주제:**\n"${topic}"\n→ 이 주제의 핵심 메시지와 CTA(행동 유도)를 반드시 보존하세요. 주제에 담긴 어조와 의도가 게시물에 살아있어야 합니다.\n`
    : '';
  const titleBlock = title ? `**원고 제목:** ${title}\n` : '';

  return `아래는 ${userInfo.name} ${userInfo.position}이 작성한 블로그 원고입니다. 이를 X(트위터) 임팩트 헤드라인으로 변환해주세요.
${topicBlock}${titleBlock}
**원본 블로그 원고:**
${cleanContent}

---

${naturalToneGuide}

---

**X 전략: 임팩트 헤드라인 모드**
X는 "훑어보는 곳"입니다. **1개 게시물**에 핵심 메시지 + 임팩트 요소를 담으세요.

${styleGuide}

**[STEP 1] 원본에서 반드시 추출할 요소:**
원본 원고를 분석하여 다음 요소를 찾아내세요:
- **고유명사/상징**: 장소명, 이벤트명, 브랜드 등 (예: "광안리 대첩", "지스타")
- **차별화 포인트**: "최초", "유일", "혁신" 등 독보적인 가치
- **수치/규모**: 팬 수, 예산, 일자리 수 등 구체적 숫자
- **실질적 혜택**: 누구에게 어떤 이득? (예: "청년 일자리", "관광객 유치")
- **감성적 훅**: 질문, 공감, 기억 환기 (예: "기억하시나요?", "함께했던 그 순간")
- **서사적 대비(Narrative Tension)**: 출신↔현재, 위기↔비전, 숫자↔숫자 등 극적인 간극
  (예: "부두 노동자의 아들 → AI 전문가", "경남 420억 vs 부산 103억")

**[STEP 2] 게시물 구조:**
- 감성적 훅 또는 핵심 메시지로 시작
- 원본에서 추출한 임팩트 요소 1-2개 포함
- 구체적 정책/활동 1개 언급
- ${minLengthPerPost}-${maxLengthPerPost}자 (공백 제외)
- 블로그 링크 (별도 문구 없이 자연스럽게)
- 해시태그 ${hashtagLimit}개
${blogUrl ? `- 블로그 링크: ${blogUrl}` : ''}

**작성 원칙:**
1. **${minLengthPerPost}-${maxLengthPerPost}자 엄수**: 130자 미만은 너무 짧음, 160자 초과는 너무 김
2. **줄바꿈으로 카드형 구성**: 2-5줄로 나눠 가독성 확보
3. **원본의 강력한 키워드 반드시 포함**: 추상적 요약 금지
4. **인사·서론 금지**: 핵심부터 시작
5. **원본 논조 보존**: 원본에 없는 내용 추가 금지

**[ANTI-PATTERN] 절대 금지 패턴:**
❌ "자세한 내용은 블로그에서 확인하세요" - 글자수 낭비, 저품질 CTA
❌ "~를 추진합니다!" 만으로 끝남 - 공허한 선언
❌ 원본 키워드 없는 일반적 요약 - 임팩트 없음
❌ 느낌표 남발 - 신뢰도 하락
❌ 링크 앞에 별도 안내 문구 - 링크만 배치

**[FEW-SHOT] 실제 정치인 X 게시물 예시 (김민석 국무총리):**

✅ 예시 1 - 역사적 훅 + 기념식:
"1979년 부마의 외침이
2025년 빛의혁명으로 이어졌습니다.

평범한 시민들이 일궈낸
숭고한 민주주의의 역사를 기억하고
그 정신을 가슴에 새길 때,
대한민국 민주주의는 대립과 갈등을 넘어
뿌리를 깊이 내리고 미래로 나아갈 것입니다.

제46주년 부마민주항쟁 기념식('25. 10. 16.)
국무총리 김민석"

→ 역사 연결(1979→2025) + 감성 + 명확한 맥락(기념식)

✅ 예시 2 - 영상 링크 + 개인 서사:
"[새벽총리 100일의 기록 #만남]
https://youtu.be/...

후보자 지명 후 첫 출근길
국민과 손을 맞잡고 
그 마음에 다가가고자 했습니다

현장이 곧 집무실이라는 각오로
한걸음 더 다가가고
진심을 나누고자 했습니다.

국민을 향한 발걸음
멈추지 않겠습니다"

→ 영상 링크 + 개인 서사 + 각오 표명

✅ 예시 3 - 행사 안내 + 구체적 일정:
"10·20·30대 청년들과 함께하는
K-토론나라 '미래대화 1·2·3'

#청년일자리 를 주제로
대한민국의 미래를 함께 이야기합니다.

국민 여러분의 많은 관심 부탁드립니다.

*10월 24일(금) 12:00 KTV·총리실TV·김민석TV
유튜브 채널에 녹화방송 게시 예정입니다."

→ 이벤트명 + 해시태그 + 구체적 일정(날짜/시간/채널)

**위 예시들의 공통점 (김민석 스타일):**
- 140-150자 내외 (더보기 없이 보이는 최적 범위)
- 첫 줄에 핵심/훅
- 줄바꿈으로 카드형 가독성
- 느낌표 없음, 차분하고 신뢰감 있는 어조
- "자세한 내용은 블로그에서" 같은 저품질 CTA 없음

**[FEW-SHOT] 친근한 리더 예시 (이재명 대통령):**

✅ 예시 A - 유머 + 외교:
"어설프지만, 그래서 더 잘 어울렸던 다카이치 총리님과의 합주^^
슬쩍 숟가락 하나 얹어봤지만 역시 프로의 실력은 다르더군요.

박자는 조금 달라도 리듬 맞추려는 마음은 같았던 것처럼, 미래지향적 한일 관계도 한 마음으로 만들어가겠습니다."

→ 유머러스 시작("^^") + 격식-비격식 배합 + 외교 메시지

✅ 예시 B - 셀카 + 소통:
"<화질은 확실하쥬? 😁>
경주에서 선물 받은 샤오미로 시진핑 주석님 내외분과 셀카 한 장..
덕분에 인생샷 건졌습니다 ㅎㅎ

가까이에서 만날수록 풀리는 한중관계,
앞으로 더 자주 소통하고 더 많이 협력하겠습니다^^"

→ 이모지(😁) + 신조어("인생샷") + 웃음 마크(ㅎㅎ, ^^)

✅ 예시 C - 페이커 축하:
"<GOAT.. 대상혁 청와대 등장?>
e-스포츠 사상 최초 체육훈장..
축하합니다 페이커 선수^^ 
@T1LoL

https://youtube.com/shorts/...

#페이커 #대통령훈장 #신년인사회"

→ 밈("<GOAT..>") + 멘션(@) + 해시태그 적극 활용

**친근한 리더 스타일 특징:**
- 이모지 허용 (^^, ㅎㅎ, 😁)
- 유머/밈/신조어 활용
- 친근하고 인간적인 어조


❌ 나쁜 예 (47자 - 기준 미달):
"부산을 e스포츠 허브로! 진흥재단 설립 & 세계 최초 박물관 건립 추진!
자세한 내용은 블로그에서 확인하세요!

#e스포츠도시 #부산경제"

→ 47자로 너무 짧음, "자세한 내용은 블로그에서" 저품질 CTA, 느낌표 남발, 감성적 훅 없음

**JSON 출력 형식:**
{
  "posts": [
    {
      "order": 1,
      "content": "[감성적 훅/핵심 메시지]\\n\\n[임팩트 요소 + 정책]\\n\\n${blogUrl || 'https://...'}\\n\\n#태그1 #태그2",
      "wordCount": 148
    }
  ],
  "hashtags": ["#태그1", "#태그2"],
  "totalWordCount": 148,
  "postCount": 1
}

**최종 체크리스트:**
- [ ] 130-160자 범위인가?
- [ ] 원본의 고유명사/상징이 포함되었는가?
- [ ] "자세한 내용은 블로그에서" 같은 저품질 CTA가 없는가?
- [ ] 감성적 훅 또는 구체적 수치가 있는가?
- [ ] 블로그 링크가 자연스럽게 배치되었는가?`;
}

/**
 * Threads 맥락 설명 모드 프롬프트 생성
 */
function buildThreadsPrompt(cleanContent, platformConfig, userInfo, options = {}) {
  const hashtagLimit = platformConfig.hashtagLimit;
  const minPosts = platformConfig.minPosts || 2;
  const maxPosts = platformConfig.maxPosts || 5;
  const minLengthPerPost = platformConfig.minLengthPerPost || 200;
  const maxLengthPerPost = platformConfig.maxLengthPerPost || 500;
  const targetPostCount = options.targetPostCount;
  const postCountGuidance = targetPostCount
    ? `**게시물 수는 ${targetPostCount}개로 맞춰주세요.**`
    : `**게시물 수는 원문 분량에 맞게 ${minPosts}~${maxPosts}개 중에서 선택해주세요.**`;
  const blogUrl = options.blogUrl || '';
  const topic = options.topic || '';
  const title = options.title || '';
  const naturalToneGuide = buildSNSNaturalToneGuide();

  // 주제/제목 컨텍스트 블록
  const topicBlock = topic
    ? `\n**[최우선] 작성자가 전달하고자 하는 핵심 주제:**\n"${topic}"\n→ 이 주제의 핵심 메시지와 CTA(행동 유도)를 반드시 보존하세요. 주제에 담긴 어조와 의도가 타래 전체에 살아있어야 합니다.\n`
    : '';
  const titleBlock = title ? `**원고 제목:** ${title}\n` : '';

  return `아래는 ${userInfo.name} ${userInfo.position}이 작성한 블로그 원고입니다. 이를 Threads 타래(thread)로 변환해주세요.
${topicBlock}${titleBlock}
**원본 블로그 원고:**
${cleanContent}

---

${naturalToneGuide}

---

**Threads 전략: 맥락 설명 모드**
Threads는 "대화·맥락을 쌓는 곳"입니다. 요약 + 핵심 문단을 통해 **왜 중요한지, 무엇을 하는지** 설명하세요.

**타래 구조 (${minPosts}-${maxPosts}개 게시물):**

${postCountGuidance}

- 각 게시물은 ${minLengthPerPost}-${maxLengthPerPost}자 권장 (공백 제외)
- X보다 길고 설명적으로 작성

[1번] 요약 + 훅
- 핵심 메시지와 배경을 **함께** 담은 요약
- ${minLengthPerPost}-${maxLengthPerPost}자
- 이 게시물만 봐도 전체 맥락 파악 가능
- 인사나 서론 없이 핵심부터 시작

[2번] 맥락 설명
- 왜 이 이슈가 중요한지
- 현황, 배경, 필요성 설명
- ${minLengthPerPost}-${maxLengthPerPost}자

[3번] (필요시) 핵심 내용 또는 근거
- 정책/활동/입장의 구체적 내용
- 수치, 팩트, 사례
- ${minLengthPerPost}-${maxLengthPerPost}자

[4~5번] (필요시) 추가 설명 또는 전망
- 기대효과, 향후 계획
- 추가 근거나 사례
- ${minLengthPerPost}-${maxLengthPerPost}자

[마지막] 마무리
- 입장 정리 또는 다짐
- 해시태그 ${hashtagLimit}개 포함
${blogUrl ? `- 블로그 링크 포함: ${blogUrl}` : ''}

**변환 원칙:**
- 각 게시물은 독립적으로도 의미 전달 가능
- X보다 **더 길고 설명적**으로 작성
- 대화하듯 풀어서 설명
- 이모지 사용 금지
- 원본의 정치적 입장과 논조 완전 보존
- 원본에 없는 내용 추가 금지

**JSON 출력 형식:**
{
  "posts": [
    { "order": 1, "content": "요약 + 훅", "wordCount": 280 },
    { "order": 2, "content": "맥락 설명", "wordCount": 350 },
    { "order": 3, "content": "핵심 내용", "wordCount": 320 },
    { "order": 4, "content": "마무리 #태그1 #태그2 #태그3${blogUrl ? '\\n' + blogUrl : ''}", "wordCount": 250 }
  ],
  "hashtags": ["#태그1", "#태그2", "#태그3"],
  "totalWordCount": 1200,
  "postCount": 4
}`;
}

/**
 * X/Threads 타래용 프롬프트 생성 (레거시 - 하위 호환)
 * @deprecated buildXPrompt 또는 buildThreadsPrompt 사용 권장
 */
function buildThreadPrompt(cleanContent, platform, platformConfig, userInfo, options = {}) {
  // 플랫폼별로 새 함수로 분기
  if (platform === 'x') {
    return buildXPrompt(cleanContent, platformConfig, userInfo, options);
  } else if (platform === 'threads') {
    return buildThreadsPrompt(cleanContent, platformConfig, userInfo, options);
  }

  // 아래는 레거시 코드 (만약을 위해 유지)
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
    return buildFacebookInstagramPrompt(cleanContent, platformConfig, userInfo, options);
  }

  // X와 Threads는 타래 구조 (통일)
  return buildThreadPrompt(cleanContent, platform, platformConfig, userInfo, options);
}

module.exports = {
  buildSNSPrompt,
  buildXPrompt,
  buildThreadsPrompt,
  buildThreadPrompt,  // 레거시 호환
  SNS_LIMITS,
  cleanHTMLContent
};
