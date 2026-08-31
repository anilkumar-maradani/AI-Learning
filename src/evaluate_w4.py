"""
evaluate_w4.py — Golden-set retrieval evaluation: hit-rate@3, failure
                 labelling (R / G / Not-In-Corpus) and a vector-vs-hybrid
                 before/after comparison.

What this file does (in simple words):
  1. Loads the 12-question golden set (questions we know the right answer for)
  2. For each question, searches the database and checks if the correct chunk
     appears in the TOP 3 results (hit-rate@3)
  3. For every miss (wrong answer), looks at what WAS returned and labels WHY:
       R           = Retrieval failed (wrong chunks came back)
       G           = Good chunks came back, but AI would misuse them
       Not-In-Corpus = The answer doesn't exist in any document
  4. Times each query so we can report p50 latency (median response time)
  5. Can run against BOTH the old vector-only retriever and the new hybrid one

Usage:
    python src/evaluate_w4.py --strategy structure_aware
    python src/evaluate_w4.py --strategy hybrid
    python src/evaluate_w4.py --strategy both      # side-by-side table
"""

import os
import sys
import json
import time
import statistics
import argparse

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from retrieval import search as vector_search
from console import enable_utf8

enable_utf8()

GOLDEN_SET_PATH = os.path.join(os.path.dirname(__file__), "..", "golden_set.jsonl")

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"


def load_golden_set(path: str) -> list[dict]:
    """
    Load the 12 golden questions from the JSONL file.
    JSONL = one JSON object per line (like a list, but one item per line).
    """
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def check_hit_at_3(hits: list[dict], expected_form: str, expected_fragment: str) -> dict:
    """
    Check if the correct chunk appears in the top 3 results.

    A result is a HIT if ALL of these are true for any of the top-3 chunks:
      1. The chunk's form_number matches expected_form (e.g. "HO-0304")
      2. The expected text fragment appears somewhere in the chunk's text

    Returns:
        {
          "hit": True/False,
          "hit_rank": 1/2/3/None,
          "top3_forms": [list of form numbers in top 3],
          "top3_clause_ids": [list of clause_ids in top 3],
        }
    """
    top3 = hits[:3]
    hit = False
    hit_rank = None

    top3_forms = []
    top3_clause_ids = []

    for r in top3:
        meta = r["metadata"]
        form = meta.get("form_number", "")
        clause = meta.get("clause_id", "")
        top3_forms.append(form)
        top3_clause_ids.append(clause)

        form_match = form == expected_form
        text_match = expected_fragment.lower() in r["text"].lower()

        if form_match and text_match and not hit:
            hit = True
            hit_rank = r["rank"]

    return {
        "hit": hit,
        "hit_rank": hit_rank,
        "top3_forms": top3_forms,
        "top3_clause_ids": top3_clause_ids,
    }


def label_failure(hits: list[dict], question: dict) -> dict:
    """
    For a missed question, figure out WHY it failed.

    Labels:
      R   — Retrieval returned wrong chunks (correct chunk not in top-3)
      G   — Retrieval found a good chunk but the AI would misuse it
            (chunk is present in top-3 but still wrong-ish answer expected)
      NIC — Not-In-Corpus: the answer literally doesn't exist in the documents

    Logic used here:
      - If expected_form not in ANY of top-5 results → likely R or NIC
      - If expected_form IS in top-5 but not top-3 → R (just barely missed)
      - If correct form+fragment IS in top-3 but still "miss" → G (shouldn't happen with our checker, but possible)
      - If hit-check returned False and top-5 also don't contain fragment → could be NIC

    This is a heuristic — in a real system you'd manually inspect each one.
    """
    expected_form = question["expected_form"]
    expected_fragment = question["expected_clause_fragment"]

    # Check top-5 (broader window for diagnosis)
    top5 = hits[:5]
    forms_in_top5 = [r["metadata"].get("form_number", "") for r in top5]
    texts_in_top5 = [r["text"].lower() for r in top5]

    form_appears_in_top5 = expected_form in forms_in_top5
    fragment_in_top5 = any(expected_fragment.lower() in t for t in texts_in_top5)
    fragment_in_top3 = any(
        expected_fragment.lower() in r["text"].lower() for r in hits[:3]
    )

    if fragment_in_top3:
        # Fragment IS in top-3 → retrieval worked, but something else is off
        label = "G"
        evidence = (
            f"Expected fragment '{expected_fragment}' found in top-3 but form "
            f"mismatch or hit check failed. Top-3 forms: {forms_in_top5[:3]}"
        )
    elif fragment_in_top5:
        # Fragment found at rank 4 or 5 → retrieval almost worked, just not top-3
        label = "R"
        evidence = (
            f"Expected fragment '{expected_fragment}' found in top-5 but NOT top-3. "
            f"Form '{expected_form}' appeared but ranked below 3. "
            f"Exact-token retrieval weakness likely."
        )
    elif form_appears_in_top5:
        # Correct form returned but wrong clause/section
        label = "R"
        evidence = (
            f"Form '{expected_form}' appeared in top-5 but correct clause "
            f"'{expected_fragment}' was NOT in the returned chunks. "
            f"Vector search returned semantically similar but wrong clause."
        )
    else:
        # Neither form nor fragment appeared at all
        label = "R"
        evidence = (
            f"Form '{expected_form}' not found in top-5 at all. "
            f"Dense vector search completely missed the target document. "
            f"Likely an exact-token failure (exclusion code or form number in query)."
        )

    return {"label": label, "evidence": evidence}


def run_evaluation(strategy: str = "structure_aware", n_results: int = 5) -> dict:
    """
    Run the full evaluation pipeline:
      1. Load 12 golden questions
      2. For each: search, check hit@3, time it
      3. Label all misses
      4. Report hit-rate@3 and p50 latency

    Args:
        strategy: "structure_aware", "naive", or "hybrid"
        n_results: How many results to fetch (default 5 — we check top-3)
    """
    print(f"\n{BOLD}{CYAN}{'─'*65}{RESET}")
    print(f"{BOLD}{CYAN}  Golden-set evaluation — retriever: {strategy.upper()}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*65}{RESET}\n")

    # Load golden questions
    questions = load_golden_set(GOLDEN_SET_PATH)
    print(f"Loaded {len(questions)} golden questions from golden_set.jsonl\n")

    # Choose the search function
    if strategy == "hybrid":
        try:
            from hybrid_retrieval import hybrid_search
            search_fn = lambda q, n: hybrid_search(q, n_results=n)
        except ImportError:
            print(f"{RED}ERROR: hybrid_retrieval.py not found. "
                  f"Run with --strategy structure_aware first.{RESET}")
            sys.exit(1)
    else:
        search_fn = lambda q, n: vector_search(q, strategy=strategy, n_results=n)

    results = []
    latencies = []
    hits = 0
    misses = []

    # ── Run each question ──────────────────────────────────────────────────────
    for q in questions:
        qid = q["id"]
        question_text = q["question"]
        expected_form = q["expected_form"]
        expected_fragment = q["expected_clause_fragment"]
        has_exact_token = q.get("has_exact_token", False)

        # Time the search
        t_start = time.perf_counter()
        retrieved_hits = search_fn(question_text, n_results)
        t_end = time.perf_counter()
        latency_ms = (t_end - t_start) * 1000  # convert to milliseconds
        latencies.append(latency_ms)

        # Check hit@3
        hit_result = check_hit_at_3(retrieved_hits, expected_form, expected_fragment)
        is_hit = hit_result["hit"]

        if is_hit:
            hits += 1
            label = "HIT"
            evidence = f"Correct chunk at rank {hit_result['hit_rank']}"
            failure_label = None
            failure_evidence = None
        else:
            label = "MISS"
            failure_info = label_failure(retrieved_hits, q)
            failure_label = failure_info["label"]
            failure_evidence = failure_info["evidence"]
            misses.append({**q, "failure_label": failure_label, "failure_evidence": failure_evidence})

        # Print result
        icon = f"{GREEN}✅ HIT {RESET}" if is_hit else f"{RED}❌ MISS{RESET}"
        token_tag = f"{YELLOW}[exact-token]{RESET}" if has_exact_token else ""
        print(
            f"  Q{qid:02d} {icon} {token_tag} | {latency_ms:.0f}ms | "
            f"form={expected_form}"
        )
        print(f"       {DIM}{question_text[:80]}...{RESET}" if len(question_text) > 80
              else f"       {DIM}{question_text}{RESET}")
        if not is_hit:
            print(f"       {RED}Label: {failure_label} — {failure_evidence[:100]}{RESET}")
        print()

        results.append({
            "id": qid,
            "question": question_text,
            "expected_form": expected_form,
            "expected_fragment": expected_fragment,
            "has_exact_token": has_exact_token,
            "hit": is_hit,
            "hit_rank": hit_result.get("hit_rank"),
            "top3_forms": hit_result["top3_forms"],
            "top3_clause_ids": hit_result["top3_clause_ids"],
            "latency_ms": round(latency_ms, 1),
            "failure_label": failure_label,
            "failure_evidence": failure_evidence,
        })

    # ── Compute summary stats ─────────────────────────────────────────────────
    hit_rate = hits / len(questions)
    p50_latency = statistics.median(latencies)
    p90_latency = sorted(latencies)[int(len(latencies) * 0.9)]

    # Tally of failure labels
    r_count = sum(1 for m in misses if m["failure_label"] == "R")
    g_count = sum(1 for m in misses if m["failure_label"] == "G")
    nic_count = sum(1 for m in misses if m["failure_label"] == "Not-In-Corpus")

    print(f"\n{BOLD}{'─'*65}{RESET}")
    print(f"{BOLD}  Results Summary — {strategy.upper()}{RESET}")
    print(f"{'─'*65}")
    print(f"  Hit-rate@3 : {BOLD}{hits}/{len(questions)} = {hit_rate:.1%}{RESET}")
    print(f"  p50 latency: {BOLD}{p50_latency:.0f}ms{RESET}")
    print(f"  p90 latency: {p90_latency:.0f}ms")
    print(f"\n  Failure Tally:")
    print(f"    R (Retrieval)       : {r_count}")
    print(f"    G (Generation)      : {g_count}")
    print(f"    Not-In-Corpus (NIC) : {nic_count}")
    print(f"{'─'*65}\n")

    return {
        "strategy": strategy,
        "hit_rate": hit_rate,
        "hits": hits,
        "total": len(questions),
        "p50_latency_ms": round(p50_latency, 1),
        "p90_latency_ms": round(p90_latency, 1),
        "r_count": r_count,
        "g_count": g_count,
        "nic_count": nic_count,
        "results": results,
        "misses": misses,
    }


def print_comparison_table(before: dict, after: dict) -> None:
    """Print a nice before/after comparison table."""
    print(f"\n{BOLD}{CYAN}{'═'*65}{RESET}")
    print(f"{BOLD}{CYAN}  BEFORE vs AFTER Comparison{RESET}")
    print(f"{BOLD}{CYAN}{'═'*65}{RESET}")
    print(f"  {'Metric':<30} {'BEFORE (vector)':<20} {'AFTER (hybrid)':<20}")
    print(f"  {'─'*28} {'─'*18} {'─'*18}")

    before_hr = f"{before['hit_rate']:.1%} ({before['hits']}/{before['total']})"
    after_hr  = f"{after['hit_rate']:.1%} ({after['hits']}/{after['total']})"
    print(f"  {'Hit-rate@3':<30} {before_hr:<20} {after_hr:<20}")

    before_lat = f"{before['p50_latency_ms']:.0f}ms"
    after_lat  = f"{after['p50_latency_ms']:.0f}ms"
    print(f"  {'p50 Latency':<30} {before_lat:<20} {after_lat:<20}")
    print(f"{BOLD}{CYAN}{'═'*65}{RESET}\n")

    # Per-question table
    print(f"  {'Q#':<4} {'Has Exact Token':<18} {'BEFORE':<10} {'AFTER':<10} {'Status'}")
    print(f"  {'─'*3} {'─'*17} {'─'*9} {'─'*9} {'─'*15}")
    before_by_id = {r["id"]: r for r in before["results"]}
    after_by_id  = {r["id"]: r for r in after["results"]}

    for qid in sorted(before_by_id.keys()):
        b = before_by_id[qid]
        a = after_by_id.get(qid, {})
        b_hit = "✅ HIT" if b["hit"] else "❌ MISS"
        a_hit = "✅ HIT" if a.get("hit") else "❌ MISS"
        exact = "yes" if b["has_exact_token"] else "no"

        if not b["hit"] and a.get("hit"):
            status = f"{GREEN}FIXED ✅{RESET}"
        elif not b["hit"] and not a.get("hit"):
            status = f"{RED}still broken ❌{RESET}"
        elif b["hit"] and a.get("hit"):
            status = f"{DIM}unchanged ✅{RESET}"
        else:
            status = f"{YELLOW}regressed ⚠️{RESET}"

        print(f"  Q{qid:<3} {exact:<18} {b_hit:<10} {a_hit:<10} {status}")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PolicyLens golden-set retrieval evaluation")
    parser.add_argument(
        "--strategy",
        choices=["structure_aware", "naive", "hybrid", "both"],
        default="structure_aware",
        help="Which retrieval strategy to evaluate",
    )
    args = parser.parse_args()

    if args.strategy == "both":
        print(f"{BOLD}Running BEFORE (vector-only) evaluation...{RESET}")
        before_result = run_evaluation("structure_aware")

        print(f"\n{BOLD}Running AFTER (hybrid) evaluation...{RESET}")
        after_result = run_evaluation("hybrid")

        print_comparison_table(before_result, after_result)
    else:
        run_evaluation(args.strategy)
