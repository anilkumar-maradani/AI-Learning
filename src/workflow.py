"""
workflow.py — Fixed 4-step workflow for insurance claim triage.

Same tools, same model, same output contract as the agent loop —
but with NO loop: the four steps are hard-coded in order.

Step 1: get_claim_details      — retrieve governing endorsement chunks
Step 2: check_policy_exclusions — determine coverage (exclusion lookup)
Step 3: compute_payout          — arithmetic: damage minus excess/sublimit
Step 4: call_model              — final answer from all accumulated context

The point of having both systems is the race in week7/run_race.py:
the workflow establishes the baseline that the agent must beat (or fail to beat)
on pass rate, p50 latency, total tokens, and cost per claim.
"""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))

import prompts
from tools import dispatch_tool
from redaction import redact_text
from tracing import TraceWriter, TraceRecord


def fixed_workflow(
    claim: dict,
    writer: TraceWriter | None = None,
    model_params: dict | None = None,
    verbose: bool = False,
) -> dict:
    """
    Hard-coded 4-step triage workflow. Same tools and model as agent_loop;
    no loop of any kind.

    ``claim`` keys: question, loss_summary, claimant_name, claim_number,
    damage_estimate, deductible_amount, and optionally form_number, channel, tags.

    Returns a result dict with keys:
        trace_id, final_answer, total_tokens, total_cost_usd, wall_clock_s,
        step_results, error
    """
    from generation import call_model_with_tools, estimate_cost, get_model

    _DEFAULT_MODEL = {
        "temperature": 0.0,
        "max_tokens": 800,
        "top_p": 1.0,
        "seed": None,
    }
    model_params = {**_DEFAULT_MODEL, **(model_params or {})}
    writer = writer or TraceWriter(
        path=os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
            "traces", "workflow_traces.jsonl",
        )
    )

    # ── PII redaction ──────────────────────────────────────────────────────
    claimant_name = claim.get("claimant_name", "")
    claim_number = claim.get("claim_number", "")
    question = claim["question"]
    loss_summary = claim.get("loss_summary", "")
    damage_estimate = float(claim.get("damage_estimate", 0.0))
    deductible_amount = float(claim.get("deductible_amount", 0.0))
    hint_form = claim.get("form_number", "")

    claim_ref_red, _ = redact_text(claim_number, [claimant_name])
    loss_red, _ = redact_text(loss_summary, [claimant_name])
    question_red, _ = redact_text(question, [claimant_name])

    total_tokens = 0
    total_cost = 0.0
    t0 = time.perf_counter()
    step_results: dict[str, dict] = {}
    last_error: dict | None = None

    # ── STEP 1: Retrieve endorsement context ───────────────────────────────
    step1 = dispatch_tool(
        "get_claim_details",
        {"claim_number": claim_ref_red, "loss_description": loss_red},
    )
    step_results["step1_get_claim_details"] = step1
    if verbose:
        print(f"  [WF step1] retrieved {step1.get('chunks_retrieved', 0)} chunks")

    # ── STEP 2: Check policy exclusions ───────────────────────────────────
    # Derive the best form number from step 1 results or the claim hint
    form_number = hint_form or _extract_top_form(step1)
    loss_type = _infer_loss_type(loss_summary)

    step2 = dispatch_tool(
        "check_policy_exclusions",
        {
            "form_number": form_number,
            "exclusion_code": "",        # let the tool find the most relevant
            "loss_type": loss_type,
        },
    )
    step_results["step2_check_exclusions"] = step2
    if verbose:
        print(f"  [WF step2] determination={step2.get('determination')} "
              f"clause={step2.get('source_clause_id')}")

    # ── STEP 3: Compute payout — depends on step 2's determination ─────────
    # This is the genuine data dependency: step 3 gets its claim_status from
    # step 2's output; it never runs independently.
    determination = step2.get("determination", "DEPENDS_ON_FACTS")
    sublimit = step2.get("sublimit_usd")  # may be None

    step3 = dispatch_tool(
        "compute_payout",
        {
            "damage_estimate": damage_estimate,
            "deductible_amount": deductible_amount,
            "sublimit": sublimit,
            "claim_status": determination,
        },
    )
    step_results["step3_compute_payout"] = step3
    if verbose:
        print(f"  [WF step3] payable=${step3.get('payable_amount')} "
              f"({step3.get('claim_status')})")

    # ── STEP 4: Final model call — synthesise all context into an answer ───
    context_block = _build_context_block(step1, step2, step3)
    system_msg = {"role": "system", "content": prompts.get_system_prompt("claims-v1")}
    user_msg = {
        "role": "user",
        "content": (
            f"CLAIM FILE: {claim_ref_red}\n"
            f"LOSS SUMMARY: {loss_red}\n\n"
            f"WORKFLOW RESULTS:\n{context_block}\n\n"
            f"QUESTION: {question_red}\n\n"
            "Using the workflow results above as your authoritative context, "
            "give the coverage position (COVERED / NOT COVERED / PARTIALLY COVERED), "
            "cite the relevant clause and exclusion code, and state the net payable amount."
        ),
    }

    # Single model call — no tools attached; the model synthesises from context
    from generation import get_client
    client = get_client()
    try:
        resp_raw = client.chat.completions.create(
            model=model_params.get("name") or get_model(),
            messages=[system_msg, user_msg],
            temperature=model_params["temperature"],
            max_tokens=model_params["max_tokens"],
        )
        choice = resp_raw.choices[0]
        usage = getattr(resp_raw, "usage", None)
        usage_dict = {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0),
            "completion_tokens": getattr(usage, "completion_tokens", 0),
        } if usage else None

        if usage_dict:
            total_tokens += (usage_dict["prompt_tokens"] + usage_dict["completion_tokens"])
            total_cost += estimate_cost(usage_dict)

        final_answer = (choice.message.content or "").strip()
        finish_reason = choice.finish_reason
    except Exception as exc:
        final_answer = ""
        finish_reason = "error"
        last_error = {"type": type(exc).__name__, "message": str(exc)[:400]}
        usage_dict = None
        if verbose:
            print(f"  [WF step4] model error: {exc}")

    wall_clock_s = round(time.perf_counter() - t0, 3)

    if verbose:
        print(f"  [WF done] {wall_clock_s:.2f}s {total_tokens} tok "
              f"${total_cost:.4f}: {final_answer[:80]}")

    # ── Write trace ────────────────────────────────────────────────────────
    record = TraceRecord.build(
        question=question,
        loss_summary=loss_summary,
        claimant_name=claimant_name,
        claim_number=claim_number,
        prompt_version="claims-v1",
        retrieval_meta={"mode": "fixed_workflow", "n_results": 5},
        hits=[],
        model_meta={
            "provider": "groq",
            "name": model_params.get("name") or get_model(),
            "temperature": model_params["temperature"],
            "max_tokens": model_params["max_tokens"],
            "top_p": model_params["top_p"],
            "seed": model_params.get("seed"),
            "finish_reason": finish_reason,
            "usage": usage_dict,
            "system_fingerprint": None,
        },
        raw_output=final_answer,
        timing={
            "retrieval_ms": 0,
            "generation_ms": round(wall_clock_s * 1000, 1),
            "total_ms": round(wall_clock_s * 1000, 1),
        },
        error=last_error,
        tags=claim.get("tags", []),
        channel=claim.get("channel", "fixed_workflow"),
    )

    record.agent_meta = {
        "mode": "fixed_workflow",
        "iterations": 4,       # always exactly 4 steps
        "tool_calls": [
            {"step": 1, "tool": "get_claim_details",      "result_summary": f"{step1.get('chunks_retrieved',0)} chunks"},
            {"step": 2, "tool": "check_policy_exclusions", "result_summary": f"determination={determination}"},
            {"step": 3, "tool": "compute_payout",          "result_summary": f"payable=${step3.get('payable_amount')}"},
            {"step": 4, "tool": "call_model",              "result_summary": f"final answer ({len(final_answer)} chars)"},
        ],
        "budget_terminated": False,
        "budget_trigger": None,
        "budgets": None,
        "total_tokens_all_iterations": total_tokens,
        "total_cost_usd": round(total_cost, 6),
    }

    writer.write(record, known_names=[claimant_name] if claimant_name else None)

    return {
        "trace_id": record.trace_id,
        "final_answer": final_answer,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "wall_clock_s": wall_clock_s,
        "step_results": step_results,
        "error": last_error,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_top_form(step1_result: dict) -> str:
    """Best-guess form number from step 1 chunks."""
    chunks = step1_result.get("chunks", [])
    if chunks:
        return chunks[0].get("form_number", "HO-0304")
    return "HO-0304"


def _infer_loss_type(loss_summary: str) -> str:
    """Simple keyword-based loss-type label for the exclusion lookup query."""
    low = loss_summary.lower()
    if any(w in low for w in ("mold", "mould", "fungus", "remediation")):
        return "mold remediation"
    if any(w in low for w in ("supply line", "pipe burst", "plumbing", "sprinkler", "dishwasher")):
        return "water damage supply line"
    if any(w in low for w in ("hurricane", "named storm", "tropical", "wind damage")):
        return "named storm wind damage"
    if any(w in low for w in ("sinkhole", "earthquake", "subsidence", "earth movement", "mudslide")):
        return "earth movement"
    if any(w in low for w in ("business", "client", "office", "day care")):
        return "business pursuits"
    if any(w in low for w in ("scheduled", "jewelry", "ring", "watch")):
        return "scheduled personal property"
    return "water damage"


def _build_context_block(step1: dict, step2: dict, step3: dict) -> str:
    """Format workflow results for the final model call."""
    lines = [
        "=== STEP 1: Endorsement Chunks Retrieved ===",
    ]
    for chunk in step1.get("chunks", [])[:3]:
        lines.append(
            f"[{chunk.get('form_number')} / {chunk.get('clause_id')}] "
            f"(score={chunk.get('score'):.4f})\n{chunk.get('text','')[:300]}"
        )
    lines += [
        "",
        "=== STEP 2: Exclusion Check ===",
        f"Form: {step2.get('form_number')}",
        f"Loss type: {step2.get('loss_type')}",
        f"Determination: {step2.get('determination')}",
        f"Sublimit: ${step2.get('sublimit_usd'):,.2f}" if step2.get("sublimit_usd") else "Sublimit: None",
        f"Source clause: {step2.get('source_clause_id')}",
        f"Excerpt: {step2.get('excerpt','')[:200]}",
        "",
        "=== STEP 3: Payout Computation ===",
        f"Damage estimate: ${step3.get('payable_amount', 'N/A')}",
        step3.get("explanation", ""),
    ]
    return "\n".join(lines)
