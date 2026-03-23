"""?? ?? ???????."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Sequence

from ..corrector import apply_corrections, summarize_violations
from ..critic import has_hard_violations, run_critic_review, summarize_guidelines
from ..generation_stages import create_progress_state, create_retry_message

from .heuristics import run_heuristic_validation
from .keyword_validation import build_fallback_draft

logger = logging.getLogger(__name__)

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
