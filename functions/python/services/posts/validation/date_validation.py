"""??/?? ?? ????."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

WEEKDAY_SHORT_TOKENS = ("월", "화", "수", "목", "금", "토", "일")
WEEKDAY_FULL_TOKENS = tuple(f"{token}요일" for token in WEEKDAY_SHORT_TOKENS)
WEEKDAY_TOKEN_PATTERN = r"(?:월|화|수|목|금|토|일)(?:요일)?"
DATE_WEEKDAY_PATTERN = re.compile(
    rf"(?:(?P<year>\d{{4}})\s*년\s*)?"
    rf"(?P<month>\d{{1,2}})\s*월\s*"
    rf"(?P<day>\d{{1,2}})\s*일"
    rf"\s*"
    rf"(?:"
    rf"(?P<open>[\(\[])\s*(?P<weekday_bracket>{WEEKDAY_TOKEN_PATTERN})\s*(?P<close>[\)\]])"
    rf"|"
    rf"(?P<weekday_text>{'|'.join(WEEKDAY_FULL_TOKENS)})"
    rf")"
)

def _normalize_weekday_token(token: str) -> str:
    raw = str(token or "").strip()
    if raw.endswith("요일"):
        raw = raw[:-2]
    return raw if raw in WEEKDAY_SHORT_TOKENS else ""


def _resolve_year_hint(year_hint: Any) -> Optional[int]:
    if isinstance(year_hint, int):
        return year_hint if 1900 <= year_hint <= 9999 else None
    if isinstance(year_hint, (datetime, date)):
        return int(year_hint.year)
    if year_hint is None:
        return None
    text = str(year_hint).strip()
    if not text:
        return None
    match = re.search(r"(19|20)\d{2}", text)
    if not match:
        return None
    return int(match.group(0))


def _weekday_short_from_date(target_date: date) -> str:
    return WEEKDAY_SHORT_TOKENS[target_date.weekday()]


def _render_weekday_for_style(short_token: str, original_token: str) -> str:
    original = str(original_token or "").strip()
    if original.endswith("요일"):
        return f"{short_token}요일"
    return short_token


def extract_date_weekday_pairs(text: str) -> List[Dict[str, Any]]:
    source = str(text or "")
    if not source:
        return []

    pairs: List[Dict[str, Any]] = []
    for match in DATE_WEEKDAY_PATTERN.finditer(source):
        year_raw = match.group("year")
        month_raw = match.group("month")
        day_raw = match.group("day")
        weekday_token = match.group("weekday_bracket") or match.group("weekday_text") or ""
        if not weekday_token:
            continue

        token_group = "weekday_bracket" if match.group("weekday_bracket") else "weekday_text"
        token_start = match.start(token_group)
        token_end = match.end(token_group)

        try:
            month = int(month_raw)
            day = int(day_raw)
        except Exception:
            continue

        pairs.append(
            {
                "raw": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "tokenStart": token_start,
                "tokenEnd": token_end,
                "year": int(year_raw) if year_raw else None,
                "month": month,
                "day": day,
                "weekdayToken": weekday_token,
                "weekdayShort": _normalize_weekday_token(weekday_token),
            }
        )

    return pairs


def validate_date_weekday_pairs(text: str, year_hint: Any = None) -> Dict[str, Any]:
    source = str(text or "")
    pairs = extract_date_weekday_pairs(source)
    if not pairs:
        return {"passed": True, "issues": [], "pairs": [], "checkedCount": 0}

    issues: List[Dict[str, Any]] = []
    hint_year = _resolve_year_hint(year_hint)
    fallback_year = hint_year or int(datetime.now().year)

    for pair in pairs:
        month = int(pair.get("month") or 0)
        day = int(pair.get("day") or 0)
        resolved_year = int(pair.get("year") or fallback_year)
        weekday_token = str(pair.get("weekdayToken") or "")
        weekday_short = str(pair.get("weekdayShort") or "")
        date_label = (
            f"{resolved_year}년 {month}월 {day}일"
            if pair.get("year")
            else f"{month}월 {day}일"
        )

        try:
            target_date = date(resolved_year, month, day)
        except ValueError:
            issues.append(
                {
                    "type": "invalid_date",
                    "dateText": date_label,
                    "resolvedYear": resolved_year,
                    "weekdayToken": weekday_token,
                    "message": f"유효하지 않은 날짜입니다: {date_label}",
                    "start": pair.get("start"),
                    "end": pair.get("end"),
                    "tokenStart": pair.get("tokenStart"),
                    "tokenEnd": pair.get("tokenEnd"),
                }
            )
            continue

        expected_short = _weekday_short_from_date(target_date)
        if weekday_short != expected_short:
            expected_token = _render_weekday_for_style(expected_short, weekday_token)
            issues.append(
                {
                    "type": "date_weekday_mismatch",
                    "dateText": date_label,
                    "resolvedYear": resolved_year,
                    "expectedWeekday": expected_token,
                    "expectedWeekdayShort": expected_short,
                    "foundWeekday": weekday_token,
                    "message": f"{date_label}의 실제 요일은 {expected_token}입니다.",
                    "start": pair.get("start"),
                    "end": pair.get("end"),
                    "tokenStart": pair.get("tokenStart"),
                    "tokenEnd": pair.get("tokenEnd"),
                }
            )

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "pairs": pairs,
        "checkedCount": len(pairs),
        "yearHint": hint_year,
    }


def repair_date_weekday_pairs(text: str, year_hint: Any = None) -> Dict[str, Any]:
    source = str(text or "")
    if not source:
        return {
            "text": source,
            "edited": False,
            "changes": [],
            "validation": {"passed": True, "issues": [], "pairs": [], "checkedCount": 0},
        }

    validation = validate_date_weekday_pairs(source, year_hint=year_hint)
    issues = validation.get("issues") if isinstance(validation, dict) else []
    if not isinstance(issues, list):
        issues = []

    replacements: List[Dict[str, Any]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        if str(issue.get("type") or "") != "date_weekday_mismatch":
            continue
        token_start = issue.get("tokenStart")
        token_end = issue.get("tokenEnd")
        expected = str(issue.get("expectedWeekday") or "").strip()
        found = str(issue.get("foundWeekday") or "").strip()
        if not isinstance(token_start, int) or not isinstance(token_end, int):
            continue
        if token_start < 0 or token_end <= token_start:
            continue
        if not expected or expected == found:
            continue
        replacements.append(
            {
                "start": token_start,
                "end": token_end,
                "from": found,
                "to": expected,
                "dateText": str(issue.get("dateText") or "").strip(),
                "resolvedYear": issue.get("resolvedYear"),
            }
        )

    if not replacements:
        return {
            "text": source,
            "edited": False,
            "changes": [],
            "validation": validation,
        }

    repaired = source
    for item in sorted(replacements, key=lambda x: int(x["start"]), reverse=True):
        start = int(item["start"])
        end = int(item["end"])
        repaired = repaired[:start] + str(item["to"]) + repaired[end:]

    return {
        "text": repaired,
        "edited": repaired != source,
        "changes": replacements,
        "validation": validate_date_weekday_pairs(repaired, year_hint=year_hint),
    }
