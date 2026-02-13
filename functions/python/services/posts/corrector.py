"""Corrector Agent - 위반 사항 정정 모듈.

Node.js `functions/services/posts/corrector.js` 포팅.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Sequence

from agents.common.gemini_client import generate_content_async

logger = logging.getLogger(__name__)


def build_corrector_prompt(
    *,
    draft: str,
    violations: Sequence[Dict[str, Any]],
    rag_context: Optional[str],
    author_name: Optional[str],
    status: Optional[str],
) -> str:
    violations_list = "\n".join(
        (
            f'{i + 1}. [{v.get("severity", "SOFT")}] {v.get("type", "위반")}\n'
            f'   위치: {v.get("location", "미지정")}\n'
            f'   문제: "{v.get("problematic", "")}"\n'
            f'   수정안: {v.get("suggestion", "자연스럽게 수정")}'
        )
        for i, v in enumerate(violations)
    )

    status_guideline = ""
    if status in {"준비", "현역"}:
        status_guideline = f"""
⚠️ 중요: 현재 상태가 "{status}"이므로, "~하겠습니다" 형태의 공약 표현을 모두 제거해야 합니다.
대체 표현: "~을 검토하고 있습니다", "~이 필요합니다", "~을 위해 노력 중입니다"
"""

    return f"""당신은 원고 수정 전문가입니다.
아래 초안에서 지적된 문제점만 정확히 수정하세요.

═══════════════════════════════════════
[수정할 초안]
═══════════════════════════════════════
{draft}

═══════════════════════════════════════
[발견된 문제점 - 반드시 수정할 것]
═══════════════════════════════════════
{violations_list}
{status_guideline}

═══════════════════════════════════════
[참조 데이터 (팩트 확인용)]
수치나 사업명 수정 시 반드시 이 데이터를 참조하세요.
═══════════════════════════════════════
{rag_context or '(참조 데이터 없음 - 구체적 수치/사업명 사용 자제)'}

═══════════════════════════════════════
[수정 원칙]
═══════════════════════════════════════
1. 위에서 지적된 문제점만 수정하고, 나머지는 원문 그대로 유지
2. 글의 전체 흐름과 분량은 유지
3. 작성자 "{author_name or '의원'}님"의 입장에서 자연스럽게 수정
4. 수정된 부분도 문맥에 맞게 자연스럽게 연결

═══════════════════════════════════════
[출력 형식]
═══════════════════════════════════════
수정된 HTML 원고만 출력하세요.
설명이나 주석 없이 오직 수정된 원고 본문만 출력합니다.
JSON 형식이 아닌, HTML 형식의 원고 본문을 출력하세요."""


def clean_corrector_response(response: str) -> Optional[str]:
    if not response:
        return None

    cleaned = str(response).strip()
    cleaned = re.sub(r"^```html?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)

    if cleaned.startswith("{") and '"content"' in cleaned:
        try:
            parsed = json.loads(cleaned)
            content = parsed.get("content")
            if content:
                cleaned = str(content)
        except json.JSONDecodeError:
            pass

    return cleaned.strip()


def validate_correction(original: str, corrected: Optional[str]) -> Dict[str, Any]:
    if not corrected or len(corrected) < 100:
        return {"valid": False, "reason": "수정된 원고가 너무 짧습니다"}

    original_length = len(re.sub(r"<[^>]*>", "", original or ""))
    corrected_length = len(re.sub(r"<[^>]*>", "", corrected or ""))
    if original_length <= 0:
        return {"valid": True}

    ratio = corrected_length / original_length
    if ratio < 0.5:
        return {"valid": False, "reason": f"수정 후 분량이 너무 줄었습니다 ({round(ratio * 100)}%)"}
    if ratio > 1.5:
        return {"valid": False, "reason": f"수정 후 분량이 너무 늘었습니다 ({round(ratio * 100)}%)"}

    return {"valid": True}


async def apply_corrections(
    *,
    draft: str,
    violations: Sequence[Dict[str, Any]],
    rag_context: Optional[str],
    author_name: Optional[str],
    status: Optional[str],
    model_name: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    logger.info("Corrector Agent 시작: %s건 수정 예정", len(violations or []))

    if not violations:
        return {"success": True, "corrected": draft, "unchanged": True}

    try:
        prompt = build_corrector_prompt(
            draft=draft,
            violations=list(violations),
            rag_context=rag_context,
            author_name=author_name,
            status=status,
        )
        response = await generate_content_async(prompt, model_name=model_name, temperature=1.0)
        if not response:
            raise RuntimeError("Corrector Agent 응답 없음")

        corrected = clean_corrector_response(response)
        validation = validate_correction(draft, corrected)
        if not validation.get("valid", False):
            logger.warning("Corrector 검증 실패: %s", validation.get("reason"))
            return {"success": False, "corrected": draft, "error": validation.get("reason")}

        return {
            "success": True,
            "corrected": corrected,
            "originalLength": len(draft or ""),
            "correctedLength": len(corrected or ""),
        }
    except Exception as exc:
        logger.exception("Corrector Agent 실행 실패: %s", exc)
        return {"success": False, "corrected": draft, "error": str(exc)}


def filter_hard_violations(violations: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [item for item in (violations or []) if (item or {}).get("severity") == "HARD"]


def summarize_violations(violations: Sequence[Dict[str, Any]]) -> str:
    if not violations:
        return "위반 사항 없음"

    hard = len([v for v in violations if (v or {}).get("severity") == "HARD"])
    soft = len([v for v in violations if (v or {}).get("severity") == "SOFT"])
    political = len([v for v in violations if (v or {}).get("severity") == "POLITICAL"])

    parts: List[str] = []
    if hard:
        parts.append(f"치명적 {hard}건")
    if soft:
        parts.append(f"개선필요 {soft}건")
    if political:
        parts.append(f"권고 {political}건")

    return ", ".join(parts)


# JS 호환 별칭
buildCorrectorPrompt = build_corrector_prompt
cleanCorrectorResponse = clean_corrector_response
validateCorrection = validate_correction
applyCorrections = apply_corrections
filterHardViolations = filter_hard_violations
summarizeViolations = summarize_violations


__all__ = [
    "build_corrector_prompt",
    "clean_corrector_response",
    "validate_correction",
    "apply_corrections",
    "filter_hard_violations",
    "summarize_violations",
    "buildCorrectorPrompt",
    "cleanCorrectorResponse",
    "validateCorrection",
    "applyCorrections",
    "filterHardViolations",
    "summarizeViolations",
]
