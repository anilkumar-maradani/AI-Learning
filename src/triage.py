"""
triage.py — What the agent and the workflow share: the output contract, the
final-answer parser and the outcome grader. Keeping these in one place is what
makes the race a like-for-like comparison.

Output contract (the final answer of both systems):
{
  "claim_number": "CLM-2026-20101",
  "decision": "covered" | "partially_covered" | "excluded" | "needs_info",
  "exclusion_ids": ["E-41"],        # every exclusion relied on, [] if none
  "clauses": ["WE-1"],              # clauses relied on
  "payable": 5300.0 | null,         # null only for needs_info
  "reason": "one or two sentences"
}
"""

import json
import re

DECISIONS = ["covered", "partially_covered", "excluded", "needs_info"]

CONTRACT_TEXT = """Final answer: reply with ONE JSON object and nothing else:
{"claim_number": "...", "decision": "covered|partially_covered|excluded|needs_info",
 "exclusion_ids": ["E-NN", ...], "clauses": ["XX-N", ...], "payable": <number or null>,
 "reason": "<one or two sentences>"}
- covered: everything claimed is paid (less the deductible).
- partially_covered: part of the claimed amount is excluded, or the payment is capped by a sublimit.
- excluded: nothing is payable because an exclusion applies.
- needs_info: the claim file does not yet hold enough facts to decide; payable is null.
- payable must be the number returned by compute_payout (0 when excluded)."""


def parse_final(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def grade(answer: dict | None, expected: dict) -> dict:
    """Outcome pass = right decision, right payable (within $1), right exclusion cited."""
    if not answer:
        return {"pass": False, "why": "no parseable final answer"}
    why = []
    if answer.get("decision") != expected["decision"]:
        why.append(f"decision {answer.get('decision')} != {expected['decision']}")
    exp_pay, got = expected["payable"], answer.get("payable")
    if exp_pay is None:
        if got not in (None, "null"):
            why.append(f"payable {got} but expected none (needs_info)")
    else:
        try:
            if abs(float(got) - exp_pay) > 1:
                why.append(f"payable {got} != {exp_pay}")
        except (TypeError, ValueError):
            why.append(f"payable {got!r} not a number")
    cited = {str(e).replace("‑", "-") for e in answer.get("exclusion_ids") or []}
    for group in expected.get("exclusions_any_of", []):
        if not cited & set(group):
            why.append(f"missing exclusion {'/'.join(group)}")
    return {"pass": not why, "why": "; ".join(why) or "ok"}
