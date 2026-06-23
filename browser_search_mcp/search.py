"""Search engine abstraction.

Orchestrates the search flow: discover browser → navigate to
search engine → extract page content → parse results.
Supports Google, Bing, Baidu, and DuckDuckGo via CDP or the
browser-takeover extension bridge.
"""

from __future__ import annotations

import time
import urllib.parse
from typing import Any

from . import bridge as bridge_mod
from . import cdp as cdp_mod
from .parsers import PARSERS, SearchResults


# ── Search engine config ─────────────────────────────────────────────

SEARCH_ENGINES: dict[str, dict[str, str]] = {
    "google": {
        "name": "Google",
        "url": "https://www.google.com/search?q={query}",
        "wait_selector": "h3, #search",
        "result_indicator": "h3",
    },
    "bing": {
        "name": "Bing",
        "url": "https://www.bing.com/search?q={query}",
        "wait_selector": ".b_algo, #b_results",
        "result_indicator": "h2",
    },
    "baidu": {
        "name": "Baidu",
        "url": "https://www.baidu.com/s?wd={query}",
        "wait_selector": ".result, .c-container, #content_left",
        "result_indicator": "h3",
    },
    "duckduckgo": {
        "name": "DuckDuckGo",
        "url": "https://duckduckgo.com/?q={query}",
        "wait_selector": 'article[data-testid="result"]',
        "result_indicator": "h2",
    },
}


# ── Search execution ─────────────────────────────────────────────────

class SearchSession:
    """Manages a browser session for performing searches.
    
    Detects available browser control methods (CDP ports, extension bridge)
    and uses the best available option.
    """

    def __init__(self):
        self._cdp_host: str | None = None
        self._cdp_port: int | None = None
        self._bridge_available: bool = False
        self._browser_launched: bool = False
        self._launch_info: dict | None = None

    def detect(self) -> dict:
        """Detect available browser control methods.
        
        Returns a status dict with detected capabilities.
        """
        info: dict[str, Any] = {
            "cdp": {"available": False, "browsers": []},
            "bridge": {"available": False, "status": None},
        }

        # Check for CDP-accessible browsers
        browsers = cdp_mod.discover_ports()
        if browsers:
            info["cdp"]["available"] = True
            info["cdp"]["browsers"] = browsers
            self._cdp_host = browsers[0]["host"]
            self._cdp_port = browsers[0]["port"]

        # Check for browser-takeover bridge
        bridge_status = bridge_mod.bridge_status()
        if bridge_status:
            info["bridge"]["available"] = True
            info["bridge"]["status"] = bridge_status
            self._bridge_available = True
            # If bridge is available but no CDP yet, try to find the browser
            if not browsers:
                for client in bridge_status.get("clients") or []:
                    browser_name = client.get("browser", "").lower()
                    if "chrome" in browser_name:
                        browsers = cdp_mod.discover_ports()
                        break

        return info

    def ensure_browser(self, headless: bool = False) -> dict:
        """Ensure a browser is available, launching one if needed."""
        # First check if any CDP port is already available
        browsers = cdp_mod.discover_ports()
        if browsers:
            self._cdp_host = browsers[0]["host"]
            self._cdp_port = browsers[0]["port"]
            return {"source": "existing", "browsers": browsers}

        # Try launching one
        for browser_name in ("edge", "chrome", "chromium"):
            info = cdp_mod.launch_browser(browser_name, headless=headless)
            if info.get("launched") and info.get("cdpReady", True):
                self._cdp_host = "127.0.0.1"
                self._cdp_port = info["port"]
                self._browser_launched = True
                self._launch_info = info
                return {"source": "launched", "info": info}

        return {"source": "failed", "error": "No browser could be found or launched"}

    @property
    def available(self) -> bool:
        return self._cdp_port is not None

    def get_page_text(self, page_id: str | None = None) -> str:
        """Get visible text from the current CDP page."""
        if not self._cdp_host or not self._cdp_port:
            raise RuntimeError("No CDP session available")
        return cdp_mod.get_page_text(self._cdp_host, self._cdp_port, page_id)

    def navigate(self, url: str, page_id: str | None = None) -> dict:
        """Navigate the browser to a URL."""
        if not self._cdp_host or not self._cdp_port:
            raise RuntimeError("No CDP session available")
        return cdp_mod.navigate(self._cdp_host, self._cdp_port, url, page_id)

    def evaluate(self, expression: str, page_id: str | None = None) -> Any:
        """Evaluate JavaScript in the browser."""
        if not self._cdp_host or not self._cdp_port:
            raise RuntimeError("No CDP session available")
        return cdp_mod.evaluate_js(self._cdp_host, self._cdp_port, expression, page_id)

    def close(self) -> None:
        """Clean up if we launched a browser."""
        # CDP-launched browsers are best left running for the session
        self._cdp_host = None
        self._cdp_port = None


# ── Search with JavaScript extraction ────────────────────────────────

GOOGLE_EXTRACTOR = r"""
(() => {
    const results = [];
    const items = document.querySelectorAll('#search .g, #search .MjjYud');
    items.forEach(item => {
        const titleEl = item.querySelector('h3');
        const linkEl = item.querySelector('a[jsname]');
        const snippetEl = item.querySelector('.VwiC3b, [data-sncf="1"]');
        if (titleEl && titleEl.textContent.trim()) {
            results.push({
                title: titleEl.textContent.trim(),
                url: linkEl ? (linkEl.href || '') : '',
                snippet: snippetEl ? snippetEl.textContent.trim() : ''
            });
        }
    });
    return JSON.stringify(results.slice(0, 20));
})()
"""

BING_EXTRACTOR = r"""
(() => {
    const results = [];
    const items = document.querySelectorAll('#b_results .b_algo');
    items.forEach(item => {
        const titleEl = item.querySelector('h2 a');
        const snippetEl = item.querySelector('.b_caption p');
        if (titleEl && titleEl.textContent.trim()) {
            results.push({
                title: titleEl.textContent.trim(),
                url: titleEl.href || '',
                snippet: snippetEl ? snippetEl.textContent.trim() : ''
            });
        }
    });
    return JSON.stringify(results.slice(0, 20));
})()
"""

BAIDU_EXTRACTOR = r"""
(() => {
    const results = [];
    const items = document.querySelectorAll(
        '#content_left .result, #content_left .c-container, .result-op'
    );
    items.forEach(item => {
        const titleEl = item.querySelector('h3 a');
        const snippetEl = item.querySelector('.c-abstract, .content-right_8Zs40, .c-span-last');
        if (titleEl && titleEl.textContent.trim()) {
            results.push({
                title: titleEl.textContent.trim(),
                url: titleEl.href || '',
                snippet: snippetEl ? snippetEl.textContent.trim() : ''
            });
        }
    });
    return JSON.stringify(results.slice(0, 20));
})()
"""

DUCKDUCKGO_EXTRACTOR = r"""
(() => {
    const results = [];
    const items = document.querySelectorAll('article[data-testid="result"]');
    items.forEach(item => {
        const titleEl = item.querySelector('h2 a');
        const snippetEl = item.querySelector('[data-result="snippet"]');
        if (titleEl && titleEl.textContent.trim()) {
            results.push({
                title: titleEl.textContent.trim(),
                url: titleEl.href || '',
                snippet: snippetEl ? snippetEl.textContent.trim() : ''
            });
        }
    });
    return JSON.stringify(results.slice(0, 20));
})()
"""

EXTRACTORS: dict[str, str] = {
    "google": GOOGLE_EXTRACTOR,
    "bing": BING_EXTRACTOR,
    "baidu": BAIDU_EXTRACTOR,
    "duckduckgo": DUCKDUCKGO_EXTRACTOR,
}


async def web_search(
    session: SearchSession,
    query: str,
    engine: str = "google",
    max_results: int = 10,
) -> SearchResults:
    """Perform a web search and return structured results.
    
    Uses the browser session to navigate to the search engine,
    extracts results via JavaScript DOM parsing, and returns
    them as a list of {title, url, snippet} dicts.
    """
    if engine not in SEARCH_ENGINES:
        raise ValueError(f"Unsupported search engine: {engine}. "
                         f"Supported: {', '.join(SEARCH_ENGINES.keys())}")

    engine_config = SEARCH_ENGINES[engine]
    search_url = engine_config["url"].format(query=urllib.parse.quote_plus(query))

    if not session.available:
        session.ensure_browser(headless=True)

    if not session.available:
        raise RuntimeError("Cannot perform search: no browser available. "
                          "Ensure Chrome/Edge is running with --remote-debugging-port, "
                          "or run 'browser-search-mcp launch' first.")

    # Navigate to search engine
    session.navigate(search_url)

    # Wait for results to load
    time.sleep(2.0)

    # Try JavaScript extraction first
    extractor = EXTRACTORS.get(engine)
    if extractor:
        try:
            result = session.evaluate(extractor)
            raw = result.get("result", {}).get("result", {}).get("value", "[]")
            if raw and raw != "[]":
                parsed = __import__("json").loads(raw)
                if parsed:
                    return parsed[:max_results]
        except Exception:
            pass

    # Fallback: text-based parsing
    text = session.get_page_text()
    parser = PARSERS.get(engine)
    if parser:
        return parser(text)[:max_results]

    return []


async def web_search_multi(
    session: SearchSession,
    query: str,
    engines: list[str] | None = None,
    max_results_per_engine: int = 5,
) -> dict[str, SearchResults]:
    """Search multiple engines and return combined results."""
    if engines is None:
        engines = ["google", "bing", "duckduckgo"]

    results: dict[str, SearchResults] = {}
    for engine in engines:
        try:
            results[engine] = await web_search(session, query, engine, max_results_per_engine)
        except Exception as exc:
            results[engine] = [{"title": f"Error: {exc}", "url": "", "snippet": ""}]

    return results
