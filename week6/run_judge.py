"""
run_judge.py — Run LLM judge v1 and v2, compute agreement with human labels.

Steps:
  1. Load eval cases + generated summaries + human labels
  2. Run all 4 deterministic assertions per case
  3. Run LLM judge v1 on each case
  4. Compute agreement_v1 = matching verdicts / 25
  5. Find disagreements (human ≠ judge)
  6. Build judge_v2.txt by appending 2 disagreements as few-shot examples
  7. Run LLM judge v2 on each case
  8. Compute agreement_v2
  9. Save all results to judge_results.json

Usage:
    python week6/run_judge.py                   # full run
    python week6/run_judge.py --v1-only         # just v1
    python week6/run_judge.py --skip-generate   # skip summary generation
"""

import argparse
import json
import os
import sys
import time

WEEK6_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(WEEK6_DIR)

sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from generation import get_client, get_model     # noqa: E402


# ───────────────────────────────────────────────────────────────
# Loaders
# ───────────────────────────────────────────────────────────────

def load_cases(path: str = None) -> list[dict]:
    path = path or os.path.join(WEEK6_DIR, "eval_cases_25.jsonl")
    cases = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def load_summaries(path: str = None) -> list[dict]:
    path = path or os.path.join(WEEK6_DIR, "summaries_25.json")
    with open(path) as fh:
        return json.load(fh)


def load_labels(path: str = None) -> list[dict]:
    path = path or os.path.join(WEEK6_DIR, "labels_25.json")
    with open(path) as fh:
        return json.load(fh)


def load_judge_prompt(version: str = "v1") -> str:
    path = os.path.join(WEEK6_DIR, f"judge_{version}.txt")
    with open(path) as fh:
        return fh.read()


# ───────────────────────────────────────────────────────────────
# Judge execution
# ───────────────────────────────────────────────────────────────

def run_judge_on_summary(
    judge_prompt: str,
    adjuster_notes: str,
    summary: str,
    sleep: float = 1.0,
) -> dict:
    """Run one judge evaluation. Returns verdict + raw output."""
    client = get_client()
    model = get_model()

    user_msg = (
        f"ADJUSTER NOTES:\n{adjuster_notes}\n\n"
        f"CLAIM SUMMARY:\n{summary}\n\n"
        f"Evaluate this summary now."
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": judge_prompt},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.0,
        max_tokens=200,
    )

    output = response.choices[0].message.content.strip()
    verdict = "PASS" if output.upper().startswith("PASS") else "FAIL"
    time.sleep(sleep)
    return {"verdict": verdict, "raw": output}


def run_judge_batch(
    judge_prompt: str,
    cases: list[dict],
    summaries: list[dict],
    sleep: float = 1.0,
) -> list[dict]:
    """Run the judge on all cases. Returns list of verdict dicts."""
    summary_by_id = {s["id"]: s["summary"] for s in summaries}
    verdicts = []

    for case in cases:
        cid = case["id"]
        summary = summary_by_id.get(cid, "")
        if summary.startswith("ERROR:"):
            verdicts.append({"verdict": "FAIL", "raw": f"Summary generation failed: {summary}"})
            continue

        print(f"    Judging case {cid:>2} (mode={case['mode']})…", end=" ", flush=True)
        try:
            v = run_judge_on_summary(judge_prompt, case["adjuster_notes"], summary, sleep)
        except Exception as exc:
            v = {"verdict": "FAIL", "raw": f"Judge error: {type(exc).__name__}: {exc}"}
        print(v["verdict"])
        verdicts.append(v)

    return verdicts


# ───────────────────────────────────────────────────────────────
# Agreement
# ───────────────────────────────────────────────────────────────

def compute_agreement(labels: list[dict], verdicts: list[dict]) -> float:
    """Percentage of cases where human label == judge verdict."""
    matches = sum(
        1 for h, j in zip(labels, verdicts)
        if h["human_label"] == j["verdict"]
    )
    return round(matches / len(labels) * 100, 1)


def find_disagreements(
    labels: list[dict],
    verdicts: list[dict],
    cases: list[dict],
    summaries: list[dict],
) -> list[dict]:
    """Return cases where human ≠ judge."""
    summary_by_id = {s["id"]: s["summary"] for s in summaries}
    disagreements = []
    for h, j, case in zip(labels, verdicts, cases):
        if h["human_label"] != j["verdict"]:
            disagreements.append({
                "id":              case["id"],
                "mode":            case["mode"],
                "human_label":     h["human_label"],
                "human_notes":     h.get("notes", ""),
                "judge_verdict":   j["verdict"],
                "judge_reason":    j["raw"],
                "adjuster_notes":  case["adjuster_notes"],
                "summary":         summary_by_id.get(case["id"], ""),
            })
    return disagreements


# ───────────────────────────────────────────────────────────────
# Build judge_v2.txt from disagreements
# ───────────────────────────────────────────────────────────────

def build_judge_v2(disagreements: list[dict], max_examples: int = 2) -> str:
    """Append few-shot calibration examples to the v1 prompt."""
    v1 = load_judge_prompt("v1")

    if not disagreements:
        print("  ⚠ No disagreements to add — v2 = v1")
        return v1

    examples = disagreements[:max_examples]
    lines = [
        v1.rstrip(),
        "",
        "",
        "═══════════════════════════════════════════════════════════════",
        "CALIBRATION EXAMPLES",
        "(from cases where my previous version disagreed with a human reviewer)",
        "═══════════════════════════════════════════════════════════════",
        "",
    ]

    for i, d in enumerate(examples, 1):
        # Determine who was right based on analysis
        correct_label = d["human_label"]  # default to human
        lines.extend([
            f"── Example {i} (Case {d['id']}, mode: {d['mode']}) ──",
            "",
            f"ADJUSTER NOTES:",
            d["adjuster_notes"],
            "",
            f"SUMMARY:",
            d["summary"],
            "",
            f"HUMAN REVIEWER LABEL: {d['human_label']}",
            f"MY PREVIOUS VERDICT:  {d['judge_verdict']}",
            f"CORRECT VERDICT:      {correct_label}",
            f"EXPLANATION:          The human reviewer noted: \"{d['human_notes']}\"",
            "",
        ])

    lines.append("Use these examples to calibrate your judgment on similar cases.")

    v2_text = "\n".join(lines) + "\n"

    v2_path = os.path.join(WEEK6_DIR, "judge_v2.txt")
    with open(v2_path, "w") as fh:
        fh.write(v2_text)
    print(f"  ✓ Wrote judge_v2.txt with {len(examples)} calibration examples")
    return v2_text


# ───────────────────────────────────────────────────────────────
# Assertions (delegate to assertions.py)
# ───────────────────────────────────────────────────────────────

def run_assertions_batch(cases, summaries):
    """Run all 4 deterministic assertions on every case."""
    sys.path.insert(0, WEEK6_DIR)
    from assertions import run_all_assertions

    summary_by_id = {s["id"]: s["summary"] for s in summaries}
    all_results = []
    for case in cases:
        summary = summary_by_id.get(case["id"], "")
        results = run_all_assertions(summary, case)
        all_results.append({
            "id": case["id"],
            "mode": case["mode"],
            "assertions": results,
            "all_passed": all(r["passed"] for r in results),
        })
    return all_results


# ───────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Run judge v1/v2 and measure agreement")
    ap.add_argument("--v1-only", action="store_true",
                    help="Only run v1, skip v2")
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="Seconds between API calls (default 1.0)")
    args = ap.parse_args()

    print("=" * 60)
    print("  Week 6 — Judge Validation Runner")
    print("=" * 60)

    # Load data
    print("\n▸ Loading data…")
    cases     = load_cases()
    summaries = load_summaries()
    labels    = load_labels()
    print(f"  {len(cases)} cases, {len(summaries)} summaries, {len(labels)} labels")

    # 1. Deterministic assertions
    print("\n▸ Running deterministic assertions…")
    assertion_results = run_assertions_batch(cases, summaries)
    a_pass = sum(1 for r in assertion_results if r["all_passed"])
    print(f"  Assertions passed: {a_pass}/{len(cases)}")

    # 2. Judge v1
    print("\n▸ Running LLM judge v1…")
    v1_prompt  = load_judge_prompt("v1")
    v1_verdicts = run_judge_batch(v1_prompt, cases, summaries, sleep=args.sleep)
    agreement_v1 = compute_agreement(labels, v1_verdicts)
    print(f"\n  Agreement (v1): {agreement_v1}%")

    # 3. Find disagreements
    disagreements = find_disagreements(labels, v1_verdicts, cases, summaries)
    print(f"  Disagreements: {len(disagreements)}")
    for d in disagreements:
        print(f"    Case {d['id']:>2}: human={d['human_label']}, "
              f"judge={d['judge_verdict']} (mode={d['mode']})")

    # 4. Build v2 and run
    agreement_v2 = None
    v2_verdicts = None
    if not args.v1_only:
        print("\n▸ Building judge v2 from disagreements…")
        v2_prompt = build_judge_v2(disagreements)

        print("\n▸ Running LLM judge v2…")
        v2_verdicts = run_judge_batch(v2_prompt, cases, summaries, sleep=args.sleep)
        agreement_v2 = compute_agreement(labels, v2_verdicts)
        print(f"\n  Agreement (v2): {agreement_v2}%")

    # 5. Save results
    results = {
        "assertion_results": assertion_results,
        "assertions_passed": a_pass,
        "assertions_total": len(cases),
        "v1_verdicts": v1_verdicts,
        "agreement_v1": agreement_v1,
        "disagreements": disagreements,
        "v2_verdicts": v2_verdicts,
        "agreement_v2": agreement_v2,
    }

    results_path = os.path.join(WEEK6_DIR, "judge_results.json")
    with open(results_path, "w") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)
    print(f"\n  ✓ Full results → {results_path}")

    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"  Deterministic assertions: 4 (passed {a_pass}/{len(cases)})")
    print(f"  Judged criteria (subjective): 3")
    print(f"  Agreement (v1 — before): {agreement_v1}%")
    if agreement_v2 is not None:
        print(f"  Agreement (v2 — after):  {agreement_v2}%")
    print(f"  Disagreements analyzed:  {len(disagreements)}")


if __name__ == "__main__":
    main()
