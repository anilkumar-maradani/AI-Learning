"""
tools.py — The claims agent's tools. Each description names one job and says
what the tool does NOT do, so no two descriptions overlap.

  get_claim       the claim file: policy terms, estimate lines, adjuster notes
  search_policy   endorsement wording: clauses and exclusion rows
  compute_payout  (Week 7 addition) arithmetic only: covered amount -> payable

The first two existed before Week 7 as get_claim_details / check_policy_exclusions,
and BOTH searched the policy corpus. That overlap is what reports/week7/tool_diff.md
shows being removed. The deductible is read from the claim file by the tool, never
taken from the model, so a model cannot invent a deductible.
"""

import json
import re

from claim_store import CLAIM_NUMBER_RE, get_claim as _load_claim

FORM_RE = re.compile(r"^NG-\d{4}$")

GET_CLAIM = {
    "type": "function",
    "function": {
        "name": "get_claim",
        "description": (
            "Return one claim file from the claims system: the policy it is written on "
            "(forms attached, Coverage A limit, all-peril deductible, scheduled articles), "
            "the first notice of loss, the estimate lines and every dated adjuster note. "
            "This is the only source of facts about the loss. It does not contain any "
            "policy wording."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "claim_number": {
                    "type": "string",
                    "pattern": "^CLM-\\d{4}-\\d{5}$",
                    "description": "Claim number exactly as given, e.g. CLM-2026-20101.",
                }
            },
            "required": ["claim_number"],
            "additionalProperties": False,
        },
    },
}

SEARCH_POLICY = {
    "type": "function",
    "function": {
        "name": "search_policy",
        "description": (
            "Read endorsement wording (coverage clauses, exclusion table rows, deductible "
            "and sublimit rules). With form_number, returns that form's COMPLETE wording: "
            "every clause and its whole exclusion table, so one call per form is enough "
            "and repeating it returns nothing new. Without form_number, returns the best "
            "matching passages across all forms for the query. It knows nothing about "
            "any particular claim."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The peril, cause or rule to look up, e.g. 'water from a pipe broken by ground movement'.",
                },
                "form_number": {
                    "type": "string",
                    "pattern": "^NG-\\d{4}$",
                    "description": "Optional. Restrict to one form attached to the policy, e.g. NG-1105.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

CLAIM_STATUS = ["covered", "covered_subject_to_sublimit", "excluded"]

COMPUTE_PAYOUT = {
    "type": "function",
    "function": {
        "name": "compute_payout",
        "description": (
            "Arithmetic only: turn a coverage decision you have already made into the "
            "amount payable. Applies the deductible from the claim file (or the hurricane "
            "deductible, or none for scheduled articles), then any sublimit. It does not "
            "look up policy wording and does not decide coverage."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "claim_number": {"type": "string", "pattern": "^CLM-\\d{4}-\\d{5}$"},
                "claim_status": {
                    "type": "string",
                    "enum": CLAIM_STATUS,
                    "description": "Your coverage decision for the covered portion of the loss.",
                },
                "covered_amount": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Sum of the estimate lines you decided are covered, before any deductible.",
                },
                "deductible_basis": {
                    "type": "string",
                    "enum": ["all_peril", "hurricane", "none_scheduled_article"],
                    "description": "Which deductible the policy wording says applies.",
                },
                "sublimit": {
                    "type": "number",
                    "minimum": 0,
                    "description": "Required only when claim_status is covered_subject_to_sublimit.",
                },
            },
            "required": ["claim_number", "claim_status", "covered_amount", "deductible_basis"],
            "additionalProperties": False,
        },
    },
}

TOOLS = [GET_CLAIM, SEARCH_POLICY, COMPUTE_PAYOUT]


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def get_claim(claim_number: str) -> dict:
    if not CLAIM_NUMBER_RE.match(claim_number or ""):
        return {"error": f"'{claim_number}' is not a claim number (expected CLM-YYYY-NNNNN)"}
    claim = _load_claim(claim_number)
    if claim is None:
        return {"error": f"No claim {claim_number} in the claims system"}
    return {k: v for k, v in claim.items() if k != "claimant_name"}


def search_policy(query: str, form_number: str | None = None, n_results: int = 4) -> dict:
    from hybrid_retrieval import hybrid_search
    if form_number and not FORM_RE.match(form_number):
        return {"error": f"'{form_number}' is not a form number (expected NG-NNNN)"}
    if form_number:
        # Week 8 mitigation: the whole form, in document order, minus header chunks.
        # Before, 4 ranked slots were often spent on PREAMBLE chunks and the agent
        # re-searched the same form to find the clause it still needed.
        from hybrid_retrieval import _get_bm25_index
        hits = sorted(
            (c for c in _get_bm25_index().chunks
             if c["metadata"].get("form_number") == form_number
             and c["metadata"].get("clause_id") != "PREAMBLE"),
            key=lambda c: c["metadata"]["chunk_index"],
        )
        if not hits:
            return {"error": f"No form {form_number} in the policy library"}
    else:
        hits = hybrid_search(query, n_results=n_results)
    return {
        "passages": [
            {
                "chunk_id": h["chunk_id"],
                "form_number": h["metadata"].get("form_number"),
                "clause_id": h["metadata"].get("clause_id"),
                "text": h["text"].split("\n", 1)[-1][:900],
            }
            for h in hits
        ]
    }


def compute_payout(claim_number: str, claim_status: str, covered_amount: float,
                   deductible_basis: str, sublimit: float | None = None) -> dict:
    claim = _load_claim(claim_number) if CLAIM_NUMBER_RE.match(claim_number or "") else None
    if claim is None:
        return {"error": f"No claim {claim_number} in the claims system"}
    if claim_status not in CLAIM_STATUS:
        return {"error": f"claim_status must be one of {CLAIM_STATUS}"}
    if claim_status == "excluded":
        return {"payable": 0.0, "working": "excluded: nothing payable"}
    if claim_status == "covered_subject_to_sublimit" and sublimit is None:
        return {"error": "sublimit is required when claim_status is covered_subject_to_sublimit"}
    deductible = {
        "all_peril": float(claim["all_peril_deductible"]),
        "hurricane": round(0.02 * claim["coverage_a_limit"], 2),
        "none_scheduled_article": 0.0,
    }.get(deductible_basis)
    if deductible is None:
        return {"error": "unknown deductible_basis"}
    net = max(0.0, float(covered_amount) - deductible)
    working = f"{covered_amount:,.2f} - deductible {deductible:,.2f} = {net:,.2f}"
    if claim_status == "covered_subject_to_sublimit" and net > sublimit:
        net = float(sublimit)
        working += f", capped at sublimit {sublimit:,.2f}"
    return {"payable": round(net, 2), "deductible_applied": deductible, "working": working}


_EXECUTORS = {"get_claim": get_claim, "search_policy": search_policy,
              "compute_payout": compute_payout}


def dispatch(name: str, arguments: str | dict) -> dict:
    if name not in _EXECUTORS:
        return {"error": f"unknown tool {name!r}"}
    try:
        kwargs = json.loads(arguments) if isinstance(arguments, str) else dict(arguments)
    except json.JSONDecodeError as exc:
        return {"error": f"arguments are not valid JSON: {exc}"}
    try:
        return _EXECUTORS[name](**kwargs)
    except TypeError as exc:
        return {"error": f"bad arguments: {exc}"}
