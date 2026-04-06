"""SNS 플랫폼별 변환 프롬프트 빌더.

Node.js `functions/prompts/builders/sns-conversion.js` 호환 API.
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict, Optional

from agents.templates.sns_conversion import (
    build_facebook_instagram_prompt as _build_facebook_instagram_prompt,
    build_threads_prompt as _build_threads_prompt,
    build_x_prompt as _build_x_prompt,
)

X_TARGET_AVG_NON_SPACE = 111
X_MIN_NON_SPACE = 60
THREADS_MIN_NON_SPACE = 120


SNS_LIMITS: Dict[str, Dict[str, Any]] = {
    "facebook-instagram": {
        "minLength": 300,
        "maxLength": 1000,
        "hashtagLimit": 5,
        "charsPerLine": 22,
        "previewLimit": 125,
        "name": "Facebook/Instagram",
        "isThread": False,
    },
    "x": {
        "maxLengthPerPost": X_TARGET_AVG_NON_SPACE,
        "minLengthPerPost": X_MIN_NON_SPACE,
        "recommendedMinLength": X_TARGET_AVG_NON_SPACE,
        "hashtagLimit": 2,
        "charsPerLine": 32,
        "name": "X(Twitter)",
        "isThread": True,
        "minPosts": 1,
        "maxPosts": 1,
    },
    "threads": {
        "maxLengthPerPost": 350,
        "minLengthPerPost": THREADS_MIN_NON_SPACE,
        "recommendedMinLength": 250,
        "hashtagLimit": 3,
        "charsPerLine": 27,
        "name": "Threads",
        "isThread": True,
        "minPosts": 2,
        "maxPosts": 5,
    },
}


def clean_html_content(original_content: str) -> str:
    text = original_content or ""
    text = re.sub(r"</?(h[1-6]|p|div|br|li)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(ul|ol)[^>]*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]*>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def build_facebook_instagram_prompt(
    clean_content: str,
    platform_config: Dict[str, Any],
    user_info: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None,
) -> str:
    return _build_facebook_instagram_prompt(clean_content, platform_config, user_info, options or {})


def build_x_prompt(
    clean_content: str,
    platform_config: Dict[str, Any],
    user_info: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None,
) -> str:
    return _build_x_prompt(clean_content, platform_config, user_info, options or {})


def build_threads_prompt(
    clean_content: str,
    platform_config: Dict[str, Any],
    user_info: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None,
) -> str:
    return _build_threads_prompt(clean_content, platform_config, user_info, options or {})


def build_thread_prompt(
    clean_content: str,
    platform: str,
    platform_config: Dict[str, Any],
    user_info: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None,
) -> str:
    platform = (platform or "").strip().lower()
    options = options or {}

    if platform == "x":
        return build_x_prompt(clean_content, platform_config, user_info, options)
    if platform == "threads":
        return build_threads_prompt(clean_content, platform_config, user_info, options)

    platform_name = platform_config.get("name", platform)
    hashtag_limit = int(platform_config.get("hashtagLimit", 3))
    min_posts = int(platform_config.get("minPosts", 3))
    max_posts = int(platform_config.get("maxPosts", 7))
    min_len = int(platform_config.get("minLengthPerPost", X_MIN_NON_SPACE))
    max_len = int(platform_config.get("maxLengthPerPost", platform_config.get("maxLength", 250)))

    return f"""아래는 {user_info.get('name', '정치인')} {user_info.get('position', '의원')}이 작성한 블로그 원고입니다. 이를 {platform_name} 타래(thread)로 변환해주세요.

**원본 블로그 원고:**
{clean_content}

**타래 구조 ({min_posts}-{max_posts}개 게시물)**
- 각 게시물은 최대 {max_len}자, 분량 억지 확장 금지
- 1번: 훅/핵심 메시지
- 2~(마지막-1): 배경/핵심/근거
- 마지막: 마무리 + 해시태그 {hashtag_limit}개

**JSON 출력 형식**
{{
  "posts": [
    {{ "order": 1, "content": "첫 번째 게시물", "wordCount": 170 }},
    {{ "order": 2, "content": "두 번째 게시물", "wordCount": 180 }}
  ],
  "hashtags": ["#태그1", "#태그2"],
  "totalWordCount": 350,
  "postCount": 2
}}"""


def build_sns_prompt(
    original_content: str,
    platform: str,
    platform_config: Optional[Dict[str, Any]] = None,
    post_keywords: str = "",
    user_info: Optional[Dict[str, Any]] = None,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    _ = post_keywords  # JS 호환 인자 유지
    user_info = user_info or {}
    options = options or {}
    platform = (platform or "").strip().lower()

    config = dict(platform_config or SNS_LIMITS.get(platform) or {})
    if not config:
        raise ValueError(f"지원하지 않는 플랫폼입니다: {platform}")

    clean_content = clean_html_content(original_content)

    if platform == "facebook-instagram":
        return build_facebook_instagram_prompt(clean_content, config, user_info, options)

    return build_thread_prompt(clean_content, platform, config, user_info, options)


# JS 호환 별칭
buildSNSPrompt = build_sns_prompt
buildXPrompt = build_x_prompt
buildThreadsPrompt = build_threads_prompt
buildThreadPrompt = build_thread_prompt
cleanHTMLContent = clean_html_content


__all__ = [
    "SNS_LIMITS",
    "build_sns_prompt",
    "build_x_prompt",
    "build_threads_prompt",
    "build_thread_prompt",
    "build_facebook_instagram_prompt",
    "clean_html_content",
    "buildSNSPrompt",
    "buildXPrompt",
    "buildThreadsPrompt",
    "buildThreadPrompt",
    "cleanHTMLContent",
]
