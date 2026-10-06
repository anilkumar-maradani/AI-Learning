"""
mcp_client.py — The host side of MCP: start servers from config, discover
their tools, call them. Nothing in here knows any tool by name.

Config (mcp_config.json, the same shape other MCP hosts use):

    {"mcpServers": {
        "policy_docs": {"command": "${python}", "args": ["mcp_servers/policy_docs/server.py"],
                        "env": {...}, "attach_resources": ["policy://exclusion-schedule"]}
    }}

  ${python}     the interpreter running the host, so a server inherits the venv
  ${NAME}       any other ${...} is read from the environment (.env included),
                so tokens stay out of the config file
  env           the ONLY variables a server gets beyond the OS basics; it
                never inherits the host's environment (GROQ_API_KEY stays here)
  attach_resources  resources the APP reads and puts in front of the model.
                Resources are context the app attaches; tools are what the model
                chooses to call. The exclusion schedule is the former.

Per server, the lifecycle is the spec's:
    initialize -> notifications/initialized -> tools/list -> tools/call ...

Tools are exposed to the model as "<server>__<tool>", so every step in a trace
says which server it went to, and two servers may both have a tool called
"search" without colliding.

Pass a list as ``wire`` to record every raw JSON-RPC message in both
directions; Week 9's wire.json is captured this way.
"""

import json
import os
import queue
import re
import subprocess
import sys
import threading

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "policylens-host", "version": "0.9.0"}
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_CONFIG = os.path.join(ROOT, "mcp_config.json")
SEP = "__"

_VAR_RE = re.compile(r"\$\{([^}]+)\}")
_BASE_ENV = {"PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP",
             "HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "APPDATA", "LOCALAPPDATA",
             "LANG", "HF_HOME"}


class MCPError(Exception):
    """A JSON-RPC error response: a protocol failure, not a tool result."""


def _expand(value: str) -> str:
    return _VAR_RE.sub(
        lambda m: sys.executable if m.group(1) == "python" else os.environ.get(m.group(1), ""),
        value)


def load_config(path: str = DEFAULT_CONFIG) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["mcpServers"]


class MCPServer:
    """One stdio connection to one MCP server."""

    def __init__(self, name: str, spec: dict, wire: list | None = None, timeout_s: float = 180.0):
        self.name, self.spec, self.wire, self.timeout_s = name, spec, wire, timeout_s
        self._next_id = 0
        self._inbox: queue.Queue = queue.Queue()
        self.server_info: dict = {}
        self.tools: list[dict] = []

    # -- transport ----------------------------------------------------------

    def start(self):
        # A server gets the OS basics plus what its config entry declares, never
        # the host's whole environment: GROQ_API_KEY and other servers' tokens
        # stay out of a third-party process.
        env = {k: v for k, v in os.environ.items() if k.upper() in _BASE_ENV}
        env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        env.update({k: _expand(v) for k, v in (self.spec.get("env") or {}).items()})
        cmd = [_expand(self.spec["command"])] + [_expand(a) for a in self.spec.get("args", [])]
        self._proc = subprocess.Popen(
            cmd, cwd=_expand(self.spec.get("cwd", ROOT)), env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=sys.stderr)
        threading.Thread(target=self._read_loop, daemon=True).start()
        return self

    def _read_loop(self):
        for raw in self._proc.stdout:
            line = raw.decode("utf-8").strip()
            if line:
                self._inbox.put(json.loads(line))
        self._inbox.put(None)  # server exited

    def _log(self, direction: str, msg: dict):
        if self.wire is not None:
            self.wire.append({"server": self.name, "direction": direction, "message": msg})

    def _write(self, msg: dict):
        self._log("client->server", msg)
        self._proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        self._proc.stdin.flush()

    def request(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        rid = self._next_id
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)
        while True:
            try:
                reply = self._inbox.get(timeout=self.timeout_s)
            except queue.Empty:
                raise MCPError(f"{self.name}: no reply to {method} in {self.timeout_s:.0f}s")
            if reply is None:
                raise MCPError(f"{self.name}: server exited during {method}")
            self._log("server->client", reply)
            if reply.get("id") != rid:      # a server notification; not ours
                continue
            if "error" in reply:
                raise MCPError(f"{self.name}: {reply['error'].get('message')} "
                               f"(code {reply['error'].get('code')})")
            return reply["result"]

    def notify(self, method: str, params: dict | None = None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._write(msg)

    # -- protocol -----------------------------------------------------------

    def initialize(self) -> dict:
        res = self.request("initialize", {"protocolVersion": PROTOCOL_VERSION,
                                          "capabilities": {}, "clientInfo": CLIENT_INFO})
        self.server_info = res
        self.notify("notifications/initialized")
        return res

    def list_tools(self) -> list[dict]:
        tools, cursor = [], None
        while True:
            res = self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools += res.get("tools", [])
            cursor = res.get("nextCursor")
            if not cursor:
                break
        self.tools = tools
        return tools

    def call_tool(self, name: str, arguments: dict) -> dict:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def read_resource(self, uri: str) -> str:
        res = self.request("resources/read", {"uri": uri})
        return "\n".join(c.get("text", "") for c in res.get("contents", []))

    def close(self):
        try:
            self._proc.stdin.close()
            self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()


def result_text(result: dict) -> str:
    return "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")


class ToolRegistry:
    """Every tool every configured server reported in tools/list, keyed '<server>__<tool>'."""

    def __init__(self, servers: dict[str, MCPServer]):
        self.servers = servers
        self.routes: dict[str, tuple[MCPServer, dict]] = {}
        for srv in servers.values():
            for t in srv.tools:
                self.routes[f"{srv.name}{SEP}{t['name']}"] = (srv, t)

    @classmethod
    def from_config(cls, path: str = DEFAULT_CONFIG, wire: list | None = None) -> "ToolRegistry":
        servers = {}
        for name, spec in load_config(path).items():
            srv = MCPServer(name, spec, wire=wire).start()
            srv.initialize()
            srv.list_tools()
            servers[name] = srv
        return cls(servers)

    def names(self) -> list[str]:
        return list(self.routes)

    def openai_tools(self) -> list[dict]:
        """tools/list entries as chat-completions function tools, unchanged in meaning."""
        return [{"type": "function",
                 "function": {"name": full, "description": t.get("description", ""),
                              "parameters": t.get("inputSchema") or {"type": "object", "properties": {}}}}
                for full, (_srv, t) in self.routes.items()]

    def attached_context(self) -> list[tuple[str, str, str]]:
        """(server, uri, text) for every resource the config says the app attaches."""
        out = []
        for srv in self.servers.values():
            for uri in srv.spec.get("attach_resources", []):
                out.append((srv.name, uri, srv.read_resource(uri)))
        return out

    def call(self, full_name: str, arguments: str | dict) -> dict:
        """Returns {server, tool, is_error, text}. Never raises for a model mistake."""
        if full_name not in self.routes:
            return {"server": None, "tool": full_name, "is_error": True,
                    "text": f"unknown tool {full_name!r}; available: {', '.join(self.routes)}"}
        srv, t = self.routes[full_name]
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
        except json.JSONDecodeError as exc:
            return {"server": srv.name, "tool": t["name"], "is_error": True,
                    "text": f"arguments are not valid JSON: {exc}"}
        try:
            res = srv.call_tool(t["name"], args)
        except MCPError as exc:
            return {"server": srv.name, "tool": t["name"], "is_error": True, "text": str(exc)}
        return {"server": srv.name, "tool": t["name"], "is_error": bool(res.get("isError")),
                "text": result_text(res)}

    def close(self):
        for srv in self.servers.values():
            srv.close()
