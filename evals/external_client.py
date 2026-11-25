#!/usr/bin/env python3
"""
Week 12: call PolicyLens' MCP server the way another squad's agent would.

    python evals/external_client.py

A raw JSON-RPC 2.0 client over stdio. It shares NO code with the PolicyLens
host (no mcp_client, no ToolRegistry): it starts the server exactly as
`python policylens.py serve-mcp` does, identifies itself as "fresh-eyes-client",
discovers the tools, calls each of them (including the mistakes a stranger
makes: the wrong product, a typo in a form number, no loss date), and then scans
everything the server handed back for claimant names, addresses and injuries.

The server's own call log for these calls goes to traces/w12/external_calls.jsonl:
that file is the answer to "what exactly did your MCP server hand to another
squad's agent?".
"""

import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from console import enable_utf8  # noqa: E402

enable_utf8()

LOG = os.path.join(ROOT, "traces", "w12", "external_calls.jsonl")

CALLS = [
    ("lookup_policy", {"claim_number": "CLM-2025-30001"}),
    ("check_coverage_in_force", {"policy_number": "HOP-6610301", "loss_date": "2025-08-11"}),
    ("check_coverage_in_force", {"policy_number": "HOP-6610307", "loss_date": "2025-11-02"}),
    ("search_policy_wording", {"query": "rain runoff came in under the back door", "loss_date": "2025-08-11"}),
    ("search_policy_wording", {"query": "flood", "loss_date": "2025-08-11", "form_number": "NG-1101"}),
    ("search_policy_wording", {"query": "flood", "loss_date": "2026-03-01", "form_number": "NG-1101"}),
    # what a stranger gets wrong
    ("search_policy_wording", {"query": "windscreen damage", "loss_date": "2025-08-11", "product": "motor"}),
    ("search_policy_wording", {"query": "flood", "loss_date": "2025-08-11", "form_number": "NG-1110"}),
    ("search_policy_wording", {"query": "flood", "loss_date": "2019-01-01", "form_number": "NG-1101"}),
    ("search_policy_wording", {"query": "flood"}),
]


def main():
    from claim_store import load_claims
    from redaction import INJURY_RE, _PATTERNS

    env = {k: v for k, v in os.environ.items()}
    env.update({"POLICYLENS_CALL_LOG": LOG, "POLICYLENS_WORDING_VERSION": "v2",
                "PYTHONUTF8": "1", "HF_HUB_OFFLINE": "1"})
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "mcp_servers", "coverage", "server.py")],
                            cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    nid = 0

    def rpc(method, params=None, notify=False):
        nonlocal nid
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            nid += 1
            msg["id"] = nid
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        if notify:
            return None
        while True:
            reply = json.loads(proc.stdout.readline())
            if reply.get("id") == nid:
                return reply

    init = rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "fresh-eyes-client", "version": "0.1"}})
    print("server:", init["result"]["serverInfo"])
    rpc("notifications/initialized", notify=True)
    tools = rpc("tools/list")["result"]["tools"]
    print("tools discovered:", [t["name"] for t in tools])
    for t in tools:
        print(f"  {t['name']}({', '.join(t['inputSchema'].get('properties', {}))})  "
              f"required={t['inputSchema'].get('required', [])}")

    handed_out = []
    print("\ncalls:")
    for name, args in CALLS:
        r = rpc("tools/call", {"name": name, "arguments": args})
        if "error" in r:
            text, is_err = f"JSON-RPC error {r['error']['code']}: {r['error']['message']}", True
        else:
            text = "\n".join(c.get("text", "") for c in r["result"]["content"])
            is_err = r["result"].get("isError", False)
        handed_out.append(text)
        short = text if len(text) < 170 else text[:170] + "..."
        print(f"  {'ERR' if is_err else 'ok '} {name} {json.dumps(args)}\n      -> {short}")
    proc.stdin.close()
    proc.wait(timeout=10)

    # PII scan of everything the server handed out
    claims = load_claims().values()
    names = {c["claimant_name"] for c in claims}
    parts = {p for n in names for p in n.split() if len(p) > 2}
    addr = _PATTERNS[4][1]
    blob = "\n".join(handed_out)
    leaks = [p for p in parts if re.search(rf"\b{re.escape(p)}\b", blob)]
    leaks += [m.group(0) for m in addr.finditer(blob)]
    leaks += [m.group(0) for m in INJURY_RE.finditer(blob)]
    print(f"\nPII scan of {len(handed_out)} responses ({len(blob):,} chars): "
          f"{'CLEAN: no claimant name, address or injury' if not leaks else 'LEAKS: ' + str(leaks)}")
    print(f"server call log for these calls: {os.path.relpath(LOG, ROOT)}")
    return 0 if not leaks else 1


if __name__ == "__main__":
    sys.exit(main())
