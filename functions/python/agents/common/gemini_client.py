"""
Common Gemini client utilities.

This module centralizes model invocation, retry/backoff policy,
and structured JSON output helpers used by agents.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import random
import re
import time
from typing import Any, Dict, Iterable, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_RETRIES = 3

BASE_RETRY_DELAY_SEC = 1.0
MAX_RETRY_DELAY_SEC = 8.0

DEFAULT_TOP_K = 20
DEFAULT_TOP_P = 0.80

# LLM이 JSON 대신 반환하는 흔한 프리앰블 패턴 (lowercase 비교)
_PREAMBLE_PATTERNS = (
    "here is the json",
    "here is the requested",
    "here's the json",
    "the json output",
    "json response:",
    "아래는 json",
    "다음은 json",
)

SAFETY_SETTINGS = [
    types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_ONLY_HIGH"),
    types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_MEDIUM_AND_ABOVE"),
    types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_ONLY_HIGH"),
]

_client = None
_api_key_logged = False


class GeminiClientError(RuntimeError):
    """Raised when Gemini invocation fails."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class StructuredOutputError(GeminiClientError):
    """Raised when model output does not satisfy the structured JSON contract."""


def _normalize_model_name(model_name: str) -> str:
    if model_name.startswith("models/"):
        return model_name[7:]
    return model_name


def _extract_error_text(error: Exception) -> str:
    parts = [str(error)]
    raw_message = getattr(error, "message", None)
    if raw_message:
        parts.append(str(raw_message))
    status_text = getattr(error, "status_text", None)
    if status_text:
        parts.append(str(status_text))
    original_error = getattr(error, "original_error", None)
    if original_error:
        parts.append(str(original_error))
        nested_message = getattr(original_error, "message", None)
        if nested_message:
            parts.append(str(nested_message))
    return " | ".join(part for part in parts if part).lower()


def _extract_status_code(error: Exception) -> Optional[int]:
    for attr in ("status_code", "status", "code"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value
    return None


def get_user_friendly_error_message(error: Exception) -> str:
    error_text = _extract_error_text(error)
    status_code = _extract_status_code(error)

    if (
        status_code == 429
        or "429" in error_text
        or "too many requests" in error_text
        or "quota" in error_text
        or "resource exhausted" in error_text
    ):
        return (
            "AI 사용량 한도를 초과했습니다.\n\n"
            "잠시 후 다시 시도해 주세요."
        )

    if status_code == 401 or "unauthorized" in error_text or "api key" in error_text:
        return "API 인증에 실패했습니다. 관리자에게 문의해 주세요."

    if status_code == 403 or "forbidden" in error_text:
        return "API 접근 권한이 없습니다. 관리자에게 문의해 주세요."

    if (
        status_code in {500, 502, 503, 504}
        or "internal server error" in error_text
        or "service unavailable" in error_text
    ):
        return "AI 서비스에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."

    if (
        "timeout" in error_text
        or "timed out" in error_text
        or "deadline exceeded" in error_text
        or "network" in error_text
        or "connection reset" in error_text
        or "econnreset" in error_text
    ):
        return "네트워크 연결에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요."

    if "empty response" in error_text:
        return "AI 응답이 비어 있습니다. 다시 시도해 주세요."

    return f"AI 원고 생성 중 오류가 발생했습니다: {error}"


def _is_empty_response_error(error: Exception) -> bool:
    error_text = _extract_error_text(error)
    if "empty response" in error_text or "structured output is empty" in error_text:
        return True
    original_error = getattr(error, "original_error", None)
    if isinstance(original_error, Exception):
        original_text = _extract_error_text(original_error)
        if "empty response" in original_text or "structured output is empty" in original_text:
            return True
    return False


def _should_retry(error: Exception, attempt: int, retries: int) -> bool:
    if attempt >= retries:
        return False

    status_code = _extract_status_code(error)
    if status_code in {429, 500, 502, 503, 504}:
        return True

    error_text = _extract_error_text(error)
    transient_keywords = (
        "timeout",
        "timed out",
        "deadline exceeded",
        "service unavailable",
        "internal server error",
        "connection reset",
        "econnreset",
        "network",
        "temporarily unavailable",
    )
    if any(keyword in error_text for keyword in transient_keywords):
        return True

    if _is_empty_response_error(error):
        return True

    return False


def _compute_backoff_sec(attempt: int) -> float:
    exponential = min(BASE_RETRY_DELAY_SEC * (2 ** (attempt - 1)), MAX_RETRY_DELAY_SEC)
    jitter = random.uniform(0, 0.25)
    return exponential + jitter


def _build_generation_config(
    *,
    temperature: float,
    max_output_tokens: int,
    response_mime_type: Optional[str],
    options: Optional[Dict[str, Any]],
) -> types.GenerateContentConfig:
    opts = dict(options or {})

    config = types.GenerateContentConfig(
        temperature=temperature,
        top_k=opts.get("top_k", DEFAULT_TOP_K),
        top_p=opts.get("top_p", DEFAULT_TOP_P),
        max_output_tokens=max_output_tokens,
        stop_sequences=opts.get("stop_sequences", []),
        safety_settings=SAFETY_SETTINGS,
    )

    if response_mime_type:
        config.response_mime_type = response_mime_type

    if opts.get("response_schema") is not None:
        config.response_schema = opts["response_schema"]

    if opts.get("response_json_schema") is not None:
        config.response_json_schema = opts["response_json_schema"]

    # thinking_config: 명시적 전달 또는 JSON 요청 시 자동 비활성화
    thinking_config = opts.get("thinking_config")
    if thinking_config is not None:
        try:
            config.thinking_config = thinking_config
        except Exception:
            pass  # 모델/SDK가 thinking_config 미지원 시 무시
    elif opts.get("enable_thinking") is not True:
        try:
            config.thinking_config = types.ThinkingConfig(thinking_budget=0)
        except Exception:
            pass  # 모델/SDK가 thinking_config 미지원 시 무시

    return config


def _extract_response_text(response: Any) -> str:
    def _to_clean_text(value: Any) -> str:
        raw = value
        if callable(raw):
            try:
                raw = raw()
            except Exception:
                return ""
        if raw is None:
            return ""
        return str(raw).strip()

    text = _to_clean_text(getattr(response, "text", None))
    deferred_preamble = ""
    if text:
        if _detect_preamble(text):
            deferred_preamble = text  # parsed/parts 우선 시도 후 fallback
        else:
            return text

    parsed = getattr(response, "parsed", None)
    if callable(parsed):
        try:
            parsed = parsed()
        except Exception:
            parsed = None
    if parsed is not None:
        if isinstance(parsed, str):
            parsed_text = parsed.strip()
            if parsed_text:
                return parsed_text
        else:
            try:
                parsed_json = json.dumps(parsed, ensure_ascii=False, default=str).strip()
                if parsed_json:
                    return parsed_json
            except Exception:
                parsed_text = str(parsed).strip()
                if parsed_text and parsed_text.lower() not in {"none", "null"}:
                    return parsed_text

    candidate_texts: list[str] = []
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        candidate_text = _to_clean_text(getattr(candidate, "text", None))
        if candidate_text:
            candidate_texts.append(candidate_text)

        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            if getattr(part, "thought", False):
                continue
            part_text = _to_clean_text(getattr(part, "text", None))
            if part_text:
                candidate_texts.append(part_text)

    merged = "\n".join(part for part in candidate_texts if part).strip()
    if merged:
        return merged

    finish_reasons = []
    for candidate in candidates:
        finish_reason = getattr(candidate, "finish_reason", None)
        reason_name = _to_clean_text(getattr(finish_reason, "name", None))
        reason_text = reason_name or _to_clean_text(finish_reason)
        if reason_text:
            finish_reasons.append(reason_text)
    finish_reasons = list(dict.fromkeys(finish_reasons))

    prompt_feedback = getattr(response, "prompt_feedback", None)
    block_reason = _to_clean_text(getattr(prompt_feedback, "block_reason", None))

    # 프리앰블 텍스트라도 _parse_json_object가 JSON 추출을 시도할 수 있도록 반환
    if deferred_preamble:
        return deferred_preamble

    details = []
    if finish_reasons:
        details.append(f"finish_reasons={','.join(finish_reasons)}")
    if block_reason:
        details.append(f"block_reason={block_reason}")
    suffix = f" ({', '.join(details)})" if details else ""

    raise ValueError(f"Gemini API returned an empty response.{suffix}")


def _truncate_for_log(value: str, *, limit: int = 320) -> str:
    text = str(value or "").replace("\r", "\\r").replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[:limit] + f"...(+{len(text) - limit} chars)"


def _detect_preamble(text: str) -> bool:
    """LLM이 JSON 대신 프리앰블 텍스트만 반환했는지 감지."""
    lowered = str(text or "").lower().strip()
    return any(p in lowered for p in _PREAMBLE_PATTERNS)


def _repair_loose_json(value: str) -> str:
    """
    Try to repair common LLM JSON breakages conservatively:
    - raw newline inside string -> \\n
    - unescaped quote inside string -> \\\"
    - trailing comma before } or ]
    - missing closing quote/brackets at end
    """
    text = str(value or "")
    if not text:
        return text

    chars: list[str] = []
    stack: list[str] = []
    in_string = False
    escaped = False
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]
        if in_string:
            if escaped:
                chars.append(ch)
                escaped = False
                i += 1
                continue

            if ch == "\\":
                chars.append(ch)
                escaped = True
                i += 1
                continue

            if ch == "\r":
                i += 1
                continue

            if ch == "\n":
                chars.append("\\n")
                i += 1
                continue

            if ch == '"':
                j = i + 1
                while j < n and text[j] in " \t\r\n":
                    j += 1
                nxt = text[j] if j < n else ""
                # If next char does not look like a JSON delimiter, treat it as an inner quote.
                if nxt and nxt not in [",", "]", "}", ":"]:
                    chars.append('\\"')
                else:
                    chars.append('"')
                    in_string = False
                i += 1
                continue

            chars.append(ch)
            i += 1
            continue

        if ch == '"':
            in_string = True
            chars.append(ch)
            i += 1
            continue

        if ch in "{[":
            stack.append(ch)
            chars.append(ch)
            i += 1
            continue

        if ch in "}]":
            if not stack:
                i += 1
                continue
            open_ch = stack[-1]
            if (open_ch == "{" and ch == "}") or (open_ch == "[" and ch == "]"):
                stack.pop()
                chars.append(ch)
                i += 1
                continue

            chars.append("}" if open_ch == "{" else "]")
            stack.pop()
            continue

        chars.append(ch)
        i += 1

    if in_string:
        chars.append('"')

    while stack:
        open_ch = stack.pop()
        chars.append("}" if open_ch == "{" else "]")

    repaired = "".join(chars)
    repaired = re.sub(r",(\s*[}\]])", r"\1", repaired)
    return repaired


def _parse_json_object(
    raw_text: str,
    *,
    required_keys: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        raise StructuredOutputError("Structured output is empty.")

    text = text.lstrip("\ufeff")

    def _extract_json_from_fence(value: str) -> str:
        # 앵커 없이 검색: 프리앰블 텍스트("Here is the JSON:" 등) 뒤의 fence도 추출
        fence_match = re.search(
            r"```(?:json)?\s*(.*?)\s*```",
            value,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if fence_match:
            inner = str(fence_match.group(1) or "").strip()
            if inner:
                return inner
        return value

    def _extract_first_balanced_object(value: str) -> Optional[str]:
        start = value.find("{")
        if start < 0:
            return None
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(value)):
            ch = value[index]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
                continue
            if ch == "}":
                depth -= 1
                if depth == 0:
                    return value[start : index + 1]
        return None

    def _extract_all_balanced_objects(value: str, *, max_objects: int = 8) -> list[str]:
        objects: list[str] = []
        start: Optional[int] = None
        depth = 0
        in_string = False
        escape = False
        for index, ch in enumerate(value):
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                if depth == 0:
                    start = index
                depth += 1
                continue
            if ch == "}" and depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    objects.append(value[start : index + 1])
                    start = None
                    if len(objects) >= max_objects:
                        break
        return objects

    candidates: list[str] = []
    seen_candidates: set[str] = set()

    def _push_candidate(value: Optional[str]) -> None:
        candidate = str(value or "").strip()
        if not candidate or candidate in seen_candidates:
            return
        seen_candidates.add(candidate)
        candidates.append(candidate)
        repaired_candidate = _repair_loose_json(candidate).strip()
        if repaired_candidate and repaired_candidate not in seen_candidates:
            seen_candidates.add(repaired_candidate)
            candidates.append(repaired_candidate)

    _push_candidate(text)
    _push_candidate(_extract_json_from_fence(text))
    _push_candidate(_extract_first_balanced_object(text))
    for balanced_obj in _extract_all_balanced_objects(text):
        _push_candidate(balanced_obj)

    if re.match(r'^\s*".*"\s*$', text, flags=re.DOTALL):
        try:
            inner_text = json.loads(text)
            if isinstance(inner_text, str):
                _push_candidate(inner_text)
                _push_candidate(_extract_json_from_fence(inner_text))
                _push_candidate(_extract_first_balanced_object(inner_text))
        except Exception:
            pass

    if re.match(r'^\s*"[^"]+"\s*:\s*', text):
        _push_candidate("{" + text + "}")

    required_key_list = [str(k) for k in (required_keys or [])]
    parsed_dict_candidates: list[Dict[str, Any]] = []

    def _required_coverage(payload: Dict[str, Any]) -> int:
        if not required_key_list:
            return 0
        return sum(1 for key in required_key_list if key in payload)

    last_error: Optional[Exception] = None
    last_type_name = "unknown"
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as error:
            last_error = error
            continue

        payload = parsed
        if isinstance(payload, str):
            inner = payload.strip()
            if inner:
                try:
                    payload = json.loads(inner)
                except Exception as error:
                    last_error = error
                    last_type_name = "string"
                    continue

        if isinstance(payload, dict):
            parsed_dict_candidates.append(payload)
            if not required_key_list:
                return payload
            if _required_coverage(payload) == len(required_key_list):
                return payload
            continue

        last_type_name = type(payload).__name__

    if parsed_dict_candidates:
        # Required keys를 모두 만족하는 후보가 없으면, 가장 많이 만족하는 후보를 반환한다.
        # 호출부에서 _assert_required_keys가 최종 검증을 수행하므로 계약은 유지된다.
        best_payload = max(
            parsed_dict_candidates,
            key=lambda payload: (_required_coverage(payload), len(payload)),
        )
        return best_payload

    if _detect_preamble(text):
        logger.warning(
            "[GeminiClient] Model returned preamble text instead of JSON (retryable): %s",
            _truncate_for_log(text),
        )

    if isinstance(last_error, json.JSONDecodeError):
        snippet = _truncate_for_log(text)
        raise StructuredOutputError(
            f"Structured output is not valid JSON: {last_error} | rawSnippet={snippet}"
        ) from last_error
    if last_error is not None:
        raise StructuredOutputError(f"Structured output parse failed: {last_error}") from last_error

    raise StructuredOutputError(
        f"Structured output must be a JSON object, got {last_type_name}."
    )


def _assert_required_keys(payload: Dict[str, Any], required_keys: Optional[Iterable[str]]) -> None:
    if not required_keys:
        return
    missing = [key for key in required_keys if key not in payload]
    if missing:
        key_snapshot = ",".join(sorted(str(k) for k in payload.keys()))[:240]
        raise StructuredOutputError(
            "Structured output missing required keys: "
            f"{', '.join(str(k) for k in missing)} | payloadKeys={key_snapshot}"
        )


def _read_api_key() -> Optional[str]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("[GeminiClient] GEMINI_API_KEY is not set.")
        return None
    return api_key


def _log_api_key_preview_once(api_key: str) -> None:
    global _api_key_logged
    if _api_key_logged:
        return

    key_preview = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "****"
    logger.info("[GeminiClient] API key loaded: %s", key_preview)
    _api_key_logged = True


def _build_client_instance() -> Optional[genai.Client]:
    api_key = _read_api_key()
    if not api_key:
        return None
    _log_api_key_preview_once(api_key)
    return genai.Client(api_key=api_key)


async def _close_async_client(client: Any) -> None:
    aio_client = getattr(client, "aio", None)
    if aio_client is None:
        return

    close_method = getattr(aio_client, "aclose", None) or getattr(aio_client, "close", None)
    if not callable(close_method):
        return

    try:
        result = close_method()
        if inspect.isawaitable(result):
            await result
    except Exception as error:  # pragma: no cover
        logger.debug("[GeminiClient] async client close skipped: %s", error)


def get_client():
    """Return process-wide sync Gemini client singleton."""
    global _client
    if _client is not None:
        return _client

    _client = _build_client_instance()
    return _client


def generate_content(
    prompt: str,
    model_name: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_output_tokens: int = 8192,
    response_mime_type: Optional[str] = None,
    retries: int = DEFAULT_RETRIES,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    client = get_client()
    if not client:
        raise GeminiClientError("AI client is not initialized.")

    normalized_model = _normalize_model_name(model_name)
    config = _build_generation_config(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type=response_mime_type,
        options=options,
    )

    tries = max(1, int(retries or 1))
    last_error: Optional[Exception] = None

    for attempt in range(1, tries + 1):
        try:
            logger.info("[GeminiClient] sync call (%s/%s) model=%s", attempt, tries, normalized_model)
            response = client.models.generate_content(
                model=normalized_model,
                contents=prompt,
                config=config,
            )
            text = _extract_response_text(response)
            usage = getattr(response, "usage_metadata", None)
            if usage:
                logger.warning(
                    "[GeminiClient] sync usage model=%s prompt=%s candidates=%s thoughts=%s total=%s",
                    normalized_model,
                    getattr(usage, "prompt_token_count", "?"),
                    getattr(usage, "candidates_token_count", "?"),
                    getattr(usage, "thoughts_token_count", "?"),
                    getattr(usage, "total_token_count", "?"),
                )
            return text
        except Exception as error:  # pragma: no cover
            last_error = error
            logger.warning("[GeminiClient] sync failed (%s/%s): %s", attempt, tries, error)
            if not _should_retry(error, attempt, tries):
                break
            delay_sec = _compute_backoff_sec(attempt)
            logger.info("[GeminiClient] retry after %.2fs", delay_sec)
            time.sleep(delay_sec)

    raise GeminiClientError(
        get_user_friendly_error_message(last_error or Exception("Unknown error")),
        original_error=last_error,
    ) from last_error


async def generate_content_async(
    prompt: str,
    model_name: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_output_tokens: int = 8192,
    response_mime_type: Optional[str] = None,
    retries: int = DEFAULT_RETRIES,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    # Route to Claude client when model name starts with "claude-"
    if str(model_name or "").startswith("claude-"):
        from .claude_client import generate_content_async as _claude_generate
        return await _claude_generate(
            prompt,
            model_name=model_name,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_mime_type=response_mime_type,
            retries=retries,
            options=options,
        )

    # request-scoped async client to avoid event-loop binding issues in Cloud Functions
    client = _build_client_instance()
    if not client:
        raise GeminiClientError("AI client is not initialized.")

    normalized_model = _normalize_model_name(model_name)
    config = _build_generation_config(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type=response_mime_type,
        options=options,
    )

    tries = max(1, int(retries or 1))
    last_error: Optional[Exception] = None

    try:
        for attempt in range(1, tries + 1):
            try:
                logger.info("[GeminiClient] async call (%s/%s) model=%s", attempt, tries, normalized_model)
                response = await client.aio.models.generate_content(
                    model=normalized_model,
                    contents=prompt,
                    config=config,
                )
                text = _extract_response_text(response)
                usage = getattr(response, "usage_metadata", None)
                if usage:
                    logger.warning(
                        "[GeminiClient] async usage model=%s prompt=%s candidates=%s thoughts=%s total=%s",
                        normalized_model,
                        getattr(usage, "prompt_token_count", "?"),
                        getattr(usage, "candidates_token_count", "?"),
                        getattr(usage, "thoughts_token_count", "?"),
                        getattr(usage, "total_token_count", "?"),
                    )
                return text
            except Exception as error:  # pragma: no cover
                last_error = error
                logger.warning("[GeminiClient] async failed (%s/%s): %s", attempt, tries, error)
                if not _should_retry(error, attempt, tries):
                    break
                delay_sec = _compute_backoff_sec(attempt)
                logger.info("[GeminiClient] async retry after %.2fs", delay_sec)
                await asyncio.sleep(delay_sec)
    finally:
        await _close_async_client(client)

    raise GeminiClientError(
        get_user_friendly_error_message(last_error or Exception("Unknown error")),
        original_error=last_error,
    ) from last_error


async def generate_json_async(
    prompt: str,
    *,
    model_name: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    max_output_tokens: int = 4096,
    retries: int = DEFAULT_RETRIES,
    options: Optional[Dict[str, Any]] = None,
    response_schema: Optional[Dict[str, Any]] = None,
    required_keys: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """
    Generate structured JSON and return a validated top-level object.

    Enforced behavior:
    - response_mime_type=application/json
    - optional Gemini native response_schema
    - optional top-level required key check
    """
    merged_options: Dict[str, Any] = dict(options or {})
    if response_schema is not None:
        merged_options["response_schema"] = response_schema
    parse_retries = max(1, int(merged_options.pop("json_parse_retries", 2) or 1))
    content_retries = max(1, int(retries or 1))
    last_error: Optional[Exception] = None

    for parse_attempt in range(1, parse_retries + 1):
        try:
            raw_text = await generate_content_async(
                prompt,
                model_name=model_name,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_mime_type="application/json",
                retries=content_retries if parse_attempt == 1 else max(1, content_retries - 1),
                options=merged_options,
            )
        except (GeminiClientError, RuntimeError) as error:
            last_error = error
            if parse_attempt >= parse_retries or not _should_retry(error, parse_attempt, parse_retries):
                raise
            logger.warning(
                "[GeminiClient] structured JSON generation retry (%s/%s): %s",
                parse_attempt,
                parse_retries,
                error,
            )
            continue
        try:
            payload = _parse_json_object(raw_text, required_keys=required_keys)
            _assert_required_keys(payload, required_keys)
            return payload
        except StructuredOutputError as error:
            last_error = error
            if parse_attempt >= parse_retries:
                break
            # 프리앰블만 반환된 경우 다음 재시도에 JSON-only 지시를 추가
            if _detect_preamble(raw_text):
                prompt = prompt + (
                    "\n\n[CRITICAL: 반드시 순수한 JSON 객체만 출력하세요. "
                    "설명, 마크다운, 프리앰블 텍스트 없이 {로 시작하는 JSON만 반환하세요.]"
                )
            logger.warning(
                "[GeminiClient] structured JSON parse failed (%s/%s, preamble=%s): %s",
                parse_attempt,
                parse_retries,
                _detect_preamble(raw_text),
                error,
            )

    raise StructuredOutputError(str(last_error or "Structured output parse failed."))


def configure_genai() -> bool:
    """Backward-compatible helper."""
    return get_client() is not None


def get_model(model_name: str = DEFAULT_MODEL, with_json_response: bool = False) -> Dict[str, Any]:
    """Backward-compatible metadata helper."""
    return {
        "model_name": model_name,
        "with_json_response": with_json_response,
    }
