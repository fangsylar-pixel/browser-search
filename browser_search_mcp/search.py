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

# Anti-bot helpers
import random as _random_ab
import time as _time_ab
_CAPTCHA_KW = [
    "captcha","verify","unusual traffic","robot","automated queries",
    chr(39564)+chr(35797)+chr(30721), chr(23433)+chr(20840)+chr(39564),
    chr(26837)+chr(22120)+chr(36755)+chr(39564),
]
_last_ts = {}

# Engine health cache
_engine_health = {}
_ENGINE_HEALTH_TTL = 300


def _check_engine_health(session, engine):
    now = _time_ab.time()
    if engine in _engine_health:
        h, ts = _engine_health[engine]
        if now - ts < _ENGINE_HEALTH_TTL:
            return h
    if not session or not session.available:
        return True
    try:
        cfg = SEARCH_ENGINES.get(engine)
        if not cfg:
            return False
        session.navigate(cfg["url"].format(query="healthcheck"))
        _time_ab.sleep(2.0)
        txt = session.get_page_text()
        if _has_captcha(txt):
            _engine_health[engine] = (False, now)
            return False
        _engine_health[engine] = (True, now)
        return True
    except Exception:
        _engine_health[engine] = (False, _time_ab.time())
        return False


def _normalize_url(url):
    if not url:
        return ""
    u = url.strip()
    u = u.split("?")[0] if "?" in u else u
    u = u.rstrip("/")
    return u.lower()


def _title_similarity(t1, t2):
    if not t1 or not t2:
        return 0.0
    a, b = t1.lower().strip(), t2.lower().strip()
    if a == b:
        return 1.0
    wa, wb = set(a.split()), set(b.split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(len(wa), len(wb))


def _deduplicate_results(results):
    seen_urls = set()
    seen_titles = []
    deduped = []
    for r in results:
        url = _normalize_url(r.get("url", ""))
        title = r.get("title", "")
        if url and url in seen_urls:
            continue
        if any(_title_similarity(title, st) > 0.7 for st in seen_titles):
            continue
        if url:
            seen_urls.add(url)
        seen_titles.append(title)
        deduped.append(r)
    return deduped


def get_engine_health():
    now = _time_ab.time()
    result = {}
    for engine in SEARCH_ENGINES:
        if engine in _engine_health:
            h, ts = _engine_health[engine]
            result[engine] = {"healthy": h, "age": round(now - ts, 1)}
        else:
            result[engine] = {"healthy": True, "age": -1}
    return result


def _has_captcha(t):
    if not t: return False
    t = t.lower()
    for kw in _CAPTCHA_KW:
        if kw in t: return True
    return False

def _delay(engine):
    now = _time_ab.time()
    last = _last_ts.get(engine, 0)
    if now - last < 0.5:
        _time_ab.sleep(_random_ab.uniform(0.1, 0.5))
    _time_ab.sleep(_random_ab.uniform(0.1, 0.3))
    _last_ts[engine] = _time_ab.time()

FALLBACK = {
    "google": ["bing","duckduckgo","baidu"],
    "bing": ["duckduckgo","google","baidu"],
    "baidu": ["bing","duckduckgo"],
    "duckduckgo": ["bing","google"],
}

def _next_fallback(engine, tried):
    for fb in FALLBACK.get(engine, []):
        if fb not in tried: return fb
    return None



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
   """Persistent browser session for performing searches.
    
   Maintains a single CDP WebSocket connection across all search
   operations, reducing overhead. Handles auto-reconnect and
   graceful browser lifecycle management.
   """

   def __init__(self):
       self._cdp_host: str | None = None
       self._cdp_port: int | None = None
       self._bridge_available: bool = False
       self._browser_launched: bool = False
       self._launch_info: dict | None = None
       self._session: object | None = None  # CdpSession instance

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
       return cdp_mod.get_page_text(self._cdp_host, self._cdp_port, page_id)

   def navigate(self, url: str, page_id: str | None = None) -> dict:
       """Navigate the browser to a URL."""
       return cdp_mod.navigate(self._cdp_host, self._cdp_port, url, page_id)

   def evaluate(self, expression: str, page_id: str | None = None) -> Any:
       """Evaluate JavaScript in the browser."""
       return cdp_mod.evaluate_js(self._cdp_host, self._cdp_port, expression, page_id)

   def close(self) -> None:
       """Clean up session and browser."""
       if self._session:
           try:
               self._session.close()
           except Exception:
               pass
           self._session = None
       # Kill browser if we launched it
       if self._browser_launched:
           try:
               import subprocess
               subprocess.run(["taskkill", "/F", "/IM", "msedge.exe"], capture_output=True, timeout=3)
               subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True, timeout=3)
           except Exception:
               pass
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
    page: int = 1,
    time_range: str or None = None,
    deep_mode: bool = False,
) -> SearchResults:
    """
    Perform a web search with anti-bot detection and engine fallback.
    
    Tries primary engine first, detects CAPTCHA, falls back automatically.
    deep_mode: also reads full content from top 2 results.
    """
    tried = set()
    current = engine

    while current and current not in tried:
        tried.add(current)
        _delay(current)

        if current not in SEARCH_ENGINES:
            current = _next_fallback(engine, tried)
            continue

        cfg = SEARCH_ENGINES[current]
        url = cfg["url"].format(query=urllib.parse.quote_plus(query))
        if page > 1:
            pp = {"google": "&start=" + str((page-1)*10), "bing": "&first=" + str((page-1)*10+1), "duckduckgo": "&s=" + str((page-1)*10)}
            if current in pp:
                url += pp[current]
        if time_range:
            tp = {"google": {"hour":"&tbs=qdr:h","day":"&tbs=qdr:d","week":"&tbs=qdr:w","month":"&tbs=qdr:m","year":"&tbs=qdr:y"},
                  "bing": {"hour":"&qft=filterui:age-lasthour","day":"&qft=filterui:age-lastday","week":"&qft=filterui:age-lastweek","month":"&qft=filterui:age-lastmonth","year":"&qft=filterui:age-lastyear"}}
            t = tp.get(current, {}).get(time_range) if time_range else None
            if t:
                url += t

        if not session.available:
            session.ensure_browser(headless=True)
        if not session.available:
            raise RuntimeError("No browser available")

        try:
            nav = session.navigate(url)
            pid = nav.get("page", {}).get("id") if nav else None

            _time_ab.sleep(1.0)
            for _ in range(15):
                try:
                    r = session.evaluate("document.readyState", page_id=pid)
                    s = (r.get("result") or {}).get("result", {}).get("value", "")
                    if s == "complete": break
                except: pass
                _time_ab.sleep(0.3)
            _time_ab.sleep(1.0)

            # CAPTCHA detection
            try:
                txt = session.get_page_text(page_id=pid)
                if _has_captcha(txt):
                    current = _next_fallback(engine, tried)
                    continue
            except: pass

            # JS extraction
            ext = EXTRACTORS.get(current)
            rl = []
            if ext:
                for _ in range(3):
                    try:
                        res = session.evaluate(ext, page_id=pid)
                        raw = res.get("result",{}).get("result",{}).get("value","[]")
                        if raw and raw != "[]":
                            import json as _j
                            rl = _j.loads(raw)
                            if rl: break
                    except:
                        if _ < 2: _time_ab.sleep(1.0)

            # Text fallback
            if not rl:
                try:
                    txt = session.get_page_text(page_id=pid)
                    parser = PARSERS.get(current)
                    if parser: rl = parser(txt)
                except: pass

            if rl:
                # Deep mode: auto-read top 2 results
                if deep_mode:
                    for item in rl[:2]:
                        u = item.get("url", "")
                        if u:
                            try:
                                session.navigate(u)
                                _time_ab.sleep(2.0)
                                ft = session.get_page_text()
                                item["full_content"] = (ft or "")[:2000]
                            except:
                                item["full_content"] = ""
                return rl[:max_results]
            else:
                current = _next_fallback(engine, tried)
        except Exception:
            current = _next_fallback(engine, tried)

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
