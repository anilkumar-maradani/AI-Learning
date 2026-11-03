"""
test_week11_request_log.py — Evidence that the Week 11 request log is both
searchable and clean.

Run:  python tests/test_week11_request_log.py

  1. Clean: no line holds a raw claim number, policy number or claimant name,
     and no adjuster note appears verbatim (notes are logged as hash + count).
  2. Complete: every answered line carries a prompt version + SHA-256, the
     retrieved context ids, and one span per stage call with latency, tokens and
     cost; the stage totals add up to the line's totals.
"""

import json
import os
import re
import sys

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from claim_store import load_claims  # noqa: E402
from observability import REQUESTS_PATH, STAGES, read_requests  # noqa: E402

CLAIM_RE = re.compile(r"\bCLM-\d{4}-\d{5}\b")
POLICY_RE = re.compile(r"\bHOP-\d{5,10}\b")


def check_1_clean(raw_lines: list[str]) -> None:
    claims = load_claims().values()
    names = {c["claimant_name"] for c in claims}
    surnames = {n.split()[-1] for n in names}
    notes = {n["text"] for c in claims for n in c.get("adjuster_notes") or []}
    for i, line in enumerate(raw_lines, 1):
        assert not CLAIM_RE.search(line), f"line {i}: raw claim number"
        assert not POLICY_RE.search(line), f"line {i}: raw policy number"
        for s in surnames:
            assert not re.search(rf"\b{re.escape(s)}\b", line), f"line {i}: claimant surname {s!r}"
        for t in notes:
            assert t not in line, f"line {i}: an adjuster note was logged verbatim"
    print(f"  [1] {len(raw_lines)} lines: no claim/policy number, no claimant name, no verbatim note")


def check_2_complete(rows: list[dict]) -> None:
    answered = [r for r in rows if r["totals"]["tokens"]]
    for r in answered:
        p = r["prompt"]
        assert p.get("version") and len(p.get("system_sha256", "")) == 64, r["trace_id"]
        assert r["retrieval"]["context_ids"], f"{r['trace_id']}: no context ids"
        assert {s["stage"] for s in r["spans"]} == set(STAGES), f"{r['trace_id']}: a stage has no span"
        for s in r["spans"]:
            assert s["latency_ms"] is not None and "total" in s["tokens"] and "cost_usd" in s, s["name"]
        for st in STAGES:
            want = sum(s["cost_usd"] for s in r["spans"] if s["stage"] == st)
            assert abs(r["totals"]["by_stage"][st]["cost_usd"] - want) < 1e-9, (r["trace_id"], st)
    print(f"  [2] {len(answered)} answered lines: prompt version + sha, context ids, "
          f"spans for {'/'.join(STAGES)} with latency/tokens/cost, totals add up")


if __name__ == "__main__":
    if not os.path.exists(REQUESTS_PATH):
        sys.exit(f"no log at {REQUESTS_PATH}; run `python evals/week11.py traffic` first")
    with open(REQUESTS_PATH, encoding="utf-8") as fh:
        raw = [l for l in fh if l.strip()]
    print(f"Week 11 request log: {os.path.relpath(REQUESTS_PATH, _ROOT)}")
    check_1_clean(raw)
    check_2_complete(read_requests())
    print("PASS")
