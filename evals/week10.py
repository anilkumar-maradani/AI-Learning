#!/usr/bin/env python3
"""
Week 10 — race the claims squad (orchestrator + 2 workers) against the single agent.

    python evals/week10.py single              # agent.py over the 10 cases
    python evals/week10.py squad               # squad.py over the same 10
    python evals/week10.py judge               # Week 6 judge v2 over both arms' answers
    python evals/week10.py table               # race_table.md, handoffs.log, multiplier.txt
    python evals/week10.py fail --case 2       # squad with the exclusions worker returning HTTP 500
    python evals/week10.py squad --cases 10    # re-run only these cases; the others are kept

Groq's free tier caps each model at 200K tokens per DAY. A run that hits that cap
is an infrastructure failure, not a result: it is flagged (quota_hit), the runner
stops, and the case is re-run later with --cases. `judge` saves after every
verdict and skips runs already judged, so it resumes; a judge call that errors is
never recorded as a FAIL. `table` refuses to run while any case is unjudged or
quota-hit.

The cases are the first 10 of evals/cases/week6_cases.jsonl, by id: no new cases,
no picking. Both arms see the claim file with the adjuster's decision note
withheld (tools.get_claim); the judge sees the whole file, decision included,
exactly as in Week 6.

The judge grades the same rendering of each arm's answer: decision, exclusions
relied on, amount payable. Free-text reasons are not shown to it, so neither arm
is failed for quoting policy wording the claim file does not contain.

Latency is model + tool time; rate-limit sleeps (Groq free tier, 8K tokens/min)
are excluded, as in Weeks 7-8. p99 over 10 runs is the nearest-rank p99, which
is the slowest run.
"""

import argparse
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from console import enable_utf8  # noqa: E402

enable_utf8()

CASES = os.path.join(ROOT, "evals", "cases", "week6_cases.jsonl")
OUT = os.path.join(ROOT, "reports", "week10")
N_CASES = 10
JUDGE_VERSION = "v2"
TPM = 8000
ARMS = ("single", "squad")


def _jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _write_jsonl(rows, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write(name, text):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote reports/week10/{name}")


def load_cases():
    return sorted(_jsonl(CASES), key=lambda c: c["id"])[:N_CASES]


def runs_path(arm):
    return os.path.join(OUT, f"{arm}_runs.jsonl")


def pace(tokens):
    """Let the per-minute token window refill. Not timed."""
    time.sleep(min(70, tokens / TPM * 60))


def warm_up():
    from tools import search_policy
    search_policy("warm up the embedding model and BM25 index")


# -- race ---------------------------------------------------------------------

def quota_hit(run) -> bool:
    """True if any model call in the run died on the provider's DAILY token cap."""
    calls = (run.get("handoffs") or []) + (run.get("steps") or [])
    return any(isinstance(c.get("error"), dict) and
               (c["error"].get("quota") or "tokens per day" in c["error"].get("message", ""))
               for c in calls)


def cmd_race(arm, args):
    from agent import run_agent
    from squad import run_squad
    only = {int(x) for x in args.cases.split(",")} if args.cases else None
    runs = {}
    if only and os.path.exists(runs_path(arm)):
        runs = {r["case"]["id"]: r for r in _jsonl(runs_path(arm))}
    warm_up()
    for case in load_cases():
        if only and case["id"] not in only:
            continue
        print(f"{arm} case {case['id']} {case['claim_number']} ({case['mode']})", flush=True)
        r = run_agent(case["claim_number"], log=print) if arm == "single" else \
            run_squad(case["claim_number"], log=print)
        r["case"] = case
        print(f"  -> {(r['answer'] or {}).get('decision')} payable={(r['answer'] or {}).get('payable')} | "
              f"{r['tokens']} tok ${r['cost_usd']:.5f} {r['latency_s']}s", flush=True)
        runs[case["id"]] = r
        if quota_hit(r):
            print(f"  DAILY TOKEN QUOTA hit on case {case['id']}: stopping. Re-run it later with "
                  f"--cases {case['id']}", flush=True)
            break
        pace(r["tokens"])
    _write_jsonl([runs[k] for k in sorted(runs)], runs_path(arm))


# -- judge --------------------------------------------------------------------

def answer_text(claim_number, answer):
    """What the judge reads, identical for both arms."""
    if not answer:
        return f"Claim {claim_number}: no answer was produced."
    excl = ", ".join(answer.get("exclusion_ids") or []) or "none"
    pay = answer.get("payable")
    pay = f"${float(pay):,.2f}" if isinstance(pay, (int, float)) else "none stated"
    return (f"Claim {claim_number}: coverage decision {answer.get('decision')}; "
            f"exclusions relied on: {excl}; amount payable: {pay}.")


def judge_runs(runs, save=None) -> bool:
    """Judge every run that has no verdict yet. A failed judge call records nothing
    (judge.py would otherwise turn it into a FAIL) and returns False."""
    from claim_store import get_claim
    from judge import judge_summary, load_judge_prompt
    prompt = load_judge_prompt(JUDGE_VERSION)
    for r in runs:
        if (r.get("judge") or {}).get("verdict"):
            continue
        text = answer_text(r["claim_number"], r.get("answer"))
        v = judge_summary(prompt, get_claim(r["claim_number"]), text)
        if v["error"]:
            print(f"  judge call failed on case {r['case']['id']}: {v['error']['message'][:160]}", flush=True)
            return False
        r["judged_text"] = text
        r["judge"] = {"version": JUDGE_VERSION, "verdict": v["verdict"], "reason": v["reason"],
                      "tokens": v["usage"]["total"]}
        print(f"  {r.get('system')} case {r['case']['id']}: {v['verdict']}  {text}", flush=True)
        if save:
            save()
        pace(v["usage"]["total"])
    return True


def cmd_judge(_args):
    for arm in ARMS:
        runs = _jsonl(runs_path(arm))
        hit = [r["case"]["id"] for r in runs if quota_hit(r)]
        if hit:
            sys.exit(f"{arm}: cases {hit} hit the daily token quota; re-run them with "
                     f"`{arm} --cases {','.join(map(str, hit))}` before judging")
        ok = judge_runs(runs, save=lambda: _write_jsonl(runs, runs_path(arm)))
        _write_jsonl(runs, runs_path(arm))
        if not ok:
            sys.exit("stopped: a judge call failed and nothing was recorded for it. Run `judge` again to resume.")


# -- table --------------------------------------------------------------------

def p99(values):
    s = sorted(values)
    return s[math.ceil(0.99 * len(s)) - 1]


def four_numbers(runs):
    lat = [r["latency_s"] for r in runs]
    return {
        "pass_rate": sum(r["judge"]["verdict"] == "PASS" for r in runs) / len(runs),
        "p50": statistics.median(lat),
        "p99": p99(lat),
        "tokens": sum(r["tokens"] for r in runs),
        "cost_per_claim": sum(r["cost_usd"] for r in runs) / len(runs),
    }


def handoff_rows(run):
    """(hand-off name, grouped name, usage) for every model call in a run."""
    if run["system"] == "single":
        out = []
        for u in run["lap_usage"]:
            name = "agent lap 1 (system + question)" if u["lap"] == 1 else \
                f"agent lap {u['lap']} (whole conversation re-sent)"
            group = "agent lap 1" if u["lap"] == 1 else "agent laps 2+ (conversation re-send)"
            out.append((name, group, u))
        return out
    return [(c["handoff"], c["handoff"].split(" (lap")[0], c) for c in run["handoffs"]]


def cmd_table(_args):
    runs = {arm: _jsonl(runs_path(arm)) for arm in ARMS}
    for arm in ARMS:
        for r in runs[arm]:
            r["system"] = arm
            if quota_hit(r) or not (r.get("judge") or {}).get("verdict"):
                sys.exit(f"{arm} case {r['case']['id']}: quota-hit or unjudged run; finish the race first")
    ids = [[r["case"]["id"] for r in runs[a]] for a in ARMS]
    assert ids[0] == ids[1], "the two arms did not run the same cases"
    n = {arm: four_numbers(runs[arm]) for arm in ARMS}
    s, m = n["single"], n["squad"]
    case_names = ", ".join(f"{r['case']['id']} ({r['claim_number']})" for r in runs["single"])

    # hand-off log
    log_lines, totals = [], {arm: defaultdict(int) for arm in ARMS}
    for arm in ARMS:
        log_lines.append(f"# {arm}: one line per model call (hand-off), tokens = prompt + completion")
        for r in runs[arm]:
            for name, group, u in handoff_rows(r):
                totals[arm][group] += u["total"]
                log_lines.append(f"case {r['case']['id']:>2} {r['claim_number']} | {arm:<6} | {name:<48} | "
                                 f"prompt {u['prompt']:>6} | completion {u['completion']:>5} | total {u['total']:>6}")
        log_lines.append("")
    all_tokens = {arm: sum(totals[arm].values()) for arm in ARMS}
    for arm in ARMS:
        log_lines.append(f"# {arm}: tokens by hand-off, all 10 cases ({all_tokens[arm]:,} total)")
        for group, tok in sorted(totals[arm].items(), key=lambda kv: -kv[1]):
            log_lines.append(f"  {group:<48} {tok:>8,}  {tok / all_tokens[arm]:6.1%}")
        log_lines.append("")
    _write("handoffs.log", "\n".join(log_lines))

    # multiplier
    mult = m["tokens"] / s["tokens"]
    top_group, top_tok = max(totals["squad"].items(), key=lambda kv: kv[1])
    biggest = max(((name, u["total"], r) for r in runs["squad"] for name, _g, u in handoff_rows(r)),
                  key=lambda x: x[1])
    mult_line = (f"Context re-send multiplier: squad {m['tokens']:,} / single {s['tokens']:,} tokens = "
                 f"{mult:.1f}x. Largest share: {top_group} (every lap re-sends the brief, the notes "
                 f"worker's facts and the form wording read so far), {top_tok / m['tokens']:.0%} of all "
                 f"squad tokens. Largest single hand-off: {biggest[0]} on case {biggest[2]['case']['id']}, "
                 f"{biggest[1]:,} tokens.\n")
    _write("multiplier.txt", mult_line)

    # race table
    rows = [
        "| | Single agent (`src/agent.py`) | Squad (`src/squad.py`) |", "|---|---:|---:|",
        f"| Pass rate (Week 6 judge {JUDGE_VERSION}) | {s['pass_rate']:.0%} | {m['pass_rate']:.0%} |",
        f"| p50 latency (s) | {s['p50']:.2f} | {m['p50']:.2f} |",
        f"| p99 latency (s) | {s['p99']:.2f} | {m['p99']:.2f} |",
        f"| Total tokens (10 cases, every call) | {s['tokens']:,} | {m['tokens']:,} |",
        f"| Cost per claim (USD) | ${s['cost_per_claim']:.5f} | ${m['cost_per_claim']:.5f} |",
    ]
    per_case = ["| Case | Claim | Mode | Adjuster decided | Single | Squad |", "|---|---|---|---|---|---|"]
    for a, b in zip(runs["single"], runs["squad"]):
        c = a["case"]
        exp = c["expected_decision"] + (f" {'/'.join(c['expected_exclusion_ids'])}" if c["expected_exclusion_ids"] else "")
        cell = lambda r: (f"{r['judge']['verdict']}: {(r.get('answer') or {}).get('decision')} "  # noqa: E731
                          f"{'/'.join((r.get('answer') or {}).get('exclusion_ids') or [])} "
                          f"${(r.get('answer') or {}).get('payable')}").replace("$None", "no payable")
        per_case.append(f"| {c['id']} | {c['claim_number']} | {c['mode']} | {exp} | {cell(a)} | {cell(b)} |")
    judge_tokens = sum(r["judge"]["tokens"] for arm in ARMS for r in runs[arm])
    text = "\n".join([
        "# Week 10 race: single agent vs claims squad", "",
        f"Same 10 Week 6 cases (the first 10 of `evals/cases/week6_cases.jsonl`, by id): {case_names}.",
        f"Same judge: `reports/week6/judge_{JUDGE_VERSION}.txt`. Same model (`gpt-oss-120b`), same tools, "
        "same output contract (`src/triage.py`).", "",
        *rows, "",
        mult_line,
        f"Judge tokens ({judge_tokens:,} over 20 verdicts) are the ruler, not the arms, and are counted in neither column.",
        "p99 over 10 runs is nearest-rank, i.e. the slowest run.", "",
        "## Per case", "", *per_case, "",
    ])
    _write("race_table.md", text)
    print(text)


# -- failure ------------------------------------------------------------------

def cmd_fail(args):
    from squad import run_squad
    case = next(c for c in load_cases() if c["id"] == args.case)
    warm_up()
    r = run_squad(case["claim_number"], inject=args.worker, log=print)
    r["case"] = case
    r["system"] = "squad"
    if quota_hit(r):
        sys.exit("daily token quota hit during the failure run; try again later")
    pace(r["tokens"])
    if not judge_runs([r]):
        sys.exit("judge call failed; failure run not saved")
    _write_jsonl([r], os.path.join(OUT, "failure_run.jsonl"))
    print(json.dumps({"answer": r["answer"], "worker_failures": r["worker_failures"],
                      "judge": r["judge"]}, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["single", "squad", "judge", "table", "fail"])
    ap.add_argument("--case", type=int, default=2)
    ap.add_argument("--worker", default="exclusions_worker")
    ap.add_argument("--cases", help="comma-separated case ids to (re-)run; the others are kept")
    args = ap.parse_args()
    if args.cmd in ARMS:
        cmd_race(args.cmd, args)
    else:
        {"judge": cmd_judge, "table": cmd_table, "fail": cmd_fail}[args.cmd](args)


if __name__ == "__main__":
    main()
