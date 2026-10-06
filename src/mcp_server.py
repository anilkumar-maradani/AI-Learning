"""
mcp_server.py — The smallest MCP server that is still the real protocol.

MCP over stdio is JSON-RPC 2.0, one message per line: the host writes requests
to the server's stdin and reads responses from its stdout. This module is the
server half for PolicyLens' own servers (mcp_servers/policy_docs, the Week 9
gateway). It answers four methods and one notification:

  initialize                  version + capability handshake
  notifications/initialized   the client says it is ready (no reply)
  tools/list                  every tool: name, description, inputSchema
  tools/call                  run one tool, return content blocks
  resources/list, resources/read   app-attached context (not model-invoked)

A tool's description IS its docstring. That is deliberate: the docstring is
the only thing the model reads before deciding whether and how to call the
tool, so it is written as a prompt, not as a code comment.

Two kinds of failure, kept apart on purpose:
  * ToolError  -> a normal result with isError: true. The model sees the
                  message and can fix its call. Write these for the model.
  * protocol errors (unknown method / tool, bad params) -> a JSON-RPC error.
                  The host sees these; the model normally does not.

No model is called anywhere in a server. The server exposes a capability; the
host runs the model.
"""

import inspect
import json
import sys
import traceback

PROTOCOL_VERSION = "2025-06-18"

# JSON-RPC error codes
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = (
    -32700, -32600, -32601, -32602, -32603)


class ToolError(Exception):
    """Raise inside a tool for a failure the MODEL should read and recover from."""


class Server:
    def __init__(self, name: str, version: str, instructions: str = ""):
        self.name, self.version, self.instructions = name, version, instructions
        self._tools: dict[str, dict] = {}
        self._resources: dict[str, dict] = {}
        # The protocol owns stdout. Anything else that prints (model loading,
        # index building) would corrupt the stream, so ordinary prints go to
        # stderr from here on and the protocol writes to the saved handle.
        # UTF-8 both ways, or a Windows code page breaks on the first "—".
        for stream in (sys.stdin, sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        self._out = sys.stdout
        sys.stdout = sys.stderr

    # -- registration -------------------------------------------------------

    def tool(self, input_schema: dict):
        """Register fn as a tool. Its docstring becomes the tool description."""
        def wrap(fn):
            self._tools[fn.__name__] = {
                "fn": fn,
                "spec": {
                    "name": fn.__name__,
                    "description": inspect.cleandoc(fn.__doc__ or ""),
                    "inputSchema": input_schema,
                },
            }
            return fn
        return wrap

    def add_tool(self, spec: dict, fn):
        """Register a tool whose spec came from elsewhere (the gateway re-exports
        downstream tools/list entries verbatim)."""
        self._tools[spec["name"]] = {"fn": fn, "spec": spec}

    def resource(self, uri: str, name: str, description: str, mime_type: str = "text/plain"):
        def wrap(fn):
            self._resources[uri] = {
                "fn": fn,
                "spec": {"uri": uri, "name": name, "description": description,
                         "mimeType": mime_type},
            }
            return fn
        return wrap

    # -- method handlers ----------------------------------------------------

    def _initialize(self, params: dict) -> dict:
        caps = {"tools": {"listChanged": False}}
        if self._resources:
            caps["resources"] = {"subscribe": False, "listChanged": False}
        out = {
            "protocolVersion": params.get("protocolVersion", PROTOCOL_VERSION),
            "capabilities": caps,
            "serverInfo": {"name": self.name, "version": self.version},
        }
        if self.instructions:
            out["instructions"] = self.instructions
        return out

    def _tools_list(self, _params: dict) -> dict:
        return {"tools": [t["spec"] for t in self._tools.values()]}

    def _tools_call(self, params: dict) -> dict:
        name = params.get("name")
        if name not in self._tools:
            raise _RpcError(INVALID_PARAMS, f"Unknown tool: {name}")
        args = params.get("arguments") or {}
        try:
            out = self._tools[name]["fn"](**args)
        except ToolError as exc:
            return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
        except TypeError as exc:
            return {"content": [{"type": "text", "text": f"bad arguments: {exc}"}], "isError": True}
        text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        return {"content": [{"type": "text", "text": text}], "isError": False}

    def _resources_list(self, _params: dict) -> dict:
        return {"resources": [r["spec"] for r in self._resources.values()]}

    def _resources_read(self, params: dict) -> dict:
        uri = params.get("uri")
        if uri not in self._resources:
            raise _RpcError(INVALID_PARAMS, f"Unknown resource: {uri}")
        r = self._resources[uri]
        return {"contents": [{"uri": uri, "mimeType": r["spec"]["mimeType"], "text": r["fn"]()}]}

    # -- loop ---------------------------------------------------------------

    def _send(self, msg: dict):
        self._out.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self._out.flush()

    def run(self):
        handlers = {
            "initialize": self._initialize,
            "ping": lambda _p: {},
            "tools/list": self._tools_list,
            "tools/call": self._tools_call,
            "resources/list": self._resources_list,
            "resources/read": self._resources_read,
        }
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as exc:
                self._send({"jsonrpc": "2.0", "id": None,
                            "error": {"code": PARSE_ERROR, "message": str(exc)}})
                continue
            if "id" not in msg:          # a notification: never answered
                continue
            method = msg.get("method")
            try:
                if method not in handlers:
                    raise _RpcError(METHOD_NOT_FOUND, f"Method not found: {method}")
                result = handlers[method](msg.get("params") or {})
                self._send({"jsonrpc": "2.0", "id": msg["id"], "result": result})
            except _RpcError as exc:
                self._send({"jsonrpc": "2.0", "id": msg["id"],
                            "error": {"code": exc.code, "message": exc.message}})
            except Exception as exc:  # a server bug, not a bad call
                traceback.print_exc(file=sys.stderr)
                self._send({"jsonrpc": "2.0", "id": msg["id"],
                            "error": {"code": INTERNAL_ERROR, "message": f"{type(exc).__name__}: {exc}"}})


class _RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code, self.message = code, message
