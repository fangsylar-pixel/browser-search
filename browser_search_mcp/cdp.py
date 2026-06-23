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
    """Scan common CDP ports and return reachable browser info."""
    reachable = []
    for port in ports or DEFAULT_PORTS:
        try:
            version = cdp_version(host, port)
            pages = cdp_pages(host, port)
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
) -> dict:
    """Launch a browser with remote debugging enabled."""
    exe = find_browser_exe(browser)
    if not exe:
        return {"launched": False, "error": f"{browser} executable not found"}
    if not user_data_dir:
        user_data_dir = str(Path.home() / f".browser-search-mcp/{browser}-profile")
    os.makedirs(user_data_dir, exist_ok=True)
    args = [
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        args.append("--headless=new")
    last_error = None
    for attempt in range(15):
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
    """Minimal WebSocket client for Chrome DevTools Protocol."""

    def __init__(self, ws_url: str):
        parsed = urllib.parse.urlparse(ws_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 9222
        path = parsed.path or "/"
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        sock = socket.create_connection((host, port), timeout=10)
        sock.sendall(
            (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            ).encode("ascii")
        )
        resp = sock.recv(4096)
        lines = resp.split(b"\r\n")
        if b" 101 " not in lines[0]:
            sock.close()
            raise RuntimeError(f"WebSocket handshake failed: {lines[0].decode()}")
        accept_line = next((l for l in lines if l.startswith(b"Sec-WebSocket-Accept:")), None)
        if accept_line:
            expected = base64.b64encode(
                hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
            )
            if expected not in accept_line:
                sock.close()
                raise RuntimeError("WebSocket accept header mismatch")
        self._sock = sock
        self._buf = b""
        self._lock = threading.Lock()

    def _read_frame(self) -> bytes:
        while True:
            first = self._sock.recv(1)
            if not first:
                raise RuntimeError("WebSocket closed")
            opcode = first[0] & 0x0F
            if opcode == 8:
                raise RuntimeError("WebSocket closed by browser")
            if opcode == 9:
                self._sock.sendall(b"\x8a\x00")
                continue
            if opcode not in (1, 2):
                continue
            second = self._sock.recv(1)
            masked = (second[0] & 0x80) != 0
            length = second[0] & 0x7F
            if length == 126:
                length = int.from_bytes(self._sock.recv(2), "big")
            elif length == 127:
                length = int.from_bytes(self._sock.recv(8), "big")
            if masked:
                mask = self._sock.recv(4)
                data = self._sock.recv(length)
                return bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            return self._sock.recv(length)

    def call(self, method: str, params: dict | None = None) -> Any:
        """Send a CDP command and wait for the result."""
        cmd_id = id(method)
        payload = json.dumps({"id": cmd_id, "method": method, "params": params or {}})
        with self._lock:
            frame = bytearray()
            frame.append(0x81)
            data = payload.encode("utf-8")
            if len(data) < 126:
                frame.append(len(data))
            elif len(data) < 65536:
                frame.append(126)
                frame.extend(len(data).to_bytes(2, "big"))
            else:
                frame.append(127)
                frame.extend(len(data).to_bytes(8, "big"))
            frame.extend(data)
            self._sock.sendall(bytes(frame))
            while True:
                msg = self._read_frame()
                try:
                    obj = json.loads(msg.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if obj.get("id") == cmd_id:
                    if "error" in obj:
                        raise RuntimeError(obj["error"].get("message", str(obj["error"])))
                    return obj.get("result")

    def close(self) -> None:
        try:
            self._sock.close()
        except Exception:
            pass


# ── High-level CDP Operations ────────────────────────────────────────

def cdp_call(
    host: str, port: int, method: str, params: dict | None = None, page_id: str | None = None
) -> dict:
    """Execute a CDP method on the first/selected page."""
    page = choose_page(host, port, page_id)
    if not page:
        raise RuntimeError(f"No CDP-accessible page found on {host}:{port}")
    ws = CdpWebSocket(page["webSocketDebuggerUrl"])
    try:
        result_data = ws.call(method, params or {})
        return {
            "page": {"id": page.get("id"), "title": page.get("title"), "url": page.get("url")},
            "result": result_data,
        }
    finally:
        ws.close()


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
