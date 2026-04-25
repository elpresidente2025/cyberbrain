import os
import re
from typing import Dict, Any, Optional, List, Tuple

try:
    from kiwipiepy import Kiwi
    _kiwi = Kiwi()
except Exception:
    _kiwi = None
from .structure_utils import strip_html, material_key, normalize_context_text
from .intro_echo_utils import find_intro_conclusion_duplicates
from ..common.h2_guide import H2_MIN_LENGTH, H2_MAX_LENGTH
from ..common.h2_quality import (
    detect_dependent_section_opening,
    h2_semantic_family_key,
    is_h2_prefix_fragment,
)
from ..common.editorial import STRUCTURE_SPEC, QUALITY_SPEC
from ..common.section_contract import (
    find_section_semantic_mismatch,
    get_section_contract_sequence,
    validate_cross_section_contracts,
    validate_section_contract,
)

_INTRO_ORPHAN_TRANSITION_PREFIXES = (
    "특히",
    "또한",
    "아울러",
    "이와 함께",
    "이러한",
    "이는",
    "앞으로도",
    "이제는",
)

_LOW_INFORMATION_H2_SURFACE_RE = re.compile(
    r"(?:"
    r"실행\s*계획을\s*세우겠습니다|"
    r"제도\s*기반을\s*세우겠습니다|"
    r"제도로\s*뒷받침하겠습니다|"
    r"재정\s*우려,?\s*어떻게\s*넘"
    r")"
)

# 기초의원 화자가 직접 사용하면 안 되는 집행형 동사 원형 (advisory)
# 구청장·단체장 집행부 고유 권한에 해당하는 행위
_EXECUTIVE_VERB_STEMS = frozenset({
    '신설하다', '설치하다', '구축하다', '도입하다', '운영하다',
    '체결하다', '배치하다', '임명하다', '편성하다', '집행하다',
    '착공하다', '개통하다', '설립하다',
})

# 직책 키워드 + 부정 조합 검출 (advisory — passed:True 유지)
_ROLE_NEGATIVE_VERB_PATTERN = re.compile(
    r"(?:구의원|시의원|도의원|국회의원|구청장|의원|예비후보)\s*"
    r"(?:추진|결정|처리|통과|발의|제안|요청|협의|합의|검토|추천|지정|선정)"
    r"\s*"
    r"(?:실패|무산|좌절|반대|부결|후퇴|못\s*하|안\s*되|않겠|없이|불가|거부|철회|취소|포기|중단)",
    re.IGNORECASE,
)
_ROLE_AS_POLICY_OBJECT_PATTERN = re.compile(
    r"(?:구의원|시의원|도의원|국회의원|구청장|의원|예비후보)\s*"
    r"(?:추진|복원|회복|후퇴|변화|성과|실행|처리|해결|흐지부지)",
    re.IGNORECASE,
)
_ROLE_ODD_JOSA_PATTERN = re.compile(
    r"(?:구의원|시의원|도의원|국회의원|구청장|의원|예비후보)"
    r"(?:이|가|을|를|의)?\s*같은\s*(?:후퇴|변화|성과|문제)",
    re.IGNORECASE,
)

# 지역 비하성 은유 검출 (advisory — passed:True 유지)
_REGIONAL_DEROGATORY_METAPHOR_PATTERN = re.compile(
    r"(?:"
    r"지방\s*(?:소멸|쇠퇴|죽어가|사라져|낙후|후진)"
    r"|(?:구도심|원도심|달동네|쪽방촌|낡은\s*동네|낙후된\s*지역)\s*(?:처럼|같은|수준)"
    r"|멈춘\s*심장\s*(?:처럼|같이|같은)"
    r"|(?:[가-힣]{2,12}(?:동|구|군|시|읍|면|리).{0,12})?(?:활력을\s*잃|생기를\s*잃|죽어가|멈춰\s*있)"
    r")",
    re.IGNORECASE,
)

class ContentValidator:
    def _validate_bundle_section_contracts(
        self,
        content: str,
        *,
        poll_focus_bundle: Optional[Dict[str, Any]],
        body_sections: int,
    ) -> Optional[Dict[str, Any]]:
        body_contracts, conclusion_contract = get_section_contract_sequence(
            poll_focus_bundle,
            body_sections=body_sections,
        )
        if not body_contracts and not conclusion_contract:
            return None

        first_h2_match = re.search(r'<h2\b', content, re.IGNORECASE)
        if not first_h2_match:
            return None

        h2_blocks = [
            block
            for block in re.split(r'(?=<h2\b)', content[first_h2_match.start():], flags=re.IGNORECASE)
            if block and block.strip()
        ]
        if not h2_blocks:
            return None

        primary_pair = (
            poll_focus_bundle.get('primaryPair')
            if isinstance(poll_focus_bundle, dict) and isinstance(poll_focus_bundle.get('primaryPair'), dict)
            else {}
        )
        speaker = normalize_context_text(
            primary_pair.get('speaker') if isinstance(primary_pair, dict) else ''
        ) or normalize_context_text((poll_focus_bundle or {}).get('speaker') if isinstance(poll_focus_bundle, dict) else '')
        opponent = normalize_context_text(
            primary_pair.get('opponent') if isinstance(primary_pair, dict) else ''
        )

        def _parse_block(block: str) -> tuple[str, List[str]]:
            heading_match = re.search(r'<h2[^>]*>(.*?)</h2>', block, re.IGNORECASE | re.DOTALL)
            heading_text = strip_html(heading_match.group(1)).strip() if heading_match else ''
            paragraphs = [
                strip_html(item).strip()
                for item in re.findall(r'<p\b[^>]*>([\s\S]*?)</p\s*>', block, re.IGNORECASE)
                if strip_html(item).strip()
            ]
            return heading_text, paragraphs

        body_blocks = h2_blocks[:-1] if conclusion_contract and len(h2_blocks) >= 2 else h2_blocks
        parsed_sections: List[Dict[str, Any]] = []
        for index, contract in enumerate(body_contracts):
            if index >= len(body_blocks):
                break
            heading_text, paragraphs = _parse_block(body_blocks[index])
            parsed_sections.append({"heading": heading_text, "paragraphs": paragraphs})
            violation = validate_section_contract(
                heading=heading_text,
                paragraphs=paragraphs,
                contract=contract,
                speaker=speaker,
                opponent=opponent,
            )
            if violation:
                violation_code = normalize_context_text(violation.get('code'))
                feedback = (
                    f"본론 {index + 1}은 '{heading_text}'에 직접 답하는 첫 문장으로 시작하고, "
                    "경험 문장 다음에는 사실·행동·구체 결과·해법 연결만 오도록 다시 작성하십시오."
                )
                if violation_code == 'section_disallowed_role':
                    feedback = (
                        f"본론 {index + 1}에는 타인 반응 해석형이나 경험 → 역량 인증형 문장을 넣지 마십시오. "
                        "수치·사실·행동·구체 결과·해법 연결만 남기십시오."
                    )
                return {
                    'passed': False,
                    'code': 'SECTION_ROLE_CONTRACT',
                    'reason': (
                        f"본론 {index + 1} 허용 문장 계약 위반 "
                        f"({normalize_context_text(violation.get('message')) or '구조 위반'})"
                    ),
                    'feedback': feedback,
                    'sectionIndex': index + 1,
                    'sectionHeading': heading_text,
                    'violation': violation,
                }

        if conclusion_contract and h2_blocks:
            heading_text, paragraphs = _parse_block(h2_blocks[-1])
            parsed_sections.append({"heading": heading_text, "paragraphs": paragraphs})
            violation = validate_section_contract(
                heading=heading_text,
                paragraphs=paragraphs,
                contract=conclusion_contract,
                speaker=speaker,
                opponent=opponent,
            )
            if violation:
                violation_code = normalize_context_text(violation.get('code'))
                feedback = (
                    "결론은 선언형 소제목과 직접 연결되는 요약/다짐 문장으로 시작하고, "
                    "뒤 문장은 실행 계획이나 생활 변화 약속으로만 정리하십시오."
                )
                if violation_code == 'section_disallowed_role':
                    feedback = (
                        "결론에는 타인 반응 해석형과 경험 → 역량 인증형을 넣지 마십시오. "
                        "요약, 실행 다짐, 생활 변화 약속만 남기십시오."
                    )
                return {
                    'passed': False,
                    'code': 'SECTION_ROLE_CONTRACT',
                    'reason': (
                        f"결론 허용 문장 계약 위반 "
                        f"({normalize_context_text(violation.get('message')) or '구조 위반'})"
                    ),
                    'feedback': feedback,
                    'sectionIndex': len(body_blocks) + 1,
                    'sectionHeading': heading_text,
                    'violation': violation,
                }

        duplicate_cross_section_violation = validate_cross_section_contracts(
            sections=parsed_sections,
            speaker=speaker,
            opponent=opponent,
        )
        if duplicate_cross_section_violation:
            section_index = int(duplicate_cross_section_violation.get("sectionIndex") or 0) or None
            heading_text = normalize_context_text(duplicate_cross_section_violation.get("sectionHeading"))
            violation_code = normalize_context_text(duplicate_cross_section_violation.get("code"))
            feedback = (
                "같은 경력 나열은 원고 전체에서 한 번만 쓰십시오. "
                "다른 섹션에서는 그 경험이나 현장에서 익힌 판단·행동만 이어 쓰십시오."
            )
            if violation_code == "duplicate_policy_evidence_fact":
                feedback = (
                    "같은 정책 사례·검증 근거는 한 번만 쓰십시오. "
                    "다음 섹션에서는 실행 계획이나 기대 효과만 이어 쓰십시오."
                )
            return {
                'passed': False,
                'code': 'SECTION_ROLE_CONTRACT',
                'reason': (
                    f"섹션 {section_index or '?'} 섹션 간 중복 금지 위반 "
                    f"({normalize_context_text(duplicate_cross_section_violation.get('message')) or '구조 위반'})"
                ),
                'feedback': feedback,
                'sectionIndex': section_index,
                'sectionHeading': heading_text,
                'violation': duplicate_cross_section_violation,
            }

        return None

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

    def _first_plain_sentence(self, text: str) -> str:
        sentences = self._split_plain_sentences(text)
        return sentences[0] if sentences else normalize_context_text(text)

    def _validate_h2_quality_set(
        self,
        h2_texts: List[str],
        *,
        user_keywords: Optional[List[str]],
        context_analysis: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        seen: set[str] = set()
        seen_family: Dict[str, str] = {}

        for h2_text in h2_texts:
            normalized = normalize_context_text(h2_text)
            compact = material_key(normalized)
            if compact and compact in seen:
                return {
                    'passed': False,
                    'code': 'H2_DUPLICATE',
                    'reason': f'소제목 중복 ({normalized})',
                    'feedback': f'중복된 소제목 "{normalized}"을 섹션의 고유 실행수단이 드러나도록 다시 쓰십시오.',
                    'sectionHeading': normalized,
                }
            if compact:
                seen.add(compact)

            if is_h2_prefix_fragment(normalized):
                return {
                    'passed': False,
                    'code': 'H2_TEXT_FRAGMENT',
                    'reason': f'앞말이 잘린 소제목 ({normalized})',
                    'feedback': f'소제목 "{normalized}"은 앞 토큰이 잘린 형태입니다. 원문 정책명이나 검색어가 온전하게 보이도록 다시 쓰십시오.',
                    'sectionHeading': normalized,
                }

            if _LOW_INFORMATION_H2_SURFACE_RE.search(normalized):
                return {
                    'passed': False,
                    'code': 'H2_LOW_INFORMATION_TEMPLATE',
                    'reason': f'본문 고유 실행수단이 빠진 추상 소제목 ({normalized})',
                    'feedback': (
                        f'소제목 "{normalized}"은 실행 계획/제도 기반 같은 추상 틀만 반복합니다. '
                        '해당 섹션 본문에 있는 사업명·시설·절차·수치·대상 중 하나를 소제목에 직접 넣으십시오.'
                    ),
                    'sectionHeading': normalized,
                }

            family = h2_semantic_family_key(normalized)
            if family:
                previous = seen_family.get(family)
                if previous:
                    return {
                        'passed': False,
                        'code': 'H2_GENERIC_FAMILY_REPEAT',
                        'reason': f'저정보 소제목 템플릿 반복 ({previous} / {normalized})',
                        'feedback': (
                            f'"{previous}"와 "{normalized}"이 같은 저정보 소제목 틀을 반복합니다. '
                            '각 소제목은 원문에 있는 해당 섹션의 고유 실행수단을 직접 드러내야 합니다.'
                        ),
                        'sectionHeading': normalized,
                        'previousHeading': previous,
                    }
                seen_family[family] = normalized

        keyword_candidates: List[str] = []
        if isinstance(context_analysis, dict):
            contract = context_analysis.get("source_contract")
            if isinstance(contract, dict):
                primary_keyword = normalize_context_text(contract.get("primary_keyword"))
                if primary_keyword:
                    keyword_candidates.append(primary_keyword)
        for raw_keyword in user_keywords or []:
            keyword = normalize_context_text(raw_keyword)
            if keyword and keyword not in keyword_candidates:
                keyword_candidates.append(keyword)

        concrete_keywords = [
            keyword
            for keyword in keyword_candidates
            if len(material_key(keyword)) >= 3 and keyword not in {"정책", "방안", "지역", "시민"}
        ]
        if concrete_keywords and h2_texts:
            if not any(any(keyword in h2 for keyword in concrete_keywords[:3]) for h2 in h2_texts):
                joined = ", ".join(concrete_keywords[:3])
                return {
                    'passed': False,
                    'code': 'H2_USER_KEYWORD_MISSING',
                    'reason': f'검색어/핵심 정책명이 소제목에 없음 ({joined})',
                    'feedback': f'소제목 중 최소 1개는 검색어 또는 핵심 정책명({joined})을 앞부분에 포함해야 합니다.',
                    'keywords': concrete_keywords[:3],
                }

        return None

    def _paragraph_minimums(
        self,
        *,
        is_intro_section: bool,
        is_last_section: bool,
        paragraph_index: int,
        paragraph_count: int,
    ) -> Tuple[int, int]:
        if is_intro_section and paragraph_index == 1:
            return (2, 60)
        if is_last_section and paragraph_index == paragraph_count:
            return (2, 60)
        return (3, 80)

    def _validate_paragraph_substance(
        self,
        paragraph_text: str,
        *,
        section_index: int,
        paragraph_index: int,
        paragraph_count: int,
        is_intro_section: bool,
        is_last_section: bool,
        section_heading: str,
    ) -> Optional[Dict[str, Any]]:
        plain = normalize_context_text(paragraph_text)
        if not plain:
            return None
        min_sentences, min_chars = self._paragraph_minimums(
            is_intro_section=is_intro_section,
            is_last_section=is_last_section,
            paragraph_index=paragraph_index,
            paragraph_count=paragraph_count,
        )
        sentences = self._split_plain_sentences(plain)
        sentence_count = len(sentences) or 1
        if sentence_count < min_sentences or len(plain) < min_chars:
            return {
                'passed': False,
                'code': 'P_THIN',
                'reason': (
                    f"섹션 {section_index} 문단 {paragraph_index}이 실질 문단 기준 미달 "
                    f"({sentence_count}문장/{len(plain)}자, 최소 {min_sentences}문장/{min_chars}자)"
                ),
                'feedback': (
                    f"섹션 {section_index} 문단 {paragraph_index}은 최소 {min_sentences}문장, "
                    f"{min_chars}자 이상의 실질 문단이어야 합니다. 한 문장을 별도 <p>로 분리하지 말고 "
                    "주장, 근거, 의미/실행 문장을 한 문단 안에서 완성하십시오."
                ),
                'sectionIndex': section_index,
                'paragraphIndex': paragraph_index,
                'sentenceCount': sentence_count,
                'paragraphLength': len(plain),
                'paragraphMinSentences': min_sentences,
                'paragraphMinChars': min_chars,
                'sectionHeading': section_heading,
                'isIntroSection': is_intro_section,
            }
        return None

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
            # 시스템 내부 변수명 (literal 매칭 — false positive 없음, \b 미사용: 한국어 \w 충돌 방지)
            re.compile(r'source_sequence|execution_items|forbidden_inferred|required_source_facts', re.IGNORECASE),
            re.compile(r'central_claim|primary_keyword', re.IGNORECASE),
            # 메타 지시 한국어 표현
            re.compile(r'원문에서\s*약속한\s*범위', re.IGNORECASE),
            re.compile(r'금지된\s*추론', re.IGNORECASE),
            re.compile(r'사용자\s*입력에\s*없으므로', re.IGNORECASE),
            re.compile(r'위\s*실행\s*항목', re.IGNORECASE),
            re.compile(r'메타\s*지시|프롬프트\s*(?:설명|지시|내용)', re.IGNORECASE),
            re.compile(r'새\s*공약처럼', re.IGNORECASE),
            re.compile(r'필수\s*반영|누락하지\s*말고\s*본론에', re.IGNORECASE),
        ]
        if os.environ.get("ENABLE_SEQUENTIAL_STRUCTURE", "true").lower() == "true":
            patterns.extend([
                re.compile(r'(본론|서론|결론)에서 (확인한|다룬|언급한|살펴본|제기한)', re.IGNORECASE),
                re.compile(r'앞서 (확인한|다룬|언급한|살펴본|제기한)', re.IGNORECASE),
                re.compile(r'위(?:에서)? (확인한|다룬|언급한|살펴본|제기한)', re.IGNORECASE),
            ])
        leaks: List[str] = []
        for sentence in self._split_plain_sentences(plain_text):
            if any(pattern.search(sentence) for pattern in patterns):
                leaks.append(sentence)
        return leaks

    def _find_role_negative_combinations(self, content: str) -> List[str]:
        plain_text = re.sub(r'<[^>]*>', ' ', content or '')
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        if not plain_text:
            return []
        hits: List[str] = []
        for sentence in self._split_plain_sentences(plain_text):
            if (
                _ROLE_NEGATIVE_VERB_PATTERN.search(sentence)
                or _ROLE_AS_POLICY_OBJECT_PATTERN.search(sentence)
                or _ROLE_ODD_JOSA_PATTERN.search(sentence)
            ):
                hits.append(sentence[:100])
        return hits

    def _find_regional_derogatory_metaphors(self, content: str) -> List[str]:
        plain_text = re.sub(r'<[^>]*>', ' ', content or '')
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        if not plain_text:
            return []
        hits: List[str] = []
        for sentence in self._split_plain_sentences(plain_text):
            if _REGIONAL_DEROGATORY_METAPHOR_PATTERN.search(sentence):
                hits.append(sentence[:100])
        return hits

    def _find_executive_verb_claims(self, content: str, position: str = '') -> List[str]:
        """기초의원 프로필에서 집행부 고유 집행형 동사를 kiwi로 검출 (advisory)."""
        if _kiwi is None or position != '기초의원':
            return []
        plain_text = re.sub(r'<[^>]*>', ' ', content or '')
        plain_text = re.sub(r'\s+', ' ', plain_text).strip()
        if not plain_text:
            return []
        hits: List[str] = []
        for sentence in self._split_plain_sentences(plain_text):
            try:
                tokens = _kiwi.analyze(sentence, top_n=1)[0][0]
                for token in tokens:
                    if token.tag.startswith('V') and token.lemma in _EXECUTIVE_VERB_STEMS:
                        hits.append(sentence[:100])
                        break
            except Exception:
                continue
        return hits

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
            '부산항 부두 노동자의 막내로': int(QUALITY_SPEC['phrase3wordMax']),
            '시민 여러분과 함께': int(QUALITY_SPEC['phrase3wordMax']),
        }
        overused: List[str] = []
        for phrase, limit in phrase_limits.items():
            count = len(re.findall(re.escape(phrase), plain_text))
            if count > limit:
                overused.append(f'"{phrase}" {count}회')
        return overused

    def _intro_has_stance_anchor(
        self,
        intro_plain: str,
        context_analysis: Optional[Dict[str, Any]],
        *,
        min_overlap_tokens: int = 2,
    ) -> bool:
        if not intro_plain or not isinstance(context_analysis, dict):
            return True

        stance_topics: List[str] = []
        for item in context_analysis.get('mustIncludeFromStance') or []:
            if isinstance(item, dict):
                topic = normalize_context_text(item.get('topic'))
            else:
                topic = normalize_context_text(item)
            if topic:
                stance_topics.append(topic)

        if not stance_topics:
            return True

        intro_text = normalize_context_text(intro_plain, sep=' ')
        intro_compact = re.sub(r'\s+', '', intro_text)
        if not intro_compact:
            return False

        for topic in stance_topics[:3]:
            normalized_topic = normalize_context_text(topic, sep=' ')
            compact_topic = re.sub(r'\s+', '', normalized_topic)
            if len(compact_topic) >= 6:
                probe = compact_topic[: min(18, len(compact_topic))]
                if probe and probe in intro_compact:
                    return True

            tokens = [tok for tok in re.split(r'\s+', normalized_topic) if len(tok) >= 2]
            if not tokens:
                continue
            overlap = sum(1 for tok in tokens if tok in intro_text)
            if overlap >= min(min_overlap_tokens, len(tokens)):
                return True

        return False

    def _extract_intro_paragraphs(self, intro_block: str) -> List[str]:
        return [
            strip_html(item).strip()
            for item in re.findall(r'<p\b[^>]*>([\s\S]*?)</p\s*>', intro_block or '', re.IGNORECASE)
            if strip_html(item).strip()
        ]

    def _intro_transition_prefix(self, paragraph: str) -> str:
        cleaned = normalize_context_text(paragraph)
        for prefix in _INTRO_ORPHAN_TRANSITION_PREFIXES:
            if cleaned.startswith(prefix):
                return prefix
        return ""

    def _is_short_intro_fragment(self, paragraph: str) -> bool:
        cleaned = normalize_context_text(paragraph)
        if not cleaned:
            return False
        sentence_count = len(self._split_plain_sentences(cleaned)) or 1
        return sentence_count <= 1 and len(cleaned) <= 95

    def _validate_intro_flow(self, intro_block: str) -> Optional[Dict[str, Any]]:
        intro_paragraphs = self._extract_intro_paragraphs(intro_block)
        if len(intro_paragraphs) >= 3:
            short_fragment_count = sum(
                1 for paragraph in intro_paragraphs if self._is_short_intro_fragment(paragraph)
            )
            if short_fragment_count >= 2:
                return {
                    'passed': False,
                    'code': 'INTRO_FRAGMENTED',
                    'reason': '서론이 짧은 단문으로 과도하게 분절됨',
                    'feedback': '서론은 3문단으로 구성하되, 각 문단이 2문장 이상·110자 이상이어야 합니다. 짧은 단문을 별도 문단으로 분리하지 말고 앞뒤 문단에 통합하십시오.',
                    'introParagraphCount': len(intro_paragraphs),
                }

        for index, paragraph in enumerate(intro_paragraphs[1:], start=1):
            prefix = self._intro_transition_prefix(paragraph)
            if not prefix:
                continue
            previous = normalize_context_text(intro_paragraphs[index - 1])
            previous_sentence_count = len(self._split_plain_sentences(previous)) or (1 if previous else 0)
            if previous_sentence_count <= 1 and len(previous) <= 90:
                return {
                    'passed': False,
                    'code': 'INTRO_ORPHAN_TRANSITION',
                    'reason': f'서론 연결어 "{prefix}"의 선행 문맥이 약함',
                    'feedback': f'서론에서 "{prefix}"로 시작하는 문단은 앞 문단과 합치거나, 연결 대상이 드러나도록 명시적 주어로 다시 써 주십시오.',
                    'transitionPrefix': prefix,
                }

        return None

    def _validate_section_semantic_lanes(
        self,
        content: str,
        *,
        category: str = '',
    ) -> Optional[Dict[str, Any]]:
        normalized_category = normalize_context_text(category).lower()
        if not normalized_category:
            return None

        first_h2_match = re.search(r'<h2\b', content, re.IGNORECASE)
        if not first_h2_match:
            return None

        h2_blocks = [
            block
            for block in re.split(r'(?=<h2\b)', content[first_h2_match.start():], flags=re.IGNORECASE)
            if block and block.strip()
        ]
        if len(h2_blocks) < 2:
            return None

        parsed_sections: List[Dict[str, Any]] = []
        for block in h2_blocks:
            heading_match = re.search(r'<h2[^>]*>(.*?)</h2>', block, re.IGNORECASE | re.DOTALL)
            heading_text = strip_html(heading_match.group(1)).strip() if heading_match else ''
            paragraphs = [
                strip_html(item).strip()
                for item in re.findall(r'<p\b[^>]*>([\s\S]*?)</p\s*>', block, re.IGNORECASE)
                if strip_html(item).strip()
            ]
            if heading_text and paragraphs:
                parsed_sections.append({"heading": heading_text, "paragraphs": paragraphs})

        violation = find_section_semantic_mismatch(
            sections=parsed_sections,
            category=normalized_category,
        )
        if not violation:
            return None

        section_index = int(violation.get('sectionIndex') or 0) or None
        heading_text = normalize_context_text(violation.get('sectionHeading'))
        target_heading = normalize_context_text(violation.get('targetSectionHeading'))
        sentence = normalize_context_text(violation.get('sentence'))
        target_label = f"'{target_heading}' 섹션" if target_heading else "뒤쪽 비전/과제 섹션"
        return {
            'passed': False,
            'code': 'SECTION_TOPIC_DRIFT',
            'reason': f"섹션 {section_index or '?'} 주제 경계 이탈",
            'feedback': (
                f"'{heading_text}' 섹션에는 이미 수행한 성과와 그 효과만 남기고, "
                f"앞으로의 실행 과제를 설명하는 문장(\"{sentence}\")은 {target_label}으로 옮기십시오."
            ),
            'sectionIndex': section_index,
            'sectionHeading': heading_text,
            'violation': violation,
        }

    _SOURCE_CONTRACT_STOP_TOKENS = {
        "관련",
        "정책",
        "방안",
        "효과",
        "회복",
        "복원",
        "재정비",
        "구성",
        "분석",
        "개정",
        "축소",
        "약화",
        "미사용",
        "급감",
    }

    def _contract_item_tokens(self, item: str) -> List[str]:
        text = normalize_context_text(item)
        tokens = [
            token
            for token in re.findall(r"[0-9A-Za-z가-힣]+", text)
            if len(token) >= 2 and token not in self._SOURCE_CONTRACT_STOP_TOKENS
        ]
        if not tokens:
            tokens = [
                token
                for token in re.findall(r"[0-9A-Za-z가-힣]+", text)
                if len(token) >= 2
            ]
        return tokens

    def _plain_covers_contract_item(self, plain_text: str, item: str) -> bool:
        item_text = normalize_context_text(item)
        if not item_text:
            return True
        plain_compact = material_key(plain_text)
        item_compact = material_key(item_text)
        if item_compact and len(item_compact) >= 6 and item_compact in plain_compact:
            return True

        tokens = self._contract_item_tokens(item_text)
        if not tokens:
            return True
        hits = sum(1 for token in tokens if token in plain_text)
        if len(tokens) == 1:
            return hits == 1
        return hits >= min(2, len(tokens))

    _DETACHED_LEADERSHIP_MARKERS = (
        "AI",
        "인공지능",
        "로봇",
        "노동의 종말",
        "다니엘",
        "라벤토스",
        "공화주의",
        "낙수효과",
        "분수효과",
        "선별 복지",
        "선별복지",
        "조세 저항",
        "보편적 복지",
        "기본사회",
        "존엄성",
    )

    def _find_detached_leadership_paragraphs(
        self,
        content: str,
        contract: Dict[str, Any],
    ) -> List[str]:
        source_items: List[str] = []
        for key in ("required_source_facts", "execution_items", "source_sequence_items"):
            raw_values = contract.get(key)
            if not isinstance(raw_values, list):
                continue
            for raw in raw_values:
                item = normalize_context_text(raw)
                if item and item not in source_items:
                    source_items.append(item)
        primary_keyword = normalize_context_text(contract.get("primary_keyword"))
        if primary_keyword:
            source_items.append(primary_keyword)
        if not source_items:
            return []

        detached: List[str] = []
        paragraph_blocks = re.findall(r'<p\b[^>]*>([\s\S]*?)</p\s*>', content or '', re.IGNORECASE)
        for block in paragraph_blocks:
            paragraph = normalize_context_text(strip_html(block), sep=' ')
            if not paragraph:
                continue
            if not any(marker in paragraph for marker in self._DETACHED_LEADERSHIP_MARKERS):
                continue
            if any(self._plain_covers_contract_item(paragraph, item) for item in source_items):
                continue
            detached.append(paragraph)
        return detached

    def _validate_source_contract(
        self,
        content: str,
        context_analysis: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(context_analysis, dict):
            return None
        contract = context_analysis.get("source_contract")
        if not isinstance(contract, dict):
            return None
        if normalize_context_text(contract.get("answer_type")) != "implementation_plan":
            return None

        plain_text = normalize_context_text(strip_html(content), sep=' ')
        if not plain_text:
            return None

        forbidden_hits: List[str] = []
        plain_compact = material_key(plain_text)
        for raw_item in contract.get("forbidden_inferred_actions") or []:
            item = normalize_context_text(raw_item)
            if not item or item == "(없음)":
                continue
            item_compact = material_key(item)
            if item in plain_text or (item_compact and item_compact in plain_compact):
                forbidden_hits.append(item)
        if forbidden_hits:
            joined = ", ".join(forbidden_hits[:3])
            return {
                'passed': False,
                'code': 'UNSUPPORTED_INFERRED_ACTION',
                'reason': f"사용자 입력에 없는 실행안 생성 ({joined})",
                'feedback': (
                    f"사용자 입력에 없는 실행안({joined})을 삭제하고, "
                    "원문에 있는 실행 항목만으로 다시 작성하십시오."
                ),
                'unsupportedItems': forbidden_hits[:5],
            }

        detached_leadership = self._find_detached_leadership_paragraphs(content, contract)
        if detached_leadership:
            sample = detached_leadership[0][:80]
            return {
                'passed': False,
                'code': 'LEADERSHIP_DETACHED',
                'reason': f"상위 원칙이 원문 실행수단과 분리됨 ({sample})",
                'feedback': (
                    "leadership.py의 상위 원칙은 허용되지만, 같은 문단 안에서 사용자 원문에 있는 "
                    "정책명·실행수단·제도화 항목과 직접 연결해야 합니다. 원문과 분리된 일반론은 삭제하거나 "
                    "원문 실행수단에 붙여 다시 쓰십시오."
                ),
                'paragraphSamples': detached_leadership[:3],
            }

        required_items: List[str] = []
        for key in ("required_source_facts", "execution_items", "source_sequence_items"):
            raw_values = contract.get(key)
            if not isinstance(raw_values, list):
                continue
            for raw_item in raw_values:
                item = normalize_context_text(raw_item)
                if item and item not in required_items:
                    required_items.append(item)

        missing = [
            item
            for item in required_items
            if not self._plain_covers_contract_item(plain_text, item)
        ]
        if missing:
            joined = ", ".join(missing[:4])
            return {
                'passed': False,
                'code': 'SOURCE_CONTRACT_MISSING',
                'reason': f"사용자 입력 핵심 재료 누락 ({joined})",
                'feedback': (
                    f"사용자 입력 텍스트의 핵심 재료({joined})를 본문에 반영하십시오. "
                    "외부 사례나 일반론을 늘리지 말고 원문 재료를 중심으로 다시 작성하십시오."
                ),
                'missingItems': missing[:8],
            }

        return None

    def validate(
        self,
        content: str,
        length_spec: Dict[str, int],
        *,
        category: str = '',
        context_analysis: Optional[Dict[str, Any]] = None,
        is_event_announcement: bool = False,
        event_date_hint: str = '',
        event_location_hint: str = '',
        user_keywords: Optional[List[str]] = None,
        poll_focus_bundle: Optional[Dict[str, Any]] = None,
    ) -> Dict:
        if not content:
            return {'passed': False, 'code': 'EMPTY_CONTENT', 'reason': '내용 없음', 'feedback': '내용이 비어있습니다.'}
        
        plain_length = len(strip_html(content))
        min_length = length_spec['min_chars']
        max_length = length_spec['max_chars']
        expected_h2 = length_spec['expected_h2']
        per_section_recommended = length_spec.get('per_section_recommended', int(STRUCTURE_SPEC['sectionCharTarget']))
        per_section_max = length_spec.get('per_section_max', int(STRUCTURE_SPEC['sectionCharMax']))
        total_sections = length_spec.get('total_sections', int(STRUCTURE_SPEC['minSections']))

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
            if len(h2_text) > H2_MAX_LENGTH:
                return {'passed': False, 'code': 'H2_TEXT_LONG', 'reason': "h2 텍스트 길이 초과", 'feedback': f'h2 텍스트가 {H2_MAX_LENGTH}자를 초과했습니다: "{h2_text}"'}
            if len(h2_text) < H2_MIN_LENGTH:
                return {'passed': False, 'code': 'H2_TEXT_SHORT', 'reason': "h2 텍스트 너무 짧음", 'feedback': f'h2 텍스트가 {H2_MIN_LENGTH}자 미만으로 너무 짧습니다: "{h2_text}"'}
            if re.search(r'(위한|향한|만드는|통한|대한)(\s|$)', h2_text):
                return {'passed': False, 'code': 'H2_TEXT_MODIFIER', 'reason': "h2 금지된 수식어", 'feedback': f'금지 수식어(위한/향한/만드는/통한/대한)를 제거하십시오: "{h2_text}"'}
            if re.search(r'(?:^|[\s,])(저는|제가|나는|내가)(?:[\s,]|$)', h2_text):
                return {
                    'passed': False,
                    'code': 'H2_TEXT_FIRST_PERSON',
                    'reason': "h2 1인칭 표현 포함",
                    'feedback': f'소제목은 헤드라인형으로 작성하고 1인칭 표현(저는/제가/나는/내가)을 제거하십시오: "{h2_text}"',
                }

        h2_quality_issue = self._validate_h2_quality_set(
            h2_texts,
            user_keywords=user_keywords,
            context_analysis=context_analysis,
        )
        if h2_quality_issue:
            return h2_quality_issue

        section_blocks: List[str] = []
        section_intro_flags: List[bool] = []
        first_h2_match = re.search(r'<h2\b', content, re.IGNORECASE)
        if first_h2_match:
            intro_block = content[:first_h2_match.start()].strip()
            if intro_block:
                section_blocks.append(intro_block)
                section_intro_flags.append(True)
            h2_blocks = [
                block
                for block in re.split(r'(?=<h2\b)', content[first_h2_match.start():], flags=re.IGNORECASE)
                if block and block.strip()
            ]
            section_blocks.extend(h2_blocks)
            section_intro_flags.extend([False] * len(h2_blocks))
        else:
            section_blocks.append(content)
            section_intro_flags.append(True)
        section_plain_lengths = [len(strip_html(block)) for block in section_blocks]

        from ..common.aeo_config import paragraph_contract_from_length_spec
        paragraph_contract = paragraph_contract_from_length_spec(length_spec)
        min_p = int(paragraph_contract['section_paragraph_min'])
        max_p = int(paragraph_contract['section_paragraph_max'])

        for section_index, section_content in enumerate(section_blocks, start=1):
            section_paragraphs = [
                strip_html(item).strip()
                for item in re.findall(r'<p\b[^>]*>([\s\S]*?)</p\s*>', section_content, re.IGNORECASE)
                if strip_html(item).strip()
            ]
            section_p_count = len(section_paragraphs)
            is_intro_section = bool(section_intro_flags[section_index - 1]) if section_index - 1 < len(section_intro_flags) else False
            heading_match = re.search(r'<h2[^>]*>(.*?)</h2>', section_content, re.IGNORECASE | re.DOTALL)
            section_heading = strip_html(heading_match.group(1)).strip() if heading_match else ''
            section_block_index = section_index - 2 if not is_intro_section else -1
            if section_p_count < min_p or section_p_count > max_p:
                return {
                    'passed': False,
                    'code': 'SECTION_P_COUNT',
                    'reason': f"섹션 {section_index} 문단 수 위반 ({section_p_count}개, 허용 {min_p}~{max_p}개)",
                    'feedback': f"섹션 {section_index}의 <p> 개수는 {min_p}~{max_p}개여야 합니다. 현재 {section_p_count}개입니다.",
                    'sectionIndex': section_index,
                    'sectionParagraphCount': section_p_count,
                    'sectionParagraphMin': min_p,
                    'sectionParagraphMax': max_p,
                    'sectionHeading': section_heading,
                    'sectionBlockIndex': section_block_index,
                    'isIntroSection': is_intro_section,
                }
            if not is_intro_section and section_paragraphs:
                first_sentence = self._first_plain_sentence(section_paragraphs[0])
                opening_issue = detect_dependent_section_opening(first_sentence)
                if opening_issue.get('detected'):
                    return {
                        'passed': False,
                        'code': 'SECTION_OPENING_DEPENDENT_REFERENCE',
                        'reason': (
                            f"섹션 {section_index} 첫 문장이 독립 주어 없이 앞 문맥에 의존함 "
                            f"({opening_issue.get('surface')})"
                        ),
                        'feedback': (
                            f"섹션 {section_index} 첫 문장은 '{opening_issue.get('surface')}'처럼 앞 문맥을 받는 표현으로 시작하지 말고, "
                            "정책명·제도명·지역명·실행수단 같은 명시적 주어로 다시 시작하십시오."
                        ),
                        'sectionIndex': section_index,
                        'sectionHeading': section_heading,
                        'sectionBlockIndex': section_block_index,
                        'opening': dict(opening_issue),
                    }

            for paragraph_index, paragraph_text in enumerate(section_paragraphs, start=1):
                substance_issue = self._validate_paragraph_substance(
                    paragraph_text,
                    section_index=section_index,
                    paragraph_index=paragraph_index,
                    paragraph_count=section_p_count,
                    is_intro_section=is_intro_section,
                    is_last_section=(section_index == len(section_blocks)),
                    section_heading=section_heading,
                )
                if substance_issue:
                    substance_issue['sectionBlockIndex'] = section_block_index
                    return substance_issue
            section_plain_length = section_plain_lengths[section_index - 1]
            sec_min = length_spec.get('per_section_min', int(STRUCTURE_SPEC['sectionCharMin'])) - int(STRUCTURE_SPEC['validatorSectionTolerance'])
            sec_max = length_spec.get('per_section_max', int(STRUCTURE_SPEC['sectionCharMax'])) + int(STRUCTURE_SPEC['validatorSectionTolerance'])
            if section_index == len(section_blocks):
                sec_min = min(sec_min, 130)
            # LLM 출력 편차로 인한 미세 오차(±10자)는 허용해 불필요한 파이프라인 실패를 줄인다.
            section_length_tolerance = int(STRUCTURE_SPEC['validatorMicroTolerance'])
            if section_plain_length < sec_min or section_plain_length > sec_max:
                underflow = sec_min - section_plain_length
                overflow = section_plain_length - sec_max
                if 0 < underflow <= section_length_tolerance:
                    continue
                if 0 < overflow <= section_length_tolerance:
                    continue
                section_length_trace = ", ".join(str(length) for length in section_plain_lengths)
                return {
                    'passed': False,
                    'code': 'SECTION_LENGTH',
                    'reason': (
                        f"섹션 {section_index} 글자 수 위반 "
                        f"({section_plain_length}자, 허용 {sec_min}~{sec_max}자)"
                    ),
                    'feedback': (
                        f"섹션 {section_index}의 글자 수는 {sec_min}~{sec_max}자여야 합니다. "
                        f"현재 {section_plain_length}자이며, 전체 섹션 길이는 [{section_length_trace}]입니다."
                    ),
                    'sectionIndex': section_index,
                    'sectionLength': section_plain_length,
                    'sectionMin': sec_min,
                    'sectionMax': sec_max,
                    'sectionLengths': section_plain_lengths,
                    'sectionHeading': section_heading,
                    'sectionBlockIndex': section_block_index,
                    'isIntroSection': is_intro_section,
                }

        section_contract_issue = self._validate_bundle_section_contracts(
            content,
            poll_focus_bundle=poll_focus_bundle,
            body_sections=length_spec.get('body_sections', max(1, expected_h2 - 1)),
        )
        if section_contract_issue:
            return section_contract_issue

        normalized_user_keywords: List[str] = []
        for keyword in user_keywords or []:
            keyword_plain = strip_html(str(keyword or ''))
            if keyword_plain and keyword_plain not in normalized_user_keywords:
                normalized_user_keywords.append(keyword_plain)

        if len(section_blocks) >= 2:
            intro_plain = strip_html(section_blocks[0])
            conclusion_plain = strip_html(section_blocks[-1])
            if not self._intro_has_stance_anchor(intro_plain, context_analysis):
                return {
                    'passed': False,
                    'code': 'INTRO_STANCE_MISSING',
                    'reason': '서론에 입장문 앵커 누락',
                    'feedback': '서론 1~2문단에 입장문 핵심 주장을 분명히 포함해 주십시오.',
                }

            intro_flow_issue = self._validate_intro_flow(section_blocks[0])
            if intro_flow_issue:
                return intro_flow_issue

            section_semantic_issue = self._validate_section_semantic_lanes(
                content,
                category=category,
            )
            if section_semantic_issue:
                return section_semantic_issue

            min_phrase_len = 12
            duplicate_phrases = find_intro_conclusion_duplicates(
                intro_plain,
                conclusion_plain,
                user_keywords=normalized_user_keywords,
                min_phrase_len=min_phrase_len,
            )
            if len(duplicate_phrases) > int(QUALITY_SPEC['introEchoMax']):
                return {
                    'passed': False,
                    'code': 'INTRO_CONCLUSION_ECHO',
                    'reason': f'서론-결론 문구 중복 감지 ({len(duplicate_phrases)}개)',
                    'feedback': '서론과 결론에서 동일 표현이 과도하게 반복되었습니다. 결론 문장을 재구성하십시오.',
                    'duplicateCount': len(duplicate_phrases),
                    'duplicatePhrases': duplicate_phrases[:5],
                    'minPhraseLen': min_phrase_len,
                    'introEchoMax': int(QUALITY_SPEC['introEchoMax']),
                }

        p_open_tags = re.findall(r'<p\b[^>]*>', content, re.IGNORECASE)
        p_close_tags = re.findall(r'</p\s*>', content, re.IGNORECASE)
        p_count = len(p_open_tags)
        if p_count != len(p_close_tags):
            return {'passed': False, 'code': 'P_MALFORMED', 'reason': f"p 태그 짝 불일치", 'feedback': '모든 문단은 <p>...</p> 형태로 정확히 닫아 주십시오.'}

        expected_min_p = total_sections * int(paragraph_contract['section_paragraph_min'])
        expected_max_p = total_sections * int(paragraph_contract['section_paragraph_max'])
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

        source_contract_issue = self._validate_source_contract(content, context_analysis)
        if source_contract_issue:
            return source_contract_issue

        overused_anchor_phrases = self._find_overused_anchor_phrases(content)
        if overused_anchor_phrases:
            return {'passed': False, 'code': 'PHRASE_REPEAT_CAP', 'reason': "상투 구문 반복 과다", 'feedback': "대표 문구 반복이 과다합니다. 다른 표현으로 교체하십시오."}

        material_reuse_issues = self._detect_material_reuse_issues(
            content,
            context_analysis,
            max_mentions=int(QUALITY_SPEC['materialReuseMax']),
        )
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

        # 동일 문장 반복 체크
        sentences = self._split_plain_sentences(plain_text)
        sentence_counts: Dict[str, int] = {}
        for s in sentences:
            normalized = re.sub(r'\s+', ' ', s).strip()
            if len(normalized) >= 20:
                sentence_counts[normalized] = sentence_counts.get(normalized, 0) + 1
        duplicated = [s for s, c in sentence_counts.items() if c > QUALITY_SPEC['duplicateSentenceMax']]
        if duplicated:
            duplicate_samples = duplicated[:3]
            return {
                'passed': False,
                'code': 'DUPLICATE_SENTENCE',
                'reason': f'동일 문장 반복 ({len(duplicated)}건)',
                'feedback': f'동일 문장이 {QUALITY_SPEC["duplicateSentenceMax"]}회를 초과하여 반복되었습니다. 표현을 변형하십시오.',
                'duplicateCount': len(duplicated),
                'duplicateSamples': duplicate_samples,
            }

        # 3어절 이상 동일 구문 반복 체크 (문장 경계 존중)
        sentence_word_lists = []
        for sent in self._split_plain_sentences(plain_text):
            sent_words = sent.split()
            if len(sent_words) >= 3:
                sentence_word_lists.append(sent_words)
        if sentence_word_lists:
            trigram_counts: Dict[str, int] = {}
            for words in sentence_word_lists:
                for i in range(len(words) - 2):
                    trigram = ' '.join(words[i:i+3])
                    if len(trigram) >= 6:
                        trigram_counts[trigram] = trigram_counts.get(trigram, 0) + 1
            overused_phrases = [p for p, c in trigram_counts.items() if c > QUALITY_SPEC['phrase3wordMax']]
            if overused_phrases:
                worst = max(overused_phrases, key=lambda p: trigram_counts[p])
                return {
                    'passed': False,
                    'code': 'PHRASE_REPEAT',
                    'reason': f'3어절 구문 반복 과다 ("{worst}" {trigram_counts[worst]}회)',
                    'feedback': f'동일 구문이 {QUALITY_SPEC["phrase3wordMax"]}회를 초과했습니다. 다른 표현으로 교체하십시오.',
                }

        # 동사 과다 반복 체크 (종결어미 기반)
        verb_pattern = re.compile(r'(\S{2,}(?:합니다|했습니다|됩니다|겠습니다|봅니다|드립니다|줍니다))')
        # 계사(copula) 종결어미는 제외: "~입니다"는 일반 서술이므로 반복 체크 대상이 아님
        copula_pattern = re.compile(r'^.{0,4}입니다$')
        verb_matches = verb_pattern.findall(plain_text)
        if verb_matches:
            verb_counts: Dict[str, int] = {}
            for v in verb_matches:
                if copula_pattern.match(v):
                    continue
                verb_counts[v] = verb_counts.get(v, 0) + 1
            overused_verbs = [v for v, c in verb_counts.items() if c > QUALITY_SPEC['verbRepeatMax']]
            if overused_verbs:
                worst_verb = max(overused_verbs, key=lambda v: verb_counts[v])
                return {
                    'passed': False,
                    'code': 'VERB_REPEAT',
                    'reason': f'동사 반복 과다 ("{worst_verb}" {verb_counts[worst_verb]}회)',
                    'feedback': f'동일 동사/구문이 {QUALITY_SPEC["verbRepeatMax"]}회를 초과했습니다. 동의어로 교체하십시오.',
                }

        position = (context_analysis or {}).get('position') or ''
        all_advisories = []
        role_neg = self._find_role_negative_combinations(content)
        if role_neg:
            all_advisories.append({'code': 'ROLE_NEGATIVE_COMBO', 'reason': '직책+부정동사', 'samples': role_neg[:3]})
        regional = self._find_regional_derogatory_metaphors(content)
        if regional:
            all_advisories.append({'code': 'REGIONAL_DEROGATORY_METAPHOR', 'reason': '지역 비하성 은유', 'samples': regional[:3]})
        exec_verbs = self._find_executive_verb_claims(content, position=position)
        if exec_verbs:
            all_advisories.append({'code': 'EXECUTIVE_VERB_CLAIM', 'reason': '기초의원 집행형 동사', 'samples': exec_verbs[:3]})
        result: Dict[str, Any] = {'passed': True}
        if all_advisories:
            result['advisories'] = all_advisories
        return result
