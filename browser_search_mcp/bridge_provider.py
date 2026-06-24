"""Bridge-based search provider for browser-search-mcp.

Directly imports the browser-takeover-bridge MCP module and uses its
HTTP API to perform searches through the users existing browser.
When the extension is not registered, falls back gracefully.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("browser-search-mcp")

BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 17321
BRIDGE_BASE = "http://" + BRIDGE_HOST + ":" + str(BRIDGE_PORT)


def bridge_check() -> bool:
    """Quick check: is the bridge HTTP server running?"""
    try:
        req = urllib.request.Request(BRIDGE_BASE + "/bridge/status", method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            clients = data.get("clients", [])
            return len(clients) > 0
    except Exception:
        return False


def create_bridge_search_provider() -> object | None:
    """Create a BridgeSearchProvider if the bridge extension is active.

    Requires the browser-takeover-bridge HTTP server on port 17321
    with at least one connected extension client.
    """
    if not bridge_check():
        return None
    return BridgeSearchProvider()


class BridgeSearchProvider:
    """Search provider that routes through the bridge extension."""

    def search(
        self, query: str, engine: str = "bing",
        max_results: int = 10, **kwargs
    ) -> list[dict]:
        """Perform a search using the bridge extension."""
        try:
            # Get tabs via bridge HTTP API
            req = urllib.request.Request(
                BRIDGE_BASE + "/bridge/tabs", method="GET"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                tabs_data = json.loads(resp.read().decode("utf-8"))

            tabs = tabs_data.get("tabs", [])
            if not tabs:
                raise RuntimeError("No tabs through bridge")

            tab = tabs[0]
            client_id = tab.get("clientId", "")
            tab_id = tab.get("tabId")

            if not client_id or tab_id is None:
                raise RuntimeError("Invalid tab info from bridge")

            # Search
            from .search import SEARCH_ENGINES, EXTRACTORS, PARSERS

            cfg = SEARCH_ENGINES.get(engine, {})
            search_url = cfg.get("url", "").format(
                query=urllib.parse.quote_plus(query)
            )
            if not search_url:
                raise RuntimeError("Unsupported engine: " + str(engine))

            # Navigate via bridge
            nav_body = json.dumps({
                "clientId": client_id,
                "tabId": tab_id,
                "url": search_url,
                "timeout": 15,
            }).encode("utf-8")
            nav_req = urllib.request.Request(
                BRIDGE_BASE + "/bridge/navigate",
                data=nav_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(nav_req, timeout=20) as resp:
                nav_result = json.loads(resp.read().decode("utf-8"))
            if not nav_result or not nav_result.get("ok", False):
                raise RuntimeError("Navigation failed")

            time.sleep(1.5)

            # Evaluate via bridge
            extractor = EXTRACTORS.get(engine, "")
            if not extractor:
                raise RuntimeError("No extractor for " + str(engine))

            eval_body = json.dumps({
                "clientId": client_id,
                "tabId": tab_id,
                "expression": extractor,
                "timeout": 10,
            }).encode("utf-8")
            eval_req = urllib.request.Request(
                BRIDGE_BASE + "/bridge/evaluate",
                data=eval_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(eval_req, timeout=15) as resp:
                eval_result = json.loads(resp.read().decode("utf-8"))

            if eval_result and eval_result.get("ok", False):
                raw = eval_result.get("result", {}).get("value", "[]")
                if raw and raw != "[]":
                    return json.loads(raw)[:max_results]

            # Fallback: page text
            text_body = json.dumps({
                "clientId": client_id,
                "tabId": tab_id,
                "expression": "document.body.innerText",
                "timeout": 10,
            }).encode("utf-8")
            text_req = urllib.request.Request(
                BRIDGE_BASE + "/bridge/evaluate",
                data=text_body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(text_req, timeout=15) as resp:
                text_result = json.loads(resp.read().decode("utf-8"))

            if text_result and text_result.get("ok", False):
                page_text = text_result.get("result", {}).get("value", "")
                parser = PARSERS.get(engine)
                if parser:
                    return parser(page_text)[:max_results]

            return []

        except Exception as e:
            raise RuntimeError("Bridge search failed: " + str(e))
