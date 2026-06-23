# Browser Search MCP
 
> 基于 [browser-takeover-bridge](https://github.com/fangsylar-pixel/browser-takeover-bridge) 架构的 MCP 搜索引擎服务器。
> 让任何支持 MCP 的大模型（Ollama、Claude、Codex 等）都能通过真实浏览器搜索网页内容。
 
English | [中文](#browser-search-mcp)
 
MCP server for web search via real browser. Built on the same CDP + extension bridge
architecture as [browser-takeover-bridge](https://github.com/fangsylar-pixel/browser-takeover-bridge).
 
## Why?
 
Local LLMs like Ollama can't search the web. Most "web search" tools use
HTTP requests that get blocked by anti-bot measures. This project uses a
**real browser** (Chrome/Edge) to search, so you get:
 
- Accurate, human-like search results
- Support for search engines with anti-bot protection (Google, Baidu)
- Authenticated sessions via the browser-takeover extension bridge
- Works with any MCP-compatible client
 
## How It Works
 
```text
LLM/Agent → MCP Client → browser-search-mcp → Browser (CDP) → Search Engine
                                                    ↓ (optional)
                                          browser-takeover extension
```
 
1. The MCP server finds or launches a Chrome/Edge browser with remote debugging
2. Navigates to the search engine (Google, Bing, Baidu, DuckDuckGo)
3. Extracts structured results via JavaScript DOM parsing
4. Returns {title, url, snippet} as JSON
 
If the [browser-takeover-bridge](https://github.com/fangsylar-pixel/browser-takeover-bridge)
extension is installed and its bridge is running, the search MCP will detect it
and can use the extension for authenticated browsing sessions.
 
## Quick Start
 
### Install
 
```bash
# Clone the repo
git clone https://github.com/fangsylar-pixel/browser-search-mcp.git
cd browser-search-mcp
 
# Install dependencies
pip install -e .
 
# Install Playwright browser (if using headless mode)
playwright install chromium
```
 
### Run
 
```bash
# Start the MCP server (stdin/stdout transport)
browser-search-mcp
# Or: python -m browser_search_mcp
```
 
### Configure with MCP Client
 
**Codex / Claude Desktop:**
 
Add to your MCP config:
```json
{
  "mcpServers": {
    "browser-search": {
      "command": "browser-search-mcp",
      "args": []
    }
  }
}
```
 
**Ollama:** Use a MCP client like [mcp-cli](https://github.com/beamlit/mcp-cli)
or configure via your Ollama tool interface.
 
## MCP Tools
 
| Tool | Description |
|------|-------------|
| `web_search` | Search the web and return structured results |
| `web_search_multi` | Search multiple engines at once |
| `web_search_read_page` | Read the full content of a search result URL |
| `web_search_status` | Check browser/bridge health |
| `web_search_discover_browsers` | Find available browsers with CDP |
 
### web_search
 
Search a single engine:
 
```json
// Input
{
  "query": "Python async programming best practices",
  "engine": "google",
  "max_results": 5
}
 
// Output
[
  {
    "title": "Async IO in Python: A Complete Walkthrough",
    "url": "https://realpython.com/async-io-python/",
    "snippet": "In this quiz, you'll test your understanding of async IO in Python..."
  },
  ...
]
```
 
### web_search_multi
 
Combine results from multiple search engines:
 
```json
// Input
{
  "query": "latest AI research 2026",
  "engines": "google,bing,duckduckgo",
  "max_results_per_engine": 3
}
 
// Output
{
  "google": [...],
  "bing": [...],
  "duckduckgo": [...]
}
```
 
## Search Engines
 
| Engine | Status | Notes |
|--------|--------|-------|
| Google | ✅ | DOM + JS extraction |
| Bing | ✅ | DOM + JS extraction |
| Baidu | ✅ | DOM + JS extraction |
| DuckDuckGo | ✅ | DOM + JS extraction, no CAPTCHA |
 
## Architecture
 
Built on the same principles as [browser-takeover-bridge](https://github.com/fangsylar-pixel/browser-takeover-bridge):
 
- **CDP (Chrome DevTools Protocol)**: Primary browser control path. Uses raw WebSocket
  to communicate with Chrome/Edge's DevTools, same as browser-takeover's CDP tools.
- **Extension Bridge**: Optional integration. If the browser-takeover extension bridge
  is running on port 17321, the search MCP detects it and can use the extension
  for authenticated browsing sessions.
- **JavaScript DOM Extraction**: Runs JavaScript directly in the browser context
  to extract search results — more reliable than text-based parsing.
 
### Project Structure
 
```text
browser-search-mcp/
├── browser_search_mcp/
│   ├── __init__.py    # Package info
│   ├── __main__.py    # CLI entry point
│   ├── cdp.py         # CDP browser control (same approach as browser-takeover)
│   ├── bridge.py      # Browser-takeover extension bridge client
│   ├── search.py      # Search engine abstraction & JS extractors
│   ├── parsers.py     # Text-based search result parsers (fallback)
│   └── server.py      # FastMCP server with search tools
├── pyproject.toml
└── README.md
```
 
## Requirements
 
- Python 3.11+
- Chrome or Edge installed (for CDP mode)
- Optional: [browser-takeover-bridge](https://github.com/fangsylar-pixel/browser-takeover-bridge)
  extension (for authenticated sessions)
 
## License
 
MIT
