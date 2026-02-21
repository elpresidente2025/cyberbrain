import re
from typing import Dict, Any, Optional, List, Tuple
from .structure_utils import strip_html, material_key, normalize_context_text

class ContentValidator:
    def _detect_material_reuse_issues(
        self,
        content: str,
        context_analysis: Optional[Dict[str, Any]],
        *,
        max_mentions: int = 1,
    ) -> List[Dict[str, Any]]:
        if not content or not isinstance(context_analysis, dict):
            return []
        normalized_body = material_key(strip_html(content))
        if not normalized_body:
            return []
        candidates: List[Tuple[str, str]] = []
        for item in context_analysis.get('mustIncludeFromStance') or []:
            if isinstance(item, dict):
                candidates.append(("stance", normalize_context_text(item.get('topic'))))
            else:
                candidates.append(("stance", normalize_context_text(item)))
        for item in context_analysis.get('mustIncludeFacts') or []:
            candidates.append(("fact", normalize_context_text(item)))
        for item in context_analysis.get('newsQuotes') or []:
            candidates.append(("quote", normalize_context_text(item)))
        issues: List[Dict[str, Any]] = []
        seen_keys: set[str] = set()
        for material_type, text in candidates:
            key = material_key(text)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            if len(key) < 16:
                continue
            count = normalized_body.count(key)
            if count > max_mentions:
                issues.append({"type": material_type, "text": text, "count": count})
        return issues

    def _split_plain_sentences(self, text: str) -> List[str]:
        if not text:
            return []
        chunks = re.findall(r'[^.!?。]+[.!?。]?', text)
        sentences = []
        for chunk in chunks:
            sentence = re.sub(r'\s+', ' ', chunk).strip()
            if sentence:
                sentences.append(sentence)
        return sentences

    def _find_meta_prompt_leak_sentences(self, content: str) -> List[str]:
        plain_text = re.sub(r'<[^>]*>', ' ', content or '')
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        if not plain_text:
            return []
        patterns = [
            re.compile(r'문제는 .*현장 .*데이터.*점검해야', re.IGNORECASE),
            re.compile(r'관련 .*쟁점.*함께 .*봐야', re.IGNORECASE),
            re.compile(r'그래도 .*문제는 .*점검해야', re.IGNORECASE),
            re.compile(r'현장 .*데이터.*함께 .*점검', re.IGNORECASE),
        ]
        leaks: List[str] = []
        for sentence in self._split_plain_sentences(plain_text):
            if any(pattern.search(sentence) for pattern in patterns):
                leaks.append(sentence)
        return leaks

    def _count_event_fact_sentence_mentions(
        self, content: str, *, event_date_hint: str = '', event_location_hint: str = ''
    ) -> int:
        plain_text = re.sub(r'<[^>]*>', ' ', content or '')
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        if not plain_text:
            return 0
        location_tokens: List[str] = []
        for token in ('서면 영광도서', '부산 영광도서'):
            if token in plain_text:
                location_tokens.append(token)
        if event_location_hint:
            normalized_location_hint = re.sub(r'\s+', ' ', event_location_hint).strip()
            if normalized_location_hint and normalized_location_hint not in location_tokens:
                location_tokens.append(normalized_location_hint)
        date_tokens: List[str] = []
        if event_date_hint:
            for pattern in (
                r'\d{1,2}\s*월\s*\d{1,2}\s*일(?:\s*\([^)]+\))?',
                r'(?:오전|오후)\s*\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?',
            ):
                match = re.search(pattern, event_date_hint)
                if match:
                    date_tokens.append(re.sub(r'\s+', ' ', match.group(0)).strip())
        if not date_tokens:
            date_tokens = [r'\d{1,2}\s*월\s*\d{1,2}\s*일', r'(?:오전|오후)\s*\d{1,2}\s*시']
        count = 0
        for sentence in self._split_plain_sentences(plain_text):
            has_location = any(token and token in sentence for token in location_tokens)
            has_date = any(re.search(token, sentence) for token in date_tokens)
            if has_location and has_date:
                count += 1
        return count

    def _find_overused_anchor_phrases(self, content: str) -> List[str]:
        plain_text = re.sub(r'<[^>]*>', ' ', content or '')
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        if not plain_text:
            return []
        phrase_limits = {
            '부산항 부두 노동자의 막내로': 2,
            '시민 여러분과 함께': 2,
        }
        overused: List[str] = []
        for phrase, limit in phrase_limits.items():
            count = len(re.findall(re.escape(phrase), plain_text))
            if count > limit:
                overused.append(f'"{phrase}" {count}회')
        return overused

    def validate(
        self,
        content: str,
        length_spec: Dict[str, int],
        *,
        context_analysis: Optional[Dict[str, Any]] = None,
        is_event_announcement: bool = False,
        event_date_hint: str = '',
        event_location_hint: str = '',
        user_keywords: Optional[List[str]] = None,
    ) -> Dict:
        if not content:
            return {'passed': False, 'code': 'EMPTY_CONTENT', 'reason': '내용 없음', 'feedback': '내용이 비어있습니다.'}
        
        plain_length = len(strip_html(content))
        min_length = length_spec['min_chars']
        max_length = length_spec['max_chars']
        expected_h2 = length_spec['expected_h2']
        per_section_recommended = length_spec.get('per_section_recommended', 350)
        per_section_max = length_spec.get('per_section_max', 420)
        total_sections = length_spec.get('total_sections', 5)

        placeholder_count = len(re.findall(r'\[[^\]\n]{1,40}\]', content))
        if placeholder_count >= 2:
            return {'passed': False, 'code': 'TEMPLATE_ECHO', 'reason': f"예시/플레이스홀더 잔존 ({placeholder_count}개)", 'feedback': '예시 문구([제목], [구체적 내용] 등)를 모두 제거하고 실제 본문으로 작성하십시오.'}

        if plain_length < min_length:
            return {'passed': False, 'code': 'LENGTH_SHORT', 'reason': f"분량 부족 ({plain_length}자 < {min_length}자)", 'feedback': f"현재 분량({plain_length}자)이 최소 기준({min_length}자)보다 부족합니다. 섹션당 {per_section_recommended}자 안팎으로 구성하되, 총 {max_length}자를 넘기지 마십시오."}
        
        if plain_length > max_length:
            return {'passed': False, 'code': 'LENGTH_LONG', 'reason': f"분량 초과 ({plain_length}자 > {max_length}자)", 'feedback': f"현재 분량({plain_length}자)이 최대 기준({max_length}자)을 초과했습니다. 압축하십시오."}

        disallowed_heading_count = len(re.findall(r'<h(?!2\b)[1-6]\b[^>]*>', content, re.IGNORECASE))
        if disallowed_heading_count > 0:
            return {'passed': False, 'code': 'TAG_DISALLOWED', 'reason': f"허용되지 않은 heading 태그 사용 (h2 외 {disallowed_heading_count}개)", 'feedback': '소제목은 <h2>만 사용하십시오.'}

        h2_open_tags = re.findall(r'<h2\b[^>]*>', content, re.IGNORECASE)
        h2_close_tags = re.findall(r'</h2\s*>', content, re.IGNORECASE)
        h2_count = len(h2_open_tags)
        if h2_count != len(h2_close_tags):
            return {'passed': False, 'code': 'H2_MALFORMED', 'reason': f"h2 태그 짝 불일치", 'feedback': '모든 소제목은 <h2>...</h2> 형태로 정확히 닫아 주십시오.'}

        if h2_count < expected_h2:
            return {'passed': False, 'code': 'H2_SHORT', 'reason': f"소제목 부족", 'feedback': f"소제목(<h2>)이 부족합니다. <h2>를 정확히 {expected_h2}개 작성하십시오."}
        if h2_count > expected_h2:
            return {'passed': False, 'code': 'H2_LONG', 'reason': f"소제목 과다", 'feedback': f"소제목(<h2>)이 너무 많습니다. <h2>를 정확히 {expected_h2}개로 맞추십시오."}

        h2_texts = [strip_html(text).strip() for text in re.findall(r'<h2[^>]*>(.*?)</h2>', content, re.IGNORECASE | re.DOTALL)]
        for h2_text in h2_texts:
            if len(h2_text) > 25:
                return {'passed': False, 'code': 'H2_TEXT_LONG', 'reason': "h2 텍스트 길이 초과", 'feedback': f'h2 텍스트가 25자를 초과했습니다: "{h2_text}"'}
            if re.search(r'(합니다|입니다|됩니다|겠습니다|했습니다|봅니다|까요)\s*$', h2_text):
                return {'passed': False, 'code': 'H2_TEXT_PREDICATE', 'reason': "h2 텍스트가 서술어로 종료됨", 'feedback': f'서술어를 제거하십시오: "{h2_text}"'}
            if re.search(r'(위한|향한|만드는|통한|대한)(\s|$)', h2_text):
                return {'passed': False, 'code': 'H2_TEXT_MODIFIER', 'reason': "h2 금지된 수식어", 'feedback': f'금지 수식어(위한/향한/만드는/통한/대한)를 제거하십시오: "{h2_text}"'}

        section_blocks: List[str] = []
        first_h2_match = re.search(r'<h2\b', content, re.IGNORECASE)
        if first_h2_match:
            section_blocks.append(content[:first_h2_match.start()])
            section_blocks.extend(block for block in re.split(r'(?=<h2\b)', content[first_h2_match.start():], flags=re.IGNORECASE) if block and block.strip())
        else:
            section_blocks.append(content)

        for section_index, section_content in enumerate(section_blocks, start=1):
            section_p_count = len(re.findall(r'<p\b[^>]*>[\s\S]*?</p\s*>', section_content, re.IGNORECASE))
            if section_p_count < 2 or section_p_count > 4:
                return {'passed': False, 'code': 'SECTION_P_COUNT', 'reason': f"섹션 {section_index} 문단 수 위반", 'feedback': f"섹션 {section_index}의 <p> 개수는 2~4개여야 합니다."}
            section_plain_length = len(strip_html(section_content))
            if section_plain_length < 200 or section_plain_length > 500:
                return {'passed': False, 'code': 'SECTION_LENGTH', 'reason': f"섹션 {section_index} 글자 수 위반", 'feedback': f"섹션 {section_index}의 글자 수는 200~500자여야 합니다."}

        normalized_user_keywords: List[str] = []
        for keyword in user_keywords or []:
            keyword_plain = strip_html(str(keyword or ''))
            if keyword_plain and keyword_plain not in normalized_user_keywords:
                normalized_user_keywords.append(keyword_plain)

        if len(section_blocks) >= 2:
            intro_plain = strip_html(section_blocks[0])
            conclusion_plain = strip_html(section_blocks[-1])
            duplicate_phrases: List[str] = []
            seen_duplicate_phrases: set[str] = set()
            min_phrase_len = 12
            if intro_plain and conclusion_plain and len(intro_plain) >= min_phrase_len and len(conclusion_plain) >= min_phrase_len:
                idx = 0
                while idx <= len(intro_plain) - min_phrase_len:
                    phrase = intro_plain[idx:idx + min_phrase_len]
                    if any(kw and kw in phrase for kw in normalized_user_keywords):
                        idx += 1
                        continue
                    if phrase in conclusion_plain and phrase not in seen_duplicate_phrases:
                        seen_duplicate_phrases.add(phrase)
                        duplicate_phrases.append(phrase)
                        idx += min_phrase_len
                    else:
                        idx += 1
            if len(duplicate_phrases) >= 3:
                return {'passed': False, 'code': 'INTRO_CONCLUSION_ECHO', 'reason': f"서론-결론 문구 중복 감지 ({len(duplicate_phrases)}개)", 'feedback': "서론과 결론에서 동일 표현이 과도하게 반복되었습니다. 재작성하십시오."}

        p_open_tags = re.findall(r'<p\b[^>]*>', content, re.IGNORECASE)
        p_close_tags = re.findall(r'</p\s*>', content, re.IGNORECASE)
        p_count = len(p_open_tags)
        if p_count != len(p_close_tags):
            return {'passed': False, 'code': 'P_MALFORMED', 'reason': f"p 태그 짝 불일치", 'feedback': '모든 문단은 <p>...</p> 형태로 정확히 닫아 주십시오.'}

        expected_min_p = total_sections * 2
        expected_max_p = total_sections * 4
        if p_count < expected_min_p:
             return {'passed': False, 'code': 'P_SHORT', 'reason': f"문단 수 부족", 'feedback': f"최소 {expected_min_p}개 문단이 필요합니다."}
        if p_count > expected_max_p:
            return {'passed': False, 'code': 'P_LONG', 'reason': f"문단 수 과다", 'feedback': f"최대 {expected_max_p}개 문단 이하로 줄이십시오."}

        location_orphan_paragraphs: List[str] = []
        paragraph_blocks = re.findall(r'<p\b[^>]*>([\s\S]*?)</p\s*>', content, re.IGNORECASE)
        location_pattern = re.compile(r'(서면\s*영광도서|부산\s*영광도서)', re.IGNORECASE)
        for block in paragraph_blocks:
            paragraph_text = re.sub(r'<[^>]*>', ' ', block)
            paragraph_text = re.sub(r'\s+', ' ', paragraph_text).strip()
            if not paragraph_text or not location_pattern.search(paragraph_text):
                continue
            sentence_tokens = [token.strip() for token in re.split(r'(?<=[.!?。])\s+', paragraph_text) if token and token.strip()]
            sentence_count = len(sentence_tokens) if sentence_tokens else (1 if paragraph_text else 0)
            if sentence_count <= 1:
                location_orphan_paragraphs.append(paragraph_text)
        if len(location_orphan_paragraphs) >= 2:
            return {'passed': False, 'code': 'LOCATION_ORPHAN_REPEAT', 'reason': "장소 단문 반복", 'feedback': "영광도서 단독 안내 문단은 최대 1회만 허용됩니다."}

        plain_text = re.sub(r'<[^>]*>', ' ', content)
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()

        meta_leaks = self._find_meta_prompt_leak_sentences(content)
        if meta_leaks:
            return {'passed': False, 'code': 'META_PROMPT_LEAK', 'reason': "메타 문구 누수", 'feedback': "프롬프트 설명 문장이 본문으로 출력되었습니다. 삭제하십시오."}

        overused_anchor_phrases = self._find_overused_anchor_phrases(content)
        if overused_anchor_phrases:
            return {'passed': False, 'code': 'PHRASE_REPEAT_CAP', 'reason': "상투 구문 반복 과다", 'feedback': "대표 문구 반복이 과다합니다. 다른 표현으로 교체하십시오."}

        material_reuse_issues = self._detect_material_reuse_issues(content, context_analysis, max_mentions=1)
        if material_reuse_issues:
            return {'passed': False, 'code': 'MATERIAL_REUSE', 'reason': "동일 소재 재사용 감지", 'feedback': "같은 인용/일화/근거가 여러 섹션에서 반복되었습니다."}

        event_signal_patterns = [r'\d{1,2}\s*월\s*\d{1,2}\s*일', r'출판기념회', r'행사', r'오후\s*\d{1,2}\s*시', r'서면\s*영광도서', r'부산\s*영광도서']
        event_signal_hits = sum(1 for pattern in event_signal_patterns if re.search(pattern, plain_text, re.IGNORECASE))
        if is_event_announcement or event_signal_hits >= 2:
            event_fact_mentions = self._count_event_fact_sentence_mentions(content, event_date_hint=event_date_hint, event_location_hint=event_location_hint)
            if event_fact_mentions > 2:
                return {'passed': False, 'code': 'EVENT_FACT_REPEAT', 'reason': "행사 안내 문장 반복", 'feedback': "일시+장소 결합 문장은 과다 반복을 피하십시오."}
            invite_patterns = {'직접 만나': r'직접\s*만나', '진솔한 소통': r'진솔한\s*소통', '기다리겠습니다': r'기다리겠습니다'}
            for label, pattern in invite_patterns.items():
                if len(re.findall(pattern, plain_text, re.IGNORECASE)) > 2:
                    return {'passed': False, 'code': 'EVENT_INVITE_REDUNDANT', 'reason': f"초대 문구({label}) 반복 과다", 'feedback': "안내 문구는 간결히, 반복 구간은 다른 내용으로 대체하십시오."}

        return {'passed': True}
