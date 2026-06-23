"""Configuration management for browser-search-mcp.
 
Supports JSON config file at ~/.browser-search-mcp/config.json
and environment variable overrides.
"""
 
from __future__ import annotations
 
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
 
 
# ── Default config path ─────────────────────────────────────────────
 
CONFIG_DIR = Path.home() / ".browser-search-mcp"
CONFIG_FILE = CONFIG_DIR / "config.json"
 
 
# ── Config dataclass ─────────────────────────────────────────────────
 
@dataclass
class BrowserConfig:
    """Browser settings."""
    name: str = "edge"  # edge, chrome, chromium
    port: int = 9222
    headless: bool = False  # False = visible browser (can use logged-in sessions)
    user_data_dir: str | None = None  # None = auto-generated
    executable_path: str | None = None  # None = auto-detect
    launch_timeout: int = 15  # seconds to wait for CDP after launch
 
 
@dataclass
class SearchEngineConfig:
    """Per-engine settings."""
    enabled: bool = True
    timeout: int = 30  # seconds
    max_results: int = 10
 
 
@dataclass
class CacheConfig:
    """Result caching settings."""
    enabled: bool = True
    ttl: int = 300  # seconds (5 minutes)
    max_size: int = 100  # max cached queries
 
 
@dataclass
class ServerConfig:
    """MCP server settings."""
    log_level: str = "INFO"
    default_engine: str = "google"
    search_timeout: int = 60  # max seconds for a search
 
 
@dataclass
class AppConfig:
    """Top-level application configuration."""
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    engines: dict[str, SearchEngineConfig] = field(default_factory=lambda: {
        name: SearchEngineConfig() for name in ["google", "bing", "baidu", "duckduckgo"]
    })
 
    @classmethod
    def load(cls) -> AppConfig:
        """Load config from file and env vars, merging with defaults."""
        cfg = cls()
 
        # Load from file
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text("utf-8"))
                cfg = _merge_config(cfg, data)
            except (json.JSONDecodeError, OSError) as exc:
                import logging
                logging.warning("Failed to load config from %s: %s", CONFIG_FILE, exc)
 
        # Environment variable overrides
        env = os.environ
        if "BROWSER_SEARCH_BROWSER" in env:
            cfg.browser.name = env["BROWSER_SEARCH_BROWSER"]
        if "BROWSER_SEARCH_HEADLESS" in env:
            cfg.browser.headless = env["BROWSER_SEARCH_HEADLESS"].lower() in ("1", "true", "yes")
        if "BROWSER_SEARCH_PORT" in env:
            cfg.browser.port = int(env["BROWSER_SEARCH_PORT"])
        if "BROWSER_SEARCH_CACHE_TTL" in env:
            cfg.cache.ttl = int(env["BROWSER_SEARCH_CACHE_TTL"])
        if "BROWSER_SEARCH_DEFAULT_ENGINE" in env:
            cfg.server.default_engine = env["BROWSER_SEARCH_DEFAULT_ENGINE"]
        if "BROWSER_SEARCH_LOG_LEVEL" in env:
            cfg.server.log_level = env["BROWSER_SEARCH_LOG_LEVEL"]
        if "BROWSER_SEARCH_BROWSER_PATH" in env:
            cfg.browser.executable_path = env["BROWSER_SEARCH_BROWSER_PATH"]
 
        return cfg
 
    def save(self) -> None:
        """Save current config to file."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), "utf-8")
 
    def to_dict(self) -> dict:
        return {
            "browser": {
                "name": self.browser.name,
                "port": self.browser.port,
                "headless": self.browser.headless,
                "user_data_dir": self.browser.user_data_dir,
                "executable_path": self.browser.executable_path,
                "launch_timeout": self.browser.launch_timeout,
            },
            "cache": {
                "enabled": self.cache.enabled,
                "ttl": self.cache.ttl,
                "max_size": self.cache.max_size,
            },
            "server": {
                "log_level": self.server.log_level,
                "default_engine": self.server.default_engine,
                "search_timeout": self.server.search_timeout,
            },
        }
 
 
def _merge_config(cfg: AppConfig, data: dict) -> AppConfig:
    """Merge a dict into an AppConfig, preserving defaults for missing keys."""
    browser = data.get("browser", {})
    if "name" in browser:
        cfg.browser.name = browser["name"]
    if "port" in browser:
        cfg.browser.port = int(browser["port"])
    if "headless" in browser:
        cfg.browser.headless = bool(browser["headless"])
    if "executable_path" in browser:
        cfg.browser.executable_path = browser.get("executable_path")
    if "launch_timeout" in browser:
        cfg.browser.launch_timeout = int(browser["launch_timeout"])
    cache = data.get("cache", {})
    if "enabled" in cache:
        cfg.cache.enabled = bool(cache["enabled"])
    if "ttl" in cache:
        cfg.cache.ttl = int(cache["ttl"])
    if "max_size" in cache:
        cfg.cache.max_size = int(cache["max_size"])
    server = data.get("server", {})
    if "log_level" in server:
        cfg.server.log_level = server["log_level"]
    if "default_engine" in server:
        cfg.server.default_engine = server["default_engine"]
    if "search_timeout" in server:
        cfg.server.search_timeout = int(server["search_timeout"])
    return cfg
