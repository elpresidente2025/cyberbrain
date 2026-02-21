"""
Gemini keyword expansion service migrated from `functions/services/gemini-expander.js`.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List

import google.generativeai as genai

logger = logging.getLogger(__name__)

_GENAI_CONFIGURED = False


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _configure_genai() -> None:
    global _GENAI_CONFIGURED
    if _GENAI_CONFIGURED:
        return

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    genai.configure(api_key=api_key)
    _GENAI_CONFIGURED = True


def generate_expansion_prompt(
    district: str,
    topic: str,
    base_keywords: List[str],
    target_count: int,
) -> str:
    base_keyword_list = f"\n참고용 기본 키워드: {', '.join(base_keywords)}" if base_keywords else ""

    return (
        "당신은 정치인을 위한 SEO 전문가입니다.\n"
        "지역구 의원 블로그 콘텐츠를 작성할 때 사용할 롱테일 키워드를 생성해 주세요.\n\n"
        f"**지역구:** {district}\n"
        f"**정책 주제:** {topic}{base_keyword_list}\n\n"
        "**요구사항:**\n"
        f"1. 총 {target_count}개의 롱테일 키워드를 생성하세요\n"
        "2. 각 키워드는 3-6개 단어로 구성하세요\n"
        "3. 지역구 이름과 주제를 자연스럽게 포함하세요\n"
        "4. 주민이 실제로 검색할 법한 구체적인 표현을 사용하세요\n"
        "5. 검색 의도가 명확한 키워드를 우선하세요\n\n"
        "**출력 형식:**\n"
        "반드시 JSON 배열 형식으로만 응답하세요.\n"
        '["키워드1", "키워드2", "키워드3"]\n'
    )


def parse_gemini_response(text: str) -> List[str]:
    try:
        match = re.search(r"\[[\s\S]*\]", str(text or ""))
        if not match:
            return []

        parsed = json.loads(match.group(0))
        if not isinstance(parsed, list):
            return []

        valid_keywords = []
        seen = set()
        for item in parsed:
            keyword = str(item or "").strip()
            if not keyword:
                continue
            if keyword in seen:
                continue
            seen.add(keyword)
            valid_keywords.append(keyword)
        return valid_keywords
    except Exception:
        return []


def generate_fallback_keywords(
    district: str,
    topic: str,
    base_keywords: List[str],
    target_count: int,
) -> List[str]:
    keywords: List[str] = []
    templates = [
        f"{district} {topic}",
        f"{district} {topic} 현황",
        f"{district} {topic} 문제점",
        f"{district} {topic} 개선",
        f"{district} {topic} 정책",
        f"{district} {topic} 주민 의견",
        f"{district} {topic} 예산",
        f"{district} {topic} 사업",
        f"{district} {topic} 계획",
        f"{district} 지역 {topic}",
        f"{district} {topic} 민원",
        f"{district} {topic} 해결 방안",
        f"{district} {topic} 지원",
        f"{district} {topic} 실태",
        f"{district} {topic} 의원",
        f"{district} {topic} 활동",
        f"{district} {topic} 필요성",
        f"{district} {topic} 변화",
        f"{district} {topic} 주민",
        f"{district} {topic} 개편",
    ]
    keywords.extend(templates)

    for base in base_keywords:
        normalized = str(base or "").strip()
        if not normalized:
            continue
        keywords.extend(
            [
                f"{district} {normalized}",
                f"{normalized} {district}",
                f"{district} {normalized} 현황",
                f"{district} {normalized} 개선",
            ]
        )

    modifiers = ["현황", "문제", "해결", "개선", "정책", "의견", "민원", "지원"]
    for modifier in modifiers:
        keywords.append(f"{district} {topic} {modifier}")

    deduped: List[str] = []
    seen = set()
    for item in keywords:
        keyword = str(item or "").strip()
        if not keyword or keyword in seen:
            continue
        seen.add(keyword)
        deduped.append(keyword)
        if len(deduped) >= target_count:
            break
    return deduped


def validate_keywords(keywords: List[str], district: str, topic: str) -> List[str]:
    _ = district
    _ = topic
    validated: List[str] = []
    for raw_keyword in keywords:
        keyword = str(raw_keyword or "").strip()
        if not keyword:
            continue

        words = [part for part in keyword.split() if part.strip()]
        if len(words) < 2:
            continue
        if len(keyword) > 100:
            continue
        if not re.search(r"[0-9A-Za-z\uAC00-\uD7A3]", keyword):
            continue

        validated.append(keyword)
    return validated


def expand_keywords_with_gemini(params: Dict[str, Any]) -> List[str]:
    district = str(params.get("district") or "")
    topic = str(params.get("topic") or "")
    base_keywords = [str(item).strip() for item in _safe_list(params.get("baseKeywords")) if str(item).strip()]
    target_count = int(params.get("targetCount") or 30)

    try:
        _configure_genai()
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = generate_expansion_prompt(district, topic, base_keywords, target_count)
        response = model.generate_content(prompt)
        text = str(getattr(response, "text", "") or "")
        expanded_keywords = parse_gemini_response(text)
        if len(expanded_keywords) == 0:
            return generate_fallback_keywords(district, topic, base_keywords, target_count)
        return expanded_keywords[:target_count]
    except Exception as exc:
        logger.warning("Gemini expansion failed: %s", exc)
        return generate_fallback_keywords(district, topic, base_keywords, target_count)


def expand_and_validate_keywords(params: Dict[str, Any]) -> List[str]:
    district = str(params.get("district") or "")
    topic = str(params.get("topic") or "")
    expanded_keywords = expand_keywords_with_gemini(params)
    validated_keywords = validate_keywords(expanded_keywords, district, topic)
    return validated_keywords
