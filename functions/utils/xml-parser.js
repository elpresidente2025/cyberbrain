/**
 * functions/utils/xml-parser.js
 * AI 출력에서 XML 태그 사이의 내용을 안전하게 추출하는 유틸리티
 * 
 * 목적:
 * - AI의 XML 구조화된 응답에서 데이터 추출 자동화
 * - 닫는 태그 누락, 불필요한 텍스트 등 예외 상황 대응
 * - 에이전트 간 구조화된 데이터 교환 지원
 */

'use strict';

/**
 * 단일 태그 내용 추출 (Robust 정규표현식)
 * - 정상적인 열림/닫힘 태그 우선 추출
 * - 닫는 태그 누락 시 Fallback 처리
 * - 속성이 있는 태그도 지원
 * 
 * @param {string} text - AI 응답 텍스트
 * @param {string} tagName - 추출할 태그명 (예: 'title', 'content')
 * @returns {string|null} - 추출된 내용 또는 null
 */
function extractTag(text, tagName) {
    if (!text || typeof text !== 'string') return null;
    if (!tagName || typeof tagName !== 'string') return null;

    const escapedTag = tagName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    // 1차 시도: 정상적인 열림/닫힘 태그 (속성 포함)
    // 예: <title attr="value">내용</title>
    const normalPattern = new RegExp(
        `<${escapedTag}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${escapedTag}>`,
        'i'
    );
    const normalMatch = text.match(normalPattern);
    if (normalMatch) {
        return normalMatch[1].trim();
    }

    // 2차 시도: 닫는 태그 누락 시, 다음 여는 태그까지 추출
    // 예: <title>내용 <other> → "내용"까지만 추출
    const unclosedPattern = new RegExp(
        `<${escapedTag}(?:\\s[^>]*)?>([\\s\\S]*?)(?=<[a-zA-Z_][a-zA-Z0-9_-]*(?:\\s|>)|$)`,
        'i'
    );
    const unclosedMatch = text.match(unclosedPattern);
    if (unclosedMatch) {
        const content = unclosedMatch[1].trim();
        // 빈 문자열이 아닌 경우에만 반환
        if (content.length > 0) {
            return content;
        }
    }

    // 3차 시도: Self-closing 태그 형식
    // 예: <title content="내용"/> 또는 <title>내용</>
    const selfClosingPattern = new RegExp(
        `<${escapedTag}\\s+(?:content|value)=["']([^"']*)["']\\s*/?>`,
        'i'
    );
    const selfClosingMatch = text.match(selfClosingPattern);
    if (selfClosingMatch) {
        return selfClosingMatch[1].trim();
    }

    return null;
}

/**
 * 여러 태그를 한번에 추출하여 JSON 객체로 반환
 * 
 * @param {string} text - AI 응답 텍스트
 * @param {string[]} tagNames - 추출할 태그명 배열
 * @returns {Object} - { tagName: extractedContent, ... }
 */
function extractMultipleTags(text, tagNames) {
    if (!text || !Array.isArray(tagNames)) {
        return {};
    }

    const result = {};
    for (const tag of tagNames) {
        result[tag] = extractTag(text, tag);
    }
    return result;
}

/**
 * AI 응답에서 표준 출력 형식 추출
 * (title, content, hashtags, summary 등)
 * 
 * @param {string} text - AI 응답 텍스트
 * @returns {{title: string|null, content: string|null, hashtags: string[], summary: string|null}}
 */
function parseStandardOutput(text) {
    const title = extractTag(text, 'title');
    const content = extractTag(text, 'content');
    const summary = extractTag(text, 'summary');
    const hashtagsRaw = extractTag(text, 'hashtags');

    // 해시태그 파싱 (콤마, 줄바꿈, 공백으로 분리)
    let hashtags = [];
    if (hashtagsRaw) {
        hashtags = hashtagsRaw
            .split(/[,\n\s]+/)
            .map(h => h.trim())
            .filter(h => h.length > 0)
            .map(h => h.startsWith('#') ? h : `#${h}`)
            // 중복 제거
            .filter((h, i, arr) => arr.indexOf(h) === i);
    }

    return { title, content, hashtags, summary };
}

/**
 * 중첩된 태그 구조 추출
 * 예: <rules><rule>...</rule><rule>...</rule></rules>
 * 
 * @param {string} text - AI 응답 텍스트
 * @param {string} containerTag - 컨테이너 태그명 (예: 'rules')
 * @param {string} itemTag - 아이템 태그명 (예: 'rule')
 * @returns {string[]} - 추출된 아이템 배열
 */
function extractNestedTags(text, containerTag, itemTag) {
    if (!text || !containerTag || !itemTag) return [];

    // 컨테이너 내용 추출
    const containerContent = extractTag(text, containerTag);
    if (!containerContent) return [];

    // 아이템들 추출
    const escapedItemTag = itemTag.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const itemPattern = new RegExp(
        `<${escapedItemTag}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${escapedItemTag}>`,
        'gi'
    );

    const items = [];
    let match;
    while ((match = itemPattern.exec(containerContent)) !== null) {
        items.push(match[1].trim());
    }

    return items;
}

/**
 * 태그의 속성 값 추출
 * 예: <rule type="must" priority="critical">내용</rule>
 * 
 * @param {string} text - AI 응답 텍스트
 * @param {string} tagName - 태그명
 * @param {string} attrName - 속성명
 * @returns {string|null} - 속성 값 또는 null
 */
function extractTagAttribute(text, tagName, attrName) {
    if (!text || !tagName || !attrName) return null;

    const escapedTag = tagName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const escapedAttr = attrName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    const pattern = new RegExp(
        `<${escapedTag}[^>]*\\s${escapedAttr}=["']([^"']*)["'][^>]*>`,
        'i'
    );

    const match = text.match(pattern);
    return match ? match[1] : null;
}

/**
 * 기존 텍스트 프로토콜 파서 (이전 버전 호환성)
 * ===TITLE===, ===CONTENT=== 형식 파싱
 * 
 * @param {string} text - AI 응답 텍스트
 * @param {string} fallbackTitle - 기본 제목
 * @returns {{title: string, content: string}}
 */
function parseTextProtocol(text, fallbackTitle = '') {
    if (!text) return { title: fallbackTitle, content: '' };

    let clean = text.trim();

    // 마크다운 코드블록 제거
    if (clean.startsWith('```')) {
        clean = clean.replace(/^```(?:html|text|json)?[\s\n]*/i, '').replace(/[\s\n]*```$/, '');
    }

    // 텍스트 프로토콜 파싱
    const titleMatch = clean.match(/===TITLE===\s*([\s\S]*?)\s*===CONTENT===/);
    const contentMatch = clean.match(/===CONTENT===\s*([\s\S]*)/);

    const title = titleMatch ? titleMatch[1].trim() : fallbackTitle;

    let content = '';
    if (contentMatch) {
        content = contentMatch[1].trim();
    } else if (!titleMatch) {
        // 구분자가 아예 없으면 전체를 본문으로
        content = clean;
    }

    return { title, content };
}

/**
 * 통합 파서: XML 태그와 텍스트 프로토콜을 모두 지원
 * XML 태그 우선, 실패 시 텍스트 프로토콜로 폴백
 * 
 * @param {string} text - AI 응답 텍스트
 * @param {string} fallbackTitle - 기본 제목
 * @returns {{title: string|null, content: string|null, hashtags: string[], parseMethod: string}}
 */
function parseAIResponse(text, fallbackTitle = '') {
    if (!text || typeof text !== 'string') {
        return { title: fallbackTitle, content: '', hashtags: [], parseMethod: 'fallback' };
    }

    // 1차 시도: XML 태그 파싱
    const xmlResult = parseStandardOutput(text);
    if (xmlResult.title || xmlResult.content) {
        return {
            ...xmlResult,
            title: xmlResult.title || fallbackTitle,
            parseMethod: 'xml'
        };
    }

    // 2차 시도: 텍스트 프로토콜 파싱
    const textResult = parseTextProtocol(text, fallbackTitle);
    if (textResult.content) {
        return {
            title: textResult.title,
            content: textResult.content,
            hashtags: [],
            parseMethod: 'text-protocol'
        };
    }

    // 최종 폴백: 전체 텍스트를 본문으로
    return {
        title: fallbackTitle,
        content: text.trim(),
        hashtags: [],
        parseMethod: 'raw-fallback'
    };
}

/**
 * 디버그용: 파싱 결과 요약 출력
 * 
 * @param {string} text - AI 응답 텍스트
 * @returns {Object} - 디버그 정보
 */
function debugParse(text) {
    const result = parseAIResponse(text);
    return {
        parseMethod: result.parseMethod,
        hasTitle: !!result.title,
        titleLength: result.title?.length || 0,
        hasContent: !!result.content,
        contentLength: result.content?.length || 0,
        hashtagCount: result.hashtags?.length || 0,
        firstChars: result.content?.substring(0, 100) || ''
    };
}

module.exports = {
    extractTag,
    extractMultipleTags,
    parseStandardOutput,
    extractNestedTags,
    extractTagAttribute,
    parseTextProtocol,
    parseAIResponse,
    debugParse
};
