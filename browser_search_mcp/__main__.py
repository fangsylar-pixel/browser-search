"""Entry point for python -m browser_search_mcp and the CLI script."""

from __future__ import annotations

import sys


def main() -> None:
    """Run the browser-search-mcp server.
    
    Starts an MCP server that provides web search tools.
    Communicates via stdin/stdout (standard MCP transport).
    """
    from .server import run_server
    run_server()


if __name__ == "__main__":
    main()
