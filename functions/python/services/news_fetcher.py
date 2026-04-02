from __future__ import annotations

import json
import logging

import requests
from bs4 import BeautifulSoup

from agents.common.gemini_client import generate_content_async

logger = logging.getLogger(__name__)


async def fetch_naver_news(topic: str, limit: int = 3) -> list:
    if not topic or not topic.strip():
        return []

    try:
        url = "https://search.naver.com/search.naver"
        params = {
            "where": "news",
            "query": topic,
            "sort": "date",
        }
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
        }

        logger.info("Fetching Naver news for topic: %s", topic)
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")
        news_list = []

        for element in soup.select(".news_area")[:limit]:
            title_node = element.select_one(".news_tit")
            if not title_node:
                continue

            summary_node = element.select_one(".news_dsc")
            press_node = element.select_one(".info.press")
            info_nodes = element.select(".info_group .info")

            news_list.append(
                {
                    "title": title_node.get("title") or title_node.get_text(strip=True),
                    "summary": summary_node.get_text(strip=True) if summary_node else "",
                    "press": press_node.get_text(strip=True) if press_node else "",
                    "date": info_nodes[-1].get_text(strip=True) if info_nodes else "",
                    "link": title_node.get("href"),
                }
            )

        logger.info("Fetched %s Naver news items for topic: %s", len(news_list), topic)
        return news_list
    except Exception as exc:
        logger.error("Failed to fetch Naver news: %s", exc)
        return []


async def compress_news_with_ai(news_list: list) -> dict | None:
    if not news_list:
        return None

    combined = "\n\n".join(
        f"{item['title']}{'. ' + item['summary'] if item['summary'] else ''}"
        for item in news_list
    )

    prompt = f"""다음 뉴스를 100자 이내로 요약하세요.

{combined}

반드시 JSON만 출력하세요.
{{
  "summary": "핵심 요약",
  "keyPoints": ["핵심1", "핵심2", "핵심3"]
}}"""

    try:
        response_text = await generate_content_async(
            prompt,
            model_name="gemini-2.5-flash",
            response_mime_type="application/json",
        )
        cleaned = str(response_text or "").replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned)
        compressed = {
            "summary": parsed.get("summary", ""),
            "keyPoints": parsed.get("keyPoints", []),
            "sources": [item["link"] for item in news_list],
        }
        logger.info("Compressed news summary: %s", compressed["summary"][:50])
        return compressed
    except Exception as exc:
        logger.error("Failed to compress news with AI: %s", exc)
        first = news_list[0] if news_list else {}
        return {
            "summary": first.get("title", ""),
            "keyPoints": [item["title"] for item in news_list[:3]],
            "sources": [item["link"] for item in news_list],
        }


def format_news_for_prompt(news_data: dict | list) -> str:
    if not news_data:
        return ""

    if isinstance(news_data, dict) and "summary" in news_data:
        key_points = "\n".join(
            f"{index + 1}. {point}" for index, point in enumerate(news_data.get("keyPoints", []))
        )
        sources = ", ".join(news_data.get("sources", [])[:2])
        return f"""
[뉴스 요약]
{news_data["summary"]}

주요 포인트
{key_points}

출처: {sources if sources else "네이버 뉴스"}

---
"""

    if isinstance(news_data, list) and news_data:
        news_text = "\n\n".join(
            f"{index + 1}. {item['title']} ({item.get('date', '')})\n   요약: {item.get('summary', '')}"
            for index, item in enumerate(news_data)
        )
        return f"""
[최신 뉴스 정보]
아래는 실제 최신 뉴스입니다. 이 정보를 참고하여 구체적이고 사실 기반의 원고를 작성하세요.

{news_text}

---
"""

    return ""


def should_fetch_news(category: str) -> bool:
    normalized = str(category or "").strip()
    needs_news = {
        "current-affairs",
        "policy-proposal",
        "educational-content",
        "activity-report",
        "local-issues",
        "critical_writing",
        "diagnostic_writing",
        "logical_writing",
        "direct_writing",
        "analytical_writing",
        "시사비평",
        "정책제안",
        "의정활동",
        "지역현안",
    }
    return normalized in needs_news
