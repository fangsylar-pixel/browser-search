from browser_search_mcp import __main__


def test_cli_http_dispatches_to_http_api(monkeypatch):
    calls = []
    monkeypatch.setattr("sys.argv", ["browser-search-mcp", "http", "9191"])
    monkeypatch.setattr("browser_search_mcp.http_api.run", lambda port=None: calls.append(port))

    __main__.main()

    assert calls == [9191]
