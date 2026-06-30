# API search providers for browser-search-mcp
# Browser provider is built into server.py

import logging
log = logging.getLogger("browser-search-mcp")


class TavilyProvider:
    name = "tavily"

    def __init__(self, api_key):
        self.api_key = api_key

    def search(self, query, max_results=10, **kwargs):
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=self.api_key)
            result = client.search(query=query, max_results=max_results)
            items = []
            for r in result.get("results", []):
                items.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("content", ""),
                })
            return items
        except ImportError:
            raise RuntimeError(
                "Tavily not installed. Run: pip install browser-search-mcp[tavily]"
            )


class BraveProvider:
    name = "brave"

    def __init__(self, api_key):
        self.api_key = api_key

    def search(self, query, max_results=10, **kwargs):
        try:
            import httpx
        except ImportError:
            raise RuntimeError(
                "httpx not installed. Run: pip install browser-search-mcp[brave]"
            )
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": self.api_key},
            params={"q": query, "count": max_results},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        items = []
        for r in data.get("web", {}).get("results", []):
            items.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("description", ""),
            })
        return items


def get_provider(provider_name=None, config=None):
    if config is None:
        from .config import AppConfig
        config = AppConfig.load()

    name = provider_name or config.provider.name

    if name == "tavily":
        key = config.provider.tavily_api_key or ""
        if not key:
            raise RuntimeError(
                "Tavily API key not configured. "
                "Set tavily_api_key in config.json or BROWSER_SEARCH_TAVILY_KEY env var."
            )
        return TavilyProvider(key)

    elif name == "brave":
        key = config.provider.brave_api_key or ""
        if not key:
            raise RuntimeError(
                "Brave API key not configured. "
                "Set brave_api_key in config.json or BROWSER_SEARCH_BRAVE_KEY env var."
            )
        return BraveProvider(key)

    else:
        return None
