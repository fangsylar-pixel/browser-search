import json

from browser_search_mcp import server


def test_search_cache_key_includes_options():
    cache = server.SearchCache()
    cache.set("mcp", "bing", "page1", page=1, max_results=3)
    cache.set("mcp", "bing", "page2", page=2, max_results=3)

    assert cache.get("mcp", "bing", page=1, max_results=3) == "page1"
    assert cache.get("mcp", "bing", page=2, max_results=3) == "page2"
    assert cache.get("mcp", "bing", page=1, max_results=5) is None


def test_normalize_results_unwraps_bing_redirect_url():
    results = server._normalize_results(
        [
            {
                "title": "MCP",
                "url": "https://www.bing.com/ck/a?!&&u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9kb2M&ntb=1",
                "snippet": "doc",
            }
        ],
        "bing",
    )

    assert results == [
        {
            "title": "MCP",
            "url": "https://example.com/doc",
            "snippet": "doc",
            "engine": "bing",
        }
    ]


def test_get_provider_uses_bridge_provider(monkeypatch):
    class DummyBridgeProvider:
        pass

    cfg = server.AppConfig()
    cfg.provider.name = "browser"
    monkeypatch.setattr(server.AppConfig, "load", classmethod(lambda cls: cfg))
    monkeypatch.setattr(
        "browser_search_mcp.bridge_provider.create_bridge_search_provider",
        lambda: DummyBridgeProvider(),
    )

    provider = server._get_provider()

    assert isinstance(provider, DummyBridgeProvider)


def test_web_search_returns_structured_browser_failure(monkeypatch):
    class FailingSession:
        available = False

        def detect(self):
            return {}

        def ensure_browser(self, headless=False):
            return {"source": "failed", "error": "no browser", "details": [{"browser": "edge"}]}

    monkeypatch.setattr(server, "get_provider_instance", lambda: None)
    monkeypatch.setattr(server, "get_session", lambda: FailingSession())
    monkeypatch.setattr(server, "_SEARCH_CACHE", None)

    payload = json.loads(server.web_search("mcp", engine="bing"))

    assert payload["ok"] is False
    assert payload["error"] == "no browser"
    assert payload["details"] == [{"browser": "edge"}]


def test_extract_current_page_returns_structured_content():
    class FakeSession:
        def evaluate(self, expression):
            return {
                "result": {
                    "result": {
                        "value": json.dumps(
                            {
                                "title": "Example",
                                "url": "https://example.com/final",
                                "description": "Description",
                                "site_name": "Example Site",
                                "published_time": "2026-06-30",
                                "content": "abcdef",
                            }
                        )
                    }
                }
            }

        def get_page_text(self):
            return "fallback"

    page = server._extract_current_page(FakeSession(), "https://example.com", max_length=3)

    assert page["ok"] is True
    assert page["title"] == "Example"
    assert page["content"] == "abc"
    assert page["length"] == 6
    assert page["truncated"] is True


def test_web_research_enriches_top_results(monkeypatch):
    monkeypatch.setattr(
        server,
        "web_search",
        lambda **kwargs: json.dumps([
            {"title": "MCP One", "url": "https://example.com/1", "snippet": "s1"},
            {"title": "MCP Two", "url": "https://example.com/2", "snippet": "s2"},
        ]),
    )
    monkeypatch.setattr(server, "get_session", lambda: object())
    monkeypatch.setattr(
        server,
        "_read_url_with_session",
        lambda session, url, max_length=5000: {
            "ok": True,
            "url": url,
            "title": "Page",
            "content": "content",
        },
    )

    payload = json.loads(server.web_research("mcp", max_results=2, read_top=1))

    assert payload["ok"] is True
    assert payload["results"][0]["id"] == 1
    assert payload["results"][0]["page"]["content"] == "content"
    assert "page" not in payload["results"][1]


def test_query_candidates_extract_customer_intent():
    candidates = server._query_candidates("比如我搜索今日头条游戏方面写哪些方面比较好")

    assert candidates[0] == "比如我搜索今日头条游戏方面写哪些方面比较好"
    assert "今日头条 游戏 选题 方向 赛道 爆款" in candidates
    assert "游戏 选题 方向 赛道 爆款" in candidates


def test_query_candidates_work_for_non_game_topics():
    candidates = server._query_candidates("小红书美食账号写什么选题比较好")

    assert "小红书 美食 选题 方向 赛道 爆款" in candidates
    assert "美食 选题 方向 赛道 爆款" in candidates


def test_extract_intent_does_not_treat_toutiao_as_today():
    intent = server._extract_intent("今日头条游戏方面写哪些比较好")

    assert intent["platform"] == ["今日头条"]
    assert intent["time"] == []


def test_web_search_plan_exposes_generic_intent():
    platform = "\u5c0f\u7ea2\u4e66"
    topic = "\u7f8e\u98df"
    task = "\u9009\u9898"
    query = f"{platform}{topic}\u8d26\u53f7\u5199\u4ec0\u4e48{task}\u6bd4\u8f83\u597d"

    plan = json.loads(server.web_search_plan(query))

    assert plan["intent"]["platform"] == [platform]
    assert plan["intent"]["topic"] == [topic]
    assert task in plan["intent"]["task"]
    assert f"{platform} {topic} {task} \u65b9\u5411 \u8d5b\u9053 \u7206\u6b3e" in plan["candidate_queries"]


def test_web_search_plan_handles_general_recommendation_questions():
    topic = "\u526f\u4e1a"
    query = f"\u9002\u5408\u666e\u901a\u4eba\u7684{topic}\u6709\u54ea\u4e9b"

    plan = json.loads(server.web_search_plan(query))

    assert plan["intent"]["topic"] == [topic]
    assert "\u63a8\u8350" in plan["intent"]["task"]
    assert "\u6e05\u5355" in plan["intent"]["task"]
    assert plan["required_anchor_groups"][-1]["label"] == "task"


def test_filter_relevant_results_removes_unrelated_pages():
    results = server._filter_relevant_results(
        "今日头条 游戏 创作",
        [
            {"title": "Nullarbor road trip", "url": "https://travel.example", "snippet": "Australia travel"},
            {"title": "今日头条游戏创作指南", "url": "https://example.com/game", "snippet": "游戏领域内容选题"},
        ],
    )

    assert len(results) == 1
    assert results[0]["title"] == "今日头条游戏创作指南"
    assert results[0]["matched_terms"] == ["今日头条", "游戏", "创作"]
    assert results[0]["coverage"] == "strict"


def test_filter_relevant_results_can_require_anchor_groups():
    strict = server._filter_relevant_results(
        "今日头条 游戏 创作",
        [
            {"title": "今日头条爆款文章", "url": "https://example.com/toutiao", "snippet": "创作选题"},
            {"title": "今日头条游戏攻略创作", "url": "https://example.com/game", "snippet": "手游选题"},
        ],
        require_anchor_groups=True,
    )

    assert len(strict) == 1
    assert strict[0]["title"] == "今日头条游戏攻略创作"
    assert strict[0]["matched_anchor_groups"] == ["platform", "topic", "task"]


def test_generic_guide_does_not_satisfy_game_anchor():
    strict = server._filter_relevant_results(
        "今日头条 游戏 创作",
        [
            {"title": "今日头条创作者收益全攻略", "url": "https://example.com/toutiao", "snippet": "创作选题"}
        ],
        require_anchor_groups=True,
    )

    assert strict == []


def test_web_research_retries_when_first_results_are_irrelevant(monkeypatch):
    calls = []

    def fake_web_search(**kwargs):
        calls.append((kwargs["query"], kwargs["engine"]))
        if len(calls) == 1:
            return json.dumps([
                {"title": "Nullarbor road trip", "url": "https://travel.example", "snippet": "Australia travel"}
            ])
        return json.dumps([
            {"title": "今日头条游戏创作指南", "url": "https://example.com/game", "snippet": "游戏领域内容选题"}
        ])

    monkeypatch.setattr(server, "web_search", fake_web_search)
    monkeypatch.setattr(server, "get_session", lambda: object())
    monkeypatch.setattr(
        server,
        "_read_url_with_session",
        lambda session, url, max_length=5000: {
            "ok": True,
            "url": url,
            "title": "Page",
            "content": "content",
        },
    )

    payload = json.loads(server.web_research("今日头条 游戏 创作", engine="bing", max_results=1, read_top=1))

    assert payload["ok"] is True
    assert len(payload["attempts"]) >= 2
    assert payload["results"][0]["title"] == "今日头条游戏创作指南"


def test_web_research_marks_partial_when_domain_anchor_missing(monkeypatch):
    monkeypatch.setattr(
        server,
        "web_search",
        lambda **kwargs: json.dumps([
            {"title": "今日头条爆款文章", "url": "https://example.com/toutiao", "snippet": "创作选题"}
        ]),
    )
    monkeypatch.setattr(server, "get_session", lambda: object())
    monkeypatch.setattr(
        server,
        "_read_url_with_session",
        lambda session, url, max_length=5000: {"ok": True, "url": url, "content": "content"},
    )

    payload = json.loads(server.web_research("今日头条 游戏 创作", engine="bing", max_results=1, read_top=0))

    assert payload["ok"] is True
    assert payload["quality"] == "partial"
    assert payload["warnings"]
    assert payload["diagnostics"]["missing_anchor_groups"] == ["topic"]
    assert payload["results"][0]["missing_anchor_groups"] == ["topic"]


def test_web_research_returns_diagnostics_when_no_relevant_results(monkeypatch):
    monkeypatch.setattr(
        server,
        "web_search",
        lambda **kwargs: json.dumps([
            {"title": "Nullarbor road trip", "url": "https://travel.example", "snippet": "Australia travel"}
        ]),
    )

    payload = json.loads(server.web_research(
        "\u5c0f\u7ea2\u4e66\u7f8e\u98df\u8d26\u53f7\u5199\u4ec0\u4e48\u9009\u9898\u6bd4\u8f83\u597d",
        engine="bing",
        max_results=1,
        read_top=0,
        auto_expand=False,
    ))

    assert payload["ok"] is False
    assert payload["diagnostics"]["intent"]["platform"] == ["\u5c0f\u7ea2\u4e66"]
    assert payload["diagnostics"]["intent"]["topic"] == ["\u7f8e\u98df"]
    assert payload["diagnostics"]["candidate_queries"]
