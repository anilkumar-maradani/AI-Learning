#!/usr/bin/env python3
"""
Week 7 — race the claims agent against the fixed workflow.

    python evals/week7.py agent           # agent over the 10 race claims (one command)
    python evals/week7.py workflow        # workflow over the same 10 (one command)
    python evals/week7.py table           # race.csv + race_table.md from the saved runs
    python evals/week7.py budget-demo     # one real run that hits a budget and stops cleanly

Latency is model time + tool time. Rate-limit sleeps (Groq free tier: 8K
tokens/min) are recorded separately as throttle_s and never counted.
"""

import argparse
import csv
import json
import os
import statistics
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from console import enable_utf8  # noqa: E402

enable_utf8()

from triage import grade  # noqa: E402

CASES = os.path.join(ROOT, "evals", "cases", "race_10.jsonl")
OUT = os.path.join(ROOT, "reports", "week7")
TPM = 8000


def load_cases(path=CASES):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def warm_up():
    from tools import search_policy
    search_policy("warm up the embedding model and BM25 index")


def pace(tokens: int):
    """Wait long enough for the per-minute token window to refill. Not timed."""
    time.sleep(min(70, tokens / TPM * 60))


def race(system: str, cases: list[dict], out_path: str, budgets: dict | None = None) -> list[dict]:
    from agent import run_agent
    from workflow import run_workflow
    warm_up()
    runs = []
    for case in cases:
        print(f"{system} {case['claim_number']} ({case['class']})")
        if system == "agent":
            r = run_agent(case["claim_number"], budgets=budgets, log=print)
        else:
            r = run_workflow(case["claim_number"], log=print)
        r["case"] = case
        r["grade"] = grade(r["answer"], case)
        print(f"  -> {'PASS' if r['grade']['pass'] else 'FAIL'} {r['grade']['why']} | "
              f"{r['tokens']} tok ${r['cost_usd']:.5f} {r['latency_s']}s")
        runs.append(r)
        pace(r["tokens"])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        for r in runs:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return runs


def load_runs(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def four_numbers(runs):
    return {
        "pass_rate": sum(r["grade"]["pass"] for r in runs) / len(runs),
        "p50_latency_s": statistics.median(r["latency_s"] for r in runs),
        "total_tokens": sum(r["tokens"] for r in runs),
        "cost_per_claim_usd": sum(r["cost_usd"] for r in runs) / len(runs),
    }


def cmd_table(_args):
    a = load_runs(os.path.join(OUT, "agent_runs.jsonl"))
    w = load_runs(os.path.join(OUT, "workflow_runs.jsonl"))
    assert [r["claim_number"] for r in a] == [r["claim_number"] for r in w], "different inputs"
    na, nw = four_numbers(a), four_numbers(w)
    with open(os.path.join(OUT, "race.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(["system", "pass_rate", "p50_latency_s", "total_tokens", "cost_per_claim_usd", "n_claims"])
        for name, n in (("agent", na), ("workflow", nw)):
            wr.writerow([name, f"{n['pass_rate']:.2f}", f"{n['p50_latency_s']:.2f}",
                         n["total_tokens"], f"{n['cost_per_claim_usd']:.6f}", len(a)])
    lines = [
        "| | Agent | Workflow |", "|---|---:|---:|",
        f"| Pass rate | {na['pass_rate']:.0%} | {nw['pass_rate']:.0%} |",
        f"| p50 latency (s) | {na['p50_latency_s']:.2f} | {nw['p50_latency_s']:.2f} |",
        f"| Total tokens (10 claims, all laps) | {na['total_tokens']:,} | {nw['total_tokens']:,} |",
        f"| Cost per claim (USD) | ${na['cost_per_claim_usd']:.5f} | ${nw['cost_per_claim_usd']:.5f} |",
        "",
        "| Claim | Class | Expected | Agent | Workflow | Agent path |",
        "|---|---|---|---|---|---|",
    ]
    for ra, rw in zip(a, w):
        c = ra["case"]
        exp = f"{c['decision']} / {c['payable']}"
        fa = "PASS" if ra["grade"]["pass"] else f"FAIL: {ra['grade']['why']}"
        fw = "PASS" if rw["grade"]["pass"] else f"FAIL: {rw['grade']['why']}"
        path = " → ".join(s["tool"] or "error" for s in ra["steps"])
        lines.append(f"| {c['claim_number']} | {c['class']} | {exp} | {fa} | {fw} | {path} |")
    with open(os.path.join(OUT, "race_table.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def cmd_budget_demo(args):
    """A real claim, a tight but realistic token budget: the loop must stop, not spin."""
    from agent import run_agent
    warm_up()
    budgets = {"max_tokens": args.max_tokens}
    log_lines = []

    def log(msg):
        print(msg)
        log_lines.append(msg)

    log(f"claim {args.claim}  budgets: max_iterations=8 max_tokens={args.max_tokens} "
        f"max_cost_usd=0.02 max_wall_s=240")
    r = run_agent(args.claim, budgets=budgets, log=log)
    log(f"stop_reason={r['stop_reason']} laps={r['laps']} tokens={r['tokens']} "
        f"cost=${r['cost_usd']:.5f} wall={r['wall_s']}s final_answer={r['answer']}")
    for s in r["steps"]:
        log(f"  step lap {s['lap']}: {s['tool']} {json.dumps(s.get('args'))}")
    with open(os.path.join(OUT, "budget_log.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(log_lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["agent", "workflow", "table", "budget-demo"])
    ap.add_argument("--claim", default="CLM-2026-20103")
    ap.add_argument("--max-tokens", type=int, default=6000)
    args = ap.parse_args()
    if args.cmd in ("agent", "workflow"):
        race(args.cmd, load_cases(), os.path.join(OUT, f"{args.cmd}_runs.jsonl"))
    elif args.cmd == "table":
        cmd_table(args)
    else:
        cmd_budget_demo(args)


if __name__ == "__main__":
    main()
