"""원고 품질/선거법/키워드 휴리스틱 검증 모듈.

Node.js `functions/services/posts/validation.js`의 핵심 검증 로직 포팅.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from agents.common.election_rules import get_election_stage
from agents.common.fact_guard import extract_numeric_tokens, find_unsupported_numeric_tokens
from agents.common.legal import ViolationDetector

from .corrector import apply_corrections, summarize_violations
from .critic import has_hard_violations, run_critic_review, summarize_guidelines
from .generation_stages import GENERATION_STAGES, create_progress_state, create_retry_message
from .keyword_insertion_policy import (
    LOCATION_CONTEXT_TOKENS,
    SENTENCE_FOCUS_TOKENS,
    UNSAFE_LOCATION_ATTACH_TOKENS,
    UNSAFE_LOCATION_CONTEXT_TOKENS,
    is_location_context_text as _policy_is_location_context_text,
    is_greeting_sentence as _policy_is_greeting_sentence,
    is_terminal_sentence as _policy_is_terminal_sentence,
    is_unsafe_location_context as _policy_is_unsafe_location_context,
    normalize_plain as _policy_normalize_plain,
)

logger = logging.getLogger(__name__)

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


# ============================================================================
# 선거법 하이브리드 검증 상수
# ============================================================================

ALLOWED_ENDINGS: List[re.Pattern[str]] = [
    re.compile(r"입니다\.?$"),
    re.compile(r"습니다\.?$"),
    re.compile(r"됩니다\.?$"),
    re.compile(r"했습니다\.?$"),
    re.compile(r"되었습니다\.?$"),
    re.compile(r"였습니다\.?$"),
    re.compile(r"었습니다\.?$"),
    re.compile(r"해야\s*합니다\.?$"),
    re.compile(r"되어야\s*합니다\.?$"),
    re.compile(r"필요합니다\.?$"),
    re.compile(r"바랍니다\.?$"),
    re.compile(r"생각합니다\.?$"),
    re.compile(r"봅니다\.?$"),
    re.compile(r"압니다\.?$"),
    re.compile(r"느낍니다\.?$"),
    re.compile(r"[까요까]\?$"),
    re.compile(r"[습읍]니까\?$"),
    re.compile(r"라고\s*합니다\.?$"),
    re.compile(r"답니다\.?$"),
]

EXPLICIT_PLEDGE_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"약속드립니다"),
    re.compile(r"약속합니다"),
    re.compile(r"공약합니다"),
    re.compile(r"반드시.*하겠습니다"),
    re.compile(r"꼭.*하겠습니다"),
    re.compile(r"제가.*하겠습니다"),
    re.compile(r"저는.*하겠습니다"),
    re.compile(r"당선되면"),
    re.compile(r"당선\s*후"),
]


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", text or "")).strip()


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


def extract_sentences(text: str) -> List[str]:
    plain_text = _strip_html(text)
    if not plain_text:
        return []
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.?!])\s+", plain_text)
        if sentence and len(sentence.strip()) > 10
    ]


def is_allowed_ending(sentence: str) -> bool:
    return any(pattern.search(sentence or "") for pattern in ALLOWED_ENDINGS)


def is_explicit_pledge(sentence: str) -> bool:
    return any(pattern.search(sentence or "") for pattern in EXPLICIT_PLEDGE_PATTERNS)


def contains_pledge_candidate(sentence: str) -> bool:
    return bool(re.search(r"겠[습어]", sentence or ""))


def _extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    text = (raw or "").strip()
    if not text:
        return None
    text = re.sub(r"```(?:json)?\s*([\s\S]*?)```", r"\1", text).strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


async def check_pledges_with_llm(
    sentences: Sequence[str],
    model_name: str = "gemini-2.5-flash",
) -> List[Dict[str, Any]]:
    if not sentences:
        return []

    prompt = f"""당신은 대한민국 선거법 전문가입니다.
아래 문장들이 "정치인 본인의 선거 공약/약속"인지 판단하세요.

[판단 기준]
- 공약 O: 정치인 본인이 주어로, 미래에 ~하겠다는 약속
  예: "일자리를 만들겠습니다", "교통 문제를 해결하겠습니다"

- 공약 X: 다음은 공약이 아님
  예: "비가 오겠습니다" (날씨 예측)
  예: "좋은 결과가 있겠습니다" (희망/기대)
  예: "정부가 해야겠습니다" (제3자 당위)
  예: "함께 만들어가겠습니다" (시민 참여 호소, 맥락에 따라)

[검증 대상 문장]
{chr(10).join(f'{i + 1}. "{s}"' for i, s in enumerate(sentences))}

[출력 형식 - JSON]
{{
  "results": [
    {{ "index": 1, "isPledge": true/false, "reason": "판단 근거" }},
    ...
  ]
}}"""

    try:
        from agents.common.gemini_client import generate_content_async

        response = await generate_content_async(
            prompt,
            model_name=model_name,
            temperature=0.1,
            response_mime_type="application/json",
        )
        parsed = _extract_json_object(response) or {}
        results = parsed.get("results")
        if not isinstance(results, list):
            raise ValueError("results 필드 없음")

        normalized: list[Dict[str, Any]] = []
        for idx, item in enumerate(results):
            if not isinstance(item, dict):
                continue
            item_index = int(item.get("index", idx + 1))
            source_idx = max(1, item_index) - 1
            sentence = sentences[source_idx] if source_idx < len(sentences) else sentences[idx]
            normalized.append(
                {
                    "sentence": sentence,
                    "isPledge": bool(item.get("isPledge")),
                    "reason": str(item.get("reason") or "판단 근거 없음"),
                }
            )
        return normalized
    except Exception as exc:
        logger.warning("LLM 공약 검증 실패, 보수적 처리: %s", exc)
        return [
            {"sentence": sentence, "isPledge": True, "reason": "LLM 검증 실패 - 보수적 처리"}
            for sentence in sentences
        ]


def _collect_bribery_violations(plain_text: str) -> List[Dict[str, Any]]:
    violations: list[Dict[str, Any]] = []
    for item in ViolationDetector.check_bribery_risk(plain_text):
        matches = item.get("matches") or []
        sentence = matches[0] if matches else ""
        violations.append(
            {
                "sentence": sentence,
                "type": "BRIBERY",
                "reason": item.get("reason") or "기부행위 금지 위반 위험",
            }
        )
    return violations


def _collect_fact_violations(plain_text: str) -> List[Dict[str, Any]]:
    violations: list[Dict[str, Any]] = []
    for item in ViolationDetector.check_fact_claims(plain_text):
        matches = item.get("matches") or item.get("claims") or []
        sentence = matches[0] if matches else ""
        severity = str(item.get("severity") or "").upper()
        violations.append(
            {
                "sentence": sentence,
                "type": "FACT_CRITICAL" if severity == "CRITICAL" else "FACT_WARNING",
                "reason": item.get("reason") or "허위사실/비방 위험",
            }
        )
    return violations


async def detect_election_law_violation_hybrid(
    content: str,
    status: str | None,
    title: str = "",
    *,
    model_name: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    if not status:
        return {"passed": True, "violations": [], "skipped": True}

    election_stage = get_election_stage(status)
    if not election_stage or election_stage.get("name") != "STAGE_1":
        return {"passed": True, "violations": [], "skipped": True}

    full_text = f"{title or ''} {content or ''}"
    sentences = extract_sentences(full_text)
    violations: list[Dict[str, Any]] = []
    llm_candidates: list[str] = []

    for sentence in sentences:
        if is_explicit_pledge(sentence):
            violations.append(
                {
                    "sentence": sentence[:60] + ("..." if len(sentence) > 60 else ""),
                    "type": "EXPLICIT_PLEDGE",
                    "reason": "명시적 공약 표현",
                }
            )
            continue
        if is_allowed_ending(sentence):
            continue
        if contains_pledge_candidate(sentence):
            llm_candidates.append(sentence)

    if llm_candidates:
        llm_results = await check_pledges_with_llm(llm_candidates, model_name=model_name)
        for result in llm_results:
            if result.get("isPledge"):
                sentence = str(result.get("sentence") or "")
                violations.append(
                    {
                        "sentence": sentence[:60] + ("..." if len(sentence) > 60 else ""),
                        "type": "LLM_DETECTED",
                        "reason": str(result.get("reason") or "공약성 표현"),
                    }
                )

    plain_text = _strip_html(full_text)
    violations.extend(_collect_bribery_violations(plain_text))
    violations.extend(_collect_fact_violations(plain_text))

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "status": status,
        "stage": election_stage.get("name"),
        "stats": {
            "totalSentences": len(sentences),
            "llmChecked": len(llm_candidates),
            "violationCount": len(violations),
        },
    }


# ============================================================================
# 휴리스틱 품질 검증
# ============================================================================


def detect_sentence_repetition(content: str) -> Dict[str, Any]:
    plain_text = _strip_html(content)
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.?!])\s+", plain_text)
        if sentence and len(sentence.strip()) > 20
    ]
    normalized = [re.sub(r"\s+", "", sentence).lower() for sentence in sentences]
    counts: Dict[str, Dict[str, Any]] = {}
    repeated_sentences: list[str] = []

    for idx, sentence in enumerate(normalized):
        if sentence not in counts:
            counts[sentence] = {"count": 0, "original": sentences[idx]}
        counts[sentence]["count"] += 1

    for value in counts.values():
        if value["count"] >= 2:
            original = str(value["original"])
            repeated_sentences.append(f"\"{original[:50]}...\" ({value['count']}회 반복)")

    return {"passed": len(repeated_sentences) == 0, "repeatedSentences": repeated_sentences}


def detect_phrase_repetition(content: str) -> Dict[str, Any]:
    plain_text = _strip_html(content)
    words = [word for word in re.split(r"\s+", plain_text) if word]
    phrase_count: Dict[str, int] = {}

    for n in range(3, 7):
        for idx in range(0, len(words) - n + 1):
            phrase = " ".join(words[idx : idx + n])
            if len(phrase) < 10:
                continue
            phrase_count[phrase] = phrase_count.get(phrase, 0) + 1

    over_limit = sorted(
        [(phrase, count) for phrase, count in phrase_count.items() if count >= 3],
        key=lambda item: len(item[0]),
        reverse=True,
    )

    covered: set[str] = set()
    repeated_phrases: list[str] = []
    raw_repeated_phrases: list[Dict[str, Any]] = []
    for phrase, count in over_limit:
        if any(existing.find(phrase) >= 0 for existing in covered):
            continue
        covered.add(phrase)
        repeated_phrases.append(f"\"{phrase[:40]}{'...' if len(phrase) > 40 else ''}\" ({count}회 반복)")
        raw_repeated_phrases.append({"phrase": phrase, "count": count})

    return {
        "passed": len(repeated_phrases) == 0,
        "repeatedPhrases": repeated_phrases,
        "rawRepeatedPhrases": raw_repeated_phrases,
    }


def _replace_repetition_tail(
    content: str,
    pattern: re.Pattern[str],
    *,
    keep: int = 2,
) -> tuple[str, int]:
    """패턴 반복이 keep회를 초과하면 뒤에서부터 변형 치환한다."""
    matches = list(pattern.finditer(content or ""))
    if len(matches) <= keep:
        return str(content or ""), 0

    working = str(content or "")
    replaced = 0
    to_replace = list(reversed(matches[keep:]))
    for idx, match in enumerate(to_replace):
        phrase = match.group(0)
        time_match = re.search(r"(오전|오후)\s*\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?", phrase)
        time_token = time_match.group(0) if time_match else "해당 시간"
        location_match = re.search(r"(서면|부산)\s*영광도서", phrase)
        location_token = location_match.group(0) if location_match else "행사 현장"
        replacement = (
            f"행사 당일 {time_token}, {location_token} 현장에서"
            if idx == 0
            else "행사 당일 현장에서"
        )
        start, end = match.span()
        working = working[:start] + replacement + working[end:]
        replaced += 1

    return working, replaced


def _replace_location_postposition_repetition(
    content: str,
    pattern: re.Pattern[str],
    *,
    keep: int = 2,
) -> tuple[str, int]:
    """장소+조사(…영광도서에서) 반복을 변형해 동일 n-gram을 줄인다."""
    matches = list(pattern.finditer(content or ""))
    if len(matches) <= keep:
        return str(content or ""), 0

    working = str(content or "")
    replaced = 0
    suffixes = ("현장에서", "행사장에서", "공간에서")
    to_replace = list(reversed(matches[keep:]))

    for idx, match in enumerate(to_replace):
        phrase = match.group(0)
        city_match = re.search(r"(서면|부산)\s*영광도서", phrase, re.IGNORECASE)
        location_token = f"{city_match.group(1)} 영광도서" if city_match else "행사 현장"
        replacement = f"{location_token} {suffixes[idx % len(suffixes)]}"
        start, end = match.span()
        working = working[:start] + replacement + working[end:]
        replaced += 1

    return working, replaced


def _replace_anchor_phrase_repetition(
    content: str,
    pattern: re.Pattern[str],
    replacements: Sequence[str],
    *,
    keep: int = 2,
) -> tuple[str, int]:
    """앵커 구문 반복이 keep회를 초과하면 뒤에서부터 유의어로 치환한다."""
    matches = list(pattern.finditer(content or ""))
    if len(matches) <= keep:
        return str(content or ""), 0

    replacement_pool = [item for item in (replacements or []) if str(item).strip()]
    if not replacement_pool:
        return str(content or ""), 0

    working = str(content or "")
    replaced = 0
    to_replace = list(reversed(matches[keep:]))
    for idx, match in enumerate(to_replace):
        replacement = replacement_pool[idx % len(replacement_pool)]
        start, end = match.span()
        working = working[:start] + replacement + working[end:]
        replaced += 1

    return working, replaced


def _dedupe_repeated_sentences_in_paragraphs(
    content: str,
    *,
    min_sentence_len: int = 20,
    keep: int = 1,
) -> tuple[str, int]:
    """문단 단위로 긴 문장 중복을 제거해 반복 게이트 실패를 완화한다."""
    raw_content = str(content or "")
    if not raw_content:
        return raw_content, 0

    seen: Dict[str, int] = {}
    removed = 0

    def replace_paragraph(match: re.Match[str]) -> str:
        nonlocal removed
        inner = str(match.group(1) or "")
        plain_inner = re.sub(r"<[^>]*>", " ", inner)
        plain_inner = re.sub(r"\s+", " ", plain_inner).strip()
        if not plain_inner:
            return ""

        sentences = [
            sentence.strip()
            for sentence in re.findall(r"[^.!?。]+[.!?。]?", plain_inner)
            if sentence and sentence.strip()
        ]
        if not sentences:
            return match.group(0)

        kept: list[str] = []
        for sentence in sentences:
            normalized = re.sub(r"\s+", " ", sentence).strip()
            if len(normalized) < min_sentence_len:
                kept.append(normalized)
                continue

            key = re.sub(r"\s+", "", normalized).lower()
            count = seen.get(key, 0)
            if count >= keep:
                removed += 1
                continue
            seen[key] = count + 1
            kept.append(normalized)

        if not kept:
            return ""
        return f"<p>{' '.join(kept).strip()}</p>"

    updated = re.sub(
        r"<p\b[^>]*>([\s\S]*?)</p\s*>",
        replace_paragraph,
        raw_content,
        flags=re.IGNORECASE,
    )
    updated = re.sub(r"\n{3,}", "\n\n", updated).strip()
    return updated, removed


def enforce_repetition_requirements(content: str) -> Dict[str, Any]:
    """반복 품질 위반을 최소 보정으로 완화한다.

    현재는 행사 일시+장소 결합 구문, 장소+조사 반복, 상투 앵커 구문을 우선적으로 줄인다.
    """
    base = str(content or "")
    working = base
    actions: list[Dict[str, Any]] = []

    event_datetime_location_pattern = re.compile(
        r"\d{1,2}\s*월\s*\d{1,2}\s*일(?:\([^)]+\))?\s*"
        r"(?:오전|오후)\s*\d{1,2}\s*시(?:\s*\d{1,2}\s*분)?\s*,?\s*"
        r"(?:서면|부산)(?:\s*영광도서)?\s*에서",
        re.IGNORECASE,
    )
    working, replaced = _replace_repetition_tail(working, event_datetime_location_pattern, keep=2)
    if replaced > 0:
        actions.append(
            {
                "type": "event_datetime_phrase_dedupe",
                "replaced": replaced,
                "keep": 2,
            }
        )

    location_postposition_pattern = re.compile(
        r"(?:서면|부산)\s*영광도서\s*에서",
        re.IGNORECASE,
    )
    working, location_replaced = _replace_location_postposition_repetition(
        working,
        location_postposition_pattern,
        keep=2,
    )
    if location_replaced > 0:
        actions.append(
            {
                "type": "location_postposition_dedupe",
                "replaced": location_replaced,
                "keep": 2,
            }
        )

    anchor_phrase_rules = [
        {
            "name": "부산항 부두 노동자의",
            "pattern": re.compile(r"부산항\s*부두\s*노동자의", re.IGNORECASE),
            "replacements": ("부산항 노동자 가정의", "부산항 현장 노동자 집안의"),
        },
        {
            "name": "시민 여러분과 함께",
            "pattern": re.compile(r"시민\s*여러분과\s*함께", re.IGNORECASE),
            "replacements": ("시민과 함께", "여러분과 함께", "지역사회와 함께"),
        },
    ]
    for rule in anchor_phrase_rules:
        working, anchor_replaced = _replace_anchor_phrase_repetition(
            working,
            rule["pattern"],
            rule["replacements"],
            keep=2,
        )
        if anchor_replaced > 0:
            actions.append(
                {
                    "type": "anchor_phrase_dedupe",
                    "phrase": rule["name"],
                    "replaced": anchor_replaced,
                    "keep": 2,
                }
            )

    working, sentence_removed = _dedupe_repeated_sentences_in_paragraphs(
        working,
        min_sentence_len=20,
        keep=1,
    )
    if sentence_removed > 0:
        actions.append(
            {
                "type": "sentence_dedupe",
                "removed": sentence_removed,
                "keep": 1,
            }
        )

    sentence_result = detect_sentence_repetition(working)
    phrase_result = detect_phrase_repetition(working)
    near_dup_result = detect_near_duplicate_sentences(working)
    issues: list[str] = []
    if not sentence_result.get("passed", True):
        issues.append(f"⚠️ 문장 반복 감지: {', '.join(sentence_result.get('repeatedSentences', []))}")
    if not phrase_result.get("passed", True):
        issues.append(f"⚠️ 구문 반복 감지: {', '.join(phrase_result.get('repeatedPhrases', []))}")
    if not near_dup_result.get("passed", True):
        summary = ", ".join(
            f"\"{pair['a']}\" ≈ \"{pair['b']}\" ({pair['similarity']}%)"
            for pair in (near_dup_result.get("similarPairs") or [])[:3]
        )
        issues.append(f"⚠️ 유사 문장 감지: {summary}")

    return {
        "content": working,
        "edited": working != base,
        "actions": actions,
        "passed": len(issues) == 0,
        "issues": issues,
        "details": {
            "repetition": sentence_result,
            "phrase": phrase_result,
            "nearDuplicate": near_dup_result,
        },
    }


def detect_near_duplicate_sentences(content: str, threshold: float = 0.6) -> Dict[str, Any]:
    plain_text = _strip_html(content)
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.?!])\s+", plain_text)
        if sentence and len(sentence.strip()) > 25
    ]
    word_sets: list[set[str]] = []
    for sentence in sentences:
        words = [word for word in re.split(r"\s+", re.sub(r"[.?!,]", "", sentence)) if len(word) >= 2]
        word_sets.append(set(words))

    similar_pairs: list[Dict[str, Any]] = []
    for i in range(len(sentences)):
        for j in range(i + 1, len(sentences)):
            set_a = word_sets[i]
            set_b = word_sets[j]
            if len(set_a) < 3 or len(set_b) < 3:
                continue
            intersection = len(set_a.intersection(set_b))
            union = len(set_a.union(set_b))
            similarity = (intersection / union) if union else 0
            if similarity < threshold:
                continue
            if similarity >= 0.95:
                continue
            similar_pairs.append(
                {
                    "a": sentences[i][:50] + ("..." if len(sentences[i]) > 50 else ""),
                    "b": sentences[j][:50] + ("..." if len(sentences[j]) > 50 else ""),
                    "similarity": round(similarity * 100),
                }
            )

    return {"passed": len(similar_pairs) == 0, "similarPairs": similar_pairs}


def detect_election_law_violation(content: str, status: str | None, title: str = "") -> Dict[str, Any]:
    if not status:
        return {"passed": True, "violations": [], "skipped": True}

    election_stage = get_election_stage(status)
    if not election_stage or election_stage.get("name") != "STAGE_1":
        return {"passed": True, "violations": [], "skipped": True}

    plain_text = _strip_html(f"{title or ''} {content or ''}")

    pledge_patterns = [
        r"추진하겠습니다",
        r"실현하겠습니다",
        r"만들겠습니다",
        r"해내겠습니다",
        r"전개하겠습니다",
        r"제공하겠습니다",
        r"활성화하겠습니다",
        r"개선하겠습니다",
        r"확대하겠습니다",
        r"강화하겠습니다",
        r"설립하겠습니다",
        r"구축하겠습니다",
        r"마련하겠습니다",
        r"지원하겠습니다",
        r"해결하겠습니다",
        r"바꾸겠습니다",
        r"펼치겠습니다",
        r"이루겠습니다",
        r"열겠습니다",
        r"세우겠습니다",
        r"이뤄내겠습니다",
        r"해드리겠습니다",
        r"드리겠습니다",
        r"약속드리겠습니다",
        r"바꿉니다",
        r"만듭니다",
        r"이룹니다",
        r"해결합니다",
        r"약속합니다",
        r"실현합니다",
        r"책임집니다",
    ]

    violations: list[str] = []
    for pattern in pledge_patterns:
        matches = re.findall(pattern, plain_text)
        if matches:
            violations.append(f"\"{matches[0]}\" ({len(matches)}회) - 공약성 표현")

    bribery_items = ViolationDetector.check_bribery_risk(plain_text)
    for item in bribery_items:
        violations.append(f"🔴 {item.get('reason') or '기부행위 금지 위반 위험'}")

    fact_items = ViolationDetector.check_fact_claims(plain_text)
    for item in fact_items:
        severity = str(item.get("severity") or "").upper()
        emoji = "🔴" if severity == "CRITICAL" else "⚠️"
        violations.append(f"{emoji} {item.get('reason') or '허위사실/비방 위험'}")

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "status": status,
        "stage": election_stage.get("name"),
        "hasCritical": bool(bribery_items) or any(
            str(item.get("severity") or "").upper() == "CRITICAL" for item in fact_items
        ),
    }


def validate_title_quality(
    title: str,
    user_keywords: Optional[Sequence[str]] = None,
    content: str = "",
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    options = options or {}
    strict_facts = options.get("strictFacts") is True
    user_keywords = list(user_keywords or [])

    if not title:
        return {"passed": True, "issues": [], "details": {}}

    issues: list[Dict[str, Any]] = []
    details: Dict[str, Any] = {
        "length": len(title),
        "maxLength": 35,
        "keywordPosition": None,
        "abstractExpressions": [],
        "hasNumbers": False,
    }

    if len(title) < 10:
        issues.append(
            {
                "type": "title_too_short",
                "severity": "critical",
                "description": f"제목이 너무 짧음 ({len(title)}자)",
                "instruction": "10자 이상으로 구체적인 내용을 포함하여 작성하세요. 단순 키워드 나열 금지.",
            }
        )

    if len(title) > 35:
        issues.append(
            {
                "type": "title_length",
                "severity": "critical",
                "description": f"제목 {len(title)}자 → 35자 초과 (네이버에서 잘림)",
                "instruction": "35자 이내로 줄이세요. 불필요한 조사, 부제목(:, -) 제거.",
            }
        )

    if user_keywords:
        primary_kw = user_keywords[0]
        kw_index = title.find(primary_kw)
        details["keywordPosition"] = kw_index

        if kw_index == -1:
            issues.append(
                {
                    "type": "keyword_missing",
                    "severity": "high",
                    "description": f"핵심 키워드 \"{primary_kw}\" 제목에 없음",
                    "instruction": f"\"{primary_kw}\"를 제목 앞부분에 포함하세요.",
                }
            )
        elif kw_index > 10:
            issues.append(
                {
                    "type": "keyword_position",
                    "severity": "medium",
                    "description": f"키워드 \"{primary_kw}\" 위치 {kw_index}자 → 너무 뒤쪽",
                    "instruction": "핵심 키워드는 제목 앞쪽 8자 이내에 배치하세요 (앞쪽 1/3 법칙).",
                }
            )

        clean_title = re.sub(r"\s+", "", title)
        clean_kw = re.sub(r"\s+", "", primary_kw)
        if clean_kw and clean_kw in clean_title and len(clean_title) <= len(clean_kw) + 4:
            issues.append(
                {
                    "type": "title_too_generic",
                    "severity": "critical",
                    "description": "제목이 키워드와 너무 유사함 (단순 명사형)",
                    "instruction": "서술어인 \"현안 진단\", \"핵심 분석\", \"이슈 점검\" 등을 반드시 포함하여 구체화하세요.",
                }
            )

    if content:
        title_numeric_tokens = extract_numeric_tokens(title)
        content_numeric_tokens = extract_numeric_tokens(content)
        if title_numeric_tokens:
            if not content_numeric_tokens:
                issues.append(
                    {
                        "type": "title_number_mismatch",
                        "severity": "high",
                        "description": "제목에 수치가 있으나 본문에 근거 수치 없음",
                        "instruction": "본문에 실제로 있는 수치/단위를 제목에 사용하세요.",
                    }
                )
            else:
                missing_tokens = [token for token in title_numeric_tokens if token not in content_numeric_tokens]
                if missing_tokens:
                    issues.append(
                        {
                            "type": "title_number_mismatch",
                            "severity": "high",
                            "description": f"제목 수치/단위가 본문과 불일치: {', '.join(missing_tokens)}",
                            "instruction": "본문에 실제로 등장하는 수치/단위를 제목에 그대로 사용하세요.",
                        }
                    )

    abstract_patterns = [
        ("비전", r"비전"),
        ("혁신", r"혁신"),
        ("발전", r"발전"),
        ("노력", r"노력"),
        ("최선", r"최선"),
        ("약속", r"약속"),
        ("다짐", r"다짐"),
        ("함께", r"함께"),
        ("확충", r"확충"),
        ("개선", r"개선"),
        ("추진", r"추진"),
        ("시급", r"시급"),
        ("강화", r"강화"),
        ("증진", r"증진"),
        ("도모", r"도모"),
        ("향상", r"향상"),
        ("활성화", r"활성화"),
        ("선도", r"선도"),
        ("선진", r"선진"),
        ("미래", r"미래"),
    ]
    found_abstract = [word for word, pattern in abstract_patterns if re.search(pattern, title)]
    if found_abstract:
        details["abstractExpressions"] = found_abstract
        issues.append(
            {
                "type": "abstract_expression",
                "severity": "medium",
                "description": f"추상적 표현 사용: {', '.join(found_abstract)}",
                "instruction": "구체적 수치나 사실로 대체하세요. 예: \"발전\" → \"40% 증가\", \"비전\" → \"3대 핵심 정책\"",
            }
        )

    details["hasNumbers"] = bool(re.search(r"\d", title))
    if (not details["hasNumbers"]) and issues and (not strict_facts):
        issues.append(
            {
                "type": "no_numbers",
                "severity": "low",
                "description": "숫자/구체적 데이터 없음",
                "instruction": "가능하면 숫자를 포함하세요. 예: \"3대 정책\", \"120억 확보\", \"40% 개선\"",
            }
        )

    has_blocking_issue = any(issue.get("severity") in {"critical", "high"} for issue in issues)
    return {"passed": not has_blocking_issue, "issues": issues, "details": details}


def run_heuristic_validation_sync(
    content: str,
    status: str,
    title: str = "",
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    options = options or {}
    fact_allowlist = options.get("factAllowlist")

    issues: list[str] = []

    repetition_result = detect_sentence_repetition(content)
    if not repetition_result.get("passed", True):
        issues.append(f"⚠️ 문장 반복 감지: {', '.join(repetition_result.get('repeatedSentences', []))}")

    phrase_result = detect_phrase_repetition(content)
    if not phrase_result.get("passed", True):
        issues.append(f"⚠️ 구문 반복 감지: {', '.join(phrase_result.get('repeatedPhrases', []))}")

    near_dup_result = detect_near_duplicate_sentences(content)
    if not near_dup_result.get("passed", True):
        summary = ", ".join(
            f"\"{pair['a']}\" ≈ \"{pair['b']}\" ({pair['similarity']}%)"
            for pair in (near_dup_result.get("similarPairs") or [])[:3]
        )
        issues.append(f"⚠️ 유사 문장 감지: {summary}")

    election_result = detect_election_law_violation(content, status, title)
    if not election_result.get("passed", True):
        issues.append(f"⚠️ 선거법 위반 표현: {', '.join(election_result.get('violations', []))}")

    fact_check_result = None
    if fact_allowlist:
        content_check = find_unsupported_numeric_tokens(content, fact_allowlist)
        title_check = find_unsupported_numeric_tokens(title, fact_allowlist) if title else {"passed": True, "unsupported": []}
        fact_check_result = {"content": content_check, "title": title_check}

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "details": {
            "repetition": repetition_result,
            "electionLaw": election_result,
            "factCheck": fact_check_result,
        },
    }


async def run_heuristic_validation(
    content: str,
    status: str,
    title: str = "",
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    options = options or {}
    use_llm = options.get("useLLM", True)
    user_keywords = list(options.get("userKeywords") or [])
    fact_allowlist = options.get("factAllowlist")
    model_name = options.get("modelName", "gemini-2.5-flash")

    issues: list[str] = []

    repetition_result = detect_sentence_repetition(content)
    if not repetition_result.get("passed", True):
        issues.append(f"⚠️ 문장 반복 감지: {', '.join(repetition_result.get('repeatedSentences', []))}")

    phrase_result = detect_phrase_repetition(content)
    if not phrase_result.get("passed", True):
        issues.append(f"⚠️ 구문 반복 감지: {', '.join(phrase_result.get('repeatedPhrases', []))}")

    near_dup_result = detect_near_duplicate_sentences(content)
    if not near_dup_result.get("passed", True):
        summary = ", ".join(
            f"\"{pair['a']}\" ≈ \"{pair['b']}\" ({pair['similarity']}%)"
            for pair in (near_dup_result.get("similarPairs") or [])[:3]
        )
        issues.append(f"⚠️ 유사 문장 감지: {summary}")

    if use_llm:
        election_result = await detect_election_law_violation_hybrid(
            content,
            status,
            title,
            model_name=model_name,
        )
        if not election_result.get("passed", True):
            violation_summary = ", ".join(
                f"\"{item.get('sentence', '')}\" ({item.get('reason', '')})"
                for item in (election_result.get("violations") or [])
            )
            issues.append(f"⚠️ 선거법 위반: {violation_summary}")
    else:
        election_result = detect_election_law_violation(content, status, title)
        if not election_result.get("passed", True):
            issues.append(f"⚠️ 선거법 위반 표현: {', '.join(election_result.get('violations', []))}")

    title_result = validate_title_quality(
        title,
        user_keywords=user_keywords,
        content=content,
        options={"strictFacts": bool(fact_allowlist)},
    )
    if not title_result.get("passed", True):
        blocking_title_issues = [
            issue.get("description")
            for issue in (title_result.get("issues") or [])
            if issue.get("severity") in {"critical", "high"}
        ]
        if blocking_title_issues:
            issues.append(f"⚠️ 제목 품질 문제: {', '.join(blocking_title_issues)}")

    fact_check_result = None
    if fact_allowlist:
        content_check = find_unsupported_numeric_tokens(content, fact_allowlist)
        title_check = find_unsupported_numeric_tokens(title, fact_allowlist) if title else {"passed": True, "unsupported": []}
        fact_check_result = {"content": content_check, "title": title_check}

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "details": {
            "repetition": repetition_result,
            "electionLaw": election_result,
            "titleQuality": title_result,
            "factCheck": fact_check_result,
        },
    }


# ============================================================================
# 초당적 협력 / 핵심 문구 / 비판 대상 검증
# ============================================================================


BIPARTISAN_FORBIDDEN_PHRASES = [
    "정신을 이어받아",
    "뜻을 받들어",
    "배워야 합니다",
    "배울 점",
    "깊은 울림",
    "용기에 박수",
    "귀감이 됩니다",
    "본받아야",
    "존경합니다",
    "멘토",
    "스승",
    "깊은 감명",
    "우리보다 낫다",
    "우리보다 훨씬 낫다",
    "우리는 저렇게 못한다",
    "정책이 100% 맞다",
    "전적으로 동의한다",
    "완전히 옳다",
    "정치인 중 최고",
    "유일하게 믿을 수 있다",
    "가장 훌륭하다",
    "개인적으로 좋아한다",
    "헌신적인 노력",
    "헌신적인 모습",
]


def detect_bipartisan_forbidden_phrases(content: str) -> Dict[str, Any]:
    violations: list[str] = []
    corrected = content or ""

    for phrase in BIPARTISAN_FORBIDDEN_PHRASES:
        if phrase not in corrected:
            continue
        violations.append(phrase)
        if phrase == "귀감이 됩니다":
            corrected = corrected.replace(phrase, "주목할 만합니다")
        elif phrase == "배워야 합니다":
            corrected = corrected.replace(phrase, "참고할 수 있습니다")
        elif phrase == "깊은 감명":
            corrected = corrected.replace(phrase, "관심")
        elif "헌신적인" in phrase:
            corrected = corrected.replace(phrase, "꾸준한 노력")
        else:
            corrected = corrected.replace(phrase, "")

    corrected = re.sub(r"\s+", " ", corrected)
    corrected = re.sub(r"\s+\.", ".", corrected).strip()
    return {"hasForbidden": len(violations) > 0, "violations": violations, "correctedContent": corrected}


def calculate_praise_proportion(content: str, rival_names: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    rival_names = list(rival_names or [])
    if not rival_names:
        return {"percentage": 0, "exceedsLimit": False, "rivalMentions": 0}

    sentences = extract_sentences(content or "")
    rival_mention_sentences = 0
    for sentence in sentences:
        if any(name in sentence for name in rival_names):
            rival_mention_sentences += 1

    percentage = round((rival_mention_sentences / len(sentences)) * 100) if sentences else 0
    return {
        "percentage": percentage,
        "exceedsLimit": percentage > 15,
        "rivalMentions": rival_mention_sentences,
        "totalSentences": len(sentences),
    }


def validate_bipartisan_praise(content: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    options = options or {}
    rival_names = list(options.get("rivalNames") or [])
    category = str(options.get("category") or "")

    if ("bipartisan" not in category) and ("초당적" not in category):
        return {"passed": True, "issues": [], "correctedContent": content}

    issues: list[str] = []
    forbidden_result = detect_bipartisan_forbidden_phrases(content or "")
    if forbidden_result["hasForbidden"]:
        issues.append(
            f"⚠️ 초당적 협력 금지 표현 감지 및 자동 수정: {', '.join(forbidden_result['violations'])}"
        )

    proportion_result = calculate_praise_proportion(forbidden_result["correctedContent"], rival_names)
    if proportion_result.get("exceedsLimit"):
        issues.append(
            f"⚠️ 경쟁자 칭찬 비중 초과: {proportion_result['percentage']}% "
            f"({proportion_result['rivalMentions']}/{proportion_result['totalSentences']} 문장) - 권장 15% 이하"
        )

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "correctedContent": forbidden_result["correctedContent"],
        "details": {"forbiddenPhrases": forbidden_result, "praiseProportion": proportion_result},
    }


def validate_key_phrase_inclusion(content: str, required_phrases: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    required_phrases = list(required_phrases or [])
    if not content or not required_phrases:
        return {"passed": True, "missing": [], "included": [], "details": {}}

    plain_content = _strip_html(content)
    included: list[Dict[str, str]] = []
    missing: list[str] = []
    details: Dict[str, Any] = {}

    for phrase in required_phrases:
        if not phrase or len(phrase) < 5:
            continue
        exact_match = phrase in plain_content
        core_words = [
            word
            for word in re.split(r"\s+", re.sub(r"[.?!,~]", "", phrase))
            if len(word) >= 4 and not re.match(r"^(있습니다|없습니다|합니다|입니다|것입니다|아닙니다)$", word)
        ]
        core_word_matches = [word for word in core_words if word in plain_content]
        paraphrase_match = bool(core_words) and len(core_word_matches) >= (len(core_words) + 1) // 2

        details[phrase] = {
            "exactMatch": exact_match,
            "paraphraseMatch": paraphrase_match,
            "coreWords": core_words,
            "coreWordMatches": core_word_matches,
            "included": exact_match or paraphrase_match,
        }

        if exact_match or paraphrase_match:
            included.append({"phrase": phrase, "matchType": "exact" if exact_match else "paraphrase"})
        else:
            missing.append(phrase)

    has_exact_match = any(item.get("matchType") == "exact" for item in included)
    all_included = len(missing) == 0
    passed = all_included and (len(required_phrases) <= 1 or has_exact_match)

    return {
        "passed": passed,
        "missing": missing,
        "included": included,
        "hasExactMatch": has_exact_match,
        "details": details,
        "message": (
            None
            if passed
            else (
                f"핵심 문구 누락: {', '.join(f'\"{item[:30]}...\"' for item in missing)}"
                if missing
                else "원문 그대로 인용된 문구가 없습니다. 최소 1개는 원문 인용이 필요합니다."
            )
        ),
    }


def validate_criticism_target(content: str, responsibility_target: str) -> Dict[str, Any]:
    if not content or not responsibility_target:
        return {"passed": True, "targetMentioned": False, "count": 0}

    plain_content = re.sub(r"<[^>]*>", " ", content)
    target_parts = [part for part in re.split(r"\s+", responsibility_target) if part]
    target_name = target_parts[0] if target_parts else responsibility_target
    escaped_name = re.escape(target_name)

    matches = re.findall(escaped_name, plain_content)
    count = len(matches)
    count_passed = count >= 2

    intent_reversal_patterns = [
        re.compile(rf"{escaped_name}[^.]*(?:협력|존중|함께|노력|인정|공로|성과)"),
        re.compile(rf"(?:협력|존중|함께)하여[^.]*{escaped_name}"),
        re.compile(rf"{escaped_name}[^.]*(?:의\s*노력|과\s*협력|과\s*함께|을\s*존중)"),
    ]

    intent_reversal_count = 0
    intent_reversal_matches: list[str] = []
    for pattern in intent_reversal_patterns:
        detected = pattern.findall(plain_content)
        intent_reversal_count += len(detected)
        intent_reversal_matches.extend(detected)

    criticism_patterns = [
        re.compile(rf"{escaped_name}[^.]*(?:역부족|한계|문제|책임|비판|실패|부족)"),
        re.compile(rf"(?:역부족|한계|문제|책임|비판|실패|부족)[^.]*{escaped_name}"),
    ]
    criticism_context_count = sum(len(pattern.findall(plain_content)) for pattern in criticism_patterns)
    has_intent_reversal = intent_reversal_count > 0 and intent_reversal_count > criticism_context_count
    passed = count_passed and (not has_intent_reversal)

    message = None
    if not count_passed:
        message = f"비판 대상 \"{target_name}\" 언급 부족 (현재 {count}회, 최소 2회 필요)"
    elif has_intent_reversal:
        message = (
            f"🔴 의도 역전 감지: 비판 대상 \"{target_name}\"이(가) 긍정적 맥락(협력/존중/함께)으로 언급됨. "
            f"원본의 비판적 논조를 유지하세요. [감지된 표현: {', '.join(intent_reversal_matches[:2])}]"
        )

    return {
        "passed": passed,
        "targetMentioned": count > 0,
        "count": count,
        "targetName": target_name,
        "hasIntentReversal": has_intent_reversal,
        "intentReversalCount": intent_reversal_count,
        "criticismContextCount": criticism_context_count,
        "message": message,
    }


# ============================================================================
# 키워드 삽입 검증
# ============================================================================


def count_keyword_occurrences(content: str, keyword: str) -> int:
    clean_content = re.sub(r"<[^>]*>", "", content or "")
    escaped = re.escape(keyword or "")
    if not escaped:
        return 0
    return len(re.findall(escaped, clean_content))


def build_keyword_variants(keyword: str) -> List[str]:
    trimmed = str(keyword or "").strip()
    if not trimmed:
        return []
    parts = [part for part in re.split(r"\s+", trimmed) if part]
    variants: list[str] = []
    if len(parts) >= 2:
        first = parts[0]
        rest = " ".join(parts[1:])
        variants.append(f"{first}의 {rest}")
        variants.append(f"{rest} {first}")
    deduped: list[str] = []
    seen: set[str] = set()
    for item in variants:
        if item and item != trimmed and item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def count_keyword_coverage(content: str, keyword: str) -> int:
    if not keyword:
        return 0
    keywords = [keyword, *build_keyword_variants(keyword)]
    return sum(count_keyword_occurrences(content, item) for item in keywords)


def _keyword_user_threshold(user_keywords: Optional[Sequence[str]] = None) -> tuple[int, int]:
    normalized = [item for item in (user_keywords or []) if item]
    kw_count = len(normalized) if normalized else 1
    user_min_count = 3 if kw_count >= 2 else 5
    user_max_count = user_min_count + 1
    return user_min_count, user_max_count


def _parse_keyword_sections(content: str) -> List[Dict[str, Any]]:
    sections: list[Dict[str, Any]] = []
    h2_matches = list(re.finditer(r"<h2[^>]*>[\s\S]*?<\/h2>", content or "", re.IGNORECASE))

    if not h2_matches:
        return [
            {
                "type": "single",
                "startIndex": 0,
                "endIndex": len(content or ""),
                "content": content or "",
            }
        ]

    first_h2_start = h2_matches[0].start()
    if first_h2_start > 0:
        sections.append(
            {
                "type": "intro",
                "startIndex": 0,
                "endIndex": first_h2_start,
                "content": (content or "")[:first_h2_start],
            }
        )

    for idx, match in enumerate(h2_matches):
        start_index = match.start()
        end_index = h2_matches[idx + 1].start() if idx < len(h2_matches) - 1 else len(content or "")
        section_type = "conclusion" if idx == len(h2_matches) - 1 else f"body{idx + 1}"
        sections.append(
            {
                "type": section_type,
                "startIndex": start_index,
                "endIndex": end_index,
                "content": (content or "")[start_index:end_index],
            }
        )

    return sections


def _section_priority(section_type: str) -> int:
    if section_type.startswith("body"):
        return 0
    if section_type == "conclusion":
        return 1
    if section_type == "intro":
        return 2
    return 3


def _select_keyword_section_indexes(
    sections: Sequence[Dict[str, Any]],
    keyword: str,
    needed: int,
) -> List[int]:
    if not sections or needed <= 0:
        return []

    indexed = list(enumerate(sections))

    def _location_section_penalty(section_content: str) -> int:
        plain = re.sub(r"<[^>]*>", " ", str(section_content or ""))
        plain = re.sub(r"\s+", " ", plain).strip()
        if _is_event_context_text(plain, keyword=keyword):
            return 0
        if _is_unsafe_location_context(plain):
            return 2
        return 1

    if _is_location_keyword(keyword):
        ranked = sorted(
            indexed,
            key=lambda item: (
                count_keyword_occurrences(str(item[1].get("content") or ""), keyword),
                _location_section_penalty(str(item[1].get("content") or "")),
                _section_priority(str(item[1].get("type") or "")),
                item[0],
            ),
        )
    else:
        ranked = sorted(
            indexed,
            key=lambda item: (
                count_keyword_occurrences(str(item[1].get("content") or ""), keyword),
                _section_priority(str(item[1].get("type") or "")),
                item[0],
            ),
        )
    if not ranked:
        return []

    chosen: list[int] = []
    while len(chosen) < needed:
        progressed = False
        for idx, _section in ranked:
            chosen.append(idx)
            progressed = True
            if len(chosen) >= needed:
                break
        if not progressed:
            break
    return chosen[:needed]


def _is_location_keyword(keyword: str) -> bool:
    normalized = str(keyword or "").strip()
    if not normalized:
        return False
    location_tokens = (
        "영광도서",
        "도서관",
        "광장",
        "센터",
        "공원",
        "시청",
        "구청",
        "동",
    )
    return any(token in normalized for token in location_tokens)


LOCATION_EVENT_CONTEXT_TOKENS = LOCATION_CONTEXT_TOKENS
LOCATION_UNSAFE_CONTEXT_TOKENS = UNSAFE_LOCATION_CONTEXT_TOKENS
LOCATION_UNSAFE_ATTACH_TOKENS = UNSAFE_LOCATION_ATTACH_TOKENS


def _is_event_context_text(text: str, keyword: str = "") -> bool:
    return _policy_is_location_context_text(text, keyword=keyword)


def _is_unsafe_location_context(text: str) -> bool:
    return _policy_is_unsafe_location_context(text)


def _is_non_editable_sentence(text: str) -> bool:
    normalized = _policy_normalize_plain(text)
    if not normalized:
        return True
    if _policy_is_greeting_sentence(normalized):
        return True
    if _policy_is_terminal_sentence(normalized):
        return True
    return False


def _is_unnatural_location_phrase(text: str, keyword: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    normalized_keyword = str(keyword or "").strip()
    if not normalized or not normalized_keyword or not _is_location_keyword(normalized_keyword):
        return False
    if _is_event_context_text(normalized, keyword=normalized_keyword):
        return False

    token_pattern = "|".join(re.escape(token) for token in LOCATION_UNSAFE_ATTACH_TOKENS)
    around_kw = re.compile(
        rf"(?:{re.escape(normalized_keyword)}\s*(?:{token_pattern})|(?:{token_pattern})\s*{re.escape(normalized_keyword)})",
        re.IGNORECASE,
    )
    return bool(around_kw.search(normalized))


def _try_contextual_location_replacement(section_html: str, keyword: str) -> tuple[str, bool]:
    raw_section = str(section_html or "")
    normalized_keyword = str(keyword or "").strip()
    if not raw_section or not normalized_keyword:
        return raw_section, False

    plain_section = _policy_normalize_plain(raw_section)
    if not _is_event_context_text(plain_section, keyword=normalized_keyword):
        return raw_section, False

    before_count = count_keyword_occurrences(raw_section, normalized_keyword)
    area_match = re.match(r"(서면|부산)\s*", normalized_keyword)
    area = area_match.group(1) if area_match else ""

    substitutions: List[tuple[str, str]] = []
    if area:
        substitutions.extend(
            [
                (rf"{re.escape(area)}\s*영광도서\s*현장에서", f"{normalized_keyword} 현장에서"),
                (rf"{re.escape(area)}\s*영광도서\s*에서", f"{normalized_keyword}에서"),
                (rf"{re.escape(area)}\s*영광도서", normalized_keyword),
            ]
        )
    substitutions.extend(
        [
            (r"영광도서\s*현장에서", f"{normalized_keyword} 현장에서"),
            (r"영광도서\s*에서", f"{normalized_keyword}에서"),
            (r"영광도서", normalized_keyword),
        ]
    )

    paragraph_matches = list(re.finditer(r"<p\b[^>]*>([\s\S]*?)</p\s*>", raw_section, re.IGNORECASE))
    if not paragraph_matches:
        return raw_section, False

    for paragraph_match in paragraph_matches:
        paragraph_inner = str(paragraph_match.group(1) or "")
        paragraph_plain = _policy_normalize_plain(paragraph_inner)
        if not paragraph_plain:
            continue
        if not _is_event_context_text(paragraph_plain, keyword=normalized_keyword):
            continue
        if _is_unsafe_location_context(paragraph_plain):
            continue
        if _is_non_editable_sentence(paragraph_plain):
            continue

        for pattern, replacement in substitutions:
            updated_inner, changed = re.subn(
                pattern,
                replacement,
                paragraph_inner,
                count=1,
                flags=re.IGNORECASE,
            )
            if changed <= 0:
                continue
            candidate = (
                raw_section[: paragraph_match.start(1)]
                + updated_inner
                + raw_section[paragraph_match.end(1) :]
            )
            if _is_unnatural_location_phrase(candidate, normalized_keyword):
                continue
            after_count = count_keyword_occurrences(candidate, normalized_keyword)
            if after_count > before_count:
                return candidate, True

    return raw_section, False


def _rewrite_sentence_with_keyword(sentence: str, keyword: str, variant_index: int = 0) -> str:
    _ = variant_index
    normalized_sentence = re.sub(r"\s+", " ", str(sentence or "")).strip()
    normalized_keyword = str(keyword or "").strip()
    if not normalized_sentence or not normalized_keyword:
        return normalized_sentence
    if normalized_keyword in normalized_sentence:
        return normalized_sentence

    if _is_location_keyword(normalized_keyword):
        # 위치 키워드는 일반 명사 앞 강제 삽입 시 비문이 잘 발생하므로,
        # 문장 리라이트 경로를 비활성화하고
        # 1) 문맥 치환, 2) 행사형 보강 문장 경로만 사용한다.
        return normalized_sentence

    anchor_tokens = (
        "출판기념회",
        "행사",
        "일정",
        "현장",
        "참여",
        "소통",
        "대화",
        "문제",
        "과제",
        "쟁점",
        "해법",
        "계획",
        "설명",
        "논의",
        "비전",
        "해법",
    )

    for token in anchor_tokens:
        if token in normalized_sentence:
            rewritten = normalized_sentence.replace(token, f"{normalized_keyword} {token}", 1)
            if _is_unnatural_location_phrase(rewritten, normalized_keyword):
                continue
            return rewritten

    # 템플릿형 접두/접속 문장은 사용하지 않는다 (자연 문장 유지)
    return normalized_sentence


def _inject_keyword_into_section(
    section_html: str,
    keyword: str,
    section_type: str,
    variant_index: int = 0,
) -> tuple[str, bool, str]:
    raw_section = str(section_html or "")
    normalized_keyword = str(keyword or "").strip()
    if not raw_section or not normalized_keyword:
        return raw_section, False, ""

    before_count = count_keyword_occurrences(raw_section, normalized_keyword)
    if _is_location_keyword(normalized_keyword):
        replaced_section, replaced = _try_contextual_location_replacement(raw_section, normalized_keyword)
        if replaced:
            return replaced_section, True, f"{normalized_keyword} (문맥 치환)"

    paragraph_matches = list(re.finditer(r"<p\b[^>]*>([\s\S]*?)</p\s*>", raw_section, re.IGNORECASE))
    if not paragraph_matches:
        # 섹션 구조가 없으면 무리한 템플릿 보정 없이 통과시킨다.
        return raw_section, False, ""

    if str(section_type or "").startswith("body"):
        paragraph_indexes = list(range(len(paragraph_matches)))
    elif section_type == "conclusion":
        paragraph_indexes = list(reversed(range(len(paragraph_matches))))
    else:
        paragraph_indexes = list(range(len(paragraph_matches)))

    focus_tokens = SENTENCE_FOCUS_TOKENS

    for paragraph_index in paragraph_indexes:
        paragraph_match = paragraph_matches[paragraph_index]
        paragraph_inner = str(paragraph_match.group(1) or "")
        sentence_matches = list(re.finditer(r"[^.!?。]+[.!?。]?", paragraph_inner))
        if not sentence_matches:
            continue

        ranked_sentences = sorted(
            sentence_matches,
            key=lambda m: (
                0
                if any(token in re.sub(r"\s+", " ", m.group(0)).strip() for token in focus_tokens)
                else 1,
                -len(re.sub(r"\s+", " ", m.group(0)).strip()),
            ),
        )

        for sentence_match in ranked_sentences:
            original_sentence = re.sub(r"\s+", " ", sentence_match.group(0)).strip()
            if not original_sentence:
                continue
            if len(original_sentence) < 14:
                continue
            if _is_non_editable_sentence(original_sentence):
                continue
            if _is_location_keyword(normalized_keyword):
                if not _is_event_context_text(original_sentence, keyword=normalized_keyword):
                    continue
                if _is_unsafe_location_context(original_sentence):
                    continue
            if "존경하는" in original_sentence and "안녕하십니까" in original_sentence:
                continue
            rewritten_sentence = _rewrite_sentence_with_keyword(
                original_sentence,
                normalized_keyword,
                variant_index,
            )
            if not rewritten_sentence or rewritten_sentence == original_sentence:
                continue

            sentence_start = sentence_match.start()
            sentence_end = sentence_match.end()
            updated_inner = (
                paragraph_inner[:sentence_start]
                + rewritten_sentence
                + paragraph_inner[sentence_end:]
            )
            candidate = (
                raw_section[: paragraph_match.start(1)]
                + updated_inner
                + raw_section[paragraph_match.end(1) :]
            )
            if count_keyword_occurrences(candidate, normalized_keyword) > before_count:
                return candidate, True, rewritten_sentence

    # 신규 문장 보강 없이, 기존 문맥 리라이트가 불가능하면 실패를 반환한다.
    return raw_section, False, ""


def _replace_last_keyword_occurrences(
    content: str,
    keyword: str,
    remove_count: int,
) -> tuple[str, int]:
    """정확 일치 기준 과다 키워드를 뒤에서부터 치환해 개수를 줄인다."""
    if not content or not keyword or remove_count <= 0:
        return str(content or ""), 0

    escaped = re.escape(str(keyword))
    matches = list(re.finditer(escaped, str(content)))
    if not matches:
        return str(content), 0

    replacements_needed = min(remove_count, len(matches))
    variants = build_keyword_variants(keyword)
    fallback_token = "이 사안"
    replacement_pool = variants if variants else [fallback_token]

    working = str(content)
    replaced = 0
    # 뒤에서부터 치환해 인덱스 어긋남을 방지한다.
    for idx, match in enumerate(reversed(matches[-replacements_needed:])):
        replacement = replacement_pool[idx % len(replacement_pool)]
        start, end = match.span()
        if start < 0 or end > len(working) or start >= end:
            continue
        working = working[:start] + replacement + working[end:]
        replaced += 1

    return working, replaced


def enforce_keyword_requirements(
    content: str,
    user_keywords: Optional[Sequence[str]] = None,
    auto_keywords: Optional[Sequence[str]] = None,
    target_word_count: Optional[int] = None,
    max_iterations: int = 2,
) -> Dict[str, Any]:
    working_content = str(content or "")
    user_keywords = [item for item in (user_keywords or []) if item]
    auto_keywords = [item for item in (auto_keywords or []) if item]

    initial_result = validate_keyword_insertion(
        working_content,
        user_keywords,
        auto_keywords,
        target_word_count,
    )
    if not working_content or (not user_keywords and not auto_keywords):
        return {
            "content": working_content,
            "edited": False,
            "insertions": [],
            "keywordResult": initial_result,
        }
    if initial_result.get("valid"):
        return {
            "content": working_content,
            "edited": False,
            "insertions": [],
            "keywordResult": initial_result,
        }

    insertions: list[Dict[str, Any]] = []
    reductions: list[Dict[str, Any]] = []
    per_keyword_insertions: Dict[str, int] = {}
    current_result = initial_result

    for _ in range(max_iterations):
        details = (current_result.get("details") or {}).get("keywords") or {}
        sections = _parse_keyword_sections(working_content)
        if not details or not sections:
            break

        adjusted_for_excess = False
        for keyword in user_keywords:
            keyword_info = details.get(keyword) or {}
            current_count = int(keyword_info.get("count") or keyword_info.get("coverage") or 0)
            max_allowed = int(keyword_info.get("max") or _keyword_user_threshold(user_keywords)[1])
            excess = max(0, current_count - max_allowed)
            if excess <= 0:
                continue

            updated_content, replaced_count = _replace_last_keyword_occurrences(
                working_content,
                keyword,
                excess,
            )
            if replaced_count <= 0:
                continue

            adjusted_for_excess = True
            working_content = updated_content
            reductions.append(
                {
                    "keyword": keyword,
                    "excess": excess,
                    "replaced": replaced_count,
                    "targetMax": max_allowed,
                }
            )

        if adjusted_for_excess:
            current_result = validate_keyword_insertion(
                working_content,
                user_keywords,
                auto_keywords,
                target_word_count,
            )
            if current_result.get("valid"):
                break
            details = (current_result.get("details") or {}).get("keywords") or {}
            sections = _parse_keyword_sections(working_content)
            if not details or not sections:
                break

        insertion_plan: Dict[int, List[Dict[str, Any]]] = {}
        needs_fix = False

        for keyword in [*user_keywords, *auto_keywords]:
            keyword_info = details.get(keyword) or {}
            expected = int(keyword_info.get("expected") or (1 if keyword in auto_keywords else _keyword_user_threshold(user_keywords)[0]))
            current_count = int(keyword_info.get("count") or keyword_info.get("coverage") or 0)
            deficit = max(0, expected - current_count)
            if deficit <= 0:
                continue

            needs_fix = True
            target_indexes = _select_keyword_section_indexes(sections, keyword, deficit)
            for section_idx in target_indexes:
                if section_idx < 0 or section_idx >= len(sections):
                    continue
                section = sections[section_idx]
                variant_index = per_keyword_insertions.get(keyword, 0)
                per_keyword_insertions[keyword] = variant_index + 1
                insertion_plan.setdefault(section_idx, []).append(
                    {
                        "keyword": keyword,
                        "section": section_idx,
                        "sectionType": section.get("type"),
                        "variantIndex": variant_index,
                    }
                )

        if not needs_fix or not insertion_plan:
            break

        applied_in_iteration = 0
        for section_idx in sorted(insertion_plan.keys(), reverse=True):
            if section_idx < 0 or section_idx >= len(sections):
                continue
            section = sections[section_idx]
            start_index = int(section.get("startIndex") or 0)
            end_index = int(section.get("endIndex") or 0)
            if end_index < start_index:
                continue

            payload = insertion_plan[section_idx]
            section_content = working_content[start_index:end_index]
            applied_payload: list[Dict[str, Any]] = []
            for item in payload:
                updated_section, edited, applied_sentence = _inject_keyword_into_section(
                    section_content,
                    str(item.get("keyword") or ""),
                    str(item.get("sectionType") or ""),
                    int(item.get("variantIndex") or 0),
                )
                if not edited:
                    continue
                section_content = updated_section
                item["sentence"] = applied_sentence
                item["strategy"] = "contextual_section_rewrite"
                applied_payload.append(item)
                applied_in_iteration += 1
            if not applied_payload:
                continue
            working_content = working_content[:start_index] + section_content + working_content[end_index:]
            insertions.extend(applied_payload)

        if applied_in_iteration <= 0:
            break

        current_result = validate_keyword_insertion(
            working_content,
            user_keywords,
            auto_keywords,
            target_word_count,
        )
        if current_result.get("valid"):
            break

    return {
        "content": working_content,
        "edited": working_content != str(content or ""),
        "insertions": insertions,
        "reductions": reductions,
        "keywordResult": current_result,
    }


def build_fallback_draft(params: Optional[Dict[str, Any]] = None) -> str:
    params = params or {}
    topic = str(params.get("topic") or "현안").strip()
    full_name = str(params.get("fullName") or "").strip()
    user_keywords = list(params.get("userKeywords") or [])

    greeting = f"존경하는 시민 여러분, {full_name}입니다." if full_name else "존경하는 시민 여러분."
    keyword_sentences = [f"{keyword}와 관련한 현황을 점검합니다." for keyword in user_keywords[:5] if keyword]
    keyword_paragraph = f"<p>{' '.join(keyword_sentences)}</p>" if keyword_sentences else ""

    blocks = [
        f"<p>{greeting} {topic}에 대해 핵심 현황을 정리합니다.</p>",
        "<h2>현안 개요</h2>",
        f"<p>{topic}의 구조적 배경과 최근 흐름을 객관적으로 살펴봅니다.</p>",
        keyword_paragraph,
        "<h2>핵심 쟁점</h2>",
        "<p>원인과 영향을 구분해 사실관계를 정리하고, 논의가 필요한 지점을 확인합니다.</p>",
        "<h2>확인 과제</h2>",
        "<p>추가 확인이 필요한 데이터와 점검 과제를 중심으로 정리합니다.</p>",
        f"<p>{full_name} 드림</p>" if full_name else "",
    ]
    return "\n".join(block for block in blocks if block)


def validate_keyword_insertion(
    content: str,
    user_keywords: Optional[Sequence[str]] = None,
    auto_keywords: Optional[Sequence[str]] = None,
    target_word_count: Optional[int] = None,
) -> Dict[str, Any]:
    _ = target_word_count
    user_keywords = [item for item in (user_keywords or []) if item]
    auto_keywords = [item for item in (auto_keywords or []) if item]
    plain_text = re.sub(r"\s", "", re.sub(r"<[^>]*>", "", content or ""))
    actual_word_count = len(plain_text)

    user_min_count, user_max_count = _keyword_user_threshold(user_keywords)
    auto_min_count = 1

    results: Dict[str, Dict[str, Any]] = {}
    all_valid = True

    for keyword in user_keywords:
        exact_count = count_keyword_occurrences(content, keyword)
        coverage_count = count_keyword_coverage(content, keyword)
        # 사용자 입력 키워드는 "정확 일치" 기준으로 검증한다.
        is_under_min = exact_count < user_min_count
        is_over_max = exact_count > user_max_count
        is_valid = (not is_under_min) and (not is_over_max)
        results[keyword] = {
            "count": exact_count,
            "exactCount": exact_count,
            "coverage": coverage_count,
            "expected": user_min_count,
            "max": user_max_count,
            "valid": is_valid,
            "type": "user",
        }
        if not is_valid:
            all_valid = False

    for keyword in auto_keywords:
        exact_count = count_keyword_occurrences(content, keyword)
        coverage_count = count_keyword_coverage(content, keyword)
        is_valid = coverage_count >= auto_min_count
        results[keyword] = {
            "count": coverage_count,
            "exactCount": exact_count,
            "coverage": coverage_count,
            "expected": auto_min_count,
            "valid": is_valid,
            "type": "auto",
        }

    all_keywords = [*user_keywords, *auto_keywords]
    total_keyword_chars = 0
    for keyword in all_keywords:
        occurrences = count_keyword_coverage(content, keyword)
        total_keyword_chars += len(re.sub(r"\s", "", keyword)) * occurrences
    density = (total_keyword_chars / actual_word_count * 100) if actual_word_count else 0

    return {
        "valid": all_valid,
        "details": {
            "keywords": results,
            "density": {
                "value": f"{density:.2f}",
                "valid": True,
                "optimal": 1.5 <= density <= 2.5,
            },
            "wordCount": actual_word_count,
        },
    }


async def _generate_draft_text(
    prompt: str,
    model_name: str,
    generate_fn: Optional[Callable[..., Awaitable[str]]] = None,
) -> str:
    if generate_fn:
        try:
            candidate = generate_fn(prompt, model_name)
        except TypeError:
            candidate = generate_fn(prompt)
        result = await candidate
        return str(result or "")

    from agents.common.gemini_client import generate_content_async

    return await generate_content_async(
        prompt,
        model_name=model_name,
        temperature=1.0,
    )


async def validate_and_retry(
    *,
    prompt: str,
    model_name: str,
    full_name: str | None = None,
    full_region: str | None = None,
    target_word_count: Optional[int] = None,
    user_keywords: Optional[Sequence[str]] = None,
    auto_keywords: Optional[Sequence[str]] = None,
    status: str | None = None,
    fact_allowlist: Optional[Sequence[str]] = None,
    rag_context: Optional[str] = None,
    author_name: Optional[str] = None,
    topic: Optional[str] = None,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    max_attempts: int = 3,
    max_critic_attempts: int = 2,
    generate_fn: Optional[Callable[..., Awaitable[str]]] = None,
) -> str:
    """AI 응답 생성 + 휴리스틱 검증 + Critic/Corrector 루프."""

    _ = (full_region, target_word_count, auto_keywords)
    user_keywords = list(user_keywords or [])
    status_value = status or ""
    author = author_name or full_name
    critic_model = "gemini-2.5-flash"
    corrector_model = "gemini-2.5-flash"

    def notify_progress(stage_id: str, additional_info: Optional[Dict[str, Any]] = None) -> None:
        if not callable(on_progress):
            return
        try:
            on_progress(create_progress_state(stage_id, additional_info or {}))
        except Exception as exc:
            logger.warning("Progress 콜백 오류: %s", exc)

    best_version: Optional[str] = None
    best_score = 0
    draft: Optional[str] = None
    heuristic_passed = False

    notify_progress("DRAFTING")

    for attempt in range(1, max_attempts + 1):
        logger.info("원고 생성 시도 (%s/%s)", attempt, max_attempts)

        try:
            candidate = await _generate_draft_text(prompt, model_name, generate_fn=generate_fn)
        except Exception as exc:
            logger.warning("원고 생성 실패 (%s/%s): %s", attempt, max_attempts, exc)
            continue

        if not candidate or len(candidate.strip()) < 100:
            logger.warning("응답이 너무 짧아 재시도합니다 (%s/%s)", attempt, max_attempts)
            continue

        notify_progress("BASIC_CHECK", {"attempt": attempt})
        heuristic_result = await run_heuristic_validation(
            candidate,
            status_value,
            "",
            {
                "useLLM": False,
                "factAllowlist": fact_allowlist,
                "userKeywords": user_keywords,
                "modelName": model_name,
            },
        )

        issues = list(heuristic_result.get("issues") or [])
        draft = candidate

        if heuristic_result.get("passed", False):
            heuristic_passed = True
            best_version = candidate
            best_score = max(best_score, 70)
            logger.info("휴리스틱 검증 통과 (%s/%s)", attempt, max_attempts)
            break

        estimated_score = max(10, 70 - (len(issues) * 15))
        if estimated_score > best_score:
            best_score = estimated_score
            best_version = candidate

        logger.warning("휴리스틱 검증 실패 (%s/%s): %s", attempt, max_attempts, issues)
        if attempt < max_attempts:
            notify_progress("DRAFTING", {"attempt": attempt + 1})

    if not heuristic_passed:
        logger.error("%s회 시도 후에도 휴리스틱 검증 실패", max_attempts)
        fallback = best_version or build_fallback_draft(
            {
                "topic": topic,
                "fullName": full_name,
                "userKeywords": user_keywords,
            }
        )
        notify_progress("COMPLETED", {"warning": "품질 검증 일부 실패", "score": best_score})
        return fallback

    guidelines = summarize_guidelines(status_value, topic)
    current_draft = draft or ""
    critic_attempt = 0

    while critic_attempt < max_critic_attempts:
        critic_attempt += 1
        retry_msg = create_retry_message(critic_attempt, max_critic_attempts, best_score)
        notify_progress(
            "EDITOR_REVIEW",
            {
                "attempt": critic_attempt,
                "message": retry_msg.get("message"),
                "detail": retry_msg.get("detail"),
            },
        )

        critic_report = await run_critic_review(
            draft=current_draft,
            rag_context=rag_context,
            guidelines=guidelines,
            status=status_value,
            topic=topic,
            author_name=author,
            model_name=critic_model,
        )

        score = int(critic_report.get("score") or 0)
        if score > best_score:
            best_score = score
            best_version = current_draft

        if critic_report.get("passed") or (not critic_report.get("needsRetry")):
            notify_progress("FINALIZING")
            final_check = await run_heuristic_validation(
                current_draft,
                status_value,
                "",
                {
                    "useLLM": True,
                    "factAllowlist": fact_allowlist,
                },
            )

            if not final_check.get("passed", True):
                details = final_check.get("details") or {}
                election_law = details.get("electionLaw") or {}
                violations = election_law.get("violations") or []
                if violations:
                    correction_result = await apply_corrections(
                        draft=current_draft,
                        violations=[
                            {
                                "type": "HARD",
                                "field": "content",
                                "issue": item.get("reason"),
                                "suggestion": f"\"{item.get('sentence', '')}\" 표현을 수정하세요",
                                "severity": "HARD",
                                "location": "본문",
                                "problematic": item.get("sentence", ""),
                            }
                            for item in violations
                        ],
                        rag_context=rag_context,
                        author_name=author,
                        status=status_value,
                        model_name=corrector_model,
                    )
                    if correction_result.get("success") and (not correction_result.get("unchanged")):
                        current_draft = str(correction_result.get("corrected") or current_draft)

            notify_progress("COMPLETED", {"score": score})
            return current_draft

        violations = list(critic_report.get("violations") or [])
        if has_hard_violations(critic_report):
            notify_progress("CORRECTING", {"violations": summarize_violations(violations)})
            correction_result = await apply_corrections(
                draft=current_draft,
                violations=violations,
                rag_context=rag_context,
                author_name=author,
                status=status_value,
                model_name=corrector_model,
            )
            if correction_result.get("success") and (not correction_result.get("unchanged")):
                current_draft = str(correction_result.get("corrected") or current_draft)
            else:
                logger.warning("Corrector 수정 실패: %s", correction_result.get("error") or "변경 없음")
        else:
            notify_progress("COMPLETED", {"score": score, "warnings": len(violations)})
            return current_draft

    notify_progress(
        "COMPLETED",
        {
            "score": best_score,
            "warning": "일부 품질 기준 미달 - 수동 검토 권장",
        },
    )
    final_draft = best_version if best_score >= 70 else current_draft
    return final_draft or current_draft or (draft or "")


async def evaluate_quality_with_llm(content: str, model_name: str) -> Dict[str, Any]:
    """Legacy 호환 함수 (Critic 대체 이전 API)."""

    _ = (content, model_name)
    return {"passed": True, "issues": [], "suggestions": []}


# JS 호환 별칭
extractSentences = extract_sentences
isAllowedEnding = is_allowed_ending
isExplicitPledge = is_explicit_pledge
containsPledgeCandidate = contains_pledge_candidate
checkPledgesWithLLM = check_pledges_with_llm
detectElectionLawViolationHybrid = detect_election_law_violation_hybrid
detectSentenceRepetition = detect_sentence_repetition
detectPhraseRepetition = detect_phrase_repetition
detectNearDuplicateSentences = detect_near_duplicate_sentences
detectElectionLawViolation = detect_election_law_violation
extractDateWeekdayPairs = extract_date_weekday_pairs
validateDateWeekdayPairs = validate_date_weekday_pairs
repairDateWeekdayPairs = repair_date_weekday_pairs
validateTitleQuality = validate_title_quality
runHeuristicValidationSync = run_heuristic_validation_sync
runHeuristicValidation = run_heuristic_validation
detectBipartisanForbiddenPhrases = detect_bipartisan_forbidden_phrases
calculatePraiseProportion = calculate_praise_proportion
validateBipartisanPraise = validate_bipartisan_praise
validateKeyPhraseInclusion = validate_key_phrase_inclusion
validateCriticismTarget = validate_criticism_target
countKeywordOccurrences = count_keyword_occurrences
buildKeywordVariants = build_keyword_variants
countKeywordCoverage = count_keyword_coverage
buildFallbackDraft = build_fallback_draft
validateKeywordInsertion = validate_keyword_insertion
enforceKeywordRequirements = enforce_keyword_requirements
enforceRepetitionRequirements = enforce_repetition_requirements
validateAndRetry = validate_and_retry
evaluateQualityWithLLM = evaluate_quality_with_llm


__all__ = [
    "ALLOWED_ENDINGS",
    "EXPLICIT_PLEDGE_PATTERNS",
    "BIPARTISAN_FORBIDDEN_PHRASES",
    "GENERATION_STAGES",
    "extract_sentences",
    "is_allowed_ending",
    "is_explicit_pledge",
    "contains_pledge_candidate",
    "check_pledges_with_llm",
    "detect_election_law_violation_hybrid",
    "detect_sentence_repetition",
    "detect_phrase_repetition",
    "detect_near_duplicate_sentences",
    "detect_election_law_violation",
    "extract_date_weekday_pairs",
    "validate_date_weekday_pairs",
    "repair_date_weekday_pairs",
    "validate_title_quality",
    "run_heuristic_validation_sync",
    "run_heuristic_validation",
    "detect_bipartisan_forbidden_phrases",
    "calculate_praise_proportion",
    "validate_bipartisan_praise",
    "validate_key_phrase_inclusion",
    "validate_criticism_target",
    "count_keyword_occurrences",
    "build_keyword_variants",
    "count_keyword_coverage",
    "build_fallback_draft",
    "validate_keyword_insertion",
    "enforce_keyword_requirements",
    "enforce_repetition_requirements",
    "validate_and_retry",
    "evaluate_quality_with_llm",
]

