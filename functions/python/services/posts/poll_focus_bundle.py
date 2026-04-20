"""Shared poll focus bundle for matchup-oriented title/body generation."""

from __future__ import annotations

import html
import re
from typing import Any, Dict, Iterable, List, Optional

from agents.common.role_keyword_policy import extract_role_keyword_parts
from agents.common.section_contract import build_matchup_allowed_h2_kinds

from .poll_fact_guard import build_poll_matchup_fact_table

_HTML_TAG_RE = re.compile(r"<[^>]*>")
_SPACE_RE = re.compile(r"\s+")
_PERSON_RE = re.compile(r"[가-힣]{2,4}")

_GENERIC_NAME_TOKENS = {
    # 직함·선거 용어
    "부산시장",
    "서울시장",
    "시장",
    "도지사",
    "후보",
    "예비후보",
    "양자대결",
    "가상대결",
    "대결",
    "접전",
    "각축",
    "여론조사",
    "가능성",
    "경쟁력",
    "정당",
    "지지율",
    "민주당",
    "국민의힘",
    # 광역시·도 (2~4자 한글이라 인물명 패턴에 걸리는 지명)
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "세종",
    "경기",
    "강원",
    "충북",
    "충남",
    "전북",
    "전남",
    "경북",
    "경남",
    "제주",
}

_FORBIDDEN_METRICS = [
    "정당 지지율",
    "지지정당 없음",
    "당내 경선 수치",
    "후보 적합도",
    "후보군 전체 비교",
]


def _normalize_text(value: Any) -> str:
    text = html.unescape(str(value or ""))
    text = _HTML_TAG_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def _normalize_person_name(value: Any) -> str:
    name = re.sub(r"[^가-힣]", "", str(value or ""))
    if 2 <= len(name) <= 8:
        return name
    return ""


def _unique_names(items: Iterable[Any]) -> List[str]:
    result: List[str] = []
    seen: set[str] = set()
    for item in items:
        name = _normalize_person_name(item)
        if not name or name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def _extract_topic_names(topic: str) -> List[str]:
    topic_text = _normalize_text(topic)
    if not topic_text:
        return []
    names: List[str] = []
    for token in _PERSON_RE.findall(topic_text):
        if token in _GENERIC_NAME_TOKENS:
            continue
        if token not in names:
            names.append(token)
    return names[:4]


def _extract_keyword_names(user_keywords: Iterable[Any]) -> List[str]:
    names: List[str] = []
    for raw_keyword in user_keywords or []:
        keyword = str(raw_keyword or "").strip()
        if not keyword:
            continue
        parts = extract_role_keyword_parts(keyword)
        name = parts.get("name") or keyword
        normalized = _normalize_person_name(name)
        if normalized and normalized not in names:
            names.append(normalized)
    return names[:4]


def _extract_source_names(text_sources: Iterable[Any]) -> List[str]:
    names: List[str] = []
    for raw in text_sources or []:
        source_text = _normalize_text(raw)
        if not source_text:
            continue
        for token in _PERSON_RE.findall(source_text):
            if token in _GENERIC_NAME_TOKENS:
                continue
            if token not in names:
                names.append(token)
    return names[:8]


def _format_percent(value: Any) -> str:
    try:
        number = round(float(value), 1)
    except (TypeError, ValueError):
        return ""
    if abs(number - int(number)) < 0.05:
        return f"{int(number)}%"
    return f"{number:.1f}%"


def _has_final_consonant(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    char = normalized[-1]
    if not ("가" <= char <= "힣"):
        return False
    return (ord(char) - ord("가")) % 28 != 0


def _with_particle(text: str, consonant: str, vowel: str) -> str:
    base = str(text or "").strip()
    if not base:
        return ""
    return f"{base}{consonant if _has_final_consonant(base) else vowel}"


def _normalize_pair_record(entry: Dict[str, Any], speaker: str) -> Dict[str, Any]:
    left = _normalize_person_name(entry.get("left"))
    right = _normalize_person_name(entry.get("right"))
    left_score = entry.get("leftScore")
    right_score = entry.get("rightScore")
    speaker_is_left = speaker == left
    opponent = right if speaker_is_left else left
    speaker_score = left_score if speaker_is_left else right_score
    opponent_score = right_score if speaker_is_left else left_score
    try:
        margin = round(abs(float(speaker_score) - float(opponent_score)), 1)
    except (TypeError, ValueError):
        margin = 99.0
    return {
        "left": left,
        "right": right,
        "speaker": speaker,
        "opponent": opponent,
        "speakerScore": speaker_score,
        "opponentScore": opponent_score,
        "speakerPercent": _format_percent(speaker_score),
        "opponentPercent": _format_percent(opponent_score),
        "margin": margin,
        "records": list(entry.get("records") or []),
    }


def _build_pair_fact_sentence(record: Dict[str, Any]) -> str:
    speaker = str(record.get("speaker") or "").strip()
    opponent = str(record.get("opponent") or "").strip()
    speaker_percent = str(record.get("speakerPercent") or "").strip()
    opponent_percent = str(record.get("opponentPercent") or "").strip()
    if not speaker or not opponent or not speaker_percent or not opponent_percent:
        return ""
    return f"{speaker}·{opponent} 가상대결에서는 {speaker_percent} 대 {opponent_percent}로 나타났습니다."


def _build_pair_heading(record: Dict[str, Any]) -> str:
    speaker = str(record.get("speaker") or "").strip()
    opponent = str(record.get("opponent") or "").strip()
    speaker_percent = str(record.get("speakerPercent") or "").strip()
    opponent_percent = str(record.get("opponentPercent") or "").strip()
    if not speaker or not opponent or not speaker_percent or not opponent_percent:
        return ""
    return f"{_with_particle(opponent, '과', '와')}의 가상대결, {speaker} {speaker_percent} 대 {opponent_percent}"


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_speaker_ahead(record: Dict[str, Any]) -> bool:
    speaker_score = _to_float(record.get("speakerScore"))
    opponent_score = _to_float(record.get("opponentScore"))
    if speaker_score is None or opponent_score is None:
        return False
    return speaker_score > opponent_score


def _build_primary_matchup_heading(record: Dict[str, Any]) -> str:
    speaker = str(record.get("speaker") or "").strip()
    opponent = str(record.get("opponent") or "").strip()
    if not speaker or not opponent:
        return ""
    subject = _with_particle(speaker, "이", "가")
    if _is_speaker_ahead(record):
        return f"{subject} {opponent}와의 가상대결에서 앞선 이유"
    return f"{subject} {opponent}와의 가상대결에서 접전을 만든 배경"


def _build_secondary_matchup_heading(record: Dict[str, Any]) -> str:
    speaker = str(record.get("speaker") or "").strip()
    opponent = str(record.get("opponent") or "").strip()
    if not speaker or not opponent:
        return ""
    margin = _to_float(record.get("margin"))
    if margin is not None and margin <= 3.1:
        return f"{opponent}과의 접전에서 확인된 {speaker} 경쟁력"
    return f"{opponent}과의 대결에서 드러난 {speaker} 구도"


def _build_title_lanes(primary_pair: Dict[str, Any]) -> List[Dict[str, str]]:
    speaker = str(primary_pair.get("speaker") or "").strip()
    opponent = str(primary_pair.get("opponent") or "").strip()
    speaker_percent = str(primary_pair.get("speakerPercent") or "").strip()
    opponent_percent = str(primary_pair.get("opponentPercent") or "").strip()
    if not speaker or not opponent or not speaker_percent or not opponent_percent:
        return []
    score_text = f"{speaker_percent} 대 {opponent_percent}"
    return [
        {
            "id": "intent_fact",
            "label": "intent+fact",
            "template": f"{opponent} 구도 속, {speaker}·{opponent} 가상대결 {score_text}",
        },
        {
            "id": "fact_direct",
            "label": "fact_direct",
            "template": f"{speaker}·{opponent} 가상대결 {score_text}",
        },
        {
            "id": "contest_observation",
            "label": "contest_observation",
            "template": f"{_with_particle(opponent, '과', '와')}의 가상대결서 확인된 {speaker} 경쟁력",
        },
    ]


def build_poll_focus_bundle(
    *,
    topic: str,
    user_keywords: Iterable[Any],
    full_name: str,
    text_sources: Iterable[Any],
    poll_fact_table: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    speaker = _normalize_person_name(full_name)
    topic_names = _extract_topic_names(topic)
    keyword_names = _extract_keyword_names(user_keywords)
    source_names = _extract_source_names(text_sources)
    seed_names = _unique_names([speaker, *topic_names, *keyword_names, *source_names])
    title_name_priority = _unique_names([speaker, *keyword_names, *topic_names, *source_names])

    table = poll_fact_table if isinstance(poll_fact_table, dict) else None
    if not table or not isinstance(table.get("pairs"), dict) or not table.get("pairs"):
        table = build_poll_matchup_fact_table(text_sources, known_names=seed_names)

    pairs = (table or {}).get("pairs") or {}
    if not speaker or not isinstance(pairs, dict) or not pairs:
        return {
            "scope": "",
            "speaker": speaker,
            "focusNames": seed_names,
            "titleNamePriority": title_name_priority,
            "titleNameRepeatLimit": 1,
            "primaryPair": {},
            "secondaryPairs": [],
            "primaryFactTemplate": {},
            "allowedTitleLanes": [],
            "allowedH2Kinds": [],
            "forbiddenMetrics": list(_FORBIDDEN_METRICS),
            "focusedSourceText": "",
        }

    focus_names = _unique_names(
        [speaker, *topic_names, *keyword_names, *source_names, *((table or {}).get("knownNames") or [])]
    )
    pair_candidates: List[tuple[tuple[int, int, float], Dict[str, Any]]] = []
    for raw_entry in pairs.values():
        entry = raw_entry if isinstance(raw_entry, dict) else {}
        left = _normalize_person_name(entry.get("left"))
        right = _normalize_person_name(entry.get("right"))
        if speaker not in {left, right}:
            continue
        normalized = _normalize_pair_record(entry, speaker)
        opponent = str(normalized.get("opponent") or "").strip()
        relevance = 0
        if opponent in topic_names:
            relevance += 6
        if opponent in keyword_names:
            relevance += 4
        if opponent in focus_names:
            relevance += 2
        sort_key = (
            relevance,
            len(normalized.get("records") or []),
            -float(normalized.get("margin") or 99.0),
        )
        pair_candidates.append((sort_key, normalized))

    if not pair_candidates:
        return {
            "scope": "",
            "speaker": speaker,
            "focusNames": focus_names,
            "titleNamePriority": title_name_priority,
            "titleNameRepeatLimit": 1,
            "primaryPair": {},
            "secondaryPairs": [],
            "primaryFactTemplate": {},
            "allowedTitleLanes": [],
            "allowedH2Kinds": [],
            "forbiddenMetrics": list(_FORBIDDEN_METRICS),
            "focusedSourceText": "",
        }

    pair_candidates.sort(key=lambda item: item[0], reverse=True)
    primary_pair = pair_candidates[0][1]
    secondary_pairs = [item[1] for item in pair_candidates[1:3]]

    primary_fact_template = {
        "sentence": _build_pair_fact_sentence(primary_pair),
        "heading": _build_pair_heading(primary_pair),
    }
    allowed_title_lanes = _build_title_lanes(primary_pair)
    allowed_h2_kinds = build_matchup_allowed_h2_kinds(primary_pair, secondary_pairs, speaker)

    focused_lines: List[str] = []
    if primary_fact_template["sentence"]:
        focused_lines.append(f"[주대결] {primary_fact_template['sentence']}")
    for pair in secondary_pairs:
        pair_fact = _build_pair_fact_sentence(pair)
        if pair_fact:
            focused_lines.append(f"[보조대결] {pair_fact}")
    focused_lines.append(
        "[제외통계] 정당 지지율, 당내 경선 수치, 후보 적합도는 제목과 주대결 설명의 중심으로 쓰지 않습니다."
    )

    return {
        "scope": "matchup",
        "speaker": speaker,
        "focusNames": focus_names,
        "titleNamePriority": title_name_priority,
        "titleNameRepeatLimit": 1,
        "primaryPair": primary_pair,
        "secondaryPairs": secondary_pairs,
        "primaryFactTemplate": primary_fact_template,
        "allowedTitleLanes": allowed_title_lanes,
        "allowedH2Kinds": allowed_h2_kinds,
        "forbiddenMetrics": list(_FORBIDDEN_METRICS),
        "focusedSourceText": "\n".join(line for line in focused_lines if line).strip(),
    }


__all__ = ["build_poll_focus_bundle"]
