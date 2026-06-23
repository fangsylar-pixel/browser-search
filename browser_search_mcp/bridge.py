"""Browser-takeover bridge client.

Detects and communicates with the running browser-takeover-bridge
on 127.0.0.1:17321 to discover browser instances and leverage
the installed extension for authenticated browsing.
"""

from __future__ import annotations

import urllib.error
import urllib.parse
import urllib.request


BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 17321


def bridge_status() -> dict | None:
    """Check if the browser-takeover bridge is running and healthy."""
    try:
        req = urllib.request.Request(
            f"http://{BRIDGE_HOST}:{BRIDGE_PORT}/bridge/status",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            import json
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def bridge_browser_info() -> dict | None:
    """Get browser info from the running bridge, if available.
    
    Returns the bridge status which includes client browser info
    and tab counts.
    """
    return bridge_status()


def is_bridge_alive() -> bool:
    """Quick check if the bridge is running and has connected clients."""
    status = bridge_status()
    if not status:
        return False
    clients = status.get("clients") or []
    return len(clients) > 0 and any(
        client.get("health", {}).get("polling") for client in clients
    )
