"""??? ? ??? ??."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from agents.common.election_rules import get_election_stage
from agents.common.fact_guard import extract_numeric_tokens, find_unsupported_numeric_tokens
from agents.common.legal import ViolationDetector

from ._shared import _strip_html
from .repetition_checker import contains_pledge_candidate, extract_sentences, is_allowed_ending

logger = logging.getLogger(__name__)

_NUMBER_CLAIM_PATTERN = re.compile(r"[0-9]+%|[0-9]+명|[0-9]+건|[0-9]+억|[0-9]+조")
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


def _collect_fact_violation_items(plain_text: str) -> List[Dict[str, Any]]:
    sentences = extract_sentences(plain_text)
    violations: list[Dict[str, Any]] = []

    number_claims = _NUMBER_CLAIM_PATTERN.findall(plain_text)
    if number_claims:
        has_source = re.search(r"\[출처:|출처:|자료:", plain_text, re.IGNORECASE)
        if not has_source:
            for claim in number_claims[:3]:
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


def _collect_fact_violations(plain_text: str) -> List[Dict[str, Any]]:
    return _collect_fact_violation_items(plain_text)


async def detect_election_law_violation_hybrid(
    content: str,
    status: str | None,
    title: str = "",
    *,
    model_name: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    if not status:
        return _build_violation_response(violations=[], status=status, skipped=True)

    election_stage = get_election_stage(status)
    if not election_stage or election_stage.get("name") != "STAGE_1":
        return _build_violation_response(
            violations=[],
            status=status,
            stage_name=str(election_stage.get("name") or ""),
            skipped=True,
        )

    full_text = f"{title or ''} {content or ''}"
    sentences = extract_sentences(full_text)
    violations: list[Dict[str, Any]] = []
    llm_candidates: list[str] = []

    for sentence in sentences:
        if is_explicit_pledge(sentence):
            _append_violation_item(
                violations,
                violation_type="EXPLICIT_PLEDGE",
                severity="HIGH",
                reason="명시적 공약 표현",
                sentence=sentence,
                matched_text=sentence,
                repair_hint='"~하겠습니다" 같은 약속 표현을 정책 필요성·검토 표현으로 바꾸세요.',
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
                _append_violation_item(
                    violations,
                    violation_type="LLM_DETECTED",
                    severity="HIGH",
                    reason=str(result.get("reason") or "공약성 표현"),
                    sentence=sentence,
                    matched_text=sentence,
                    repair_hint='"~하겠습니다"류 공약성 표현을 정책 필요성·검토 표현으로 바꾸세요.',
                )

    plain_text = _strip_html(full_text)
    violations.extend(_collect_bribery_violations(plain_text))
    violations.extend(_collect_fact_violations(plain_text))
    return _build_violation_response(
        violations=violations,
        status=status,
        stage_name=str(election_stage.get("name") or ""),
    )

def detect_election_law_violation(content: str, status: str | None, title: str = "") -> Dict[str, Any]:
    if not status:
        return _build_violation_response(violations=[], status=status, skipped=True)

    election_stage = get_election_stage(status)
    if not election_stage or election_stage.get("name") != "STAGE_1":
        return _build_violation_response(
            violations=[],
            status=status,
            stage_name=str(election_stage.get("name") or ""),
            skipped=True,
        )

    plain_text = _strip_html(f"{title or ''} {content or ''}")
    sentences = extract_sentences(plain_text)

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

    violation_items: list[Dict[str, Any]] = []
    for pattern in pledge_patterns:
        matches = list(re.finditer(pattern, plain_text))
        if not matches:
            continue
        matched_text = matches[0].group(0)
        sentence = _extract_sentence_for_match(sentences, matched_text)
        _append_violation_item(
            violation_items,
            violation_type="pledge_expression",
            severity="HIGH",
            reason=f'"{matched_text}" ({len(matches)}회) - 공약성 표현',
            sentence=sentence,
            matched_text=matched_text,
            repair_hint='"~하겠습니다"를 "필요합니다", "추진이 필요합니다", "검토하겠습니다"처럼 완곡하게 바꾸세요.',
        )

    violation_items.extend(_collect_bribery_violations(plain_text))
    violation_items.extend(_collect_fact_violations(plain_text))
    return _build_violation_response(
        violations=violation_items,
        status=status,
        stage_name=str(election_stage.get("name") or ""),
    )
