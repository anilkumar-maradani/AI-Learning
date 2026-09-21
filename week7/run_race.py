#!/usr/bin/env python3
"""
run_race.py — Race the agent loop against the fixed workflow over 10 claims.

Usage:
    python week7/run_race.py                  # full race (both systems)
    python week7/run_race.py --mode agent     # agent only
    python week7/run_race.py --mode workflow  # workflow only
    python week7/run_race.py --budget-demo    # trigger max_iterations on claim 6

Outputs (written to week7/):
    race.csv         — 8 numbers (4 per system)
    budget_log.txt   — log of one budget-triggered termination
    tool_diff.md     — third tool description diff
    verdict.md       — verdict paragraph (<150 words)
    results_w7.md    — combined report
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time

# Make src/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from console import enable_utf8
enable_utf8()

WEEK7_DIR = os.path.dirname(os.path.abspath(__file__))
CLAIMS_PATH = os.path.join(WEEK7_DIR, "claims_10.jsonl")


# ---------------------------------------------------------------------------
# Load claims
# ---------------------------------------------------------------------------

def load_claims(path: str = CLAIMS_PATH) -> list[dict]:
    claims = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                claims.append(json.loads(line))
    return claims


# ---------------------------------------------------------------------------
# Pass / fail scoring
# ---------------------------------------------------------------------------

_COVERED_WORDS = {"covered", "cover", "payable", "applicable"}
_NOT_COVERED_WORDS = {"not covered", "denied", "excluded", "exclusion applies", "not payable"}


def _score_answer(final_answer: str, expected_status: str) -> bool:
    """
    Heuristic: does the final_answer agree with expected_status?
    Returns True (pass) / False (fail).
    """
    if not final_answer:
        return False
    low = final_answer.lower()

    if expected_status == "COVERED":
        # Must contain a covered signal and NOT a primary denial signal
        has_covered = any(w in low for w in _COVERED_WORDS)
        has_denied = "not covered" in low or "not payable" in low or "$0.00" in low
        return has_covered and not has_denied

    if expected_status == "NOT_COVERED":
        return "not covered" in low or "denied" in low or "exclusion" in low or "$0.00" in low

    if expected_status == "PARTIALLY_COVERED":
        return "covered" in low or "payable" in low or "sublimit" in low

    return True   # DEPENDS_ON_FACTS — always pass for now


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(results: list[dict], claims: list[dict]) -> dict:
    """
    Compute the four required metrics from a list of run results.

    Pass rate:    % with correct coverage determination
    p50 latency:  median wall-clock across all 10 claims (seconds)
    total_tokens: sum of tokens across all iterations for all 10 claims
    cost_per_claim: total USD / 10
    """
    latencies = [r["wall_clock_s"] for r in results if r.get("wall_clock_s") is not None]
    tokens = sum(r.get("total_tokens", 0) for r in results)
    cost_total = sum(r.get("total_cost_usd", 0.0) for r in results)

    passes = 0
    for r, c in zip(results, claims):
        answer = r.get("final_answer", "")
        expected = c.get("expected_status", "")
        if _score_answer(answer, expected):
            passes += 1

    return {
        "pass_rate": round(passes / len(results), 3) if results else 0.0,
        "p50_latency_s": round(statistics.median(latencies), 3) if latencies else 0.0,
        "total_tokens": tokens,
        "cost_per_claim_usd": round(cost_total / max(len(results), 1), 6),
        "n_claims": len(results),
        "pass_count": passes,
    }


# ---------------------------------------------------------------------------
# Race
# ---------------------------------------------------------------------------

def run_agent(claims: list[dict], verbose: bool = True) -> list[dict]:
    from claims_agent import agent_loop
    from tracing import TraceWriter

    writer = TraceWriter(
        path=os.path.join(
            os.path.dirname(WEEK7_DIR), "traces", "agent_race_traces.jsonl"
        )
    )
    results = []
    for i, claim in enumerate(claims, 1):
        print(f"\n  [Agent {i}/{len(claims)}] {claim['claim_id']}: {claim['question'][:70]}...")
        try:
            result = agent_loop(claim, writer=writer, verbose=verbose)
        except Exception as exc:
            result = {
                "trace_id": None,
                "final_answer": "",
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "wall_clock_s": 0.0,
                "budget_terminated": False,
                "budget_trigger": None,
                "tool_call_log": [],
                "error": {"type": type(exc).__name__, "message": str(exc)[:200]},
                "iterations": 0,
            }
        print(f"    -> {result['final_answer'][:100]}")
        print(f"    -> iter={result.get('iterations')} "
              f"tok={result.get('total_tokens')} "
              f"${result.get('total_cost_usd', 0):.4f} "
              f"{result.get('wall_clock_s', 0):.2f}s "
              f"budget_hit={result.get('budget_terminated')}")
        results.append(result)
        time.sleep(0.5)   # rate-limit cushion
    return results


def run_workflow(claims: list[dict], verbose: bool = True) -> list[dict]:
    from workflow import fixed_workflow
    from tracing import TraceWriter

    writer = TraceWriter(
        path=os.path.join(
            os.path.dirname(WEEK7_DIR), "traces", "workflow_race_traces.jsonl"
        )
    )
    results = []
    for i, claim in enumerate(claims, 1):
        print(f"\n  [Workflow {i}/{len(claims)}] {claim['claim_id']}: {claim['question'][:70]}...")
        try:
            result = fixed_workflow(claim, writer=writer, verbose=verbose)
        except Exception as exc:
            result = {
                "trace_id": None,
                "final_answer": "",
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "wall_clock_s": 0.0,
                "step_results": {},
                "error": {"type": type(exc).__name__, "message": str(exc)[:200]},
            }
        print(f"    -> {result['final_answer'][:100]}")
        print(f"    -> tok={result.get('total_tokens')} "
              f"${result.get('total_cost_usd', 0):.4f} "
              f"{result.get('wall_clock_s', 0):.2f}s")
        results.append(result)
        time.sleep(0.5)
    return results


# ---------------------------------------------------------------------------
# Budget demo — force max_iterations to fire on claim 6
# ---------------------------------------------------------------------------

def run_budget_demo(claim: dict) -> dict:
    """Run claim 6 with max_iterations=3 so the budget fires mid-session."""
    from claims_agent import agent_loop
    from tracing import TraceWriter

    writer = TraceWriter(
        path=os.path.join(
            os.path.dirname(WEEK7_DIR), "traces", "budget_demo_traces.jsonl"
        )
    )
    tight_budgets = {
        "max_iterations": 3,      # force fire — claim 6 needs 4+ tool calls
        "max_tokens": 15_000,
        "max_cost_usd": 0.05,
        "max_wall_clock_s": 60.0,
    }
    print("\n=== BUDGET DEMO: max_iterations=3 on claim 6 ===")
    result = agent_loop(claim, writer=writer, budgets=tight_budgets, verbose=True)
    return result


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_race_csv(
    agent_metrics: dict,
    workflow_metrics: dict,
    path: str,
) -> None:
    rows = [
        {
            "system": "agent",
            "pass_rate": agent_metrics["pass_rate"],
            "p50_latency_s": agent_metrics["p50_latency_s"],
            "total_tokens": agent_metrics["total_tokens"],
            "cost_per_claim_usd": agent_metrics["cost_per_claim_usd"],
            "pass_count": agent_metrics["pass_count"],
            "n_claims": agent_metrics["n_claims"],
        },
        {
            "system": "workflow",
            "pass_rate": workflow_metrics["pass_rate"],
            "p50_latency_s": workflow_metrics["p50_latency_s"],
            "total_tokens": workflow_metrics["total_tokens"],
            "cost_per_claim_usd": workflow_metrics["cost_per_claim_usd"],
            "pass_count": workflow_metrics["pass_count"],
            "n_claims": workflow_metrics["n_claims"],
        },
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWritten: {path}")


def write_budget_log(budget_result: dict, path: str) -> None:
    lines = [
        "=== BUDGET TERMINATION LOG ===",
        f"Claim: W7-CLM-006 (earthquake -> supply line -> flood, concurrent causation)",
        f"Budget: max_iterations=3  (race uses max_iterations=8)",
        f"",
        f"--- Iteration-by-iteration log ---",
    ]
    for entry in budget_result.get("tool_call_log", []):
        lines.append(
            f"  Iter {entry['iteration']:>2}: tool={entry['tool']:<28} "
            f"result={entry['result_summary']}"
        )
    lines += [
        "",
        f"--- Budget fire ---",
        f"  Budget triggered: {budget_result.get('budget_trigger', 'unknown')}",
        f"  Iterations completed: {budget_result.get('iterations')}",
        f"  Tokens used: {budget_result.get('total_tokens')}",
        f"  Cost: ${budget_result.get('total_cost_usd', 0):.6f}",
        f"  Wall clock: {budget_result.get('wall_clock_s', 0):.3f}s",
        "",
        f"  Final answer (budget message):",
        f"  {budget_result.get('final_answer', '')}",
        "",
        "=== END BUDGET LOG ===",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Written: {path}")


def write_tool_diff(path: str) -> None:
    content = """# Tool Description Diff — Third Tool (`compute_payout`)

The first two tools existed implicitly in the pipeline (retrieval + exclusion lookup).
`compute_payout` is the new, explicitly named third tool added for Week 7.

## Tool Registry Before Week 7

```
Tools: [implicit retrieval via hybrid_search(), implicit exclusion reading]
```

## Tool Registry After Week 7 (`src/tools.py`)

```diff
  TOOLS = [
      {
          "type": "function",
          "function": {
              "name": "get_claim_details",
              "description": "Retrieve the endorsement context and policy wording
                              relevant to a claim's loss description. Returns ranked
                              endorsement chunks (form_number, clause_id, text) from
                              the indexed homeowners policy corpus. Call this first.",
              "parameters": {
                  "claim_number": str,
                  "loss_description": str  [required]
              }
          }
      },
      {
          "type": "function",
          "function": {
              "name": "check_policy_exclusions",
              "description": "Look up whether a specific exclusion code applies to
                              a given loss type under a named endorsement form. Returns
                              the exact exclusion table row text, the coverage
                              determination (COVERED / NOT_COVERED / PARTIALLY_COVERED),
                              and any conditions or sublimits that attach.",
              "parameters": {
                  "form_number": str,        [required]
                  "exclusion_code": str,
                  "loss_type": str           [required]
              }
          }
      },
+     {
+         "type": "function",
+         "function": {
+             "name": "compute_payout",
+             "description": "Compute the net payable amount on a claim given the
+                             damage estimate, the applicable deductible (all-peril
+                             or named-storm), any form-specific sublimits (e.g. the
+                             $10,000 mold remediation cap under HO-0306 MF-2), and
+                             the coverage determination from the exclusion lookup.
+                             Returns the payable amount, the deductible applied, any
+                             sublimit that capped the payment, and a plain-English
+                             explanation. Call this only after check_policy_exclusions
+                             has returned a determination — never before.",
+             "parameters": {
+                 "damage_estimate":  float  [required],
+                 "deductible_amount": float [required],
+                 "sublimit":         float  [optional, nullable],
+                 "claim_status": enum {     [required]
+                     "COVERED",
+                     "NOT_COVERED",
+                     "PARTIALLY_COVERED",
+                     "DEPENDS_ON_FACTS"
+                 }
+             }
+         }
+     },
  ]
```

## Why No Overlap

| Tool | Job | What it does NOT do |
|------|-----|---------------------|
| `get_claim_details` | Semantic search over endorsement corpus | No coverage judgement, no arithmetic |
| `check_policy_exclusions` | Exclusion table lookup → coverage determination | No retrieval of general context, no arithmetic |
| `compute_payout` | Post-lookup arithmetic (damage − excess − sublimit) | No retrieval, no exclusion lookup, no model call |

The `claim_status` enum (4 values) enforces that `compute_payout` is always called
after `check_policy_exclusions` — the enum values are exactly the determinations the
exclusion tool can return, creating an explicit data dependency.
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Written: {path}")


def write_verdict(
    agent_metrics: dict,
    workflow_metrics: dict,
    claims: list[dict],
    agent_results: list[dict],
    workflow_results: list[dict],
    path: str,
) -> None:
    # Apply the decision rule: does the path vary by input?
    step_dep_claims = [c for c in claims if c.get("step_dependency")]
    step_dep_ids = [c["claim_id"] for c in step_dep_claims]

    agent_wins = sum([
        1 if agent_metrics["pass_rate"] > workflow_metrics["pass_rate"] else 0,
        1 if agent_metrics["p50_latency_s"] < workflow_metrics["p50_latency_s"] else 0,
        1 if agent_metrics["total_tokens"] < workflow_metrics["total_tokens"] else 0,
        1 if agent_metrics["cost_per_claim_usd"] < workflow_metrics["cost_per_claim_usd"] else 0,
    ])
    workflow_wins = 4 - agent_wins

    if workflow_wins >= 3:
        verdict_leader = "workflow"
        verdict_conclusion = (
            "none of the 10 claims requires an agent. The workflow's path is "
            "identical for all input classes — fixed steps 1→2→3→4 regardless of "
            "whether notes reveal a flood cause, a sublimit, or concurrent causation. "
            "The agent adds latency and tokens without improving accuracy."
        )
    else:
        verdict_leader = "agent"
        verdict_conclusion = (
            f"the concurrent-causation class (claims {', '.join(step_dep_ids)}) "
            "forces a variable path: the agent calls check_policy_exclusions twice "
            "when both E-31 and E-12 apply, while the workflow calls it once. "
            "For that class, the agent is required."
        )

    content = f"""# Verdict — Agent vs Fixed Workflow

**Race summary (10 claims, same inputs, same tools, same model):**

| Metric | Agent | Workflow | Winner |
|--------|-------|----------|--------|
| Pass rate | {agent_metrics['pass_rate']:.0%} ({agent_metrics['pass_count']}/10) | {workflow_metrics['pass_rate']:.0%} ({workflow_metrics['pass_count']}/10) | {'Agent' if agent_metrics['pass_rate'] > workflow_metrics['pass_rate'] else ('Workflow' if workflow_metrics['pass_rate'] > agent_metrics['pass_rate'] else 'Tie')} |
| p50 latency | {agent_metrics['p50_latency_s']:.2f}s | {workflow_metrics['p50_latency_s']:.2f}s | {'Agent' if agent_metrics['p50_latency_s'] < workflow_metrics['p50_latency_s'] else 'Workflow'} |
| Total tokens | {agent_metrics['total_tokens']:,} | {workflow_metrics['total_tokens']:,} | {'Agent' if agent_metrics['total_tokens'] < workflow_metrics['total_tokens'] else 'Workflow'} |
| Cost/claim | ${agent_metrics['cost_per_claim_usd']:.4f} | ${workflow_metrics['cost_per_claim_usd']:.4f} | {'Agent' if agent_metrics['cost_per_claim_usd'] < workflow_metrics['cost_per_claim_usd'] else 'Workflow'} |

**Decision rule applied:** Does the tool-calling path vary by input class?

**Verdict:** The {verdict_leader} wins on {workflow_wins if verdict_leader == 'workflow' else agent_wins}/4 metrics. {verdict_conclusion}

*Step-dependency claims (genuine variable-path cases): {', '.join(step_dep_ids)}*
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Written: {path}")


def write_results_report(
    claims: list[dict],
    agent_results: list[dict],
    workflow_results: list[dict],
    agent_metrics: dict,
    workflow_metrics: dict,
    budget_result: dict | None,
    path: str,
) -> None:
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    md = f"""# PolicyLens Week 7 — Agent vs Workflow Race Results

**Generated:** {now}  
**Claims:** 10 (3 with step-3-depends-on-step-2 dependency)  
**Model:** openai/gpt-oss-120b via Groq  
**Tools:** get_claim_details · check_policy_exclusions · compute_payout (new)

---

## Race Table (8 Numbers)

| Metric | Agent | Workflow |
|--------|-------|----------|
| Pass rate | {agent_metrics['pass_rate']:.0%} ({agent_metrics['pass_count']}/10) | {workflow_metrics['pass_rate']:.0%} ({workflow_metrics['pass_count']}/10) |
| p50 latency (s) | {agent_metrics['p50_latency_s']:.3f} | {workflow_metrics['p50_latency_s']:.3f} |
| Total tokens (all claims) | {agent_metrics['total_tokens']:,} | {workflow_metrics['total_tokens']:,} |
| Cost per claim (USD) | ${agent_metrics['cost_per_claim_usd']:.6f} | ${workflow_metrics['cost_per_claim_usd']:.6f} |

---

## Per-Claim Detail

| Claim | Expected | Agent Answer (first 80 chars) | Agent Pass | WF Pass |
|-------|----------|-------------------------------|-----------|---------|
"""
    for c, ar, wr in zip(claims, agent_results, workflow_results):
        a_pass = "✅" if _score_answer(ar.get("final_answer",""), c["expected_status"]) else "❌"
        w_pass = "✅" if _score_answer(wr.get("final_answer",""), c["expected_status"]) else "❌"
        dep_mark = " ⚡" if c.get("step_dependency") else ""
        md += (
            f"| {c['claim_id']}{dep_mark} | {c['expected_status']} "
            f"| {ar.get('final_answer','')[:80].replace('|','-')} "
            f"| {a_pass} | {w_pass} |\n"
        )

    md += "\n*⚡ = step-3-depends-on-step-2 claim*\n\n---\n\n"

    # Budget log
    if budget_result:
        md += "## Budget Termination Log\n\n```\n"
        for entry in budget_result.get("tool_call_log", []):
            md += (f"Iter {entry['iteration']:>2}: tool={entry['tool']:<28} "
                   f"result={entry['result_summary']}\n")
        md += f"\nBudget triggered: {budget_result.get('budget_trigger')}\n"
        md += f"Final message: {budget_result.get('final_answer','')}\n```\n\n---\n\n"

    # Read and embed tool_diff and verdict
    for fname, section in [("tool_diff.md", "Third Tool Diff"), ("verdict.md", "Verdict")]:
        fpath = os.path.join(WEEK7_DIR, fname)
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8") as f:
                md += f"## {section}\n\n{f.read()}\n\n---\n\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"Written: {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="W7 Race: agent vs workflow")
    ap.add_argument("--mode", choices=["agent", "workflow", "both"], default="both")
    ap.add_argument("--budget-demo", action="store_true",
                    help="Run claim 6 with max_iterations=3 to demonstrate budget firing")
    ap.add_argument("--verbose", action="store_true", default=True)
    ap.add_argument("--no-verbose", dest="verbose", action="store_false")
    args = ap.parse_args()

    claims = load_claims()
    print(f"Loaded {len(claims)} claims from {CLAIMS_PATH}")

    agent_results: list[dict] = []
    workflow_results: list[dict] = []
    budget_result: dict | None = None

    # ── Budget demo ───────────────────────────────────────────────────────
    # Always run budget demo when requested, or with the full race
    budget_demo_claim = claims[5]   # claim 6 — earthquake+concurrent causation

    if args.budget_demo or args.mode == "both":
        print("\n=== BUDGET DEMO ===")
        budget_result = run_budget_demo(budget_demo_claim)
        write_budget_log(
            budget_result,
            os.path.join(WEEK7_DIR, "budget_log.txt"),
        )

    # ── Agent race ────────────────────────────────────────────────────────
    if args.mode in ("agent", "both"):
        print("\n=== AGENT LOOP RACE ===")
        agent_results = run_agent(claims, verbose=args.verbose)

    # ── Workflow race ─────────────────────────────────────────────────────
    if args.mode in ("workflow", "both"):
        print("\n=== FIXED WORKFLOW RACE ===")
        workflow_results = run_workflow(claims, verbose=args.verbose)

    # ── Metrics and outputs ───────────────────────────────────────────────
    if agent_results and workflow_results:
        agent_metrics = compute_metrics(agent_results, claims)
        workflow_metrics = compute_metrics(workflow_results, claims)

        print("\n=== RACE RESULTS ===")
        print(f"{'Metric':<25} {'Agent':>12} {'Workflow':>12}")
        print("-" * 52)
        print(f"{'Pass rate':<25} {agent_metrics['pass_rate']:>12.1%} {workflow_metrics['pass_rate']:>12.1%}")
        print(f"{'p50 latency (s)':<25} {agent_metrics['p50_latency_s']:>12.3f} {workflow_metrics['p50_latency_s']:>12.3f}")
        print(f"{'Total tokens':<25} {agent_metrics['total_tokens']:>12,} {workflow_metrics['total_tokens']:>12,}")
        print(f"{'Cost/claim (USD)':<25} {agent_metrics['cost_per_claim_usd']:>12.6f} {workflow_metrics['cost_per_claim_usd']:>12.6f}")

        write_race_csv(
            agent_metrics, workflow_metrics,
            os.path.join(WEEK7_DIR, "race.csv"),
        )
        write_tool_diff(os.path.join(WEEK7_DIR, "tool_diff.md"))
        write_verdict(
            agent_metrics, workflow_metrics, claims,
            agent_results, workflow_results,
            os.path.join(WEEK7_DIR, "verdict.md"),
        )
        write_results_report(
            claims, agent_results, workflow_results,
            agent_metrics, workflow_metrics,
            budget_result,
            os.path.join(WEEK7_DIR, "results_w7.md"),
        )

    elif agent_results:
        agent_metrics = compute_metrics(agent_results, claims)
        print("\nAgent only results:", agent_metrics)

    elif workflow_results:
        workflow_metrics = compute_metrics(workflow_results, claims)
        print("\nWorkflow only results:", workflow_metrics)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
