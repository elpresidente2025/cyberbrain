import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..common.editorial import STRUCTURE_SPEC
from ..common.h2_guide import (
    H2_MAX_LENGTH,
    H2_MIN_LENGTH,
    sanitize_h2_text,
)
from ..common.section_contract import (
    _SECTION_WIDE_FORBIDDEN_ROLES,
    get_section_contract_sequence,
    split_sentences,
)
from .structure_utils import strip_html, normalize_artifacts, normalize_context_text


_HEADING_ALIGNMENT_GENERIC_IGNORE_TOKENS = {
    "시장",
    "부산시장",
    "후보",
    "예비후보",
    "의원",
    "국회의원",
    "위원장",
    "대표",
}


_INTRO_ORPHAN_TRANSITION_PREFIXES = (
    "특히",
    "또한",
    "아울러",
    "이와 함께",
    "이러한",
    "이는",
)

_INTRO_BRIDGE_TRANSITION_PREFIXES = (
    "앞으로도",
    "이제는",
    "이와 함께",
)


def _coerce_int_option(
    value: Any,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _infer_sentence_role(*args: Any, **kwargs: Any) -> str:
    from . import structure_agent as structure_agent_module

    return structure_agent_module.infer_sentence_role(*args, **kwargs)


def _validate_section_contract(*args: Any, **kwargs: Any) -> Optional[Dict[str, Any]]:
    from . import structure_agent as structure_agent_module

    return structure_agent_module.validate_section_contract(*args, **kwargs)


class SectionNormalizerMixin:
    def _clean_plain_text(self, value: Any) -> str:
        text = normalize_context_text(value, sep=' ')
        text = re.sub(r'<[^>]*>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _sanitize_heading_text(self, heading: Any) -> str:
        text = self._clean_plain_text(heading)
        if not text:
            raise ValueError("구조 JSON 계약 위반: 소제목이 비어 있습니다.")
        if self._BANNED_FIRST_PERSON_HEADING_PATTERN.search(text):
            raise ValueError(f"구조 JSON 계약 위반: 소제목 1인칭 표현 금지('{text}')")
        text = re.sub(r'(위한|향한|만드는|통한|대한)(\s|$)', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip(' -_.,')
        text = sanitize_h2_text(
            text,
            min_length=H2_MIN_LENGTH,
            max_length=H2_MAX_LENGTH,
        )
        return text

    def _count_plain_sentences(self, text: Any) -> int:
        cleaned = self._clean_plain_text(text)
        if not cleaned:
            return 0
        sentences = [sentence for sentence in split_sentences(cleaned) if self._clean_plain_text(sentence)]
        return len(sentences) if sentences else 1

    def _intro_transition_prefix(self, paragraph: Any) -> str:
        cleaned = self._clean_plain_text(paragraph)
        for prefix in _INTRO_ORPHAN_TRANSITION_PREFIXES + _INTRO_BRIDGE_TRANSITION_PREFIXES:
            if cleaned.startswith(prefix):
                return prefix
        return ""

    def _is_short_intro_fragment(self, paragraph: Any) -> bool:
        cleaned = self._clean_plain_text(paragraph)
        if not cleaned:
            return False
        sentence_count = self._count_plain_sentences(cleaned)
        return sentence_count <= 1 and len(cleaned) <= 95

    def _should_merge_intro_paragraph(
        self,
        previous: Any,
        current: Any,
    ) -> bool:
        previous_text = self._clean_plain_text(previous)
        current_text = self._clean_plain_text(current)
        if not previous_text or not current_text:
            return False

        previous_sentence_count = self._count_plain_sentences(previous_text)
        current_sentence_count = self._count_plain_sentences(current_text)
        transition_prefix = self._intro_transition_prefix(current_text)
        if transition_prefix:
            if transition_prefix in _INTRO_ORPHAN_TRANSITION_PREFIXES:
                return previous_sentence_count <= 2 or len(previous_text) <= 140
            return previous_sentence_count <= 1 or len(previous_text) <= 90

        if len(previous_text) <= 30 and current_sentence_count <= 2:
            return True
        if (
            previous_sentence_count <= 1
            and current_sentence_count <= 1
            and len(previous_text) + len(current_text) <= 180
        ):
            return True
        return False

    def _normalize_intro_paragraphs(
        self,
        paragraphs: Any,
        *,
        target_count: int,
    ) -> List[str]:
        cleaned_list = self._normalize_section_paragraphs(
            paragraphs,
            target_count=max(1, min(target_count, 3)),
        )
        if len(cleaned_list) <= 1:
            return cleaned_list

        merged: List[str] = []
        for paragraph in cleaned_list:
            cleaned = self._clean_plain_text(paragraph)
            if not cleaned:
                continue
            if not merged:
                merged.append(cleaned)
                continue
            if self._should_merge_intro_paragraph(merged[-1], cleaned):
                merged[-1] = f"{merged[-1]} {cleaned}".strip()
                continue
            merged.append(cleaned)

        while len(merged) > 2:
            tail = self._clean_plain_text(merged[-1])
            prev = self._clean_plain_text(merged[-2])
            if self._intro_transition_prefix(tail) or self._is_short_intro_fragment(tail):
                merged[-2] = f"{prev} {tail}".strip()
                merged.pop()
                continue
            if self._is_short_intro_fragment(prev) and len(merged) >= 3:
                merged[-3] = f"{self._clean_plain_text(merged[-3])} {prev}".strip()
                merged.pop(-2)
                continue
            break

        return merged

    def _heading_identity_key(self, heading: Any) -> str:
        text = self._clean_plain_text(heading)
        return re.sub(r"[^0-9A-Za-z가-힣]+", "", text).lower()

    def _heading_semantic_family_key(self, heading: Any) -> str:
        text = self._clean_plain_text(heading)
        compact = re.sub(r"\s+", "", text)
        if "주목" in compact and ("가능성" in compact or "이유" in compact):
            return "possibility_focus"
        return ""

    def _heading_alignment_tokens(
        self,
        value: Any,
        *,
        ignore_tokens: Optional[Sequence[str]] = None,
    ) -> set[str]:
        text = self._clean_plain_text(value)
        if not text:
            return set()
        ignored = {
            re.sub(r"\s+", "", str(token or "").strip().lower())
            for token in (ignore_tokens or [])
            if str(token or "").strip()
        }
        ignored.update(_HEADING_ALIGNMENT_GENERIC_IGNORE_TOKENS)
        tokens: set[str] = set()
        for raw in re.findall(r"[0-9A-Za-z가-힣]{2,}", text):
            token = raw.lower().strip()
            for suffix in self._HEADING_ALIGNMENT_SUFFIXES:
                if token.endswith(suffix) and len(token) - len(suffix) >= 2:
                    token = token[: -len(suffix)]
                    break
            if not token or token in self._HEADING_ALIGNMENT_STOPWORDS:
                continue
            if token.isdigit():
                continue
            if token in ignored:
                continue
            tokens.add(token)
        return tokens

    def _heading_body_alignment_score(
        self,
        heading: Any,
        paragraphs: Any,
        *,
        use_all_paragraphs: bool = False,
        ignore_tokens: Optional[Sequence[str]] = None,
    ) -> float:
        heading_tokens = self._heading_alignment_tokens(heading, ignore_tokens=ignore_tokens)
        if not heading_tokens:
            return 0.0
        paragraph_list = paragraphs if isinstance(paragraphs, list) else [paragraphs]
        lead_text = " ".join(
            self._clean_plain_text(item)
            for item in (paragraph_list if use_all_paragraphs else paragraph_list[:2])
            if self._clean_plain_text(item)
        ).strip()
        body_tokens = self._heading_alignment_tokens(lead_text, ignore_tokens=ignore_tokens)
        if not body_tokens:
            return 0.0
        overlap = len(heading_tokens & body_tokens)
        return overlap / max(1, len(heading_tokens))

    def _repair_low_alignment_heading(
        self,
        *,
        heading: str,
        paragraphs: Sequence[str],
        contract: Optional[Dict[str, Any]],
        section_label: str,
        use_all_paragraphs: bool = False,
        ignore_tokens: Optional[Sequence[str]] = None,
        minimum_score: float = 0.24,
    ) -> str:
        alignment_score = self._heading_body_alignment_score(
            heading,
            paragraphs,
            use_all_paragraphs=use_all_paragraphs,
            ignore_tokens=ignore_tokens,
        )
        if alignment_score >= minimum_score:
            return heading

        template = ""
        raw_template = (contract or {}).get("template")
        if self._clean_plain_text(raw_template):
            template = self._sanitize_heading_text(raw_template)
        if template:
            template_score = self._heading_body_alignment_score(
                template,
                paragraphs,
                use_all_paragraphs=use_all_paragraphs,
                ignore_tokens=ignore_tokens,
            )
            print(
                f"🩹 [StructureAgent] {section_label} 소제목 정합성 보정: "
                f"'{heading}' -> '{template}' (score={alignment_score:.2f}->{template_score:.2f}, threshold={minimum_score:.2f})"
            )
            return template

        print(
            f"⚠️ [StructureAgent] {section_label} 소제목 정합성 낮음 유지: "
            f"'{heading}' (score={alignment_score:.2f}, threshold={minimum_score:.2f})"
        )
        return heading

    def _normalize_section_paragraphs(
        self,
        paragraphs: Any,
        *,
        target_count: int,
    ) -> List[str]:
        candidates = paragraphs if isinstance(paragraphs, list) else [paragraphs]
        cleaned_list: List[str] = []
        for item in candidates:
            cleaned = self._clean_plain_text(item)
            if cleaned:
                cleaned_list.append(cleaned)

        if len(cleaned_list) > target_count:
            keep = cleaned_list[: target_count - 1]
            tail = " ".join(cleaned_list[target_count - 1 :]).strip()
            if tail:
                keep.append(tail)
            cleaned_list = keep

        if len(cleaned_list) < target_count:
            print(
                f"⚠️ [StructureAgent] 문단 수 부족({len(cleaned_list)}개, "
                f"요구 {target_count}개) — 있는 만큼 사용, normalize_section_p_count가 보정"
            )

        return cleaned_list[:target_count]

    def _remove_sentence_from_paragraphs(
        self,
        paragraphs: List[str],
        *,
        target_sentence: str,
    ) -> List[str]:
        target = self._clean_plain_text(target_sentence)
        if not target:
            return paragraphs

        repaired: List[str] = []
        removed = False
        for paragraph in paragraphs:
            cleaned_paragraph = self._clean_plain_text(paragraph)
            if not cleaned_paragraph:
                continue
            sentence_candidates = [self._clean_plain_text(chunk) for chunk in split_sentences(cleaned_paragraph)]
            kept_sentences: List[str] = []
            for sentence in sentence_candidates:
                if not sentence:
                    continue
                if not removed and sentence == target:
                    removed = True
                    continue
                kept_sentences.append(sentence)
            rebuilt = " ".join(kept_sentences).strip()
            if rebuilt:
                repaired.append(rebuilt)

        if not removed:
            print(f"⚠️ [StructureAgent] 문장 제거 실패: {target}")
            return paragraphs
        return repaired

    def _split_h2_blocks(self, content: str) -> Tuple[str, List[str]]:
        normalized = normalize_artifacts(content or "")
        first_h2_match = re.search(r'<h2\b', normalized, re.IGNORECASE)
        if not first_h2_match:
            return normalized.strip(), []
        intro = normalized[:first_h2_match.start()].strip()
        h2_blocks = [
            block.strip()
            for block in re.split(r'(?=<h2\b)', normalized[first_h2_match.start():], flags=re.IGNORECASE)
            if block and block.strip()
        ]
        return intro, h2_blocks

    def _replace_h2_block(self, content: str, block_index: int, new_block: str) -> str:
        intro, h2_blocks = self._split_h2_blocks(content)
        if block_index < 0 or block_index >= len(h2_blocks):
            return content
        updated_blocks = list(h2_blocks)
        updated_blocks[block_index] = normalize_artifacts(new_block).strip()
        parts: List[str] = []
        if intro:
            parts.append(intro)
        parts.extend(block for block in updated_blocks if block)
        return "\n".join(parts).strip()

    def _resolve_section_block_from_validation(
        self,
        content: str,
        validation: Dict[str, Any],
    ) -> Tuple[int, str, str]:
        _, h2_blocks = self._split_h2_blocks(content)
        if not h2_blocks:
            return -1, "", ""

        block_index = -1
        raw_block_index = validation.get('sectionBlockIndex')
        try:
            if raw_block_index is not None and int(raw_block_index) >= 0:
                block_index = int(raw_block_index)
        except (TypeError, ValueError):
            block_index = -1

        if block_index < 0:
            try:
                section_index = int(validation.get('sectionIndex') or 0)
            except (TypeError, ValueError):
                section_index = 0
            if section_index > 0:
                block_index = section_index - 1

        if block_index < 0 or block_index >= len(h2_blocks):
            target_heading = normalize_context_text(validation.get('sectionHeading'))
            if target_heading:
                for index, block in enumerate(h2_blocks):
                    heading_match = re.search(r'<h2[^>]*>(.*?)</h2>', block, re.IGNORECASE | re.DOTALL)
                    heading_text = strip_html(heading_match.group(1)).strip() if heading_match else ''
                    if heading_text == target_heading:
                        block_index = index
                        break

        if block_index < 0 or block_index >= len(h2_blocks):
            return -1, "", ""

        block_html = h2_blocks[block_index]
        heading_match = re.search(r'<h2[^>]*>(.*?)</h2>', block_html, re.IGNORECASE | re.DOTALL)
        heading_text = strip_html(heading_match.group(1)).strip() if heading_match else ''
        return block_index, block_html, heading_text

    def _resolve_section_contract_for_block(
        self,
        *,
        poll_focus_bundle: Optional[Dict[str, Any]],
        length_spec: Dict[str, int],
        block_index: int,
    ) -> Optional[Dict[str, Any]]:
        if block_index < 0:
            return None
        body_contracts, conclusion_contract = get_section_contract_sequence(
            poll_focus_bundle,
            body_sections=max(1, int(length_spec.get('body_sections') or 1)),
        )
        if block_index < len(body_contracts):
            return body_contracts[block_index]
        if block_index == len(body_contracts):
            return conclusion_contract
        return None

    def _build_degraded_section_block(
        self,
        *,
        heading_text: str,
        section_block_html: str,
        section_contract: Optional[Dict[str, Any]],
        validation: Dict[str, Any],
    ) -> str:
        paragraph_matches = re.findall(r'<p\b[^>]*>([\s\S]*?)</p\s*>', section_block_html, re.IGNORECASE)
        paragraphs = [self._clean_plain_text(strip_html(item)) for item in paragraph_matches if self._clean_plain_text(strip_html(item))]
        violation = validation.get('violation') if isinstance(validation.get('violation'), dict) else {}
        target_sentence = normalize_context_text(violation.get('sentence'))
        cleaned_paragraphs = self._remove_sentence_from_paragraphs(paragraphs, target_sentence=target_sentence) if target_sentence else paragraphs
        answer_lead = normalize_context_text((section_contract or {}).get('answerLead'))

        kept_paragraphs: List[str] = []
        if answer_lead:
            kept_paragraphs.append(answer_lead)
        for paragraph in cleaned_paragraphs:
            if paragraph and paragraph not in kept_paragraphs:
                kept_paragraphs.append(paragraph)
            if len(kept_paragraphs) >= 2:
                break
        if not kept_paragraphs and cleaned_paragraphs:
            kept_paragraphs.append(cleaned_paragraphs[0])

        rebuilt_parts = [f"<h2>{heading_text}</h2>"]
        for paragraph in kept_paragraphs:
            rebuilt_parts.append(f"<p>{paragraph}</p>")
        return "\n".join(rebuilt_parts).strip()

    def _build_html_from_structure_json(
        self,
        payload: Dict[str, Any],
        *,
        length_spec: Dict[str, int],
        topic: str,
        poll_focus_bundle: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str]:
        section_paragraphs = _coerce_int_option(
            length_spec.get('paragraphs_per_section'),
            default=int(STRUCTURE_SPEC['paragraphsPerSection']),
            minimum=2,
            maximum=4,
        )
        body_sections = max(1, int(length_spec.get('body_sections') or 1))

        title = self._clean_plain_text(payload.get('title'))
        if not title:
            title = (topic or "새 원고").strip()[:40]

        intro_payload = payload.get('intro')
        if not isinstance(intro_payload, dict):
            raise ValueError("구조 JSON 계약 위반: intro 객체가 누락되었습니다.")
        intro_paragraphs = self._normalize_intro_paragraphs(
            intro_payload.get('paragraphs'),
            target_count=section_paragraphs,
        )

        body_payload = payload.get('body')
        if not isinstance(body_payload, list):
            raise ValueError("구조 JSON 계약 위반: body 배열이 누락되었습니다.")
        conclusion_payload = payload.get('conclusion')
        if not isinstance(conclusion_payload, dict):
            raise ValueError("구조 JSON 계약 위반: conclusion 객체가 누락되었습니다.")

        html_parts: List[str] = []
        seen_heading_keys: set[str] = set()
        seen_heading_families: set[str] = set()
        body_contracts, conclusion_contract = get_section_contract_sequence(
            poll_focus_bundle,
            body_sections=body_sections,
        )
        primary_pair = (
            poll_focus_bundle.get('primaryPair')
            if isinstance(poll_focus_bundle, dict) and isinstance(poll_focus_bundle.get('primaryPair'), dict)
            else {}
        )
        contract_speaker = normalize_context_text(
            primary_pair.get('speaker') if isinstance(primary_pair, dict) else ''
        ) or normalize_context_text((poll_focus_bundle or {}).get('speaker') if isinstance(poll_focus_bundle, dict) else '')
        contract_opponent = normalize_context_text(
            primary_pair.get('opponent') if isinstance(primary_pair, dict) else ''
        )
        alignment_ignore_tokens = [
            token
            for token in (
                contract_speaker,
                contract_opponent,
            )
            if token
        ]

        def _register_heading_or_raise(heading_text: str) -> None:
            heading_key = self._heading_identity_key(heading_text)
            if heading_key and heading_key in seen_heading_keys:
                raise ValueError(f"구조 JSON 계약 위반: 소제목 중복('{heading_text}')")
            if heading_key:
                seen_heading_keys.add(heading_key)

            family_key = self._heading_semantic_family_key(heading_text)
            if family_key and family_key in seen_heading_families:
                raise ValueError(f"구조 JSON 계약 위반: 소제목 의미 중복('{heading_text}')")
            if family_key:
                seen_heading_families.add(family_key)

        def _remove_role_sentences_from_paragraphs(
            source_paragraphs: List[str],
            *,
            target_role: Optional[str] = None,
            target_roles: Optional[Sequence[str]] = None,
            log_label: str,
            summary_label: str = "",
        ) -> List[str]:
            role_set = {
                normalize_context_text(role)
                for role in (target_roles or ([] if target_role is None else [target_role]))
                if normalize_context_text(role)
            }
            if not role_set:
                return list(source_paragraphs)
            cleaned_paragraphs: List[str] = []
            removed_any = False
            for paragraph in source_paragraphs:
                sentences = split_sentences(paragraph)
                if not sentences:
                    normalized_paragraph = self._clean_plain_text(paragraph)
                    if normalized_paragraph:
                        cleaned_paragraphs.append(normalized_paragraph)
                    continue
                kept_sentences: List[str] = []
                for sentence in sentences:
                    role = _infer_sentence_role(
                        sentence,
                        speaker=contract_speaker,
                        opponent=contract_opponent,
                    )
                    if role in role_set:
                        removed_any = True
                        print(f"🩹 [StructureAgent] {log_label} {role} 자동 정리: {sentence}")
                        continue
                    kept_sentences.append(sentence)
                rebuilt = " ".join(kept_sentences).strip()
                if rebuilt:
                    cleaned_paragraphs.append(rebuilt)
            if removed_any and summary_label:
                print(f"🩹 [StructureAgent] {log_label} {summary_label} 사전 정리 완료")
            return cleaned_paragraphs

        def _validate_section_contract_or_raise(
            *,
            heading_text: str,
            paragraphs: List[str],
            contract: Optional[Dict[str, Any]],
            section_label: str,
        ) -> List[str]:
            repaired = list(paragraphs)
            if contract is None:
                repaired = _remove_role_sentences_from_paragraphs(
                    repaired,
                    target_role='audience_reaction',
                    log_label=section_label,
                )
                return repaired
            allowed_sentence_roles = {
                normalize_context_text(role) for role in (contract.get('allowedSentenceRoles') or []) if normalize_context_text(role)
            }
            section_wide_forbidden_roles = {
                role for role in _SECTION_WIDE_FORBIDDEN_ROLES if role not in allowed_sentence_roles
            }
            if section_wide_forbidden_roles:
                pre_cleaned = _remove_role_sentences_from_paragraphs(
                    repaired,
                    target_roles=sorted(section_wide_forbidden_roles),
                    log_label=section_label,
                    summary_label='section_wide_forbidden',
                )
                if pre_cleaned != repaired:
                    repaired = pre_cleaned
            removable_codes = {
                'experience_followup_disallowed',
                'experience_followup_role_mismatch',
                'section_disallowed_role',
                'first_sentence_forbidden_role',
            }
            violation: Optional[Dict[str, Any]] = None
            for _ in range(6):
                violation = _validate_section_contract(
                    heading=heading_text,
                    paragraphs=repaired,
                    contract=contract,
                    speaker=contract_speaker,
                    opponent=contract_opponent,
                )
                if not violation:
                    return repaired
                violation_code = normalize_context_text(violation.get('code'))
                violation_sentence = normalize_context_text(violation.get('sentence'))
                if violation_code not in removable_codes or not violation_sentence:
                    break
                next_repaired = self._remove_sentence_from_paragraphs(
                    repaired,
                    target_sentence=violation_sentence,
                )
                if next_repaired == repaired:
                    break
                repaired = next_repaired
                print(
                    f"🩹 [StructureAgent] {section_label} 허용 문장 계약 위반 자동 정리: "
                    f"{violation_code}"
                )

            if not violation:
                return repaired
            message = normalize_context_text(violation.get('message')) or '허용 문장 계약 위반'
            print(
                f"⚠️ [StructureAgent] {section_label} 허용 문장 계약 위반 보류: "
                f"'{heading_text}' / {message}"
            )
            return repaired

        def _clean_intro_audience_reaction_paragraphs(paragraphs: List[str]) -> List[str]:
            return _remove_role_sentences_from_paragraphs(
                paragraphs,
                target_role='audience_reaction',
                log_label='intro',
            )

        def _has_renderable_paragraphs(paragraphs: List[str]) -> bool:
            return any(self._clean_plain_text(paragraph) for paragraph in paragraphs)

        def _log_empty_section_drop(
            *,
            section_label: str,
            heading_text: str,
            reason: str,
            before_count: int,
            after_count: int,
        ) -> None:
            print(
                f"⚠️ [StructureAgent] {section_label} 본문이 비어 섹션을 드롭합니다: "
                f"'{heading_text}' (reason={reason}, before={before_count}, after={after_count})"
            )

        intro_paragraphs = _clean_intro_audience_reaction_paragraphs(intro_paragraphs)

        for paragraph in intro_paragraphs:
            html_parts.append(f"<p>{paragraph}</p>")

        for index in range(body_sections):
            if index >= len(body_payload) or not isinstance(body_payload[index], dict):
                raise ValueError(
                    f"구조 JSON 계약 위반: 본론 섹션 누락({index + 1}/{body_sections})"
                )
            section = body_payload[index]
            heading = self._sanitize_heading_text(section.get('heading'))
            section_paragraph_list = self._normalize_section_paragraphs(
                section.get('paragraphs'),
                target_count=section_paragraphs,
            )
            if not _has_renderable_paragraphs(section_paragraph_list):
                _log_empty_section_drop(
                    section_label=f"본론 {index + 1}",
                    heading_text=heading,
                    reason="empty_after_normalize",
                    before_count=0,
                    after_count=len(section_paragraph_list),
                )
                continue
            contract = body_contracts[index] if index < len(body_contracts) else None
            section_paragraph_count_before_contract = len(section_paragraph_list)
            section_paragraph_list = _validate_section_contract_or_raise(
                heading_text=heading,
                paragraphs=section_paragraph_list,
                contract=contract,
                section_label=f"본론 {index + 1}",
            )
            if not _has_renderable_paragraphs(section_paragraph_list):
                _log_empty_section_drop(
                    section_label=f"본론 {index + 1}",
                    heading_text=heading,
                    reason="emptied_after_contract_cleanup",
                    before_count=section_paragraph_count_before_contract,
                    after_count=len(section_paragraph_list),
                )
                continue
            heading = self._repair_low_alignment_heading(
                heading=heading,
                paragraphs=section_paragraph_list,
                contract=contract,
                section_label=f"본론 {index + 1}",
                ignore_tokens=alignment_ignore_tokens,
                minimum_score=0.34,
            )
            _register_heading_or_raise(heading)
            html_parts.append(f"<h2>{heading}</h2>")
            for paragraph in section_paragraph_list:
                html_parts.append(f"<p>{paragraph}</p>")

        conclusion_heading = self._sanitize_heading_text(conclusion_payload.get('heading'))
        conclusion_paragraphs = self._normalize_section_paragraphs(
            conclusion_payload.get('paragraphs'),
            target_count=section_paragraphs,
        )
        if not _has_renderable_paragraphs(conclusion_paragraphs):
            _log_empty_section_drop(
                section_label='결론',
                heading_text=conclusion_heading,
                reason="empty_after_normalize",
                before_count=0,
                after_count=len(conclusion_paragraphs),
            )
            content = "\n".join(html_parts).strip()
            return content, title
        conclusion_paragraph_count_before_contract = len(conclusion_paragraphs)
        conclusion_paragraphs = _validate_section_contract_or_raise(
            heading_text=conclusion_heading,
            paragraphs=conclusion_paragraphs,
            contract=conclusion_contract,
            section_label='결론',
        )
        if not _has_renderable_paragraphs(conclusion_paragraphs):
            _log_empty_section_drop(
                section_label='결론',
                heading_text=conclusion_heading,
                reason="emptied_after_contract_cleanup",
                before_count=conclusion_paragraph_count_before_contract,
                after_count=len(conclusion_paragraphs),
            )
            content = "\n".join(html_parts).strip()
            return content, title
        conclusion_heading = self._repair_low_alignment_heading(
            heading=conclusion_heading,
            paragraphs=conclusion_paragraphs,
            contract=conclusion_contract,
            section_label='결론',
            use_all_paragraphs=True,
            ignore_tokens=alignment_ignore_tokens,
            minimum_score=0.24,
        )
        _register_heading_or_raise(conclusion_heading)
        html_parts.append(f"<h2>{conclusion_heading}</h2>")
        for paragraph in conclusion_paragraphs:
            html_parts.append(f"<p>{paragraph}</p>")

        content = "\n".join(html_parts).strip()
        return content, title
