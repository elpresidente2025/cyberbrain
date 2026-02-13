"""SNS 플랫폼별 변환 프롬프트 빌더.

Node.js `functions/prompts/builders/sns-conversion.js` 호환 API.
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict, Optional

from agents.templates.sns_conversion import (
    build_sns_natural_tone_guide as _build_sns_natural_tone_guide,
    build_threads_prompt as _build_threads_prompt,
    build_x_prompt as _build_x_prompt,
)


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
        "maxLengthPerPost": 160,
        "minLengthPerPost": 130,
        "recommendedMinLength": 130,
        "hashtagLimit": 2,
        "charsPerLine": 32,
        "name": "X(Twitter)",
        "isThread": True,
        "minPosts": 1,
        "maxPosts": 1,
    },
    "threads": {
        "maxLengthPerPost": 350,
        "minLengthPerPost": 250,
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


def _topic_title_block(options: Dict[str, Any]) -> str:
    topic = str(options.get("topic") or "")
    title = str(options.get("title") or "")
    topic_block = (
        f'\n<core_topic priority="highest">\n'
        f'  <message>{topic}</message>\n'
        f'  <instruction>이 주제의 핵심 메시지와 CTA(행동 유도)를 반드시 보존하세요.</instruction>\n'
        f'</core_topic>\n'
        if topic
        else ""
    )
    title_block = f"<source_title>{title}</source_title>\n" if title else ""
    return f"{topic_block}{title_block}"


def build_facebook_instagram_prompt(
    clean_content: str,
    platform_config: Dict[str, Any],
    user_info: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None,
) -> str:
    options = options or {}
    chars_per_line = int(platform_config.get("charsPerLine", 22))
    topic_title = _topic_title_block(options)
    natural_tone_guide = _build_sns_natural_tone_guide()

    min_len = platform_config.get('minLength', 300)
    max_len = platform_config.get('maxLength', 1000)
    hashtag_limit = platform_config.get('hashtagLimit', 5)

    return f"""아래는 {user_info.get('name', '정치인')} {user_info.get('position', '의원')}이 작성한 블로그 원고입니다. 이를 Instagram 캡션으로 변환해주세요.
{topic_title}
<source_content>
{clean_content}
</source_content>

{natural_tone_guide}

<instagram_conversion platform="instagram" chars_per_line="{chars_per_line}">
  <algorithm_optimization>
    <rule>첫 125자에 핵심 메시지 + 검색 키워드를 배치</rule>
    <rule>모바일 가독성을 위해 한 줄을 {chars_per_line}자 내외로 유지</rule>
    <rule>단순 요약보다 배경/의미/기대효과를 설명하는 해설형 캡션으로 작성</rule>
    <rule>이모지는 도입 1개 + 본문 2~3개 + CTA 1개 수준으로 제한</rule>
    <rule>해시태그는 본문 하단에 3줄 띄우고 최대 {hashtag_limit}개 사용</rule>
  </algorithm_optimization>

  <structure>
    <section order="1" name="훅">첫 문장: 타겟 독자를 부르고 궁금증을 유도</section>
    <section order="2" name="핵심 요약">바쁜 독자용 3~4줄</section>
    <section order="3" name="상세 설명">정책 배경/수치/기대효과를 구체적으로 설명</section>
    <section order="4" name="마무리">개인적 소회 또는 비전</section>
    <section order="5" name="CTA">댓글/저장 유도</section>
    <section order="6" name="해시태그">최대 {hashtag_limit}개</section>
  </structure>

  <banned_patterns>
    <rule>"자세한 내용은 블로그에서" 같은 저품질 문구</rule>
    <rule>원문에 없는 정책/수치 창작</rule>
    <rule>과도한 느낌표/감탄사 남발</rule>
  </banned_patterns>

  <output_requirements min_length="{min_len}" max_length="{max_len}" hashtag_limit="{hashtag_limit}">
    원본의 정치적 입장과 논조 유지
  </output_requirements>
</instagram_conversion>

JSON 출력 형식:
{{
  "content": "변환된 Instagram 캡션 전체 텍스트",
  "hashtags": ["#태그1", "#태그2", "#태그3"],
  "wordCount": 실제글자수
}}"""


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
    min_len = int(platform_config.get("minLengthPerPost", 130))
    max_len = int(platform_config.get("maxLengthPerPost", platform_config.get("maxLength", 250)))

    return f"""아래는 {user_info.get('name', '정치인')} {user_info.get('position', '의원')}이 작성한 블로그 원고입니다. 이를 {platform_name} 타래(thread)로 변환해주세요.

**원본 블로그 원고:**
{clean_content}

**타래 구조 ({min_posts}-{max_posts}개 게시물)**
- 각 게시물은 {min_len}-{max_len}자 권장
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

