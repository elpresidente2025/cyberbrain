
import re
from bs4 import BeautifulSoup

# ==============================================================================
# Constants & Regex Patterns
# ==============================================================================

SUMMARY_PARAGRAPH_REGEX = re.compile(r'<p[^>]*data-summary=["\']true["\'][^>]*>[\s\S]*?</p>', re.IGNORECASE)
CONCLUSION_HEADING_REGEX = re.compile(r'<h[23][^>]*>[^<]*(정리|결론|요약|마무리|다짐|미래|변화|과제|인사)[^<]*</h[23]>', re.IGNORECASE)
HEADING_TAG_REGEX = re.compile(r'<h[23][^>]*>[\s\S]*?</h[23]>', re.IGNORECASE)
CONTENT_BLOCK_REGEX = re.compile(r'<p[^>]*>[\s\S]*?</p>|<ul[^>]*>[\s\S]*?</ul>|<ol[^>]*>[\s\S]*?</ol>', re.IGNORECASE)

SIGNATURE_MARKERS = [
    '부산의 준비된 신상품', '부산경제는 이재성', '감사합니다', '감사드립니다', 
    '고맙습니다', '사랑합니다', '드림'
]

# 비문 패턴 중앙 집중 처리
GRAMMATICAL_ERROR_PATTERNS = [
    (re.compile(r'것이라는 점입니다'), '것입니다'),
    (re.compile(r'거라는 점입니다'), '것입니다'),
    (re.compile(r'한다는 점입니다'), '합니다'),
    (re.compile(r'하다는 점입니다'), '합니다'),
    (re.compile(r'된다는 점입니다'), '됩니다'),
    (re.compile(r'있다는 점입니다'), '있습니다'),
    (re.compile(r'없다는 점입니다'), '없습니다'),
    (re.compile(r'이라는 점입니다'), '입니다'),
    (re.compile(r'라는 점입니다'), '입니다'),
    (re.compile(r'것일 것입니다'), '것입니다'),
    (re.compile(r'있을 것일 것입니다'), '있을 것입니다'),
    (re.compile(r'없을 것일 것입니다'), '없을 것입니다'),
    (re.compile(r'될 것일 것입니다'), '될 것입니다'),
    (re.compile(r'할 것일 것입니다'), '할 것입니다')
]

# ==============================================================================
# Helper Functions
# ==============================================================================

def strip_html(text: str) -> str:
    """HTML 태그 제거"""
    if not text:
        return ""
    text = re.sub(r'<[^>]*>', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()

def normalize_heading_spaces(text: str) -> str:
    return re.sub(r'\s+', ' ', text or "").strip()

def find_last_index_of_any(text: str, markers: list) -> int:
    max_index = -1
    for marker in markers:
        index = text.rfind(marker)
        if index > max_index:
            max_index = index
    return max_index

def split_content_by_signature(content: str) -> tuple[str, str]:
    if not content:
        return "", ""
    
    signature_index = find_last_index_of_any(content, SIGNATURE_MARKERS)
    if signature_index == -1:
        return content, ""

    paragraph_start = content.rfind('<p', 0, signature_index)
    if paragraph_start != -1:
        return content[:paragraph_start].strip(), content[paragraph_start:].strip()

    return content[:signature_index].strip(), content[signature_index:].strip()

def join_content(body: str, tail: str) -> str:
    if not tail:
        return body
    if not body:
        return tail
    combined = f"{body}\n{tail}"
    return re.sub(r'\n{3,}', '\n\n', combined)

# ==============================================================================
# Core Processing Functions
# ==============================================================================

def remove_artifacts(content: str) -> str:
    """메타데이터 및 불필요한 아티팩트 제거"""
    if not content:
        return content
    
    cleaned = content
    
    # 1. 앞뒤 따옴표/이스케이프 문자 제거
    while True:
        original = cleaned
        cleaned = cleaned.strip()
        if cleaned.startswith('"') or cleaned.startswith('“'): cleaned = cleaned[1:]
        if cleaned.endswith('"') or cleaned.endswith('”'): cleaned = cleaned[:-1]
        if cleaned.startswith('\\"'): cleaned = cleaned[2:]
        if cleaned.endswith('\\"'): cleaned = cleaned[:-2]
        
        if cleaned == original:
            break
            
    # 2. 메타데이터 라인 제거
    cleaned = re.sub(r'카테고리:[\s\S]*$', '', cleaned)
    cleaned = re.sub(r'검색어 삽입 횟수:[\s\S]*$', '', cleaned)
    cleaned = re.sub(r'생성 시간:[\s\S]*$', '', cleaned)
    
    # 3. JSON 키 잔여물 제거
    cleaned = re.sub(r'"content"\s*:\s*', '', cleaned)
    
    return cleaned.strip()

def remove_grammatical_errors(content: str) -> str:
    """비문 및 어색한 표현 수정"""
    if not content:
        return content
    
    fixed = content
    for pattern, replacement in GRAMMATICAL_ERROR_PATTERNS:
        fixed = pattern.sub(replacement, fixed)
    return fixed

def ensure_paragraph_tags(content: str) -> str:
    """모든 문단을 <p> 태그로 감싸기 (이미 태그가 있는 경우 제외)"""
    if not content:
        return content
    
    if re.search(r'<p\b', content, re.IGNORECASE):
        return content
        
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return content
        
    wrapped = []
    for line in lines:
        if re.match(r'^<h[23]\b', line, re.IGNORECASE) or \
           re.match(r'^<ul\b', line, re.IGNORECASE) or \
           re.match(r'^<ol\b', line, re.IGNORECASE):
            wrapped.append(line)
        else:
            wrapped.append(f"<p>{line}</p>")
            
    return "\n".join(wrapped)

def strip_markdown_emphasis(content: str) -> str:
    if not content:
        return content
    return content.replace('**', '')

def normalize_paragraph_endings(content: str) -> str:
    """문단 끝 정규화 (BS4 사용)"""
    # Python에서는 정규식만으로 HTML 파싱이 어려우므로 
    # 간단한 경우만 처리하거나 BS4 활용.
    # 여기선 1차적으로 정규식 기반 처리 (Node.js 로직 유사하게)
    if not content:
        return content
        
    def replacer(match):
        full_p = match.group(0)
        inner = re.sub(r'^<p[^>]*>', '', full_p, flags=re.IGNORECASE)
        inner = re.sub(r'</p>$', '', inner, flags=re.IGNORECASE)
        
        if re.search(r'<[^>]+>', inner): # 태그가 더 있으면 건너뜀
            return full_p
            
        plain = re.sub(r'\s+', ' ', inner).strip()
        if not plain:
            return full_p
            
        # TODO: dedupeRepeatedEndings logic is complex. 
        # For now, just return cleaned plain text.
        return f"<p>{plain}</p>"

    return re.sub(r'<p[^>]*>[\s\S]*?</p>', replacer, content, flags=re.IGNORECASE)

def strip_empty_heading_sections(content: str) -> str:
    """내용이 없는 소제목 섹션 제거"""
    if not content:
        return content
    # Lookahead pattern mostly works in Python re module
    return re.sub(r'<h([23])[^>]*>[\s\S]*?</h\1>\s*(?=<h[23][^>]*>|$)', '', content, flags=re.IGNORECASE)


def move_summary_to_conclusion_start(content: str) -> str:
    """
    data-summary="true" 속성이 있는 문단(요약문)을 찾아,
    결론("정리", "마무리" 등) 소제목 바로 다음으로 이동시킴.
    """
    if not content:
        return content
        
    body, tail = split_content_by_signature(content)
    
    summary_matches = list(SUMMARY_PARAGRAPH_REGEX.finditer(body))
    if not summary_matches:
        return content
        
    summaries = [m.group(0) for m in summary_matches]
    
    # Remove summaries from original position
    cleaned_body = SUMMARY_PARAGRAPH_REGEX.sub('', body)
    cleaned_body = re.sub(r'\n{3,}', '\n\n', cleaned_body).strip()
    
    # Find conclusion heading
    heading_match = CONCLUSION_HEADING_REGEX.search(cleaned_body)
    
    if heading_match:
        insert_index = heading_match.end()
        # Insert after heading
        summary_text = "\n".join(summaries)
        cleaned_body = f"{cleaned_body[:insert_index]}\n{summary_text}\n{cleaned_body[insert_index:]}"
        cleaned_body = re.sub(r'\n{3,}', '\n\n', cleaned_body)
    else:
        # Append to end if no conclusion heading
        summary_text = "\n".join(summaries)
        cleaned_body = f"{cleaned_body}\n{summary_text}".strip()
        
    return join_content(cleaned_body, tail)


def cleanup_post_content(content: str) -> str:
    """
    메인 정리 함수
    """
    if not content:
        return content
        
    # [0단계] 아티팩트 제거
    updated = remove_artifacts(content)
    
    # [1단계] 비문 및 포맷 정리
    updated = remove_grammatical_errors(updated)
    updated = strip_markdown_emphasis(updated)
    updated = ensure_paragraph_tags(updated) # ensure p tags first if strict
    updated = normalize_paragraph_endings(updated)
    updated = strip_empty_heading_sections(updated)
    
    # [2단계] 소수점 뒤 공백 제거 (0. 7% -> 0.7%)
    updated = re.sub(r'(\d)\.\s+(\d)', r'\1.\2', updated)
    
    # [3단계] 요약문 이동 (중요)
    updated = move_summary_to_conclusion_start(updated)
    
    return updated.strip()
