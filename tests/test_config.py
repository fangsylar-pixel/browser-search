from browser_search_mcp.config import AppConfig, _merge_config


def test_merge_browser_user_data_dir_and_provider_once():
    cfg = _merge_config(
        AppConfig(),
        {
            "browser": {
                "name": "chrome",
                "port": 9333,
                "user_data_dir": "C:/tmp/browser-profile",
                "executable_path": "C:/browser/chrome.exe",
                "launch_timeout": 3,
            },
            "provider": {
                "name": "brave",
                "brave_api_key": "key",
            },
        },
    )

    assert cfg.browser.name == "chrome"
    assert cfg.browser.port == 9333
    assert cfg.browser.user_data_dir == "C:/tmp/browser-profile"
    assert cfg.browser.executable_path == "C:/browser/chrome.exe"
    assert cfg.browser.launch_timeout == 3
    assert cfg.provider.name == "brave"
    assert cfg.provider.brave_api_key == "key"


def test_merge_string_booleans():
    cfg = _merge_config(
        AppConfig(),
        {
            "browser": {"headless": "false"},
            "cache": {"enabled": "true"},
        },
    )

    assert cfg.browser.headless is False
    assert cfg.cache.enabled is True
