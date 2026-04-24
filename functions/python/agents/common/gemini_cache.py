"""
Gemini context caching helpers (Phase B-4).

Goal: register a large shared prompt prefix (e.g., StructureAgent base_prompt)
as a Gemini server-side cache once per job, so subsequent calls in the same job
can reuse the cached portion at the discounted cache-input price.

All functions are best-effort: any failure returns None / no-op so callers
silently fall back to the existing full-prompt path.
"""

from __future__ import annotations

import inspect
import logging
from typing import Optional

from google.genai import types

from .gemini_client import (
    DEFAULT_MODEL,
    _build_client_instance,
    _close_async_client,
    _normalize_model_name,
)

logger = logging.getLogger(__name__)

DEFAULT_CACHE_TTL_SEC = 900
MIN_CACHEABLE_PROMPT_CHARS = 3500


async def ensure_cache(
    *,
    base_prompt: str,
    model_name: str = DEFAULT_MODEL,
    ttl_sec: int = DEFAULT_CACHE_TTL_SEC,
    display_name: str = "structure-base",
) -> Optional[str]:
    """Register base_prompt as a Gemini cache and return its resource name.

    Returns None on any failure (size below floor, SDK incompatibility,
    auth/network/quota error). Callers should treat None as "no cache" and
    fall back to sending the full prompt as usual.
    """
    if not base_prompt or len(base_prompt) < MIN_CACHEABLE_PROMPT_CHARS:
        return None

    client = _build_client_instance()
    if client is None:
        return None

    normalized_model = _normalize_model_name(model_name)
    try:
        config = types.CreateCachedContentConfig(
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=base_prompt)],
                )
            ],
            ttl=f"{int(ttl_sec)}s",
            display_name=display_name,
        )
        created = await client.aio.caches.create(
            model=normalized_model,
            config=config,
        )
        cache_name = getattr(created, "name", None)
        if not cache_name:
            return None
        logger.info(
            "[GeminiCache] created cache name=%s model=%s ttl=%ss chars=%s",
            cache_name,
            normalized_model,
            ttl_sec,
            len(base_prompt),
        )
        return cache_name
    except Exception as exc:
        logger.warning(
            "[GeminiCache] cache create failed model=%s chars=%s: %s",
            normalized_model,
            len(base_prompt),
            exc,
        )
        return None
    finally:
        await _close_async_client(client)


async def delete_cache(name: Optional[str]) -> None:
    """Best-effort cache deletion. Silent on failure (TTL will reclaim it)."""
    if not name:
        return

    client = _build_client_instance()
    if client is None:
        return

    try:
        result = client.aio.caches.delete(name=name)
        if inspect.isawaitable(result):
            await result
        logger.debug("[GeminiCache] deleted cache name=%s", name)
    except Exception as exc:
        logger.debug("[GeminiCache] cache delete failed name=%s: %s", name, exc)
    finally:
        await _close_async_client(client)
