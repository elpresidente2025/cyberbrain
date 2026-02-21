"""
Scraper service migrated from `functions/services/scraper.js`.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def get_naver_autocomplete(keyword: str) -> List[str]:
    try:
        url = "https://ac.search.naver.com/nx/ac"
        params = {
            "q": keyword,
            "con": 1,
            "frm": "nv",
            "ans": 2,
            "r_format": "json",
            "r_enc": "UTF-8",
            "r_unicode": 0,
            "t_koreng": 1,
            "run": 2,
            "rev": 4,
            "q_enc": "UTF-8",
            "st": 100,
        }
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "application/json",
            "Referer": "https://www.naver.com/",
        }
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        payload = response.json()
        items = _safe_list(payload.get("items"))
        suggestions = _safe_list(items[0]) if items else []
        keywords = []
        for item in suggestions:
            if isinstance(item, list) and len(item) > 0:
                text = str(item[0] or "").strip()
                if text:
                    keywords.append(text)
        return keywords[:15]
    except Exception as exc:
        logger.warning("Naver autocomplete failed: %s", exc)
        return []


def get_related_keywords_from_search_page(keyword: str) -> List[str]:
    try:
        url = f"https://search.naver.com/search.naver?query={quote_plus(keyword)}"
        response = requests.get(
            url,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "text/html",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            },
            timeout=15,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        related_keywords: List[str] = []

        for selector in (".related_srch .keyword", "a.related_keyword", ".lst_related_srch a"):
            elements = soup.select(selector)
            for element in elements:
                text = element.get_text(strip=True)
                if text:
                    related_keywords.append(text)
            if related_keywords:
                break

        deduped: List[str] = []
        seen = set()
        for item in related_keywords:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
            if len(deduped) >= 15:
                break
        return deduped
    except Exception as exc:
        logger.warning("Related keyword scrape failed: %s", exc)
        return []


def get_keywords_with_fallback(keyword: str) -> List[str]:
    # JS uses Puppeteer fallback. Python runtime currently keeps a lightweight fallback.
    # If dynamic extraction is required later, replace with Playwright/Selenium implementation.
    return [str(keyword or "").strip()] if str(keyword or "").strip() else []


def get_naver_suggestions(keyword: str) -> List[str]:
    try:
        suggestions = get_naver_autocomplete(keyword)
        if len(suggestions) > 0:
            return suggestions

        related_keywords = get_related_keywords_from_search_page(keyword)
        if len(related_keywords) > 0:
            return related_keywords

        return get_keywords_with_fallback(keyword)
    except Exception as exc:
        logger.warning("Naver suggestion flow failed: %s", exc)
        fallback = get_keywords_with_fallback(keyword)
        return fallback if fallback else [str(keyword or "").strip()]


def analyze_naver_serp(keyword: str) -> Dict[str, Any]:
    try:
        url = f"https://search.naver.com/search.naver?query={quote_plus(keyword)}"
        response = requests.get(
            url,
            headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "text/html"},
            timeout=15,
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results: List[Dict[str, Any]] = []

        for selector in (".total_wrap", ".api_subject_bx"):
            for element in soup.select(selector):
                if len(results) >= 5:
                    break
                link = element.select_one("a")
                if not link:
                    continue
                href = str(link.get("href") or "").strip()
                if not href:
                    continue

                title_node = element.select_one(".total_tit, .api_txt_lines")
                snippet_node = element.select_one(".total_txt, .api_txt_lines")
                title = title_node.get_text(strip=True) if title_node else link.get_text(strip=True)
                snippet = snippet_node.get_text(strip=True) if snippet_node else ""
                if not title:
                    continue
                results.append(
                    {
                        "title": title,
                        "url": href,
                        "snippet": snippet[:150],
                    }
                )
            if len(results) >= 5:
                break

        if len(results) < 5:
            for element in soup.select(".sh_blog_top"):
                if len(results) >= 5:
                    break
                title_node = element.select_one(".sh_blog_title")
                if not title_node:
                    continue
                href = str(title_node.get("href") or "").strip()
                title = title_node.get_text(strip=True)
                snippet_node = element.select_one(".sh_blog_passage")
                snippet = snippet_node.get_text(strip=True) if snippet_node else ""
                if title and href:
                    results.append(
                        {
                            "title": title,
                            "url": href,
                            "snippet": snippet[:150],
                        }
                    )

        blog_count = sum(
            1 for item in results if "blog.naver.com" in str(item.get("url") or "") or "tistory.com" in str(item.get("url") or "")
        )
        official_count = sum(
            1
            for item in results
            if ".go.kr" in str(item.get("url") or "")
            or ".or.kr" in str(item.get("url") or "")
            or "news.naver.com" in str(item.get("url") or "")
        )
        return {
            "results": results[:5],
            "blogCount": blog_count,
            "officialCount": official_count,
            "totalResults": len(results),
        }
    except Exception as exc:
        logger.warning("SERP analysis failed: %s", exc)
        return {
            "results": [],
            "blogCount": 0,
            "officialCount": 0,
            "totalResults": 0,
        }


def get_search_result_count(keyword: str) -> int:
    try:
        url = f"https://search.naver.com/search.naver?query={quote_plus(keyword)}"
        response = requests.get(url, headers={"User-Agent": DEFAULT_USER_AGENT}, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        title_desc = soup.select_one(".title_desc")
        text = title_desc.get_text(" ", strip=True) if title_desc else soup.get_text(" ", strip=True)
        match = re.search(r"(\d+(?:,\d+)*)", text)
        if match:
            return int(match.group(1).replace(",", ""))
        has_results = bool(soup.select(".total_wrap, .api_subject_bx"))
        return 1000 if has_results else 0
    except Exception as exc:
        logger.warning("Search result count failed: %s", exc)
        return 1000
