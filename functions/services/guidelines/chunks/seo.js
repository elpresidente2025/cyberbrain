/**
 * functions/services/guidelines/chunks/seo.js
 * SEO 최적화 지침 청크
 */

'use strict';

const SEO_CHUNKS = [
  // ============================================================================
  // HIGH: 글자수 규칙
  // ============================================================================
  {
    id: 'SEO-001',
    type: 'seo',
    priority: 'HIGH',
    applies_to: { category: ['all'] },
    keywords: ['글자수', '분량', '길이', '워드카운트'],
    instruction: '글자수 1,500~2,300자 준수 (공백 제외)',
    forbidden: [],
    examples: [
      { bad: '500자 짧은 원고', good: '1,500자 이상의 충실한 원고' },
      { bad: '3,000자 과도하게 긴 원고', good: '2,300자 이내로 간결하게' }
    ],
    details: {
      min: 1500,
      max: 2300,
      target: 2000,
      rationale: '1500자 미만은 콘텐츠 부족, 2300자 초과는 가독성 저하'
    }
  },

  // ============================================================================
  // HIGH: 키워드 배치 규칙
  // ============================================================================
  {
    id: 'SEO-002',
    type: 'seo',
    priority: 'HIGH',
    applies_to: { category: ['all'] },
    keywords: ['키워드', '검색어', 'SEO', '노출'],
    instruction: '키워드를 본문 400자당 1회, 도입-본론-결론에 분산 배치',
    forbidden: ['키워드 스터핑', '동일 문단 2회 반복'],
    examples: [
      { bad: '청년일자리 청년일자리 청년일자리', good: '청년 일자리 정책이 중요합니다... (400자 후) 청년 일자리 확대를 위해...' },
      { bad: '키워드만 나열', good: '문장 내 자연스럽게 삽입' }
    ],
    details: {
      interval: 400,
      positions: {
        intro: '첫 2문단에 1회',
        body: '본론에 분산',
        conclusion: '마지막 2문단에 1회'
      },
      methods: [
        '주어 위치: "○○은(는) 이번 행사에서..."',
        '목적어 위치: "...에서 ○○을(를) 논의했습니다."',
        '수식어 위치: "○○의 성과로..."'
      ]
    }
  },

  // ============================================================================
  // MEDIUM: 제목 최적화
  // ============================================================================
  {
    id: 'SEO-003',
    type: 'seo',
    priority: 'MEDIUM',
    applies_to: { category: ['all'] },
    keywords: ['제목', '타이틀', '헤드라인'],
    instruction: '제목 30~40자, 핵심 키워드 앞쪽 배치, 구체적 정보 포함',
    forbidden: [],
    examples: [
      { bad: '정책에 대하여', good: '계양구 청년 일자리 정책, 3가지 핵심 방향 제안' },
      { bad: '인사드립니다', good: '부평구 주민 여러분께 드리는 봄 인사' }
    ],
    details: {
      length: { min: 30, max: 40 },
      strategy: [
        '핵심 키워드 앞쪽 배치',
        '구체적이고 명확한 표현',
        '감정적 어필 요소 포함',
        '지역명/날짜 등 구체 정보 활용'
      ]
    }
  },

  // ============================================================================
  // MEDIUM: 구조화 (H2, H3 태그)
  // ============================================================================
  {
    id: 'SEO-004',
    type: 'seo',
    priority: 'MEDIUM',
    applies_to: { category: ['all'] },
    keywords: ['구조', '소제목', '문단', 'HTML'],
    instruction: 'H2 2~3개, H3 3~5개로 구조화, 문단은 150~250자',
    forbidden: [],
    examples: [
      { bad: '소제목 없이 긴 텍스트', good: '<h2>첫 번째 주제</h2><p>내용...</p>' },
      { bad: '한 문단에 500자', good: '150~250자 단위로 문단 분리' }
    ],
    details: {
      headings: {
        h2: '2-3개, 주요 섹션 구분',
        h3: '3-5개, 세부 내용 구조화'
      },
      paragraphs: {
        count: '10-15개',
        length: '150-250자',
        rule: '한 문단 하나의 주제'
      }
    }
  }
];

/**
 * 키워드 배치 계산
 */
function calculateKeywordDistribution(targetWordCount, keywordCount) {
  const interval = 400;
  const minInsertions = Math.max(2, Math.floor(targetWordCount / interval));

  let distribution;
  if (minInsertions <= 2) {
    distribution = { intro: 1, body: 1, conclusion: 0 };
  } else if (minInsertions <= 4) {
    distribution = { intro: 1, body: 2, conclusion: 1 };
  } else {
    const intro = Math.ceil(minInsertions * 0.25);
    const conclusion = Math.ceil(minInsertions * 0.25);
    const body = minInsertions - intro - conclusion;
    distribution = { intro, body, conclusion };
  }

  return {
    perKeyword: minInsertions,
    distribution,
    total: minInsertions * keywordCount
  };
}

/**
 * SEO 지침 텍스트 생성
 */
function buildSEOGuideline(keywords = [], targetWordCount = 2000) {
  const seoChunk = SEO_CHUNKS.find(c => c.id === 'SEO-001');
  const keywordChunk = SEO_CHUNKS.find(c => c.id === 'SEO-002');

  let text = `[글자수] ${seoChunk.details.min}~${seoChunk.details.max}자 (목표: ${targetWordCount}자)\n`;

  if (keywords.length > 0) {
    const dist = calculateKeywordDistribution(targetWordCount, keywords.length);
    text += `[키워드] ${keywords.join(', ')} → 각 ${dist.perKeyword}회 삽입\n`;
    text += `  - 도입부: ${dist.distribution.intro}회\n`;
    text += `  - 본론: ${dist.distribution.body}회\n`;
    text += `  - 결론: ${dist.distribution.conclusion}회\n`;
  }

  return text;
}

module.exports = {
  SEO_CHUNKS,
  calculateKeywordDistribution,
  buildSEOGuideline
};
