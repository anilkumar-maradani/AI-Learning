#!/usr/bin/env python3
"""
policylens.py: the one entry point of the integrated claims triage system.

    python policylens.py setup                       build the index (both editions) + the claims snapshot
    python policylens.py triage CLM-2025-30001       FNOL in -> tool calls live -> referral out, trace id
            [--version w12-v2|w12-v1] [--model M]
    python policylens.py trace TRACE_ID              the request line + the MCP server's spans for it
    python policylens.py serve-mcp                   our coverage MCP server on stdio, for another squad
    python policylens.py eval [args...]              the Week 12 eval suite (evals/week12.py)
"""

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

from console import enable_utf8  # noqa: E402

enable_utf8()


def cmd_setup(_a):
    from claim_store import write_triage_snapshot
    from ingest import ingest_all
    ingest_all(reset=True)
    print("claims snapshot:", write_triage_snapshot())


def _index_ready() -> bool:
    try:
        from hybrid_retrieval import _get_bm25_index
        return any("effective_from" in c["metadata"] for c in _get_bm25_index().chunks)
    except Exception:
        return False


def cmd_triage(a):
    if not _index_ready():
        print("index missing or built before Week 12: running setup first")
        cmd_setup(a)
    from triage_agent import run_triage
    run = run_triage(a.claim, version=a.version, model=a.model, log=print)
    print("\n" + run["referral"]["text"])
    print(f"\ntrace id {run['trace_id']} · stop {run['stop_reason']} · laps {run['laps']} · "
          f"tokens {run['tokens']} · cost ${run['cost_usd']:.6f} · latency {run['latency_s']}s "
          f"(rate-limit waits {run['throttle_s']}s excluded) · guard rejections {len(run['guard_rejections'])} · "
          f"server spans joined {len(run['server_spans'])}")


def _lines(pattern: str):
    import glob
    for path in sorted(glob.glob(os.path.join(ROOT, "traces", "w12", pattern))):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)


def cmd_trace(a):
    # every run's files: requests.jsonl, requests_suite.jsonl, requests_boundary.jsonl, ...
    rec = next((r for r in _lines("requests*.jsonl") if r.get("trace_id") == a.trace_id), None)
    if rec is None:
        sys.exit(f"no request line with trace id {a.trace_id} in traces/w12/requests*.jsonl")
    server = [r for r in _lines("coverage_calls*.jsonl") if r.get("trace_id") == a.trace_id]
    if a.json:
        out = {"trace_id": rec["trace_id"], "host_request_line": rec,
               "mcp_server_spans_same_trace_id": server}
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)
        print(f"-> {a.json}")
    print(f"trace {rec['trace_id']} · {rec['version']} · {rec['model']} · prompt {rec['prompt']['version']}")
    print(f"input {rec['input']}")
    print("\nspans (host):")
    for s in rec["spans"]:
        at = s["attrs"]
        extra = f" server={at.get('server')}" if at.get("server") else ""
        if at.get("context"):
            extra += " context=" + ",".join(f"{c['chunk_id']}" for c in at["context"])
        print(f"  {s['span_id']:>4} {s['stage']:<10} {s['name']:<42} {s['latency_ms']:>9.1f} ms "
              f"{s['tokens']['total']:>6} tok ${s['cost_usd']:.6f}{extra}")
    print("\nspans (coverage MCP server, joined on the same trace id):")
    for r in server:
        print(f"  parent {r.get('parent_span_id')} {r.get('tool'):<26} {r.get('latency_ms')} ms "
              f"error={r.get('is_error')} sha256={str(r.get('result_sha256'))[:12]}")
    t = rec["totals"]
    print(f"\ntotals: {t['tokens']} tok, ${t['cost_usd']:.6f}, {t['latency_ms']} ms; by stage: "
          + ", ".join(f"{k} {v['latency_ms']} ms ${v['cost_usd']:.6f}" for k, v in t["by_stage"].items()))
    print("\n" + rec["referral"]["text"])


def cmd_serve(_a):
    server = os.path.join(ROOT, "mcp_servers", "coverage", "server.py")
    env = dict(os.environ)
    env.setdefault("POLICYLENS_WORDING_VERSION", "v2")
    env.setdefault("POLICYLENS_CALL_LOG", os.path.join(ROOT, "traces", "w12", "coverage_calls.jsonl"))
    sys.exit(subprocess.call([sys.executable, server], env=env))


def cmd_eval(a):
    sys.exit(subprocess.call([sys.executable, os.path.join(ROOT, "evals", "week12.py"), *a.rest]))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup").set_defaults(fn=cmd_setup)
    t = sub.add_parser("triage")
    t.add_argument("claim")
    t.add_argument("--version", default="w12-v2", choices=["w12-v1", "w12-v2"])
    t.add_argument("--model", default=None)
    t.set_defaults(fn=cmd_triage)
    tr = sub.add_parser("trace")
    tr.add_argument("trace_id")
    tr.add_argument("--json", default=None, help="also write the joined trace (host line + MCP server spans) here")
    tr.set_defaults(fn=cmd_trace)
    sub.add_parser("serve-mcp").set_defaults(fn=cmd_serve)
    e = sub.add_parser("eval")
    e.add_argument("rest", nargs=argparse.REMAINDER)
    e.set_defaults(fn=cmd_eval)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
