"""
evaluate.py — Known-answer retrieval harness (hit-in-top-5, both chunkers).

Runs 8 known-answer questions against both chunking strategies (search-only),
collects per-question hit-in-top-5, and writes the full raw dump.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(__file__))
from retrieval import hit_in_top5, search, metadata_filter_demo, format_results
from console import enable_utf8

enable_utf8()

# ---------------------------------------------------------------------------
# The 8 known-answer questions
# Written BEFORE looking at retrieval results — correctness verified from
# the endorsement text files directly.
# ---------------------------------------------------------------------------

QUESTIONS = [
    {
        "id": "Q1",
        "question": (
            "Does exclusion E-43 apply to water damage caused by a sewer or drain "
            "backup under endorsement NG-1101 ed. 01-26?"
        ),
        "expected_form": "NG-1101",
        "expected_clause": "EXCLUSION-TABLE",
        "expected_answer_fragment": "E-43",  # Must appear in retrieved text
        "note": "Table row — E-43 excludes sewer and drain backup, including municipal lines.",
    },
    {
        "id": "Q2",
        "question": (
            "What is the effective date of endorsement NG-1102 ed. 01-26?"
        ),
        "expected_form": "NG-1102",
        "expected_clause": "PREAMBLE",
        "expected_answer_fragment": "January 1, 2026",
        "note": "Header metadata — effective date January 1, 2026.",
    },
    {
        "id": "Q3",
        "question": (
            "Does exclusion E-61 in NG-1103 ed. 02-26 cover mold caused by "
            "condensation or high indoor humidity?"
        ),
        "expected_form": "NG-1103",
        "expected_clause": "EXCLUSION-TABLE",
        "expected_answer_fragment": "E-61",  # mold from seepage or humidity
        "note": "Table row — E-61 excludes mold from seepage, condensation or humidity.",
    },
    {
        "id": "Q4",
        "question": (
            "What policy line does endorsement NG-1104 ed. 02-26 modify?"
        ),
        "expected_form": "NG-1104",
        "expected_clause": "PREAMBLE",
        "expected_answer_fragment": "homeowners",
        "note": "Preamble header — policy_line is homeowners.",
    },
    {
        "id": "Q5",
        "question": (
            "Under endorsement NG-1105 ed. 03-26, does exclusion E-81 apply "
            "to damage caused by earth movement?"
        ),
        "expected_form": "NG-1105",
        "expected_clause": "EXCLUSION-TABLE",
        "expected_answer_fragment": "E-81",  # earth movement excluded
        "note": "Table row — E-81 excludes any loss caused by earth movement as defined in GM-1.",
    },
    {
        "id": "Q6",
        "question": (
            "What is the hurricane deductible amount or formula under "
            "NG-1102 ed. 01-26?"
        ),
        "expected_form": "NG-1102",
        "expected_clause": "CLAUSE-WH-1",
        "expected_answer_fragment": "2%",
        "note": "CLAUSE WH-1 — 2% of the Coverage A limit, once per named hurricane.",
    },
    {
        "id": "Q7",
        "question": (
            "Does endorsement NG-1106 ed. 03-26 exclude stock held for sale, "
            "and if so, what is its exclusion code?"
        ),
        "expected_form": "NG-1106",
        "expected_clause": "EXCLUSION-TABLE",
        "expected_answer_fragment": "E-91",  # stock held for sale
        "note": "Table row — E-91 is the stock-held-for-sale exclusion in NG-1106.",
    },
    {
        "id": "Q8",
        "question": (
            "Under NG-1101 ed. 01-26, what clause defines a 'sudden' escape of water "
            "and how long can the escape continue before it is treated as seepage?"
        ),
        "expected_form": "NG-1101",
        "expected_clause": "CLAUSE-WE-1",
        "expected_answer_fragment": "ten (10)",  # fewer than ten (10) days
        "note": "CLAUSE WE-1 — sudden only if it continued fewer than 10 days; else seepage (E-41).",
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
    "Does exclusion E-81 apply to earth movement damage?"
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
