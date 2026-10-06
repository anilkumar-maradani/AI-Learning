#!/usr/bin/env python3
"""
claims-system MCP server  v0.3.1
Maintainer: Northgate Mutual claims platform team (claims-platform@northgate.example)

THIRD-PARTY CODE. Vendored into PolicyLens as a stand-in for the platform
team's server so the Week 9 exercise runs offline. PolicyLens does not edit
this file; it only adds the server to mcp_config.json. See
reports/week9/risk_note.md for what it can reach.

Tools
  get_claim_status(claim_number)    status, policy, dates, forms, claimant
  get_adjuster_notes(claim_number)  every dated adjuster note on the claim

Auth: CLAIMS_API_TOKEN must be set. Any non-empty token reads every claim,
open or closed (the real backend has no per-claim scoping either).
Logging: every call is appended to $CLAIMS_SYSTEM_LOG
(default logs/claims_system.log): time, tool, claim number, token fingerprint.

Stdio JSON-RPC 2.0, standard library only.
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

VERSION = "0.3.1"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("CLAIMS_DATA_DIR", os.path.join(HERE, "..", "..", "data", "claims"))
LOG_PATH = os.environ.get("CLAIMS_SYSTEM_LOG", os.path.join(HERE, "..", "..", "logs", "claims_system.log"))
CLAIM_RE = re.compile(r"^CLM-\d{4}-\d{5}$")

TOOLS = [
    {
        "name": "get_claim_status",
        "description": (
            "Current status of one claim in the Northgate claims system, looked up by claim "
            "number (format CLM-YYYY-nnnnn, e.g. CLM-2026-20103). Returns the status "
            "(open/closed), policy number, claimant, date of loss, date reported, the "
            "endorsement forms on the policy, how many adjuster notes exist and the date "
            "of the latest one. It does not return the note text (use get_adjuster_notes) "
            "and it does not say whether anything is covered."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"claim_number": {"type": "string", "pattern": "^CLM-\\d{4}-\\d{5}$",
                                            "description": "e.g. CLM-2026-20103"}},
            "required": ["claim_number"],
        },
    },
    {
        "name": "get_adjuster_notes",
        "description": (
            "The adjuster note history behind one claim, oldest first: date, adjuster id and "
            "the note text. Notes record what the adjuster found on site and often say what "
            "actually caused the loss. A claim with no notes yet returns an empty list, "
            "which means the facts are not in yet, not that nothing happened."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"claim_number": {"type": "string", "pattern": "^CLM-\\d{4}-\\d{5}$",
                                            "description": "e.g. CLM-2026-20103"}},
            "required": ["claim_number"],
        },
    },
]

_claims = None


def claims():
    global _claims
    if _claims is None:
        _claims = {}
        for name in ("open_claims.jsonl", "closed_claims.jsonl"):
            with open(os.path.join(DATA_DIR, name), encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        c = json.loads(line)
                        _claims[c["claim_number"]] = c
    return _claims


def audit(tool, claim_number, outcome):
    token = os.environ.get("CLAIMS_API_TOKEN", "")
    fp = hashlib.sha256(token.encode()).hexdigest()[:8] if token else "none"
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} tool={tool} "
                 f"claim={claim_number} outcome={outcome} token={fp}\n")


def lookup(claim_number):
    """(claim, error_text). Unknown and malformed claim numbers are told apart."""
    cn = (claim_number or "").strip().upper()
    if not CLAIM_RE.match(cn):
        return None, (f"'{claim_number}' is not a claim number: claim numbers look like "
                      f"CLM-YYYY-nnnnn, e.g. CLM-2026-20103. Ask the adjuster for the full number.")
    c = claims().get(cn)
    if c is None:
        return None, (f"claim {cn} not found in the claims system. The number is well formed, "
                      f"so check it for a typo with the adjuster; the claims system itself is up.")
    return c, None


def call_tool(name, args):
    if not os.environ.get("CLAIMS_API_TOKEN"):
        audit(name, args.get("claim_number"), "no_token")
        return True, "claims system unavailable: no CLAIMS_API_TOKEN configured for this server."
    claim, err = lookup(args.get("claim_number"))
    if err:
        audit(name, args.get("claim_number"), "not_found")
        return True, err
    audit(name, claim["claim_number"], "ok")
    notes = claim.get("adjuster_notes") or []
    if name == "get_claim_status":
        out = {
            "claim_number": claim["claim_number"],
            "status": claim["status"],
            "policy_number": claim["policy_number"],
            "claimant_name": claim["claimant_name"],
            "date_of_loss": claim["date_of_loss"],
            "reported_date": claim.get("reported_date"),
            "forms": claim["forms"],
            "adjuster_note_count": len(notes),
            "latest_note_date": notes[-1]["date"] if notes else None,
        }
    else:
        out = {"claim_number": claim["claim_number"], "notes": notes}
    return False, json.dumps(out, ensure_ascii=False)


def handle(msg):
    method, params = msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        return {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "claims-system", "version": VERSION}}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        if params.get("name") not in {t["name"] for t in TOOLS}:
            raise LookupError(params.get("name"))
        is_error, text = call_tool(params["name"], params.get("arguments") or {})
        return {"content": [{"type": "text", "text": text}], "isError": is_error}
    raise NotImplementedError(method)


def main():
    for stream in (sys.stdin, sys.stdout):
        stream.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        if "id" not in msg:
            continue
        try:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg)}
        except NotImplementedError as exc:
            reply = {"jsonrpc": "2.0", "id": msg["id"],
                     "error": {"code": -32601, "message": f"Method not found: {exc}"}}
        except LookupError as exc:
            reply = {"jsonrpc": "2.0", "id": msg["id"],
                     "error": {"code": -32602, "message": f"Unknown tool: {exc}"}}
        sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
