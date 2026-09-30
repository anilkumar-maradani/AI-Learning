#!/usr/bin/env python3
"""
Week 6 — validate the claim-summary judge before trusting its number.

    python evals/week6.py                 # THE one command: assertions + judge, pass rate by mode
    python evals/week6.py produce         # "production" run over the 30 closed claims, traced
    python evals/week6.py select          # build the 25-case eval set (2+ regression cases from failed traces)
    python evals/week6.py summarise       # frozen summaries for the 25 cases
    python evals/week6.py label           # blind hand-labelling (human only); --full shows whole claim files
    python evals/week6.py judge --version v1
    python evals/week6.py iterate         # judge_v2 from 2 of v1's own disagreements
    python evals/week6.py judge --version v2

Protocol is enforced here, not just described:
  * `label` refuses to start once any judge result exists.
  * `judge` refuses to run unless labels_25.json is committed and unmodified,
    and records that commit hash in its output.
  * `iterate` refuses to run unless prediction.txt is committed.
"""

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))

from console import enable_utf8  # noqa: E402

enable_utf8()

from assertions import run_assertions  # noqa: E402
from claim_store import get_claim, render_claim_file  # noqa: E402
from tracing import EventWriter, read_traces  # noqa: E402

REPORT = os.path.join(ROOT, "reports", "week6")
POOL = os.path.join(ROOT, "evals", "cases", "week6_pool.jsonl")
CASES = os.path.join(ROOT, "evals", "cases", "week6_cases.jsonl")
PROD_TRACES = os.path.join(ROOT, "traces", "summariser_traces.jsonl")
SUMMARIES = os.path.join(REPORT, "summaries_25.json")
LABELS = os.path.join(REPORT, "labels_25.json")
PREDICTION = os.path.join(REPORT, "prediction.txt")
N_CASES = 25


def _jsonl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _dump(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def _committed_clean(path: str) -> str | None:
    """Commit hash that last touched `path`, or None if uncommitted / modified."""
    rel = os.path.relpath(path, ROOT).replace("\\", "/")
    commit = _git("log", "-1", "--format=%H", "--", rel)
    dirty = _git("status", "--porcelain", "--", rel)
    return commit if commit and not dirty else None


# ---------------------------------------------------------------------------
# produce / select / summarise
# ---------------------------------------------------------------------------

def cmd_produce(_args):
    from summariser import summarise
    writer = EventWriter(PROD_TRACES)
    pool = _jsonl(POOL)
    failed = 0
    for case in pool:
        claim = get_claim(case["claim_number"])
        out = summarise(claim)
        checks = run_assertions(out["summary"], case)
        ok = all(c["passed"] for c in checks)
        failed += not ok
        tid = writer.write({
            "kind": "claim_summary",
            "claim_ref": claim["claim_number"],
            "input_sha256": out["input_sha256"],
            "prompt_version": out["prompt_version"],
            "model": out["model"],
            "output": out["summary"],
            "assertions": checks,
            "assertions_passed": ok,
            "usage": out["usage"],
            "error": out["error"],
        }, known_names=[claim["claimant_name"]])
        print(f"  {tid}  {'ok  ' if ok else 'FAIL'}  {case['mode']}")
    print(f"\n{failed}/{len(pool)} production summaries failed an assertion -> {PROD_TRACES}")


def cmd_select(_args):
    """25 cases: every mode kept at >= 4, plus the first 2 failed production traces as regressions."""
    from redaction import redact_text
    pool = _jsonl(POOL)
    traces = [t for t in read_traces(PROD_TRACES) if t.get("kind") == "claim_summary"]
    by_ref = {}
    for case in pool:  # trace stores the pseudonymised claim ref; map it back through the store
        by_ref[redact_text(case["claim_number"])[0]] = case
    failed = [t for t in traces if not t["assertions_passed"] and not t.get("error")]
    if len(failed) < 2:
        sys.exit(f"Only {len(failed)} failed production traces; need 2 real failures for regression cases.")

    regressions, used_modes = [], set()
    for t in failed:  # prefer failures from different modes
        case = by_ref[t["claim_ref"]]
        if case["mode"] not in used_modes:
            regressions.append((case, t))
            used_modes.add(case["mode"])
        if len(regressions) == 2:
            break
    for t in failed:
        if len(regressions) == 2:
            break
        case = by_ref[t["claim_ref"]]
        if all(case is not r[0] for r in regressions):
            regressions.append((case, t))

    reg_ids = {c["claim_number"] for c, _ in regressions}
    rest = [c for c in pool if c["claim_number"] not in reg_ids]
    # drop from the biggest modes until 25 remain
    counts = defaultdict(int)
    for c in pool:
        counts[c["mode"]] += 1
    while len(rest) + len(regressions) > N_CASES:
        mode = max(counts, key=counts.get)
        victim = next(c for c in reversed(rest) if c["mode"] == mode)
        rest.remove(victim)
        counts[mode] -= 1

    cases = []
    for c in rest:
        cases.append({**c, "is_regression": False})
    for c, t in regressions:
        cases.append({**c, "is_regression": True, "source_trace_id": t["trace_id"],
                      "source_input_sha256": t["input_sha256"],
                      "source_failed_assertions": [a["name"] for a in t["assertions"] if not a["passed"]]})
    cases.sort(key=lambda c: c["claim_number"])
    for i, c in enumerate(cases, 1):
        c["id"] = i
    with open(CASES, "w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(c) + "\n")
    print(f"{len(cases)} cases -> {CASES}")
    for c, t in regressions:
        print(f"  regression: {c['claim_number']} from {t['trace_id']} ({c['mode']})")


def cmd_summarise(_args):
    from summariser import input_sha256, summarise
    out = []
    for case in _jsonl(CASES):
        claim = get_claim(case["claim_number"])
        if case["is_regression"] and input_sha256(claim) != case["source_input_sha256"]:
            sys.exit(f"{case['claim_number']}: input no longer matches trace {case['source_trace_id']}")
        res = summarise(claim)
        out.append({"id": case["id"], "claim_number": case["claim_number"],
                    "summary": res["summary"], "summary_sha256": _sha(res["summary"]),
                    "input_sha256": res["input_sha256"], "model": res["model"]})
        print(f"  [{case['id']:>2}] {case['claim_number']} {len(res['summary'])} chars")
    _dump({"generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "summaries": out}, SUMMARIES)
    print(f"-> {SUMMARIES}")


# ---------------------------------------------------------------------------
# label (human, blind)
# ---------------------------------------------------------------------------

def cmd_label(args):
    if any(f.startswith("judge_results") for f in os.listdir(REPORT)):
        sys.exit("A judge result already exists. Labels written now would not be blind.")
    summaries = {s["id"]: s for s in _load(SUMMARIES)["summaries"]}
    labels = _load(LABELS) if os.path.exists(LABELS) else {"labeller": None, "labels": []}
    if not labels["labeller"]:
        labels["labeller"] = input("Your name (recorded in the file): ").strip()
    done = {l["id"] for l in labels["labels"]}
    order = sorted(summaries)
    random.Random(6).shuffle(order)  # fixed shuffle so modes are not read in blocks
    print("Criterion (the judge's only one): would a reader of the summary alone get the SAME\n"
          "coverage outcome and payable amount the adjuster decided, with no unsupported facts?\n"
          "Ignore claim-number / date / deductible / exclusion-code formatting; code checks those.\n")
    for n, cid in enumerate(order, 1):
        if cid in done:
            continue
        s = summaries[cid]
        claim = get_claim(s["claim_number"])
        print("=" * 78)
        print(f"Summary {n}/{len(order)}  (case id {cid})  {claim['claim_number']}\n")
        if args.full:
            print(render_claim_file(claim))
        else:
            decision = claim["adjuster_notes"][-1]
            print(f"ADJUSTER'S DECISION [{decision['date']}]:\n  {decision['text']}")
        print("\n--- SUMMARY ---")
        print(s["summary"])
        print("-" * 78)
        verdict = ""
        while verdict not in ("P", "F"):
            prompt = "PASS or FAIL? [p/f]: " if args.full else "PASS or FAIL? [p/f, m = show full claim file]: "
            verdict = input(prompt).strip().upper()[:1]
            if verdict == "M":
                print("\n" + render_claim_file(claim) + "\n")
        reason = ""
        while not reason:
            reason = input("One-line reason (required): ").strip()
        labels["labels"].append({
            "id": cid, "claim_number": s["claim_number"],
            "human_label": "PASS" if verdict == "P" else "FAIL",
            "reason": reason, "summary_sha256": s["summary_sha256"],
            "view": "full" if args.full else "decision_note",
            "labelled_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        labels["labels"].sort(key=lambda l: l["id"])
        _dump(labels, LABELS)  # saved after every answer, so you can stop and resume
    print(f"\nAll {len(labels['labels'])} labelled -> {LABELS}")
    print("Next: commit this file on its own BEFORE any judge run.")


# ---------------------------------------------------------------------------
# judge / iterate
# ---------------------------------------------------------------------------

def _labels_or_exit():
    commit = _committed_clean(LABELS)
    if not commit:
        sys.exit("labels_25.json must be committed and unmodified before the judge runs.")
    labels = _load(LABELS)["labels"]
    if len(labels) < N_CASES:
        sys.exit(f"Only {len(labels)} labels; need {N_CASES}.")
    return commit, {l["id"]: l for l in labels}


def cmd_judge(args):
    from judge import judge_summary, load_judge_prompt
    labels_commit, labels = _labels_or_exit()
    prompt = load_judge_prompt(args.version)
    summaries = {s["id"]: s for s in _load(SUMMARIES)["summaries"]}
    rows = []
    for cid in sorted(summaries):
        s = summaries[cid]
        if labels[cid]["summary_sha256"] != s["summary_sha256"]:
            sys.exit(f"case {cid}: summary changed after it was labelled")
        v = judge_summary(prompt, get_claim(s["claim_number"]), s["summary"])
        agree = v["verdict"] == labels[cid]["human_label"]
        rows.append({"id": cid, "claim_number": s["claim_number"], "judge": v["verdict"],
                     "human": labels[cid]["human_label"], "agree": agree,
                     "judge_reason": v["reason"], "usage": v["usage"], "error": v["error"]})
        print(f"  [{cid:>2}] judge={v['verdict']} human={labels[cid]['human_label']} {'' if agree else '<-- disagree'}")
    agreement = sum(r["agree"] for r in rows) / len(rows)
    result = {
        "version": args.version,
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "labels_commit": labels_commit,
        "judge_prompt_sha256": _sha(prompt),
        "agreement": round(agreement, 4),
        "agreement_excluding_fewshot": None,
        "rows": rows,
    }
    if args.version != "v1":
        shots = _load(os.path.join(REPORT, "fewshot_ids.json"))["ids"]
        held = [r for r in rows if r["id"] not in shots]
        result["agreement_excluding_fewshot"] = round(sum(r["agree"] for r in held) / len(held), 4)
    _dump(result, os.path.join(REPORT, f"judge_results_{args.version}.json"))
    print(f"\nagreement_{args.version} = {agreement:.0%}  ({sum(r['agree'] for r in rows)}/{len(rows)})")
    if result["agreement_excluding_fewshot"] is not None:
        print(f"  on the {len(rows) - 2} cases not used as few-shot: {result['agreement_excluding_fewshot']:.0%}")


def cmd_iterate(_args):
    if not _committed_clean(PREDICTION):
        sys.exit("Write and commit reports/week6/prediction.txt before iterating.")
    v1 = _load(os.path.join(REPORT, "judge_results_v1.json"))
    _, labels = _labels_or_exit()
    summaries = {s["id"]: s for s in _load(SUMMARIES)["summaries"]}
    dis = [r for r in v1["rows"] if not r["agree"]]
    if len(dis) < 2:
        sys.exit(f"v1 has {len(dis)} disagreements; need 2 to iterate.")
    # one of each direction when possible: judge too lenient and judge too strict
    lenient = [r for r in dis if r["judge"] == "PASS"]
    strict = [r for r in dis if r["judge"] == "FAIL"]
    picks = ([lenient[0], strict[0]] if lenient and strict else dis[:2])
    blocks = []
    for n, r in enumerate(picks, 1):
        claim = get_claim(r["claim_number"])
        blocks.append(
            f"EXAMPLE {n} (a case you previously got wrong)\n"
            f"CLAIM FILE\n{render_claim_file(claim)}\n\n"
            f"SUMMARY\n{summaries[r['id']]['summary']}\n\n"
            f"Your earlier verdict: {r['judge']} ({r['judge_reason']})\n"
            f"Correct verdict: {labels[r['id']]['human_label']}\n"
            f"Why: {labels[r['id']]['reason']}"
        )
    v1_prompt = open(os.path.join(REPORT, "judge_v1.txt"), encoding="utf-8").read()
    v2 = v1_prompt.rstrip() + "\n\nWORKED EXAMPLES FROM YOUR OWN PAST MISTAKES\n\n" + "\n\n".join(blocks) + "\n"
    with open(os.path.join(REPORT, "judge_v2.txt"), "w", encoding="utf-8") as fh:
        fh.write(v2)
    _dump({"ids": [r["id"] for r in picks]}, os.path.join(REPORT, "fewshot_ids.json"))
    print(f"judge_v2.txt written with disagreements on case ids {[r['id'] for r in picks]}")


# ---------------------------------------------------------------------------
# default: the one command
# ---------------------------------------------------------------------------

def cmd_run(_args):
    cases = {c["id"]: c for c in _jsonl(CASES)}
    summaries = {s["id"]: s for s in _load(SUMMARIES)["summaries"]}
    judged = None
    for v in ("v2", "v1"):
        p = os.path.join(REPORT, f"judge_results_{v}.json")
        if os.path.exists(p):
            judged = _load(p)
            break
    verdicts = {r["id"]: r["judge"] for r in judged["rows"]} if judged else {}

    table = defaultdict(lambda: {"n": 0, "assert": 0, "judge": 0, "both": 0})
    n_assert_checks = 0
    for cid, case in cases.items():
        checks = run_assertions(summaries[cid]["summary"], case)
        n_assert_checks = len(checks)
        a_ok = all(c["passed"] for c in checks)
        j_ok = verdicts.get(cid) == "PASS"
        for key in (case["mode"], "regression" if case["is_regression"] else None, "ALL"):
            if key is None:
                continue
            row = table[key]
            row["n"] += 1
            row["assert"] += a_ok
            row["judge"] += j_ok
            row["both"] += a_ok and j_ok

    jv = judged["version"] if judged else "none (judge not run yet)"
    print(f"\nWeek 6 eval — {len(cases)} cases, {n_assert_checks} assertions + 1 judged criterion, judge {jv}\n")
    print(f"{'mode':<32}{'n':>3}  {'assertions':>10}  {'judge':>7}  {'pass rate':>9}")
    order = sorted(k for k in table if k not in ("regression", "ALL")) + ["regression", "ALL"]
    for k in order:
        if k not in table:
            continue
        r = table[k]
        j = f"{r['judge']}/{r['n']}" if judged else "-"
        rate = f"{r['both'] / r['n']:.0%}" if judged else "-"
        print(f"{k:<32}{r['n']:>3}  {r['assert']:>5}/{r['n']:<4}  {j:>7}  {rate:>9}")
    print("\npass = all assertions pass AND judge says PASS")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="run",
                    choices=["run", "produce", "select", "summarise", "label", "judge", "iterate"])
    ap.add_argument("--version", default="v1")
    ap.add_argument("--full", action="store_true",
                    help="label: show the whole claim file for every case (default shows the decision note)")
    args = ap.parse_args()
    {"run": cmd_run, "produce": cmd_produce, "select": cmd_select, "summarise": cmd_summarise,
     "label": cmd_label, "judge": cmd_judge, "iterate": cmd_iterate}[args.cmd](args)


if __name__ == "__main__":
    main()
