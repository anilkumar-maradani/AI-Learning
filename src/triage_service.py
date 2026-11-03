"""
triage_service.py — Week 11: the production front door of claim triage.

    handle(claim_number, user=...)  ->  route to a workflow version
                                    ->  run it (spans recorded)
                                    ->  write ONE redacted line to traces/week11/requests.jsonl

Version routing is configuration, not a deploy, so a canary can be widened or
rolled back by changing one environment variable:

    POLICYLENS_STABLE_VERSION   the version every request gets by default
    POLICYLENS_CANARY_VERSION   the version under test (unset = no canary)
    POLICYLENS_CANARY_PERCENT   0-100: share of CLAIMS routed to the canary

The canary bucket is a hash of the claim number, so one claim always gets the
same version: an adjuster re-checking a claim during the canary never sees the
coverage call flip between versions.
"""

import hashlib
import os

from observability import REQUESTS_PATH, build_record, write_record
from tools import get_claim as tool_get_claim
from workflow import PROMPTS, run_workflow
from claim_store import get_claim as store_get_claim

# Week 11 rollout of the exclusion-schedule fix (reports/week11/canary.md):
# v2 stays stable, v3 serves a sticky 10% of claims. Rollback = CANARY_PERCENT=0.
DEFAULT_STABLE = "workflow-v2"
DEFAULT_CANARY = "workflow-v3"
DEFAULT_CANARY_PERCENT = 10


def routing() -> dict:
    stable = os.environ.get("POLICYLENS_STABLE_VERSION", DEFAULT_STABLE)
    canary = os.environ.get("POLICYLENS_CANARY_VERSION", DEFAULT_CANARY or "") or None
    pct = int(os.environ.get("POLICYLENS_CANARY_PERCENT", DEFAULT_CANARY_PERCENT))
    for v in (stable, canary):
        if v and v not in PROMPTS:
            raise ValueError(f"unknown workflow version {v!r}; known: {sorted(PROMPTS)}")
    return {"stable": stable, "canary": canary, "canary_percent": pct if canary else 0}


def bucket(claim_number: str) -> int:
    return int(hashlib.sha256(claim_number.encode("utf-8")).hexdigest()[:8], 16) % 100


def route_version(claim_number: str) -> tuple[str, str]:
    """(version, arm) for one claim under the current routing config."""
    r = routing()
    if r["canary"] and bucket(claim_number) < r["canary_percent"]:
        return r["canary"], "canary"
    return r["stable"], "stable"


def handle(claim_number: str, user: str, channel: str = "adjuster_console",
           ts_utc: str | None = None, version: str | None = None,
           path: str = REQUESTS_PATH, write: bool = True, log=None) -> tuple[dict, dict]:
    """Answer one triage request. Returns (request_line, run). ``version`` pins a
    workflow version (used by the replay of days when only one version existed)."""
    arm = "pinned"
    if version is None:
        version, arm = route_version(claim_number)
    run = run_workflow(claim_number, log=log, version=version)
    claim_view = tool_get_claim(claim_number)          # what the workflow saw, decision note withheld
    rec = build_record(run=run, claim=claim_view, user=user, channel=channel, ts_utc=ts_utc,
                       extra={"route": {"arm": arm, **routing()} if arm != "pinned" else {"arm": arm}})
    if write:
        stored = store_get_claim(claim_number) or {}
        rec["trace_id"] = write_record(rec, stored.get("claimant_name"), path)
    return rec, run
