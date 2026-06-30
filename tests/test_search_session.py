from browser_search_mcp.config import AppConfig
from browser_search_mcp.search import SearchSession


def test_ensure_browser_uses_configured_browser_profile_and_timeout(monkeypatch):
    calls = []
    cfg = AppConfig()
    cfg.browser.name = "edge"
    cfg.browser.port = 9444
    cfg.browser.user_data_dir = "C:/profiles/search"
    cfg.browser.executable_path = "C:/edge/msedge.exe"
    cfg.browser.launch_timeout = 2

    monkeypatch.setattr("browser_search_mcp.search.cdp_mod.discover_ports", lambda ports=None: [])

    def fake_launch_browser(browser, **kwargs):
        kwargs["browser"] = browser
        calls.append(kwargs)
        return {"launched": True, "port": kwargs["port"]}

    monkeypatch.setattr("browser_search_mcp.search.cdp_mod.launch_browser", fake_launch_browser)

    result = SearchSession(config=cfg).ensure_browser(headless=True)

    assert result["source"] == "launched"
    assert calls[0] == {
        "browser": "edge",
        "port": 9444,
        "user_data_dir": "C:/profiles/search",
        "headless": True,
        "executable_path": "C:/edge/msedge.exe",
        "launch_timeout": 2,
    }


def test_detect_scans_configured_port_first(monkeypatch):
    seen_ports = []
    cfg = AppConfig()
    cfg.browser.port = 9444

    def fake_discover_ports(ports=None):
        seen_ports.append(ports)
        return [{"host": "127.0.0.1", "port": 9444, "browser": "Edge"}]

    monkeypatch.setattr("browser_search_mcp.search.cdp_mod.discover_ports", fake_discover_ports)
    monkeypatch.setattr("browser_search_mcp.search.bridge_mod.bridge_status", lambda: None)

    info = SearchSession(config=cfg).detect()

    assert info["cdp"]["available"] is True
    assert seen_ports[0][0] == 9444


def test_ensure_browser_continues_after_launch_failure(monkeypatch):
    calls = []
    cfg = AppConfig()
    cfg.browser.name = "edge"

    monkeypatch.setattr("browser_search_mcp.search.cdp_mod.discover_ports", lambda ports=None: [])

    def fake_launch_browser(browser, **kwargs):
        calls.append(browser)
        if browser == "edge":
            return {"launched": False, "error": "profile denied"}
        return {"launched": True, "port": kwargs["port"]}

    monkeypatch.setattr("browser_search_mcp.search.cdp_mod.launch_browser", fake_launch_browser)

    result = SearchSession(config=cfg).ensure_browser(headless=True)

    assert result["source"] == "launched"
    assert calls[:2] == ["edge", "chrome"]
