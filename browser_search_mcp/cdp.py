"""Chrome DevTools Protocol browser control.

Reuses the same CDP approach as browser-takeover-bridge:
discover browser instances, connect via WebSocket,
navigate pages, evaluate JavaScript, extract content.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


# ── Helpers ──────────────────────────────────────────────────────────

def http_json(url: str, method: str = "GET", body: Any = None, timeout: float = 3) -> Any:
   """Fetch a JSON response from a local HTTP endpoint."""
   req = urllib.request.Request(url, method=method)
   if body is not None:
       data = json.dumps(body).encode("utf-8")
       req.add_header("Content-Type", "application/json")
   else:
       data = None
   try:
       with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
           return json.loads(resp.read().decode("utf-8"))
   except (urllib.error.URLError, json.JSONDecodeError, OSError):
       return None


# ── Browser Discovery ────────────────────────────────────────────────

DEFAULT_PORTS = [9222, 9223, 9333]

BROWSER_CANDIDATES = {
   "chrome": [
       r"Google\Chrome\Application\chrome.exe",
       r"Google\Chrome SxS\Application\chrome.exe",
   ],
   "edge": [
       r"Microsoft\Edge\Application\msedge.exe",
       r"Microsoft\Edge SxS\Application\msedge.exe",
   ],
   "chromium": [],
}


def find_browser_exe(browser: str) -> str | None:
   """Locate a browser executable under LOCALAPPDATA and PROGRAMFILES."""
   local = Path(os.environ.get("LOCALAPPDATA", ""))
   prog = Path(os.environ.get("PROGRAMFILES", ""))
   prog_x86 = Path(os.environ.get("PROGRAMFILES(X86)", ""))
   for suffix in BROWSER_CANDIDATES.get(browser, []):
       for base in (local, prog, prog_x86):
           candidate = base / suffix
           if candidate.exists():
               return str(candidate)
   return None


def cdp_base(host: str = "127.0.0.1", port: int = 9222) -> str:
   return f"http://{host}:{int(port)}"


def cdp_version(host: str = "127.0.0.1", port: int = 9222) -> Any:
   return http_json(f"{cdp_base(host, port)}/json/version")


def cdp_pages(host: str = "127.0.0.1", port: int = 9222) -> list[dict]:
   pages = http_json(f"{cdp_base(host, port)}/json/list") or []
   return pages


def choose_page(host: str, port: int, page_id: str | None = None) -> dict | None:
   """Find a page by id or pick the first available page."""
   pages = cdp_pages(host, port)
   if page_id:
       for p in pages:
           if p.get("id") == page_id:
               return p
   for p in pages:
       if p.get("type") == "page" and p.get("webSocketDebuggerUrl"):
           return p
   return pages[0] if pages else None


def discover_ports(host: str = "127.0.0.1", ports: list[int] | None = None) -> list[dict]:
   """Scan common CDP ports and return reachable browser info.
   
   Uses fast socket connect first, then HTTP for responsive ports only.
   """
   reachable = []
   for port in ports or DEFAULT_PORTS:
       # Fast socket check first
       try:
           import socket as _sk
           _s = _sk.socket(_sk.AF_INET, _sk.SOCK_STREAM)
           _s.settimeout(0.5)
           if _s.connect_ex((host, port)) != 0:
               _s.close()
               continue
           _s.close()
       except:
           continue
       # Port is open, try CDP
       try:
           version = http_json(f"http://{host}:{port}/json/version", timeout=1.5)
           pages = http_json(f"http://{host}:{port}/json/list", timeout=1.5)
           if version:
               reachable.append({
                   "host": host,
                   "port": port,
                   "browser": version.get("Browser", "unknown"),
                   "webSocketDebuggerUrl": version.get("webSocketDebuggerUrl"),
                   "pageCount": len(pages),
               })
       except Exception:
           pass
   return reachable


def launch_browser(
   browser: str = "chrome",
   port: int = 9222,
   user_data_dir: str | None = None,
   headless: bool = False,
   executable_path: str | None = None,
   launch_timeout: int = 15,
) -> dict:
   """Launch a browser with remote debugging enabled."""
   exe = executable_path or find_browser_exe(browser)
   if not exe:
       return {"launched": False, "error": f"{browser} executable not found"}
   if not user_data_dir:
       user_data_dir = str(Path.home() / f".browser-search-mcp/{browser}-profile")
   try:
       os.makedirs(user_data_dir, exist_ok=True)
   except OSError as exc:
       return {
           "launched": False,
           "browser": browser,
           "port": port,
           "userDataDir": user_data_dir,
           "error": f"Could not create browser profile directory: {exc}",
       }
   args = [
       exe,
       f"--remote-debugging-port={port}",
       f"--user-data-dir={user_data_dir}",
       "--no-first-run",
       "--no-default-browser-check",
       "--remote-allow-origins=*",
   ]
   if headless:
       args.append("--headless=new")
       args.append("--disable-gpu")
       args.append("--no-sandbox")
   args.append("about:blank")
   last_error = None
   attempts = max(1, int(launch_timeout * 2))
   for attempt in range(attempts):
       if attempt == 0:
           try:
               subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
           except Exception as exc:
               return {"launched": False, "error": str(exc)}
       time.sleep(0.5)
       try:
           version = cdp_version("127.0.0.1", port)
           if version:
               return {
                   "launched": True,
                   "browser": browser,
                   "port": port,
                   "userDataDir": user_data_dir,
                   "version": version,
               }
       except Exception as exc:
           last_error = str(exc)
   return {
       "launched": True,
       "browser": browser,
       "port": port,
       "userDataDir": user_data_dir,
       "cdpReady": False,
       "error": last_error,
   }


# ── WebSocket CDP Communication ──────────────────────────────────────

class CdpWebSocket:
   """WebSocket client for CDP using the websockets library."""

   def __init__(self, ws_url: str):
       import asyncio
       self._ws_url = ws_url
       self._lock = threading.Lock()
       self._loop = asyncio.new_event_loop()
       self._ws = self._loop.run_until_complete(self._connect())

   async def _connect(self):
       import websockets
       return await websockets.connect(self._ws_url, max_size=2**20, close_timeout=10)

   def _run(self, coro):
       return self._loop.run_until_complete(coro)

   def call(self, method: str, params=None):
       import asyncio, json, websockets
       cmd_id = id(method)
       payload = json.dumps({"id": cmd_id, "method": method, "params": params or {}})
       with self._lock:
           try:
               self._run(self._ws.send(payload))
               while True:
                   msg = self._run(asyncio.wait_for(self._ws.recv(), timeout=30))
                   try:
                       obj = json.loads(msg)
                   except (json.JSONDecodeError, UnicodeDecodeError):
                       continue
                   if obj.get("id") == cmd_id:
                       if "error" in obj:
                           raise RuntimeError(obj["error"].get("message", str(obj["error"])))
                       return obj.get("result")
           except asyncio.TimeoutError:
               raise RuntimeError("timed out")
           except websockets.ConnectionClosed as e:
               raise RuntimeError("WebSocket closed: " + str(e))

   def close(self):
       try:
           if self._ws:
               self._run(self._ws.close())
           self._loop.close()
       except Exception:
           pass

def cdp_call(
   host: str, port: int, method: str, params: dict | None = None, page_id: str | None = None
) -> dict:
   """Execute a CDP method on the first/selected page using websockets."""
   import asyncio, json, websockets
   page = choose_page(host, port, page_id)
   if not page:
       raise RuntimeError(f"No CDP-accessible page found on {host}:{port}")
   ws_url = page["webSocketDebuggerUrl"]
   result_data = _cdp_call_via_ws(ws_url, method, params or {})
   return {
       "page": {"id": page.get("id"), "title": page.get("title"), "url": page.get("url")},
       "result": result_data,
   }


_CDP_CMD_COUNTER = [1000]  # mutable list for counter


def _cdp_call_via_ws(ws_url: str, method: str, params: dict) -> dict:
   """Single CDP call via fresh websocket, isolated in its own thread."""
   import asyncio, json, websockets, threading

   _result = None
   _error = None

   def _run_in_thread():
       nonlocal _result, _error
       _loop = asyncio.new_event_loop()
       asyncio.set_event_loop(_loop)
       try:
           _result = _loop.run_until_complete(_do_call())
       except Exception as e:
           _error = e
       finally:
           _loop.close()

   async def _do_call():
       async with websockets.connect(ws_url, max_size=2**20, close_timeout=5) as ws:
           _CDP_CMD_COUNTER[0] += 1
           cmd_id = _CDP_CMD_COUNTER[0]
           await ws.send(json.dumps({"id": cmd_id, "method": method, "params": params}))
           while True:
               msg = await asyncio.wait_for(ws.recv(), timeout=30)
               try:
                   obj = json.loads(msg)
               except (json.JSONDecodeError, UnicodeDecodeError):
                   continue
               if obj.get("id") == cmd_id:
                   if "error" in obj:
                       raise RuntimeError(obj["error"].get("message", str(obj["error"])))
                   return obj.get("result")

   t = threading.Thread(target=_run_in_thread)
   t.start()
   t.join()
   if _error:
       raise _error
   return _result


def navigate(host: str, port: int, url: str, page_id: str | None = None) -> dict:
   """Navigate a page to a URL."""
   return cdp_call(host, port, "Page.navigate", {"url": url}, page_id)


def evaluate_js(
   host: str, port: int, expression: str, page_id: str | None = None, await_promise: bool = True
) -> Any:
   """Evaluate JavaScript in a page and return the result."""
   result = cdp_call(
       host,
       port,
       "Runtime.evaluate",
       {"expression": expression, "awaitPromise": await_promise, "returnByValue": True},
       page_id,
   )
   return result


def get_page_text(host: str, port: int, page_id: str | None = None) -> str:
   """Extract visible text from a page."""
   result = evaluate_js(
       host, port, "document.body?.innerText || ''", page_id, await_promise=False
   )
   return (result.get("result") or {}).get("result", {}).get("value", "")


def get_page_html(host: str, port: int, page_id: str | None = None) -> str:
   """Extract the full HTML from a page."""
   result = evaluate_js(
       host, port, "document.documentElement?.outerHTML || ''", page_id, await_promise=False
   )
   return (result.get("result") or {}).get("result", {}).get("value", "")


# ── Persistent CDP Session ────────────────────────────────────────────

class CdpSession:
    """Persistent CDP connection to a single page.
    
    Keeps the WebSocket open across multiple operations,
    reducing overhead. Reconnects automatically.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 9222, page_id: str | None = None, timeout: int = 30):
        self._host = host
        self._port = port
        self._page_id = page_id
        self._timeout = timeout
        self._ws = None
        self._loop = None
        self._page_info = None

    def connect(self):
        import asyncio
        page = choose_page(self._host, self._port, self._page_id)
        if not page:
            raise RuntimeError(f"No CDP page found on {self._host}:{self._port}")
        self._page_info = page
        self._page_id = page.get("id")
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._ws = self._loop.run_until_complete(self._connect_ws(page["webSocketDebuggerUrl"]))
        return self._page_info

    async def _connect_ws(self, ws_url):
        import websockets
        return await websockets.connect(ws_url, max_size=2**20, close_timeout=10)

    def _reconnect(self):
        try:
            self.close()
        except Exception:
            pass
        self.connect()

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def call(self, method: str, params: dict | None = None) -> dict:
        import asyncio, json, websockets
        # Check if connection is alive
        if self._ws is None:
            self._reconnect()
        else:
            try:
                state = self._ws.state
                if state == websockets.protocol.State.CLOSED or state == websockets.protocol.State.CLOSING:
                    self._reconnect()
            except Exception:
                self._reconnect()
        _CDP_CMD_COUNTER[0] += 1
        cmd_id = _CDP_CMD_COUNTER[0]
        try:
            self._run(self._ws.send(json.dumps({"id": cmd_id, "method": method, "params": params or {}})))
            while True:
                msg = self._run(asyncio.wait_for(self._ws.recv(), timeout=self._timeout))
                try:
                    obj = json.loads(msg)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if obj.get("id") == cmd_id:
                    if "error" in obj:
                        raise RuntimeError(obj["error"].get("message", str(obj["error"])))
                    return obj.get("result")
        except asyncio.TimeoutError:
            raise RuntimeError("timed out")
        except websockets.ConnectionClosed:
            self._ws = None
            raise RuntimeError("WebSocket closed, will reconnect")

    def navigate(self, url: str) -> dict:
        return self.call("Page.navigate", {"url": url})

    def evaluate(self, expression: str, await_promise: bool = True) -> Any:
        return self.call("Runtime.evaluate", {
            "expression": expression, "awaitPromise": await_promise, "returnByValue": True,
        })

    def get_text(self) -> str:
        result = self.evaluate("document.body?.innerText || ''", await_promise=False)
        r = result or {}
        r2 = r.get("result") or {}
        return r2.get("value") or ""

    def close(self):
        try:
            if self._ws:
                self._run(self._ws.close())
        except Exception:
            pass
        try:
            if self._loop:
                self._loop.close()
        except Exception:
            pass
        self._ws = None
        self._loop = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()
