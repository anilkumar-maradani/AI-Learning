"""
tools.py — Three explicit tool definitions for the W7 claims agent.

Each tool wraps an existing capability with a single, non-overlapping job:

  get_claim_details       — retrieve relevant endorsement chunks for a loss
  check_policy_exclusions — look up whether a specific exclusion applies
  compute_payout          — arithmetic: damage minus excess and sublimits

The tool schemas follow the OpenAI function-calling format so they work
directly as the `tools=` argument to client.chat.completions.create().

Executors are Python callables dispatched by dispatch_tool(); they return
plain dicts that are JSON-serialised into tool_result messages.
"""

from __future__ import annotations

import json
import math
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))


# ---------------------------------------------------------------------------
# Tool 1 — get_claim_details
# ---------------------------------------------------------------------------

_GET_CLAIM_DETAILS = {
    "type": "function",
    "function": {
        "name": "get_claim_details",
        "description": (
            "Retrieve the endorsement context and policy wording relevant to a "
            "claim's loss description. Returns ranked endorsement chunks "
            "(form_number, clause_id, text) from the indexed homeowners policy "
            "corpus. Call this first to understand what policy language governs "
            "the loss before attempting any coverage determination."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "claim_number": {
                    "type": "string",
                    "description": "The claim reference number (e.g. CLM-2024-10001).",
                },
                "loss_description": {
                    "type": "string",
                    "description": (
                        "Natural-language summary of the loss event, including "
                        "the form of damage, peril suspected, and any relevant "
                        "dates. Used as the search query."
                    ),
                },
            },
            "required": ["claim_number", "loss_description"],
        },
    },
}


def _exec_get_claim_details(claim_number: str, loss_description: str) -> dict:
    """Hybrid BM25+vector search over the indexed endorsement corpus."""
    try:
        from hybrid_retrieval import hybrid_search
        hits = hybrid_search(loss_description, n_results=5)
    except Exception:
        from retrieval import search as vector_search
        hits = vector_search(loss_description, strategy="structure_aware", n_results=5)

    chunks = [
        {
            "rank": h["rank"],
            "chunk_id": h["chunk_id"],
            "score": round(h["score"], 4),
            "form_number": h["metadata"].get("form_number", "UNKNOWN"),
            "clause_id": h["metadata"].get("clause_id", "N/A"),
            "text": h["text"][:600],  # truncate for token budget
        }
        for h in hits
    ]
    return {
        "claim_number": claim_number,
        "chunks_retrieved": len(chunks),
        "chunks": chunks,
    }


# ---------------------------------------------------------------------------
# Tool 2 — check_policy_exclusions
# ---------------------------------------------------------------------------

_CHECK_POLICY_EXCLUSIONS = {
    "type": "function",
    "function": {
        "name": "check_policy_exclusions",
        "description": (
            "Look up whether a specific exclusion code applies to a given loss "
            "type under a named endorsement form. Returns the exact exclusion "
            "table row text, the coverage determination (COVERED / NOT_COVERED / "
            "PARTIALLY_COVERED), and any conditions or sublimits that attach. "
            "Call this after get_claim_details once you know the form number and "
            "suspect an exclusion code."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "form_number": {
                    "type": "string",
                    "description": (
                        "The endorsement form to search in (e.g. 'HO-0304', "
                        "'HO-0306'). Must be one of the indexed forms."
                    ),
                },
                "exclusion_code": {
                    "type": "string",
                    "description": (
                        "The exclusion table code to look up (e.g. 'E-17', "
                        "'E-11'). Use empty string if you want all exclusions "
                        "for this form returned."
                    ),
                },
                "loss_type": {
                    "type": "string",
                    "description": (
                        "Plain-English description of the loss type being "
                        "assessed (e.g. 'burst supply line', 'mold after pipe "
                        "burst', 'sinkhole'). Used to enrich the search query."
                    ),
                },
            },
            "required": ["form_number", "loss_type"],
        },
    },
}


def _exec_check_policy_exclusions(
    form_number: str, loss_type: str, exclusion_code: str = ""
) -> dict:
    """Targeted hybrid search for the exclusion row, then extract coverage determination."""
    query = f"{form_number} {exclusion_code} {loss_type}".strip()
    try:
        from hybrid_retrieval import hybrid_search
        hits = hybrid_search(query, n_results=5)
    except Exception:
        from retrieval import search as vector_search
        hits = vector_search(query, strategy="structure_aware", n_results=5)

    # Find the most relevant chunk for this exclusion
    relevant = [
        h for h in hits
        if h["metadata"].get("form_number", "") == form_number
    ] or hits  # fall back to all hits if no form match

    best = relevant[0] if relevant else None
    chunk_text = best["text"] if best else ""

    # Heuristic coverage determination from text
    determination = _infer_determination(chunk_text, exclusion_code)

    # Detect any sublimit (dollar cap like $10,000)
    import re
    sublimit_matches = re.findall(r"\$([0-9,]+)\s*(?:sublimit|cap|limit)", chunk_text, re.IGNORECASE)
    sublimit = None
    if sublimit_matches:
        try:
            sublimit = float(sublimit_matches[0].replace(",", ""))
        except ValueError:
            sublimit = None

    return {
        "form_number": form_number,
        "exclusion_code_queried": exclusion_code,
        "loss_type": loss_type,
        "determination": determination,
        "sublimit_usd": sublimit,
        "source_chunk_id": best["chunk_id"] if best else None,
        "source_clause_id": best["metadata"].get("clause_id") if best else None,
        "excerpt": chunk_text[:400],
    }


def _infer_determination(text: str, exclusion_code: str) -> str:
    """Heuristic: parse 'NOT excluded' / 'is covered' vs 'excluded' from chunk text."""
    low = text.lower()
    # E-17 pattern: explicitly says NOT excluded / IS COVERED
    if "not excluded" in low or "is covered" in low or "not withheld" in low:
        return "COVERED"
    # Pattern for coverage confirmation rows
    if "coverage applies" in low or "covered under" in low:
        return "COVERED"
    # Partial coverage (sublimit)
    if "sublimit" in low or "remediation sublimit" in low or "subject to" in low:
        return "PARTIALLY_COVERED"
    # Default exclusion when the exclusion code appears and no coverage language
    if exclusion_code and exclusion_code.lower() in low:
        return "NOT_COVERED"
    # Can't determine without reading the context
    return "DEPENDS_ON_FACTS"


# ---------------------------------------------------------------------------
# Tool 3 — compute_payout  [NEW THIRD TOOL]
# ---------------------------------------------------------------------------

_COMPUTE_PAYOUT = {
    "type": "function",
    "function": {
        "name": "compute_payout",
        "description": (
            "Compute the net payable amount on a claim given the damage estimate, "
            "the applicable deductible (all-peril or named-storm), any "
            "form-specific sublimits (e.g. the $10,000 mold remediation cap under "
            "HO-0306 MF-2), and the coverage determination from the exclusion "
            "lookup. Returns the payable amount, the deductible applied, any "
            "sublimit that capped the payment, and a plain-English explanation. "
            "Call this only after check_policy_exclusions has returned a "
            "determination — never before."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "damage_estimate": {
                    "type": "number",
                    "description": "Total estimated damage amount in US dollars.",
                },
                "deductible_amount": {
                    "type": "number",
                    "description": (
                        "Applicable deductible in US dollars. Use the named-storm "
                        "deductible when a named storm triggered the loss; "
                        "otherwise the all-peril deductible."
                    ),
                },
                "sublimit": {
                    "type": "number",
                    "description": (
                        "Form-specific sublimit in US dollars, if one applies "
                        "(e.g. $10,000 for mold remediation under HO-0306 MF-2). "
                        "Omit or pass null when no sublimit applies."
                    ),
                    "nullable": True,
                },
                "claim_status": {
                    "type": "string",
                    "enum": [
                        "COVERED",
                        "NOT_COVERED",
                        "PARTIALLY_COVERED",
                        "DEPENDS_ON_FACTS",
                    ],
                    "description": (
                        "Coverage determination returned by check_policy_exclusions. "
                        "COVERED: full payment less deductible. "
                        "NOT_COVERED: zero payable. "
                        "PARTIALLY_COVERED: payment capped by sublimit then less deductible. "
                        "DEPENDS_ON_FACTS: cannot compute — adjuster must resolve ambiguity first."
                    ),
                },
            },
            "required": ["damage_estimate", "deductible_amount", "claim_status"],
        },
    },
}


def _exec_compute_payout(
    damage_estimate: float,
    deductible_amount: float,
    claim_status: str,
    sublimit: float | None = None,
) -> dict:
    """Pure arithmetic: no model call, no retrieval, no IO."""
    damage_estimate = float(damage_estimate)
    deductible_amount = float(deductible_amount)
    sublimit = float(sublimit) if sublimit is not None else None

    if claim_status == "NOT_COVERED":
        return {
            "payable_amount": 0.0,
            "deductible_applied": 0.0,
            "sublimit_applied": None,
            "claim_status": claim_status,
            "explanation": (
                f"Loss is NOT COVERED — exclusion applies. "
                f"Damage estimate ${damage_estimate:,.2f} is not payable."
            ),
        }

    if claim_status == "DEPENDS_ON_FACTS":
        return {
            "payable_amount": None,
            "deductible_applied": None,
            "sublimit_applied": None,
            "claim_status": claim_status,
            "explanation": (
                "Coverage is ambiguous. Adjuster must resolve the factual "
                "ambiguity before a payout figure can be computed."
            ),
        }

    # COVERED or PARTIALLY_COVERED
    capped = damage_estimate
    sublimit_applied = None
    if sublimit is not None and damage_estimate > sublimit:
        capped = sublimit
        sublimit_applied = sublimit

    net = max(0.0, capped - deductible_amount)

    parts = []
    if sublimit_applied:
        parts.append(f"damage ${damage_estimate:,.2f} capped at ${sublimit_applied:,.2f} sublimit")
    else:
        parts.append(f"damage ${damage_estimate:,.2f}")
    parts.append(f"deductible ${deductible_amount:,.2f} applied")
    parts.append(f"net payable ${net:,.2f}")

    return {
        "payable_amount": round(net, 2),
        "deductible_applied": round(deductible_amount, 2),
        "sublimit_applied": round(sublimit_applied, 2) if sublimit_applied else None,
        "claim_status": claim_status,
        "explanation": "; ".join(parts) + ".",
    }


# ---------------------------------------------------------------------------
# Public registry
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    _GET_CLAIM_DETAILS,
    _CHECK_POLICY_EXCLUSIONS,
    _COMPUTE_PAYOUT,
]

_EXECUTORS: dict[str, Any] = {
    "get_claim_details": _exec_get_claim_details,
    "check_policy_exclusions": _exec_check_policy_exclusions,
    "compute_payout": _exec_compute_payout,
}


def dispatch_tool(name: str, arguments: str | dict) -> dict:
    """
    Call the named tool executor with the arguments the model supplied.

    ``arguments`` may arrive as a JSON string (from the API) or a dict
    (from unit tests). Always returns a plain dict that can be
    JSON-serialised into a tool_result message.
    """
    if name not in _EXECUTORS:
        return {"error": f"Unknown tool: {name!r}. Available: {sorted(_EXECUTORS)}"}

    if isinstance(arguments, str):
        try:
            kwargs = json.loads(arguments)
        except json.JSONDecodeError as exc:
            return {"error": f"Could not parse tool arguments as JSON: {exc}"}
    else:
        kwargs = arguments

    try:
        return _EXECUTORS[name](**kwargs)
    except TypeError as exc:
        return {"error": f"Tool call failed (bad arguments): {exc}"}
    except Exception as exc:
        return {"error": f"Tool execution error: {type(exc).__name__}: {exc}"}
