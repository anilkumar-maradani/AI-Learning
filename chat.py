#!/usr/bin/env python3
"""
chat.py — PolicyLens interactive console.

Ask plain-English questions about the indexed homeowners endorsements and get
a grounded, cited answer — or an explicit refusal when the corpus does not
contain the answer.

Retrieval modes
    hybrid  (default)  BM25 keyword search + dense vector search, fused with
                       Reciprocal Rank Fusion. Handles exact tokens such as
                       "E-17" or "HO-0304 ed. 03-24" reliably.
    vector             Dense-only search over the structure-aware collection.

Usage
    python chat.py
    python chat.py --mode vector
    python chat.py --top-k 5

Console commands
    sources   show every chunk that fed the previous answer
    quit      leave the console
"""

import os
import sys
import argparse
from dotenv import load_dotenv

# Pull GROQ_API_KEY (and anything else) from a local .env before src imports run.
load_dotenv()

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from console import enable_utf8
enable_utf8()

from retrieval import search as vector_search
from generation import generate_answer

try:
    from hybrid_retrieval import hybrid_search
    HYBRID_AVAILABLE = True
except ImportError:
    HYBRID_AVAILABLE = False

# ── Terminal styling ─────────────────────────────────────────────────────────
MAGENTA = "\033[95m"
BLUE    = "\033[94m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RESET   = "\033[0m"

INDEXED_FORMS = ["HO-0304", "HO-0305", "HO-0306", "HO-0307", "HO-0308", "HO-0309"]

EXAMPLE_QUESTIONS = [
    "What is the named storm deductible under HO-0305?",
    "Does E-17 apply under HO-0304 ed. 03-24?",
    "Is mold damage excluded by HO-0306?",
    "How does HO-0304 define 'sudden and accidental'?",
    "Does HO-0308 exclude earthquake damage?",
    "What does HO-0309 say about business pursuits?",
]

RULE = f"{DIM}{'·' * 66}{RESET}"


def print_banner(mode_label: str, top_k: int) -> None:
    print()
    print(f"{BOLD}{MAGENTA}  PolicyLens{RESET}  {DIM}endorsement Q&A over your indexed policy forms{RESET}")
    print(RULE)
    print(f"  {DIM}forms      {RESET}{', '.join(INDEXED_FORMS)}")
    print(f"  {DIM}retrieval  {RESET}{mode_label}")
    print(f"  {DIM}top-k      {RESET}{top_k} chunks per question")
    print(f"  {DIM}commands   {RESET}{BOLD}sources{RESET}{DIM} (show last evidence) · {RESET}{BOLD}quit{RESET}")
    print(RULE)
    print(f"  {YELLOW}Try asking:{RESET}")
    for q in EXAMPLE_QUESTIONS:
        print(f"    {DIM}›{RESET} {q}")
    print()


def pick_search_fn(mode: str):
    """Return (search_fn, human_label) for the requested retrieval mode."""
    if mode == "hybrid" and HYBRID_AVAILABLE:
        return (lambda q, n: hybrid_search(q, n_results=n),
                f"{BOLD}hybrid{RESET} — BM25 + vector, RRF-fused")
    if mode == "hybrid":
        print(f"{YELLOW}  hybrid_retrieval unavailable — using dense vector search instead.{RESET}")
    return (lambda q, n: vector_search(q, strategy="structure_aware", n_results=n),
            f"{BOLD}vector{RESET} — dense only (structure-aware collection)")


def show_sources(hits: list[dict]) -> None:
    if not hits:
        print(f"{DIM}  No evidence yet — ask a question first.{RESET}")
        return
    print(f"\n{BOLD}{BLUE}  Evidence used for the last answer{RESET}")
    for h in hits:
        meta = h["metadata"]
        snippet = h["text"][:220].replace("\n", " ")
        print(f"  {BOLD}#{h['rank']}{RESET} {DIM}score={h['score']:.3f}{RESET}  "
              f"{meta.get('form_number', '?')} · {meta.get('clause_id', '?')} · "
              f"{DIM}{h['chunk_id']}{RESET}")
        print(f"     {DIM}{snippet}…{RESET}")
    print()


def run_chat(mode: str = "hybrid", top_k: int = 7) -> None:
    search_fn, mode_label = pick_search_fn(mode)
    print_banner(mode_label, top_k)

    if not os.environ.get("GROQ_API_KEY"):
        print(f"{RED}  GROQ_API_KEY is not set.{RESET}")
        print(f"  Copy .env.example to .env and paste your key, or set it in this shell:")
        print(f"    {BOLD}PowerShell:{RESET} $env:GROQ_API_KEY = \"gsk_...\"")
        print(f"    {BOLD}bash/zsh:  {RESET} export GROQ_API_KEY=gsk_...\n")
        sys.exit(1)

    last_hits: list[dict] = []

    while True:
        print(RULE)
        try:
            question = input(f"\n{BOLD}{MAGENTA}Ask ›{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n\n{DIM}Bye.{RESET}\n")
            break

        if not question:
            continue
        lowered = question.lower()
        if lowered in ("quit", "exit", "q", ":q"):
            print(f"\n{DIM}Bye.{RESET}\n")
            break
        if lowered in ("sources", "evidence", "why"):
            show_sources(last_hits)
            continue

        # ── Retrieve ────────────────────────────────────────────────────
        # top_k defaults to 7 rather than 5: short PREAMBLE chunks carry the
        # "[FORM ed. DATE]" prefix and tend to crowd the top ranks, so the
        # exclusion-table chunk that actually answers the question is often
        # at rank 4–5. Fetching a few extra keeps it in the LLM's context.
        print(f"\n{DIM}  searching…{RESET}", end="", flush=True)
        try:
            hits = search_fn(question, top_k)
        except Exception as exc:
            print(f"\r{RED}  retrieval failed: {exc}{RESET}")
            continue
        last_hits = hits

        print(f"\r{DIM}  {len(hits)} chunks retrieved — top matches:{RESET}")
        for h in hits[:3]:
            meta = h["metadata"]
            print(f"    {DIM}#{h['rank']}  {meta.get('form_number', '?'):<8} "
                  f"{meta.get('clause_id', '?')}  ({h['score']:.3f}){RESET}")

        # ── Generate ────────────────────────────────────────────────────
        print(f"\n{DIM}  composing answer…{RESET}", end="", flush=True)
        try:
            result = generate_answer(question, hits, verbose=False)
        except Exception as exc:
            print(f"\r{RED}  generation failed: {exc}{RESET}")
            continue

        print("\r", end="")
        if result["is_refusal"]:
            print(f"\n{BOLD}{RED}  ⛔ Not in corpus{RESET}")
            print(f"  {RED}{result['answer']}{RESET}")
        else:
            print(f"\n{BOLD}{GREEN}  ✔ Answer{RESET}")
            print(f"  {result['answer']}")
            if hits:
                meta = hits[0]["metadata"]
                print(f"\n  {DIM}primary source → {meta.get('source_file', '?')}  "
                      f"[{meta.get('form_number', '?')} / {meta.get('clause_id', '?')}]"
                      f"   type 'sources' for all evidence{RESET}")

    print(f"{DIM}Session closed.{RESET}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PolicyLens — endorsement Q&A console")
    parser.add_argument("--mode", choices=["hybrid", "vector"], default="hybrid",
                        help="retrieval mode (default: hybrid)")
    parser.add_argument("--top-k", type=int, default=7,
                        help="number of chunks passed to the model (default: 7)")
    args = parser.parse_args()
    run_chat(mode=args.mode, top_k=args.top_k)
