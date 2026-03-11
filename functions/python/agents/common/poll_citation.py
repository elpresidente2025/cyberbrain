"""여론조사 조사개요 추출 및 표준화 유틸."""

from __future__ import annotations

import html
import re
from datetime import date, timedelta
from collections.abc import Iterable

_STOP_MARKERS: tuple[str, ...] = (
    "카테고리:",
    "검색어 삽입 횟수",
    "생성 시간:",
)

_POLL_MARKERS: tuple[str, ...] = (
    "조사개요",
    "조사 요약",
    "조사요약",
)

_POLL_HINTS: tuple[str, ...] = (
    "여론조사",
    "조사기관",
    "조사기간",
    "조사대상",
    "표본오차",
    "응답률",
    "무선 ars",
    "자동응답",
    "전화면접",
    "의뢰·",
    "조사(",
    "중앙선거여론조사심의위원회",
)

_DEFAULT_DISCLAIMER = "기타 자세한 사항은 중앙선거여론조사심의위원회 홈페이지 참조"

_REPORTER_SIGNOFF_RE = re.compile(
    r"^(?:(?:[A-Z]{2,6}|[가-힣A-Za-z]{2,16})\s+)?[가-힣]{2,4}(?:\s+기자)?입니다\.?$"
)
_COMPACT_POLL_RE = re.compile(r".+조사\s*\(.+\)")
_AGENCY_FIELD_RE = re.compile(r"(?:조사기관|의뢰기관|의뢰|기관)\s*[:|]\s*(.+)", re.IGNORECASE)
_PERIOD_FIELD_RE = re.compile(r"(?:조사기간|기간|조사일시)\s*[:|]\s*(.+)", re.IGNORECASE)
_TARGET_FIELD_RE = re.compile(r"(?:조사대상|대상)\s*[:|]\s*(.+)", re.IGNORECASE)
_SAMPLE_FIELD_RE = re.compile(r"(?:표본수|표본크기|표본)\s*[:|]\s*(.+)", re.IGNORECASE)
_METHOD_FIELD_RE = re.compile(r"(?:조사방법|조사방식|방법)\s*[:|]\s*(.+)", re.IGNORECASE)
_MARGIN_FIELD_RE = re.compile(r"(?:표본오차|오차범위)\s*[:|]\s*(.+)", re.IGNORECASE)
_RESPONSE_FIELD_RE = re.compile(r"(?:응답률)\s*[:|]\s*(.+)", re.IGNORECASE)
_AGENCY_NARRATIVE_RE = re.compile(
    r"(?P<client>[가-힣A-Za-z0-9()·&]+?)이\s+(?P<org>[가-힣A-Za-z0-9()·&]+?)에\s+의뢰해",
    re.IGNORECASE,
)
_PERIOD_NARRATIVE_RE = re.compile(
    r"(?:(?P<year>\d{4})년\s*)?(?:(?P<month>\d{1,2})월\s*)?"
    r"(?P<start>\d{1,2})일(?:과|와|~|-)\s*(?:(?P<end_month>\d{1,2})월\s*)?(?P<end>\d{1,2})일",
    re.IGNORECASE,
)
_TARGET_SAMPLE_NARRATIVE_RE = re.compile(
    r"(?P<target>(?:[\uac00-\ud7a3\s]{1,40}?\uc5d0\s*거주하고\s*있는\s+)?만\s*18세\s*이상[^.\n]{0,100}?)\s*(?P<sample>\d{1,3}(?:,\d{3})*)명",
    re.IGNORECASE,
)
_METHOD_NARRATIVE_RE = re.compile(
    r"(무선\s*ARS\s*자동응답\s*방식|무선\s*ARS|자동응답\s*방식|전화면접\s*방식|전화면접)",
    re.IGNORECASE,
)
_MARGIN_NARRATIVE_RE = re.compile(
    r"(?P<sig>\d{2,3}\s*%\s*신뢰수준)[^\d±]*?(?P<margin>±\s*\d+(?:\.\d+)?\s*(?:%p|포인트))",
    re.IGNORECASE,
)
_RESPONSE_NARRATIVE_RE = re.compile(r"응답률(?:은|는)?\s*[: ]?\s*(?P<rate>\d+(?:\.\d+)?%)", re.IGNORECASE)
_TARGET_ANCHOR_RE = re.compile(
    r"(?:[\uac00-\ud7a3\s]{1,40}?\uc5d0\s*거주하고\s*있는\s+)?만\s*18세\s*이상",
    re.IGNORECASE,
)
_REFERENCE_DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?:입력|등록|작성|수정)\s*[:：]?\s*(?P<year>\d{4})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:입력|등록|작성|수정)\s*[:：]?\s*(?P<year>\d{4})년\s*(?P<month>\d{1,2})월\s*(?P<day>\d{1,2})일",
        re.IGNORECASE,
    ),
)


def _normalize_text(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_line(line: object) -> str:
    normalized = re.sub(r"\s+", " ", str(line or "")).strip(" ,")
    normalized = normalized.replace(" ,", ",").replace("( ", "(").replace(" )", ")")
    normalized = normalized.replace(" .", ".")
    normalized = normalized.replace(" · ", "·").replace("· ", "·").replace(" ·", "·")
    normalized = re.sub(r"\s*%p", "%p", normalized)
    return normalized.strip()


def _iter_normalized_sources(*sources: object) -> Iterable[str]:
    seen: set[str] = set()
    for item in _iter_source_values(*sources):
        normalized = _normalize_text(item)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        yield normalized


def _extract_after_marker(text: str, marker: str) -> str:
    if not text or not marker:
        return ""
    idx = text.find(marker)
    if idx < 0:
        return ""

    body = text[idx + len(marker) :].lstrip(" :")
    if not body:
        return ""

    cut = len(body)
    for stop in _STOP_MARKERS:
        stop_idx = body.find(stop)
        if 0 <= stop_idx < cut:
            cut = stop_idx
    return body[:cut].strip()


def _dedupe_lines(lines: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for line in lines:
        normalized = _normalize_line(line)
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return result


def _should_drop_poll_line(line: str) -> bool:
    normalized = _normalize_line(line)
    if not normalized:
        return True
    if _REPORTER_SIGNOFF_RE.fullmatch(normalized):
        return True
    if normalized in {"조사개요", "조사 요약", "조사요약"}:
        return True
    return False


def _iter_source_values(*sources: object) -> Iterable[object]:
    for source in sources:
        if source is None:
            continue
        if isinstance(source, (str, bytes, bytearray)):
            yield source
            continue
        if isinstance(source, Iterable):
            for item in source:
                if item is not None:
                    yield item
            continue
        yield source


def _extract_candidate_lines(*sources: object) -> list[str]:
    normalized_sources = list(_iter_normalized_sources(*sources))
    if not normalized_sources:
        return []

    candidate_lines: list[str] = []
    for source in normalized_sources:
        for marker in _POLL_MARKERS:
            extracted = _extract_after_marker(source, marker)
            if not extracted:
                continue
            candidate_lines.extend(
                line
                for line in _dedupe_lines(extracted.splitlines())
                if not _should_drop_poll_line(line)
            )
        for line in source.splitlines():
            normalized = _normalize_line(line)
            if not normalized or _should_drop_poll_line(normalized):
                continue
            if _looks_like_poll_detail_line(normalized):
                candidate_lines.append(normalized)
    return _dedupe_lines(candidate_lines)


def _normalize_sample_text(value: str) -> str:
    normalized = _normalize_line(value)
    normalized = re.sub(r"(?<=\d),(?=\d)", "", normalized)
    normalized = normalized.replace(" 명", "명")
    if re.fullmatch(r"\d+", normalized):
        return f"{normalized}명"
    return normalized


def _normalize_target_text(value: str) -> str:
    normalized = _normalize_line(value)
    anchor = _TARGET_ANCHOR_RE.search(normalized)
    if anchor:
        normalized = normalized[anchor.start() :].strip()
    normalized = re.sub(r"\s*을\s*대상(?:으로)?(?:\s*실시[^\n.]*)?$", "", normalized)
    normalized = re.sub(r"\s*를\s*대상(?:으로)?(?:\s*실시[^\n.]*)?$", "", normalized)
    normalized = normalized.rstrip("은는이가을를")
    return normalized.strip(" ,")


def _normalize_margin_text(value: str) -> str:
    normalized = _normalize_line(value).replace("퍼센트포인트", "%p").replace("포인트", "%p")
    normalized = re.sub(r"\s*%p", "%p", normalized)
    return normalized


def _extract_field_value(lines: list[str], pattern: re.Pattern[str]) -> str:
    for line in lines:
        match = pattern.search(line)
        if not match:
            continue
        value = _normalize_line(match.group(1))
        if value:
            return value
    return ""


def _looks_like_poll_detail_line(line: str) -> bool:
    normalized = _normalize_line(line)
    if not normalized:
        return False
    lowered = normalized.lower()
    if _COMPACT_POLL_RE.fullmatch(normalized):
        return True
    if any(hint in lowered for hint in _POLL_HINTS):
        return True
    return any(
        pattern.search(normalized)
        for pattern in (
            _AGENCY_FIELD_RE,
            _PERIOD_FIELD_RE,
            _TARGET_FIELD_RE,
            _SAMPLE_FIELD_RE,
            _METHOD_FIELD_RE,
            _MARGIN_FIELD_RE,
            _RESPONSE_FIELD_RE,
            _AGENCY_NARRATIVE_RE,
            _PERIOD_NARRATIVE_RE,
            _TARGET_SAMPLE_NARRATIVE_RE,
            _METHOD_NARRATIVE_RE,
            _MARGIN_NARRATIVE_RE,
            _RESPONSE_NARRATIVE_RE,
        )
    )


def _extract_agency(lines: list[str]) -> str:
    field_value = _extract_field_value(lines, _AGENCY_FIELD_RE)
    if field_value:
        normalized = re.sub(r"\s+", " ", field_value).strip()
        if "조사" not in normalized:
            normalized = f"{normalized} 조사"
        return normalized

    for line in lines:
        match = _AGENCY_NARRATIVE_RE.search(line)
        if not match:
            continue
        client = _normalize_line(match.group("client")).rstrip("은는이가")
        org = _normalize_line(match.group("org")).rstrip("은는이가")
        if client and org:
            return f"{client} 의뢰·{org} 조사"
    return ""


def _extract_reference_date(*sources: object) -> date | None:
    for source in _iter_normalized_sources(*sources):
        for line in source.splitlines():
            normalized = _normalize_line(line)
            if not normalized:
                continue
            for pattern in _REFERENCE_DATE_PATTERNS:
                match = pattern.search(normalized)
                if not match:
                    continue
                try:
                    return date(
                        int(match.group("year")),
                        int(match.group("month")),
                        int(match.group("day")),
                    )
                except Exception:
                    continue
    return None


def _format_period_text(
    *,
    year: int | None,
    start_month: int | None,
    start_day: int,
    end_month: int | None,
    end_day: int,
) -> str:
    left_parts: list[str] = []
    if year:
        left_parts.append(f"{year}년")
    if start_month:
        left_parts.append(f"{start_month}월")
    left_parts.append(f"{start_day}일")
    left = " ".join(left_parts)
    if end_month and start_month and end_month != start_month:
        right = f"{end_month}월 {end_day}일"
    elif end_month and not start_month:
        right = f"{end_month}월 {end_day}일"
    else:
        right = f"{end_day}일"
    return f"{left}~{right}"


def _resolve_period_text(value: str, *, reference_date: date | None = None) -> str:
    normalized_value = _normalize_line(value)
    if not normalized_value:
        return ""

    match = _PERIOD_NARRATIVE_RE.search(normalized_value)
    if not match:
        return normalized_value

    raw_year = str(match.group("year") or "").strip()
    raw_month = str(match.group("month") or "").strip()
    raw_start = str(match.group("start") or "").strip()
    raw_end_month = str(match.group("end_month") or "").strip()
    raw_end = str(match.group("end") or "").strip()
    if not raw_start or not raw_end:
        return normalized_value

    year_num = int(raw_year) if raw_year else None
    start_month_num = int(raw_month) if raw_month else None
    end_month_num = int(raw_end_month) if raw_end_month else None
    start_day = int(raw_start)
    end_day = int(raw_end)

    if reference_date:
        if start_month_num is None and end_month_num is None:
            inferred = reference_date
            if max(start_day, end_day) > reference_date.day:
                inferred = reference_date.replace(day=1) - timedelta(days=1)
            year_num = inferred.year
            start_month_num = inferred.month
            end_month_num = inferred.month
        elif start_month_num is not None and year_num is None:
            year_num = reference_date.year
            if start_month_num > reference_date.month:
                year_num -= 1
            if end_month_num is None:
                end_month_num = start_month_num
        elif start_month_num is None and end_month_num is not None:
            base_year = year_num or reference_date.year
            if end_month_num > reference_date.month:
                base_year -= 1
            year_num = base_year
            if start_day > end_day:
                previous_month_anchor = date(base_year, end_month_num, 1) - timedelta(days=1)
                start_month_num = previous_month_anchor.month
                year_num = previous_month_anchor.year
            else:
                start_month_num = end_month_num

    return _format_period_text(
        year=year_num,
        start_month=start_month_num,
        start_day=start_day,
        end_month=end_month_num,
        end_day=end_day,
    )


def _extract_period(lines: list[str], *sources: object) -> str:
    reference_date = _extract_reference_date(*sources)
    field_value = _extract_field_value(lines, _PERIOD_FIELD_RE)
    if field_value:
        return _resolve_period_text(field_value, reference_date=reference_date)

    for line in lines:
        resolved = _resolve_period_text(line, reference_date=reference_date)
        if resolved and resolved != _normalize_line(line):
            return resolved
    return ""


def _extract_target_and_sample(lines: list[str]) -> tuple[str, str]:
    target = _extract_field_value(lines, _TARGET_FIELD_RE)
    sample = _extract_field_value(lines, _SAMPLE_FIELD_RE)

    if target and sample:
        return _normalize_target_text(target), _normalize_sample_text(sample)

    for line in lines:
        match = _TARGET_SAMPLE_NARRATIVE_RE.search(line)
        if not match:
            continue
        target = _normalize_target_text(match.group("target"))
        sample = _normalize_sample_text(match.group("sample"))
        if target and sample:
            return target, sample

    return _normalize_target_text(target), _normalize_sample_text(sample)


def _extract_method(lines: list[str]) -> str:
    field_value = _extract_field_value(lines, _METHOD_FIELD_RE)
    if field_value:
        return field_value
    for line in lines:
        match = _METHOD_NARRATIVE_RE.search(line)
        if match:
            return _normalize_line(match.group(1))
    return ""


def _extract_margin(lines: list[str]) -> str:
    field_value = _extract_field_value(lines, _MARGIN_FIELD_RE)
    if field_value:
        return _normalize_margin_text(field_value)

    for line in lines:
        match = _MARGIN_NARRATIVE_RE.search(line)
        if not match:
            continue
        sig = _normalize_line(match.group("sig"))
        margin = _normalize_margin_text(match.group("margin"))
        return f"{sig} {margin}".strip()
    return ""


def _extract_response(lines: list[str]) -> str:
    field_value = _extract_field_value(lines, _RESPONSE_FIELD_RE)
    if field_value:
        return f"응답률 {field_value}".strip()
    for line in lines:
        match = _RESPONSE_NARRATIVE_RE.search(line)
        if match:
            return f"응답률 {_normalize_line(match.group('rate'))}"
    return ""


def _extract_disclaimer(lines: list[str]) -> str:
    for line in lines:
        normalized = _normalize_line(line)
        if "중앙선거여론조사심의위원회" in normalized:
            return normalized
    return _DEFAULT_DISCLAIMER


def _build_standard_summary(lines: list[str], *sources: object) -> str:
    for line in lines:
        normalized = _normalize_line(line)
        if _COMPACT_POLL_RE.fullmatch(normalized):
            return normalized

    agency = _extract_agency(lines)
    period = _extract_period(lines, *sources)
    target, sample = _extract_target_and_sample(lines)
    method = _extract_method(lines)
    margin = _extract_margin(lines)
    response = _extract_response(lines)

    if not agency:
        return ""

    parts = [item for item in (period, target, sample, method, margin, response) if item]
    if not parts:
        return agency
    return f"{agency}({', '.join(parts)})"


def normalize_poll_citation_text(*sources: object) -> str:
    lines = _extract_candidate_lines(*sources)
    if not lines:
        return ""

    compact_line = _build_standard_summary(lines, *sources)
    disclaimer = _extract_disclaimer(lines)

    if compact_line:
        return f"{compact_line}\n{disclaimer}".strip()

    fallback_lines = [line for line in lines if not _should_drop_poll_line(line)]
    if not fallback_lines:
        return ""
    if disclaimer not in fallback_lines:
        fallback_lines.append(disclaimer)
    return "\n".join(fallback_lines[:4]).strip()[:900].strip()


def build_poll_citation_text(*sources: object) -> str:
    """입력 텍스트에서 조사개요를 추출해 표준 2줄 형식으로 반환."""
    return normalize_poll_citation_text(*sources)


__all__ = ["build_poll_citation_text", "normalize_poll_citation_text"]
