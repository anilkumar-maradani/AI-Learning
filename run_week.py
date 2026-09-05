#!/usr/bin/env python
"""
run_week.py — Replay a week of adjuster traffic through the claims assistant
and write one trace per question.

    python run_week.py                     # full week -> traces/traces.jsonl
    python run_week.py --limit 3           # smoke test
    python run_week.py --demo              # the 10 curated demo claims
    python run_week.py --resume            # skip questions already traced

The point of this script is to produce a log nobody curated. It runs every
question in traffic/week_traffic.py in shuffled order and does not inspect,
grade, or filter the answers. Grading happens later, by hand.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "traffic"))

from console import enable_utf8
from claims_agent import answer_claim_question
from tracing import TraceWriter, TRACE_DIR, read_traces
from week_traffic import build_traffic, demo_set

enable_utf8()

DEMO_TRACE_PATH = os.path.join(TRACE_DIR, "demo_traces.jsonl")


def retry_errors(path: str | None, demo: bool = False, sleep: float = 2.0) -> int:
    """
    Re-run only the traces whose provider call failed and swap the fresh record
    into the same slot in the log.

    Why this exists: bulk-generating a week of traffic in one sitting exhausts
    the free-tier daily token budget, and every call after that point returns a
    429 with no answer. Those are artefacts of the *generation harness*, not of
    the assistant, and leaving them in the log would invent a top failure mode
    out of my own rate limit. The questions are unchanged; only the failed calls
    are re-issued. Every replacement is announced on stdout so the substitution
    is on the record.
    """
    import json

    from redaction import redact_text
    from tracing import TraceRecord, read_traces

    log_path = path or TraceWriter().path
    traces = read_traces(log_path)
    failed = [(i, t) for i, t in enumerate(traces) if t.get("error")]
    if not failed:
        print(f"No errored traces in {log_path}.")
        return 0

    claims = demo_set() if demo else build_traffic()
    by_question = {
        redact_text(c["question"], [c["claimant_name"]])[0]: c for c in claims
    }

    print(f"Retrying {len(failed)} errored trace(s) in {log_path}\n")
    writer = TraceWriter(log_path)          # reused only for its leak check
    still_failing = 0

    for n, (idx, old) in enumerate(failed, 1):
        claim = by_question.get(old["input"]["question"])
        if claim is None:
            print(f"  [{n}/{len(failed)}] {old['trace_id']}: no matching claim, left as-is")
            still_failing += 1
            continue
        try:
            rec = answer_claim_question(claim, writer=_NullWriter())
        except Exception as exc:
            print(f"  [{n}/{len(failed)}] {old['trace_id']}: {type(exc).__name__}: {exc}")
            still_failing += 1
            continue
        if rec.error:
            print(f"  [{n}/{len(failed)}] {old['trace_id']} -> still failing "
                  f"({rec.error['type']})")
            still_failing += 1
        else:
            print(f"  [{n}/{len(failed)}] {old['trace_id']} -> {rec.trace_id}  "
                  f"{rec.timing['total_ms']:>7.0f}ms  {rec.input['question'][:56]}")
        from dataclasses import asdict
        traces[idx] = asdict(rec)
        time.sleep(sleep)

    with open(log_path, "w", encoding="utf-8") as fh:
        for t in traces:
            line = json.dumps(t, ensure_ascii=False)
            leaks = __import__("redaction").assert_clean(line)
            if leaks:
                raise RuntimeError(f"refusing to rewrite log, leak: {leaks}")
            fh.write(line + "\n")

    print(f"\nRewrote {log_path}: {len(failed) - still_failing} replaced, "
          f"{still_failing} still failing.")
    return 0


class _NullWriter:
    """Collects the record without appending — retry_errors rewrites the log itself."""
    path = None

    def write(self, record, known_names=None):
        return record.trace_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--demo", action="store_true",
                    help="run the curated monthly-review set into demo_traces.jsonl")
    ap.add_argument("--resume", action="store_true",
                    help="skip questions whose redacted text is already in the log")
    ap.add_argument("--sleep", type=float, default=0.4,
                    help="pause between calls to stay inside the free-tier rate limit")
    ap.add_argument("--retry-errors", action="store_true",
                    help="re-run only the traces whose provider call failed, "
                         "replacing them in place in the log")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.retry_errors:
        return retry_errors(
            DEMO_TRACE_PATH if args.demo else None,
            demo=args.demo,
            sleep=max(args.sleep, 2.0),
        )

    claims = demo_set() if args.demo else build_traffic()
    out_path = args.out or (DEMO_TRACE_PATH if args.demo else None)
    writer = TraceWriter(out_path) if out_path else TraceWriter()

    if args.resume:
        from redaction import redact_text
        seen = {t["input"]["question"] for t in read_traces(writer.path)}
        before = len(claims)
        claims = [
            c for c in claims
            if redact_text(c["question"], [c["claimant_name"]])[0] not in seen
        ]
        print(f"resume: {before - len(claims)} already traced, {len(claims)} to go")

    if args.limit:
        claims = claims[: args.limit]

    print(f"Running {len(claims)} claim questions -> {writer.path}\n")
    errors = 0
    t_start = time.time()

    for i, claim in enumerate(claims, 1):
        try:
            rec = answer_claim_question(claim, writer=writer)
        except Exception as exc:
            errors += 1
            print(f"  [{i}/{len(claims)}] FAILED to trace: {type(exc).__name__}: {exc}")
            continue
        flag = "ERR " if rec.error else ("REF " if rec.output["is_refusal"] else "ans ")
        print(f"  [{i}/{len(claims)}] {flag} {rec.trace_id}  "
              f"{rec.timing['total_ms']:>7.0f}ms  {rec.input['question'][:66]}")
        if rec.error:
            errors += 1
        time.sleep(args.sleep)

    mins = (time.time() - t_start) / 60
    print(f"\nDone in {mins:.1f} min. {errors} error(s). Log: {writer.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
