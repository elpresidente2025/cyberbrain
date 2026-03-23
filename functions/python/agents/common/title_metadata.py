"""?? ??? ?????/??/??? ??."""

import re
from typing import Any, Dict, List, Optional

from .title_common import (
    EVENT_NAME_MARKERS,
    TITLE_LENGTH_HARD_MAX,
    _fit_title_length,
    extract_numbers_from_content,
    normalize_title_surface,
)

def _detect_event_label(topic: str) -> str:
    for marker in EVENT_NAME_MARKERS:
        if marker in (topic or ''):
            return marker
    return '행사'

def _extract_date_hint(text: str) -> str:
    if not text:
        return ''
    month_day = re.search(r'(\d{1,2}\s*월\s*\d{1,2}\s*일)', text)
    if month_day:
        return re.sub(r'\s+', ' ', month_day.group(1)).strip()
    iso_like = re.search(r'(\d{4}[./-]\d{1,2}[./-]\d{1,2})', text)
    if iso_like:
        return iso_like.group(1).strip()
    return ''

def _contains_date_hint(title: str, date_hint: str) -> bool:
    if not title:
        return False
    if date_hint:
        no_space_title = re.sub(r'\s+', '', title)
        no_space_hint = re.sub(r'\s+', '', date_hint)
        if no_space_hint in no_space_title:
            return True
        month_day = re.search(r'(\d{1,2})\s*월\s*(\d{1,2})\s*일', date_hint)
        if month_day:
            m, d = month_day.group(1), month_day.group(2)
            if re.search(fr'{m}\s*월\s*{d}\s*일', title):
                return True
    return bool(_extract_date_hint(title))

def _normalize_digit_token(value: str) -> str:
    digits = re.sub(r'\D', '', str(value or ''))
    if not digits:
        return ''
    normalized = digits.lstrip('0')
    return normalized or '0'

def _extract_digit_tokens(text: str) -> List[str]:
    if not text:
        return []
    tokens = []
    seen = set()
    for match in re.findall(r'\d+', str(text)):
        normalized = _normalize_digit_token(match)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(normalized)
    return tokens

def _split_hint_tokens(text: str) -> List[str]:
    if not text:
        return []
    clean = re.sub(r'[\(\)\[\]\{\},]', ' ', str(text))
    tokens = [t.strip() for t in re.split(r'\s+', clean) if t.strip()]
    result: List[str] = []
    for token in tokens:
        if len(token) >= 2:
            result.append(token)
    return result

def resolve_title_purpose(topic: str, params: Dict[str, Any]) -> str:
    event_markers = EVENT_NAME_MARKERS + (
        '행사',
        '개최',
        '열리는',
        '열립니다',
        '초대',
        '참석',
    )
    if any(marker in (topic or '') for marker in event_markers):
        return 'event_announcement'

    context_analysis = params.get('contextAnalysis') if isinstance(params.get('contextAnalysis'), dict) else {}
    intent = str(context_analysis.get('intent') or '').strip().lower()
    offline_intents = {
        'event_announcement',
        'offline_engagement',
        'event_participation',
        'event_attendance',
        'brief_notice',
        'schedule_notice',
    }
    if intent in offline_intents:
        return 'event_announcement'
    if intent:
        return intent
    return ''

BOOK_TITLE_QUOTE_PATTERNS = (
    ('angle', re.compile(r'<\s*([^<>]{2,80}?)\s*>')),
    ('double_angle', re.compile(r'《\s*([^《》]{2,80}?)\s*》')),
    ('single_angle', re.compile(r'〈\s*([^〈〉]{2,80}?)\s*〉')),
    ('double_quote', re.compile(r'"\s*([^"\n]{2,80}?)\s*"')),
    ('single_quote', re.compile(r"'\s*([^'\n]{2,80}?)\s*'")),
    ('curly_double_quote', re.compile(r'“\s*([^”\n]{2,80}?)\s*”')),
    ('curly_single_quote', re.compile(r'‘\s*([^’\n]{2,80}?)\s*’')),
    ('corner_quote', re.compile(r'「\s*([^「」]{2,80}?)\s*」')),
    ('white_corner_quote', re.compile(r'『\s*([^『』]{2,80}?)\s*』')),
)
BOOK_TITLE_WRAPPER_PAIRS = (
    ('<', '>'),
    ('《', '》'),
    ('〈', '〉'),
    ('「', '」'),
    ('『', '』'),
    ('"', '"'),
    ("'", "'"),
    ('“', '”'),
    ('‘', '’'),
)
BOOK_TITLE_CONTEXT_MARKERS = (
    '책',
    '저서',
    '도서',
    '신간',
    '출간',
    '출판',
    '북토크',
    '토크콘서트',
    '출판행사',
    '출판기념회',
    '제목',
)
BOOK_TITLE_EVENT_MARKERS = (
    '출판기념회',
    '북토크',
    '토크콘서트',
    '출판행사',
    '출간기념',
)
BOOK_TITLE_DISALLOWED_TOKENS = (
    '출판기념회',
    '북토크',
    '토크콘서트',
    '행사',
    '초대',
    '안내',
    '개최',
)
BOOK_TITLE_LOCATION_HINTS = (
    '도서',
    '센터',
    '홀',
    '광장',
    '시청',
    '구청',
)
BOOK_TITLE_LOCATION_SUFFIXES = (
    '도서',
    '센터',
    '홀',
    '광장',
    '시청',
    '구청',
)

def _normalize_book_title_candidate(text: str) -> str:
    normalized = str(text or '').strip()
    if not normalized:
        return ''

    while True:
        changed = False
        for left, right in BOOK_TITLE_WRAPPER_PAIRS:
            if normalized.startswith(left) and normalized.endswith(right) and len(normalized) > len(left) + len(right):
                normalized = normalized[len(left):len(normalized) - len(right)].strip()
                changed = True
        if not changed:
            break

    normalized = normalize_title_surface(normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip(' ,')
    normalized = re.sub(r'^[\-–—:;]+', '', normalized).strip()
    normalized = re.sub(r'[\-–—:;]+$', '', normalized).strip()
    return normalized

def _collect_book_title_candidates(topic: str) -> List[Dict[str, Any]]:
    text = str(topic or '').strip()
    if not text:
        return []

    candidates: List[Dict[str, Any]] = []

    for source, pattern in BOOK_TITLE_QUOTE_PATTERNS:
        for match in pattern.finditer(text):
            raw = str(match.group(1) or '').strip()
            if not raw:
                continue
            candidates.append(
                {
                    'raw': raw,
                    'start': int(match.start(1)),
                    'end': int(match.end(1)),
                    'source': source,
                }
            )

    event_pattern = re.compile(
        r'([가-힣A-Za-z0-9][^\n]{1,80}?)\s*(?:출판기념회|북토크|토크콘서트|출판행사)'
    )
    for match in event_pattern.finditer(text):
        raw = str(match.group(1) or '').strip()
        if not raw:
            continue
        candidates.append(
            {
                'raw': raw,
                'start': int(match.start(1)),
                'end': int(match.end(1)),
                'source': 'event_context',
            }
        )

    after_book_pattern = re.compile(
        r'(?:^|[\s\(\[\{\'"“‘<《])(?:책|저서|도서|신간|작품|제목)\s*(?:(?:은|는|이|가)\s+|[:：]\s*)?([^\n]{2,80})'
    )
    for match in after_book_pattern.finditer(text):
        raw = str(match.group(1) or '').strip()
        if not raw:
            continue
        clipped = re.split(r'(?:출판기념회|북토크|토크콘서트|출판행사|안내|초대|개최|에서|현장)', raw, maxsplit=1)[0].strip()
        if clipped:
            candidates.append(
                {
                    'raw': clipped,
                    'start': int(match.start(1)),
                    'end': int(match.start(1) + len(clipped)),
                    'source': 'book_context',
                }
            )

    return candidates

def _score_book_title_candidate(
    candidate: Dict[str, Any],
    topic: str,
    full_name: str,
) -> int:
    raw = str(candidate.get('raw') or '')
    text = _normalize_book_title_candidate(raw)
    if not text:
        return -999

    if not re.search(r'[가-힣A-Za-z0-9]', text):
        return -999

    score = 0
    source = str(candidate.get('source') or '')
    start = int(candidate.get('start') or 0)
    end = int(candidate.get('end') or start)
    topic_text = str(topic or '')

    if source in {'angle', 'double_angle', 'single_angle', 'double_quote', 'single_quote', 'curly_double_quote', 'curly_single_quote', 'corner_quote', 'white_corner_quote'}:
        score += 5
    elif source in {'author_event_context', 'event_context', 'book_context'}:
        score += 3

    if 4 <= len(text) <= 30:
        score += 3
    elif 2 <= len(text) <= 45:
        score += 1
    else:
        score -= 4

    if len(text) <= 3:
        score -= 5

    for token in BOOK_TITLE_DISALLOWED_TOKENS:
        if token in text:
            score -= 8

    if full_name and text == full_name:
        score -= 8

    if re.fullmatch(r'[\d\s.,:/-]+', text):
        score -= 6
    if re.search(r'\d+\s*월(?:\s*\d+\s*일)?', text):
        score -= 10
    if any(ch in text for ch in '<>《》〈〉「」『』'):
        score -= 8

    left_context = topic_text[max(0, start - 22):start]
    right_context = topic_text[end:min(len(topic_text), end + 22)]
    around_context = f'{left_context} {right_context}'

    if any(marker in around_context for marker in BOOK_TITLE_CONTEXT_MARKERS):
        score += 5
    if any(marker in right_context for marker in BOOK_TITLE_EVENT_MARKERS):
        score += 4
    if any(marker in left_context for marker in BOOK_TITLE_EVENT_MARKERS):
        score += 2

    has_location_hint = any(loc in text for loc in BOOK_TITLE_LOCATION_HINTS)
    if has_location_hint:
        score -= 2
        if source in {'event_context', 'book_context'}:
            score -= 4
    if any(text.endswith(suffix) for suffix in BOOK_TITLE_LOCATION_SUFFIXES):
        score -= 12
    if source in {'event_context', 'book_context'} and not any(marker in text for marker in BOOK_TITLE_CONTEXT_MARKERS):
        score -= 3

    if ',' in text or '·' in text:
        score += 1

    return score

def _extract_book_title(topic: str, params: Optional[Dict[str, Any]] = None) -> str:
    if not topic:
        return ''

    full_name = ''
    if isinstance(params, dict):
        full_name = str(params.get('fullName') or '').strip()

        context_analysis = params.get('contextAnalysis') if isinstance(params.get('contextAnalysis'), dict) else {}
        must_preserve = context_analysis.get('mustPreserve') if isinstance(context_analysis.get('mustPreserve'), dict) else {}
        explicit = _normalize_book_title_candidate(str(must_preserve.get('bookTitle') or ''))
        if explicit:
            return explicit

    candidates = _collect_book_title_candidates(topic)
    if full_name:
        author_event_pattern = re.compile(
            rf'{re.escape(full_name)}\s+([^\n]{{2,80}}?)\s*(?:출판기념회|북토크|토크콘서트|출판행사)'
        )
        for match in author_event_pattern.finditer(str(topic)):
            raw = str(match.group(1) or '').strip()
            if not raw:
                continue
            candidates.append(
                {
                    'raw': raw,
                    'start': int(match.start(1)),
                    'end': int(match.end(1)),
                    'source': 'author_event_context',
                }
            )
    best_title = ''
    best_score = -999
    seen: set[str] = set()

    for candidate in candidates:
        normalized = _normalize_book_title_candidate(str(candidate.get('raw') or ''))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        nested_candidates = _collect_book_title_candidates(normalized)
        nested_title = ''
        nested_score = -999
        for nested in nested_candidates:
            nested_score_candidate = _score_book_title_candidate(nested, normalized, full_name)
            nested_normalized = _normalize_book_title_candidate(str(nested.get('raw') or ''))
            if nested_score_candidate > nested_score and nested_normalized:
                nested_score = nested_score_candidate
                nested_title = nested_normalized

        score = _score_book_title_candidate(candidate, topic, full_name)
        title = normalized
        if nested_title and nested_score > score:
            score = nested_score
            title = nested_title

        if score > best_score:
            best_score = score
            best_title = title

    if best_score >= 5:
        if full_name and best_title.startswith(f'{full_name} '):
            tail = _normalize_book_title_candidate(best_title[len(full_name):])
            if tail:
                best_title = tail
        return best_title

    return ''

def _normalize_generated_title_without_fit(generated_title: str, params: Dict[str, Any]) -> str:
    if not generated_title:
        return ''

    normalized = normalize_title_surface(generated_title)
    # 도서명 꺾쇠 표기는 유지하되 내부 공백만 정리한다.
    normalized = re.sub(r'<\s*([^>]+?)\s*>', r'<\1>', normalized)
    normalized = re.sub(r'《\s*([^》]+?)\s*》', r'《\1》', normalized)
    normalized = re.sub(r'\s+,', ',', normalized)
    normalized = re.sub(r',\s*,', ',', normalized)
    normalized = normalize_title_surface(normalized)

    topic = str(params.get('topic') or '')
    title_purpose = resolve_title_purpose(topic, params)
    book_title = _extract_book_title(topic, params) if title_purpose == 'event_announcement' else ''
    if book_title:
        # 모델이 빈 꺾쇠(<>, 《》)를 출력한 경우 책 제목을 복원한다.
        if re.search(r'<\s*>', normalized) and book_title not in normalized:
            normalized = re.sub(r'<\s*>', f'<{book_title}>', normalized)
        if re.search(r'《\s*》', normalized) and book_title not in normalized:
            normalized = re.sub(r'《\s*》', f'《{book_title}》', normalized)
        normalized = normalize_title_surface(normalized)

    return normalized

def _normalize_generated_title(generated_title: str, params: Dict[str, Any]) -> str:
    normalized = _normalize_generated_title_without_fit(generated_title, params)
    if not normalized:
        return ''

    topic = str(params.get('topic') or '')
    title_purpose = resolve_title_purpose(topic, params)

    if len(normalized) <= TITLE_LENGTH_HARD_MAX:
        return normalized

    if title_purpose == 'event_announcement':
        normalized = re.sub(r'\s{2,}', ' ', normalized).strip(' ,')
        if len(normalized) <= TITLE_LENGTH_HARD_MAX:
            return normalized

    return _fit_title_length(normalized)
