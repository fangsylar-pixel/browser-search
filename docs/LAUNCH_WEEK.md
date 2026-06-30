# Browser Search MCP Launch Week

This is the first-week launch plan for Browser Search MCP. The goal is not to
claim "another AI search tool"; the goal is to show a concrete agent workflow:
search with a real browser, read pages, expand unclear user requests, and return
diagnostics that help the caller trust or reject the result.

## Positioning

**One-line pitch**

Browser Search MCP gives AI agents real-browser web search, page reading, query
planning, and result-quality diagnostics without requiring a search API key.

**Short tagline**

Search like a real browser. Read like a research agent.

**Chinese tagline**

让本地 AI 像真人一样搜索、打开网页、读取正文，并判断结果是否靠谱。

## Audience

| Audience | Pain | Message |
|----------|------|---------|
| Local LLM users | The model cannot search the web | Add browser search to Ollama, Claude Desktop, Cursor, or Codex |
| Agent builders | Search results are noisy and hard to trust | Get query planning, page reading, and diagnostics in one MCP tool |
| Private/enterprise workflows | External search APIs are not always acceptable | Run search locally through a real browser |
| Research automation builders | Search snippets are not enough | Read top pages and return cleaned content for citations |
| Browser automation users | They already rely on browser sessions | Use browser-takeover bridge for authenticated workflows |

## Core Claims

Use these claims consistently:

- Real browser search through Chrome/Edge, not only HTTP scraping.
- No search API key required in browser mode.
- MCP-native tools for Claude Desktop, Cursor, Codex, Ollama, and local agents.
- `web_search_plan` expands vague user questions into better search queries.
- `web_research` searches, filters, reads pages, and reports result quality.
- Bridge mode can reuse browser-takeover sessions for authenticated contexts.

Avoid these claims unless benchmarked:

- "Best search tool"
- "Never blocked"
- "Always accurate"
- "Better than official search"

## Demo Scenarios

Use these three examples in launch posts, screenshots, or short videos.

### 1. Creator research

Prompt:

```text
What topics should I write about for gaming on Toutiao?
```

What to show:

- `web_search_plan` extracts platform/topic/task.
- Candidate queries include platform + topic + content angles.
- `web_research` returns strict or partial quality with diagnostics.

### 2. Shopping comparison

Prompt:

```text
Home projector vs TV: which is better?
```

What to show:

- The tool identifies comparison/buying-guide intent.
- It searches for buying-guide style pages instead of only keyword matching.
- It reads top pages for a grounded answer.

### 3. Study plan

Prompt:

```text
How should I study English for the 2026 exam?
```

What to show:

- The tool keeps the time anchor.
- Candidate queries include study plan, preparation, methods, and resources.
- Returned page content is clean enough for an agent to summarize.

## First-Week Calendar

### Day 1: GitHub polish

- Update README top section with positioning, examples, and comparison table.
- Add `docs/LAUNCH_WEEK.md` and `docs/LAUNCH_POSTS.md`.
- Add GitHub topics:
  - `mcp`
  - `model-context-protocol`
  - `web-search`
  - `ai-agent`
  - `browser-automation`
  - `local-llm`
- Create a GitHub release named `v0.2.0` or `Launch Week`.

Success metric:

- README explains the project in under 30 seconds.

### Day 2: Demo asset

- Record a 30-60 second terminal demo.
- Show install, MCP config, `web_search_plan`, and `web_research`.
- Use the shopping comparison example because it is easy to understand.

Success metric:

- A viewer can understand the tool without reading docs.

### Day 3: English developer launch

Post to:

- GitHub discussions or relevant MCP communities.
- Hacker News "Show HN" if the demo is ready.
- Reddit communities focused on local LLMs, AI agents, and MCP.

Success metric:

- 5-10 comments or questions from developers.

### Day 4: Chinese developer launch

Post to:

- V2EX
- 掘金
- 知乎
- 即刻

Success metric:

- 10+ GitHub clicks from Chinese channels.

### Day 5: Comparison post

Publish:

```text
Browser Search MCP vs search APIs: when a real browser matters
```

Main points:

- Local/private workflows.
- Authenticated browser context.
- Full page reading.
- Diagnostics over opaque snippets.

Success metric:

- At least one user asks about integrating it into their agent stack.

### Day 6: User feedback loop

- Turn repeated questions into FAQ entries.
- Convert bugs into GitHub issues.
- Add one integration guide if a user asks for it.

Success metric:

- 3+ actionable issues or integration requests.

### Day 7: Follow-up release note

Publish a short update:

- What changed during launch week.
- What feedback came in.
- What is next: benchmark set, UI/demo, more integrations.

Success metric:

- Maintains momentum after the first post spike.

## Metrics

Track these numbers daily:

- GitHub stars
- GitHub clones
- PyPI downloads
- README views if available
- Issues opened
- Integration questions
- Demo video views
- Community comments

## Risk Controls

- Be clear that browser mode depends on the local browser environment.
- Do not claim guaranteed anti-bot bypass.
- Do not position the project as replacing official search in every use case.
- Emphasize control, inspectability, and agent workflows.

## Call To Action

Primary:

```text
Try it with your MCP client:
pip install browser-search-mcp
```

Secondary:

```text
Star the repo if you want more local-agent search tooling.
```

Tertiary:

```text
Open an issue with the agent/client you want supported next.
```
