"""browser-search-mcp: MCP server for web search via real browser.

Built on the browser-takeover-bridge architecture - uses CDP
for browser control with search-specific tools for Google,
Bing, Baidu, and DuckDuckGo.

Features:
- Real browser-based search (bypasses anti-bot measures)
- Persistent CDP session with auto-reconnect
- LRU result caching with configurable TTL
- Configurable via JSON file and environment variables
- Supports Google, Bing, Baidu, DuckDuckGo
- Integrates with browser-takeover extension bridge
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
