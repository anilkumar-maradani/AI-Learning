"""
claims_agent.py — The claims assistant, instrumented.

One call per adjuster question:

    retrieve (hybrid BM25 + vector + RRF)  ->  generate (Groq)  ->  write trace

The function returns the trace record rather than a pretty answer, because for
this week the trace *is* the product. Every parameter that influences the output
is captured on the way past: retrieval mode and candidate counts, each chunk's
id / rank / score / form / edition, the prompt version, the model and its
sampling parameters, and the untouched raw completion.

Failure is traced too. A provider error produces a trace with ``error`` set and
an empty output rather than no trace at all — a log that only records successes
would understate exactly the failure modes error analysis is looking for.
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
import prompts
from tracing import TraceRecord, TraceWriter

DEFAULT_RETRIEVAL = {
    "mode": "hybrid_rrf",
    "strategy": "structure_aware",
    "n_results": 5,
    "bm25_candidates": 25,
    "vector_candidates": 25,
    "rrf_k": 60,
}

DEFAULT_MODEL_PARAMS = {
    "temperature": 0.0,
    "max_tokens": 800,
    "top_p": 1.0,
    "seed": None,
}


def build_user_message(
    prompt_version: str,
    context: str,
    claim_ref: str,
    loss_summary: str,
    question: str,
) -> str:
    """Single source of truth for the user turn — used live AND by replay."""
    return prompts.get_user_template(prompt_version).format(
        context=context,
        claim_ref=claim_ref,
        loss_summary=loss_summary,
        question=question,
    )


def retrieve(question: str, retrieval_cfg: dict) -> list[dict]:
    from hybrid_retrieval import hybrid_search
    from retrieval import search as vector_search

    if retrieval_cfg["mode"] == "hybrid_rrf":
        return hybrid_search(
            question,
            n_results=retrieval_cfg["n_results"],
            bm25_candidates=retrieval_cfg["bm25_candidates"],
            vector_candidates=retrieval_cfg["vector_candidates"],
        )
    return vector_search(
        question,
        strategy=retrieval_cfg["strategy"],
        n_results=retrieval_cfg["n_results"],
    )


_WAIT_RE = re.compile(r"try again in\s+(?:(\d+)m)?([\d.]+)s", re.IGNORECASE)


def _suggested_wait(message: str) -> float | None:
    """Seconds the provider asked us to wait, parsed out of a 429 body."""
    m = _WAIT_RE.search(message)
    if not m:
        return None
    minutes = float(m.group(1) or 0)
    seconds = float(m.group(2))
    return minutes * 60 + seconds + 2  # small cushion


def call_model(
    system_prompt: str,
    user_message: str,
    model_params: dict,
    max_wait_s: float = 300.0,
) -> dict:
    """Returns raw text plus provider metadata. Retries transient 429/5xx."""
    from generation import get_client, get_model

    client = get_client()
    model_name = model_params.get("name") or get_model()
    kwargs = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": model_params["temperature"],
        "max_tokens": model_params["max_tokens"],
        "top_p": model_params["top_p"],
    }
    if model_params.get("seed") is not None:
        kwargs["seed"] = model_params["seed"]

    last_exc = None
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(**kwargs)
            choice = resp.choices[0]
            usage = getattr(resp, "usage", None)
            return {
                "raw": (choice.message.content or "").strip(),
                "finish_reason": choice.finish_reason,
                "usage": {
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                } if usage else None,
                "system_fingerprint": getattr(resp, "system_fingerprint", None),
                "error": None,
            }
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            transient = any(s in msg for s in ("429", "500", "502", "503", "timeout", "Timeout"))
            if attempt < 3 and transient:
                # Groq states the wait explicitly on a quota 429
                # ("Please try again in 3m56.736s"). Honour it rather than
                # burning the remaining attempts on a fixed short backoff.
                time.sleep(min(_suggested_wait(msg) or 3 * (attempt + 1), max_wait_s))
                continue
            break

    return {
        "raw": "",
        "finish_reason": "error",
        "usage": None,
        "system_fingerprint": None,
        "error": {"type": type(last_exc).__name__, "message": str(last_exc)[:400]},
    }


def answer_claim_question(
    claim: dict,
    writer: TraceWriter | None = None,
    prompt_version: str = prompts.CURRENT_VERSION,
    retrieval_cfg: dict | None = None,
    model_params: dict | None = None,
    verbose: bool = False,
) -> TraceRecord:
    """
    ``claim`` keys: question, loss_summary, claimant_name, claim_number,
    and optionally channel / tags.
    """
    from generation import format_context, get_model

    retrieval_cfg = {**DEFAULT_RETRIEVAL, **(retrieval_cfg or {})}
    model_params = {**DEFAULT_MODEL_PARAMS, **(model_params or {})}
    writer = writer or TraceWriter()

    question = claim["question"]
    loss_summary = claim.get("loss_summary", "")
    claimant_name = claim.get("claimant_name", "")
    claim_number = claim.get("claim_number", "")

    t0 = time.perf_counter()
    hits = retrieve(question, retrieval_cfg)
    t1 = time.perf_counter()

    # The claim reference sent to the model is already pseudonymised: the raw
    # claim number never leaves the process, not even to the provider.
    from redaction import redact_text
    claim_ref_for_prompt, _ = redact_text(claim_number, [claimant_name])
    loss_for_prompt, _ = redact_text(loss_summary, [claimant_name])
    question_for_prompt, _ = redact_text(question, [claimant_name])

    user_message = build_user_message(
        prompt_version,
        format_context(hits),
        claim_ref_for_prompt,
        loss_for_prompt,
        question_for_prompt,
    )
    result = call_model(
        prompts.get_system_prompt(prompt_version), user_message, model_params
    )
    t2 = time.perf_counter()

    record = TraceRecord.build(
        question=question,
        loss_summary=loss_summary,
        claimant_name=claimant_name,
        claim_number=claim_number,
        prompt_version=prompt_version,
        retrieval_meta={k: v for k, v in retrieval_cfg.items()},
        hits=hits,
        model_meta={
            "provider": "groq",
            "name": model_params.get("name") or get_model(),
            "temperature": model_params["temperature"],
            "max_tokens": model_params["max_tokens"],
            "top_p": model_params["top_p"],
            "seed": model_params.get("seed"),
            "finish_reason": result["finish_reason"],
            "usage": result["usage"],
            "system_fingerprint": result["system_fingerprint"],
        },
        raw_output=result["raw"],
        timing={
            "retrieval_ms": round((t1 - t0) * 1000, 1),
            "generation_ms": round((t2 - t1) * 1000, 1),
            "total_ms": round((t2 - t0) * 1000, 1),
        },
        error=result["error"],
        tags=claim.get("tags", []),
        channel=claim.get("channel", "adjuster_console"),
    )
    writer.write(record, known_names=[claimant_name] if claimant_name else None)

    if verbose:
        print(f"[{record.trace_id}] {record.input['question'][:80]}")
        print(f"    -> {record.output['raw'][:160]}\n")

    return record


# ---------------------------------------------------------------------------
# Week 7 — Agent loop with explicit tool-calling and budget enforcement
# ---------------------------------------------------------------------------

# Budget defaults — all four are enforced in the loop, not just declared.
DEFAULT_BUDGETS = {
    "max_iterations": 8,        # hard loop cap
    "max_tokens": 15_000,       # summed across ALL iterations
    "max_cost_usd": 0.05,       # total USD per claim
    "max_wall_clock_s": 60.0,   # wall-clock per claim
}


def agent_loop(
    claim: dict,
    writer: "TraceWriter | None" = None,
    prompt_version: str = prompts.AGENT_VERSION,
    model_params: dict | None = None,
    budgets: dict | None = None,
    verbose: bool = False,
) -> dict:
    """
    Agentic triage loop for a single claim.

    The model decides which tools to call at each iteration.  Four budgets
    are enforced at the TOP of every loop — not just declared as constants.
    Token counts are summed across all iterations (the message list grows
    each lap, so per-call tokens understate the true cost).

    ``claim`` keys: question, loss_summary, claimant_name, claim_number,
    damage_estimate, deductible_amount, and optionally channel / tags.

    Returns a result dict with keys:
        trace_id, final_answer, iterations, total_tokens, total_cost_usd,
        wall_clock_s, budget_terminated, budget_trigger, tool_call_log,
        error
    """
    import json as _json
    from generation import call_model_with_tools, estimate_cost, get_model
    from tools import TOOLS, dispatch_tool
    from redaction import redact_text
    from tracing import TraceWriter, TraceRecord

    budgets = {**DEFAULT_BUDGETS, **(budgets or {})}
    model_params = {**DEFAULT_MODEL_PARAMS, **(model_params or {})}
    writer = writer or TraceWriter()

    # ── PII redaction before anything leaves the process ──────────────────
    claimant_name = claim.get("claimant_name", "")
    claim_number = claim.get("claim_number", "")
    question = claim["question"]
    loss_summary = claim.get("loss_summary", "")
    damage_estimate = claim.get("damage_estimate", 0.0)
    deductible_amount = claim.get("deductible_amount", 0.0)

    claim_ref_red, _ = redact_text(claim_number, [claimant_name])
    loss_red, _ = redact_text(loss_summary, [claimant_name])
    question_red, _ = redact_text(question, [claimant_name])

    system_msg = {"role": "system", "content": prompts.get_system_prompt(prompt_version)}
    user_text = prompts.get_user_template(prompt_version).format(
        claim_ref=claim_ref_red,
        loss_summary=loss_red,
        question=question_red,
        damage_estimate=f"{damage_estimate:,.2f}",
        deductible_amount=f"{deductible_amount:,.2f}",
    )
    user_msg = {"role": "user", "content": user_text}
    messages = [system_msg, user_msg]

    # ── Loop state ─────────────────────────────────────────────────────────
    total_tokens = 0
    total_cost = 0.0
    t0 = time.perf_counter()
    tool_call_log: list[dict] = []
    final_answer: str | None = None
    budget_terminated = False
    budget_trigger: str | None = None
    last_error: dict | None = None
    iteration = 0
    # Anti-thrash: track consecutive calls to the same tool
    _last_tool_called: str | None = None
    _consecutive_same_tool: int = 0
    _THRASH_THRESHOLD = 2   # inject hint after this many repeated calls

    for iteration in range(budgets["max_iterations"] + 1):
        # ── ALL FOUR BUDGET CHECKS at top of every iteration ──────────────
        elapsed = time.perf_counter() - t0

        if iteration >= budgets["max_iterations"]:
            budget_terminated = True
            budget_trigger = "max_iterations"
            final_answer = (
                f"[BUDGET: max_iterations={budgets['max_iterations']} reached "
                f"after {iteration} iterations — terminated cleanly]"
            )
            if verbose:
                print(f"  BUDGET FIRED: max_iterations={budgets['max_iterations']}")
            break

        if total_tokens >= budgets["max_tokens"]:
            budget_terminated = True
            budget_trigger = "max_tokens"
            final_answer = (
                f"[BUDGET: max_tokens={budgets['max_tokens']} reached "
                f"(used {total_tokens}) — terminated cleanly]"
            )
            if verbose:
                print(f"  BUDGET FIRED: max_tokens, used={total_tokens}")
            break

        if total_cost >= budgets["max_cost_usd"]:
            budget_terminated = True
            budget_trigger = "max_cost"
            final_answer = (
                f"[BUDGET: max_cost_usd=${budgets['max_cost_usd']:.4f} reached "
                f"(used ${total_cost:.4f}) — terminated cleanly]"
            )
            if verbose:
                print(f"  BUDGET FIRED: max_cost, used=${total_cost:.4f}")
            break

        if elapsed >= budgets["max_wall_clock_s"]:
            budget_terminated = True
            budget_trigger = "wall_clock"
            final_answer = (
                f"[BUDGET: max_wall_clock_s={budgets['max_wall_clock_s']:.1f}s reached "
                f"(elapsed {elapsed:.1f}s) — terminated cleanly]"
            )
            if verbose:
                print(f"  BUDGET FIRED: wall_clock, elapsed={elapsed:.1f}s")
            break

        # ── Model call with tools ──────────────────────────────────────────
        resp = call_model_with_tools(messages, TOOLS, model_params)

        if resp["error"]:
            last_error = resp["error"]
            if verbose:
                print(f"  Iteration {iteration}: model error: {resp['error']}")
            break

        # Accumulate tokens across ALL iterations (not just the last call)
        if resp["usage"]:
            total_tokens += (
                (resp["usage"].get("prompt_tokens") or 0)
                + (resp["usage"].get("completion_tokens") or 0)
            )
            total_cost += estimate_cost(resp["usage"])

        if verbose:
            tc_names = [tc["name"] for tc in (resp["tool_calls"] or [])]
            print(f"  Iter {iteration}: finish={resp['finish_reason']} "
                  f"tools={tc_names or 'none'} "
                  f"tokens_so_far={total_tokens}")

        # ── No tool calls → model delivered final answer ───────────────────
        if not resp["tool_calls"]:
            final_answer = resp["content"] or ""
            break

        # ── Anti-thrash: detect repeated same-tool calls ────────────────────
        called_tools = [tc["name"] for tc in resp["tool_calls"]]
        first_tool = called_tools[0] if called_tools else None
        if first_tool == _last_tool_called:
            _consecutive_same_tool += 1
        else:
            _consecutive_same_tool = 0
        _last_tool_called = first_tool

        if _consecutive_same_tool >= _THRASH_THRESHOLD:
            # Inject a system hint to push the model to the next tool
            # This is state-driven (not a static prompt hack) — we know which
            # tool was just called and tell the model what to do next.
            _tool_order = ["get_claim_details", "check_policy_exclusions", "compute_payout"]
            try:
                _next_tool = _tool_order[_tool_order.index(first_tool) + 1]
            except (ValueError, IndexError):
                _next_tool = "compute_payout"
            hint = (
                f"SYSTEM: You have called {first_tool} {_consecutive_same_tool + 1} times. "
                f"You now have sufficient context. "
                f"Your next call MUST be {_next_tool}, then deliver your final answer."
            )
            messages.append({"role": "user", "content": hint})
            _consecutive_same_tool = 0  # reset after injecting hint
            if verbose:
                print(f"  [anti-thrash] hint injected -> next tool should be {_next_tool}")

        # ── Append assistant message with tool_calls ───────────────────────
        # Build the assistant message in the format the API expects
        asst_msg: dict = {
            "role": "assistant",
            "content": resp["content"] or "",
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in resp["tool_calls"]
            ],
        }
        messages.append(asst_msg)

        # ── Execute each tool call and append result ───────────────────────
        for tc in resp["tool_calls"]:
            result = dispatch_tool(tc["name"], tc["arguments"])
            tool_call_log.append({
                "iteration": iteration,
                "tool": tc["name"],
                "args": tc["arguments"],
                "result_summary": _summarise_tool_result(tc["name"], result),
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": _json.dumps(result, ensure_ascii=False),
            })

    wall_clock_s = round(time.perf_counter() - t0, 3)

    # ── Build and write trace ──────────────────────────────────────────────
    # Retrieve hits from tool_call_log for TraceRecord (first get_claim_details call)
    hits: list[dict] = []
    for entry in tool_call_log:
        if entry["tool"] == "get_claim_details":
            # parse the stored result summary — hits list not readily available here,
            # so we pass an empty list and rely on agent_meta for the tool call log
            break

    record = TraceRecord.build(
        question=question,
        loss_summary=loss_summary,
        claimant_name=claimant_name,
        claim_number=claim_number,
        prompt_version=prompt_version,
        retrieval_meta={"mode": "agent_tool_call", "n_results": 5},
        hits=hits,
        model_meta={
            "provider": "groq",
            "name": model_params.get("name") or get_model(),
            "temperature": model_params["temperature"],
            "max_tokens": model_params["max_tokens"],
            "top_p": model_params["top_p"],
            "seed": model_params.get("seed"),
            "finish_reason": "agent_loop",
            "usage": {"prompt_tokens": total_tokens, "completion_tokens": 0},
            "system_fingerprint": None,
        },
        raw_output=final_answer or "",
        timing={
            "retrieval_ms": 0,
            "generation_ms": round(wall_clock_s * 1000, 1),
            "total_ms": round(wall_clock_s * 1000, 1),
        },
        error=last_error,
        tags=claim.get("tags", []),
        channel=claim.get("channel", "agent_loop"),
    )

    # Attach agent_meta (extends the base schema, backward-compatible)
    record.agent_meta = {
        "mode": "agent_loop",
        "iterations": iteration + 1 if not budget_terminated else iteration,
        "tool_calls": tool_call_log,
        "budget_terminated": budget_terminated,
        "budget_trigger": budget_trigger,
        "budgets": budgets,
        "total_tokens_all_iterations": total_tokens,
        "total_cost_usd": round(total_cost, 6),
    }

    writer.write(record, known_names=[claimant_name] if claimant_name else None)

    if verbose:
        print(f"  [{record.trace_id}] done — {iteration+1} iter, "
              f"{total_tokens} tok, ${total_cost:.4f}, {wall_clock_s:.2f}s")

    return {
        "trace_id": record.trace_id,
        "final_answer": final_answer or "",
        "iterations": record.agent_meta["iterations"],
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "wall_clock_s": wall_clock_s,
        "budget_terminated": budget_terminated,
        "budget_trigger": budget_trigger,
        "tool_call_log": tool_call_log,
        "error": last_error,
    }


def _summarise_tool_result(tool_name: str, result: dict) -> str:
    """One-line human-readable summary for the trace log."""
    if result.get("error"):
        return f"ERROR: {result['error']}"
    if tool_name == "get_claim_details":
        return f"{result.get('chunks_retrieved', 0)} chunks retrieved"
    if tool_name == "check_policy_exclusions":
        return (
            f"determination={result.get('determination')} "
            f"sublimit={result.get('sublimit_usd')} "
            f"clause={result.get('source_clause_id')}"
        )
    if tool_name == "compute_payout":
        return (
            f"payable=${result.get('payable_amount')} "
            f"status={result.get('claim_status')}"
        )
    return str(result)[:120]
