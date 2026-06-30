# Ready-to-Post Launch Copy

Use these posts during the first launch week. Replace links if needed.

## GitHub Release

Title:

```text
Browser Search MCP Launch Week: real browser search for AI agents
```

Body:

````markdown
Browser Search MCP gives MCP-compatible agents real-browser web search through
Chrome/Edge, page reading, query planning, and result-quality diagnostics.

Highlights:

- `web_search`: search Google, Bing, Baidu, or DuckDuckGo through a browser
- `web_search_plan`: expand vague user requests into better candidate queries
- `web_research`: search, filter, read top pages, and report strict/partial quality
- Optional browser-takeover bridge support for authenticated browser workflows
- HTTP API and OpenAI-compatible function-calling endpoint

Install:

```bash
pip install browser-search-mcp
browser-search-mcp
```

MCP config:

```json
{
  "mcpServers": {
    "browser-search": {
      "command": "browser-search-mcp"
    }
  }
}
```

Try it if you are building local agents, private research assistants, or MCP
workflows that need more than search snippets.
````

## English Short Post

```text
I built Browser Search MCP: real browser search for AI agents.

It lets Claude Desktop, Cursor, Codex, Ollama, and other MCP clients:

- search through Chrome/Edge
- read top result pages
- expand vague user questions
- label result quality as strict/partial
- run without a search API key in browser mode

Best default tool: web_research
Preview query planning: web_search_plan

Repo:
https://github.com/fangsylar-pixel/browser-search
```

## English Long Post

```text
Most local AI agents still have a basic problem: they cannot reliably search
and read the web.

Search APIs are useful, but they are not always available, private, inspectable,
or aligned with real browser workflows.

So I built Browser Search MCP.

It is an MCP server that gives agents real-browser search through Chrome/Edge.
It can search, read result pages, expand vague user requests into better search
queries, and report whether the result matched the expected intent.

Example:

User asks:
"Home projector vs TV: which is better?"

The tool can plan:
- topic: projector, TV
- task: comparison, buying guide, recommendation
- candidate queries:
  - home projector vs TV which is better
  - projector TV comparison pros cons buying guide

Then `web_research` searches, filters off-topic results, reads top pages, and
returns diagnostics.

Install:
pip install browser-search-mcp

Run:
browser-search-mcp

Repo:
https://github.com/fangsylar-pixel/browser-search

I am looking for feedback from MCP users, local LLM users, and agent builders.
```

## Chinese Short Post

```text
我做了一个给 AI Agent 用的真实浏览器搜索 MCP：Browser Search MCP。

它不是单纯调搜索 API，而是让 Claude Desktop、Cursor、Codex、Ollama 这类 MCP 客户端通过 Chrome/Edge 搜索网页。

现在支持：

- 真实浏览器搜索
- 读取搜索结果页面正文
- 自动扩展模糊搜索问题
- 判断结果质量 strict / partial
- 浏览器模式不需要搜索 API Key

安装：
pip install browser-search-mcp

仓库：
https://github.com/fangsylar-pixel/browser-search
```

## Chinese Long Post

```text
本地 AI 和 Agent 有一个很实际的问题：模型本身不能稳定联网搜索。

普通搜索 API 能解决一部分问题，但在本地化、私有化、登录态、页面正文读取、搜索结果可解释性方面，还是不够可控。

所以我做了 Browser Search MCP。

它是一个 MCP Server，可以让支持 MCP 的客户端通过真实 Chrome/Edge 浏览器搜索网页，并读取搜索结果页面正文。

这次重点优化了两个能力：

1. web_search_plan
   先分析用户到底想搜什么，比如平台、领域、任务，再生成候选搜索词。

2. web_research
   搜索、过滤、读取页面，并返回 strict / partial 质量诊断，告诉 Agent 结果是否真的覆盖用户意图。

比如用户问：
"家用投影仪和电视哪个好"

工具会识别成：
- 领域：投影仪、电视
- 任务：对比、选购、推荐
- 搜索词：投影仪 电视 对比 优缺点 选购

这样比直接把原话丢给搜索引擎更适合 Agent 使用。

安装：
pip install browser-search-mcp

启动：
browser-search-mcp

GitHub：
https://github.com/fangsylar-pixel/browser-search

如果你在做本地 Agent、Claude Desktop / Cursor / Codex MCP 工具，欢迎试一下，也欢迎提 issue。
```

## Hacker News / Show HN

```text
Show HN: Browser Search MCP - real browser search for AI agents

I built an MCP server that lets AI agents search the web through a real
Chrome/Edge browser, read top result pages, and return diagnostics about result
quality.

Why:
- Local agents often cannot search the web.
- Search APIs are useful, but not always private, inspectable, or aligned with
  browser-based workflows.
- Agents need page content, not just snippets.

What it does:
- MCP tools for search, multi-engine search, page reading, and research
- query planning for vague user requests
- strict/partial result-quality diagnostics
- optional browser-takeover bridge integration

Repo:
https://github.com/fangsylar-pixel/browser-search
```

## V2EX / 掘金 Title Options

```text
做了一个给 Claude / Cursor / Codex 用的真实浏览器搜索 MCP
```

```text
Browser Search MCP：让本地 AI 通过 Chrome/Edge 搜索并读取网页
```

```text
普通搜索 API 不够可控？我做了一个真实浏览器搜索 MCP
```

## Product Hunt Style

Tagline:

```text
Real browser search and page reading for AI agents
```

Description:

```text
Browser Search MCP gives MCP-compatible agents real Chrome/Edge search, page
reading, natural-language query planning, and result-quality diagnostics without
requiring a search API key in browser mode.
```
