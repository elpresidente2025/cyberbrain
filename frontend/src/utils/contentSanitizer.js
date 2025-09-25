/**
 * 콘텐츠 정화 및 처리 유틸리티
 * DOMPurify를 사용한 안전한 HTML 처리
 */

// DOMPurify 동적 import 및 fallback 처리
let DOMPurify = null;

/**
 * HTML 콘텐츠를 안전하게 정화
 * @param {string} html - 정화할 HTML 문자열
 * @returns {string} 정화된 HTML
 */
export const sanitizeHtml = (html) => {
  if (!html || typeof html !== 'string') return '';

  // DOMPurify가 로드되지 않았다면 기본 정화 사용
  if (!DOMPurify) {
    // 기본적인 위험 태그 제거
    return html
      .replace(/<script[^>]*>.*?<\/script>/gi, '') // 스크립트 제거
      .replace(/<style[^>]*>.*?<\/style>/gi, '')   // 스타일 제거
      .replace(/on\w+="[^"]*"/gi, '')              // 이벤트 핸들러 제거
      .replace(/<iframe[^>]*>.*?<\/iframe>/gi, '') // iframe 제거
      .replace(/<object[^>]*>.*?<\/object>/gi, '') // object 제거
      .replace(/<embed[^>]*>/gi, '');              // embed 제거
  }

  try {
    // DOMPurify 설정: 기본적인 텍스트 태그만 허용
    const config = {
      ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
      ALLOWED_ATTR: [],
      KEEP_CONTENT: true,
      RETURN_DOM_FRAGMENT: false,
      RETURN_DOM: false
    };

    return DOMPurify.sanitize(html, config);
  } catch (error) {
    console.warn('DOMPurify 사용 실패, 기본 정화 사용:', error);
    // fallback to basic sanitization
    return html
      .replace(/<script[^>]*>.*?<\/script>/gi, '')
      .replace(/<style[^>]*>.*?<\/style>/gi, '')
      .replace(/on\w+="[^"]*"/gi, '');
  }
};

// DOMPurify 동적 로드
if (typeof window !== 'undefined') {
  import('dompurify')
    .then((module) => {
      DOMPurify = module.default;
      console.log('✅ DOMPurify 로드 완료');
    })
    .catch((error) => {
      console.warn('⚠️ DOMPurify 로드 실패, 기본 정화 사용:', error);
    });
}

/**
 * HTML 태그를 완전히 제거하여 순수 텍스트만 반환
 * @param {string} html - 처리할 HTML 문자열
 * @returns {string} 태그가 제거된 텍스트
 */
export const stripHtmlTags = (html) => {
  if (!html || typeof html !== 'string') return '';

  return html
    .replace(/<[^>]*>/g, '')     // 모든 HTML 태그 제거
    .replace(/&nbsp;/g, ' ')     // &nbsp; → 공백
    .replace(/&amp;/g, '&')      // &amp; → &
    .replace(/&lt;/g, '<')       // &lt; → <
    .replace(/&gt;/g, '>')       // &gt; → >
    .replace(/&quot;/g, '"')     // &quot; → "
    .replace(/&#39;/g, "'")      // &#39; → '
    .replace(/\s+/g, ' ')        // 연속된 공백을 하나로
    .trim();
};

/**
 * 텍스트 길이를 계산 (HTML 태그 제외)
 * @param {string} content - 계산할 콘텐츠
 * @returns {number} 실제 텍스트 길이
 */
export const getTextLength = (content) => {
  return stripHtmlTags(content).length;
};

/**
 * SEO 최적화 여부 판단
 * @param {string} content - 판단할 콘텐츠
 * @param {number} threshold - 최소 글자 수 기준 (기본 1800자)
 * @returns {boolean} SEO 최적화 여부
 */
export const isSeoOptimized = (content, threshold = 1800) => {
  return getTextLength(content) >= threshold;
};