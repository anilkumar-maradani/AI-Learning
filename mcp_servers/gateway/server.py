"""
gateway — One MCP front door for every PolicyLens tool server (Week 9 bonus).

The agent connects to this one server. At start-up the gateway connects to the
downstream servers in gateway_config.json (same shape as mcp_config.json, via
src/mcp_client.py), re-exports every tool as "<server>__<tool>", and routes each
tools/call to the server that owns it.

Every tools/call, allowed or denied, is written as ONE line of JSON to
$GATEWAY_AUDIT_LOG (default logs/gateway_audit.jsonl):
    {"ts", "caller", "tool", "claim_number", "outcome"}

Caller identity and scope come from GATEWAY_TOKEN. The config stores only the
token's SHA-256, never the token. A denied call returns a normal tool result
with isError: true and a message the model can act on, so the model can still
answer from what it is allowed to see. Downstream secrets (CLAIMS_API_TOKEN)
are the gateway's own (read from .env here, a secret store in production); the
agent's config passes only GATEWAY_TOKEN.
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

from mcp_client import ToolRegistry  # noqa: E402
from mcp_server import Server, ToolError  # noqa: E402

CONFIG = os.environ.get("GATEWAY_CONFIG", os.path.join(HERE, "gateway_config.json"))
AUDIT_LOG = os.environ.get("GATEWAY_AUDIT_LOG", os.path.join(ROOT, "logs", "gateway_audit.jsonl"))
CLAIM_RE = re.compile(r"CLM-\d{4}-\d{5}", re.IGNORECASE)

server = Server("policylens-gateway", "0.9.0")


def _caller() -> dict:
    with open(CONFIG, encoding="utf-8") as fh:
        scopes = json.load(fh).get("tokens", {})
    token = os.environ.get("GATEWAY_TOKEN", "")
    digest = hashlib.sha256(token.encode()).hexdigest()
    return scopes.get(digest) or {"caller": "unknown", "allow": []}


def _audit(caller: str, tool: str, arguments: dict, outcome: str):
    m = CLAIM_RE.search(json.dumps(arguments))
    line = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "caller": caller,
            "tool": tool, "claim_number": m.group(0).upper() if m else None, "outcome": outcome}
    os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
    with open(AUDIT_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")


def _allowed(scope: dict, tool: str) -> bool:
    allow, deny = scope.get("allow", []), scope.get("deny", [])
    return tool not in deny and ("*" in allow or tool in allow)


def _route(registry: ToolRegistry, scope: dict, full_name: str):
    def call(**arguments):
        if not _allowed(scope, full_name):
            _audit(scope["caller"], full_name, arguments, "denied")
            raise ToolError(
                f"permission denied: caller '{scope['caller']}' is not scoped for {full_name}. "
                f"This is a permission decision, not an outage or a bad argument, so retrying "
                f"will not help. Answer from the tools you can use, and tell the adjuster this "
                f"part needs someone with access to it.")
        out = registry.call(full_name, arguments)
        _audit(scope["caller"], full_name, arguments, "error" if out["is_error"] else "ok")
        if out["is_error"]:
            raise ToolError(out["text"])
        return out["text"]
    return call


def main():
    scope = _caller()
    registry = ToolRegistry.from_config(CONFIG)
    for full_name, (_srv, spec) in registry.routes.items():
        server.add_tool({**spec, "name": full_name}, _route(registry, scope, full_name))
    # Resources pass through unchanged: they are app-attached context, not calls.
    for srv in registry.servers.values():
        if "resources" in srv.server_info.get("capabilities", {}):
            for res in srv.request("resources/list").get("resources", []):
                server.resource(res["uri"], res["name"], res.get("description", ""),
                                res.get("mimeType", "text/plain"))(
                    lambda s=srv, u=res["uri"]: s.read_resource(u))
    try:
        server.run()
    finally:
        registry.close()


if __name__ == "__main__":
    main()
