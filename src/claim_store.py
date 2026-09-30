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
CLAIM_FILES = ("open_claims.jsonl", "closed_claims.jsonl")

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
