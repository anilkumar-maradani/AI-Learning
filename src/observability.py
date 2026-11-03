"""
observability.py — Week 11: one log line per production request, with spans.

Every request the triage service answers writes ONE JSON line to
``traces/week11/requests.jsonl``. A line is enough to answer "what happened,
what did it cost, and why" without the claim file:

    who / when / what kind    ts_utc, user (adjuster id), channel, input.type
    which prompt              prompt.version + both SHA-256s
    what it read              retrieval.context_ids, and per retrieval span the
                              rank / chunk_id / form / clause of every passage
    what it said              output.decision, exclusion_ids, clauses, payable,
                              reason (redacted)
    what it cost              spans[]: one per stage call, each with latency_ms,
                              tokens and cost_usd; totals.by_stage sums them

Span stages are exactly three: ``retrieval`` (policy wording lookups),
``generation`` (model calls) and ``tools`` (claims system + payout arithmetic).

Rules carried over from Week 5:
  * Redact on write. Lines go through tracing.EventWriter, which pseudonymises
    every string and refuses to append a line that still holds an identifier.
  * Adjuster notes are never logged verbatim, not even redacted: free-text notes
    are where claimant details hide. The line keeps a SHA-256 and a count, so
    "did the input change?" is answerable, "what did the notes say?" is not.
  * Latency is model + tool time. Rate-limit sleeps are kept in their own field
    (throttle_ms) and never counted as latency, as in Weeks 7-10.
"""

import hashlib
import json
import os
import statistics
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

from tracing import EventWriter

SCHEMA = "w11-request/1"
SERVICE = "triage-workflow"

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_DIR = os.path.join(ROOT, "traces", "week11")
REQUESTS_PATH = os.path.join(LOG_DIR, "requests.jsonl")

STAGES = ("retrieval", "generation", "tools")

PERIL_BY_FORM = {
    "NG-1101": "water", "NG-1102": "wind", "NG-1103": "mold",
    "NG-1104": "valuables", "NG-1105": "earth_movement", "NG-1106": "home_business",
}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def input_type(forms: list[str]) -> str:
    """What kind of claim this is, known before any model call: the peril family of
    each attached form, '+'-joined when the policy carries more than one."""
    return "+".join(PERIL_BY_FORM.get(f, f) for f in forms) or "unknown"


_enc = None


def count_tokens(text: str) -> int:
    """o200k_base, the base of gpt-oss's harmony tokenizer. Used only to split one
    call's prompt into blocks; the provider's prompt_tokens stays the billed number."""
    global _enc
    if _enc is None:
        import tiktoken
        _enc = tiktoken.get_encoding("o200k_base")
    return len(_enc.encode(text))


# ---------------------------------------------------------------------------
# Spans
# ---------------------------------------------------------------------------

class Tracer:
    """Collects the spans of one request. Not thread-safe; one per request."""

    def __init__(self):
        self.t0 = time.perf_counter()
        self.spans: list[dict] = []

    @contextmanager
    def span(self, name: str, stage: str, **attrs):
        if stage not in STAGES:
            raise ValueError(f"stage must be one of {STAGES}")
        s = {
            "span_id": f"sp{len(self.spans) + 1}",
            "name": name,
            "stage": stage,
            "start_ms": round((time.perf_counter() - self.t0) * 1000, 1),
            "latency_ms": None,
            "throttle_ms": 0.0,
            "tokens": {"prompt": 0, "completion": 0, "total": 0},
            "cost_usd": 0.0,
            "attrs": dict(attrs),
        }
        t = time.perf_counter()
        try:
            yield s
        finally:
            if s["latency_ms"] is None:  # a generation span sets its own (model time only)
                s["latency_ms"] = round((time.perf_counter() - t) * 1000, 1)
            self.spans.append(s)

    @staticmethod
    def record_llm(s: dict, res: dict) -> None:
        """Copy one llm.chat result onto a generation span."""
        s["latency_ms"] = round(res["api_s"] * 1000, 1)
        s["throttle_ms"] = round(res["throttle_s"] * 1000, 1)
        s["tokens"] = dict(res["usage"])
        s["cost_usd"] = round(res["cost_usd"], 8)
        s["attrs"]["finish_reason"] = res["finish_reason"]
        s["attrs"]["error"] = res["error"]


def stage_totals(spans: list[dict]) -> dict:
    out = {st: {"spans": 0, "latency_ms": 0.0, "tokens": 0, "cost_usd": 0.0} for st in STAGES}
    for s in spans:
        row = out[s["stage"]]
        row["spans"] += 1
        row["latency_ms"] = round(row["latency_ms"] + s["latency_ms"], 1)
        row["tokens"] += s["tokens"]["total"]
        row["cost_usd"] = round(row["cost_usd"] + s["cost_usd"], 8)
    return out


def context_ids(spans: list[dict]) -> list[str]:
    """Every chunk id that was put in front of the model, in the order it was sent."""
    out = []
    for s in spans:
        for c in s["attrs"].get("context") or []:
            if c["chunk_id"] not in out:
                out.append(c["chunk_id"])
    return out


# ---------------------------------------------------------------------------
# The request line
# ---------------------------------------------------------------------------

def build_record(*, run: dict, claim: dict, user: str, channel: str,
                 ts_utc: str | None = None, extra: dict | None = None) -> dict:
    """One request line from a workflow run. ``claim`` is the claim file as the
    workflow saw it (decision note withheld); identifiers are redacted on write."""
    answer = run.get("answer") or {}
    spans = run.get("spans") or []
    notes = claim.get("adjuster_notes") or []
    gen = next((s for s in spans if s["stage"] == "generation"), None)
    rec = {
        "schema": SCHEMA,
        "service": SERVICE,
        "ts_utc": ts_utc or datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "user": user,
        "channel": channel,
        "prompt": run.get("prompt") or {"version": run.get("prompt_version")},
        "model": (gen or {}).get("attrs", {}).get("model"),
        "input": {
            "type": input_type(claim.get("forms") or []),
            "claim_ref": claim.get("claim_number", ""),          # pseudonymised on write
            "forms": claim.get("forms") or [],
            "fnol": claim.get("fnol_description", ""),            # one line, redacted on write
            "notes": {"count": len(notes),
                      "sha256": sha256(json.dumps(notes, ensure_ascii=False, sort_keys=True))},
        },
        "retrieval": {"context_ids": context_ids(spans)},
        "output": {
            "decision": answer.get("decision"),
            "exclusion_ids": answer.get("exclusion_ids") or [],
            "clauses": answer.get("clauses") or [],
            "payable": answer.get("payable"),
            "reason": answer.get("reason", ""),
        },
        "stop_reason": run.get("stop_reason"),
        "spans": spans,
        "totals": {
            "latency_ms": round(sum(s["latency_ms"] for s in spans), 1),
            "throttle_ms": round(sum(s["throttle_ms"] for s in spans), 1),
            "tokens": sum(s["tokens"]["total"] for s in spans),
            "cost_usd": round(sum(s["cost_usd"] for s in spans), 8),
            "by_stage": stage_totals(spans),
        },
        "error": (gen or {}).get("attrs", {}).get("error"),
    }
    if extra:
        rec.update(extra)
    return rec


def write_record(rec: dict, claimant_name: str | None, path: str = REQUESTS_PATH) -> str:
    """Redact on write (tracing.EventWriter): the raw claim number and claimant name
    never reach the file. Returns the trace id."""
    return EventWriter(path).write(rec, known_names=[claimant_name] if claimant_name else None)


def read_requests(path: str = REQUESTS_PATH) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def sort_log(path: str = REQUESTS_PATH) -> None:
    """Keep the file in time order (a planted line must not stand out by position)."""
    rows = sorted(read_requests(path), key=lambda r: r["ts_utc"])
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Slices: time / user / prompt version / input type / cost outlier (+ output)
# ---------------------------------------------------------------------------

def resolve_day(day: str, today: date | None = None) -> str:
    today = today or datetime.now(timezone.utc).date()
    if day == "today":
        return today.isoformat()
    if day == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    return date.fromisoformat(day).isoformat()


def cost_fence(rows: list[dict]) -> float:
    """Tukey's upper fence, Q3 + 1.5 IQR, over the cost of every answered request."""
    costs = sorted(r["totals"]["cost_usd"] for r in rows if r["totals"]["tokens"])
    if len(costs) < 4:
        return float("inf")
    q1, _, q3 = statistics.quantiles(costs, n=4)
    return q3 + 1.5 * (q3 - q1)


def slice_rows(rows: list[dict], *, day=None, since=None, until=None, user=None,
               prompt_version=None, input_type_has=None, decision=None,
               cost_outlier=False, grep=None, today=None) -> list[dict]:
    out = rows
    if day:
        d = resolve_day(day, today)
        out = [r for r in out if r["ts_utc"].startswith(d)]
    if since:
        out = [r for r in out if r["ts_utc"][11:16] >= since]
    if until:
        out = [r for r in out if r["ts_utc"][11:16] <= until]
    if user:
        out = [r for r in out if r["user"] in user.split(",")]
    if prompt_version:
        out = [r for r in out if r["prompt"].get("version") in prompt_version.split(",")]
    if input_type_has:
        out = [r for r in out if input_type_has in r["input"]["type"]]
    if decision:
        out = [r for r in out if (r["output"]["decision"] or "none") in decision.split(",")]
    if cost_outlier:
        fence = cost_fence(rows)
        out = [r for r in out if r["totals"]["cost_usd"] > fence]
    if grep:
        g = grep.lower()
        out = [r for r in out if g in json.dumps(r["output"], ensure_ascii=False).lower()
               or g in r["input"]["fnol"].lower()]
    return out
