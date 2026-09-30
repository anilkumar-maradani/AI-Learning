#!/usr/bin/env python3
"""
Week 8 — trajectory eval for the claims agent.

    python evals/week8.py score  --runs reports/week7/agent_runs.jsonl --label before
    python evals/week8.py run    --label after      # agent with the one mitigation switched on
    python evals/week8.py compare                   # top mode before -> after, price, regression table

The 10 expected paths live in evals/cases/trajectory_10.jsonl (a spec each);
trajectory.accepted_paths() expands every spec into the explicit set of valid
sequences, printed in the report so the alternate paths are visible.
"""

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from console import enable_utf8  # noqa: E402

enable_utf8()

from trajectory import accepted_paths, check_args, failure_modes, match_path, step_tokens  # noqa: E402
from triage import grade  # noqa: E402

OUT = os.path.join(ROOT, "reports", "week8")
SPECS = os.path.join(ROOT, "evals", "cases", "trajectory_10.jsonl")
RACE = os.path.join(ROOT, "evals", "cases", "race_10.jsonl")

MODES = ["skipped_required_lookup", "payout_before_lookup", "payout_without_facts",
         "repeated_identical_call", "unneeded_detour", "invalid_argument",
         "stopped_without_answer", "wrong_outcome"]


def _jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def score(runs: list[dict]) -> dict:
    specs = {s["claim_number"]: s for s in _jsonl(SPECS)}
    cases = {c["claim_number"]: c for c in _jsonl(RACE)}
    rows = []
    for run in runs:
        cn = run["claim_number"]
        spec, case = specs[cn], cases[cn]
        accepted = accepted_paths(spec)
        matched = match_path(run["steps"], accepted)
        args = check_args(run, case)
        outcome = grade(run.get("answer"), case)
        modes = failure_modes(run, case, spec, matched, args)
        if not outcome["pass"]:
            modes.append("wrong_outcome")
        tool_names = [s["tool"] for s in run["steps"]]
        tool_ok = any(tool_names == [("search_policy" if t.startswith("policy:") else
                                      {"claim": "get_claim", "payout": "compute_payout"}[t])
                                     for t in p] for p in accepted)
        needed = min(len(p) for p in accepted)
        traj_pass = matched is not None and all(a["valid"] for a in args) \
            and run["stop_reason"] == "final_answer"
        rows.append({
            "claim_number": cn,
            "path": [sorted(step_tokens(s)) for s in run["steps"]],
            "tools": tool_names,
            "matched_path": matched,
            "tool_choice_ok": tool_ok,
            "arg_checks": args,
            "steps_taken": len(run["steps"]),
            "steps_needed": needed,
            "outcome_pass": outcome["pass"],
            "outcome_why": outcome["why"],
            "trajectory_pass": traj_pass,
            "modes": modes,
            "cost_usd": run["cost_usd"],
            "tokens": run["tokens"],
            "latency_s": run["latency_s"],
        })
    n = len(rows)
    all_args = [a for r in rows for a in r["arg_checks"]]
    costs = [r["cost_usd"] for r in rows]
    summary = {
        "n": n,
        "tool_choice_accuracy": sum(r["tool_choice_ok"] for r in rows) / n,
        "argument_validity": sum(a["valid"] for a in all_args) / len(all_args) if all_args else 1.0,
        "n_arguments_checked": len(all_args),
        "step_efficiency": sum(r["steps_taken"] for r in rows) / sum(r["steps_needed"] for r in rows),
        "cost_p50": statistics.median(costs),
        "cost_max": max(costs),
        "cost_mean": sum(costs) / n,
        "tokens_per_claim": sum(r["tokens"] for r in rows) / n,
        "latency_p50": statistics.median(r["latency_s"] for r in rows),
        "outcome_pass_rate": sum(r["outcome_pass"] for r in rows) / n,
        "trajectory_pass_rate": sum(r["trajectory_pass"] for r in rows) / n,
        "mode_counts": {m: sum(m in r["modes"] for r in rows) for m in MODES},
    }
    summary["gap"] = summary["outcome_pass_rate"] - summary["trajectory_pass_rate"]
    return {"summary": summary, "rows": rows}


def print_score(res: dict, label: str):
    s = res["summary"]
    print(f"\n== trajectory eval: {label} ({s['n']} claims) ==")
    print(f"tool-choice accuracy   {s['tool_choice_accuracy']:.0%}")
    print(f"argument validity      {s['argument_validity']:.0%} of {s['n_arguments_checked']} arguments")
    print(f"step efficiency        {s['step_efficiency']:.2f} (steps taken / steps needed)")
    print(f"cost per claim         p50 ${s['cost_p50']:.5f}   max ${s['cost_max']:.5f}")
    print(f"outcome pass rate      {s['outcome_pass_rate']:.0%}")
    print(f"trajectory pass rate   {s['trajectory_pass_rate']:.0%}")
    print(f"GAP (outcome - traj)   {s['gap'] * 100:+.0f} pts")
    print("per claim:")
    for r in res["rows"]:
        print(f"  {r['claim_number']}  outcome={'P' if r['outcome_pass'] else 'F'} "
              f"traj={'P' if r['trajectory_pass'] else 'F'}  {' → '.join(r['tools'])}  {r['modes'] or ''}")
    print("modes:", {k: v for k, v in s["mode_counts"].items() if v})


def cmd_score(args):
    res = score(_jsonl(args.runs))
    res["source_runs"] = os.path.relpath(args.runs, ROOT).replace("\\", "/")
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"trajectory_{args.label}.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, ensure_ascii=False)
    print_score(res, args.label)


def cmd_run(args):
    sys.path.insert(0, os.path.join(ROOT, "evals"))
    from week7 import load_cases, race
    runs = race("agent", load_cases(RACE), os.path.join(OUT, f"agent_runs_{args.label}.jsonl"),
                budgets=None)
    res = score(runs)
    res["source_runs"] = f"reports/week8/agent_runs_{args.label}.jsonl"
    with open(os.path.join(OUT, f"trajectory_{args.label}.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=2, ensure_ascii=False)
    print_score(res, args.label)


def cmd_compare(_args):
    b = json.load(open(os.path.join(OUT, "trajectory_before.json"), encoding="utf-8"))["summary"]
    a = json.load(open(os.path.join(OUT, "trajectory_after.json"), encoding="utf-8"))["summary"]
    lines = ["| Mode | Before | After | Change |", "|---|---:|---:|---|"]
    for m in MODES:
        x, y = b["mode_counts"][m], a["mode_counts"][m]
        tag = "worse" if y > x else ("better" if y < x else "same")
        if x == 0 and y > 0:
            tag = "NEW"
        lines.append(f"| {m} | {x} | {y} | {tag} |")
    lines += ["", "| Metric | Before | After |", "|---|---:|---:|"]
    for k, fmt in [("tool_choice_accuracy", "{:.0%}"), ("argument_validity", "{:.0%}"),
                   ("step_efficiency", "{:.2f}"), ("cost_p50", "${:.5f}"), ("cost_max", "${:.5f}"),
                   ("cost_mean", "${:.5f}"), ("tokens_per_claim", "{:,.0f}"),
                   ("latency_p50", "{:.2f}s"), ("outcome_pass_rate", "{:.0%}"),
                   ("trajectory_pass_rate", "{:.0%}"), ("gap", "{:+.2f}")]:
        lines.append(f"| {k} | {fmt.format(b[k])} | {fmt.format(a[k])} |")
    text = "\n".join(lines)
    with open(os.path.join(OUT, "compare.md"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text)


def cmd_paths(_args):
    for spec in _jsonl(SPECS):
        paths = accepted_paths(spec)
        print(f"{spec['claim_number']}  ({len(paths)} accepted)  {spec['why']}")
        for p in paths:
            print("    " + " → ".join(p))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["score", "run", "compare", "paths"])
    ap.add_argument("--runs")
    ap.add_argument("--label", default="before")
    args = ap.parse_args()
    {"score": cmd_score, "run": cmd_run, "compare": cmd_compare, "paths": cmd_paths}[args.cmd](args)


if __name__ == "__main__":
    main()
