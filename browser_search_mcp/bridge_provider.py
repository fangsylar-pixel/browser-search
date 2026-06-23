import subprocess, json, sys, time
from pathlib import Path

PLUGIN_DIR = str(Path.home() / '.codex' / 'plugins' / 'cache' / 'personal' / 'browser-takeover' / '0.6.0+codex.20260618181149')
SCRIPT = PLUGIN_DIR + '/scripts/browser_takeover_mcp.py'


def bridge_check():
    try:
        import urllib.request as _ur
        r = _ur.urlopen('http://127.0.0.1:17321/bridge/status', timeout=2)
        d = json.loads(r.read())
        clients = d.get('clients', [])
        return bool(clients)
    except:
        return False
class BridgeMCPClient:
    def __init__(self):
        self._proc = None
    def connect(self, timeout=5):
        self._proc = subprocess.Popen([sys.executable, SCRIPT], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=PLUGIN_DIR, text=True, bufsize=1)
        self._send({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"browser-search","version":"0.2.0"}}})
        resp = self._recv(timeout)
        return bool(resp)
    def _send(self, msg):
        self._proc.stdin.write(json.dumps(msg) + chr(10))
        self._proc.stdin.flush()
    def _recv(self, timeout=5):
        start = time.time()
        while time.time() - start < timeout:
            line = self._proc.stdout.readline()
            if not line: time.sleep(0.05); continue
            line = line.strip()
            if not line: continue
            if line.startswith("Content-Length:"):
                n = int(line.split(":")[1])
                self._proc.stdout.readline()
                try: return json.loads(self._proc.stdout.read(n))
                except: continue
            try: return json.loads(line)
            except: continue
        return None
    def call(self, name, args=None, timeout=10):
        self._send({"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":name,"arguments":args or {}}})
        resp = self._recv(timeout)
        if resp and "result" in resp:
            c = resp["result"].get("content",[])
            if c:
                try: return json.loads(c[0].get("text","{}"))
                except: return c[0].get("text","")
        return None
    def close(self):
        if self._proc:
            self._proc.terminate()
            self._proc = None
def create_bridge_provider():
    if not bridge_check(): return None
    c = BridgeMCPClient()
    try:
        c.connect()
        return c
    except:
        return None
class BridgeSearchProvider:
    def __init__(self, client):
        self._client = client
    def search(self, query, engine='bing', max_results=10, **kw):
        import urllib.parse, time, json as _j
        tabs = self._client.call('browser_takeover_extension_list_tabs', {}, 10)
        all_tabs = (tabs or {}).get('tabs', [])
        if not all_tabs: raise RuntimeError('No tabs')
        t = all_tabs[0]
        cid, tid = t.get('clientId',''), t.get('tabId','')
        from .search import SEARCH_ENGINES, EXTRACTORS
        cfg = SEARCH_ENGINES.get(engine, {})
        url = cfg.get('url','').format(query=urllib.parse.quote_plus(query))
        self._client.call('browser_takeover_extension_navigate', {'clientId':cid, 'tabId':tid, 'url':url}, 15)
        time.sleep(2)
        ext = EXTRACTORS.get(engine, '')
        if not ext: return []
        r = self._client.call('browser_takeover_extension_evaluate', {'clientId':cid, 'tabId':tid, 'expression':ext, 'awaitPromise':True}, 10)
        raw = ((r or {}).get('result',{}) or {}).get('value','[]') if r else '[]'
        return _j.loads(raw)[:max_results]

def create_bridge_search_provider():
    c = create_bridge_provider()
    if c: return BridgeSearchProvider(c)
    return None
