# Support

browser-search-mcp is open source and built for developers and LLM users who need web search capabilities.

## Troubleshooting

Before reporting a problem:

1. Check browser CDP - Ensure Chrome/Edge is running with --remote-debugging-port=9222
2. Check logs - Run: browser-search-mcp (log output is on stderr)
3. Test search - Run: python -m browser_search_mcp
4. Include details - OS, browser version, Python version, and exact error message

## Common Issues

| Issue | Solution |
|-------|----------|
| WebSocket errors | Restart browser with --remote-debugging-port=9222 |
| No results | Try a different search engine (google, bing, duckduckgo) |
| Browser not found | Install Chrome or Edge browser first |

## Optional Support

If this project helps you, optional support is welcome:

[Support on Afdian](https://afdian.com/a/fangsylar)

Bug reports and contributions are welcome. See CONTRIBUTING.md.
