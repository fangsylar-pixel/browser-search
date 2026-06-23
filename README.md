# Browser Search MCP

> 基于真实浏览器的 MCP 搜索引擎服务器 - 让任何支持 MCP 的大模型都能搜索网页内容。
> Browser Search MCP - Web search via real browser for any LLM.

Built on the same CDP extension bridge architecture as **[browser-takeover-bridge](https://github.com/fangsylar-pixel/browser-takeover-bridge)**.

## Why?

Local LLMs (Ollama, etc.) cant search the web. HTTP-based search tools get blocked by anti-bot measures.
This project uses a **real browser** to search - no API keys, no blocking, no fake results.

## Quick Start

```bash
pip install browser-search-mcp

# Start the MCP server
browser-search-mcp
```

Then configure in any MCP client:

```json
{
  "mcpServers": {
    "browser-search": {
      "command": "browser-search-mcp"
    }
  }
}
```

## Features

| Feature | Status | Description |
|---------|--------|-------------|
| Google, Bing, Baidu, DuckDuckGo | Yes | DOM + JS extraction |
| Persistent browser session | Yes | Reuses CDP connection |
| Result caching | Yes | LRU with configurable TTL |
| Config file | Yes | JSON + env vars |
| Auto-reconnect | Yes | Transparent reconnection |
| browser-takeover bridge | Yes | Detects extension bridge |
| Fallback parsers | Yes | Text-based when JS fails |
| Retry on failure | Yes | Exponential backoff |

## MCP Tools

| Tool | Description |
|------|-------------|
| `web_search` | Search a single engine, returns JSON results |
| `web_search_multi` | Search multiple engines simultaneously |
| `web_search_read_page` | Read full content of a search result URL |
| `web_search_status` | Check browser, bridge, and cache status |
| `web_search_discover_browsers` | Find CDP-enabled browsers |

## Configuration

Config file: `~/.browser-search-mcp/config.json`

```json
{
  "browser": {
    "name": "edge",
    "headless": false,
    "port": 9222
  },
  "cache": {
    "enabled": true,
    "ttl": 300
  },
  "server": {
    "default_engine": "google",
    "log_level": "INFO"
  }
}
```

Environment variables also work: `BROWSER_SEARCH_HEADLESS=true`, `BROWSER_SEARCH_DEFAULT_ENGINE=bing`, etc.

## How It Works

```text
LLM/Agent -> MCP Client -> browser-search-mcp -> Browser (CDP) -> Search Engine
                                                    | (optional)
                                          browser-takeover extension
```

1. MCP server finds or launches a Chrome/Edge browser with remote debugging
2. Navigates to the search engine
3. Extracts structured results via JavaScript DOM parsing
4. Returns title, url, snippet as JSON
5. Results cached for 5 minutes by default

## Project Structure

```text
browser-search-mcp/
  browser_search_mcp/
    config.py    Configuration via JSON file + env vars
    cdp.py       CDP browser control with persistent sessions
    bridge.py    Browser-takeover extension bridge client
    search.py    Search orchestration with caching and retry
    parsers.py   Text-based search result parsers (fallback)
    server.py    FastMCP server with 5 search tools
  .github/      CI and issue templates
  README.md, CONTRIBUTING.md, LICENSE
```

## Requirements

- Python 3.11+
- Chrome or Edge installed
- Optional: browser-takeover-bridge extension (for authenticated sessions)

## License

MIT
