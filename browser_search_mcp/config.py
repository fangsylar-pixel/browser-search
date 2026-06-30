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


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("1", "true", "yes", "on")
    return bool(value)
 
 
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
class ProviderConfig:
    name: str = "browser"
    tavily_api_key: str = ""
    brave_api_key: str = ""


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
    provider: ProviderConfig = field(default_factory=ProviderConfig)
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
            cfg.browser.headless = _as_bool(env["BROWSER_SEARCH_HEADLESS"])
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
        if "BROWSER_SEARCH_USER_DATA_DIR" in env:
            cfg.browser.user_data_dir = env["BROWSER_SEARCH_USER_DATA_DIR"]
        if "BROWSER_SEARCH_LAUNCH_TIMEOUT" in env:
            cfg.browser.launch_timeout = int(env["BROWSER_SEARCH_LAUNCH_TIMEOUT"])
        if "BROWSER_SEARCH_CACHE_ENABLED" in env:
            cfg.cache.enabled = _as_bool(env["BROWSER_SEARCH_CACHE_ENABLED"])
        if "BROWSER_SEARCH_CACHE_MAX_SIZE" in env:
            cfg.cache.max_size = int(env["BROWSER_SEARCH_CACHE_MAX_SIZE"])
        if "BROWSER_SEARCH_PROVIDER" in env:
            cfg.provider.name = env["BROWSER_SEARCH_PROVIDER"]
        if "BROWSER_SEARCH_TAVILY_KEY" in env:
            cfg.provider.tavily_api_key = env["BROWSER_SEARCH_TAVILY_KEY"]
        if "BROWSER_SEARCH_BRAVE_KEY" in env:
            cfg.provider.brave_api_key = env["BROWSER_SEARCH_BRAVE_KEY"]

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
            "provider": {
                "name": self.provider.name,
                "tavily_api_key": self.provider.tavily_api_key if self.provider.tavily_api_key else "",
                "brave_api_key": self.provider.brave_api_key if self.provider.brave_api_key else "",
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
        cfg.browser.headless = _as_bool(browser["headless"])
    if "user_data_dir" in browser:
        cfg.browser.user_data_dir = browser.get("user_data_dir")
    if "executable_path" in browser:
        cfg.browser.executable_path = browser.get("executable_path")
    if "launch_timeout" in browser:
        cfg.browser.launch_timeout = int(browser["launch_timeout"])
    cache = data.get("cache", {})
    if "enabled" in cache:
        cfg.cache.enabled = _as_bool(cache["enabled"])
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
    if "provider" in data:
        p = data["provider"]
        if "name" in p:
            cfg.provider.name = p["name"]
        if "tavily_api_key" in p:
            cfg.provider.tavily_api_key = p["tavily_api_key"]
        if "brave_api_key" in p:
            cfg.provider.brave_api_key = p["brave_api_key"]
    return cfg
