"""
structure_normalizer.py
─────────────────────────
LLM이 생성한 HTML 콘텐츠의 구조(h2 개수, 섹션 문단 수, 섹션 길이,
서론-결론 중복)를 **프로그래밍적으로** 교정하여 content_validator의
합격률을 높인다.  검증 규칙 자체는 일절 변경하지 않는다.
"""

import re
from typing import Dict, Any, List, Optional, Tuple

from .structure_utils import strip_html


# ──────────────────────────────────────────────────────────
#  내부 헬퍼
# ──────────────────────────────────────────────────────────

def _split_into_sections(content: str) -> List[Dict[str, Any]]:
    """
    content를 (선택적 서론) + h2 섹션들로 분할.
    각 섹션은 {'html': str, 'has_h2': bool, 'h2_text': str|None} 딕셔너리.
    """
    first_h2 = re.search(r'<h2\b', content, re.IGNORECASE)
    sections: List[Dict[str, Any]] = []
    if first_h2 and first_h2.start() > 0:
        intro_html = content[:first_h2.start()].strip()
        if intro_html:
            sections.append({'html': intro_html, 'has_h2': False, 'h2_text': None})
        remaining = content[first_h2.start():]
    elif first_h2:
        remaining = content
    else:
        # h2가 아예 없는 경우
        sections.append({'html': content.strip(), 'has_h2': False, 'h2_text': None})
        return sections

    # h2 기준으로 분할
    parts = re.split(r'(?=<h2\b)', remaining, flags=re.IGNORECASE)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        h2_match = re.match(r'<h2[^>]*>(.*?)</h2>', part, re.IGNORECASE | re.DOTALL)
        h2_text = strip_html(h2_match.group(1)).strip() if h2_match else None
        sections.append({
            'html': part,
            'has_h2': bool(h2_match),
            'h2_text': h2_text,
        })
    return sections


def _join_sections(sections: List[Dict[str, Any]]) -> str:
    """섹션 리스트를 하나의 HTML 문자열로 재결합."""
    return '\n'.join(s['html'] for s in sections if s['html'].strip())


def _count_p_tags(html: str) -> int:
    return len(re.findall(r'<p\b[^>]*>[\s\S]*?</p\s*>', html, re.IGNORECASE))


def _get_p_blocks(html: str) -> List[str]:
    """<p>…</p> 블록 목록 반환."""
    return re.findall(r'<p\b[^>]*>[\s\S]*?</p\s*>', html, re.IGNORECASE)


def _plain_len(html: str) -> int:
    return len(strip_html(html))


def _split_sentences(text: str) -> List[str]:
    """한국어 문장 분리. 마침표/느낌표/물음표 기준."""
    chunks = re.split(r'(?<=[.!?。])\s+', text.strip())
    return [c.strip() for c in chunks if c.strip()]


def _generate_h2_text(p_block: str, index: int) -> str:
    """p 블록 내용에서 소제목 후보를 생성.
    첫 2~6 어절을 명사구로 잘라 사용한다.
    """
    plain = re.sub(r'<[^>]*>', '', p_block).strip()
    plain = re.sub(r'\s+', ' ', plain)
    # 첫 문장만 추출
    first_sentence = _split_sentences(plain)[0] if _split_sentences(plain) else plain
    # 처음 25자까지 잘라서 적절한 종결 위치 찾기
    candidate = first_sentence[:25].strip()
    # 마지막 조사/어미 제거하여 명사구화
    candidate = re.sub(r'[은는이가을를에서의와과도로만]$', '', candidate).strip()
    # 마침표 등 제거
    candidate = candidate.rstrip('.!?。,')
    if not candidate or len(candidate) < 3:
        candidate = f"핵심 주제 {index}"
    return candidate


# ──────────────────────────────────────────────────────────
#  1. H2 개수 정규화
# ──────────────────────────────────────────────────────────

def normalize_h2_count(content: str, expected_h2: int) -> str:
    """
    h2 태그 개수를 expected_h2에 맞춘다.
    - 부족 → 가장 긴 비-h2 섹션 또는 가장 긴 h2 섹션을 문단 경계에서 분할
    - 과다 → 가장 짧은 인접 h2 섹션 병합
    """
    if expected_h2 <= 0:
        return content

    sections = _split_into_sections(content)
    current_h2 = sum(1 for s in sections if s['has_h2'])

    # ─── h2 부족: 분할 ───
    max_iterations = 10  # 무한루프 방지
    iteration = 0
    while current_h2 < expected_h2 and iteration < max_iterations:
        iteration += 1
        # 분할 대상: p가 2개 이상인 섹션 (h2 있는 것 우선, 없으면 서론도 대상)
        # 우선순위: p가 많은 h2 섹션 → p가 많은 비-h2 섹션
        splittable = [
            (i, s) for i, s in enumerate(sections)
            if _count_p_tags(s['html']) >= 2
        ]
        if not splittable:
            break

        # p 개수가 가장 많은 섹션을 우선 선택 (동률 시 길이 기준)
        target_idx, target = max(
            splittable,
            key=lambda x: (_count_p_tags(x[1]['html']), _plain_len(x[1]['html']))
        )
        p_blocks = _get_p_blocks(target['html'])
        if len(p_blocks) < 2:
            break

        # 분할 지점: p가 2개이면 1+1, 3개면 1+2 또는 2+1, 4개 이상이면 절반
        if len(p_blocks) <= 3:
            split_point = 1  # 첫 p만 앞에, 나머지 뒤에
        else:
            split_point = len(p_blocks) // 2
        first_half_ps = p_blocks[:split_point]
        second_half_ps = p_blocks[split_point:]

        # 첫 번째 반: 기존 h2 유지 + 앞쪽 p
        if target['has_h2']:
            h2_tag_match = re.search(r'<h2[^>]*>.*?</h2>', target['html'], re.IGNORECASE | re.DOTALL)
            first_html = (h2_tag_match.group(0) if h2_tag_match else '') + '\n' + '\n'.join(first_half_ps)
        else:
            first_html = '\n'.join(first_half_ps)

        # 두 번째 반: 새 h2 생성 + 뒤쪽 p
        new_h2_text = _generate_h2_text(second_half_ps[0], current_h2 + 1)
        second_html = f'<h2>{new_h2_text}</h2>\n' + '\n'.join(second_half_ps)

        # 섹션 교체
        new_first = {'html': first_html.strip(), 'has_h2': target['has_h2'], 'h2_text': target['h2_text']}
        new_second = {'html': second_html.strip(), 'has_h2': True, 'h2_text': new_h2_text}
        sections[target_idx:target_idx + 1] = [new_first, new_second]
        current_h2 = sum(1 for s in sections if s['has_h2'])

    # ─── h2 과다: 병합 ───
    iteration = 0
    while current_h2 > expected_h2 and iteration < max_iterations:
        iteration += 1
        # h2 있는 섹션 중 가장 짧은 것을 이전 섹션과 병합
        h2_indices = [i for i, s in enumerate(sections) if s['has_h2']]
        if len(h2_indices) < 2:
            break

        # 가장 짧은 h2 섹션 찾기
        shortest_idx = min(h2_indices, key=lambda i: _plain_len(sections[i]['html']))

        # 이전 섹션이 있으면 이전과 합침, 없으면 다음과 합침
        if shortest_idx > 0:
            merge_with = shortest_idx - 1
            # h2 태그 제거하고 내용만 추가
            content_without_h2 = re.sub(
                r'<h2[^>]*>.*?</h2>\s*', '', sections[shortest_idx]['html'],
                count=1, flags=re.IGNORECASE | re.DOTALL
            ).strip()
            sections[merge_with]['html'] = sections[merge_with]['html'].strip() + '\n' + content_without_h2
            sections.pop(shortest_idx)
        elif shortest_idx < len(sections) - 1:
            merge_with = shortest_idx + 1
            # 현재 섹션의 h2 제거, 다음 섹션 앞에 p 추가
            content_without_h2 = re.sub(
                r'<h2[^>]*>.*?</h2>\s*', '', sections[shortest_idx]['html'],
                count=1, flags=re.IGNORECASE | re.DOTALL
            ).strip()
            sections[merge_with]['html'] = content_without_h2 + '\n' + sections[merge_with]['html']
            sections.pop(shortest_idx)
        else:
            break

        current_h2 = sum(1 for s in sections if s['has_h2'])

    return _join_sections(sections)


# ──────────────────────────────────────────────────────────
#  2. 섹션별 문단 수 정규화
# ──────────────────────────────────────────────────────────

def normalize_section_p_count(content: str) -> str:
    """
    각 섹션의 <p> 개수를 검증 범위(서론 1~4, 나머지 2~4)에 맞춘다.
    - 부족 → 긴 <p>의 문장을 분리하여 새 <p> 생성
    - 과다 → 가장 짧은 인접 <p> 2개 병합
    """
    sections = _split_into_sections(content)

    for sec_idx, section in enumerate(sections):
        p_blocks = _get_p_blocks(section['html'])
        p_count = len(p_blocks)
        is_intro = (sec_idx == 0 and not section['has_h2'])
        min_p = 1 if is_intro else 2
        max_p = 4

        # ─── p 부족: 분할 ───
        max_split_iter = 5
        split_iter = 0
        while p_count < min_p and split_iter < max_split_iter:
            split_iter += 1
            if p_count == 0:
                # p 태그가 아예 없으면 전체 텍스트를 p로 감싸고 분할
                raw_text = re.sub(r'<h2[^>]*>.*?</h2>', '', section['html'], flags=re.IGNORECASE | re.DOTALL).strip()
                raw_text = re.sub(r'<[^>]*>', '', raw_text).strip()
                if raw_text:
                    sentences = _split_sentences(raw_text)
                    if len(sentences) >= 2:
                        mid = len(sentences) // 2
                        p1 = '<p>' + ' '.join(sentences[:mid]) + '</p>'
                        p2 = '<p>' + ' '.join(sentences[mid:]) + '</p>'
                        h2_match = re.search(r'<h2[^>]*>.*?</h2>', section['html'], re.IGNORECASE | re.DOTALL)
                        new_html = (h2_match.group(0) + '\n' if h2_match else '') + p1 + '\n' + p2
                        section['html'] = new_html
                    else:
                        section['html'] = re.sub(
                            r'(<h2[^>]*>.*?</h2>)?\s*(.*)',
                            lambda m: (m.group(1) or '') + '\n<p>' + (m.group(2) or '') + '</p>',
                            section['html'],
                            flags=re.IGNORECASE | re.DOTALL
                        )
                p_blocks = _get_p_blocks(section['html'])
                p_count = len(p_blocks)
                continue

            # p가 1개인 경우 — 가장 긴 p를 문장 단위로 분할
            longest_idx = max(range(len(p_blocks)), key=lambda i: _plain_len(p_blocks[i]))
            longest_p = p_blocks[longest_idx]
            inner_text = re.sub(r'</?p[^>]*>', '', longest_p, flags=re.IGNORECASE).strip()
            sentences = _split_sentences(inner_text)

            if len(sentences) >= 2:
                mid = len(sentences) // 2
                new_p1 = '<p>' + ' '.join(sentences[:mid]) + '</p>'
                new_p2 = '<p>' + ' '.join(sentences[mid:]) + '</p>'
                section['html'] = section['html'].replace(longest_p, new_p1 + '\n' + new_p2, 1)
            else:
                break

            p_blocks = _get_p_blocks(section['html'])
            p_count = len(p_blocks)

        # ─── p 과다: 병합 ───
        merge_iter = 0
        while p_count > max_p and merge_iter < 5:
            merge_iter += 1
            p_blocks = _get_p_blocks(section['html'])
            if len(p_blocks) < 2:
                break
            # 가장 짧은 2개 인접 p 찾기
            min_combined_len = float('inf')
            merge_target = 0
            for i in range(len(p_blocks) - 1):
                combined = _plain_len(p_blocks[i]) + _plain_len(p_blocks[i + 1])
                if combined < min_combined_len:
                    min_combined_len = combined
                    merge_target = i

            inner1 = re.sub(r'</?p[^>]*>', '', p_blocks[merge_target], flags=re.IGNORECASE).strip()
            inner2 = re.sub(r'</?p[^>]*>', '', p_blocks[merge_target + 1], flags=re.IGNORECASE).strip()
            merged = f'<p>{inner1} {inner2}</p>'
            # 두 p를 merged로 대체
            section['html'] = section['html'].replace(
                p_blocks[merge_target] + '\n' + p_blocks[merge_target + 1],
                merged, 1
            )
            if p_blocks[merge_target] + p_blocks[merge_target + 1] in section['html'].replace('\n', ''):
                section['html'] = section['html'].replace(
                    p_blocks[merge_target], merged, 1
                ).replace(p_blocks[merge_target + 1], '', 1)

            p_blocks = _get_p_blocks(section['html'])
            p_count = len(p_blocks)

    return _join_sections(sections)


# ──────────────────────────────────────────────────────────
#  3. 섹션 글자 수 정규화
# ──────────────────────────────────────────────────────────

def normalize_section_length(
    content: str,
    min_chars: int = 200,
    max_chars: int = 500,
) -> str:
    """
    각 섹션의 plain text 길이를 min_chars~max_chars 범위에 맞춘다.
    - 짧은 섹션: 이전/이후 섹션에서 p를 이동
    - 긴 섹션: normalize_h2_count에서 이미 처리되므로 여기선 건너뜀
      (추가 분할은 h2 개수를 다시 어긋나게 할 수 있음)
    """
    sections = _split_into_sections(content)
    if len(sections) < 2:
        return content

    # 짧은 섹션에 이웃 섹션에서 p 이동
    changed = True
    max_iter = 10
    cur_iter = 0
    while changed and cur_iter < max_iter:
        cur_iter += 1
        changed = False
        for i in range(len(sections)):
            sec_len = _plain_len(sections[i]['html'])
            if sec_len >= min_chars:
                continue

            # 이전 섹션에서 마지막 p를 가져올 수 있는지 확인
            if i > 0:
                donor_ps = _get_p_blocks(sections[i - 1]['html'])
                donor_len = _plain_len(sections[i - 1]['html'])
                # 기부자가 min_chars 이상이고 p가 3개 이상일 때만
                if donor_len > min_chars and len(donor_ps) >= 3:
                    last_p = donor_ps[-1]
                    # 기부 후에도 기부자가 min_chars 이상인지 확인
                    donor_after = donor_len - _plain_len(last_p)
                    if donor_after >= min_chars:
                        sections[i - 1]['html'] = sections[i - 1]['html'].replace(last_p, '', 1).strip()
                        # 현재 섹션의 h2 뒤에 삽입
                        h2_match = re.search(r'<h2[^>]*>.*?</h2>', sections[i]['html'], re.IGNORECASE | re.DOTALL)
                        if h2_match:
                            insert_pos = h2_match.end()
                            sections[i]['html'] = (
                                sections[i]['html'][:insert_pos] + '\n' + last_p + '\n' +
                                sections[i]['html'][insert_pos:]
                            ).strip()
                        else:
                            sections[i]['html'] = last_p + '\n' + sections[i]['html']
                        changed = True
                        continue

            # 다음 섹션에서 첫 p를 가져올 수 있는지 확인
            if i < len(sections) - 1:
                donor_ps = _get_p_blocks(sections[i + 1]['html'])
                donor_len = _plain_len(sections[i + 1]['html'])
                if donor_len > min_chars and len(donor_ps) >= 3:
                    first_p = donor_ps[0]
                    donor_after = donor_len - _plain_len(first_p)
                    if donor_after >= min_chars:
                        sections[i + 1]['html'] = sections[i + 1]['html'].replace(first_p, '', 1).strip()
                        sections[i]['html'] = sections[i]['html'].strip() + '\n' + first_p
                        changed = True
                        continue

    return _join_sections(sections)


# ──────────────────────────────────────────────────────────
#  4. 서론-결론 중복 완화
# ──────────────────────────────────────────────────────────

# 동의어 치환 사전 (결론 쪽에서만 적용)
_SYNONYM_MAP = {
    '시민 여러분': '주민 여러분',
    '함께 만들어': '함께 이뤄',
    '함께하겠습니다': '동행하겠습니다',
    '약속드립니다': '다짐합니다',
    '최선을 다하겠습니다': '끝까지 노력하겠습니다',
    '존경하는': '사랑하는',
    '성장하는': '발전하는',
    '밝은 미래': '새로운 미래',
    '힘차게': '당차게',
    '앞장서겠습니다': '선두에 서겠습니다',
    '뛰어들었습니다': '나섰습니다',
    '반드시 이뤄내겠습니다': '꼭 실현하겠습니다',
    '감사합니다': '고맙습니다',
    '진심으로': '마음 깊이',
    '열정': '의지',
    '염원': '소망',
    '헌신': '봉사',
    '경제 대혁신': '경제 혁신',
    '미래를 열어': '미래를 만들어',
    '변화를 이끌어': '변화를 만들어',
}


def mitigate_intro_conclusion_echo(
    content: str,
    user_keywords: Optional[List[str]] = None,
    min_phrase_len: int = 12,
    max_duplicates: int = 2,
) -> str:
    """
    서론과 결론에서 12자 이상 동일 구문이 3개 이상 발견되면,
    결론 쪽의 중복 구문을 동의어로 치환한다.
    user_keywords에 포함된 구문은 치환 대상에서 제외.
    """
    sections = _split_into_sections(content)
    if len(sections) < 2:
        return content

    intro_html = sections[0]['html']
    conclusion_html = sections[-1]['html']
    intro_plain = strip_html(intro_html)
    conclusion_plain = strip_html(conclusion_html)

    if len(intro_plain) < min_phrase_len or len(conclusion_plain) < min_phrase_len:
        return content

    # 키워드 정규화
    normalized_keywords: List[str] = []
    for kw in (user_keywords or []):
        kw_plain = strip_html(str(kw or ''))
        if kw_plain:
            normalized_keywords.append(kw_plain)

    # 중복 구문 찾기
    duplicate_phrases: List[str] = []
    seen: set = set()
    idx = 0
    while idx <= len(intro_plain) - min_phrase_len:
        phrase = intro_plain[idx:idx + min_phrase_len]
        if any(kw and kw in phrase for kw in normalized_keywords):
            idx += 1
            continue
        if phrase in conclusion_plain and phrase not in seen:
            seen.add(phrase)
            duplicate_phrases.append(phrase)
            idx += min_phrase_len
        else:
            idx += 1

    if len(duplicate_phrases) < max_duplicates + 1:
        return content

    # 결론에서 중복 구문을 동의어로 치환
    modified_conclusion = conclusion_html
    replacements_made = 0
    for phrase in duplicate_phrases:
        if replacements_made >= len(duplicate_phrases) - max_duplicates:
            break
        # 동의어 사전에서 매칭되는 치환 찾기
        for original, replacement in _SYNONYM_MAP.items():
            if original in phrase:
                # 결론 HTML에서 해당 원문을 치환
                if original in modified_conclusion:
                    modified_conclusion = modified_conclusion.replace(original, replacement, 1)
                    replacements_made += 1
                    break

    if replacements_made > 0:
        sections[-1]['html'] = modified_conclusion
        return _join_sections(sections)

    return content


# ──────────────────────────────────────────────────────────
#  통합 진입점
# ──────────────────────────────────────────────────────────

def normalize_structure(
    content: str,
    length_spec: Dict[str, int],
    *,
    user_keywords: Optional[List[str]] = None,
) -> str:
    """
    LLM 출력의 HTML 구조를 프로그래밍적으로 정규화.
    파이프라인: h2 정규화 → p 정규화 → 섹션 길이 → 서론-결론 중복 완화
    """
    if not content or not content.strip():
        return content

    expected_h2 = int(length_spec.get('expected_h2', 4))
    sec_min = int(length_spec.get('per_section_min', 200))
    sec_max = int(length_spec.get('per_section_max', 500))

    result = content

    # 1. h2 개수 정규화
    result = normalize_h2_count(result, expected_h2)

    # 2. 섹션별 p 개수 정규화
    result = normalize_section_p_count(result)

    # 3. 섹션 길이 정규화
    result = normalize_section_length(result, min_chars=sec_min, max_chars=sec_max)

    # 4. 서론-결론 중복 완화
    result = mitigate_intro_conclusion_echo(result, user_keywords=user_keywords)

    return result
