"""
claim_store.py — Read-only access to the claim files in data/claims/.

A claim file is what an adjuster sees on screen: the policy it sits on
(forms attached, Coverage A limit, all-peril deductible, any scheduled
articles), the first notice of loss, the estimate lines and the dated
adjuster notes. Closed claims end with the adjuster's decision note; open
claims do not.

Expected outcomes are NOT stored here. They live in evals/cases/, so no tool
the agent can call is able to read the answer key.
"""

import json
import os
import re

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "claims")
# w12_claims.jsonl (Week 12): losses dated either side of an edition change,
# and two whose policy was not in force on the loss date.
CLAIM_FILES = ("open_claims.jsonl", "closed_claims.jsonl", "w12_claims.jsonl")
# Week 12: what the third-party claims server reads (see write_triage_snapshot).
SNAPSHOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "claims_at_triage"))

CLAIM_NUMBER_RE = re.compile(r"^CLM-\d{4}-\d{5}$")

_cache: dict[str, dict] | None = None


def load_claims() -> dict[str, dict]:
    global _cache
    if _cache is None:
        _cache = {}
        for name in CLAIM_FILES:
            with open(os.path.join(_DATA_DIR, name), encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        claim = json.loads(line)
                        _cache[claim["claim_number"]] = claim
    return _cache


def get_claim(claim_number: str) -> dict | None:
    return load_claims().get(claim_number.strip().upper())


def is_decision_note(note: dict) -> bool:
    return note["text"].startswith("Decision:")


def write_triage_snapshot(out_dir: str = SNAPSHOT_DIR) -> dict:
    """Week 12: the claims system as it stands when triage runs, for the vendored
    claims_system MCP server (which reads open_claims.jsonl / closed_claims.jsonl
    from CLAIMS_DATA_DIR and which PolicyLens does not edit).

    Every claim is included, and every closed claim loses its final
    "Decision:" note: the adjuster's coverage decision, i.e. the eval's answer
    key. tools.get_claim has withheld it since Week 10; the MCP server returned
    it verbatim (reports/week12/seams.md #6)."""
    os.makedirs(out_dir, exist_ok=True)
    counts = {"open": 0, "closed": 0, "decision_notes_withheld": 0}
    rows = {"open": [], "closed": []}
    for c in load_claims().values():
        notes = c.get("adjuster_notes") or []
        kept = [n for n in notes if not is_decision_note(n)]
        counts["decision_notes_withheld"] += len(notes) - len(kept)
        bucket = "open" if c["status"] == "open" else "closed"
        rows[bucket].append({**c, "adjuster_notes": kept})
        counts[bucket] += 1
    for bucket, items in rows.items():
        with open(os.path.join(out_dir, f"{bucket}_claims.jsonl"), "w", encoding="utf-8") as fh:
            for c in items:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    return counts


def damage_estimate(claim: dict) -> float | None:
    lines = claim.get("estimate_lines") or []
    return float(sum(l["amount"] for l in lines)) if lines else None


def render_claim_file(claim: dict, include_name: bool = False) -> str:
    """Plain-text claim file, the same view a human reviewer gets."""
    out = [
        f"Claim number: {claim['claim_number']}",
        f"Policy number: {claim['policy_number']}",
    ]
    if include_name:
        out.append(f"Claimant: {claim['claimant_name']}")
    out += [
        f"Status: {claim['status']}",
        f"Date of loss: {claim['date_of_loss']}",
        f"Forms attached: {', '.join(claim['forms'])}",
        f"Coverage A limit: ${claim['coverage_a_limit']:,}",
        f"All-peril deductible: ${claim['all_peril_deductible']:,}",
    ]
    for art in claim.get("scheduled_articles") or []:
        out.append(
            f"Scheduled article {art['item_no']}: {art['description']}, "
            f"agreed value ${art['agreed_value']:,}"
        )
    out.append(f"First notice of loss: {claim['fnol_description']}")
    lines = claim.get("estimate_lines") or []
    if lines:
        out.append("Estimate lines:")
        out += [f"  - {l['item']}: ${l['amount']:,}" for l in lines]
    notes = claim.get("adjuster_notes") or []
    out.append("Adjuster notes:" if notes else "Adjuster notes: none yet")
    out += [f"  [{n['date']}] {n['author']}: {n['text']}" for n in notes]
    return "\n".join(out)
