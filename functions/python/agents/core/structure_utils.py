import re
from html import escape as _xml_escape_raw
from typing import Dict, Any, List

def strip_html(text: str) -> str:
    if not text:
        return ''
    text = re.sub(r'<[^>]*>', '', text)
    return re.sub(r'\s+', '', text).strip()

def normalize_artifacts(text: str) -> str:
    if not text:
        return ''
    cleaned = text.strip()
    cleaned = re.sub(
        r'```(?:[\w.+-]+)?\s*([\s\S]*?)\s*```',
        lambda m: m.group(1).strip(),
        cleaned,
    ).strip()
    cleaned = re.sub(r'^\s*\\"', '', cleaned)
    cleaned = re.sub(r'\\"?\s*$', '', cleaned)
    cleaned = re.sub(r'^\s*["“]', '', cleaned)
    cleaned = re.sub(r'["”]\s*$', '', cleaned)
    lines = cleaned.splitlines()
    metadata_line_re = re.compile(
        r'^\s*\*{0,2}(카테고리|검색어 삽입 횟수|생성 시간)\*{0,2}\s*:\s*',
        re.IGNORECASE,
    )
    tail_cut_index = None
    if lines:
        tail_window_start = max(0, len(lines) - 8)
        for i in range(tail_window_start, len(lines)):
            line = lines[i].strip()
            if not line:
                continue
            if '<' in line and '>' in line:
                continue
            if metadata_line_re.match(line):
                tail_cut_index = i
                break
    if tail_cut_index is not None:
        cleaned = "\n".join(lines[:tail_cut_index]).strip()
    cleaned = re.sub(r'"content"\s*:\s*', '', cleaned)
    return cleaned.strip()

def normalize_html_structure_tags(text: str) -> str:
    if not text:
        return ''
    normalized = text
    normalized = re.sub(r'<\s*h2\b[^>]*>', '<h2>', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'<\s*/\s*h2\s*>', '</h2>', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'<\s*p\b[^>]*>', '<p>', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'<\s*/\s*p\s*>', '</p>', normalized, flags=re.IGNORECASE)
    return normalized

def is_example_like_block(text: str) -> bool:
    if not text:
        return True
    lowered = text.lower()
    placeholder_count = len(re.findall(r'\[[^\]\n]{1,40}\]', text))
    marker_count = sum(
        1 for marker in (
            'sample_output', 'reference_example', 'placeholder', '예시', '샘플', '여기에', '작성'
        ) if marker in lowered
    )
    plain_len = len(strip_html(text))
    return placeholder_count >= 2 or ('<![cdata[' in lowered and plain_len < 900) or (marker_count >= 1 and plain_len < 900)

def normalize_context_text(value: Any, *, sep: str = "\n\n") -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple, set)):
        parts: List[str] = []
        for item in value:
            normalized = normalize_context_text(item, sep=sep)
            if normalized:
                parts.append(normalized)
        return sep.join(parts)
    return str(value).strip()

def _xml_text(value: Any) -> str:
    return _xml_escape_raw(str(value or ""), quote=True)

def _xml_cdata(value: Any) -> str:
    text = str(value or "")
    safe = text.replace("]]>", "]]]]><![CDATA[>")
    return f"<![CDATA[{safe}]]>"

def material_key(value: Any) -> str:
    text = normalize_context_text(value)
    if not text:
        return ""
    text = strip_html(text).lower()
    text = re.sub(r'["\'`“”‘’\[\]\(\)<>]', '', text)
    text = re.sub(r'[\s\.,!?;:·~\-_\\/]+', '', text)
    return text

def split_into_context_items(text: str, *, min_len: int = 14, max_items: int = 40) -> List[str]:
    if not text:
        return []
    normalized = normalize_context_text(text, sep="\n")
    if not normalized:
        return []
    raw_parts = re.split(r'[\r\n]+|[;·•]+|(?<=[.!?。])\s+|다\.\s+', normalized)
    items: List[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        cleaned = re.sub(r'\s+', ' ', str(part or "")).strip(" \t-•")
        if not cleaned: continue
        if len(strip_html(cleaned)) < min_len: continue
        if len(cleaned) > 220: cleaned = cleaned[:220].rstrip() + "..."
        key = cleaned.lower()
        if key in seen: continue
        seen.add(key)
        items.append(cleaned)
        if len(items) >= max_items: break
    return items

def repair_structural_tags(text: str) -> str:
    if not text: return ""
    text = re.sub(r'^(?:##\s*)(.+)$', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    def custom_tag_replacer(m):
        heading = m.group(2).strip()
        content = m.group(3)
        if heading.lower() in ('없음', 'none', 'false') or not heading: return content
        return f"<h2>{heading}</h2>\n{content}"
    text = re.sub(r'<(body_section|conclusion|section|intro)[^>]*heading=["\']([^"\']*)["\'][^>]*>([\s\S]*?)</\1>', custom_tag_replacer, text, flags=re.IGNORECASE)
    lines = text.split('\n')
    repaired_lines = []
    in_content_block = False
    for line in lines:
        stripped = line.strip()
        if '<content>' in stripped:
            in_content_block = True
            repaired_lines.append(line)
            continue
        if '</content>' in stripped:
            in_content_block = False
            repaired_lines.append(line)
            continue
        if in_content_block and stripped:
            if not re.match(r'^<[/a-zA-Z0-9]+>', stripped) and not re.search(r'<[^>]+>$', stripped):
                line = f"<p>{stripped}</p>"
        repaired_lines.append(line)
    return '\n'.join(repaired_lines)

def parse_response(response: str) -> Dict[str, str]:
    if not response: return {'content': '', 'title': ''}
    response = repair_structural_tags(response)
    try:
        def extract_html_fallback(text: str) -> str:
            html_blocks = re.findall(r'<(?:p|h[23])\b[^>]*>[\s\S]*?</(?:p|h[23])>', text or '', re.IGNORECASE)
            return "\n".join(html_blocks).strip() if html_blocks else ''

        title_blocks = [(m.group(1) or "").strip() for m in re.finditer(r'<title>(.*?)</title>', response, re.DOTALL | re.IGNORECASE)]
        title = next((t for t in reversed(title_blocks) if t), '')
        content_blocks = [(m.group(1) or "").strip() for m in re.finditer(r'<content>(.*?)</content>', response, re.DOTALL | re.IGNORECASE)]
        content = ''
        if content_blocks:
            candidates = []
            for idx, block in enumerate(content_blocks):
                normalized = normalize_html_structure_tags(normalize_artifacts(block))
                tag_density = len(re.findall(r'<(?:h2|p)\b', normalized, re.IGNORECASE))
                plain_len = len(strip_html(normalized))
                candidates.append({'index': idx, 'content': normalized, 'tag_density': tag_density, 'plain_len': plain_len, 'is_example': is_example_like_block(normalized)})
            real_candidates = [c for c in candidates if not c['is_example']]
            pool = real_candidates if real_candidates else candidates
            max_plain_len = max((c['plain_len'] for c in pool), default=0)
            min_plain_threshold = max(300, int(max_plain_len * 0.45))
            length_filtered_pool = [c for c in pool if c['plain_len'] >= min_plain_threshold]
            selection_pool = length_filtered_pool if length_filtered_pool else pool
            selected = max(selection_pool, key=lambda c: (c['plain_len'], c['tag_density'], c['index']))
            content = selected['content'].strip()
            selected_plain_len = selected['plain_len']
            selected_idx = selected['index']
            if selected_idx < len(title_blocks):
                aligned_title = (title_blocks[selected_idx] or '').strip()
                if aligned_title: title = aligned_title
            fallback_content = extract_html_fallback(response)
            fallback_plain_len = len(strip_html(fallback_content))
            fallback_is_example = is_example_like_block(fallback_content)
            if not fallback_is_example and selected_plain_len < 180 and fallback_plain_len >= max(260, selected_plain_len + 120):
                content = fallback_content
        if not content:
            fallback_content = extract_html_fallback(response)
            if fallback_content: content = fallback_content
            else: content = response
        return {'content': content, 'title': title}
    except Exception as e:
        return {'content': response, 'title': ''}
