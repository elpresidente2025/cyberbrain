import re
from typing import Dict, List, Optional, Any

def extract_tag(text: str, tag_name: str) -> Optional[str]:
    """
    단일 태그 내용 추출 (Robust Regex)
    """
    if not text or not tag_name:
        return None
    
    escaped_tag = re.escape(tag_name)
    
    # 1. Normal: <tag ... > ... </tag>
    normal_pattern = re.compile(f'<{escaped_tag}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/{escaped_tag}>', re.IGNORECASE)
    match = normal_pattern.search(text)
    if match:
        return match.group(1).strip()
        
    # 2. Unclosed: <tag ... > ... <next_tag> or EOS
    # Lookahead for next tag start
    unclosed_pattern = re.compile(
        f'<{escaped_tag}(?:\\s[^>]*)?>([\\s\\S]*?)(?=<[a-zA-Z_][a-zA-Z0-9_-]*(?:\\s|>)|$)',
        re.IGNORECASE
    )
    match = unclosed_pattern.search(text)
    if match:
        content = match.group(1).strip()
        if content:
            return content
            
    # 3. Self-closing: <tag content="..." />
    self_closing_pattern = re.compile(
        f'<{escaped_tag}\\s+(?:content|value)=["\']([^"\']*)["\']\\s*/?>',
        re.IGNORECASE
    )
    match = self_closing_pattern.search(text)
    if match:
        return match.group(1).strip()
        
    return None

def extract_multiple_tags(text: str, tag_names: List[str]) -> Dict[str, Optional[str]]:
    if not text or not tag_names:
        return {}
    
    result = {}
    for tag in tag_names:
        result[tag] = extract_tag(text, tag)
    return result

def parse_standard_output(text: str) -> Dict[str, Any]:
    """
    Standard XML Parsing for title, content, summary, hashtags.
    """
    title = extract_tag(text, 'title')
    content = extract_tag(text, 'content')
    summary = extract_tag(text, 'summary')
    hashtags_raw = extract_tag(text, 'hashtags')
    
    hashtags = []
    if hashtags_raw:
        # Split by comma, newline, spaces
        parts = re.split(r'[,\n\s]+', hashtags_raw)
        hashtags = [h.strip() for h in parts if h.strip()]
        hashtags = [h if h.startswith('#') else f'#{h}' for h in hashtags]
        # De-duplicate
        hashtags = list(dict.fromkeys(hashtags))
        
    return {
        'title': title,
        'content': content,
        'hashtags': hashtags,
        'summary': summary
    }

def extract_nested_tags(text: str, container_tag: str, item_tag: str) -> List[str]:
    """
    Extract nested tags like <rules><rule>...</rule></rules>
    """
    if not text or not container_tag or not item_tag:
        return []
        
    container_content = extract_tag(text, container_tag)
    if not container_content:
        return []
        
    escaped_item = re.escape(item_tag)
    item_pattern = re.compile(f'<{escaped_item}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/{escaped_item}>', re.IGNORECASE)
    
    items = []
    for match in item_pattern.finditer(container_content):
        items.append(match.group(1).strip())
        
    return items

def extract_tag_attribute(text: str, tag_name: str, attr_name: str) -> Optional[str]:
    if not text or not tag_name or not attr_name:
        return None
        
    escaped_tag = re.escape(tag_name)
    escaped_attr = re.escape(attr_name)
    
    pattern = re.compile(
        f'<{escaped_tag}[^>]*\\s{escaped_attr}=["\']([^"\']*)["\'][^>]*>',
        re.IGNORECASE
    )
    
    match = pattern.search(text)
    return match.group(1) if match else None

def parse_text_protocol(text: str, fallback_title: str = '') -> Dict[str, str]:
    if not text:
        return {'title': fallback_title, 'content': ''}
        
    clean = text.strip()
    
    # Remove markdown code blocks
    if clean.startswith('```'):
        clean = re.sub(r'^```(?:html|text|json)?[\s\n]*', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'[\s\n]*```$', '', clean)
        
    title_match = re.search(r'===TITLE===\s*([\s\S]*?)\s*===CONTENT===', clean)
    content_match = re.search(r'===CONTENT===\s*([\s\S]*)', clean)
    
    title = title_match.group(1).strip() if title_match else fallback_title
    
    content = ''
    if content_match:
        content = content_match.group(1).strip()
    elif not title_match:
        # If no separators, assume all is content
        content = clean
        
    return {'title': title, 'content': content}

def parse_ai_response(text: str, fallback_title: str = '') -> Dict[str, Any]:
    if not text or not isinstance(text, str):
         return {
            'title': fallback_title,
            'content': '',
            'hashtags': [],
            'parseMethod': 'fallback'
        }
        
    # 1. XML Parsing
    xml_result = parse_standard_output(text)
    if xml_result.get('title') or xml_result.get('content'):
        return {
            **xml_result,
            'title': xml_result.get('title') or fallback_title,
            'parseMethod': 'xml'
        }
        
    # 2. Text Protocol
    text_result = parse_text_protocol(text, fallback_title)
    if text_result.get('content'):
        return {
            'title': text_result.get('title'),
            'content': text_result.get('content'),
            'hashtags': [],
            'parseMethod': 'text-protocol'
        }
        
    # 3. Fallback
    return {
        'title': fallback_title,
        'content': text.strip(),
        'hashtags': [],
        'parseMethod': 'raw-fallback'
    }

def debug_parse(text: str) -> Dict[str, Any]:
    result = parse_ai_response(text)
    return {
        'parseMethod': result.get('parseMethod'),
        'hasTitle': bool(result.get('title')),
        'titleLength': len(result.get('title') or ''),
        'hasContent': bool(result.get('content')),
        'contentLength': len(result.get('content') or ''),
        'hashtagCount': len(result.get('hashtags') or []),
        'firstChars': (result.get('content') or '')[:100]
    }
