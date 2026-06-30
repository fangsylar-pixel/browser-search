"""Entry point for python -m browser_search_mcp and the CLI script."""

from __future__ import annotations

import sys


def main() -> None:
   """Run the browser-search-mcp command line entry point."""
   import argparse

   parser = argparse.ArgumentParser(
      prog="browser-search-mcp",
      description="MCP web search server powered by a real browser.",
   )
   subparsers = parser.add_subparsers(dest="command")

   http_parser = subparsers.add_parser("http", help="Run the optional HTTP API server")
   http_parser.add_argument("port", nargs="?", type=int, default=9090)

   subparsers.add_parser("status", help="Print browser, bridge, provider, and cache status")
   subparsers.add_parser("setup", help="Run the setup assistant")
   subparsers.add_parser("doctor", help="Alias for setup")
   subparsers.add_parser("stdio", help="Run the MCP stdio server")

   args = parser.parse_args()

   if args.command == "http":
      from .http_api import run
      run(port=args.port)
      return

   if args.command == "status":
      from .server import web_search_status
      print(web_search_status())
      return

   if args.command in ("setup", "doctor"):
      from .setup_assistant import run
      run()
      return

   from .server import run_server
   run_server()


if __name__ == "__main__":
   main()
