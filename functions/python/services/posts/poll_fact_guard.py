"""여론조사 양자대결 수치 정합성 점검 유틸."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

_HTML_TAG_RE = re.compile(r"<[^>]*>")
_SPACE_RE = re.compile(r"\s+")
_PERCENT_RE = re.compile(r"(\d{1,2})\s*\.\s*(\d)\s*%")
_PAIR_RE = re.compile(
    r"([가-힣]{2,8})[^%\n]{0,120}?([0-9]{1,2}(?:\.[0-9])?)\s*%\s*(?:대|vs|VS|:)\s*([0-9]{1,2}(?:\.[0-9])?)\s*%[^가-힣\.\n]{0,20}([가-힣]{2,8})?",
    re.IGNORECASE,
)
_PAIR_WITH_AND_RE = re.compile(
    r"([가-힣]{2,8})[^가-힣\n]{0,8}(?:전\s*위원장|현\s*부산시장|부산시장|국회의원|의원)?\s*(?:과|와)\s*([가-힣]{2,8})[^%\n]{0,90}?([0-9]{1,2}(?:\.[0-9])?)\s*%\s*(?:대|vs|VS|:)\s*([0-9]{1,2}(?:\.[0-9])?)\s*%",
    re.IGNORECASE,
)
_SCORE_RE = re.compile(r"([0-9]{1,2}(?:\.[0-9])?)\s*%\s*(?:대|vs|VS|:)\s*([0-9]{1,2}(?:\.[0-9])?)\s*%")
_TITLE_MARGIN_RE = re.compile(
    r"(?P<margin>[0-9]{1,2}(?:\.[0-9])?)\s*%\s*(?:를|을)?\s*(?P<verb>"
    r"앞섰(?:나|는가|을까|을)?|앞서(?:나|는가|고)?|우세(?:였나|인가|일까)?|"
    r"밀렸(?:나|는가|을까|을)?|뒤졌(?:나|는가|을까|을)?|뒤진(?:건가|걸까)?|"
    r"이겼(?:나|는가|을까|을)?|졌(?:나|는가|을까|을)?|패했(?:나|는가|을까|을)?|"
    r"내줬(?:나|는가|을까|을)?|내준(?:건가|걸까)?"
    r")",
    re.IGNORECASE,
)
_LEADING_MARGIN_VERB_TOKENS = ("앞섰", "앞서", "우세", "이겼")
_TRAILING_MARGIN_VERB_TOKENS = ("밀렸", "뒤졌", "뒤진", "졌", "패했", "내줬", "내준")
_TITLE_PERCENT_RE = re.compile(r"([0-9]{1,2}(?:\.[0-9])?)\s*%")
_TITLE_CONTEST_CUE_PATTERN = re.compile(
    r"(?:가상대결|양자대결|대결|접전|승부|판세|앞섰|앞서|밀렸|내줬|우세|리드|가능성|경쟁력)",
    re.IGNORECASE,
)


def _normalize_text(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = _HTML_TAG_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text


def _normalize_name(value: object) -> str:
    name = re.sub(r"[^가-힣]", "", str(value or ""))
    if 2 <= len(name) <= 8:
        return name
    return ""


def _normalize_pair_key(left: str, right: str) -> str:
    names = sorted([left, right])
    return f"{names[0]}__{names[1]}"


def _normalize_decimal_percent(text: str) -> str:
    return _PERCENT_RE.sub(r"\1.\2%", str(text or ""))


@dataclass
class _PairRecord:
    left: str
    right: str
    left_score: float
    right_score: float
    source: str


def _to_float(value: str) -> float:
    try:
        return round(float(str(value or "").strip()), 1)
    except (TypeError, ValueError):
        return -1.0


def _extract_pair_records(text: str, *, known_names: set[str]) -> list[_PairRecord]:
    records: list[_PairRecord] = []
    if not text:
        return records

    for match in _PAIR_WITH_AND_RE.finditer(text):
        left = _normalize_name(match.group(1))
        right = _normalize_name(match.group(2))
        if not left or not right or left == right:
            continue
        if known_names and (left not in known_names or right not in known_names):
            continue
        left_score = _to_float(match.group(3))
        right_score = _to_float(match.group(4))
        if left_score < 0 or right_score < 0:
            continue
        records.append(
            _PairRecord(
                left=left,
                right=right,
                left_score=left_score,
                right_score=right_score,
                source=match.group(0),
            )
        )

    for match in _PAIR_RE.finditer(text):
        left = _normalize_name(match.group(1))
        right = _normalize_name(match.group(4))
        if not left:
            continue
        if not right:
            # 패턴상 우측 이름이 누락된 경우는 오탐 위험이 높아 수집하지 않는다.
            continue
        if left == right:
            continue
        if known_names and (left not in known_names or right not in known_names):
            continue
        left_score = _to_float(match.group(2))
        right_score = _to_float(match.group(3))
        if left_score < 0 or right_score < 0:
            continue
        records.append(
            _PairRecord(
                left=left,
                right=right,
                left_score=left_score,
                right_score=right_score,
                source=match.group(0),
            )
        )

    return records


def build_poll_matchup_fact_table(
    text_sources: Iterable[object],
    *,
    known_names: Iterable[object] | None = None,
) -> Dict[str, Any]:
    """입력 텍스트에서 양자대결 수치 테이블을 구성한다."""
    known_name_set = {
        normalized
        for normalized in (_normalize_name(item) for item in (known_names or []))
        if normalized
    }
    table: Dict[str, Dict[str, Any]] = {}

    for raw in text_sources or []:
        source_text = _normalize_decimal_percent(_normalize_text(raw))
        if not source_text:
            continue
        for record in _extract_pair_records(source_text, known_names=known_name_set):
            pair_key = _normalize_pair_key(record.left, record.right)
            current = table.get(pair_key)
            if current is None:
                table[pair_key] = {
                    "left": record.left,
                    "right": record.right,
                    "leftScore": record.left_score,
                    "rightScore": record.right_score,
                    "records": [record.source],
                }
                continue
            # 같은 pair_key가 이미 있을 때는 더 많이 등장한 수치를 우선.
            current_records = list(current.get("records") or [])
            current_records.append(record.source)
            current["records"] = current_records
            if (record.left == current.get("left")) and (record.right == current.get("right")):
                if current_records.count(record.source) >= 1:
                    current["leftScore"] = record.left_score
                    current["rightScore"] = record.right_score

    return {
        "pairs": table,
        "knownNames": sorted(known_name_set),
    }


def _score_signature(value_a: float, value_b: float) -> str:
    return f"{value_a:.1f}%대{value_b:.1f}%"


def _replace_first(text: str, before: str, after: str) -> str:
    index = text.find(before)
    if index < 0:
        return text
    return text[:index] + after + text[index + len(before) :]


def _resolve_title_margin_direction(verb: str) -> bool | None:
    normalized = str(verb or "").strip()
    if not normalized:
        return None
    if any(token in normalized for token in _LEADING_MARGIN_VERB_TOKENS):
        return True
    if any(token in normalized for token in _TRAILING_MARGIN_VERB_TOKENS):
        return False
    return None


def _repair_title_margin_phrase(
    text: str,
    *,
    left: str,
    right: str,
    left_score: float,
    right_score: float,
    full_name: str,
    pair_key: str,
) -> tuple[str, Dict[str, Any] | None, str]:
    normalized_text = str(text or "")
    speaker = _normalize_name(full_name)
    if not normalized_text or not speaker:
        return normalized_text, None, ""
    if speaker not in {left, right}:
        return normalized_text, None, ""
    if left not in normalized_text or right not in normalized_text:
        return normalized_text, None, ""

    margin_match = _TITLE_MARGIN_RE.search(normalized_text)
    if not margin_match:
        return normalized_text, None, ""

    speaker_score = left_score if speaker == left else right_score
    opponent = right if speaker == left else left
    opponent_score = right_score if speaker == left else left_score
    actual_margin = round(abs(speaker_score - opponent_score), 1)
    title_margin = _to_float(margin_match.group("margin"))
    title_direction = _resolve_title_margin_direction(margin_match.group("verb"))
    actual_direction = speaker_score > opponent_score

    if abs(title_margin - actual_margin) <= 0.05 and (
        title_direction is None or title_direction == actual_direction
    ):
        return normalized_text, None, ""

    replacement = f"{actual_margin:.1f}% {'앞섰나' if actual_direction else '밀렸나'}"
    updated_text = _replace_first(normalized_text, margin_match.group(0), replacement)
    if updated_text == normalized_text:
        issue = (
            f"{speaker}-{opponent} 대결 우열/격차 표현이 기준과 다릅니다 "
            f"(기준 {actual_margin:.1f}% {'우세' if actual_direction else '열세'}, 감지 {margin_match.group(0)})."
        )
        return normalized_text, None, issue

    repair = {
        "pair": pair_key,
        "reason": "제목 우열/격차 표현 보정",
        "before": margin_match.group(0),
        "after": replacement,
    }
    return updated_text, repair, ""


def _check_title_single_percent_binding(
    text: str,
    *,
    left: str,
    right: str,
    left_score: float,
    right_score: float,
) -> str:
    normalized_text = str(text or "")
    if not normalized_text:
        return ""
    if left not in normalized_text or right not in normalized_text:
        return ""
    if not _TITLE_CONTEST_CUE_PATTERN.search(normalized_text):
        return ""

    raw_percents = [
        _to_float(match.group(1))
        for match in _TITLE_PERCENT_RE.finditer(normalized_text)
    ]
    title_percents = [value for value in raw_percents if value >= 0]
    if not title_percents:
        return ""

    allowed_values = (
        round(left_score, 1),
        round(right_score, 1),
        round(abs(left_score - right_score), 1),
    )
    for detected in title_percents:
        if any(abs(detected - allowed) <= 0.05 for allowed in allowed_values):
            continue
        allowed_text = ", ".join(f"{value:.1f}%" for value in allowed_values)
        return (
            f"{left}-{right} 대결 문맥의 제목 수치 {detected:.1f}%가 입력 근거와 맞지 않습니다 "
            f"(허용: {allowed_text})."
        )
    return ""


def enforce_poll_fact_consistency(
    text: object,
    poll_fact_table: Dict[str, Any] | None,
    *,
    full_name: str = "",
    field: str = "content",
    allow_repair: bool = True,
) -> Dict[str, Any]:
    """본문/제목의 여론조사 수치 표기를 사실 테이블과 대조한다."""
    base_text = _normalize_decimal_percent(str(text or ""))
    result: Dict[str, Any] = {
        "text": base_text,
        "checked": 0,
        "edited": False,
        "blockingIssues": [],
        "warnings": [],
        "repairs": [],
    }

    pairs = (poll_fact_table or {}).get("pairs") or {}
    if not isinstance(pairs, dict) or not pairs:
        return result

    lowered_text = base_text
    for pair_key, row in pairs.items():
        if not isinstance(row, dict):
            continue
        left = _normalize_name(row.get("left"))
        right = _normalize_name(row.get("right"))
        left_score = _to_float(str(row.get("leftScore")))
        right_score = _to_float(str(row.get("rightScore")))
        if not left or not right or left_score < 0 or right_score < 0:
            continue

        canonical = _score_signature(left_score, right_score)
        reversed_sig = _score_signature(right_score, left_score)
        result["checked"] = int(result.get("checked") or 0) + 1

        if field == "title" and full_name:
            repaired_title, title_repair, title_issue = _repair_title_margin_phrase(
                lowered_text,
                left=left,
                right=right,
                left_score=left_score,
                right_score=right_score,
                full_name=full_name,
                pair_key=pair_key,
            )
            if title_repair:
                lowered_text = repaired_title
                result["edited"] = True
                result["repairs"].append(title_repair)
            elif title_issue:
                result["blockingIssues"].append(title_issue)

        if field == "title":
            single_percent_issue = _check_title_single_percent_binding(
                lowered_text,
                left=left,
                right=right,
                left_score=left_score,
                right_score=right_score,
            )
            if single_percent_issue:
                result["blockingIssues"].append(single_percent_issue)
                continue

        left_in = left in lowered_text
        right_in = right in lowered_text
        score_hits = list(_SCORE_RE.finditer(lowered_text))
        if not score_hits:
            continue

        for score_match in score_hits:
            score_sig = _score_signature(_to_float(score_match.group(1)), _to_float(score_match.group(2)))
            if score_sig == canonical:
                continue

            if score_sig == reversed_sig and left_in and right_in and allow_repair:
                before = score_match.group(0)
                after = f"{left_score:.1f}% 대 {right_score:.1f}%"
                replaced = _replace_first(lowered_text, before, after)
                if replaced != lowered_text:
                    lowered_text = replaced
                    result["edited"] = True
                    result["repairs"].append(
                        {
                            "pair": pair_key,
                            "reason": "여론조사 수치 순서 보정",
                            "before": before,
                            "after": after,
                        }
                    )
                continue

            issue = (
                f"{left}-{right} 대결 수치가 기준과 다릅니다"
                f" (기준 {left_score:.1f}% 대 {right_score:.1f}%, 감지 {score_sig})."
            )
            if field == "title":
                result["blockingIssues"].append(issue)
            else:
                result["warnings"].append(issue)

    result["text"] = lowered_text
    return result


__all__ = [
    "build_poll_matchup_fact_table",
    "enforce_poll_fact_consistency",
]
