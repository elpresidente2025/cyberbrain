"""
SNS 변환 핸들러 (Python 포팅).
Node.js `handlers/sns-addon.js`의 핵심 로직을 X/Threads 기준으로 이식한다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from firebase_admin import auth as firebase_auth
from firebase_admin import firestore
from firebase_functions import https_fn

from agents.common.fact_guard import build_fact_allowlist, find_unsupported_numeric_tokens
from agents.common.gemini_client import generate_content_async
from agents.templates.sns_conversion import SNS_LIMITS, build_sns_prompt
from services.sns_ranker import extract_first_balanced_json, rank_and_select, with_timeout

logger = logging.getLogger(__name__)

CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
URL_RE = re.compile(r"https?://[^\s)]+", re.IGNORECASE)
SOURCE_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9·]{2,}")
LOW_QUALITY_CTA_PATTERNS = [
    r"자세한\s*내용은\s*블로그에서\s*확인(?:해\s*)?(?:주세요|하세요)?",
    r"블로그에서\s*확인(?:해\s*)?(?:주세요|하세요)?",
    r"더\s*자세한\s*내용은\s*블로그에서",
]
SOURCE_STOPWORDS: Set[str] = {
    "그리고",
    "하지만",
    "그러나",
    "오늘",
    "이번",
    "우리",
    "시민",
    "부산",
    "후보",
    "시장",
    "정말",
    "또한",
    "대한",
    "위해",
    "통해",
    "대한민국",
}

# 사용자 제공 예시 원고 평균(공백 제외 약 111자) 기반 X 길이 정책
X_TARGET_AVG_NON_SPACE = 111
X_MIN_NON_SPACE = 60

SIGNATURE_MODE_VALUES = {"auto", "always", "never"}
SIGNATURE_AUTO_HINTS = (
    "출마",
    "선거",
    "추모",
    "애도",
    "감사",
    "명절",
    "회의",
    "국정",
    "정부",
    "발표",
    "성명",
    "입장",
    "보고",
    "다짐",
)
GENERIC_SIGNATURE_NAMES = {"정치인", "작성자", "사용자", "후보", "의원"}
GENERIC_SIGNATURE_TITLES = {"정치인", "작성자", "사용자"}

SOURCE_TYPE_ALIASES = {
    "position_statement": "position_statement",
    "statement": "position_statement",
    "stance": "position_statement",
    "입장문": "position_statement",
    "내 입장문": "position_statement",
    "facebook_post": "facebook_post",
    "facebook": "facebook_post",
    "fb": "facebook_post",
    "페이스북": "facebook_post",
    "페이스북 글": "facebook_post",
    "blog_draft": "blog_draft",
    "blog_post": "blog_draft",
    "blog": "blog_draft",
    "블로그": "blog_draft",
    "블로그 원고": "blog_draft",
    "원고": "blog_draft",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _json_response(payload: Dict[str, Any], status: int = 200) -> https_fn.Response:
    return https_fn.Response(
        json.dumps(payload, ensure_ascii=False),
        status=status,
        mimetype="application/json",
    )


def _error_response(status: int, code: str, message: str) -> https_fn.Response:
    return _json_response({"error": {"code": code, "message": message}}, status=status)


def _get_request_data(req: https_fn.Request) -> Dict[str, Any]:
    data = req.get_json(silent=True) or {}
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return data if isinstance(data, dict) else {}


def _get_callable_data(req: https_fn.CallableRequest) -> Dict[str, Any]:
    data = req.data
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        return data["data"]
    return data if isinstance(data, dict) else {}


def _extract_uid(req: https_fn.Request) -> str:
    auth_header = req.headers.get("Authorization") or req.headers.get("authorization") or ""
    if not auth_header.startswith("Bearer "):
        raise ApiError(401, "unauthenticated", "로그인이 필요합니다.")
    id_token = auth_header.split("Bearer ", 1)[1].strip()
    if not id_token:
        raise ApiError(401, "unauthenticated", "유효하지 않은 인증 토큰입니다.")
    try:
        decoded = firebase_auth.verify_id_token(id_token)
        uid = decoded.get("uid")
        if not uid:
            raise ApiError(401, "unauthenticated", "유효하지 않은 인증 토큰입니다.")
        return uid
    except ApiError:
        raise
    except Exception as exc:
        logger.warning("토큰 검증 실패: %s", exc)
        raise ApiError(401, "unauthenticated", "유효하지 않은 인증 토큰입니다.") from exc


def _extract_uid_from_callable(req: https_fn.CallableRequest) -> str:
    auth = req.auth
    uid = auth.uid if auth else None
    if not uid:
        raise ApiError(401, "unauthenticated", "로그인이 필요합니다.")
    return uid


def _to_https_error(error: ApiError) -> https_fn.HttpsError:
    valid_codes = {
        "cancelled",
        "unknown",
        "invalid-argument",
        "deadline-exceeded",
        "not-found",
        "already-exists",
        "permission-denied",
        "resource-exhausted",
        "failed-precondition",
        "aborted",
        "out-of-range",
        "unimplemented",
        "internal",
        "unavailable",
        "data-loss",
        "unauthenticated",
    }
    code = error.code if error.code in valid_codes else "internal"
    return https_fn.HttpsError(code, error.message)


def count_without_space(text: str) -> int:
    if not text:
        return 0
    return sum(1 for ch in text if not ch.isspace())


def normalize_blog_url(url: Any) -> str:
    if url is None:
        return ""
    trimmed = str(url).strip()
    if not trimmed or trimmed in {"undefined", "null"}:
        return ""
    return trimmed


def normalize_source_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return "blog_draft"
    return SOURCE_TYPE_ALIASES.get(normalized, "blog_draft")


def resolve_source_content(post_data: Dict[str, Any]) -> Dict[str, str]:
    data = post_data or {}
    content = str(data.get("content") or "").strip()
    candidate_keys = (
        "sourceInput",
        "sourceContent",
        "originalContent",
        "inputContent",
        "rawContent",
        "sourceText",
    )
    source_input = ""
    for key in candidate_keys:
        value = str(data.get(key) or "").strip()
        if value:
            source_input = value
            break

    source_type_keys = (
        "sourceType",
        "inputType",
        "contentType",
        "writingSource",
        "sourceMode",
    )
    source_type = "blog_draft"
    for key in source_type_keys:
        value = str(data.get(key) or "").strip()
        if value:
            source_type = normalize_source_type(value)
            break

    resolved = source_input or content
    return {"content": resolved, "sourceType": source_type}


def normalize_signature_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in SIGNATURE_MODE_VALUES else "auto"


def build_profile_signature(user_profile: Dict[str, Any], user_info: Dict[str, Any]) -> str:
    profile = user_profile or {}
    _ = user_info  # 프로필 기반(2순위)만 사용

    name = str(
        profile.get("name")
        or profile.get("fullName")
        or profile.get("displayName")
        or ""
    ).strip()
    title = str(profile.get("customTitle") or profile.get("position") or "").strip()

    if not name or name in GENERIC_SIGNATURE_NAMES:
        return ""
    if title in GENERIC_SIGNATURE_TITLES:
        title = ""

    if title and name:
        if name in title:
            return title
        if title in name:
            return name
        return f"{title} {name}".strip()
    return name


def should_attach_signature_auto(
    signature_mode: str,
    signature_text: str,
    post_data: Dict[str, Any],
    source_text: str,
) -> bool:
    signature = str(signature_text or "").strip()
    if not signature:
        return False

    mode = normalize_signature_mode(signature_mode)
    if mode == "never":
        return False
    if mode == "always":
        return True

    metadata_text = " ".join(
        str(post_data.get(key) or "")
        for key in ("category", "subCategory", "topic", "title")
    )
    sample_source = str(source_text or "")[:1500]
    text = f"{metadata_text}\n{sample_source}".lower()
    return any(token in text for token in SIGNATURE_AUTO_HINTS)


def inject_signature_line(content: str, signature_text: str) -> str:
    text = str(content or "").strip()
    signature = str(signature_text or "").strip()
    if not text or not signature:
        return text or signature
    if signature in text:
        return text

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return signature

    url_start = next((idx for idx, line in enumerate(lines) if has_url(line)), len(lines))
    before_url = lines[:url_start]
    after_url = lines[url_start:]

    hashtag_start = next((idx for idx, line in enumerate(before_url) if line.startswith("#")), len(before_url))
    body_lines = before_url[:hashtag_start]
    hashtag_lines = before_url[hashtag_start:]

    if body_lines and body_lines[-1] != signature:
        body_lines.append(signature)
    elif not body_lines:
        body_lines = [signature]

    merged = body_lines + hashtag_lines + after_url
    return "\n".join(merged).strip()


def wrap_text_lines(text: str, preferred: int, hard_max: int) -> List[str]:
    cleaned = re.sub(r"\s+", " ", str(text or "").strip())
    if not cleaned:
        return []

    tokens = cleaned.split(" ")
    lines: List[str] = []
    current = ""

    for token in tokens:
        if not token:
            continue
        candidate = token if not current else f"{current} {token}"
        if len(candidate) <= hard_max:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = token

        while len(current) > hard_max:
            lines.append(current[:hard_max].rstrip())
            current = current[hard_max:].lstrip()

    if current:
        lines.append(current)

    # 마지막 줄이 과도하게 짧으면 이전 줄과 병합
    if len(lines) >= 2 and len(lines[-1]) <= max(4, preferred // 4):
        merged = f"{lines[-2]} {lines[-1]}".strip()
        if len(merged) <= hard_max:
            lines[-2] = merged
            lines.pop()

    return [line.strip() for line in lines if line.strip()]


def format_post_for_readability(content: str, platform: str) -> str:
    text = str(content or "").strip()
    if not text:
        return text

    # URL/해시태그를 본문에서 먼저 분리한 뒤 본문만 래핑한다.
    url_lines = extract_urls(text)
    body_without_url = URL_RE.sub(" ", text)

    hashtag_candidates = re.findall(r"(?<!\w)#\S+", body_without_url)
    hashtag_lines: List[str] = []
    seen_hashtags = set()
    for tag in hashtag_candidates:
        normalized = str(tag or "").strip()
        if not normalized:
            continue
        if normalized in seen_hashtags:
            continue
        seen_hashtags.add(normalized)
        hashtag_lines.append(normalized)

    body_without_meta = re.sub(r"(?<!\w)#\S+", " ", body_without_url)
    body_lines = [line.strip() for line in body_without_meta.splitlines() if line.strip()]
    body_text = " ".join(body_lines).strip()
    if platform == "x":
        preferred, hard_max, block_size = 22, 28, 2
    else:
        preferred, hard_max, block_size = 24, 32, 3

    wrapped_body = wrap_text_lines(body_text, preferred, hard_max)
    formatted_body: List[str] = []
    for idx, line in enumerate(wrapped_body, start=1):
        formatted_body.append(line)
        if idx % block_size == 0 and idx < len(wrapped_body):
            formatted_body.append("")

    merged_lines = formatted_body + [line.strip() for line in url_lines if str(line).strip()] + hashtag_lines
    merged_text = "\n".join(merged_lines).strip()
    merged_text = re.sub(r"\n{3,}", "\n\n", merged_text)
    return merged_text


def build_thread_cta_text(blog_url: str) -> str:
    if not blog_url:
        return ""
    return f"전체 맥락은 블로그에서 확인하실 수 있습니다: {blog_url}"


def has_url(text: str) -> bool:
    return bool(URL_RE.search(text or ""))


def extract_urls(text: str) -> List[str]:
    return URL_RE.findall(text or "")


def strip_low_quality_blog_cta(text: str) -> str:
    cleaned = text or ""
    for pattern in LOW_QUALITY_CTA_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def trim_to_non_space_limit(text: str, non_space_limit: int) -> str:
    if non_space_limit <= 0:
        return ""
    trimmed = []
    count = 0
    for ch in text or "":
        if count >= non_space_limit:
            break
        trimmed.append(ch)
        if not ch.isspace():
            count += 1
    return "".join(trimmed).strip()


def ensure_x_link_policy(content: str, blog_url: str) -> str:
    normalized_url = normalize_blog_url(blog_url)
    cleaned = strip_low_quality_blog_cta(content)
    if not normalized_url:
        return cleaned
    if normalized_url in cleaned:
        return cleaned
    if has_url(cleaned):
        return cleaned
    return f"{cleaned}\n{normalized_url}".strip()


def enforce_x_length_with_link(content: str, blog_url: str, min_len: int, max_len: int) -> str:
    normalized_url = normalize_blog_url(blog_url)
    text = ensure_x_link_policy(content, normalized_url)
    if not normalized_url:
        return enforce_length(text, "x", {"maxLengthPerPost": max_len})

    total_len = count_without_space(text)
    if total_len <= max_len:
        return text

    body = text.replace(normalized_url, "").strip()
    link_len = count_without_space(normalized_url)
    body_limit = max(0, max_len - link_len)
    trimmed_body = trim_to_non_space_limit(body, body_limit)
    rebuilt = f"{trimmed_body}\n{normalized_url}".strip() if trimmed_body else normalized_url

    # 링크 보존이 우선이므로 최소 길이 미달은 품질 게이트에서 후속 재생성으로 처리한다.
    _ = min_len
    return rebuilt


def extract_source_signal_tokens(source_text: str, limit: int = 40) -> List[str]:
    tokens = []
    seen = set()
    for token in SOURCE_TOKEN_RE.findall(source_text or ""):
        token = token.strip()
        if len(token) < 2:
            continue
        if token in SOURCE_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= limit:
            break
    return tokens


def has_source_signal(content: str, source_text: str) -> bool:
    content = content or ""
    source_numbers = re.findall(r"\d+(?:\.\d+)?%?", source_text or "")
    if source_numbers:
        for num in source_numbers[:20]:
            if num in content:
                return True

    tokens = extract_source_signal_tokens(source_text, limit=30)
    return any(token in content for token in tokens)


def normalize_for_overlap(text: str) -> str:
    normalized = URL_RE.sub(" ", text or "")
    normalized = re.sub(r"(?<!\w)#\S+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def get_source_overlap_stats(content: str, source_text: str, sample_size: int = 30) -> Dict[str, float]:
    sampled_count = max(1, int(sample_size or 1))
    source_tokens = extract_source_signal_tokens(source_text, limit=max(sampled_count * 2, 20))
    if not source_tokens:
        return {"matched": 0.0, "sampled": 0.0, "ratio": 1.0}

    sampled = source_tokens[:sampled_count]
    normalized_content = normalize_for_overlap(content)
    matched = sum(1 for token in sampled if token in normalized_content)
    ratio = matched / len(sampled)
    return {"matched": float(matched), "sampled": float(len(sampled)), "ratio": ratio}


def validate_x_post_quality(
    content: str,
    source_text: str,
    blog_url: str,
    min_len: int,
    max_len: int,
) -> List[str]:
    issues = []
    text = content or ""
    actual_len = count_without_space(text)
    if actual_len > max_len:
        issues.append(f"길이 초과: {actual_len}자 (최대 {max_len}자)")

    if normalize_blog_url(blog_url) and not has_url(text):
        issues.append("블로그 링크가 본문에 포함되지 않음")

    if strip_low_quality_blog_cta(text) != text.strip():
        issues.append('저품질 CTA 문구("자세한 내용은 블로그에서...") 사용')

    if not has_source_signal(text, source_text):
        issues.append("원문의 고유명사/핵심 수치/핵심 주장 반영 부족")
    else:
        overlap = get_source_overlap_stats(text, source_text, sample_size=20)
        sampled = int(overlap["sampled"])
        matched = int(overlap["matched"])
        ratio = overlap["ratio"]
        if sampled >= 8 and (matched < 3 or ratio < 0.14):
            issues.append(f"원문 기반 변환 비율 부족: 핵심어 {matched}/{sampled}개 반영")

    return issues


def validate_threads_posts_quality(
    posts: List[Dict[str, Any]],
    blog_url: str,
    min_posts: int,
    max_posts: int,
    min_len: int,
    max_len: int,
    source_text: str = "",
) -> List[str]:
    issues = []
    post_count = len(posts or [])
    if post_count < min_posts or post_count > max_posts:
        issues.append(f"게시물 수 불일치: {post_count}개 (요구 {min_posts}~{max_posts}개)")

    normalized_url = normalize_blog_url(blog_url)
    if normalized_url and posts:
        last_content = str((posts[-1] or {}).get("content", "")).strip()
        if not has_url(last_content):
            issues.append("마지막 게시물에 블로그 링크가 없음")

    repeated_heads = set()
    weak_signal_count = 0
    for idx, post in enumerate(posts or [], start=1):
        content = str((post or {}).get("content", "")).strip()
        length = count_without_space(content)
        if length > max_len:
            issues.append(f"{idx}번 게시물 길이 초과: {length}자 (최대 {max_len}자)")

        normalized_head = re.sub(r"\s+", " ", content)[:28]
        if normalized_head and normalized_head in repeated_heads:
            issues.append("게시물 시작 문장이 반복됨")
            break
        repeated_heads.add(normalized_head)

        if source_text and not has_source_signal(content, source_text):
            weak_signal_count += 1

    if source_text and post_count:
        weak_threshold = max(2, (post_count + 1) // 2)
        if weak_signal_count >= weak_threshold:
            issues.append("원문 기반 변환 비율 부족: 다수 게시물에서 원문 핵심어 반영이 약함")

        merged_content = "\n".join(str((post or {}).get("content", "")).strip() for post in posts)
        overlap = get_source_overlap_stats(merged_content, source_text, sample_size=36)
        sampled = int(overlap["sampled"])
        matched = int(overlap["matched"])
        ratio = overlap["ratio"]
        if sampled >= 12 and (matched < 5 or ratio < 0.16):
            issues.append(f"원문 기반 변환 비율 부족: 타래 핵심어 {matched}/{sampled}개 반영")

    return issues


def clean_raw_content(raw_content: str) -> str:
    text = raw_content or ""
    text = re.sub(r"---\w+---", "", text)
    text = re.sub(r"\{[\s\S]*\}", "", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def clean_content(content: str) -> str:
    text = content or ""
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"</?(h[1-6]|p|div|br|li)[^>]*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(ul|ol)[^>]*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]*>", "", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def validate_hashtags(hashtags: Any, platform: str) -> List[str]:
    if not isinstance(hashtags, list):
        hashtags = []
    limit = SNS_LIMITS[platform]["hashtagLimit"]
    cleaned = []
    for tag in hashtags:
        tag_text = str(tag).strip()
        if len(tag_text) <= 1:
            continue
        if not tag_text.startswith("#"):
            tag_text = f"#{tag_text}"
        cleaned.append(tag_text)
    cleaned = cleaned[:limit]
    return cleaned if cleaned else generate_default_hashtags(platform)


def generate_default_hashtags(platform: str) -> List[str]:
    defaults = ["#정치", "#민생", "#소통"]
    return defaults[: SNS_LIMITS[platform]["hashtagLimit"]]


def enforce_length(content: str, platform: str, platform_config: Optional[Dict[str, Any]] = None) -> str:
    max_length = None
    if platform_config:
        max_length = platform_config.get("maxLength") or platform_config.get("maxLengthPerPost")
    if not max_length:
        max_length = SNS_LIMITS[platform].get("maxLength") or SNS_LIMITS[platform].get("maxLengthPerPost")
    if not max_length:
        return content

    actual = count_without_space(content)
    if actual <= max_length:
        return content

    trimmed = []
    char_count = 0
    for ch in content:
        if char_count >= max_length - 3:
            break
        trimmed.append(ch)
        if not ch.isspace():
            char_count += 1
    return "".join(trimmed).rstrip() + "..."


def try_parse_json(raw_content: str, platform: str) -> Dict[str, Any]:
    try:
        json_str = extract_first_balanced_json(raw_content) or raw_content.strip()
        parsed = json.loads(json_str)

        if isinstance(parsed.get("posts"), list) and parsed["posts"]:
            posts = []
            for idx, post in enumerate(parsed["posts"]):
                post_content = str((post or {}).get("content", "")).strip()
                if not post_content:
                    continue
                posts.append(
                    {
                        "order": int((post or {}).get("order", idx + 1)),
                        "content": post_content,
                        "wordCount": int((post or {}).get("wordCount", count_without_space(post_content))),
                    }
                )

            if posts:
                return {
                    "success": True,
                    "isThread": True,
                    "posts": posts,
                    "hashtags": parsed.get("hashtags", []),
                    "totalWordCount": int(
                        parsed.get("totalWordCount", sum(p["wordCount"] for p in posts))
                    ),
                    "postCount": int(parsed.get("postCount", len(posts))),
                }

        content = ""
        hashtags = []
        if parsed.get("content"):
            content = str(parsed.get("content", "")).strip()
            hashtags = parsed.get("hashtags", [])
        elif isinstance(parsed.get("summary"), dict):
            summary = parsed.get("summary") or {}
            content = str(summary.get("content", "")).strip()
            hashtags = summary.get("hashtags", [])
        elif isinstance(parsed.get("summary"), str):
            content = parsed.get("summary", "").strip()
        elif parsed.get("text"):
            content = str(parsed.get("text", "")).strip()
            hashtags = parsed.get("hashtags", [])

        if content and len(content) > 10:
            return {"success": True, "isThread": False, "content": content, "hashtags": hashtags}
    except Exception:
        pass
    return {"success": False}


def try_parse_delimiter(raw_content: str) -> Dict[str, Any]:
    try:
        content_match = re.search(r"---CONTENT---([\s\S]*?)---HASHTAGS---", raw_content)
        hashtag_match = re.search(r"---HASHTAGS---([\s\S]*?)$", raw_content)
        if not content_match:
            return {"success": False}

        content = content_match.group(1).strip()
        hashtags: List[str] = []
        if hashtag_match:
            for tag in re.split(r"[,\s]+", hashtag_match.group(1)):
                tag = tag.strip()
                if not tag:
                    continue
                hashtags.append(tag if tag.startswith("#") else f"#{tag}")

        if content and len(content) > 10:
            return {"success": True, "content": content, "hashtags": hashtags}
    except Exception:
        pass
    return {"success": False}


def parse_converted_content(
    raw_content: str,
    platform: str,
    platform_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    json_result = try_parse_json(raw_content, platform)

    if json_result.get("success") and json_result.get("isThread"):
        posts = []
        for post in json_result["posts"]:
            content = clean_content(post.get("content", ""))
            if not content:
                continue
            content = format_post_for_readability(content, platform)
            posts.append(
                {
                    **post,
                    "content": content,
                    "wordCount": count_without_space(content),
                }
            )
        hashtags = validate_hashtags(json_result.get("hashtags", []), platform)
        total_word_count = sum(p["wordCount"] for p in posts)
        return {
            "isThread": True,
            "posts": posts,
            "hashtags": hashtags,
            "totalWordCount": total_word_count,
            "postCount": len(posts),
        }

    content = ""
    hashtags: List[str] = []
    if json_result.get("success"):
        content = str(json_result.get("content", "")).strip()
        hashtags = json_result.get("hashtags", [])
    else:
        delimiter_result = try_parse_delimiter(raw_content)
        if delimiter_result.get("success"):
            content = delimiter_result.get("content", "")
            hashtags = delimiter_result.get("hashtags", [])
        else:
            content = clean_raw_content(raw_content)
            hashtags = generate_default_hashtags(platform)

    content = enforce_length(clean_content(content), platform, platform_config)
    content = format_post_for_readability(content, platform)
    hashtags = validate_hashtags(hashtags, platform)
    return {"isThread": False, "content": content, "hashtags": hashtags}


def collect_unsupported_numbers(text: str, allowlist: Dict[str, Any]) -> List[str]:
    if not allowlist:
        return []
    check = find_unsupported_numeric_tokens(text, allowlist)
    return list(check.get("unsupported", []))


def collect_unsupported_numbers_from_posts(posts: List[Dict[str, Any]], allowlist: Dict[str, Any]) -> List[str]:
    if not allowlist:
        return []
    unsupported = set()
    for post in posts or []:
        check = find_unsupported_numeric_tokens(post.get("content", ""), allowlist)
        for token in check.get("unsupported", []):
            unsupported.add(token)
    return list(unsupported)


def get_thread_length_stats(posts: List[Dict[str, Any]], min_length: int) -> Dict[str, Any]:
    lengths = [count_without_space((post.get("content") or "").strip()) for post in posts]
    total = sum(lengths)
    avg_length = round(total / len(lengths)) if lengths else 0
    short_count = len([length for length in lengths if length < min_length])
    return {"lengths": lengths, "averageLength": avg_length, "shortCount": short_count}


def get_thread_length_adjustment(
    posts: List[Dict[str, Any]],
    min_length: int,
    min_posts: int,
) -> Optional[Dict[str, Any]]:
    _ = posts
    _ = min_length
    _ = min_posts
    # SNS는 블로그처럼 분량을 강제로 채우지 않는다.
    return None


def generate_code(length: int = 6) -> str:
    return "".join(random.choice(CHARS) for _ in range(length))


async def generate_short_link(
    db,
    original_url: str,
    uid: str,
    post_id: str,
    platform: str,
) -> str:
    if not original_url:
        return ""

    short_code = None
    is_unique = False
    for _ in range(3):
        candidate = generate_code(6)
        doc = db.collection("short_links").document(candidate).get()
        if not doc.exists:
            short_code = candidate
            is_unique = True
            break
    if not is_unique or not short_code:
        return original_url

    db.collection("short_links").document(short_code).set(
        {
            "originalUrl": original_url,
            "shortCode": short_code,
            "userId": uid or "system",
            "postId": post_id or None,
            "platform": platform or "sns-autogen",
            "clicks": 0,
            "createdAt": firestore.SERVER_TIMESTAMP,
        }
    )
    base_url = "https://ai-secretary-6e9c8.web.app"
    return f"{base_url}/s/{short_code}"


async def apply_thread_cta_to_last_post(
    db,
    posts: List[Dict[str, Any]],
    blog_url: str,
    platform: str,
    uid: str,
    post_id: str,
    signature_text: str = "",
    include_signature: bool = False,
) -> List[Dict[str, Any]]:
    if not posts:
        return posts

    normalized_url = normalize_blog_url(blog_url)
    use_original_blog_url = platform == "x"
    short_url = ""
    if normalized_url and not use_original_blog_url:
        short_url = await generate_short_link(db, normalized_url, uid, post_id, platform)
    final_url = normalized_url if use_original_blog_url else (normalize_blog_url(short_url) or normalized_url)

    last_index = len(posts) - 1
    last_post = posts[last_index] if last_index >= 0 else {}
    last_content = str(last_post.get("content", "")).strip()
    if include_signature and signature_text:
        last_content = inject_signature_line(last_content, signature_text)

    if platform == "x":
        min_len = SNS_LIMITS["x"].get("minLengthPerPost", X_MIN_NON_SPACE)
        max_len = SNS_LIMITS["x"].get("maxLengthPerPost", X_TARGET_AVG_NON_SPACE)
        next_content = enforce_x_length_with_link(last_content, final_url, min_len, max_len)
    else:
        cta_text = build_thread_cta_text(final_url)
        if not cta_text:
            return posts
        if final_url and (final_url in last_content or has_url(last_content)):
            next_content = strip_low_quality_blog_cta(last_content)
        else:
            next_content = f"{last_content}\n{cta_text}".strip() if last_content else cta_text

    next_content = format_post_for_readability(next_content, platform)
    updated = list(posts)
    updated[last_index] = {
        **last_post,
        "content": next_content,
        "wordCount": count_without_space(next_content),
    }
    return updated


async def _convert_platform(
    db,
    platform: str,
    platform_index: int,
    *,
    original_content: str,
    cleaned_original_content: str,
    post_keywords: Any,
    user_info: Dict[str, Any],
    post_data: Dict[str, Any],
    fact_allowlist: Dict[str, Any],
    blog_url: str,
    uid: str,
    post_id_str: str,
    selected_model: str,
    signature_mode: str,
    signature_text: str,
    source_type: str,
) -> Dict[str, Any]:
    if platform_index > 0:
        await asyncio.sleep(platform_index * 2)

    platform_config = SNS_LIMITS[platform]
    thread_constraints = {
        "minPosts": platform_config.get("minPosts", 2),
        "maxPosts": platform_config.get("maxPosts", 5),
        "minLengthPerPost": platform_config.get("minLengthPerPost", X_MIN_NON_SPACE),
    }

    converted_result = None
    include_signature = should_attach_signature_auto(
        signature_mode=signature_mode,
        signature_text=signature_text,
        post_data=post_data,
        source_text=original_content,
    )

    try:
        sns_prompt = build_sns_prompt(
            original_content,
            platform,
            platform_config,
            post_keywords,
            user_info,
                {
                    "blogUrl": blog_url,
                    "category": post_data.get("category", ""),
                    "subCategory": post_data.get("subCategory", ""),
                    "topic": post_data.get("topic", ""),
                    "title": post_data.get("title", ""),
                    "sourceType": source_type,
                },
            )

        ranked = await with_timeout(
            rank_and_select(
                sns_prompt,
                platform,
                cleaned_original_content,
                {"platformConfig": platform_config, "userInfo": user_info, "sourceType": source_type},
            ),
            60,
            "랭킹 파이프라인 타임아웃 (60초)",
        )
        converted_text = ranked.get("text")

        if converted_text and str(converted_text).strip():
            parsed_result = parse_converted_content(converted_text, platform, platform_config)
            if parsed_result.get("isThread"):
                unsupported = collect_unsupported_numbers_from_posts(parsed_result.get("posts", []), fact_allowlist)
                if unsupported:
                    logger.warning("[FactGuard] %s 출처 미확인 수치: %s", platform, ", ".join(unsupported))

                min_posts = thread_constraints["minPosts"]
                posts = parsed_result.get("posts", [])
                has_valid_posts = isinstance(posts, list) and len(posts) >= min_posts
                is_valid_x = platform == "x" and isinstance(posts, list) and len(posts) == 1

                if has_valid_posts or is_valid_x:
                    thread_result = {
                        "isThread": True,
                        "posts": posts,
                        "hashtags": (
                            parsed_result.get("hashtags")
                            if parsed_result.get("hashtags")
                            else generate_default_hashtags(platform)
                        ),
                        "totalWordCount": parsed_result.get("totalWordCount", 0),
                        "postCount": parsed_result.get("postCount", len(posts)),
                    }

                    length_adjustment = (
                        get_thread_length_adjustment(
                            thread_result["posts"],
                            thread_constraints["minLengthPerPost"],
                            thread_constraints["minPosts"],
                        )
                        if platform != "x"
                        else None
                    )

                    if length_adjustment:
                        refined_prompt = build_sns_prompt(
                            original_content,
                            platform,
                            platform_config,
                            post_keywords,
                            user_info,
                            {
                                "targetPostCount": length_adjustment["targetPostCount"],
                                "blogUrl": blog_url,
                                "category": post_data.get("category", ""),
                                "subCategory": post_data.get("subCategory", ""),
                                "topic": post_data.get("topic", ""),
                                "title": post_data.get("title", ""),
                                "sourceType": source_type,
                            },
                        )
                        try:
                            refined_text = await with_timeout(
                                generate_content_async(
                                    refined_prompt,
                                    model_name=selected_model,
                                    temperature=0.25,
                                    max_output_tokens=25000,
                                    response_mime_type="application/json",
                                    retries=1,
                                ),
                                30,
                                "재생성 타임아웃",
                            )
                            refined_parsed = parse_converted_content(refined_text, platform, platform_config)
                            refined_posts = refined_parsed.get("posts", []) if refined_parsed.get("isThread") else []
                            if refined_posts and len(refined_posts) >= min_posts:
                                thread_result = {
                                    "isThread": True,
                                    "posts": refined_posts,
                                    "hashtags": (
                                        refined_parsed.get("hashtags")
                                        if refined_parsed.get("hashtags")
                                        else thread_result["hashtags"]
                                    ),
                                    "totalWordCount": refined_parsed.get("totalWordCount", 0),
                                    "postCount": refined_parsed.get("postCount", len(refined_posts)),
                                }
                        except Exception as exc:
                            logger.warning("%s 재생성 실패(원본 유지): %s", platform, exc)

                    converted_result = thread_result
            else:
                # 예외적으로 단일 포맷이 온 경우 안전 변환
                content = str(parsed_result.get("content", "")).strip()
                unsupported = collect_unsupported_numbers(content, fact_allowlist)
                if unsupported:
                    logger.warning("[FactGuard] %s 출처 미확인 수치: %s", platform, ", ".join(unsupported))
                if content:
                    converted_result = {
                        "isThread": True,
                        "posts": [{"order": 1, "content": content, "wordCount": count_without_space(content)}],
                        "hashtags": parsed_result.get("hashtags") or generate_default_hashtags(platform),
                        "totalWordCount": count_without_space(content),
                        "postCount": 1,
                    }
    except Exception as exc:
        logger.error("%s 랭킹 파이프라인 오류: %s", platform, exc)

    if not converted_result:
        logger.warning("%s fallback 콘텐츠 생성", platform)
        if platform == "x":
            fallback_core = clean_content(original_content)[:110] or "핵심 정책 메시지를 공유드립니다."
            fallback_content = strip_low_quality_blog_cta(fallback_core)
            converted_result = {
                "isThread": True,
                "posts": [{"order": 1, "content": fallback_content, "wordCount": count_without_space(fallback_content)}],
                "hashtags": generate_default_hashtags(platform),
                "totalWordCount": count_without_space(fallback_content),
                "postCount": 1,
            }
        else:
            p1 = f"{user_info.get('name', '작성자')}입니다."
            p2 = clean_content(original_content)[:160] or "핵심 내용을 공유드립니다."
            p3 = "앞으로도 소통하겠습니다."
            converted_result = {
                "isThread": True,
                "posts": [
                    {"order": 1, "content": p1, "wordCount": count_without_space(p1)},
                    {"order": 2, "content": p2, "wordCount": count_without_space(p2)},
                    {"order": 3, "content": p3, "wordCount": count_without_space(p3)},
                ],
                "hashtags": generate_default_hashtags(platform),
                "totalWordCount": count_without_space(p1) + count_without_space(p2) + count_without_space(p3),
                "postCount": 3,
            }

    posts = converted_result.get("posts", [])
    posts = await apply_thread_cta_to_last_post(
        db,
        posts,
        blog_url,
        platform,
        uid,
        post_id_str,
        signature_text=signature_text,
        include_signature=include_signature,
    )
    if platform == "x" and posts:
        x_min = platform_config.get("minLengthPerPost", X_MIN_NON_SPACE)
        x_max = platform_config.get("maxLengthPerPost", X_TARGET_AVG_NON_SPACE)
        first_content = str(posts[0].get("content", "")).strip()
        quality_issues = validate_x_post_quality(first_content, cleaned_original_content, blog_url, x_min, x_max)

        if quality_issues:
            logger.warning("X 품질 게이트 실패, 1회 재생성 시도: %s", ", ".join(quality_issues))
            retry_prompt = build_sns_prompt(
                original_content,
                platform,
                platform_config,
                post_keywords,
                user_info,
                {
                    "blogUrl": blog_url,
                    "category": post_data.get("category", ""),
                    "subCategory": post_data.get("subCategory", ""),
                    "topic": post_data.get("topic", ""),
                    "title": post_data.get("title", ""),
                    "qualityIssues": quality_issues,
                    "sourceType": source_type,
                },
            )
            try:
                retried_text = await with_timeout(
                    generate_content_async(
                        retry_prompt,
                        model_name=selected_model,
                        temperature=0.25,
                        max_output_tokens=25000,
                        response_mime_type="application/json",
                        retries=1,
                    ),
                    30,
                    "X 품질 재생성 타임아웃",
                )
                retried_parsed = parse_converted_content(retried_text, platform, platform_config)
                retried_posts = []
                if retried_parsed.get("isThread"):
                    retried_posts = retried_parsed.get("posts", [])
                else:
                    content = str(retried_parsed.get("content", "")).strip()
                    if content:
                        retried_posts = [
                            {"order": 1, "content": content, "wordCount": count_without_space(content)}
                        ]

                if retried_posts:
                    retried_posts = await apply_thread_cta_to_last_post(
                        db,
                        retried_posts,
                        blog_url,
                        platform,
                        uid,
                        post_id_str,
                        signature_text=signature_text,
                        include_signature=include_signature,
                    )
                    retried_content = str(retried_posts[0].get("content", "")).strip()
                    retried_issues = validate_x_post_quality(
                        retried_content,
                        cleaned_original_content,
                        blog_url,
                        x_min,
                        x_max,
                    )
                    if retried_issues:
                        logger.warning("X 재생성 후에도 품질 이슈 잔존: %s", ", ".join(retried_issues))
                    else:
                        posts = retried_posts
            except Exception as exc:
                logger.warning("X 품질 보정 재생성 실패(기존 결과 유지): %s", exc)
    elif platform == "threads" and posts:
        th_min_posts = platform_config.get("minPosts", 2)
        th_max_posts = platform_config.get("maxPosts", 5)
        th_min_len = platform_config.get("minLengthPerPost", 250)
        th_max_len = platform_config.get("maxLengthPerPost", 350)
        thread_issues = validate_threads_posts_quality(
            posts,
            blog_url,
            th_min_posts,
            th_max_posts,
            th_min_len,
            th_max_len,
            cleaned_original_content,
        )

        if thread_issues:
            logger.warning("Threads 품질 게이트 실패, 1회 재생성 시도: %s", ", ".join(thread_issues))
            retry_prompt = build_sns_prompt(
                original_content,
                platform,
                platform_config,
                post_keywords,
                user_info,
                {
                    "blogUrl": blog_url,
                    "category": post_data.get("category", ""),
                    "subCategory": post_data.get("subCategory", ""),
                    "topic": post_data.get("topic", ""),
                    "title": post_data.get("title", ""),
                    "qualityIssues": thread_issues,
                    "sourceType": source_type,
                },
            )
            try:
                retried_text = await with_timeout(
                    generate_content_async(
                        retry_prompt,
                        model_name=selected_model,
                        temperature=0.25,
                        max_output_tokens=25000,
                        response_mime_type="application/json",
                        retries=1,
                    ),
                    30,
                    "Threads 품질 재생성 타임아웃",
                )
                retried_parsed = parse_converted_content(retried_text, platform, platform_config)
                retried_posts = retried_parsed.get("posts", []) if retried_parsed.get("isThread") else []
                if retried_posts:
                    retried_posts = await apply_thread_cta_to_last_post(
                        db,
                        retried_posts,
                        blog_url,
                        platform,
                        uid,
                        post_id_str,
                        signature_text=signature_text,
                        include_signature=include_signature,
                    )
                    retried_issues = validate_threads_posts_quality(
                        retried_posts,
                        blog_url,
                        th_min_posts,
                        th_max_posts,
                        th_min_len,
                        th_max_len,
                        cleaned_original_content,
                    )
                    if retried_issues:
                        logger.warning("Threads 재생성 후에도 품질 이슈 잔존: %s", ", ".join(retried_issues))
                    else:
                        posts = retried_posts
                        retried_hashtags = retried_parsed.get("hashtags", [])
                        if retried_hashtags:
                            converted_result["hashtags"] = validate_hashtags(retried_hashtags, platform)
            except Exception as exc:
                logger.warning("Threads 품질 보정 재생성 실패(기존 결과 유지): %s", exc)

    total_word_count = sum(count_without_space(post.get("content", "")) for post in posts)
    converted_result["posts"] = posts
    converted_result["totalWordCount"] = total_word_count
    converted_result["postCount"] = len(posts)

    return {"platform": platform, "result": converted_result}


async def _convert_to_sns_core(uid: str, data: Dict[str, Any]) -> Dict[str, Any]:
    post_id = data.get("postId")
    model_name = data.get("modelName")
    target_platform = data.get("targetPlatform")

    if post_id is None or str(post_id).strip() in {"", "undefined", "null"}:
        raise ApiError(400, "invalid-argument", "원고 ID가 필요합니다.")
    post_id_str = str(post_id).strip()

    db = firestore.client()

    user_doc = db.collection("users").document(uid).get()
    if not user_doc.exists:
        raise ApiError(404, "not-found", "사용자를 찾을 수 없습니다.")
    user_data = user_doc.to_dict() or {}
    is_admin = user_data.get("role") == "admin" or user_data.get("isAdmin") is True

    post_doc = db.collection("posts").document(post_id_str).get()
    if not post_doc.exists:
        raise ApiError(404, "not-found", "원고를 찾을 수 없습니다.")
    post_data = post_doc.to_dict() or {}

    if post_data.get("userId") != uid:
        raise ApiError(403, "permission-denied", "본인의 원고만 변환할 수 있습니다.")

    user_profile = user_data.get("profile", {}) or {}
    user_info = {
        "name": user_profile.get("name", "정치인"),
        "position": user_profile.get("position", "의원"),
        "region": user_profile.get("region", "지역"),
        "experience": user_profile.get("experience", ""),
        "values": user_profile.get("values", ""),
        "tone": user_profile.get("tone", "formal"),
    }
    signature_mode = normalize_signature_mode(
        data.get("signatureMode")
        or post_data.get("snsSignatureMode")
        or user_profile.get("snsSignatureMode")
        or "auto"
    )
    signature_text = build_profile_signature(user_profile, user_info)

    source_payload = resolve_source_content(post_data)
    original_content = source_payload["content"]
    source_type = source_payload["sourceType"]
    post_keywords = post_data.get("keywords", "")
    blog_url = normalize_blog_url(post_data.get("publishUrl"))

    platforms = list(SNS_LIMITS.keys())
    if target_platform:
        if target_platform not in platforms:
            raise ApiError(400, "invalid-argument", f"지원하지 않는 플랫폼입니다: {target_platform}")
        platforms = [target_platform]

    selected_model = model_name or "gemini-2.5-flash"
    cleaned_original_content = clean_content(original_content)
    fact_allowlist = build_fact_allowlist([original_content])

    tasks = [
        _convert_platform(
            db,
            platform,
            idx,
            original_content=original_content,
            cleaned_original_content=cleaned_original_content,
            post_keywords=post_keywords,
            user_info=user_info,
            post_data=post_data,
            fact_allowlist=fact_allowlist,
            blog_url=blog_url,
            uid=uid,
            post_id_str=post_id_str,
            selected_model=selected_model,
            signature_mode=signature_mode,
            signature_text=signature_text,
            source_type=source_type,
        )
        for idx, platform in enumerate(platforms)
    ]

    try:
        platform_results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=240)
    except asyncio.TimeoutError as exc:
        raise ApiError(500, "internal", "SNS 변환 중 타임아웃이 발생했습니다.") from exc

    results: Dict[str, Any] = {}
    for item in platform_results:
        results[item["platform"]] = item["result"]

    conversion_data = {
        "userId": uid,
        "originalPostId": post_id_str,
        "platforms": platforms,
        "originalContent": original_content,
        "results": results,
        "createdAt": firestore.SERVER_TIMESTAMP,
        "metadata": {
            "originalWordCount": len(original_content or ""),
            "platformCount": len(platforms),
            "sourceType": source_type,
        },
    }
    db.collection("sns_conversions").add(conversion_data)

    update_data: Dict[str, Any] = {"snsConvertedAt": firestore.SERVER_TIMESTAMP}
    if target_platform:
        update_data[f"snsConversions.{target_platform}"] = results[target_platform]
    else:
        update_data["snsConversions"] = results
    db.collection("posts").document(post_id_str).update(update_data)

    if not is_admin:
        now = datetime.utcnow()
        month_key = f"{now.year}-{now.month:02d}"
        db.collection("users").document(uid).update(
            {
                f"snsAddon.monthlyUsage.{month_key}": firestore.Increment(1),
                "snsAddon.lastUsedAt": firestore.SERVER_TIMESTAMP,
            }
        )

    return {
        "success": True,
        "results": results,
        "platforms": platforms,
        "metadata": conversion_data["metadata"],
    }


async def _convert_to_sns_async(req: https_fn.Request) -> Dict[str, Any]:
    uid = _extract_uid(req)
    data = _get_request_data(req)
    return await _convert_to_sns_core(uid, data)


async def _convert_to_sns_async_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    uid = _extract_uid_from_callable(req)
    data = _get_callable_data(req)
    return await _convert_to_sns_core(uid, data)


def _get_sns_usage_payload(uid: str) -> Dict[str, Any]:
    db = firestore.client()
    user_doc = db.collection("users").document(uid).get()
    if not user_doc.exists:
        raise ApiError(404, "not-found", "사용자를 찾을 수 없습니다.")
    return {
        "success": True,
        "isActive": True,
        "monthlyLimit": 999999,
        "currentMonthUsage": 0,
        "remaining": 999999,
        "accessMethod": "basic",
    }


def handle_test_sns(req: https_fn.Request) -> https_fn.Response:
    _ = req
    return _json_response({"success": True, "message": "SNS 함수가 정상 작동합니다."}, status=200)


def handle_get_sns_usage(req: https_fn.Request) -> https_fn.Response:
    if req.method == "OPTIONS":
        return https_fn.Response("", status=204)

    try:
        uid = _extract_uid(req)
        result = _get_sns_usage_payload(uid)
        return _json_response(result, status=200)
    except ApiError as exc:
        return _error_response(exc.status, exc.code, exc.message)
    except Exception as exc:  # pragma: no cover
        logger.exception("SNS 사용량 조회 실패: %s", exc)
        return _error_response(500, "internal", "SNS 사용량 조회 중 오류가 발생했습니다.")


def handle_convert_to_sns(req: https_fn.Request) -> https_fn.Response:
    if req.method == "OPTIONS":
        return https_fn.Response("", status=204)
    if req.method != "POST":
        return _error_response(405, "method-not-allowed", "POST 요청만 지원합니다.")

    try:
        result = asyncio.run(_convert_to_sns_async(req))
        return _json_response(result, status=200)
    except ApiError as exc:
        return _error_response(exc.status, exc.code, exc.message)
    except Exception as exc:  # pragma: no cover
        logger.exception("SNS 변환 실패: %s", exc)
        return _error_response(500, "internal", "SNS 변환 중 오류가 발생했습니다.")


def handle_test_sns_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    _ = req
    return {"success": True, "message": "SNS 함수가 정상 작동합니다."}


def handle_get_sns_usage_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        uid = _extract_uid_from_callable(req)
        return _get_sns_usage_payload(uid)
    except ApiError as exc:
        raise _to_https_error(exc) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("SNS 사용량 조회 실패(on_call): %s", exc)
        raise https_fn.HttpsError("internal", "SNS 사용량 조회 중 오류가 발생했습니다.") from exc


def handle_convert_to_sns_call(req: https_fn.CallableRequest) -> Dict[str, Any]:
    try:
        return asyncio.run(_convert_to_sns_async_call(req))
    except ApiError as exc:
        raise _to_https_error(exc) from exc
    except Exception as exc:  # pragma: no cover
        logger.exception("SNS 변환 실패(on_call): %s", exc)
        raise https_fn.HttpsError("internal", "SNS 변환 중 오류가 발생했습니다.") from exc
