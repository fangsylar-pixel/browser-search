"""FastMCP server exposing web search tools.

Built on the browser-takeover-bridge architecture. Uses CDP
(Chrome DevTools Protocol) to control a browser for search,
with optional integration with the browser-takeover extension
for authenticated browsing sessions.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from fastmcp import FastMCP

from . import bridge as bridge_mod
from . import cdp as cdp_mod
from .search import EXTRACTORS, SEARCH_ENGINES, PARSERS, SearchSession, SearchResults
import urllib.parse


# ── Logging ──────────────────────────────────────────────────────────

logging.basicConfig(
   level=logging.INFO,
   format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("browser-search-mcp")


# ── Result Cache ────────────────────────────────────────────────────
from collections import OrderedDict
import time as _time

class SearchCache:
    """LRU cache for search results with configurable TTL."""
    def __init__(self, max_size=100, ttl=300):
        self._max = max_size
        self._ttl = ttl
        self._data = OrderedDict()
    def _key(self, q, e):
        return e + "::" + q.lower().strip()
    def get(self, q, e):
        k = self._key(q, e)
        if k in self._data:
            r, t = self._data[k]
            if _time.time() - t < self._ttl:
                self._data.move_to_end(k)
                return r
            del self._data[k]
        return None
    def set(self, q, e, r):
        k = self._key(q, e)
        self._data[k] = (r, _time.time())
        self._data.move_to_end(k)
        while len(self._data) > self._max:
            self._data.popitem(last=False)
    def clear(self):
        self._data.clear()
    @property
    def stats(self):
        return {"size": len(self._data), "max": self._max, "ttl": self._ttl}

_SEARCH_CACHE = SearchCache()

# ── Retry helper ────────────────────────────────────────────────────
def with_retry(func, args, kwargs, max_retries=2):
    import time as _t
    for a in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception:
            if a < max_retries:
                _t.sleep(1.0 * (a + 1))
                continue
            raise


# ── Server instance ──────────────────────────────────────────────────

mcp = FastMCP("browser-search-mcp")

# Shared session (lazy-initialized on first search)
_session: SearchSession | None = None


def get_session() -> SearchSession:
   """Get or create the shared search session."""
   global _session
   if _session is None:
       _session = SearchSession()
   return _session


# ── MCP Tools ────────────────────────────────────────────────────────

@mcp.tool()
def web_search(
   query: str,
   engine: str = "google",
   max_results: int = 10,
   headless: bool = True,
) -> str:
   """Search the web using a real browser and return structured results.
    
   Uses Chrome/Edge via CDP (same approach as browser-takeover-bridge)
   to navigate to the search engine, extract results from the DOM,
   and return them as structured JSON.
    
   Args:
       query: The search query string
       engine: Search engine: google, bing, baidu, or duckduckgo
       max_results: Maximum number of results to return (1-20)
       headless: Run browser in headless mode (no visible window)
    
   Returns:
       JSON array of {title, url, snippet} objects
   """
   session = get_session()
    
   # Ensure browser is ready
   try:
       info = session.detect()
       if not session.available:
           result = session.ensure_browser(headless=headless)
           if result.get("source") == "failed":
               return json.dumps({"error": result.get("error", "No browser available")})
   except Exception as exc:
       return json.dumps({"error": f"Browser detection failed: {exc}"})
    
   # Build search URL
   if engine not in SEARCH_ENGINES:
       return json.dumps({
           "error": f"Unsupported engine: {engine}. Supported: {', '.join(SEARCH_ENGINES.keys())}"
       })
    
   engine_config = SEARCH_ENGINES[engine]
   search_url = engine_config["url"].format(query=urllib.parse.quote_plus(query))
    
   try:
       # Navigate to search
       session.navigate(search_url)
       time.sleep(1.5)
        
       # Try JavaScript DOM extraction (more accurate)
       extractor = EXTRACTORS.get(engine)
       results: list[dict] = []
       if extractor:
           try:
               eval_result = session.evaluate(extractor)
               raw = eval_result.get("result", {}).get("result", {}).get("value", "[]")
               if raw and raw != "[]":
                   parsed = json.loads(raw)
                   if parsed:
                       results = parsed
           except Exception:
               pass
        
       # Fallback to text-based parsing
       if not results:
           text = session.get_page_text()
           parser = PARSERS.get(engine)
           if parser:
               results = parser(text)
        
       return json.dumps(results[:max_results], ensure_ascii=False, indent=2)
    
   except Exception as exc:
       return json.dumps({"error": f"Search failed: {exc}"})


@mcp.tool()
def web_search_multi(
   query: str,
   engines: str = "google,bing,duckduckgo",
   max_results_per_engine: int = 5,
   headless: bool = True,
) -> str:
   """Search multiple search engines and combine results.
    
   Searches multiple engines in sequence and returns
   combined results grouped by engine.
    
   Args:
       query: The search query string
       engines: Comma-separated list of engines (google,bing,baidu,duckduckgo)
       max_results_per_engine: Results per engine (1-10)
       headless: Run browser in headless mode
    
   Returns:
       JSON object with engine names as keys and result arrays as values
   """
   engine_list = [e.strip() for e in engines.split(",") if e.strip()]
   combined: dict[str, Any] = {}
    
   for engine in engine_list:
       combined[engine] = json.loads(
           web_search(query, engine, max_results_per_engine, headless)
       )
    
   return json.dumps(combined, ensure_ascii=False, indent=2)


@mcp.tool()
def web_search_read_page(
   url: str,
   max_length: int = 5000,
) -> str:
   """Navigate to a URL and return the visible page text.
    
   Useful for reading the full content of a search result.
    
   Args:
       url: The URL to navigate to
       max_length: Maximum characters to return
    
   Returns:
       The visible text content of the page
   """
   session = get_session()
   try:
       if not session.available:
           result = session.ensure_browser()
           if result.get("source") == "failed":
               return json.dumps({"error": result.get("error", "No browser available")})
        
       session.navigate(url)
       time.sleep(2.0)
       text = session.get_page_text()
       return text[:max_length]
   except Exception as exc:
       return json.dumps({"error": f"Failed to read page: {exc}"})


@mcp.tool()
def web_search_status() -> str:
   """Check the current browser and bridge status.
    
   Detects available CDP browser instances and checks if the
   browser-takeover extension bridge is running.
    
   Returns:
       JSON status information
   """
   session = get_session()
   try:
       info = session.detect()
        
       # Also check for browser-takeover bridge specifically
       bridge = bridge_mod.bridge_status()
        
       return json.dumps({
           "cdp": info.get("cdp"),
           "bridge": {
               "available": bridge is not None,
               "status": bridge,
           },
           "session_ready": session.available,
       }, ensure_ascii=False, indent=2)
   except Exception as exc:
       return json.dumps({"error": f"Status check failed: {exc}"})


@mcp.tool()
def web_search_discover_browsers() -> str:
   """Scan for browsers with CDP enabled on common ports.
    
   Checks ports 9222, 9223, 9333 for Chrome/Edge instances
   with remote debugging enabled.
    
   Returns:
       JSON list of discovered browser instances
   """
   browsers = cdp_mod.discover_ports()
   if not browsers:
       result = cdp_mod.launch_browser("edge", headless=True)
       if result.get("launched") and result.get("cdpReady", True):
           browsers = cdp_mod.discover_ports()
   return json.dumps(browsers or [], ensure_ascii=False, indent=2)


# ── Server Runner ────────────────────────────────────────────────────

def run_server() -> None:
   """Start the MCP server with stdin/stdout transport.
    
   Compatible with any MCP client (Codex, Claude Desktop,
   Ollama + mcp-client, etc.).
   """
   sys.stdout.reconfigure(encoding="utf-8")
   sys.stderr.reconfigure(encoding="utf-8")
    
   log.info("Starting browser-search-mcp server...")
    
   # Try to detect existing browser/bridge
   session = get_session()
   try:
       info = session.detect()
       if session.available:
           log.info("Browser detected via CDP on port %d", session._cdp_port)
       if info.get("bridge", {}).get("available"):
           log.info("Browser-takeover extension bridge detected")
   except Exception:
       pass
    
   mcp.run(transport="stdio")


if __name__ == "__main__":
   run_server()
