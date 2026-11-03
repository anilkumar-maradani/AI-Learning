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

Week 11: this is the version Week 7 shipped, so it is what production runs.
Every run now returns ``spans`` (one per stage call: retrieval / generation /
tools, each with latency, tokens and cost) and ``prompt`` (version + SHA-256 of
the system prompt and the user template), which observability.py writes to the
request log. Prompt versions are append-only: a change adds a key to PROMPTS.
"""

import hashlib
import json
import time

import llm
from observability import Tracer, count_tokens
from tools import dispatch
from triage import CONTRACT_TEXT, DECISIONS, parse_final

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

_USER_V2 = "CLAIM FILE\n{claim}\n\nPOLICY PASSAGES\n{passages}"

# workflow-v3 (Week 11): a RETRIEVAL fix. Step 2b attaches the complete, uncut
# exclusion table of every form on the policy. The system prompt is byte-identical
# to v2; the user template only gains the block that carries the tables. Found from
# production trace tr_03c4501f8140 (NG-1106 E-93 never in context); regression case
# W11-1 in evals/cases/week11_regressions.jsonl.
_USER_V3 = _USER_V2 + ("\n\nEXCLUSION SCHEDULES (the complete exclusion table of every form "
                       "attached to this policy)\n{schedules}")

PROMPTS = {
    "workflow-v2": {"system": DECIDE_SYSTEM, "user": _USER_V2},
    "workflow-v3": {"system": DECIDE_SYSTEM, "user": _USER_V3},
}
WORKFLOW_VERSION = "workflow-v3"   # latest; what production serves is routed in triage_service.py


def prompt_fingerprint(version: str) -> dict:
    p = PROMPTS[version]
    return {"version": version,
            "system_sha256": hashlib.sha256(p["system"].encode("utf-8")).hexdigest(),
            "user_template_sha256": hashlib.sha256(p["user"].encode("utf-8")).hexdigest()}


def _context(passages: list[dict]) -> list[dict]:
    return [{"rank": i, "chunk_id": p["chunk_id"], "form_number": p.get("form_number"),
             "clause_id": p.get("clause_id")} for i, p in enumerate(passages, 1)]


def run_workflow(claim_number: str, log=None, version: str = WORKFLOW_VERSION) -> dict:
    if version not in PROMPTS:
        raise ValueError(f"unknown workflow version {version!r}; known: {sorted(PROMPTS)}")
    t0 = time.perf_counter()
    tracer = Tracer()
    steps, tool_s = [], 0.0

    def call(name, args, stage="tools"):
        nonlocal tool_s
        ts = time.perf_counter()
        with tracer.span(f"{stage}:{name}", stage, tool=name) as sp:
            out = dispatch(name, args)
            sp["attrs"]["error"] = out.get("error")
        tool_s += time.perf_counter() - ts
        steps.append({"lap": len(steps) + 1, "tool": name, "args": args,
                      "result": json.dumps(out, ensure_ascii=False)[:300], "error": out.get("error")})
        return out, sp

    base = {"system": "workflow", "prompt_version": version, "prompt": prompt_fingerprint(version),
            "claim_number": claim_number}

    def done(**kw):
        return {**base, "steps": steps, "spans": tracer.spans,
                "wall_s": round(time.perf_counter() - t0, 3), **kw}

    # Step 1
    claim, sp = call("get_claim", {"claim_number": claim_number})
    sp["attrs"]["notes_count"] = len(claim.get("adjuster_notes") or [])
    if claim.get("error"):
        return done(answer=None, stop_reason="error", laps=0, tokens=0, cost_usd=0.0,
                    latency_s=round(tool_s, 3), throttle_s=0.0, final_text="", payout=None)
    if not claim.get("adjuster_notes"):
        answer = {"claim_number": claim_number, "decision": "needs_info", "exclusion_ids": [],
                  "clauses": [], "payable": None,
                  "reason": "No adjuster notes on file yet; cannot decide coverage."}
        return done(answer=answer, stop_reason="final_answer", laps=0, tokens=0, cost_usd=0.0,
                    latency_s=round(tool_s, 3), throttle_s=0.0, final_text=json.dumps(answer), payout=None)

    # Step 2 — one fixed query built from everything known about the loss
    query = claim["fnol_description"] + " " + " ".join(n["text"] for n in claim["adjuster_notes"])
    policy, sp = call("search_policy", {"query": query[:1500]}, stage="retrieval")
    passages = policy.get("passages") or []
    sp["attrs"].update({"query_sha256": hashlib.sha256(query[:1500].encode("utf-8")).hexdigest(),
                        "n_results": len(passages), "context": _context(passages)})

    # Step 2b (v3) — the whole exclusion table of every attached form, uncut
    schedules = []
    if version == "workflow-v3":
        for form in claim.get("forms") or []:
            out, sp = call("exclusion_schedule", {"form_number": form}, stage="retrieval")
            got = out.get("passages") or []
            sp["attrs"].update({"form_number": form, "context": _context(got)})
            schedules += got

    # Step 3 — one model call, no tools
    blocks = {"claim_file": json.dumps(claim, ensure_ascii=False),
              "policy_passages": json.dumps(passages, ensure_ascii=False)}
    if version == "workflow-v3":
        blocks["exclusion_schedules"] = json.dumps(schedules, ensure_ascii=False)
    user = PROMPTS[version]["user"].format(claim=blocks["claim_file"], passages=blocks["policy_passages"],
                                           schedules=blocks.get("exclusion_schedules", ""))
    system = PROMPTS[version]["system"]
    with tracer.span("generation:decide", "generation", model=llm.MAIN_MODEL, prompt_version=version,
                     temperature=0.0, max_tokens=2000) as sp:
        res = llm.chat([{"role": "system", "content": system},
                        {"role": "user", "content": user}], max_tokens=2000)
        Tracer.record_llm(sp, res)
        # Which block of the prompt the input tokens were spent on: lets the bill be
        # attributed to the stage that put the text there (tools / retrieval).
        sp["attrs"]["prompt_tokens_by_block"] = {
            "system": count_tokens(system),
            **{k: count_tokens(v) for k, v in blocks.items()},
            "template_and_chat_format": None,
        }
        by = sp["attrs"]["prompt_tokens_by_block"]
        by["template_and_chat_format"] = max(0, res["usage"]["prompt"] - sum(v for v in by.values() if v))
    decision = parse_final(res["content"]) or {}
    if log:
        log(f"  step3: {res['usage']['total']} tok decision={decision.get('decision')}")

    # Step 4
    payable, payout = None, None
    if decision.get("decision") in ("covered", "partially_covered", "excluded"):
        args = {"claim_number": claim_number,
                "claim_status": decision.get("claim_status", "excluded"),
                "covered_amount": float(decision.get("covered_amount") or 0),
                "deductible_basis": decision.get("deductible_basis", "all_peril")}
        if decision.get("sublimit") is not None:
            args["sublimit"] = float(decision["sublimit"])
        payout, sp = call("compute_payout", args)
        sp["attrs"].update({"args": {k: v for k, v in args.items() if k != "claim_number"},
                            "result": {k: payout.get(k) for k in ("payable", "deductible_applied", "error")}})
        payable = payout.get("payable")

    answer = {"claim_number": claim_number, "decision": decision.get("decision"),
              "exclusion_ids": decision.get("exclusion_ids") or [],
              "clauses": decision.get("clauses") or [], "payable": payable,
              "reason": decision.get("reason", "")}
    return done(answer=answer, stop_reason="error" if res["error"] else "final_answer",
                laps=1, tokens=res["usage"]["total"], cost_usd=round(res["cost_usd"], 6),
                latency_s=round(res["api_s"] + tool_s, 3), throttle_s=res["throttle_s"],
                final_text=res["content"], payout=payout)
