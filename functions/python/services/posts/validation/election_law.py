"""??? ? ??? ??."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from agents.common.election_rules import get_election_stage
from agents.common.legal import ViolationDetector

from ._shared import _strip_html
from .repetition_checker import extract_sentences

logger = logging.getLogger(__name__)

_NUMBER_CLAIM_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)?(?:%|명|건|억|조)")
_OPPONENT_FACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(상대|경쟁|타)\s*후보.*?(했습니다|했다|받았|의혹)"),
    re.compile(r"(상대|경쟁)\s*진영.*?(했습니다|했다|받았)"),
    re.compile(r"○○\s*(후보|의원).*?(했습니다|했다)"),
)
_INDIRECT_DEFAMATION_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "rumor",
        re.compile(r"(?:라는|라고)\s*소문"),
        '"~라는 소문" 같은 전언 표현을 지우고, 확인 가능한 사실만 직접 서술하세요.',
    ),
    (
        "hearsay_statement",
        re.compile(r"(?:라는|라고)\s*말이?\s*(?:있|나)"),
        '"~라는 말이 있다" 대신 확인 가능한 사실 또는 본인의 판단만 남기세요.',
    ),
    (
        "reported_as_known",
        re.compile(r"(?:라고|라는)\s*알려져"),
        '"~라고 알려져" 같은 전달형 표현을 직접 사실 서술 또는 본인 경험 서술로 바꾸세요.',
    ),
    (
        "heard_about",
        re.compile(r"들었습니다|들은\s*바"),
        '"들었습니다/들은 바" 같은 간접전언을 삭제하고 출처가 분명한 사실만 남기세요.',
    ),
)


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _truncate_text(text: str, limit: int = 100) -> str:
    normalized = _normalize_whitespace(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _extract_sentence_for_match(sentences: List[str], fragment: str) -> str:
    token = _normalize_whitespace(fragment)
    if not token:
        return ""
    for sentence in sentences:
        normalized_sentence = _normalize_whitespace(sentence)
        if token in normalized_sentence:
            return sentence
    return ""


def _stringify_match(match: Any) -> str:
    if isinstance(match, tuple):
        return "".join(str(part or "") for part in match)
    return str(match or "")


def _append_violation_item(
    items: List[Dict[str, Any]],
    *,
    violation_type: str,
    severity: str,
    reason: str,
    sentence: str = "",
    matched_text: str = "",
    repair_hint: str = "",
) -> None:
    normalized_sentence = _truncate_text(sentence)
    normalized_match = _truncate_text(matched_text, limit=60)
    normalized_hint = _normalize_whitespace(repair_hint)

    candidate = {
        "type": str(violation_type or "").strip(),
        "severity": str(severity or "").upper(),
        "reason": str(reason or "").strip(),
        "sentence": normalized_sentence,
        "matchedText": normalized_match,
        "repairHint": normalized_hint,
    }
    if candidate not in items:
        items.append(candidate)


def _format_violation_summary(item: Dict[str, Any]) -> str:
    severity = str(item.get("severity") or "").upper()
    prefix = "🔴" if severity == "CRITICAL" else "⚠️"
    reason = str(item.get("reason") or "선거법 위반 위험").strip()
    sentence = str(item.get("sentence") or "").strip()
    repair_hint = str(item.get("repairHint") or "").strip()

    summary = f"{prefix} {reason}"
    if sentence:
        summary += f' | 문제 문장: "{sentence}"'
    if repair_hint:
        summary += f" | 수정 가이드: {repair_hint}"
    return summary


def _collect_fact_violation_items(
    plain_text: str,
    source_texts: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    sentences = extract_sentences(plain_text)
    violations: list[Dict[str, Any]] = []

    # 사용자 입력 원문에 이미 존재하는 수치는 면제한다.
    # 원재료(stanceText/newsDataText)는 사용자가 자기 SNS에 게시했던 글이므로
    # 수치의 근거는 사용자 본인에게 있다.
    source_numerics: set[str] = set()
    if source_texts:
        for src in source_texts:
            if src:
                source_numerics.update(_NUMBER_CLAIM_PATTERN.findall(str(src)))

    number_claims = _NUMBER_CLAIM_PATTERN.findall(plain_text)
    if number_claims:
        has_source = re.search(r"\[출처:|출처:|자료:", plain_text, re.IGNORECASE)
        if not has_source:
            for claim in number_claims[:3]:
                if claim in source_numerics:
                    continue
                sentence = _extract_sentence_for_match(sentences, claim)
                _append_violation_item(
                    violations,
                    violation_type="false_info_risk",
                    severity="HIGH",
                    reason=f"수치 주장 발견 ({claim}) - 출처 필수 (제250조 대비)",
                    sentence=sentence,
                    matched_text=claim,
                    repair_hint="수치 출처를 명시하거나, 출처가 없으면 수치를 삭제하세요.",
                )

    for sentence in sentences:
        for pattern in _OPPONENT_FACT_PATTERNS:
            match = pattern.search(sentence)
            if not match:
                continue
            _append_violation_item(
                violations,
                violation_type="defamation_risk",
                severity="CRITICAL",
                reason="상대 후보 관련 사실 주장 - 출처·증거 필수 (제250조, 제251조)",
                sentence=sentence,
                matched_text=match.group(0),
                repair_hint="상대 후보 관련 단정 문장은 출처를 명시하거나 평가·비방 요소를 제거하세요.",
            )

    for sentence in sentences:
        for pattern_name, pattern, repair_hint in _INDIRECT_DEFAMATION_PATTERNS:
            match = pattern.search(sentence)
            if not match:
                continue
            _append_violation_item(
                violations,
                violation_type="indirect_defamation",
                severity="HIGH",
                reason="간접사실 적시 - 후보자비방죄 해당 가능 (제251조)",
                sentence=sentence,
                matched_text=match.group(0),
                repair_hint=repair_hint,
            )

    return violations


def _build_violation_response(
    *,
    violations: List[Dict[str, Any]],
    status: str | None,
    stage_name: str = "",
    skipped: bool = False,
) -> Dict[str, Any]:
    return {
        "passed": len(violations) == 0,
        "violations": [_format_violation_summary(item) for item in violations],
        "items": violations,
        "status": status,
        "stage": stage_name,
        "hasCritical": any(str(item.get("severity") or "").upper() == "CRITICAL" for item in violations),
        "skipped": skipped,
    }



def _collect_bribery_violations(plain_text: str) -> List[Dict[str, Any]]:
    violations: list[Dict[str, Any]] = []
    sentences = extract_sentences(plain_text)
    for item in ViolationDetector.check_bribery_risk(plain_text):
        matches = item.get("matches") or []
        matched_text = _stringify_match(matches[0]) if matches else ""
        sentence = _extract_sentence_for_match(sentences, matched_text)
        _append_violation_item(
            violations,
            violation_type="BRIBERY",
            severity=str(item.get("severity") or "CRITICAL"),
            reason=item.get("reason") or "기부행위 금지 위반 위험",
            sentence=sentence,
            matched_text=matched_text,
            repair_hint="금품·경품·무상 제공처럼 해석될 수 있는 표현은 삭제하세요.",
        )
    return violations


def _collect_fact_violations(
    plain_text: str,
    source_texts: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    return _collect_fact_violation_items(plain_text, source_texts=source_texts)


async def detect_election_law_violation_hybrid(
    content: str,
    status: str | None,
    title: str = "",
    *,
    model_name: str = "gemini-2.5-flash",
    source_texts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """형사 위험(기부행위·허위사실·후보자비방)만 검증한다.

    공직선거법 제59조 3항에 따라 온라인(SNS/블로그) 게시글은
    선거운동 시기 제한이 면제되므로, 공약성 표현은 검증하지 않는다.
    """
    if not status:
        return _build_violation_response(violations=[], status=status, skipped=True)

    election_stage = get_election_stage(status)
    plain_text = _strip_html(f"{title or ''} {content or ''}")
    violations: list[Dict[str, Any]] = []
    violations.extend(_collect_bribery_violations(plain_text))
    violations.extend(_collect_fact_violations(plain_text, source_texts=source_texts))
    return _build_violation_response(
        violations=violations,
        status=status,
        stage_name=str(election_stage.get("name") or ""),
    )

def detect_election_law_violation(
    content: str,
    status: str | None,
    title: str = "",
    *,
    source_texts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """형사 위험(기부행위·허위사실·후보자비방)만 검증한다.

    공직선거법 제59조 3항에 따라 온라인(SNS/블로그) 게시글은
    선거운동 시기 제한이 면제되므로, 공약성 표현은 검증하지 않는다.
    """
    if not status:
        return _build_violation_response(violations=[], status=status, skipped=True)

    election_stage = get_election_stage(status)
    plain_text = _strip_html(f"{title or ''} {content or ''}")
    violation_items: list[Dict[str, Any]] = []
    violation_items.extend(_collect_bribery_violations(plain_text))
    violation_items.extend(_collect_fact_violations(plain_text, source_texts=source_texts))
    return _build_violation_response(
        violations=violation_items,
        status=status,
        stage_name=str(election_stage.get("name") or ""),
    )
