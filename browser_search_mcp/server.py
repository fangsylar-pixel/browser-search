"""FastMCP server exposing web search tools.

Built on the browser-takeover-bridge architecture. Uses CDP
(Chrome DevTools Protocol) to control a browser for search,
with optional integration with the browser-takeover extension
for authenticated browsing sessions.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from typing import Any

from fastmcp import FastMCP

from . import bridge as bridge_mod
from . import cdp as cdp_mod
from .config import AppConfig
from .search import EXTRACTORS, SEARCH_ENGINES, PARSERS, SearchSession, SearchResults, _deduplicate_results, get_engine_health
from .providers import get_provider as _get_api_provider
import urllib.parse


# ── Logging ──────────────────────────────────────────────────────────

logging.basicConfig(
   level=logging.INFO,
   format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("browser-search-mcp")


def _get_provider():
    cfg = AppConfig.load()
    if cfg.provider.name == "browser":
        try:
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as _TimeoutError
            from . import bridge_provider as _bp
            with ThreadPoolExecutor(max_workers=1) as _exec:
                _fut = _exec.submit(_bp.create_bridge_search_provider)
                bridge_prov = _fut.result(timeout=4)
            if bridge_prov is not None:
                log.info("Using browser-takeover extension bridge for search")
                return bridge_prov
        except _TimeoutError:
            log.debug("Bridge provider connection timed out (4s)")
        except Exception as e:
            log.debug("Bridge provider not available: %s", e)
    if cfg.provider.name in ("tavily", "brave"):
        try:
            api_prov = _get_api_provider(config=cfg)
            if api_prov is not None:
                log.info("Using API provider: %s", cfg.provider.name)
                return api_prov
        except Exception as e:
            log.warning("API provider init failed: %s", e)
    return None


# ── Result Cache ────────────────────────────────────────────────────
from collections import OrderedDict
import time as _time

class SearchCache:
    """LRU cache for search results with configurable TTL."""
    def __init__(self, max_size=100, ttl=300):
        self._max = max_size
        self._ttl = ttl
        self._data = OrderedDict()
    def _key(self, q, e, **options):
        option_bits = "&".join(f"{key}={options[key]}" for key in sorted(options))
        return e + "::" + q.lower().strip() + "::" + option_bits
    def get(self, q, e, **options):
        k = self._key(q, e, **options)
        if k in self._data:
            r, t = self._data[k]
            if _time.time() - t < self._ttl:
                self._data.move_to_end(k)
                return r
            del self._data[k]
        return None
    def set(self, q, e, r, **options):
        k = self._key(q, e, **options)
        self._data[k] = (r, _time.time())
        self._data.move_to_end(k)
        while len(self._data) > self._max:
            self._data.popitem(last=False)
    def clear(self):
        self._data.clear()
    @property
    def stats(self):
        return {"size": len(self._data), "max": self._max, "ttl": self._ttl}

_cfg = AppConfig.load()
_SEARCH_CACHE = SearchCache(max_size=_cfg.cache.max_size, ttl=_cfg.cache.ttl) if _cfg.cache.enabled else None

# ── Retry helper ────────────────────────────────────────────────────
def with_retry(func, args, kwargs, max_retries=2):
    import time as _t
    for a in range(max_retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception:
            if a < max_retries:
                _t.sleep(1.0 * (a + 1))
                continue
            raise


# ── Server instance ──────────────────────────────────────────────────

def _decode_bing_url(value: str) -> str | None:
    """Decode Bing's base64-like redirect URL payload."""
    import base64

    if value.startswith("a1"):
        value = value[2:]
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding).decode("utf-8")
    except Exception:
        return None


def _unwrap_result_url(url: str) -> str:
    """Convert common search redirect URLs into their target URL."""
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)

    if "google." in parsed.netloc and parsed.path == "/url" and query.get("q"):
        return query["q"][0]
    if "duckduckgo." in parsed.netloc and query.get("uddg"):
        return query["uddg"][0]
    if "bing." in parsed.netloc and parsed.path.startswith("/ck/") and query.get("u"):
        decoded = _decode_bing_url(query["u"][0])
        if decoded:
            return decoded
    return url


def _normalize_results(results: list[dict], engine: str) -> list[dict]:
    normalized = []
    for item in results:
        if not isinstance(item, dict):
            continue
        normalized_item = dict(item)
        normalized_item["url"] = _unwrap_result_url(str(normalized_item.get("url", "")))
        normalized_item.setdefault("engine", engine)
        normalized.append(normalized_item)
    return normalized


_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with",
    "what", "which", "how", "why", "is", "are", "我", "想", "要", "的是",
    "让", "工具", "搜索", "结果", "给我", "比如", "方面", "哪些", "比较",
    "好", "写", "客户", "预期", "懂吗", "需要", "看看", "效果",
}


_CHINESE_STOP_PHRASES = (
    "比如", "我想要的是", "我想要", "我想", "我要", "我", "搜索",
    "结果", "给我", "方面", "哪些", "比较好", "好", "写", "的是",
    "这个", "那个", "客户", "预期", "懂吗", "需要", "看看", "效果",
)


_CHINESE_DOMAIN_TERMS = (
    "今日头条", "头条号", "西瓜视频", "抖音", "游戏", "手游", "端游",
    "攻略", "选题", "创作", "内容", "爆款", "热点", "流量", "推荐",
    "玩家", "版本", "更新", "活动", "角色", "强度", "零氪", "平民",
    "避坑", "新手", "测评", "盘点", "资讯", "教程",
)


def _chinese_intent_terms(query: str) -> list[str]:
    compact = re.sub(r"\s+", "", query)
    for phrase in _CHINESE_STOP_PHRASES:
        compact = compact.replace(phrase, " ")

    terms = []
    for term in _CHINESE_DOMAIN_TERMS:
        if term in query and term not in terms:
            terms.append(term)

    for token in re.findall(r"[\u4e00-\u9fff]{2,}", compact):
        if token not in _STOPWORDS and token not in terms:
            terms.append(token)

    if any(word in query for word in ("写", "哪些方面", "创作", "内容")):
        for term in ("创作", "选题", "内容", "爆款"):
            if term not in terms:
                terms.append(term)
    if "游戏" in query and "攻略" not in terms:
        terms.append("攻略")
    return terms


def _query_terms(query: str) -> list[str]:
    terms = []
    for term in _chinese_intent_terms(query):
        if term not in terms:
            terms.append(term)
    for token in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9_\-+.]{1,}", query):
        token = token.strip().lower()
        if token and token not in _STOPWORDS and token not in terms:
            terms.append(token)
    return terms


def _query_candidates(query: str, max_candidates: int = 5) -> list[str]:
    terms = _query_terms(query)
    candidates = [query.strip()]
    if terms:
        candidates.append(" ".join(terms))
    if "今日头条" in terms and "游戏" in terms:
        candidates.append("今日头条 游戏 手游 攻略 选题")
        candidates.append("今日头条 游戏 创作 选题")
        candidates.append("头条号 游戏 选题 爆款")
        candidates.append("今日头条 游戏 攻略 内容")
    chinese_terms = [term for term in terms if re.search(r"[\u4e00-\u9fff]", term)]
    if len(chinese_terms) >= 2:
        candidates.append(" ".join(f'"{term}"' for term in chinese_terms[:6]))
        candidates.append(" ".join(chinese_terms[:4]))
    if len(terms) >= 3:
        candidates.append(" ".join(terms[:3]))

    unique = []
    for candidate in candidates:
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique[:max_candidates]


def _result_relevance_score(query: str, item: dict) -> float:
    terms = _query_terms(query)
    if not terms:
        return 1.0
    haystack = " ".join(
        str(item.get(key, ""))
        for key in ("title", "snippet", "url", "engine")
    ).lower()
    hits = 0.0
    for term in terms:
        if term in haystack:
            hits += 1.0
        elif re.search(r"[\u4e00-\u9fff]", term):
            chars = set(term)
            if chars and sum(1 for ch in chars if ch in haystack) / len(chars) >= 0.6:
                hits += 0.5
    return hits / max(len(terms), 1)


def _anchor_terms(query: str) -> list[str]:
    anchors = []
    for term in ("今日头条", "头条号", "游戏", "手游", "攻略", "选题", "创作"):
        if term in query and term not in anchors:
            anchors.append(term)
    return anchors


def _required_anchor_groups(query: str) -> list[dict]:
    groups = []
    if any(term in query for term in ("今日头条", "头条号")):
        groups.append({"label": "platform", "terms": ["今日头条", "头条号", "toutiao"]})
    if any(term in query for term in ("游戏", "手游", "端游")):
        groups.append({
            "label": "game",
            "terms": ["游戏", "手游", "端游", "玩家", "game"],
        })
    return groups


def _matched_anchor_groups(haystack: str, groups: list[dict]) -> list[str]:
    matched = []
    for group in groups:
        if any(term.lower() in haystack for term in group["terms"]):
            matched.append(group["label"])
    return matched


def _filter_relevant_results(
    query: str,
    results: list[dict],
    min_score: float = 0.2,
    require_anchor_groups: bool = False,
) -> list[dict]:
    scored = []
    anchors = _anchor_terms(query)
    required_groups = _required_anchor_groups(query)
    for item in results:
        score = _result_relevance_score(query, item)
        if score >= min_score:
            enriched = dict(item)
            haystack = " ".join(
                str(item.get(key, ""))
                for key in ("title", "snippet", "url")
            ).lower()
            matched_anchors = [term for term in anchors if term.lower() in haystack]
            missing_anchors = [term for term in anchors if term not in matched_anchors]
            matched_groups = _matched_anchor_groups(haystack, required_groups)
            if require_anchor_groups and len(matched_groups) < len(required_groups):
                continue
            enriched["relevance"] = round(score, 3)
            enriched["matched_terms"] = matched_anchors
            enriched["missing_terms"] = missing_anchors
            enriched["matched_anchor_groups"] = matched_groups
            enriched["missing_anchor_groups"] = [
                group["label"] for group in required_groups if group["label"] not in matched_groups
            ]
            enriched["coverage"] = "strict" if len(matched_groups) == len(required_groups) else "partial"
            scored.append(enriched)
    scored.sort(
        key=lambda item: (len(item.get("matched_terms", [])), item.get("relevance", 0)),
        reverse=True,
    )
    return _deduplicate_results(scored)


_PLATFORM_VOCAB = {
    "platform": [
        "今日头条", "头条号", "抖音", "小红书", "B站", "哔哩哔哩", "知乎",
        "公众号", "微信公众号", "视频号", "快手", "YouTube", "TikTok",
    ],
}


_TOPIC_VOCAB = {
    "topic": [
        "游戏", "手游", "端游", "美食", "母婴", "科技", "数码", "职场",
        "财经", "旅游", "教育", "AI", "人工智能", "汽车", "房产", "健康",
        "健身", "情感", "历史", "娱乐", "影视", "宠物", "本地生活", "电商",
        "穿搭", "美妆", "家居", "法律", "心理", "英语", "考研", "副业",
        "投影仪", "电视", "家电", "新能源", "新能源汽车",
    ],
}


_TASK_VOCAB = {
    "task": [
        "选题", "创作", "内容", "爆款", "攻略", "教程", "推荐", "对比",
        "测评", "避坑", "趋势", "热点", "变现", "赚钱", "涨粉", "运营",
        "标题", "脚本", "文案", "复盘", "案例", "清单", "指南",
        "复习", "获客", "个人IP", "选品", "安排", "计划", "选购", "带货", "科普",
    ],
}


_AUDIENCE_VOCAB = {
    "audience": [
        "新手", "普通人", "学生", "宝妈", "上班族", "小白", "零氪", "平民",
        "创业者", "创作者", "商家", "家长", "年轻人", "中老年",
    ],
}


_TIME_VOCAB = {
    "time": ["今日", "今天", "最近", "最新", "今年", "本周", "本月", "2026"],
}


_TASK_EXPANSIONS = {
    "选题": ["选题", "方向", "赛道", "爆款", "案例"],
    "创作": ["创作", "内容", "标题", "选题", "爆款"],
    "攻略": ["攻略", "教程", "避坑", "新手", "指南"],
    "推荐": ["推荐", "排行", "对比", "测评", "避坑"],
    "变现": ["变现", "收益", "赚钱", "运营", "涨粉"],
    "对比": ["对比", "哪个好", "优缺点", "选购", "推荐"],
    "复习": ["复习", "备考", "计划", "资料", "方法"],
    "获客": ["获客", "线索", "转化", "运营", "案例"],
    "个人IP": ["个人IP", "定位", "内容", "运营", "涨粉"],
    "选品": ["选品", "爆品", "利润", "货源", "趋势"],
    "安排": ["安排", "计划", "方法", "清单", "指南"],
    "选购": ["选购", "对比", "推荐", "避坑", "测评"],
    "带货": ["带货", "脚本", "转化", "卖点", "案例"],
    "科普": ["科普", "选题", "案例", "内容", "脚本"],
}


def _extract_intent(query: str) -> dict:
    groups = {
        "platform": _PLATFORM_VOCAB["platform"],
        "topic": _TOPIC_VOCAB["topic"],
        "task": _TASK_VOCAB["task"],
        "audience": _AUDIENCE_VOCAB["audience"],
        "time": _TIME_VOCAB["time"],
    }
    intent = {"raw": query}
    for group, vocab in groups.items():
        hits = []
        for term in vocab:
            if group == "time" and term == "今日" and "今日头条" in query:
                continue
            if term.lower() in query.lower() and term not in hits:
                hits.append(term)
        intent[group] = hits

    if any(word in query for word in ("写什么", "写哪些", "哪些方面", "做什么方向", "怎么写")):
        for term in ("选题", "创作", "内容"):
            if term not in intent["task"]:
                intent["task"].append(term)
    phrase_tasks = {
        "哪个好": ["对比", "选购", "推荐"],
        "怎么复习": ["复习", "计划"],
        "怎么获客": ["获客", "运营"],
        "个人IP": ["个人IP", "运营"],
        "怎么选品": ["选品"],
        "怎么安排": ["安排", "计划"],
        "有哪些": ["推荐", "清单"],
        "适合": ["推荐"],
    }
    for phrase, tasks in phrase_tasks.items():
        if phrase in query:
            for term in tasks:
                if term not in intent["task"]:
                    intent["task"].append(term)
    return intent


def _query_terms(query: str) -> list[str]:
    intent = _extract_intent(query)
    terms = []
    for group in ("platform", "topic", "task", "audience", "time"):
        for term in intent[group]:
            if term not in terms:
                terms.append(term)
    for term in _chinese_intent_terms(query):
        if term not in terms:
            terms.append(term)
    for token in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9_\-+.]{1,}", query):
        token = token.strip()
        if token and token.lower() not in _STOPWORDS and token not in terms:
            terms.append(token)
    return terms


def _query_candidates(query: str, max_candidates: int = 8) -> list[str]:
    intent = _extract_intent(query)
    terms = _query_terms(query)
    candidates = [query.strip()]

    platform = intent["platform"][0] if intent["platform"] else ""
    topic = " ".join(intent["topic"][:2]) if intent["topic"] else ""
    primary_task = intent["task"][0] if intent["task"] else ""
    task_terms = _TASK_EXPANSIONS.get(primary_task, intent["task"] or ["选题", "方向", "攻略"])

    if platform and topic:
        candidates.append(" ".join([platform, topic, *task_terms[:4]]))
        if intent["audience"]:
            candidates.append(" ".join([platform, topic, intent["audience"][0], *task_terms[:3]]))
    if topic:
        candidates.append(" ".join([topic, *task_terms[:4]]))
    if platform:
        candidates.append(" ".join([platform, *task_terms[:4]]))
    if terms:
        candidates.append(" ".join(terms[:8]))

    chinese_terms = [term for term in terms if re.search(r"[\u4e00-\u9fff]", term)]
    if len(chinese_terms) >= 2:
        candidates.append(" ".join(f'"{term}"' for term in chinese_terms[:6]))
        candidates.append(" ".join(chinese_terms[:4]))

    unique = []
    for candidate in candidates:
        candidate = re.sub(r"\s+", " ", candidate).strip()
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique[:max_candidates]


def _anchor_terms(query: str) -> list[str]:
    intent = _extract_intent(query)
    anchors = []
    for group in ("platform", "topic", "task"):
        for term in intent[group]:
            if term not in anchors:
                anchors.append(term)
    return anchors


def _required_anchor_groups(query: str) -> list[dict]:
    intent = _extract_intent(query)
    groups = []
    if intent["platform"]:
        groups.append({"label": "platform", "terms": intent["platform"]})
    if intent["topic"]:
        topic_terms = list(intent["topic"])
        if "游戏" in topic_terms:
            topic_terms.extend(["手游", "端游", "玩家", "game"])
        groups.append({"label": "topic", "terms": topic_terms})
    if intent["task"]:
        task_terms = list(intent["task"])
        for task in intent["task"]:
            task_terms.extend(_TASK_EXPANSIONS.get(task, []))
        groups.append({"label": "task", "terms": list(dict.fromkeys(task_terms))})
    return groups


def _filter_relevant_results(
    query: str,
    results: list[dict],
    min_score: float = 0.2,
    require_anchor_groups: bool = False,
) -> list[dict]:
    scored = []
    anchors = _anchor_terms(query)
    required_groups = _required_anchor_groups(query)
    for item in results:
        score = _result_relevance_score(query, item)
        haystack = " ".join(
            str(item.get(key, ""))
            for key in ("title", "snippet", "url")
        ).lower()
        matched_groups = _matched_anchor_groups(haystack, required_groups)
        if score < min_score and len(matched_groups) < max(1, len(required_groups) - 1):
            continue
        if require_anchor_groups and len(matched_groups) < len(required_groups):
            continue

        enriched = dict(item)
        matched_anchors = [term for term in anchors if term.lower() in haystack]
        missing_anchors = [term for term in anchors if term not in matched_anchors]
        enriched["relevance"] = round(score, 3)
        enriched["matched_terms"] = matched_anchors
        enriched["missing_terms"] = missing_anchors
        enriched["matched_anchor_groups"] = matched_groups
        enriched["missing_anchor_groups"] = [
            group["label"] for group in required_groups if group["label"] not in matched_groups
        ]
        enriched["coverage"] = "strict" if len(matched_groups) == len(required_groups) else "partial"
        scored.append(enriched)
    scored.sort(
        key=lambda item: (len(item.get("matched_anchor_groups", [])), item.get("relevance", 0)),
        reverse=True,
    )
    return _deduplicate_results(scored)


def _search_plan_payload(query: str, max_candidates: int = 8) -> dict:
    """Describe how a natural-language request will be searched."""
    groups = _required_anchor_groups(query)
    return {
        "query": query,
        "intent": _extract_intent(query),
        "required_anchor_groups": groups,
        "candidate_queries": _query_candidates(query, max_candidates=max_candidates),
    }


def _research_diagnostics(query: str, attempts: list[dict], results: list[dict]) -> dict:
    """Summarize search coverage so callers can decide whether to trust results."""
    plan = _search_plan_payload(query)
    missing_groups = sorted({
        group
        for item in results
        for group in item.get("missing_anchor_groups", [])
    })
    best_attempt = None
    if attempts:
        best_attempt = max(
            attempts,
            key=lambda item: (item.get("strict_count", 0), item.get("partial_count", 0), item.get("raw_count", 0)),
        )
    return {
        **plan,
        "attempt_count": len(attempts),
        "best_attempt": best_attempt,
        "missing_anchor_groups": missing_groups,
    }


PAGE_EXTRACTOR = r"""
(() => {
  const textOf = (selector) => {
    const el = document.querySelector(selector);
    return el ? (el.content || el.textContent || '').trim() : '';
  };
  const badSelectors = 'script,style,noscript,svg,canvas,iframe,nav,footer,header,aside,form';
  const clone = document.body ? document.body.cloneNode(true) : document.createElement('body');
  clone.querySelectorAll(badSelectors).forEach(el => el.remove());
  const blocks = Array.from(clone.querySelectorAll('article, main, [role="main"], p, li, h1, h2, h3'))
    .map(el => (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim())
    .filter(Boolean);
  const seen = new Set();
  const content = [];
  for (const block of blocks) {
    if (block.length < 30 && !/^h[1-3]$/i.test(block.tagName || '')) continue;
    const key = block.slice(0, 160);
    if (seen.has(key)) continue;
    seen.add(key);
    content.push(block);
    if (content.join('\n\n').length > 30000) break;
  }
  return JSON.stringify({
    title: document.title || textOf('h1'),
    url: location.href,
    description: textOf('meta[name="description"]') || textOf('meta[property="og:description"]'),
    site_name: textOf('meta[property="og:site_name"]'),
    published_time: textOf('meta[property="article:published_time"]') ||
      textOf('meta[name="article:published_time"]') ||
      textOf('time[datetime]') ||
      (document.querySelector('time') ? document.querySelector('time').getAttribute('datetime') || document.querySelector('time').textContent.trim() : ''),
    content: content.join('\n\n')
  });
})()
"""


def _extract_current_page(session: SearchSession, requested_url: str, max_length: int = 5000) -> dict:
    try:
        eval_result = session.evaluate(PAGE_EXTRACTOR)
        raw = eval_result.get("result", {}).get("result", {}).get("value", "{}")
        data = json.loads(raw or "{}")
    except Exception:
        data = {
            "title": "",
            "url": requested_url,
            "description": "",
            "site_name": "",
            "published_time": "",
            "content": session.get_page_text(),
        }

    content = data.get("content") or ""
    return {
        "ok": True,
        "requested_url": requested_url,
        "url": data.get("url") or requested_url,
        "title": data.get("title") or "",
        "description": data.get("description") or "",
        "site_name": data.get("site_name") or "",
        "published_time": data.get("published_time") or "",
        "content": content[:max_length],
        "length": len(content),
        "truncated": len(content) > max_length,
    }


def _read_url_with_session(session: SearchSession, url: str, max_length: int = 5000) -> dict:
    if not url:
        return {"ok": False, "error": "URL is required"}
    session.navigate(url)
    time.sleep(2.0)
    return _extract_current_page(session, url, max_length=max_length)


mcp = FastMCP("browser-search-mcp")

# Shared session (lazy-initialized on first search)
_session: SearchSession | None = None


def get_session() -> SearchSession:
   """Get or create the shared search session."""
   global _session
   if _session is None:
       _session = SearchSession(config=AppConfig.load())
   return _session


# ──   Provider instance (lazy, may be bridge/API/CDP) 

_provider_instance = None


def get_provider_instance():
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = _get_provider()
    return _provider_instance


# MCP Tools ────────────────────────────────────────────────────────

@mcp.tool()
def web_search_plan(query: str, max_candidates: int = 8) -> str:
   """Analyze a natural-language search request before running the browser.

   Returns parsed intent, required coverage groups, and expanded candidate
   queries. This is useful when callers need predictable search behavior
   across many domains rather than a single hard-coded topic.
   """
   return json.dumps(
       _search_plan_payload(query, max_candidates=max_candidates),
       ensure_ascii=False,
       indent=2,
   )


@mcp.tool()
def web_search(
   query: str,
   engine: str = "google",
   max_results: int = 10,
   headless: bool = True,
   page: int = 1,
   time_range: str = "",
   deep_mode: bool = False,
) -> str:
   """Search the web using a real browser and return structured results.
    
   Uses Chrome/Edge via CDP (same approach as browser-takeover-bridge)
   to navigate to the search engine, extract results from the DOM,
   and return them as structured JSON.
    
   When the browser-takeover extension bridge is available, searches
   use the extension's authenticated browser session instead of a
   headless browser -- giving access to logged-in content.
    
   Args:
       query: The search query string
       engine: Search engine: google, bing, baidu, or duckduckgo
       max_results: Maximum number of results to return (1-20)
       headless: Run browser in headless mode (no visible window)
    
   Returns:
       JSON array of {title, url, snippet} objects
   """
   # Try bridge / API provider first
   provider = get_provider_instance()
   if provider is not None:
       try:
           results = provider.search(
               query=query,
               engine=engine,
               max_results=max_results,
           )
           results = _normalize_results(results, engine)
           result_str = json.dumps(results[:max_results], ensure_ascii=False, indent=2)
           if _SEARCH_CACHE is not None:
               _SEARCH_CACHE.set(query, engine, result_str, max_results=max_results, page=page, time_range=time_range, deep_mode=deep_mode)
           return result_str
       except Exception as exc:
           log.warning("Provider search failed, falling back to CDP: %s", exc)

   # CDP browser path
   session = get_session()
   
   # Check cache first
   if _SEARCH_CACHE is not None:
       cached = _SEARCH_CACHE.get(query, engine, max_results=max_results, page=page, time_range=time_range, deep_mode=deep_mode)
       if cached is not None:
           return cached
   
   # Ensure browser is ready
   try:
       info = session.detect()
       if not session.available:
           result = session.ensure_browser(headless=headless)
           if result.get("source") == "failed":
               return json.dumps({
                   "ok": False,
                   "error": result.get("error", "No browser available"),
                   "details": result.get("details", []),
               }, ensure_ascii=False)
   except Exception as exc:
       return json.dumps({"ok": False, "error": f"Browser detection failed: {exc}"}, ensure_ascii=False)
    
   # Build search URL
   if engine not in SEARCH_ENGINES:
       return json.dumps({
           "ok": False,
           "error": f"Unsupported engine: {engine}. Supported: {', '.join(SEARCH_ENGINES.keys())}"
       }, ensure_ascii=False)
    
   engine_config = SEARCH_ENGINES[engine]
   search_url = engine_config["url"].format(query=urllib.parse.quote_plus(query))
    
   try:
       # Navigate to search
       session.navigate(search_url)
       time.sleep(1.5)
        
       # Try JavaScript DOM extraction (more accurate)
       extractor = EXTRACTORS.get(engine)
       results: list[dict] = []
       if extractor:
           try:
               eval_result = session.evaluate(extractor)
               raw = eval_result.get("result", {}).get("result", {}).get("value", "[]")
               if raw and raw != "[]":
                   parsed = json.loads(raw)
                   if parsed:
                       results = parsed
           except Exception:
               pass
        
       # Fallback to text-based parsing
       if not results:
           text = session.get_page_text()
           parser = PARSERS.get(engine)
           if parser:
               results = parser(text)
        
       results = _normalize_results(results, engine)
       if deep_mode:
           for item in results[:2]:
               page_url = item.get("url", "")
               if not page_url:
                   continue
               try:
                   page_data = _read_url_with_session(session, page_url, max_length=2000)
                   item["page"] = {
                       "title": page_data.get("title", ""),
                       "description": page_data.get("description", ""),
                       "site_name": page_data.get("site_name", ""),
                       "published_time": page_data.get("published_time", ""),
                       "content": page_data.get("content", ""),
                       "truncated": page_data.get("truncated", False),
                   }
               except Exception as exc:
                   item["page"] = {"ok": False, "error": str(exc)}
       result_str = json.dumps(results[:max_results], ensure_ascii=False, indent=2)
       if _SEARCH_CACHE is not None:
           _SEARCH_CACHE.set(query, engine, result_str, max_results=max_results, page=page, time_range=time_range, deep_mode=deep_mode)
       return result_str
    
   except Exception as exc:
       return json.dumps({"ok": False, "error": f"Search failed: {exc}"}, ensure_ascii=False)


@mcp.tool()
def web_search_multi(
   query: str,
   engines: str = "google,bing,duckduckgo",
   max_results_per_engine: int = 5,
   headless: bool = True,
   page: int = 1,
   time_range: str = "",
   deep_mode: bool = False,
   deduplicate: bool = False,
) -> str:
   """Search multiple search engines and combine results.
    
   Searches multiple engines in sequence and returns
   combined results grouped by engine.
    
   Args:
       query: The search query string
       engines: Comma-separated list of engines (google,bing,baidu,duckduckgo)
       max_results_per_engine: Results per engine (1-10)
       headless: Run browser in headless mode
    
   Returns:
       JSON object with engine names as keys and result arrays as values
   """
   engine_list = [e.strip() for e in engines.split(",") if e.strip()]
   combined: dict[str, Any] = {}
    
   for engine in engine_list:
       combined[engine] = json.loads(
           web_search(query, engine, max_results_per_engine, headless, page, time_range, deep_mode)
       )
    
   # Optional dedup across engines
   if deduplicate:
       all_results = []
       for eng_results in combined.values():
           if isinstance(eng_results, list):
               all_results.extend(eng_results)
       deduped = _deduplicate_results(all_results)
       combined["_combined"] = deduped
    
   return json.dumps(combined, ensure_ascii=False, indent=2)


@mcp.tool()
def web_search_read_page(
   url: str,
   max_length: int = 5000,
) -> str:
   """Navigate to a URL and return structured page content.
    
   Useful for reading the full content of a search result.
    
   Args:
       url: The URL to navigate to
       max_length: Maximum characters to return
    
   Returns:
       The visible text content of the page
   """
   session = get_session()
   try:
       if not session.available:
           result = session.ensure_browser()
           if result.get("source") == "failed":
               return json.dumps({
                   "ok": False,
                   "error": result.get("error", "No browser available"),
                   "details": result.get("details", []),
               }, ensure_ascii=False)
        
       page = _read_url_with_session(session, url, max_length=max_length)
       return json.dumps(page, ensure_ascii=False, indent=2)
   except Exception as exc:
       return json.dumps({"ok": False, "error": f"Failed to read page: {exc}"}, ensure_ascii=False)


@mcp.tool()
def web_research(
   query: str,
   engine: str = "bing",
   max_results: int = 5,
   read_top: int = 3,
   headless: bool = True,
   page_content_length: int = 2500,
   auto_expand: bool = True,
   min_relevance: float = 0.2,
) -> str:
   """Search and read top result pages for agent-friendly research.

   Returns search results plus cleaned page content for the top N results,
   making it easier for an LLM to answer with citations.
   """
   engine_list = [e.strip() for e in engine.split(",") if e.strip()]
   if auto_expand:
       for fallback_engine in ("bing", "duckduckgo", "google", "baidu"):
           if fallback_engine not in engine_list:
               engine_list.append(fallback_engine)
   query_list = _query_candidates(query) if auto_expand else [query]

   attempts = []
   results: list[dict] = []
   fallback_results: list[dict] = []
   fallback_engine = engine
   last_error: dict | None = None
   quality = "strict"
   warnings: list[str] = []

   for candidate in query_list:
       for candidate_engine in engine_list:
           raw_results = web_search(
               query=candidate,
               engine=candidate_engine,
               max_results=max(max_results, 8),
               headless=headless,
           )
           try:
               parsed = json.loads(raw_results)
           except Exception:
               last_error = {"ok": False, "error": "Search returned invalid JSON", "raw": raw_results}
               attempts.append({
                   "query": candidate,
                   "engine": candidate_engine,
                   "ok": False,
                   "error": "invalid_json",
               })
               continue

           if isinstance(parsed, dict) and parsed.get("ok") is False:
               last_error = parsed
               attempts.append({
                   "query": candidate,
                   "engine": candidate_engine,
                   "ok": False,
                   "error": parsed.get("error", "search_failed"),
               })
               continue
           if not isinstance(parsed, list):
               attempts.append({
                   "query": candidate,
                   "engine": candidate_engine,
                   "ok": False,
                   "error": "non_list_result",
               })
               continue

           strict_relevant = _filter_relevant_results(
               query,
               parsed,
               min_score=min_relevance,
               require_anchor_groups=True,
           )
           partial_relevant = _filter_relevant_results(
               query,
               parsed,
               min_score=min_relevance,
               require_anchor_groups=False,
           )
           attempts.append({
               "query": candidate,
               "engine": candidate_engine,
               "ok": True,
               "raw_count": len(parsed),
               "strict_count": len(strict_relevant),
               "partial_count": len(partial_relevant),
           })
           if strict_relevant:
               results = strict_relevant
               engine = candidate_engine
               break
           if partial_relevant and not fallback_results:
               fallback_results = partial_relevant
               fallback_engine = candidate_engine
       if results:
           break

   if not results and fallback_results:
       results = fallback_results
       engine = fallback_engine
       quality = "partial"
       warnings.append(
           "Only partial matches were found; some required intent anchors were missing from the results."
       )

   if not results:
       payload = {
           "ok": False,
           "query": query,
           "error": "No relevant search results found",
           "attempts": attempts,
           "diagnostics": _research_diagnostics(query, attempts, []),
       }
       if last_error:
           payload["last_error"] = last_error
       return json.dumps(payload, ensure_ascii=False, indent=2)

   session = get_session()
   enriched = []
   for index, item in enumerate(results[:max_results], start=1):
       enriched_item = dict(item)
       enriched_item["id"] = index
       if index <= max(0, read_top) and item.get("url"):
           try:
               enriched_item["page"] = _read_url_with_session(
                   session,
                   item["url"],
                   max_length=page_content_length,
               )
           except Exception as exc:
               enriched_item["page"] = {"ok": False, "error": str(exc)}
       enriched.append(enriched_item)

   return json.dumps({
       "ok": True,
       "query": query,
       "engine": engine,
       "quality": quality,
       "warnings": warnings,
       "attempts": attempts,
       "diagnostics": _research_diagnostics(query, attempts, results),
       "results": enriched,
   }, ensure_ascii=False, indent=2)


@mcp.tool()
def web_search_status() -> str:
   """Check the current browser, bridge, and provider status.
    
   Detects available CDP browser instances, checks if the
   browser-takeover extension bridge is running, and reports
   the active provider type.
    
   Returns:
       JSON status information
   """
   session = get_session()
   try:
       info = session.detect()
        
       # Bridge check
       bridge = bridge_mod.bridge_status()
       from . import bridge_provider as _bp
       bridge_prov = _bp.create_bridge_search_provider()
       bridge_search_available = bridge_prov is not None
       
       # Provider info
       provider = get_provider_instance()
       provider_type = type(provider).__name__ if provider else "cdp_browser"
       
       # Engine health
       engine_health = get_engine_health()
        
       return json.dumps({
           "cdp": info.get("cdp"),
           "bridge": {
               "available": bridge is not None,
               "search_available": bridge_search_available,
               "status": bridge,
           },
           "provider": {
               "type": provider_type,
               "active": provider is not None,
           },
           "cache": _SEARCH_CACHE.stats if _SEARCH_CACHE is not None else {"enabled": False},
           "engine_health": engine_health,
           "session_ready": session.available,
       }, ensure_ascii=False, indent=2)
   except Exception as exc:
       return json.dumps({"ok": False, "error": f"Status check failed: {exc}"}, ensure_ascii=False)


@mcp.tool()
def web_search_discover_browsers() -> str:
   """Scan for browsers with CDP enabled on common ports.
    
   Checks ports 9222, 9223, 9333 for Chrome/Edge instances
   with remote debugging enabled.
    
   Returns:
       JSON list of discovered browser instances
   """
   cfg = AppConfig.load()
   ports = [cfg.browser.port]
   for port in cdp_mod.DEFAULT_PORTS:
       if port not in ports:
           ports.append(port)
   browsers = cdp_mod.discover_ports(ports=ports)
   if not browsers:
       result = cdp_mod.launch_browser(
           cfg.browser.name,
           port=cfg.browser.port,
           user_data_dir=cfg.browser.user_data_dir,
           headless=True,
           executable_path=cfg.browser.executable_path,
           launch_timeout=cfg.browser.launch_timeout,
       )
       if result.get("launched") and result.get("cdpReady", True):
           browsers = cdp_mod.discover_ports(ports=ports)
   return json.dumps(browsers or [], ensure_ascii=False, indent=2)


# ── Server Runner ────────────────────────────────────────────────────

def run_server() -> None:
   """Start the MCP server with stdin/stdout transport.
    
   Compatible with any MCP client (Codex, Claude Desktop,
   Ollama + mcp-client, etc.).
   """
   sys.stdout.reconfigure(encoding="utf-8")
   sys.stderr.reconfigure(encoding="utf-8")
    
   log.info("Starting browser-search-mcp server...")
    
   # Try to detect existing browser/bridge
   session = get_session()
   try:
       info = session.detect()
       if session.available:
           log.info("Browser detected via CDP on port %d", session._cdp_port)
       if info.get("bridge", {}).get("available"):
           log.info("Browser-takeover extension bridge detected")
   except Exception:
       pass
    
   mcp.run(transport="stdio")


if __name__ == "__main__":
   run_server()
