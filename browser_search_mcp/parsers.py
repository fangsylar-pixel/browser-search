"""Search result parsers for different search engines.

Each parser function takes the raw text content of a search
results page and returns structured results.
"""

from __future__ import annotations

import json
import re
from typing import Any


# ── Result type ──────────────────────────────────────────────────────

SearchResult = dict[str, str]
SearchResults = list[SearchResult]


# ── Google Parser ────────────────────────────────────────────────────

def parse_google(text: str) -> SearchResults:
    """Parse Google search results from page text."""
    results: SearchResults = []
    # Google often uses structured data in script tags
    # Fall back to text-based parsing
    lines = text.split("\n")
    current = {}
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip navigation/UI elements
        if stripped in ("Images", "Videos", "News", "Shopping", "Maps", "Books",
                         "Flights", "Finance", "More", "Settings", "Tools",
                         "All", "Clear", "Search", "Advanced search"):
            continue
        # URLs typically appear on their own line after a title
        if stripped.startswith("http://") or stripped.startswith("https://"):
            if current.get("title") and not current.get("url"):
                current["url"] = stripped
                if current.get("title") and current.get("url"):
                    results.append(current)
                    current = {}
            continue
        # Line could be a title if it's not too long
        if len(stripped) > 10 and len(stripped) < 200 and not current.get("title"):
            current["title"] = stripped
        elif current.get("title") and not current.get("snippet"):
            current["snippet"] = stripped[:300]
    if current.get("title") and current.get("url") and current not in results:
        results.append(current)
    return results


# ── Bing Parser ──────────────────────────────────────────────────────

def parse_bing(text: str) -> SearchResults:
    """Parse Bing search results from page text."""
    results: SearchResults = []
    lines = text.split("\n")
    current = {}
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("http://") or stripped.startswith("https://"):
            if current.get("title") and not current.get("url"):
                current["url"] = stripped
                if current.get("title") and current.get("snippet"):
                    results.append(current)
                    current = {}
            continue
        if len(stripped) > 5 and len(stripped) < 150 and not current.get("title"):
            current["title"] = stripped
        elif current.get("title") and not current.get("snippet") and len(stripped) > 20:
            current["snippet"] = stripped[:300]
    if current.get("title") and current.get("url") and current not in results:
        results.append(current)
    return results


# ── Baidu Parser ─────────────────────────────────────────────────────

def parse_baidu(text: str) -> SearchResults:
    """Parse Baidu search results from page text."""
    results: SearchResults = []
    lines = text.split("\n")
    current = {}
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Baidu results often start with a number or bullet
        if stripped.startswith("http://") or stripped.startswith("https://"):
            if current.get("title") and not current.get("url"):
                current["url"] = stripped.split("?")[0] if "?" in stripped else stripped
                if current.get("title") and current.get("url"):
                    results.append(current)
                    current = {}
            continue
        if len(stripped) > 4 and len(stripped) < 120 and not current.get("title"):
            # Skip Baidu UI elements
            if stripped not in ("网页", "资讯", "视频", "图片", "知道", "文库", "贴吧",
                                 "地图", "采购", "直播", "百科", "更多", "设置",
                                 "百度首页", "登录"):
                current["title"] = stripped
        elif current.get("title") and not current.get("snippet") and len(stripped) > 15:
            current["snippet"] = stripped[:300]
    if current.get("title") and current.get("url") and current not in results:
        results.append(current)
    return results


# ── DuckDuckGo Parser ────────────────────────────────────────────────

def parse_duckduckgo(text: str) -> SearchResults:
    """Parse DuckDuckGo search results from page text."""
    results: SearchResults = []
    lines = text.split("\n")
    current = {}
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("http://") or stripped.startswith("https://"):
            if current.get("title") and not current.get("url"):
                current["url"] = stripped
                if current.get("title") and current.get("snippet"):
                    results.append(current)
                    current = {}
            continue
        if len(stripped) > 5 and len(stripped) < 200 and not current.get("title"):
            current["title"] = stripped
        elif current.get("title") and not current.get("snippet") and len(stripped) > 20:
            current["snippet"] = stripped[:300]
    if current.get("title") and current.get("url") and current not in results:
        results.append(current)
    return results


# ── Registry ─────────────────────────────────────────────────────────

PARSERS: dict[str, callable] = {
    "google": parse_google,
    "bing": parse_bing,
    "baidu": parse_baidu,
    "duckduckgo": parse_duckduckgo,
}
