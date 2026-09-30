"""
agent.py — The claims triage agent: the model picks the next tool each lap.

Four budgets are checked in the loop, every lap, before the next model call:
  max_iterations   model calls
  max_tokens       prompt + completion tokens SUMMED over every lap (the whole
                   message list is re-sent each lap, so the last call alone
                   understates the spend by a multiple)
  max_cost_usd     summed the same way
  max_wall_s       elapsed real time for the claim
When one fires the run stops cleanly with stop_reason="budget:<name>" and no
final answer, rather than spinning.

Every step is recorded (tool, arguments, short result, tokens, time) because
Week 8 scores the path, not just the answer.
"""

import json
import time

import llm
from tools import TOOLS, dispatch
from triage import CONTRACT_TEXT, parse_final

AGENT_PROMPT_VERSION = "agent-v2"

SYSTEM = f"""You are the claims triage agent at Northgate Mutual. Given a claim \
number, decide coverage and the amount payable after the deductible.

Use the tools to get facts: the claim file for what happened, the policy \
wording for what is covered and excluded, and compute_payout for the \
arithmetic. Base every coverage call on wording you actually retrieved, and \
read the adjuster notes: they often change which rule applies. If the claim \
file does not yet hold enough facts to decide, answer needs_info instead of \
guessing.

{CONTRACT_TEXT}"""

DEFAULT_BUDGETS = {
    "max_iterations": 8,
    "max_tokens": 40_000,
    "max_cost_usd": 0.02,
    "max_wall_s": 240.0,
}


def _short(result: dict) -> str:
    s = json.dumps(result, ensure_ascii=False)
    return s if len(s) <= 300 else s[:300] + "..."


def run_agent(claim_number: str, budgets: dict | None = None, log=None) -> dict:
    b = {**DEFAULT_BUDGETS, **(budgets or {})}
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"Triage claim {claim_number}."},
    ]
    steps, tokens, cost, api_s, tool_s, throttle_s = [], 0, 0.0, 0.0, 0.0, 0.0
    t0 = time.perf_counter()
    stop, final_text, laps = None, "", 0

    def note(msg):
        if log:
            log(msg)

    while True:
        elapsed = time.perf_counter() - t0
        checks = [
            ("max_iterations", laps >= b["max_iterations"], f"{laps} laps"),
            ("max_tokens", tokens >= b["max_tokens"], f"{tokens} tokens"),
            ("max_cost_usd", cost >= b["max_cost_usd"], f"${cost:.5f}"),
            ("max_wall_s", elapsed >= b["max_wall_s"], f"{elapsed:.1f}s"),
        ]
        fired = next((c for c in checks if c[1]), None)
        if fired:
            stop = f"budget:{fired[0]}"
            note(f"  BUDGET FIRED {fired[0]} (limit {b[fired[0]]}, used {fired[2]}) -> stopping cleanly")
            break

        laps += 1
        res = llm.chat(messages, tools=TOOLS, max_tokens=2000)
        tokens += res["usage"]["total"]
        cost += res["cost_usd"]
        api_s += res["api_s"]
        throttle_s += res["throttle_s"]
        note(f"  lap {laps}: {res['usage']['total']} tok (cum {tokens}, ${cost:.5f}) "
             f"tools={[tc['name'] for tc in res['tool_calls']] or 'none'}")
        if res["error"]:
            stop = "error"
            steps.append({"lap": laps, "tool": None, "error": res["error"]})
            break
        if not res["tool_calls"]:
            final_text = res["content"]
            stop = "final_answer"
            break

        messages.append({
            "role": "assistant",
            "content": res["content"] or "",
            "tool_calls": [{"id": tc["id"], "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                           for tc in res["tool_calls"]],
        })
        for tc in res["tool_calls"]:
            ts = time.perf_counter()
            out = dispatch(tc["name"], tc["arguments"])
            tool_s += time.perf_counter() - ts
            try:
                args = json.loads(tc["arguments"])
            except json.JSONDecodeError:
                args = {"_raw": tc["arguments"]}
            steps.append({"lap": laps, "tool": tc["name"], "args": args,
                          "result": _short(out), "error": out.get("error")})
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": json.dumps(out, ensure_ascii=False)})

    return {
        "system": "agent",
        "prompt_version": AGENT_PROMPT_VERSION,
        "claim_number": claim_number,
        "answer": parse_final(final_text),
        "final_text": final_text,
        "stop_reason": stop,
        "steps": steps,
        "laps": laps,
        "tokens": tokens,
        "cost_usd": round(cost, 6),
        "latency_s": round(api_s + tool_s, 3),   # model + tool time, no rate-limit sleeps
        "throttle_s": round(throttle_s, 1),
        "wall_s": round(time.perf_counter() - t0, 3),
        "budgets": b,
    }
