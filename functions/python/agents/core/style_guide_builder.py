"""StructureAgent ??? ??? ??/?? ??."""

import re
from typing import Any, Dict, List, Optional

from .structure_utils import normalize_context_text, _xml_text

_STYLE_GUIDE_SECTION_RE = re.compile(r"^\s*\d+\.\s*(?P<section>[^:：]+)\s*[:：]\s*$")
_STYLE_GUIDE_BULLET_RE = re.compile(r"^\s*[-•]\s*(?P<label>[^:：]+?)(?:\s*[:：]\s*(?P<value>.+))?\s*$")
_STYLE_GUIDE_QUOTE_RE = re.compile(r'["“](.{3,220}?)["”]')
_STYLE_GUIDE_SOURCE_PREFIX_RE = re.compile(r"^(?:\[[^\]]+\]\s*)+")
_STYLE_GUIDE_LABEL_PREFIX_RE = re.compile(
    r"^(?:자기소개|자기 소개|프로필|약력|이력|경력|정책 메모|정책|공약|활동|성과)\s*:\s*"
)
_STYLE_GUIDE_NARRATIVE_MARKERS = (
    "태어나",
    "자라",
    "살아",
    "이어왔",
    "걸어왔",
    "노동자",
    "막내",
    "아들",
    "딸",
    "부산에서",
    "현장",
    "경험",
    "로서",
)
_STYLE_GUIDE_POLICY_MARKERS = (
    "정책",
    "정부",
    "공약",
    "비전",
    "AI",
    "경제",
    "도시",
    "산업",
    "일자리",
    "복지",
    "교통",
    "교육",
    "세우겠습니다",
    "살려내겠습니다",
    "만들겠습니다",
    "이뤄내겠습니다",
    "제시합니다",
    "바꾸겠습니다",
)
_STYLE_GUIDE_MEANING_MARKERS = (
    "비전",
    "제시합니다",
    "보여줍니다",
    "세우겠습니다",
    "살려내겠습니다",
    "만들겠습니다",
    "이뤄내겠습니다",
    "약속합니다",
    "분명한",
)
_STYLE_GUIDE_CLOSING_ENDING_RE = re.compile(
    r"(?:합니다|했습니다|있습니다|됩니다|드리겠습니다|하겠습니다|제시합니다|지키겠습니다|해내겠습니다|살려내겠습니다)\.?\s*$"
)


def _clean_style_example_text(text: Any) -> str:
    cleaned = normalize_context_text(text, sep=" ")
    if not cleaned:
        return ""
    cleaned = _STYLE_GUIDE_SOURCE_PREFIX_RE.sub("", cleaned)
    cleaned = _STYLE_GUIDE_LABEL_PREFIX_RE.sub("", cleaned)
    cleaned = re.sub(r"^(?:-\s*)+", "", cleaned).strip(" \"'“”")
    return cleaned


def _dedupe_style_items(items: List[str], *, limit: Optional[int] = None) -> List[str]:
    results: List[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = _clean_style_example_text(item)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(normalized)
        if limit is not None and len(results) >= limit:
            break
    return results


def _extract_style_quotes(text: Any) -> List[str]:
    results: List[str] = []
    for match in _STYLE_GUIDE_QUOTE_RE.findall(str(text or "")):
        cleaned = _clean_style_example_text(match)
        if cleaned:
            results.append(cleaned)
    return _dedupe_style_items(results)


def _parse_style_list_items(text: Any) -> List[str]:
    quoted = _extract_style_quotes(text)
    if quoted:
        return quoted
    cleaned = normalize_context_text(text, sep=" ")
    if not cleaned:
        return []
    parts = [
        _clean_style_example_text(part)
        for part in re.split(r"[,/|]|(?:\s{2,})", cleaned)
    ]
    return _dedupe_style_items([part for part in parts if part])


def _parse_style_guide_sections(style_guide: str) -> Dict[str, List[Dict[str, str]]]:
    sections: Dict[str, List[Dict[str, str]]] = {}
    current_section = ""
    for raw_line in normalize_context_text(style_guide, sep="\n").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        section_match = _STYLE_GUIDE_SECTION_RE.match(line)
        if section_match:
            current_section = normalize_context_text(section_match.group("section"))
            sections.setdefault(current_section, [])
            continue
        if not current_section:
            continue
        bullet_match = _STYLE_GUIDE_BULLET_RE.match(line)
        if not bullet_match:
            continue
        label = normalize_context_text(bullet_match.group("label"), sep=" ")
        value = normalize_context_text(bullet_match.group("value"), sep=" ") if bullet_match.group("value") else ""
        if not value:
            value = label
            label = ""
        sections.setdefault(current_section, []).append({"label": label, "value": value})
    return sections


def _collect_style_section_quotes(
    sections: Dict[str, List[Dict[str, str]]],
    *,
    section_keyword: str,
    label_keywords: List[str],
) -> List[str]:
    collected: List[str] = []
    for section_name, items in sections.items():
        if section_keyword not in section_name:
            continue
        for item in items:
            label = str(item.get("label") or "")
            value = str(item.get("value") or "")
            if label_keywords and not any(keyword in label or keyword in value for keyword in label_keywords):
                continue
            collected.extend(_extract_style_quotes(value))
    return _dedupe_style_items(collected)


def _collect_style_section_list_items(
    sections: Dict[str, List[Dict[str, str]]],
    *,
    section_keyword: str,
    label_keywords: List[str],
) -> List[str]:
    collected: List[str] = []
    for section_name, items in sections.items():
        if section_keyword not in section_name:
            continue
        for item in items:
            label = str(item.get("label") or "")
            value = str(item.get("value") or "")
            if label_keywords and not any(keyword in label or keyword in value for keyword in label_keywords):
                continue
            collected.extend(_parse_style_list_items(value))
    return _dedupe_style_items(collected)


def _contains_any_style_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _build_style_role_pairs(
    left_items: List[str],
    right_items: List[str],
    *,
    left_key: str,
    right_key: str,
    max_pairs: int = 2,
) -> List[Dict[str, str]]:
    pairs: List[Dict[str, str]] = []
    for idx, left in enumerate(left_items[:max_pairs]):
        if not left:
            continue
        right = right_items[idx] if idx < len(right_items) else (right_items[0] if right_items else "")
        if not right:
            continue
        pairs.append({left_key: left, right_key: right})
    return pairs


def _build_style_role_examples(
    style_guide: str,
    style_fingerprint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sections = _parse_style_guide_sections(style_guide)
    fingerprint = style_fingerprint if isinstance(style_fingerprint, dict) else {}
    rhetoric = fingerprint.get("rhetoricalDevices") or {}
    example_patterns = _dedupe_style_items(
        [_clean_style_example_text(item) for item in (rhetoric.get("examplePatterns") or [])],
        limit=3,
    )

    declaration_bridge_examples = _collect_style_section_quotes(
        sections,
        section_keyword="문장 역할별 실제 예시",
        label_keywords=["선언 뒤 연결"],
    )
    narrative_to_policy_pairs: List[Dict[str, str]] = []
    evidence_to_meaning_pairs: List[Dict[str, str]] = []
    closing_examples = _collect_style_section_quotes(
        sections,
        section_keyword="문장 역할별 실제 예시",
        label_keywords=["문단 마감"],
    )

    role_section_items = sections.get("문장 역할별 실제 예시", [])
    for item in role_section_items:
        label = str(item.get("label") or "")
        quotes = _extract_style_quotes(item.get("value"))
        if "개인 서사" in label and len(quotes) >= 2:
            narrative_to_policy_pairs.extend(
                _build_style_role_pairs(quotes[::2], quotes[1::2] or quotes[1:], left_key="narrative", right_key="policy")
            )
        if "수치/증거" in label and len(quotes) >= 2:
            evidence_to_meaning_pairs.extend(
                _build_style_role_pairs(quotes[::2], quotes[1::2] or quotes[1:], left_key="evidence", right_key="meaning")
            )

    transition_quotes = _collect_style_section_quotes(
        sections,
        section_keyword="전환 패턴",
        label_keywords=["실제 사용자 문장", "실제 전개 예시"],
    )
    transition_tokens = _collect_style_section_list_items(
        sections,
        section_keyword="전환 패턴",
        label_keywords=["선언 뒤 연결"],
    )
    concretization_quotes = _collect_style_section_quotes(
        sections,
        section_keyword="구체화 패턴",
        label_keywords=["실제 사용자 문장"],
    )
    positioning_quotes = _collect_style_section_quotes(
        sections,
        section_keyword="화자 포지셔닝 방식",
        label_keywords=["실제 자기 선언", "실제 사용자 문장"],
    )
    emotion_quotes = _collect_style_section_quotes(
        sections,
        section_keyword="감정 표현 방식",
        label_keywords=["실제 감정", "실제 선언", "실제 사용자 문장"],
    )
    closing_tokens = _collect_style_section_list_items(
        sections,
        section_keyword="리듬 패턴",
        label_keywords=["단락/문장 마감", "문장 마감"],
    )

    if not declaration_bridge_examples:
        declaration_bridge_examples = _dedupe_style_items(transition_quotes + example_patterns, limit=2)

    if not narrative_to_policy_pairs:
        narrative_candidates = [
            item
            for item in _dedupe_style_items(transition_quotes + concretization_quotes + positioning_quotes)
            if _contains_any_style_marker(item, _STYLE_GUIDE_NARRATIVE_MARKERS)
        ]
        policy_candidates = [
            item
            for item in _dedupe_style_items(example_patterns + positioning_quotes + emotion_quotes)
            if _contains_any_style_marker(item, _STYLE_GUIDE_POLICY_MARKERS)
        ]
        narrative_to_policy_pairs = _build_style_role_pairs(
            narrative_candidates,
            policy_candidates,
            left_key="narrative",
            right_key="policy",
        )

    if not evidence_to_meaning_pairs:
        evidence_candidates = [
            item
            for item in _dedupe_style_items(concretization_quotes + transition_quotes)
            if bool(re.search(r"\d", item)) or _contains_any_style_marker(item, ("부산", "시민", "현장", "기업", "경제"))
        ]
        meaning_candidates = [
            item
            for item in _dedupe_style_items(example_patterns + emotion_quotes + positioning_quotes)
            if _contains_any_style_marker(item, _STYLE_GUIDE_MEANING_MARKERS)
        ]
        evidence_to_meaning_pairs = _build_style_role_pairs(
            evidence_candidates,
            meaning_candidates,
            left_key="evidence",
            right_key="meaning",
        )

    if not closing_examples:
        closing_examples = _dedupe_style_items(
            emotion_quotes + [item for item in example_patterns if _STYLE_GUIDE_CLOSING_ENDING_RE.search(item)],
            limit=2,
        )

    return {
        "declarationBridgeExamples": declaration_bridge_examples[:2],
        "declarationBridgeTokens": transition_tokens[:4],
        "narrativeToPolicyPairs": narrative_to_policy_pairs[:2],
        "evidenceToMeaningPairs": evidence_to_meaning_pairs[:2],
        "closingExamples": closing_examples[:2],
        "closingTokens": closing_tokens[:4],
    }


def _build_style_role_guide_xml(style_guide: str, style_fingerprint: Optional[Dict[str, Any]] = None) -> str:
    role_examples = _build_style_role_examples(style_guide, style_fingerprint)
    has_examples = any(
        role_examples.get(key)
        for key in (
            "declarationBridgeExamples",
            "narrativeToPolicyPairs",
            "evidenceToMeaningPairs",
            "closingExamples",
        )
    )
    if not has_examples:
        return ""

    parts: List[str] = [
        '<style_role_guide priority="critical">',
        "  <rule id=\"prioritize_user_role_examples\">아래 실제 사용자 문장의 연결 방식은 금지 규칙보다 먼저 따른다. 문장을 그대로 복사하지 말고, 역할과 호흡만 따라 쓸 것.</rule>",
        "  <rule id=\"avoid_generic_second_sentence\">선언 다음 두 번째 문장은 범용 정치 문구로 흐르지 말고, 실제 사용자 예시처럼 경력·현장·정책·다음 근거로 즉시 이어갈 것.</rule>",
    ]

    if role_examples.get("declarationBridgeExamples") or role_examples.get("declarationBridgeTokens"):
        parts.append('  <role name="declaration_bridge">')
        parts.append("    <instruction>선언 직후 문장은 아래 실제 문장처럼 다음 근거, 경력, 현장 이야기로 바로 잇는다.</instruction>")
        bridge_tokens = "".join(
            f"<item>{_xml_text(item)}</item>" for item in role_examples.get("declarationBridgeTokens", [])
        )
        if bridge_tokens:
            parts.append(f"    <connectors>{bridge_tokens}</connectors>")
        bridge_examples = "".join(
            f"<example>{_xml_text(item)}</example>" for item in role_examples.get("declarationBridgeExamples", [])
        )
        if bridge_examples:
            parts.append(f"    <examples>{bridge_examples}</examples>")
        parts.append("  </role>")

    if role_examples.get("narrativeToPolicyPairs"):
        parts.append('  <role name="narrative_to_policy">')
        parts.append("    <instruction>개인 서사는 자기소개로 멈추지 말고, 아래 실제 문장 흐름처럼 정책·비전 선언으로 넘긴다.</instruction>")
        pair_xml = "".join(
            "<example>"
            f"<narrative>{_xml_text(item.get('narrative'))}</narrative>"
            f"<policy>{_xml_text(item.get('policy'))}</policy>"
            "</example>"
            for item in role_examples.get("narrativeToPolicyPairs", [])
            if item.get("narrative") and item.get("policy")
        )
        if pair_xml:
            parts.append(f"    <examples>{pair_xml}</examples>")
        parts.append("  </role>")

    if role_examples.get("evidenceToMeaningPairs"):
        parts.append('  <role name="evidence_to_meaning">')
        parts.append("    <instruction>수치·경력·증거를 제시한 뒤에는 아래 실제 문장 흐름처럼 그 의미를 짧고 단정하게 해석한다.</instruction>")
        pair_xml = "".join(
            "<example>"
            f"<evidence>{_xml_text(item.get('evidence'))}</evidence>"
            f"<meaning>{_xml_text(item.get('meaning'))}</meaning>"
            "</example>"
            for item in role_examples.get("evidenceToMeaningPairs", [])
            if item.get("evidence") and item.get("meaning")
        )
        if pair_xml:
            parts.append(f"    <examples>{pair_xml}</examples>")
        parts.append("  </role>")

    if role_examples.get("closingExamples") or role_examples.get("closingTokens"):
        parts.append('  <role name="closing">')
        parts.append("    <instruction>문단 마감은 아래 실제 문장처럼 짧고 단정하게 닫는다. 화자 자기평가나 시민 반응 추측으로 끝내지 않는다.</instruction>")
        closing_tokens = "".join(
            f"<item>{_xml_text(item)}</item>" for item in role_examples.get("closingTokens", [])
        )
        if closing_tokens:
            parts.append(f"    <preferred_endings>{closing_tokens}</preferred_endings>")
        closing_examples = "".join(
            f"<example>{_xml_text(item)}</example>" for item in role_examples.get("closingExamples", [])
        )
        if closing_examples:
            parts.append(f"    <examples>{closing_examples}</examples>")
        parts.append("  </role>")

    parts.append("</style_role_guide>")
    return "\n".join(parts)


def build_style_role_priority_summary(
    style_guide: str = "",
    style_fingerprint: Optional[Dict[str, Any]] = None,
) -> str:
    role_examples = _build_style_role_examples(style_guide, style_fingerprint)
    lines: List[str] = []

    declaration_examples = role_examples.get("declarationBridgeExamples") or []
    if declaration_examples:
        lines.append(f'선언 뒤 연결: "{declaration_examples[0]}"')

    narrative_pairs = role_examples.get("narrativeToPolicyPairs") or []
    if narrative_pairs:
        first_pair = narrative_pairs[0]
        lines.append(
            f'개인 서사->정책: 서사 "{first_pair.get("narrative")}" | 선언 "{first_pair.get("policy")}"'
        )

    evidence_pairs = role_examples.get("evidenceToMeaningPairs") or []
    if evidence_pairs:
        first_pair = evidence_pairs[0]
        lines.append(
            f'수치/증거->의미: 근거 "{first_pair.get("evidence")}" | 해석 "{first_pair.get("meaning")}"'
        )

    closing_examples = role_examples.get("closingExamples") or []
    if closing_examples:
        lines.append(f'문단 마감: "{closing_examples[0]}"')

    if not lines:
        return ""

    lines.append("위 실제 사용자 문장의 연결 방식을 금지 규칙보다 먼저 따른다. 문장을 복사하지 말고 역할만 따른다.")
    return "[style-role-priority]\n" + "\n".join(f"- {line}" for line in lines)
