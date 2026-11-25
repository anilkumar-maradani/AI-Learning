"""
policy_register.py: Week 12. The policy administration data the coverage
check runs against: one record per policy, with every term, its dates, the
forms attached, the Coverage A limit and the all-peril deductible.

    data/policies/policies.jsonl   no names, no addresses: a policy number,
                                   a product and terms

Two questions are answered here, and only here:

    lookup_policy(policy_number=..., claim_number=...)
    coverage_in_force(policy_number, loss_date, with_editions=True)

"In force" means: some term has term_start <= loss date <= term_end, and the
term was not cancelled with effect on or before the loss date. Edition
resolution (which wording each attached form had on that date) comes from
editions.py and is only reported when ``with_editions`` is on (the W12 v2
behaviour; v1 did not resolve wording by date).
"""

import json
import os
import re
from functools import lru_cache

from editions import as_date, edition_in_force, window

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REGISTER = os.path.join(ROOT, "data", "policies", "policies.jsonl")
POLICY_RE = re.compile(r"^HOP-\d{7}$")


@lru_cache(maxsize=1)
def _register() -> dict[str, dict]:
    with open(REGISTER, encoding="utf-8") as fh:
        rows = [json.loads(l) for l in fh if l.strip()]
    return {r["policy_number"]: r for r in rows}


def _policy_for_claim(claim_number: str) -> str | None:
    from claim_store import get_claim
    c = get_claim(claim_number)
    return c["policy_number"] if c else None


def lookup_policy(policy_number: str | None = None, claim_number: str | None = None) -> dict:
    """The policy record (product, plan, every term) by policy or claim number."""
    if not policy_number and claim_number:
        policy_number = _policy_for_claim(claim_number.strip().upper())
        if policy_number is None:
            return {"error": f"claim {claim_number} not found, so no policy could be looked up"}
    pn = (policy_number or "").strip().upper()
    if not POLICY_RE.match(pn):
        return {"error": f"'{policy_number}' is not a policy number: they look like HOP-NNNNNNN"}
    rec = _register().get(pn)
    if rec is None:
        return {"error": f"policy {pn} not found in the policy register"}
    return {"policy_number": pn, "product": rec["product"], "plan": rec["plan"],
            "terms": [{k: t[k] for k in ("term_start", "term_end", "status", "cancelled_from",
                                         "cancel_reason", "forms") if k in t}
                      for t in rec["terms"]]}


def coverage_in_force(policy_number: str, loss_date: str, with_editions: bool = True) -> dict:
    pn = (policy_number or "").strip().upper()
    if not POLICY_RE.match(pn):
        return {"error": f"'{policy_number}' is not a policy number: they look like HOP-NNNNNNN"}
    try:
        d = as_date(loss_date)
    except ValueError:
        return {"error": f"'{loss_date}' is not a date: use YYYY-MM-DD"}
    rec = _register().get(pn)
    if rec is None:
        return {"error": f"policy {pn} not found in the policy register"}
    term = next((t for t in rec["terms"]
                 if as_date(t["term_start"]) <= d <= as_date(t["term_end"])), None)
    out = {"policy_number": pn, "loss_date": d.isoformat(), "product": rec["product"]}
    if term is None:
        first = min(as_date(t["term_start"]) for t in rec["terms"])
        last = max(as_date(t["term_end"]) for t in rec["terms"])
        why = (f"loss date is before the policy first incepted on {first.isoformat()}" if d < first
               else f"loss date is after the last term ended on {last.isoformat()}" if d > last
               else "loss date falls in a gap between terms")
        return {**out, "in_force": False, "reason": why, "term": None}
    if term.get("cancelled_from") and as_date(term["cancelled_from"]) <= d:
        return {**out, "in_force": False,
                "reason": (f"term {term['term_start']} to {term['term_end']} was cancelled with effect "
                           f"from {term['cancelled_from']} ({term.get('cancel_reason', 'no reason recorded')})"),
                "term": {"term_start": term["term_start"], "term_end": term["term_end"]}}
    out.update({
        "in_force": True,
        "reason": f"loss date falls in the term {term['term_start']} to {term['term_end']}",
        "term": {"term_start": term["term_start"], "term_end": term["term_end"]},
        "forms": term["forms"],
        "all_peril_deductible": term["all_peril_deductible"],
        "coverage_a_limit": term["coverage_a_limit"],
    })
    if with_editions:
        eds = []
        for f in term["forms"]:
            ed = edition_in_force(f, d)
            eds.append({"form_number": f, "edition": ed["edition_date"] if ed else None,
                        "in_force_window": window(ed) if ed else None,
                        "title": ed["title"] if ed else None,
                        "note": None if ed else f"no edition of {f} in the library was in force on {d.isoformat()}"})
        out["wording_in_force"] = eds
    return out


def expected_numbers(policy_number: str, loss_date: str) -> dict | None:
    """Ground truth for the eval: the term's deductible and Coverage A limit."""
    r = coverage_in_force(policy_number, loss_date, with_editions=False)
    if not r.get("in_force"):
        return None
    return {"all_peril_deductible": r["all_peril_deductible"], "coverage_a_limit": r["coverage_a_limit"]}
