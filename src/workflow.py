"""
workflow.py — The same triage as agent.py, as four hard-coded steps. No loop.

  1. get_claim(claim_number)                                  code
  2. search_policy(first notice of loss + all adjuster notes)  code, one call
  3. one model call, no tools: decide coverage from 1 + 2      model
  4. compute_payout(the decision from step 3)                 code

Same tools, same model, same output contract (triage.CONTRACT_TEXT) as the
agent. The only branch is "no adjuster notes yet -> needs_info", which a
claims director would hard-code too. What the workflow cannot do is look at
what step 2 returned and decide to search again for a different peril: its
path is the same for every claim.
"""

import json
import time

import llm
from tools import dispatch
from triage import CONTRACT_TEXT, DECISIONS, parse_final

WORKFLOW_VERSION = "workflow-v2"

DECIDE_SYSTEM = f"""You are the claims triage step at Northgate Mutual. You get a \
claim file and the policy passages retrieved for it. Decide coverage using only \
that wording and the adjuster notes. Reply with ONE JSON object:
{{"decision": "{'|'.join(DECISIONS)}", "exclusion_ids": [...], "clauses": [...],
 "claim_status": "covered|covered_subject_to_sublimit|excluded",
 "covered_amount": <sum of covered estimate lines before deductible>,
 "deductible_basis": "all_peril|hurricane|none_scheduled_article",
 "sublimit": <number or null>, "reason": "<one or two sentences>"}}
The payable amount is computed by code from claim_status, covered_amount,
deductible_basis and sublimit; do not compute it yourself.

Decision meanings (same as the final contract):
{CONTRACT_TEXT.split(chr(10), 3)[3]}"""


def run_workflow(claim_number: str, log=None) -> dict:
    t0 = time.perf_counter()
    steps, tool_s = [], 0.0

    def call(name, args):
        nonlocal tool_s
        ts = time.perf_counter()
        out = dispatch(name, args)
        tool_s += time.perf_counter() - ts
        steps.append({"lap": len(steps) + 1, "tool": name, "args": args,
                      "result": json.dumps(out, ensure_ascii=False)[:300], "error": out.get("error")})
        return out

    base = {"system": "workflow", "prompt_version": WORKFLOW_VERSION, "claim_number": claim_number}

    # Step 1
    claim = call("get_claim", {"claim_number": claim_number})
    if claim.get("error"):
        return {**base, "answer": None, "stop_reason": "error", "steps": steps, "laps": 0,
                "tokens": 0, "cost_usd": 0.0, "latency_s": round(tool_s, 3), "throttle_s": 0.0,
                "wall_s": round(time.perf_counter() - t0, 3), "final_text": ""}
    if not claim.get("adjuster_notes"):
        answer = {"claim_number": claim_number, "decision": "needs_info", "exclusion_ids": [],
                  "clauses": [], "payable": None,
                  "reason": "No adjuster notes on file yet; cannot decide coverage."}
        return {**base, "answer": answer, "stop_reason": "final_answer", "steps": steps, "laps": 0,
                "tokens": 0, "cost_usd": 0.0, "latency_s": round(tool_s, 3), "throttle_s": 0.0,
                "wall_s": round(time.perf_counter() - t0, 3), "final_text": json.dumps(answer)}

    # Step 2 — one fixed query built from everything known about the loss
    query = claim["fnol_description"] + " " + " ".join(n["text"] for n in claim["adjuster_notes"])
    policy = call("search_policy", {"query": query[:1500]})

    # Step 3 — one model call, no tools
    user = ("CLAIM FILE\n" + json.dumps(claim, ensure_ascii=False) +
            "\n\nPOLICY PASSAGES\n" + json.dumps(policy["passages"], ensure_ascii=False))
    res = llm.chat([{"role": "system", "content": DECIDE_SYSTEM},
                    {"role": "user", "content": user}], max_tokens=2000)
    decision = parse_final(res["content"]) or {}
    if log:
        log(f"  step3: {res['usage']['total']} tok decision={decision.get('decision')}")

    # Step 4
    payable = None
    if decision.get("decision") in ("covered", "partially_covered", "excluded"):
        args = {"claim_number": claim_number,
                "claim_status": decision.get("claim_status", "excluded"),
                "covered_amount": float(decision.get("covered_amount") or 0),
                "deductible_basis": decision.get("deductible_basis", "all_peril")}
        if decision.get("sublimit") is not None:
            args["sublimit"] = float(decision["sublimit"])
        payable = call("compute_payout", args).get("payable")

    answer = {"claim_number": claim_number, "decision": decision.get("decision"),
              "exclusion_ids": decision.get("exclusion_ids") or [],
              "clauses": decision.get("clauses") or [], "payable": payable,
              "reason": decision.get("reason", "")}
    return {**base, "answer": answer, "stop_reason": "error" if res["error"] else "final_answer",
            "steps": steps, "laps": 1, "tokens": res["usage"]["total"],
            "cost_usd": round(res["cost_usd"], 6),
            "latency_s": round(res["api_s"] + tool_s, 3), "throttle_s": res["throttle_s"],
            "wall_s": round(time.perf_counter() - t0, 3), "final_text": res["content"]}
