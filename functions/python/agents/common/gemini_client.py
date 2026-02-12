"""
공통 Gemini 클라이언트 모듈 (google-genai SDK)
모든 에이전트가 동일한 설정/재시도/에러 처리 정책으로 Gemini API를 호출합니다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from typing import Any, Dict, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# 기본 모델명 (Node.js와 동일)
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_RETRIES = 3

# 재시도 백오프 설정
BASE_RETRY_DELAY_SEC = 1.0
MAX_RETRY_DELAY_SEC = 8.0

# 기본 generation config (Node 서비스와 동일한 기본값)
DEFAULT_TOP_K = 20
DEFAULT_TOP_P = 0.80

# Safety Settings - 정치/법률 콘텐츠 과검열 방지
SAFETY_SETTINGS = [
    types.SafetySetting(
        category="HARM_CATEGORY_HARASSMENT",
        threshold="BLOCK_ONLY_HIGH",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_HATE_SPEECH",
        threshold="BLOCK_ONLY_HIGH",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
        threshold="BLOCK_MEDIUM_AND_ABOVE",
    ),
    types.SafetySetting(
        category="HARM_CATEGORY_DANGEROUS_CONTENT",
        threshold="BLOCK_ONLY_HIGH",
    ),
]

# 싱글톤 클라이언트
_client = None


class GeminiClientError(RuntimeError):
    """Gemini 호출 실패 시 사용자 친화 메시지를 전달하기 위한 예외."""

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


def _normalize_model_name(model_name: str) -> str:
    if model_name.startswith("models/"):
        return model_name[7:]
    return model_name


def _extract_error_text(error: Exception) -> str:
    message_parts = [str(error)]
    raw_message = getattr(error, "message", None)
    if raw_message:
        message_parts.append(str(raw_message))
    status_text = getattr(error, "status_text", None)
    if status_text:
        message_parts.append(str(status_text))
    return " | ".join(part for part in message_parts if part).lower()


def _extract_status_code(error: Exception) -> Optional[int]:
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    status = getattr(error, "status", None)
    if isinstance(status, int):
        return status

    code = getattr(error, "code", None)
    if isinstance(code, int):
        return code

    return None


def get_user_friendly_error_message(error: Exception) -> str:
    """
    API 오류를 사용자 친화 메시지로 변환.
    Node 서비스의 에러 매핑 정책을 Python에서도 동일하게 적용한다.
    """
    error_text = _extract_error_text(error)
    status_code = _extract_status_code(error)

    # 429 Too Many Requests / quota 초과
    if (
        status_code == 429
        or "429" in error_text
        or "too many requests" in error_text
        or "quota" in error_text
        or "exceeded" in error_text
        or "resource exhausted" in error_text
    ):
        return (
            "AI 모델의 일일 사용량을 초과했습니다.\n\n"
            "내일 00시(한국시간) 이후 다시 시도해주세요.\n"
            "또는 관리자에게 문의하여 유료 플랜 업그레이드를 요청하세요.\n\n"
            "현재 무료 플랜: 하루 50회 제한"
        )

    # 401 Unauthorized / API 키 문제
    if (
        status_code == 401
        or "401" in error_text
        or "unauthorized" in error_text
        or "api key" in error_text
    ):
        return "API 인증에 실패했습니다. 관리자에게 문의해주세요."

    # 403 Forbidden / 권한 문제
    if status_code == 403 or "403" in error_text or "forbidden" in error_text:
        return "API 접근 권한이 없습니다. 관리자에게 문의해주세요."

    # 500 계열 서버 오류
    if (
        status_code in {500, 502, 503, 504}
        or "500" in error_text
        or "internal server error" in error_text
        or "service unavailable" in error_text
    ):
        return "AI 서비스에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요."

    # 네트워크/타임아웃 오류
    if (
        "timeout" in error_text
        or "timed out" in error_text
        or "deadline exceeded" in error_text
        or "econnreset" in error_text
        or "network" in error_text
        or "connection reset" in error_text
    ):
        return "네트워크 연결에 문제가 발생했습니다. 잠시 후 다시 시도해주세요."

    # 빈 응답
    if "빈 응답" in error_text or "empty response" in error_text:
        return "AI가 응답을 생성하지 못했습니다. 다른 주제로 다시 시도해주세요."

    return (
        "AI 원고 생성 중 오류가 발생했습니다.\n\n"
        f"오류 내용: {str(error)}\n\n"
        "관리자에게 문의하거나 잠시 후 다시 시도해주세요."
    )


def _should_retry(error: Exception, attempt: int, retries: int) -> bool:
    if attempt >= retries:
        return False

    status_code = _extract_status_code(error)
    if status_code in {429, 500, 502, 503, 504}:
        return True

    error_text = _extract_error_text(error)
    transient_keywords = [
        "timeout",
        "timed out",
        "deadline exceeded",
        "service unavailable",
        "internal server error",
        "connection reset",
        "econnreset",
        "network",
        "temporarily unavailable",
    ]
    return any(keyword in error_text for keyword in transient_keywords)


def _compute_backoff_sec(attempt: int) -> float:
    # 1s, 2s, 4s ... + jitter(최대 250ms)
    exponential = min(BASE_RETRY_DELAY_SEC * (2 ** (attempt - 1)), MAX_RETRY_DELAY_SEC)
    jitter = random.uniform(0, 0.25)
    return exponential + jitter


def _build_generation_config(
    temperature: float,
    max_output_tokens: int,
    response_mime_type: Optional[str],
    options: Optional[Dict[str, Any]],
) -> types.GenerateContentConfig:
    options = options or {}

    config = types.GenerateContentConfig(
        temperature=temperature,
        top_k=options.get("top_k", DEFAULT_TOP_K),
        top_p=options.get("top_p", DEFAULT_TOP_P),
        max_output_tokens=max_output_tokens,
        stop_sequences=options.get("stop_sequences", []),
        safety_settings=SAFETY_SETTINGS,
    )

    if response_mime_type:
        config.response_mime_type = response_mime_type

    return config


def _extract_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if callable(text):
        text = text()

    if not text or not str(text).strip():
        raise ValueError("Gemini API가 빈 응답을 반환했습니다.")

    return str(text)


def get_client():
    """Gemini 클라이언트 반환 (싱글톤)."""
    global _client
    if _client is not None:
        return _client

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("[GeminiClient] GEMINI_API_KEY 환경 변수가 설정되지 않았습니다.")
        return None

    key_preview = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "****"
    logger.info("[GeminiClient] API Key 설정됨: %s", key_preview)

    _client = genai.Client(api_key=api_key)
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
    """
    콘텐츠 생성 (동기).

    Args:
        prompt: 프롬프트
        model_name: 모델명 (기본: gemini-2.5-flash)
        temperature: 온도 (기본: 0.7)
        max_output_tokens: 최대 출력 토큰 (기본: 8192)
        response_mime_type: 응답 MIME 타입 (예: "application/json")
        retries: 실패 시 최대 재시도 횟수
        options: generation config 오버라이드(top_k/top_p/stop_sequences)

    Returns:
        응답 텍스트
    """
    client = get_client()
    if not client:
        raise GeminiClientError("AI 서비스 설정에 오류가 발생했습니다.")

    model_name = _normalize_model_name(model_name)
    config = _build_generation_config(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type=response_mime_type,
        options=options,
    )
    retries = max(1, int(retries or 1))

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            logger.info(
                "[GeminiClient] 동기 호출 시도 (%s/%s) - model=%s",
                attempt,
                retries,
                model_name,
            )
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            text = _extract_response_text(response)
            logger.info("[GeminiClient] 동기 호출 성공 (%s자)", len(text))
            return text
        except Exception as error:  # pragma: no cover - 외부 SDK 예외 타입 다양성 대응
            last_error = error
            logger.warning(
                "[GeminiClient] 동기 호출 실패 (%s/%s): %s",
                attempt,
                retries,
                error,
            )

            if not _should_retry(error, attempt, retries):
                break

            delay_sec = _compute_backoff_sec(attempt)
            logger.info("[GeminiClient] %.2f초 후 재시도", delay_sec)
            time.sleep(delay_sec)

    raise GeminiClientError(
        get_user_friendly_error_message(last_error or Exception("알 수 없는 오류")),
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
    """
    콘텐츠 생성 (비동기).

    Args:
        prompt: 프롬프트
        model_name: 모델명 (기본: gemini-2.5-flash)
        temperature: 온도 (기본: 0.7)
        max_output_tokens: 최대 출력 토큰 (기본: 8192)
        response_mime_type: 응답 MIME 타입 (예: "application/json")
        retries: 실패 시 최대 재시도 횟수
        options: generation config 오버라이드(top_k/top_p/stop_sequences)

    Returns:
        응답 텍스트
    """
    client = get_client()
    if not client:
        raise GeminiClientError("AI 서비스 설정에 오류가 발생했습니다.")

    model_name = _normalize_model_name(model_name)
    config = _build_generation_config(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type=response_mime_type,
        options=options,
    )
    retries = max(1, int(retries or 1))

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            logger.info(
                "[GeminiClient] 비동기 호출 시도 (%s/%s) - model=%s",
                attempt,
                retries,
                model_name,
            )
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
            text = _extract_response_text(response)
            logger.info("[GeminiClient] 비동기 호출 성공 (%s자)", len(text))
            return text
        except Exception as error:  # pragma: no cover - 외부 SDK 예외 타입 다양성 대응
            last_error = error
            logger.warning(
                "[GeminiClient] 비동기 호출 실패 (%s/%s): %s",
                attempt,
                retries,
                error,
            )

            if not _should_retry(error, attempt, retries):
                break

            delay_sec = _compute_backoff_sec(attempt)
            logger.info("[GeminiClient] %.2f초 후 비동기 재시도", delay_sec)
            await asyncio.sleep(delay_sec)

    raise GeminiClientError(
        get_user_friendly_error_message(last_error or Exception("알 수 없는 오류")),
        original_error=last_error,
    ) from last_error


# 하위 호환성을 위한 alias 함수들
def configure_genai():
    """하위 호환성: 클라이언트 초기화 확인."""
    return get_client() is not None


def get_model(model_name: str = DEFAULT_MODEL, with_json_response: bool = False):
    """
    하위 호환성: 모델 정보 반환 (실제 모델 객체 대신 설정 딕셔너리 반환).

    주의: 새 SDK에서는 이 함수 대신 generate_content() 또는
    generate_content_async()를 직접 사용하세요.
    """
    return {
        "model_name": model_name,
        "with_json_response": with_json_response,
    }
