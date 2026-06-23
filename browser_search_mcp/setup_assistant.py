"""Ollama setup assistant and integration bridge."""

from __future__ import annotations

import json
import os
import sys
import shutil
from pathlib import Path


def check_prerequisites() -> dict:
    """Check if all prerequisites are installed and running."""
    results = {
        "browser_search_mcp": False,
        "chrome_edge": False,
        "ollama": False,
        "mcp_sdk": False,
    }

    # Check browser-search-mcp
    try:
        from .server import mcp
        results["browser_search_mcp"] = True
    except Exception:
        pass

    # Check Chrome/Edge
    programs = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    for p in programs:
        if p.exists():
            results["chrome_edge"] = True
            break

    # Check Ollama
    try:
        import httpx
        r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=2)
        if r.status_code == 200:
            models = r.json().get("models", [])
            results["ollama"] = bool(models)
    except Exception:
        pass

    # Check MCP SDK
    try:
        import mcp
        results["mcp_sdk"] = True
    except Exception:
        pass

    return results


def print_status(results: dict) -> None:
    """Print a nice status report."""
    status_icons = {True: "[37m[32mOK[m", False: "[37m[31mMISSING[m"}

    print()
    print("  Prerequisites Check")
    print("  " + "-" * 40)

    checks = [
        ("browser-search-mcp installed", results["browser_search_mcp"]),
        ("Chrome/Edge found", results["chrome_edge"]),
        ("Ollama running", results["ollama"]),
        ("MCP SDK", results["mcp_sdk"]),
    ]

    for label, ok in checks:
        print(f"    {label:30s} {status_icons[ok]}")


def print_instructions(results: dict) -> None:
    """Print setup instructions based on what's missing."""
    print()
    print("  Setup Instructions")
    print("  " + "-" * 40)

    if not results["browser_search_mcp"]:
        print("    pip install browser-search-mcp")
    if not results["chrome_edge"]:
        print("    Install Chrome or Edge browser")
    if not results["ollama"]:
        print("    Start Ollama: ollama serve")
    if not results["mcp_sdk"]:
        print("    pip install mcp")

    print()
    print("  Then run any MCP client to use the search tools.")
    print()

    # Print MCP config example
    config = {
        "mcpServers": {
            "browser-search": {
                "command": "browser-search-mcp",
                "args": []
            }
        }
    }
    print("  MCP Client Config:")
    print(json.dumps(config, indent=2))
    print()


def run() -> None:
    """Main entry point for the setup command."""
    print()
    print("  browser-search-mcp Setup Assistant")
    print()

    results = check_prerequisites()
    print_status(results)
    print_instructions(results)

    if results["ollama"] and results["browser_search_mcp"] and results["mcp_sdk"]:
        print("  All good! Try: python -m browser_search_mcp")
    else:
        print("  Fix the missing items above, then run this again.")
