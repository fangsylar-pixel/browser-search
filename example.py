"""browser-search-mcp usage examples."""

import json


def example_direct_call():
    """Example 1: Call search directly from Python."""
    from browser_search_mcp.server import web_search

    result = json.loads(
        web_search("Python async programming", engine="bing", max_results=3)
    )
    print(f"Found {len(result)} results:")
    for r in result:
        print(f"  - {r['title'][:50]}")
        print(f"    {r['url'][:50]}")


def example_status_check():
    """Example 2: Check browser/bridge status."""
    from browser_search_mcp.server import web_search_status

    status = json.loads(web_search_status())
    print(f"CDP available: {status['cdp']['available']}")
    print(f"Cache: {status['cache']}")


def example_multi_search():
    """Example 3: Search multiple engines."""
    from browser_search_mcp.server import web_search_multi

    results = json.loads(
        web_search_multi("MCP protocol", engines="bing,duckduckgo",
                         max_results_per_engine=2)
    )
    for engine, items in results.items():
        print(f"{engine}: {len(items)} results")


if __name__ == "__main__":
    print("browser-search-mcp Examples")
    print("1. Direct call (requires browser with CDP)")
    print("2. Status check")
    print("3. Multi-engine search")
