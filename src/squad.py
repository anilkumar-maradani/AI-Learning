"""
squad.py — The claims squad: an orchestrator that decomposes a claim, delegates
to two narrow workers and synthesises the answer. Week 10 races it against the
single agent (agent.py) on the same cases, with the same judge.

  1. orchestrator:plan            one model call; sees only the claim header
                                  (forms, first notice) and writes one brief
                                  per worker
  2. orchestrator -> notes_worker one model call, no tools; reads the claim file
                                  (decision note withheld by tools.get_claim) and
                                  returns the facts that decide coverage, as JSON
  3. orchestrator -> exclusions_worker
                                  a small loop with ONE tool, search_policy;
                                  gets the notes worker's facts, NOT the raw note
                                  history, and returns a coverage call as JSON
  4. compute_payout               code, not a model (same tool as the agent)
  5. orchestrator:synthesis       one model call; worker outputs in, the
                                  triage.CONTRACT_TEXT answer out

Context strategy: each hop carries only what the next worker needs. The full
note history goes to the notes worker once and nowhere else.

Every model call is recorded as a hand-off with its own token count, so the
Week 10 report can say which hop the bill came from.

Worker failure: a worker call that raises WorkerError (an HTTP-500 stand-in;
`inject` turns one on) is retried once. If it fails again the orchestrator
carries on WITHOUT that worker and tells synthesis so explicitly. What synthesis
then does with that is measured, not assumed.
"""

import json
import time

import llm
from tools import SEARCH_POLICY, dispatch
from triage import CONTRACT_TEXT, parse_final

SQUAD_VERSION = "squad-v1"
WORKER_RETRIES = 1
EXCLUSIONS_MAX_LAPS = 4


class WorkerError(Exception):
    def __init__(self, worker: str, status: int, message: str):
        super().__init__(f"{worker} returned HTTP {status}: {message}")
        self.worker, self.status = worker, status


PLAN_SYSTEM = """You are the orchestrator of a claims squad at Northgate Mutual. \
You get the header of one claim. Write a short brief for each of two workers:
- notes_worker reads the adjuster notes and pulls out the facts that decide coverage.
- exclusions_worker reads the policy wording of the attached forms and makes the coverage call.
Reply with JSON only: {"notes_worker": "<what to look for>", "exclusions_worker": "<what to check>"}"""

NOTES_SYSTEM = """You are the adjuster-notes worker. Read the claim file and \
report the facts that decide coverage. Do not decide coverage and do not quote \
policy wording; you have none. Reply with JSON only:
{"cause": "<what actually caused the loss, per the notes>",
 "timeline": "<dates and durations that matter: how long water ran, when drying began, occupancy, named storms>",
 "damage_lines": [{"item": "...", "amount": <number>}],
 "facts_that_change_the_rule": ["<anything in the notes that differs from the first notice of loss>"]}"""

EXCLUSIONS_SYSTEM = """You are the coverage and exclusions worker at Northgate \
Mutual. You get the facts of one loss and the forms attached to the policy. \
Read the wording of each relevant form with search_policy (form_number set: one \
call per form is enough), then decide. Base the call only on wording you \
retrieved. Reply with JSON only:
{"claim_status": "covered|covered_subject_to_sublimit|excluded",
 "decision": "covered|partially_covered|excluded|needs_info",
 "exclusion_ids": ["E-NN"], "clauses": ["XX-N"],
 "covered_amount": <sum of the covered damage lines before any deductible>,
 "deductible_basis": "all_peril|hurricane|none_scheduled_article",
 "sublimit": <number or null>,
 "reason": "<one or two sentences>"}
partially_covered means some lines are excluded (or a sublimit caps the payment) \
and the rest are paid: claim_status is then covered or covered_subject_to_sublimit \
and covered_amount counts only the paid lines."""

SYNTHESIS_SYSTEM = f"""You are the orchestrator of a claims squad at Northgate \
Mutual, writing the final answer from your workers' reports. Carry the \
exclusions worker's decision over exactly: never upgrade a partial or excluded \
call to covered, and keep every exclusion it cited. Use the payable amount from \
compute_payout. If a worker report is missing, say so in the reason and do not \
invent what it would have said.

{CONTRACT_TEXT}"""


def _json(text: str) -> dict:
    return parse_final(text) or {}


class _Ledger:
    """Every model call of one run, tagged with the hand-off it served."""

    def __init__(self):
        self.calls = []

    def chat(self, handoff: str, messages: list[dict], **kw) -> dict:
        res = llm.chat(messages, max_tokens=kw.pop("max_tokens", 1500), **kw)
        self.calls.append({"handoff": handoff, **res["usage"], "cost_usd": res["cost_usd"],
                           "api_s": res["api_s"], "throttle_s": res["throttle_s"],
                           "error": res["error"]})
        return res


def _notes_worker(ledger: _Ledger, brief: str, claim: dict, fail: bool) -> dict:
    if fail:
        raise WorkerError("notes_worker", 500, "Internal Server Error (injected)")
    view = {k: claim[k] for k in ("claim_number", "date_of_loss", "forms", "coverage_a_limit",
                                  "all_peril_deductible", "fnol_description", "adjuster_notes")
            if k in claim}
    view["scheduled_articles"] = claim.get("scheduled_articles") or []
    res = ledger.chat("orchestrator -> notes_worker", [
        {"role": "system", "content": NOTES_SYSTEM},
        {"role": "user", "content": f"BRIEF\n{brief}\n\nCLAIM FILE\n{json.dumps(view, ensure_ascii=False)}"},
    ])
    return _json(res["content"])


def _exclusions_worker(ledger: _Ledger, brief: str, claim: dict, facts: dict,
                       steps: list, fail: bool) -> dict:
    if fail:
        raise WorkerError("exclusions_worker", 500, "Internal Server Error (injected)")
    handoff = {
        "brief": brief,
        "forms_attached": claim["forms"],
        "all_peril_deductible": claim["all_peril_deductible"],
        "coverage_a_limit": claim["coverage_a_limit"],
        "scheduled_articles": claim.get("scheduled_articles") or [],
        "facts_from_notes_worker": facts,
    }
    messages = [{"role": "system", "content": EXCLUSIONS_SYSTEM},
                {"role": "user", "content": json.dumps(handoff, ensure_ascii=False)}]
    for lap in range(1, EXCLUSIONS_MAX_LAPS + 1):
        last = lap == EXCLUSIONS_MAX_LAPS
        res = ledger.chat(f"orchestrator -> exclusions_worker (lap {lap})", messages,
                          tools=None if last else [SEARCH_POLICY], max_tokens=2000)
        if res["error"] or not res["tool_calls"]:
            return _json(res["content"])
        messages.append({"role": "assistant", "content": res["content"] or "",
                         "tool_calls": [{"id": tc["id"], "type": "function",
                                         "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                                        for tc in res["tool_calls"]]})
        for tc in res["tool_calls"]:
            out = dispatch(tc["name"], tc["arguments"]) if tc["name"] == "search_policy" else \
                {"error": f"unknown tool {tc['name']!r}; you have search_policy only"}
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {"_raw": tc["arguments"]}
            steps.append({"worker": "exclusions_worker", "lap": lap, "tool": tc["name"], "args": args,
                          "error": out.get("error")})
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": json.dumps(out, ensure_ascii=False)})
    return {}


def _call_worker(name: str, fn, events: list, log, *args, **kwargs):
    """Retry a failing worker WORKER_RETRIES times; return (result, error_text)."""
    last = None
    for attempt in range(1 + WORKER_RETRIES):
        try:
            return fn(*args, **kwargs), None
        except WorkerError as exc:
            last = str(exc)
            events.append({"worker": name, "attempt": attempt + 1, "status": exc.status, "error": last})
            if log:
                log(f"  {name} attempt {attempt + 1}: {exc}")
    return None, last


def run_squad(claim_number: str, inject: str | None = None, log=None) -> dict:
    """inject: name of a worker that returns HTTP 500 on every attempt in this run."""
    t0 = time.perf_counter()
    ledger, steps, events = _Ledger(), [], []

    def call(name, args):
        out = dispatch(name, args)
        steps.append({"worker": "orchestrator", "tool": name, "args": args, "error": out.get("error")})
        return out

    claim = call("get_claim", {"claim_number": claim_number})
    base = {"system": "squad", "prompt_version": SQUAD_VERSION, "claim_number": claim_number,
            "inject": inject}

    # 1. plan
    header = {"claim_number": claim_number, "forms": claim.get("forms"),
              "fnol_description": claim.get("fnol_description"),
              "adjuster_note_count": len(claim.get("adjuster_notes") or [])}
    res = ledger.chat("orchestrator:plan", [{"role": "system", "content": PLAN_SYSTEM},
                                            {"role": "user", "content": json.dumps(header)}], max_tokens=800)
    plan = _json(res["content"])

    # 2. notes worker
    facts, notes_err = _call_worker("notes_worker", _notes_worker, events, log,
                                    ledger, plan.get("notes_worker", ""), claim,
                                    inject == "notes_worker")

    # 3. exclusions worker
    coverage, excl_err = _call_worker("exclusions_worker", _exclusions_worker, events, log,
                                      ledger, plan.get("exclusions_worker", ""), claim, facts or {},
                                      steps, inject == "exclusions_worker")

    # 4. payout (code)
    payout = None
    if coverage and coverage.get("decision") in ("covered", "partially_covered", "excluded"):
        args = {"claim_number": claim_number,
                "claim_status": coverage.get("claim_status", "excluded"),
                "covered_amount": float(coverage.get("covered_amount") or 0),
                "deductible_basis": coverage.get("deductible_basis", "all_peril")}
        if coverage.get("sublimit") is not None:
            args["sublimit"] = float(coverage["sublimit"])
        payout = call("compute_payout", args)

    # 5. synthesis
    reports = {
        "claim_number": claim_number,
        "notes_worker": facts if facts is not None else {"status": "FAILED", "error": notes_err},
        "exclusions_worker": coverage if coverage is not None else {"status": "FAILED", "error": excl_err},
        "compute_payout": payout if payout is not None else {"status": "NOT RUN",
                                                              "why": "no coverage decision to price"},
    }
    res = ledger.chat("workers -> orchestrator:synthesis", [
        {"role": "system", "content": SYNTHESIS_SYSTEM},
        {"role": "user", "content": json.dumps(reports, ensure_ascii=False)}], max_tokens=1500)
    if log:
        for c in ledger.calls:
            log(f"  {c['handoff']}: {c['total']} tok")

    calls = ledger.calls
    api_s = sum(c["api_s"] for c in calls)
    wall = time.perf_counter() - t0
    throttle = sum(c["throttle_s"] for c in calls)
    return {
        **base,
        "answer": parse_final(res["content"]),
        "final_text": res["content"],
        "stop_reason": "error" if res["error"] else "final_answer",
        "plan": plan,
        "worker_reports": reports,
        "worker_failures": events,
        "steps": steps,
        "handoffs": calls,
        "laps": len(calls),
        "tokens": sum(c["total"] for c in calls),
        "cost_usd": round(sum(c["cost_usd"] for c in calls), 6),
        # model time + local tool time; rate-limit sleeps excluded, as in Weeks 7-8
        "latency_s": round(max(0.0, wall - throttle), 3),
        "api_s": round(api_s, 3),
        "throttle_s": round(throttle, 1),
        "wall_s": round(wall, 3),
    }
