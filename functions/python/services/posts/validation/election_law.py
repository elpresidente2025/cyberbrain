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
