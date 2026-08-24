"""
evaluate.py — Evaluation harness for Week 3 Practical Task Set D.

Runs 8 known-answer questions against both chunking strategies (search-only),
collects per-question hit-in-top-5, and writes the full raw dump.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))
from retrieval import hit_in_top5, search, metadata_filter_demo, format_results

# ---------------------------------------------------------------------------
# The 8 known-answer questions
# Written BEFORE looking at retrieval results — correctness verified from
# the endorsement text files directly.
# ---------------------------------------------------------------------------

QUESTIONS = [
    {
        "id": "Q1",
        "question": (
            "Does exclusion E-17 apply to water damage caused by a burst supply "
            "line under endorsement HO-0304 ed. 03-24?"
        ),
        "expected_form": "HO-0304",
        "expected_clause": "E-17",          # The exclusion table row
        "expected_answer_fragment": "E-17", # Must appear in retrieved text
        "note": "Table row — E-17 explicitly confirms coverage is NOT withheld.",
    },
    {
        "id": "Q2",
        "question": (
            "What is the effective date of endorsement HO-0305 ed. 03-24?"
        ),
        "expected_form": "HO-0305",
        "expected_clause": "SECTION-IV",
        "expected_answer_fragment": "March 15, 2024",
        "note": "Header metadata — effective date March 15, 2024.",
    },
    {
        "id": "Q3",
        "question": (
            "Does exclusion E-22 in HO-0306 ed. 04-24 cover mold damage?"
        ),
        "expected_form": "HO-0306",
        "expected_clause": "EXCLUSION-TABLE",
        "expected_answer_fragment": "E-22",  # mold damage — general exclusion
        "note": "Table row — E-22 excludes general mold damage.",
    },
    {
        "id": "Q4",
        "question": (
            "What policy line does endorsement HO-0307 ed. 04-24 modify?"
        ),
        "expected_form": "HO-0307",
        "expected_clause": "PREAMBLE",
        "expected_answer_fragment": "homeowners",
        "note": "Preamble header — policy_line is homeowners.",
    },
    {
        "id": "Q5",
        "question": (
            "Under endorsement HO-0308 ed. 05-24, does exclusion E-31 apply "
            "to damage caused by earth movement?"
        ),
        "expected_form": "HO-0308",
        "expected_clause": "EXCLUSION-TABLE",
        "expected_answer_fragment": "E-31",  # earth movement excluded
        "note": "Table row — E-31 excludes all forms of earth movement.",
    },
    {
        "id": "Q6",
        "question": (
            "What is the Named Storm deductible amount or formula under "
            "HO-0305 ed. 03-24?"
        ),
        "expected_form": "HO-0305",
        "expected_clause": "CLAUSE-NS-2",
        "expected_answer_fragment": "2%",
        "note": "CLAUSE NS-2 — $5,000 or 2% of Coverage A, whichever greater.",
    },
    {
        "id": "Q7",
        "question": (
            "Does endorsement HO-0309 ed. 05-24 contain a business pursuits "
            "exclusion, and if so, what is its exclusion code?"
        ),
        "expected_form": "HO-0309",
        "expected_clause": "EXCLUSION-TABLE",
        "expected_answer_fragment": "E-19",  # business pursuits
        "note": "Table row — E-19 is the business pursuits exclusion in HO-0309.",
    },
    {
        "id": "Q8",
        "question": (
            "Under HO-0304 ed. 03-24, what clause defines 'sudden and accidental' "
            "and what is the time limit for continuous leakage before coverage is lost?"
        ),
        "expected_form": "HO-0304",
        "expected_clause": "CLAUSE-WD-1",
        "expected_answer_fragment": "14",   # 14 consecutive days
        "note": "CLAUSE WD-1 — sudden and accidental; 14-day seepage limit.",
    },
]

# ---------------------------------------------------------------------------
# Run evaluation
# ---------------------------------------------------------------------------

def run_evaluation(verbose: bool = True) -> dict:
    """
    Run all 8 questions against both strategies.
    Returns a summary dict with per-question records and totals.
    """
    strategies = ["naive", "structure_aware"]
    records = []

    for q in QUESTIONS:
        row = {
            "id": q["id"],
            "question": q["question"],
            "expected_form": q["expected_form"],
            "expected_clause": q["expected_clause"],
            "note": q["note"],
        }
        for strat in strategies:
            result = hit_in_top5(
                q["question"],
                q["expected_form"],
                q["expected_answer_fragment"],
                strategy=strat,
                n_results=5,
            )
            row[f"hit_{strat}"] = result["hit"]
            row[f"rank_{strat}"] = result["rank"]
            row[f"results_{strat}"] = result["results"]

            if verbose:
                hit_str = f"✅ rank={result['rank']}" if result["hit"] else "❌ miss"
                print(
                    f"  [{strat:>15s}] {q['id']}: {hit_str} | "
                    f"form={q['expected_form']} clause≈{q['expected_answer_fragment']}"
                )
        records.append(row)

    naive_hits = sum(1 for r in records if r["hit_naive"])
    sa_hits = sum(1 for r in records if r["hit_structure_aware"])

    summary = {
        "records": records,
        "naive_score": f"{naive_hits}/8",
        "sa_score": f"{sa_hits}/8",
        "naive_hits": naive_hits,
        "sa_hits": sa_hits,
    }

    if verbose:
        print(f"\n{'='*50}")
        print(f"  NAIVE score:           {naive_hits}/8")
        print(f"  STRUCTURE-AWARE score: {sa_hits}/8")
        print(f"{'='*50}")

    return summary


# ---------------------------------------------------------------------------
# Metadata filter demo
# ---------------------------------------------------------------------------

FILTER_DEMO_QUERY = (
    "Does exclusion E-31 apply to earth movement damage?"
)

def run_filter_demo(verbose: bool = True) -> dict:
    """Run the metadata filter demo query and return both result lists."""
    demo = metadata_filter_demo(
        FILTER_DEMO_QUERY,
        policy_line="homeowners",
        strategy="structure_aware",
        n_results=5,
    )
    if verbose:
        print(f"\nFilter demo query: '{FILTER_DEMO_QUERY}'")
        print("\n--- UNFILTERED (top-5) ---")
        print(format_results(demo["unfiltered"]))
        print("\n--- FILTERED: policy_line=homeowners (top-5) ---")
        print(format_results(demo["filtered"]))
    return demo


if __name__ == "__main__":
    print("Running evaluation harness...\n")
    summary = run_evaluation(verbose=True)
    print("\nRunning metadata filter demo...\n")
    run_filter_demo(verbose=True)
