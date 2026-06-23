
# HTTP API + OpenAI-compatible Function Calling server.
# Run: python -m browser_search_mcp http
import json, sys
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="Browser Search MCP API")


class SearchRequest(BaseModel):
    query: str
    engine: str = "bing"
    max_results: int = 5
    page: int = 1
    time_range: str = ""
    deep_mode: bool = False


class ChatRequest(BaseModel):
    model: str = "gpt-3.5-turbo"
    messages: list = []
    tools: list = []


@app.get("/health")
async def health():
    return {"status": "ok", "service": "browser-search-mcp"}


@app.post("/search")
async def search(req: SearchRequest):
    from .server import web_search
    result = web_search(
        query=req.query,
        engine=req.engine,
        max_results=req.max_results,
        headless=True,
        page=req.page,
        time_range=req.time_range,
        deep_mode=req.deep_mode,
    )
    return json.loads(result)


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    from .server import web_search, web_search_multi, web_search_read_page, web_search_status
    
    tool_map = {
        "web_search": web_search,
        "web_search_multi": web_search_multi,
        "web_search_read_page": web_search_read_page,
        "web_search_status": web_search_status,
    }
    
    last_message = req.messages[-1]["content"] if req.messages else ""
    tool_calls = []
    
    for tool_def in req.tools:
        func = tool_def.get("function", {})
        name = func.get("name", "")
        if name in tool_map:
            try:
                args = json.loads(func.get("parameters", "{}"))
                if name == "web_search":
                    result = tool_map[name](
                        query=args.get("query", last_message),
                        engine=args.get("engine", "bing"),
                        max_results=args.get("max_results", 5),
                    )
                elif name == "web_search_multi":
                    result = tool_map[name](
                        query=args.get("query", last_message),
                        engines=args.get("engines", "google,bing"),
                        max_results_per_engine=args.get("max_results_per_engine", 3),
                    )
                elif name == "web_search_status":
                    result = tool_map[name]()
                else:
                    result = json.dumps({"error": "not implemented"})
                
                tool_calls.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": name,
                })
            except Exception as e:
                tool_calls.append({
                    "role": "tool",
                    "content": json.dumps({"error": str(e)}),
                    "tool_call_id": name,
                })
    
    if tool_calls:
        return {"choices": [{"message": {"role": "assistant", "content": json.dumps([json.loads(tc["content"]) for tc in tool_calls])}}]}
    
    return {"choices": [{"message": {"role": "assistant", "content": "No tools matched your request."}}]}


def run():
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 9090
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
