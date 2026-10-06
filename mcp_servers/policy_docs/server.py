"""
policy_docs — PolicyLens' own MCP server: search over the Northgate Mutual
endorsement library (data/policy, indexed by src/ingest.py).

  tool      search_policy                  model-invoked: read endorsement wording
  resource  policy://exclusion-schedule    app-attached: every exclusion row of
                                           every form, one line each

The exclusion schedule is a resource, not a tool, because the model should
already have it in front of it; it should never have to decide to go and
fetch it.

Run it directly only to debug; normally the host starts it from mcp_config.json:
    python mcp_servers/policy_docs/server.py      (speaks JSON-RPC on stdin/stdout)
"""

import glob
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from mcp_server import Server, ToolError  # noqa: E402

server = Server("policy-docs", "0.9.0")

POLICY_DIR = os.path.join(ROOT, "data", "policy")


@server.tool({
    "type": "object",
    "properties": {
        "query": {"type": "string"},
        "form_number": {"type": "string"},
    },
    "required": ["query"],
})
def search_policy(query: str, form_number: str | None = None) -> dict:
    """Search policy documents."""
    from tools import search_policy as _search
    try:
        out = _search(query, form_number=form_number)
    except Exception:
        raise ToolError("Error: lookup failed")
    if out.get("error"):
        raise ToolError("Error: lookup failed")
    return out


_ROW_RE = re.compile(r"^\|\s*(E-\d+)?\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$")


@server.resource("policy://exclusion-schedule", "Exclusion schedule",
                 "Every exclusion code in every Northgate Mutual endorsement, one line each.")
def exclusion_schedule() -> str:
    lines = []
    for path in sorted(glob.glob(os.path.join(POLICY_DIR, "*.txt"))):
        form = os.path.basename(path).split("_")[0]
        rows: list[list[str]] = []
        for line in open(path, encoding="utf-8"):
            m = _ROW_RE.match(line.strip())
            if not m:
                continue
            code, peril, scope = m.groups()
            if code:
                rows.append([code, peril, scope])
            elif rows and scope and not set(scope) <= {"-"}:
                rows[-1][1] = (rows[-1][1] + " " + peril).strip()
                rows[-1][2] += " " + scope
        lines += [f"{form} {c}: {p} — {s}" for c, p, s in rows]
    return "\n".join(lines)


if __name__ == "__main__":
    server.run()
