"""
Claude (Anthropic) client utilities.

Mirrors the gemini_client interface so the router in gemini_client
can delegate transparently when model_name starts with "claude-".
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)

DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_RETRIES = 3

BASE_RETRY_DELAY_SEC = 1.0
MAX_RETRY_DELAY_SEC = 8.0

_api_key_logged = False


class ClaudeClientError(RuntimeError):
    """Raised when Claude invocation fails."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class StructuredOutputError(ClaudeClientError):
    """Raised when model output does not satisfy the structured JSON contract."""


def _read_api_key() -> Optional[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("[ClaudeClient] ANTHROPIC_API_KEY is not set.")
        return None
    return api_key


def _log_api_key_preview_once(api_key: str) -> None:
    global _api_key_logged
    if _api_key_logged:
        return
    key_preview = f"{api_key[:12]}...{api_key[-4:]}" if len(api_key) > 16 else "****"
    logger.info("[ClaudeClient] API key loaded: %s", key_preview)
    _api_key_logged = True


def _should_retry(error: Exception, attempt: int, retries: int) -> bool:
    if attempt >= retries:
        return False

    error_text = str(error).lower()
    status_code = getattr(error, "status_code", None)

    if status_code in {429, 500, 502, 503, 529}:
        return True

    transient_keywords = (
        "overloaded",
        "timeout",
        "timed out",
        "connection",
        "temporarily unavailable",
        "rate limit",
    )
    return any(keyword in error_text for keyword in transient_keywords)


def _compute_backoff_sec(attempt: int) -> float:
    exponential = min(BASE_RETRY_DELAY_SEC * (2 ** (attempt - 1)), MAX_RETRY_DELAY_SEC)
    jitter = random.uniform(0, 0.25)
    return exponential + jitter


def get_user_friendly_error_message(error: Exception) -> str:
    error_text = str(error).lower()
    status_code = getattr(error, "status_code", None)

    if status_code == 429 or "rate limit" in error_text or "overloaded" in error_text:
        return "AI 사용량 한도를 초과했습니다.\n\n잠시 후 다시 시도해 주세요."

    if status_code == 401 or "authentication" in error_text or "api key" in error_text:
        return "API 인증에 실패했습니다. 관리자에게 문의해 주세요."

    if status_code in {500, 502, 503, 529}:
        return "AI 서비스에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."

    if "timeout" in error_text or "timed out" in error_text:
        return "네트워크 연결에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."

    return f"AI 원고 생성 중 오류가 발생했습니다: {error}"


async def generate_content_async(
    prompt: str,
    model_name: str = DEFAULT_CLAUDE_MODEL,
    temperature: float = 0.7,
    max_output_tokens: int = 8192,
    response_mime_type: Optional[str] = None,
    retries: int = DEFAULT_RETRIES,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate text content using Claude. Same signature as gemini_client."""
    import anthropic

    api_key = _read_api_key()
    if not api_key:
        raise ClaudeClientError("ANTHROPIC_API_KEY is not set.")
    _log_api_key_preview_once(api_key)

    client = anthropic.AsyncAnthropic(api_key=api_key)

    # Build system prompt for JSON mode if requested
    system_parts = []
    if response_mime_type == "application/json":
        system_parts.append(
            "You must respond with valid JSON only. "
            "No markdown fences, no preamble, no explanation — just the JSON object."
        )

    tries = max(1, int(retries or 1))
    last_error: Optional[Exception] = None

    try:
        for attempt in range(1, tries + 1):
            try:
                logger.info(
                    "[ClaudeClient] async call (%s/%s) model=%s",
                    attempt, tries, model_name,
                )
                kwargs: Dict[str, Any] = {
                    "model": model_name,
                    "max_tokens": max_output_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if system_parts:
                    kwargs["system"] = "\n".join(system_parts)

                response = await client.messages.create(**kwargs)

                # Extract text from response
                text_blocks = [
                    block.text
                    for block in response.content
                    if block.type == "text"
                ]
                text = "\n".join(text_blocks).strip()

                if not text:
                    raise ValueError("Claude API returned an empty response.")

                # Log usage
                usage = response.usage
                logger.warning(
                    "[ClaudeClient] async usage model=%s input=%s output=%s",
                    model_name,
                    getattr(usage, "input_tokens", "?"),
                    getattr(usage, "output_tokens", "?"),
                )
                return text

            except Exception as error:
                last_error = error
                logger.warning(
                    "[ClaudeClient] async failed (%s/%s): %s",
                    attempt, tries, error,
                )
                if not _should_retry(error, attempt, tries):
                    break
                delay_sec = _compute_backoff_sec(attempt)
                logger.info("[ClaudeClient] retry after %.2fs", delay_sec)
                await asyncio.sleep(delay_sec)
    finally:
        await client.close()

    raise ClaudeClientError(
        get_user_friendly_error_message(last_error or Exception("Unknown error")),
        original_error=last_error,
    )
