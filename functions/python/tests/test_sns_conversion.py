from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agents.templates.sns_conversion as sns_template
import handlers.sns_addon as sns_handler


def _run_async(coro):
    return asyncio.run(coro)


# synthetic_fixture
def test_facebook_instagram_prompt_is_supported_as_single_post() -> None:
    prompt = sns_template.build_sns_prompt(
        "{region} 교통 문제를 해결하기 위한 정책 방향을 설명드립니다.",
        "facebook-instagram",
        user_info={"name": "{user_name}", "position": "{organization} 의원"},
        options={
            "topic": "{region} 교통 대책",
            "title": "교통 대책 방향",
            "sourceType": "facebook_post",
        },
    )

    assert "facebook-instagram" in sns_template.SNS_LIMITS
    assert 'platform="facebook-instagram"' in prompt
    assert "Facebook" in prompt
    assert "Instagram" in prompt
    assert '"content": "Facebook/Instagram' in prompt
    assert '"posts"' not in prompt


# synthetic_fixture
def test_convert_platform_keeps_facebook_instagram_as_single_result(
    monkeypatch,
) -> None:
    async def _fake_rank_and_select(*_args, **_kwargs):
        return {
            "text": json.dumps(
                {
                    "content": "We will fix local traffic.\nConcrete actions follow.",
                    "hashtags": ["#traffic", "#policy"],
                    "wordCount": 32,
                },
                ensure_ascii=False,
            ),
            "ranking": {"bestIndex": 0, "rankings": [], "reason": "테스트"},
        }

    async def _raise_if_called(*_args, **_kwargs):
        raise AssertionError("facebook-instagram 단일 게시물에 CTA 후처리가 호출되면 안 됩니다.")

    monkeypatch.setattr(sns_handler, "rank_and_select", _fake_rank_and_select)
    monkeypatch.setattr(sns_handler, "apply_thread_cta_to_last_post", _raise_if_called)

    result = _run_async(
        sns_handler._convert_platform(
            object(),
            "facebook-instagram",
            0,
            original_content="{region} 교통 문제를 해결하기 위한 정책 방향을 설명드립니다.",
            cleaned_original_content="{region} 교통 문제를 해결하기 위한 정책 방향을 설명드립니다.",
            post_keywords="traffic, policy",
            user_info={"name": "{user_name}", "position": "{organization} 의원"},
            post_data={"category": "local-issues", "topic": "{region} 교통 대책", "title": "교통 대책 방향"},
            fact_allowlist={},
            blog_url="https://example.com/post",
            uid="user-1",
            post_id_str="post-1",
            selected_model="gemini-2.5-flash",
            signature_mode="never",
            signature_text="",
            source_type="facebook_post",
        )
    )

    payload = result["result"]
    assert payload["isThread"] is False
    assert "content" in payload
    assert payload["content"].startswith("We will fix local traffic.")
    assert payload["hashtags"] == ["#traffic", "#policy"]
    assert "posts" not in payload


# synthetic_fixture
def test_thread_cta_uses_original_blog_url_instead_of_short_link() -> None:
    blog_url = "https://blog.naver.com/{organization}/223456789012"
    posts = _run_async(
        sns_handler.apply_thread_cta_to_last_post(
            None,
            [{"order": 1, "content": "{region} 현장 점검 결과를 공유드립니다.", "wordCount": 18}],
            blog_url,
            "threads",
            "user-1",
            "post-1",
        )
    )

    last_post = posts[-1]
    assert blog_url in last_post["content"]
    assert "ai-secretary-6e9c8.web.app/s/" not in last_post["content"]
    assert "전체 맥락은 블로그에서 확인하실 수 있습니다" not in last_post["content"]
    assert last_post["content"].splitlines()[-1] == blog_url


# synthetic_fixture
def test_thread_cta_removes_mid_thread_blog_links_and_keeps_single_final_url() -> None:
    blog_url = "https://blog.naver.com/{organization}/223456789012"
    posts = _run_async(
        sns_handler.apply_thread_cta_to_last_post(
            None,
            [
                {
                    "order": 1,
                    "content": "{region} 현안을 정리했습니다.\nhttps://ai-secretary-6e9c8.web.app/s/abc123",
                    "wordCount": 20,
                },
                {
                    "order": 2,
                    "content": f"핵심 추진 방향입니다.\n더 자세한 내용은 블로그에서 확인해주세요: {blog_url}",
                    "wordCount": 24,
                },
            ],
            blog_url,
            "threads",
            "user-1",
            "post-1",
        )
    )

    assert blog_url not in posts[0]["content"]
    assert "ai-secretary-6e9c8.web.app/s/" not in posts[0]["content"]
    assert "더 자세한 내용은 블로그에서 확인해주세요" not in posts[1]["content"]
    assert posts[1]["content"].splitlines()[-1] == blog_url
    assert sum(post["content"].count(blog_url) for post in posts) == 1
