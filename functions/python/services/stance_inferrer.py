"""뉴스 텍스트 + RAG 컨텍스트(과거 입장 이력)로부터 topic과 stanceText를 추론.

사용자가 뉴스/데이터만 입력하고 topic·stanceText를 비워둔 경우,
이 모듈이 RAG 그래프(Facebook diary 누적 입장문)와 프로필 데이터를 참고하여
합성 topic·stanceText를 생성한다.  하류 파이프라인은 사용자가 직접 입력한 것과
동일하게 처리한다.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_NEWS_CHARS = 3000  # LLM 프롬프트에 넣을 뉴스 텍스트 최대 길이
_MAX_RAG_CHARS = 1500  # RAG 컨텍스트 최대 길이
_MAX_PROFILE_CHARS = 500  # 프로필 보조 컨텍스트 최대 길이
_TOPIC_FALLBACK_LEN = 50  # LLM 실패 시 뉴스 앞 N자를 topic으로 사용


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def extract_query_from_news(news_text: str) -> str:
    """뉴스 텍스트에서 RAG/뉴스검색에 쓸 핵심 키워드 2~3개를 추출한다.

    Returns:
        공백 구분 키워드 문자열.  실패 시 뉴스 앞 30자.
    """
    from agents.common.gemini_client import generate_content_async

    text = _truncate(news_text, _MAX_NEWS_CHARS)
    if len(text) < 20:
        return text[:30]

    prompt = f"""아래 뉴스 텍스트에서 핵심 키워드를 2~3개 추출하세요.
키워드만 공백으로 구분하여 한 줄로 출력하세요.  설명이나 번호를 붙이지 마세요.

[뉴스]
{text}"""

    try:
        result = await generate_content_async(
            prompt,
            model_name="gemini-2.5-flash",
            temperature=0.1,
            max_output_tokens=40,
        )
        keywords = str(result or "").strip()
        if keywords:
            return keywords
    except Exception as exc:
        logger.warning("[StanceInferrer] 키워드 추출 실패(무시): %s", exc)

    return _truncate(news_text, 30)


async def infer_stance_from_news(
    news_text: str,
    rag_context: str = "",
    user_profile: Dict[str, Any] | None = None,
    bio_content: str = "",
) -> Dict[str, Any]:
    """뉴스 + RAG 컨텍스트로부터 topic과 stanceText를 추론한다.

    Returns:
        ``{"topic": str, "stanceText": str, "inferred": True}``
        LLM 실패 시에도 최소한의 fallback을 반환한다.
    """
    from agents.common.gemini_client import generate_content_async

    news = _truncate(news_text, _MAX_NEWS_CHARS)
    if len(news) < 20:
        return _fallback(news)

    # RAG 컨텍스트가 있으면 각도 근거로 사용
    rag = _truncate(rag_context, _MAX_RAG_CHARS)

    # RAG가 빈 경우(신규 사용자) 프로필을 보조로 사용
    profile_hint = ""
    if not rag:
        profile_hint = _build_profile_hint(user_profile, bio_content)

    context_section = ""
    if rag:
        context_section = f"""
[사용자의 과거 입장문 (유사 주제)]
{rag}
"""
    elif profile_hint:
        context_section = f"""
[사용자 프로필]
{profile_hint}
"""

    prompt = f"""당신은 정치인 블로그 원고 작성을 돕는 편집자입니다.

아래 뉴스를 읽고, 이 사용자가 블로그에 쓸 원고의 **주제**와 **입장문**을 작성하세요.
{context_section}
[뉴스/데이터]
{news}

다음 JSON 형식으로만 출력하세요.  설명을 붙이지 마세요.
{{"topic":"뉴스의 핵심 주제를 30자 이내 한 문장으로","stanceText":"이 사용자가 이 뉴스에 대해 가질 입장·의견·주장을 200~400자로 서술"}}

규칙:
- 과거 입장문이 있으면 그 논조·관점·어휘를 참고하되, 그대로 복사하지 마세요.
- 과거 입장문이 없으면 뉴스 내용에 대한 일반적인 정치인 관점으로 작성하세요.
- stanceText는 1인칭 시점으로, 구체적인 주장과 근거를 포함하세요.
- 뉴스에 없는 사실을 지어내지 마세요."""

    try:
        raw = await generate_content_async(
            prompt,
            model_name="gemini-2.5-flash",
            temperature=0.4,
            max_output_tokens=600,
            response_mime_type="application/json",
        )
        parsed = _parse_json(raw)
        topic = str(parsed.get("topic") or "").strip()
        stance = str(parsed.get("stanceText") or "").strip()

        if not topic:
            topic = _truncate(news, _TOPIC_FALLBACK_LEN)
        if not stance:
            return _fallback(news)

        logger.info(
            "[StanceInferrer] 추론 완료 — topic=%d자, stance=%d자, rag=%s",
            len(topic), len(stance), "있음" if rag else "없음",
        )
        return {"topic": topic, "stanceText": stance, "inferred": True}

    except Exception as exc:
        logger.warning("[StanceInferrer] stance 합성 실패(fallback): %s", exc)
        return _fallback(news)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, max_len: int) -> str:
    t = str(text or "").strip()
    return t[:max_len] if len(t) > max_len else t


def _fallback(news_text: str) -> Dict[str, Any]:
    return {
        "topic": _truncate(news_text, _TOPIC_FALLBACK_LEN),
        "stanceText": "",
        "inferred": True,
    }


def _parse_json(raw: str) -> Dict[str, Any]:
    cleaned = re.sub(r"```json\s*", "", str(raw or ""))
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()
    return json.loads(cleaned)


def _build_profile_hint(
    user_profile: Dict[str, Any] | None,
    bio_content: str = "",
) -> str:
    """프로필에서 각도 추론에 유용한 정보만 추출."""
    if not user_profile and not bio_content:
        return ""

    parts: list[str] = []
    profile = user_profile or {}

    position = str(profile.get("position") or "").strip()
    if position:
        parts.append(f"직함: {position}")

    region = str(profile.get("regionMetro") or "").strip()
    district = str(profile.get("regionDistrict") or "").strip()
    if region or district:
        parts.append(f"지역: {' '.join(filter(None, [region, district]))}")

    committees = profile.get("committees")
    if isinstance(committees, list) and committees:
        parts.append(f"소관위: {', '.join(str(c) for c in committees[:3])}")

    experience = str(profile.get("politicalExperience") or "").strip()
    if experience:
        parts.append(f"경력: {experience}")

    bio = _truncate(bio_content, 300)
    if bio:
        parts.append(f"자기소개: {bio}")

    return "\n".join(parts[:5])[:_MAX_PROFILE_CHARS]
